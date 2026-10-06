"""
Wall pattern application, ported verbatim from
`homexperia-client-backend/utils/wall.py`.
"""

from __future__ import annotations

import math
import time
from pathlib import Path

import cv2
import numpy as np

from .shared import blend_hard_replace


def tile_texture(pattern: np.ndarray, area_w: int, area_h: int, tile_size_w: float) -> np.ndarray:
    ph, pw = pattern.shape[:2]
    scale = tile_size_w / float(pw)
    tile_size_h = max(1, int(ph * scale))
    tile = cv2.resize(pattern, (max(1, int(tile_size_w)), tile_size_h), interpolation=cv2.INTER_LANCZOS4)
    th, tw = tile.shape[:2]
    if th == 0 or tw == 0:
        return np.zeros((area_h, area_w, 3), dtype=np.uint8)
    # np.tile instead of a manual nested-loop stamp — same result, faster.
    reps_y = -(-area_h // th)
    reps_x = -(-area_w // tw)
    grid_out = np.tile(tile, (reps_y, reps_x, 1))
    return grid_out[:area_h, :area_w]


def create_super_texture(
    pattern: np.ndarray, target_w: int, target_h: int, tile_size_w: float, pad_x_tiles: int = 1, pad_y_tiles: int = 1
) -> tuple[np.ndarray, np.ndarray]:
    """pad_x_tiles/pad_y_tiles: how many tile-widths/heights of padding to
    build around the target area, beyond the flat single-tile default — a
    plane whose warp needs to reach further past its own quad edges to
    cover every masked pixel (see wall_depth.py::_warp_plane) asks for more
    here. Defaults preserve the original single-tile-of-padding behavior."""
    ph, pw = pattern.shape[:2]
    tw = max(1, int(tile_size_w))
    th = max(1, int(ph * (tile_size_w / float(pw))))
    pad_w = tw * max(1, int(pad_x_tiles))
    pad_h = th * max(1, int(pad_y_tiles))
    total_w = target_w + 2 * pad_w
    total_h = target_h + 2 * pad_h
    super_tex = tile_texture(pattern, total_w, total_h, tile_size_w)
    src_points = np.array([
        [pad_w, pad_h],
        [pad_w + target_w, pad_h],
        [pad_w + target_w, pad_h + target_h],
        [pad_w, pad_h + target_h]
    ], dtype="float32")
    return super_tex, src_points


def _is_valid_perspective_angles(quad, min_deg=50, max_deg=130) -> bool:
    """Calculates the 4 internal angles of the quad. Rejects extreme
    skews if angles fall outside the acceptable architectural range."""
    for i in range(4):
        p1 = quad[i - 1]
        p2 = quad[i]
        p3 = quad[(i + 1) % 4]

        v1 = p1 - p2
        v2 = p3 - p2

        cos_theta = np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2) + 1e-7)
        angle = np.degrees(np.arccos(np.clip(cos_theta, -1.0, 1.0)))

        if angle < min_deg or angle > max_deg:
            return False
    return True


def _get_avg_line(line_list):
    """Length-weighted average of the (up to) 3 longest (slope, intercept,
    length) candidates. Shared by the top/bottom AND left/right Hough
    fits below - the math is identical regardless of which axis the
    slope/intercept are parameterized against."""
    if not line_list:
        return None, None
    line_list.sort(key=lambda l: l[2], reverse=True)
    best = line_list[:3]
    tot_len = sum(l[2] for l in best)
    if tot_len == 0:
        return None, None
    return sum(l[0] * l[2] for l in best) / tot_len, sum(l[1] * l[2] for l in best) / tot_len


def _intersect_line(m_yx, c_yx, m_xy, c_xy, fallback_x, fallback_y):
    """Intersect a y=m*x+c line (top or bottom edge) with an x=m*y+c line
    (left or right edge). Falls back to the given point (typically the
    old shared-x evaluation) if the two lines are ~parallel."""
    denom = 1 - m_xy * m_yx
    if abs(denom) < 1e-6:
        return fallback_x, fallback_y
    px = (m_xy * c_yx + c_xy) / denom
    py = m_yx * px + c_yx
    return px, py


def detect_wall_quad(mask_gray: np.ndarray, debug_img: np.ndarray | None = None, debug_dir: Path | None = None) -> np.ndarray | None:
    """
    Port of `utils/wall.py::_detect_wall_quad`, extended to fit the left
    and right edges as their own independent lines (see
    `_left_right_lines_hough`/`_left_right_lines_profile` below) instead
    of evaluating the top/bottom line fits at a single shared x per side.
    The original approach forced corners 0/3 (top-left/bottom-left) to
    share one x value and corners 1/2 (top-right/bottom-right) to share
    another, which cannot represent a real photographed wall's vanishing-
    point perspective (independently-sloped left/right edges) and, worse,
    drags the whole corner out to the mask's raw bounding-box edge
    whenever even a thin sliver of mask touches it - confirmed against a
    real external reference this was a measured, non-tunable gap (even an
    aggressive percentile trim of the shared x only closed a fraction of
    it). When there isn't enough line data to fit left/right independently,
    this degrades to the exact original shared-x behavior for that side.

    Debug image write (`Debugs/wall_quad_debug_<ts>.jpg` in the
    original, unconditionally created whenever `debug_img` was passed)
    now only happens if `debug_dir` is not None, per the parity-
    preserving fix requested for this module: pass a `debug_dir` to
    opt in, matching how `apply_pattern` below wires it through.
    """
    H, W = mask_gray.shape
    contours, _ = cv2.findContours(mask_gray, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None

    largest = max(contours, key=cv2.contourArea)
    x, y, w, h = cv2.boundingRect(largest)

    def _left_right_lines_hough(clean_boundary):
        # Same Hough segments as the top/bottom fit below, but keeping the
        # roughly-VERTICAL ones (the top/bottom fit explicitly discards
        # these via its abs(slope) > 1.0 check) and fitting them as
        # x = m*y + c instead of y = m*x + c.
        lines = cv2.HoughLinesP(clean_boundary, 1, np.pi / 180, threshold=20, minLineLength=max(40, h // 8), maxLineGap=20)
        left_lines, right_lines = [], []
        if lines is not None:
            for line in lines.reshape(-1, 4):
                x1, y1, x2, y2 = line
                dx, dy = float(x2 - x1), float(y2 - y1)
                if abs(dy) < 1e-3:
                    continue
                slope = dx / dy
                if abs(slope) > 1.0:
                    continue
                intercept = x1 - slope * y1
                mx = (x1 + x2) / 2.0
                length = math.hypot(dx, dy)
                if mx < x + w * 0.35:
                    left_lines.append((slope, intercept, length))
                elif mx > x + w * 0.65:
                    right_lines.append((slope, intercept, length))
        return _get_avg_line(left_lines), _get_avg_line(right_lines)

    def _left_right_lines_profile():
        # Mirrors top_profile/bot_profile below, but per-ROW instead of
        # per-COLUMN: leftmost/rightmost mask x at each row.
        left_profile, right_profile = [], []
        for row in range(y, y + h):
            row_data = mask_gray[row, :]
            x_indices = np.where(row_data > 0)[0]
            if len(x_indices) > 0:
                left_profile.append([row, x_indices[0]])
                right_profile.append([row, x_indices[-1]])

        if len(left_profile) < 10 or len(right_profile) < 10:
            return (None, None), (None, None)
        lp, rp = np.array(left_profile, dtype=np.float32), np.array(right_profile, dtype=np.float32)

        def _robust_line(pts, keep_low):
            spread = np.max(pts[:, 0]) - np.min(pts[:, 0])
            if spread < h * 0.15:
                return 0.0, float(np.median(pts[:, 1]))

            x_vals = pts[:, 1]
            thresh = np.percentile(x_vals, 50)
            valid_pts = pts[x_vals <= thresh] if keep_low else pts[x_vals >= thresh]
            if len(valid_pts) < 10:
                valid_pts = pts

            vx, vy, cx, cy = cv2.fitLine(valid_pts, cv2.DIST_L1, 0, 0.01, 0.01)
            if abs(vx[0]) < 1e-3:
                return 0.0, float(np.median(valid_pts[:, 1]))

            m = np.clip(float(vy[0] / vx[0]), -0.25, 0.25)
            c = float(np.median(valid_pts[:, 1]) - m * np.median(valid_pts[:, 0]))
            return m, c

        return _robust_line(lp, True), _robust_line(rp, False)

    def _corners_from_lines(mt, ct, mb, cb, ml, cl, mr, cr, xl, xr):
        # ml/mr are None when there wasn't enough independent left/right
        # line data - degrade to a vertical line at the old shared x for
        # that side, i.e. the original behavior.
        if ml is None:
            ml, cl = 0.0, xl
        if mr is None:
            mr, cr = 0.0, xr

        tl_x, tl_y = _intersect_line(mt, ct, ml, cl, xl, mt * xl + ct)
        tr_x, tr_y = _intersect_line(mt, ct, mr, cr, xr, mt * xr + ct)
        br_x, br_y = _intersect_line(mb, cb, mr, cr, xr, mb * xr + cb)
        bl_x, bl_y = _intersect_line(mb, cb, ml, cl, xl, mb * xl + cb)
        return np.array([[tl_x, tl_y], [tr_x, tr_y], [br_x, br_y], [bl_x, bl_y]], dtype=np.float32)

    def _hough_based_quad():
        clean_boundary = np.zeros_like(mask_gray)
        cv2.drawContours(clean_boundary, [largest], -1, 255, 1)
        lines = cv2.HoughLinesP(clean_boundary, 1, np.pi / 180, threshold=20, minLineLength=max(40, w // 8), maxLineGap=20)

        top_lines, bot_lines = [], []
        if lines is not None:
            # cv2.HoughLinesP doesn't reliably return the documented (N,1,4)
            # shape - reshape defensively rather than assume line[0] indexes.
            for line in lines.reshape(-1, 4):
                x1, y1, x2, y2 = line
                dx, dy = float(x2 - x1), float(y2 - y1)
                if abs(dx) < 1e-3:
                    continue

                slope = dy / dx
                if abs(slope) > 1.0:
                    continue

                intercept = y1 - slope * x1
                my = (y1 + y2) / 2.0
                length = math.hypot(dx, dy)

                if my < y + h * 0.35:
                    top_lines.append((slope, intercept, length))
                elif my > y + h * 0.65:
                    bot_lines.append((slope, intercept, length))

        mt, ct = _get_avg_line(top_lines)
        mb, cb = _get_avg_line(bot_lines)

        if mt is None or mb is None:
            return None

        xl, xr = float(x), float(x + w)
        tl_y, tr_y = mt * xl + ct, mt * xr + ct
        bl_y, br_y = mb * xl + cb, mb * xr + cb

        if tl_y >= bl_y - 10 or tr_y >= br_y - 10:
            return None

        (ml, cl), (mr, cr) = _left_right_lines_hough(clean_boundary)
        quad = _corners_from_lines(mt, ct, mb, cb, ml, cl, mr, cr, xl, xr)

        if not _is_valid_perspective_angles(quad):
            return None

        return quad

    def _profile_based_quad():
        top_profile, bot_profile = [], []
        for col in range(x, x + w):
            col_data = mask_gray[:, col]
            y_indices = np.where(col_data > 0)[0]
            if len(y_indices) > 0:
                top_profile.append([col, y_indices[0]])
                bot_profile.append([col, y_indices[-1]])

        if len(top_profile) < 10 or len(bot_profile) < 10:
            return None
        tp, bp = np.array(top_profile, dtype=np.float32), np.array(bot_profile, dtype=np.float32)

        def _robust_line(pts, is_top):
            spread = np.max(pts[:, 0]) - np.min(pts[:, 0])
            if spread < w * 0.15:
                return 0.0, float(np.median(pts[:, 1]))

            y_vals = pts[:, 1]
            thresh = np.percentile(y_vals, 50)
            valid_pts = pts[y_vals <= thresh] if is_top else pts[y_vals >= thresh]
            if len(valid_pts) < 10:
                valid_pts = pts

            vx, vy, cx, cy = cv2.fitLine(valid_pts, cv2.DIST_L1, 0, 0.01, 0.01)
            if abs(vx[0]) < 1e-3:
                return 0.0, float(np.median(valid_pts[:, 1]))

            m = np.clip(float(vy[0] / vx[0]), -0.25, 0.25)
            c = float(np.median(valid_pts[:, 1]) - m * np.median(valid_pts[:, 0]))
            return m, c

        mt, ct = _robust_line(tp, True)
        mb, cb = _robust_line(bp, False)

        xl, xr = float(x), float(x + w)
        tl_y, tr_y = mt * xl + ct, mt * xr + ct
        bl_y, br_y = mb * xl + cb, mb * xr + cb

        if tl_y >= bl_y or tr_y >= br_y:
            mt, mb = 0.0, 0.0
            ct, cb = float(np.min(tp[:, 1])), float(np.max(bp[:, 1]))
            tl_y, tr_y, bl_y, br_y = ct, ct, cb, cb

        (ml, cl), (mr, cr) = _left_right_lines_profile()
        return _corners_from_lines(mt, ct, mb, cb, ml, cl, mr, cr, xl, xr)

    active_method = "HOUGH (PRIMARY)"
    quad = _hough_based_quad()

    if quad is None:
        active_method = "PROFILE (FALLBACK)"
        quad = _profile_based_quad()

    if quad is None:
        return None

    if debug_img is not None and debug_dir is not None:
        debug_dir.mkdir(parents=True, exist_ok=True)
        dbg = debug_img.copy()

        color = (0, 0, 255) if "HOUGH" in active_method else (0, 255, 255)
        cv2.polylines(dbg, [quad.astype(np.int32)], True, color, 3)
        cv2.putText(dbg, active_method, (int(x), max(30, int(y) - 10)), cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)

        cv2.imwrite(str(debug_dir / f"wall_quad_debug_{int(time.time())}.jpg"), dbg)

    return quad


def apply_pattern(
    base_image: np.ndarray,
    mask: np.ndarray,
    texture_image: np.ndarray,
    settings: dict,
    debug_dir: Path | None = None,
) -> np.ndarray:
    """
    Port of `utils/wall.py::apply_pattern`.

    `settings` keys read (same names as the original
    `process_single_layer` call site). Note: `process_single_layer`
    computes `repeat` once, shared across all categories, defaulting to
    12 (NOT `wall.apply_pattern`'s own internal `fallback_repeat=3`
    default, which is only reached when called directly outside
    `process_single_layer`). This port matches the real runtime default
    (12) to preserve actual observed behavior:
      - "repeat" (int, default 12) -> fallback_repeat
      - room height in px and product width in cm are passed by the
        caller today as `room_height_px=current_image.shape[0]` and
        `product_width_cm=pattern_real_width` — i.e. they are not
        `settings` dict keys at all in the original call site,
        `room_height_px` is derived from the image itself and
        `product_width_cm` comes from the product's parsed width, not
        from `settings`. This port keeps that behavior: `room_height_px`
        is computed from `base_image.shape[0]` internally, and
        `product_width_cm` is read from `settings.get("productWidthCm")`
        if present (there is no such key in the original settings dict;
        it is exposed here only as a defensive extension point). If the
        real caller has the parsed `pattern_real_width` available, it
        should pass it via `settings["productWidthCm"]` — flagged
        explicitly since this is the one place the new dict-based
        signature can't losslessly represent the original's non-dict
        `product_width_cm` argument.

    `debug_dir`: optional, forwarded to `detect_wall_quad` for the
    perspective-quad debug image. The original wrote this
    unconditionally to `Debugs/`; here it is opt-in only.
    """
    room_img = base_image
    wall_tex = texture_image
    mask_img = mask

    # settings.get("repeat", 12) is NOT a safe way to default this: the
    # HotspotSettings Pydantic model always includes the "repeat" key, set
    # to None when the admin never configured it - .get()'s default only
    # kicks in for a MISSING key, not a present-but-None one, so int(None)
    # was throwing (silently swallowed by _process_single_layer's outer
    # except, returning the room untouched) on every hotspot without an
    # explicit repeat value - i.e. most of them.
    repeat_raw = settings.get("repeat")
    fallback_repeat = int(repeat_raw) if repeat_raw is not None else 12
    room_height_px = room_img.shape[0]
    product_width_cm = settings.get("productWidthCm")

    H, W = room_img.shape[:2]

    if len(mask_img.shape) == 3:
        mask_gray = cv2.cvtColor(mask_img, cv2.COLOR_BGR2GRAY)
    else:
        mask_gray = mask_img

    mask_gray = cv2.resize(mask_gray, (W, H), interpolation=cv2.INTER_NEAREST)
    _, thresh = cv2.threshold(mask_gray, 127, 255, cv2.THRESH_BINARY)

    pts_dst = detect_wall_quad(thresh, debug_img=room_img, debug_dir=debug_dir)
    if pts_dst is None:
        return room_img

    try:
        dst_w = max(np.linalg.norm(pts_dst[0] - pts_dst[1]), np.linalg.norm(pts_dst[3] - pts_dst[2]))
        dst_h = max(np.linalg.norm(pts_dst[0] - pts_dst[3]), np.linalg.norm(pts_dst[1] - pts_dst[2]))

        # A repeat of 0 is meaningless for tiling (and, unguarded, sends
        # tile_size_w below to a division by zero) - the frontend sends 0
        # deliberately for wall_art/unrecognized categories where this
        # function was never meant to be reached, but guard it here too
        # rather than let a bad category mapping silently no-op the whole
        # apply.
        calculated_repeat = max(1, fallback_repeat)

        if room_height_px and product_width_cm:
            cm_per_px = 335.28 / float(room_height_px)
            estimated_wall_width_cm = (dst_w * cm_per_px)

            safe_product_cm = max(15.0, float(product_width_cm))

            raw_repeat = estimated_wall_width_cm / safe_product_cm
            calculated_repeat = max(1, int(round(raw_repeat)))

        tile_size_w = dst_w / calculated_repeat

        super_tex, pts_src = create_super_texture(wall_tex, int(dst_w), int(dst_h), tile_size_w)

        M = cv2.getPerspectiveTransform(pts_src, pts_dst)
        warped_tex = cv2.warpPerspective(super_tex, M, (W, H), flags=cv2.INTER_LINEAR)

        # detect_wall_quad fits a simple 4-corner quad to mask_gray's real
        # (often irregular) boundary, so the two rarely match exactly - any
        # sliver of the real mask that falls outside the fitted quad has no
        # texture warped into it there (warpPerspective's default border
        # fill is black), and blend_hard_replace would paint that black
        # straight onto the wall as if it were real product color, muddying
        # those edges toward black rather than leaving the original photo
        # showing through. Warp a plain white canvas through the same
        # transform to find exactly which pixels really received texture,
        # and only blend within that overlap.
        warp_validity = cv2.warpPerspective(
            np.full(super_tex.shape[:2], 255, dtype=np.uint8), M, (W, H), flags=cv2.INTER_NEAREST
        )
        effective_mask = cv2.bitwise_and(mask_gray, warp_validity)

        return blend_hard_replace(room_img, warped_tex, effective_mask, shadow_strength=0.4)
    except Exception:
        return room_img

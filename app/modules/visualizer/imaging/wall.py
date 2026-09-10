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
    tile = cv2.resize(pattern, (int(tile_size_w), tile_size_h), interpolation=cv2.INTER_LANCZOS4)
    th, tw = tile.shape[:2]
    if th == 0 or tw == 0:
        return np.zeros((area_h, area_w, 3), dtype=np.uint8)
    grid_h, grid_w = area_h + th, area_w + tw
    grid_out = np.zeros((grid_h, grid_w, 3), dtype=np.uint8)
    for y in range(0, grid_h, th):
        for x in range(0, grid_w, tw):
            h_slice = min(th, grid_h - y)
            w_slice = min(tw, grid_w - x)
            grid_out[y:y + h_slice, x:x + w_slice] = tile[:h_slice, :w_slice]
    return grid_out[:area_h, :area_w]


def create_super_texture(
    pattern: np.ndarray, target_w: int, target_h: int, tile_size_w: float
) -> tuple[np.ndarray, np.ndarray]:
    pad_w = target_w
    pad_h = target_h
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


def detect_wall_quad(mask_gray: np.ndarray, debug_img: np.ndarray | None = None, debug_dir: Path | None = None) -> np.ndarray | None:
    """
    Port of `utils/wall.py::_detect_wall_quad`.

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

        def _get_avg(line_list):
            if not line_list:
                return None, None
            line_list.sort(key=lambda l: l[2], reverse=True)
            best = line_list[:3]
            tot_len = sum(l[2] for l in best)
            if tot_len == 0:
                return None, None
            return sum(l[0] * l[2] for l in best) / tot_len, sum(l[1] * l[2] for l in best) / tot_len

        mt, ct = _get_avg(top_lines)
        mb, cb = _get_avg(bot_lines)

        if mt is None or mb is None:
            return None

        xl, xr = float(x), float(x + w)
        tl_y, tr_y = mt * xl + ct, mt * xr + ct
        bl_y, br_y = mb * xl + cb, mb * xr + cb

        if tl_y >= bl_y - 10 or tr_y >= br_y - 10:
            return None
        quad = np.array([[xl, tl_y], [xr, tr_y], [xr, br_y], [xl, bl_y]], dtype=np.float32)

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

        return np.array([[xl, tl_y], [xr, tr_y], [xr, br_y], [xl, bl_y]], dtype=np.float32)

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

    fallback_repeat = int(settings.get("repeat", 12))
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

        calculated_repeat = fallback_repeat

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

        return blend_hard_replace(room_img, warped_tex, mask_gray, shadow_strength=0.4)
    except Exception:
        return room_img

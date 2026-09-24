"""
Floor pattern application, ported verbatim from
`homexperia-client-backend/utils/floor.py`.
"""

from __future__ import annotations

import math

import cv2
import numpy as np

from .shared import blend_hard_replace


def _weighted_median(values, weights):
    if not values:
        return None
    order = np.argsort(np.asarray(values))
    vals = np.asarray(values, dtype=np.float64)[order]
    wts = np.asarray(weights, dtype=np.float64)[order]
    cum = np.cumsum(wts)
    idx = int(np.searchsorted(cum, cum[-1] * 0.5))
    return float(vals[min(idx, len(vals) - 1)])


def detect_floor_quad(room_img: np.ndarray) -> tuple[np.ndarray, int] | None:
    """
    Port of `utils/floor.py::_detect_floor_quad`.

    Analyzes the base image to calculate the true 3D perspective quad of
    the room floor. Returns (quad, floor_top_y).

    Note on the "or None" in the exposed signature: the original
    function has no failure path that returns None — every branch
    (Hough-line detection succeeding or not) falls through to a
    clamped/defaulted quad via the low-confidence fallback
    (`left_conf < 3 or right_conf < 3`) and always returns a quad. This
    port preserves that: it never actually returns None, matching the
    original's unconditional-return behavior exactly. The `| None` in
    the exposed type hint is kept only because callers may still want
    defensive handling; behaviorally this always yields a
    `(quad, floor_top_y)` tuple, and any error results in an exception
    (caught by the caller's apply_pattern try/except), not a None
    return, exactly as in the original.
    """
    H_orig, W_orig = room_img.shape[:2]

    MAX_PROC_W = 1536
    if W_orig > MAX_PROC_W:
        proc_scale = MAX_PROC_W / W_orig
        proc_img = cv2.resize(room_img, (MAX_PROC_W, int(H_orig * proc_scale)))
    else:
        proc_scale = 1.0
        proc_img = room_img

    H, W = proc_img.shape[:2]
    gray = cv2.cvtColor(proc_img, cv2.COLOR_BGR2GRAY)

    lower_y0 = max(0, int(H * 0.10))
    edges_full = cv2.Canny(gray[lower_y0:H, :], 35, 115)
    lines_full = cv2.HoughLinesP(
        edges_full, 1, np.pi / 180,
        threshold=max(22, W // 24),
        minLineLength=max(26, W // 9),
        maxLineGap=max(20, W // 24),
    )

    left_segs, right_segs = [], []
    if lines_full is not None:
        # cv2.HoughLinesP doesn't reliably return the documented (N,1,4)
        # shape - reshape defensively rather than assume [:, 0] unpacks.
        for x1_, y1_, x2_, y2_ in lines_full.reshape(-1, 4):
            y1g = y1_ + lower_y0
            y2g = y2_ + lower_y0
            dx = float(x2_ - x1_)
            dy = float(y2g - y1g)
            if math.hypot(dx, dy) < max(24.0, W * 0.03):
                continue
            if abs(dy) < 12.0:
                continue
            slope = dy / (dx + 1e-6)
            if abs(slope) < 0.18 or abs(slope) > 8.0:
                continue
            xm = (x1_ + x2_) * 0.5
            if slope < 0 and xm < W * 0.62:
                left_segs.append((x1_, y1g, x2_, y2g))
            elif slope > 0 and xm > W * 0.38:
                right_segs.append((x1_, y1g, x2_, y2g))

    MAX_SEGS = 15
    if len(left_segs) > MAX_SEGS:
        left_segs = sorted(left_segs, key=lambda s: math.hypot(s[2] - s[0], s[3] - s[1]), reverse=True)[:MAX_SEGS]
    if len(right_segs) > MAX_SEGS:
        right_segs = sorted(right_segs, key=lambda s: math.hypot(s[2] - s[0], s[3] - s[1]), reverse=True)[:MAX_SEGS]

    edges_all = cv2.Canny(gray, 28, 90)
    x0s, x1s = int(W * 0.08), int(W * 0.92)
    row_dens = np.mean(edges_all[:, x0s:x1s].astype(np.float32), axis=1)

    smooth_k = max(10, H // 55)
    row_sm = np.convolve(row_dens, np.ones(smooth_k) / smooth_k, mode='same')

    y_scan_lo = int(H * 0.30)
    y_scan_hi = int(H * 0.82)
    zone = row_sm[y_scan_lo:y_scan_hi]
    threshold = max(float(np.std(zone)) * 0.50, 3.0)

    win = max(20, H // 30)
    floor_top_y = int(H * 0.62)
    for y in range(y_scan_hi, y_scan_lo, -1):
        above = float(np.mean(row_sm[max(0, y - win):y]))
        below = float(np.mean(row_sm[y:min(H, y + win)]))
        if above - below >= threshold:
            floor_top_y = y
            break

    ref_lo = max(int(H * 0.30), floor_top_y - int(H * 0.08))
    ref_hi = min(int(H * 0.84), floor_top_y + int(H * 0.08))
    roi_ref = gray[ref_lo:ref_hi, int(W * 0.04):int(W * 0.96)]
    edges_ref = cv2.Canny(roi_ref, 28, 95)
    lines_ref = cv2.HoughLinesP(
        edges_ref, 1, np.pi / 180,
        threshold=max(22, W // 22),
        minLineLength=max(28, W // 8),
        maxLineGap=max(20, W // 22),
    )
    if lines_ref is not None:
        floor_top_y_init = floor_top_y
        best_score, best_y = 0.0, floor_top_y
        for x1_, y1_, x2_, y2_ in lines_ref.reshape(-1, 4):
            if abs(y2_ - y1_) > 14:
                continue
            length = math.hypot(x2_ - x1_, y2_ - y1_)
            gy = int((y1_ + y2_) * 0.5) + ref_lo
            dist = abs(gy - floor_top_y_init)
            score = (length / W) * math.exp(-dist / (H * 0.04))
            if score > best_score:
                best_score = score
                best_y = gy
        if best_score > 0.10:
            floor_top_y = best_y

    floor_top_y = max(int(H * 0.33), min(int(H * 0.82), floor_top_y))

    left_top_hits, left_top_w = [], []
    left_bot_hits, left_bot_w = [], []
    right_top_hits, right_top_w = [], []
    right_bot_hits, right_bot_w = [], []

    for (x1_, y1g, x2_, y2g) in left_segs + right_segs:
        dx = float(x2_ - x1_)
        dy = float(y2g - y1g)
        seg_len = math.hypot(dx, dy)
        slope = dy / (dx + 1e-6)
        inv = dx / dy
        x_at_top = x1_ + (floor_top_y - y1g) * inv
        x_at_bottom = x1_ + (H - 1 - y1g) * inv
        if not (-0.35 * W <= x_at_top <= 1.35 * W and -0.45 * W <= x_at_bottom <= 1.45 * W):
            continue
        xm = (x1_ + x2_) * 0.5
        sw = seg_len * (1.0 + min(1.0, abs(slope) / 2.5))
        if slope < 0 and xm < W * 0.62:
            left_top_hits.append(x_at_top)
            left_top_w.append(sw)
            left_bot_hits.append(x_at_bottom)
            left_bot_w.append(sw)
        if slope > 0 and xm > W * 0.38:
            right_top_hits.append(x_at_top)
            right_top_w.append(sw)
            right_bot_hits.append(x_at_bottom)
            right_bot_w.append(sw)

    left_top_x = _weighted_median(left_top_hits, left_top_w)
    left_bottom_x = _weighted_median(left_bot_hits, left_bot_w)
    right_top_x = _weighted_median(right_top_hits, right_top_w)
    right_bottom_x = _weighted_median(right_bot_hits, right_bot_w)

    left_conf = len(left_top_hits)
    right_conf = len(right_top_hits)

    if left_conf < 3 or right_conf < 3:
        left_top_x = W * 0.08
        right_top_x = W * 0.92
        left_bottom_x = W * -0.02
        right_bottom_x = W * 1.02

    left_top_x = float(np.clip(left_top_x or W * 0.08, -0.10 * W, 0.55 * W))
    right_top_x = float(np.clip(right_top_x or W * 0.92, 0.45 * W, 1.10 * W))
    left_bottom_x = float(np.clip(left_bottom_x or W * -0.02, -0.22 * W, 0.42 * W))
    right_bottom_x = float(np.clip(right_bottom_x or W * 1.02, 0.58 * W, 1.22 * W))

    min_top_width = max(18.0, W * 0.58)
    if right_top_x - left_top_x < min_top_width:
        cx = 0.5 * (left_top_x + right_top_x)
        left_top_x = cx - min_top_width * 0.5
        right_top_x = cx + min_top_width * 0.5

    min_bottom_width = max(24.0, W * 0.42)
    if right_bottom_x - left_bottom_x < min_bottom_width:
        cx = 0.5 * (left_bottom_x + right_bottom_x)
        left_bottom_x = cx - min_bottom_width * 0.5
        right_bottom_x = cx + min_bottom_width * 0.5

    MAX_TAPER = 0.80
    actual_top_w = right_top_x - left_top_x
    actual_bot_w = right_bottom_x - left_bottom_x
    if actual_bot_w > 0 and actual_top_w / actual_bot_w > MAX_TAPER:
        target_bot_w = actual_top_w / 0.62
        cx_bot = 0.5 * (left_bottom_x + right_bottom_x)
        left_bottom_x = cx_bot - target_bot_w * 0.5
        right_bottom_x = cx_bot + target_bot_w * 0.5

    left_bottom_x -= W * 0.04
    right_bottom_x += W * 0.04
    left_bottom_x = max(-0.30 * W, left_bottom_x)
    right_bottom_x = min(1.30 * W, right_bottom_x)

    quad = np.array([
        [left_top_x, floor_top_y],
        [right_top_x, floor_top_y],
        [right_bottom_x, H - 1],
        [left_bottom_x, H - 1],
    ], dtype=np.float32)

    if proc_scale != 1.0:
        quad[:, 0] /= proc_scale
        quad[:, 1] /= proc_scale
        quad[2, 1] = H_orig - 1
        quad[3, 1] = H_orig - 1
        floor_top_y = int(round(floor_top_y / proc_scale))

    return quad, floor_top_y


def tile_texture(
    pattern: np.ndarray,
    area_w: int,
    area_h: int,
    total_stride_w: float,
    grout_width: int = 0,
    grout_color=(180, 180, 180),
) -> tuple[np.ndarray, int, int]:
    """
    Tiles the pattern so that the total width of one tile + its grout
    perfectly matches `total_stride_w`. Returns (tiled_image, tw, th).
    """
    if isinstance(grout_color, str):
        try:
            hex_c = grout_color.lstrip('#')
            if len(hex_c) == 6:
                r = int(hex_c[0:2], 16)
                g = int(hex_c[2:4], 16)
                b = int(hex_c[4:6], 16)
                grout_color = (b, g, r)
            else:
                grout_color = (180, 180, 180)
        except ValueError:
            grout_color = (180, 180, 180)

    pattern_w = max(1, int(total_stride_w) - grout_width)

    ph, pw = pattern.shape[:2]
    scale = pattern_w / float(pw)
    pattern_h = max(1, int(ph * scale))

    tile = cv2.resize(pattern, (pattern_w, pattern_h), interpolation=cv2.INTER_LANCZOS4)

    if grout_width > 0:
        th_grout = pattern_h + grout_width
        tw_grout = pattern_w + grout_width
        tile_with_grout = np.full((th_grout, tw_grout, 3), grout_color, dtype=np.uint8)
        tile_with_grout[0:pattern_h, 0:pattern_w] = tile
        tile = tile_with_grout

    th, tw = tile.shape[:2]
    if th == 0 or tw == 0:
        return np.zeros((area_h, area_w, 3), dtype=np.uint8), 0, 0

    grid_h, grid_w = area_h + th, area_w + tw
    grid_out = np.zeros((grid_h, grid_w, 3), dtype=np.uint8)

    for y in range(0, grid_h, th):
        for x in range(0, grid_w, tw):
            h_slice = min(th, grid_h - y)
            w_slice = min(tw, grid_w - x)
            grid_out[y:y + h_slice, x:x + w_slice] = tile[:h_slice, :w_slice]

    return grid_out[:area_h, :area_w], tw, th


def apply_pattern(
    base_image: np.ndarray,
    mask: np.ndarray,
    texture_image: np.ndarray,
    floor_quad: np.ndarray,
    settings: dict,
) -> np.ndarray:
    """
    Port of `utils/floor.py::apply_pattern`.

    `settings` keys read (same names as the original
    `process_single_layer` call site). Note: `process_single_layer`
    computes `repeat`/`shading`/`rotation`/`groutWidth`/`groutColor`
    once, shared across all categories, with `repeat` defaulting to 12
    (NOT the original `floor.apply_pattern`'s own internal default of
    3, which is only reached if a caller invokes it directly without
    going through `process_single_layer`). This port matches the real
    runtime default (12) to preserve actual observed behavior:
      - "repeat" (int, default 12)
      - "rotation" (int, default 0) -> rotation_deg
      - "groutWidth" (int, default 0) -> grout_width
      - "groutColor" (str, default "#000000") -> grout_color

    `floor_quad` is the caller-supplied quad (e.g. from
    `detect_floor_quad`). NOTE: the original `apply_pattern` always
    calls `_detect_floor_quad(room_img)` itself and ignores any
    externally supplied quad — there is no such parameter in the
    original. This port's signature was specified by the task to accept
    `floor_quad` explicitly, so `floor_quad` is used as-is instead of
    re-detecting internally. If the caller wants the exact original
    behavior it should pass in `detect_floor_quad(base_image)[0]`
    directly. This is the one deliberate signature deviation from a
    line-for-line port, called out per instructions.
    """
    room_img = base_image
    floor_tex = texture_image
    mask_img = mask

    # settings.get(key, default) doesn't actually default anything here -
    # HotspotSettings.model_dump() always includes these keys, set to None
    # when unconfigured, and .get()'s default only applies to a MISSING
    # key - so int(None) was throwing (silently swallowed upstream,
    # returning the room untouched) whenever the admin left these unset.
    repeat_raw = settings.get("repeat")
    repeat = int(repeat_raw) if repeat_raw is not None else 12
    rotation_raw = settings.get("rotation")
    rotation_deg = int(rotation_raw) if rotation_raw is not None else 0
    grout_width_raw = settings.get("groutWidth")
    grout_width = int(grout_width_raw) if grout_width_raw is not None else 0
    grout_color = settings.get("groutColor") or "#000000"

    H, W = room_img.shape[:2]

    if len(mask_img.shape) == 3:
        mask_gray = cv2.cvtColor(mask_img, cv2.COLOR_BGR2GRAY)
    else:
        mask_gray = mask_img

    mask_gray = cv2.resize(mask_gray, (W, H), interpolation=cv2.INTER_NEAREST)

    try:
        quad = floor_quad

        dst_w = float(np.linalg.norm(quad[2] - quad[3]))
        dst_h = float(max(np.linalg.norm(quad[0] - quad[3]), np.linalg.norm(quad[1] - quad[2])))

        pts_src = np.array([
            [0, 0],
            [dst_w, 0],
            [dst_w, dst_h],
            [0, dst_h]
        ], dtype=np.float32)
        M = cv2.getPerspectiveTransform(pts_src, quad)
        M_inv = np.linalg.inv(M)

        coords = cv2.findNonZero(mask_gray)
        if coords is None:
            return room_img

        # cv2.findNonZero doesn't reliably return the documented (N,1,2)
        # shape - reshape defensively rather than assume [:, 0, :] indexes.
        coords_flat = coords.reshape(-1, 2)
        coords_hom = np.ones((len(coords_flat), 3), dtype=np.float32)
        coords_hom[:, :2] = coords_flat

        flat_hom_scale = (M_inv @ coords_hom.T).T
        valid_mask_scale = flat_hom_scale[:, 2] > 0.001
        flat_hom_scale = flat_hom_scale[valid_mask_scale]

        if len(flat_hom_scale) < 10:
            return room_img

        flat_coords_scale = flat_hom_scale[:, :2] / flat_hom_scale[:, 2:]

        min_flat_x = np.percentile(flat_coords_scale[:, 0], 2)
        max_flat_x = np.percentile(flat_coords_scale[:, 0], 98)
        mask_flat_width = max(10.0, max_flat_x - min_flat_x)

        total_stride_w = float(mask_flat_width) / max(1, repeat)

        _, temp_tw, temp_th = tile_texture(floor_tex, 10, 10, total_stride_w, grout_width, grout_color)
        tw = max(1, int(temp_tw))
        th = max(1, int(temp_th))
        single_tile, _, _ = tile_texture(floor_tex, tw, th, total_stride_w, grout_width, grout_color)

        x_start, y_start, w_box, h_box = cv2.boundingRect(mask_gray)
        px = np.arange(x_start, x_start + w_box)
        py = np.arange(y_start, y_start + h_box)
        X_screen, Y_screen = np.meshgrid(px, py)

        pts_screen = np.vstack((X_screen.ravel(), Y_screen.ravel(), np.ones_like(X_screen.ravel())))

        pts_flat_hom = M_inv @ pts_screen
        Z = pts_flat_hom[2, :]

        valid = Z > 0.0001

        X_flat = pts_flat_hom[0, valid] / Z[valid]
        Y_flat = pts_flat_hom[1, valid] / Z[valid]

        cx, cy = 0.0, float(dst_h)
        theta = math.radians(-rotation_deg)
        cos_t = math.cos(theta)
        sin_t = math.sin(theta)

        X_shifted = X_flat - cx
        Y_shifted = Y_flat - cy

        X_rot = X_shifted * cos_t - Y_shifted * sin_t + cx
        Y_rot = X_shifted * sin_t + Y_shifted * cos_t + cy

        U = ((X_rot - cx) % tw).astype(np.int32)
        V = ((Y_rot - cy) % th).astype(np.int32)

        U = np.clip(U, 0, tw - 1)
        V = np.clip(V, 0, th - 1)

        warped_tex = np.zeros_like(room_img)
        valid_y = Y_screen.ravel()[valid]
        valid_x = X_screen.ravel()[valid]

        warped_tex[valid_y, valid_x] = single_tile[V, U]

        return blend_hard_replace(room_img, warped_tex, mask_gray, shadow_strength=0.15)

    except Exception:
        return room_img

"""Rug-visualizer scene analysis: floor-quad detection, visible/occluder floor
masks, and shadow-map extraction.

Ported faithfully from the Flask client-backend's ``utils/rugs.py``, scoped to
exactly the pieces the ``/api/rug-visualizer-scene`` route used:

- ``detect_floor_quad`` (was ``_detect_floor_quad``)
- ``estimate_floor_masks`` (was ``_estimate_floor_masks``)
- ``combine_masks`` (was ``_rug_masks_combine``, but now takes already-decoded
  mask arrays instead of fetching URLs itself — the async caller is
  responsible for downloading, this module stays pure-algorithm)
- ``b64_to_cv2``
- ``extract_shadow_map``
- ``encode_shadow_map_b64``

``get_lighting_map`` / ``blend_hard_replace`` from the original module are
intentionally NOT ported here — they belong to the room-compositing /
rug-overlay pipeline (``old_rugs.py`` / ``rug_overlay.py``), which is being
ported separately.
"""

from __future__ import annotations

import base64
import math

import cv2
import numpy as np


def b64_to_cv2(b64_str: str) -> np.ndarray:
    if b64_str and "," in b64_str:
        b64_str = b64_str.split(",")[1]
    image_bytes = base64.b64decode(b64_str)
    image_array = np.frombuffer(image_bytes, dtype=np.uint8)
    return cv2.imdecode(image_array, cv2.IMREAD_COLOR)


def combine_masks(mask_images: list[np.ndarray]) -> np.ndarray | None:
    """Threshold each mask at 127, OR them all together, then MORPH_CLOSE
    with a 17x17 kernel. Mirrors ``_rug_masks_combine``'s per-mask logic;
    the caller is responsible for fetching/decoding the mask images (the
    original fetched them from URLs with ``requests`` and decoded via
    ``cv2.IMREAD_GRAYSCALE``, this version receives already-decoded arrays).
    """
    combined_mask: np.ndarray | None = None
    kernel = np.ones((17, 17), np.uint8)

    for mask in mask_images:
        if mask is None:
            continue
        if mask.ndim == 3:
            # Original decoded straight to grayscale via cv2.IMREAD_GRAYSCALE;
            # be defensive here in case the caller hands us a color array.
            mask = cv2.cvtColor(mask, cv2.COLOR_BGR2GRAY)
        _, mask = cv2.threshold(mask, 127, 255, cv2.THRESH_BINARY)
        combined_mask = mask if combined_mask is None else cv2.bitwise_or(combined_mask, mask)

    if combined_mask is not None:
        combined_mask = cv2.morphologyEx(combined_mask, cv2.MORPH_CLOSE, kernel)

    return combined_mask


def extract_shadow_map(room_img: np.ndarray, visible_floor_mask: np.ndarray) -> np.ndarray:
    # The 'L' channel (Lightness) separates illumination from color perfectly.
    lab_img = cv2.cvtColor(room_img, cv2.COLOR_BGR2LAB)
    l_channel, _, _ = cv2.split(lab_img)

    # This preserves sharp shadow edges while smoothing minor noise.
    l_smooth = cv2.bilateralFilter(l_channel, d=15, sigmaColor=75, sigmaSpace=75)

    floor_pixels = l_smooth[visible_floor_mask > 0]  # Analyze only the visible floor pixels

    if len(floor_pixels) == 0:
        return np.ones_like(l_channel, dtype=np.float32)

    base_lightness = np.percentile(floor_pixels, 85)
    shadow_map = l_smooth.astype(np.float32) / (base_lightness + 1e-5)

    # Pull the darks down and lower the clip floor.
    shadow_map = np.power(shadow_map, 1.5)  # Deepens the mid-tones
    shadow_map = np.clip(shadow_map, 0.15, 1.0)  # Allows shadows to get much darker (15% vs 40%)

    # Invert the visible floor mask so furniture, beds, and walls become solid white (255)
    inv_floor = cv2.bitwise_not(visible_floor_mask)

    # Expand (dilate) this inverted mask to create a "valid shadow zone" around furniture.
    # (~4% of image width, but at least 21px to handle smaller images)
    radius = max(21, int(room_img.shape[1] * 0.04) | 1)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (radius, radius))
    shadow_zone = cv2.dilate(inv_floor, kernel)

    # Smooth the shadow zone heavily so shadows fade out naturally at the edges
    fade_radius = max(31, int(room_img.shape[1] * 0.08) | 1)
    shadow_zone_float = cv2.GaussianBlur(shadow_zone.astype(np.float32), (fade_radius, fade_radius), 0) / 255.0

    # Keep the shadow map inside the zone, force pure white (1.0) on the open floor
    shadow_map = shadow_map * shadow_zone_float + 1.0 * (1.0 - shadow_zone_float)

    # Set anything completely outside the visible floor to 1.0
    shadow_map[visible_floor_mask == 0] = 1.0

    return shadow_map


def encode_shadow_map_b64(shadow_map: np.ndarray) -> str:
    shadow_map_uint8 = (shadow_map * 255).astype(np.uint8)

    # Encode as PNG
    success, buffer = cv2.imencode(".png", shadow_map_uint8)
    if not success:
        raise ValueError("Could not encode shadow map")

    return base64.b64encode(buffer).decode("utf-8")


def _weighted_median(values: list[float], weights: list[float]) -> float | None:
    if not values:
        return None
    order = np.argsort(np.asarray(values))
    vals = np.asarray(values, dtype=np.float64)[order]
    wts = np.asarray(weights, dtype=np.float64)[order]
    cum = np.cumsum(wts)
    idx = int(np.searchsorted(cum, cum[-1] * 0.5))
    return float(vals[min(idx, len(vals) - 1)])


def detect_floor_quad(
    room_img: np.ndarray, floor_mask: np.ndarray | None = None
) -> tuple[np.ndarray, int]:
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

    # Oblique perspective lines
    lower_y0 = max(0, int(H * 0.10))
    edges_full = cv2.Canny(gray[lower_y0:H, :], 35, 115)
    lines_full = cv2.HoughLinesP(
        edges_full,
        1,
        np.pi / 180,
        threshold=max(22, W // 24),
        minLineLength=max(26, W // 9),
        maxLineGap=max(20, W // 24),
    )

    left_segs, right_segs = [], []
    if lines_full is not None:
        for x1_, y1_, x2_, y2_ in lines_full[:, 0]:
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

    # Keep only 15 longest per side — kills curtain/rug noise
    MAX_SEGS = 15
    if len(left_segs) > MAX_SEGS:
        left_segs = sorted(left_segs, key=lambda s: math.hypot(s[2] - s[0], s[3] - s[1]), reverse=True)[:MAX_SEGS]
    if len(right_segs) > MAX_SEGS:
        right_segs = sorted(right_segs, key=lambda s: math.hypot(s[2] - s[0], s[3] - s[1]), reverse=True)[:MAX_SEGS]

    edges_all = cv2.Canny(gray, 28, 90)
    x0s, x1s = int(W * 0.08), int(W * 0.92)
    row_dens = np.mean(edges_all[:, x0s:x1s].astype(np.float32), axis=1)

    # Smooth over ±window rows to reduce per-pixel noise
    smooth_k = max(10, H // 55)
    row_sm = np.convolve(row_dens, np.ones(smooth_k) / smooth_k, mode="same")

    # Dynamic threshold: half the std of edge density in the search zone
    y_scan_lo = int(H * 0.30)
    y_scan_hi = int(H * 0.82)
    zone = row_sm[y_scan_lo:y_scan_hi]
    threshold = max(float(np.std(zone)) * 0.50, 3.0)

    win = max(20, H // 30)  # comparison window above/below each candidate y

    floor_top_y = int(H * 0.62)  # fallback

    if floor_mask is not None:
        if proc_scale != 1.0:
            mask_proc = cv2.resize(floor_mask, (W, H), interpolation=cv2.INTER_NEAREST)
        else:
            mask_proc = floor_mask

        if len(mask_proc.shape) == 3:
            mask_proc = cv2.cvtColor(mask_proc, cv2.COLOR_BGR2GRAY)

        coords = cv2.findNonZero(mask_proc)
        if coords is not None:
            min_y = int(np.min(coords[:, 0, 1]))
            offset = int(H * 0.02)
            floor_top_y = max(int(H * 0.20), min_y - offset)
    else:
        # Fallback to old edge-detection logic if no mask is provided
        for y in range(y_scan_hi, y_scan_lo, -1):  # bottom → top
            above = float(np.mean(row_sm[max(0, y - win) : y]))
            below = float(np.mean(row_sm[y : min(H, y + win)]))
            if above - below >= threshold:
                floor_top_y = y
                break

        ref_lo = max(int(H * 0.30), floor_top_y - int(H * 0.08))
        ref_hi = min(int(H * 0.84), floor_top_y + int(H * 0.08))
        roi_ref = gray[ref_lo:ref_hi, int(W * 0.04) : int(W * 0.96)]
        edges_ref = cv2.Canny(roi_ref, 28, 95)
        lines_ref = cv2.HoughLinesP(
            edges_ref,
            1,
            np.pi / 180,
            threshold=max(22, W // 22),
            minLineLength=max(28, W // 8),
            maxLineGap=max(20, W // 22),
        )
        if lines_ref is not None:
            floor_top_y_init = floor_top_y
            best_score, best_y = 0.0, floor_top_y
            for x1_, y1_, x2_, y2_ in lines_ref[:, 0]:
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

    # TL/TR/BL/BR from oblique lines
    left_top_hits, left_top_w = [], []
    left_bot_hits, left_bot_w = [], []
    right_top_hits, right_top_w = [], []
    right_bot_hits, right_bot_w = [], []

    for x1_, y1g, x2_, y2g in left_segs + right_segs:
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

    # Give the bottom corners a slight outward flare to ensure they cover the screen width
    left_bottom_x = float(np.clip(left_bottom_x or W * -0.02, -0.20 * W, 0.40 * W))
    right_bottom_x = float(np.clip(right_bottom_x or W * 1.02, 0.60 * W, 1.20 * W))

    bot_w = right_bottom_x - left_bottom_x
    bot_center = (left_bottom_x + right_bottom_x) / 2.0

    # Force the top center to perfectly align with the bottom center
    top_center = bot_center

    # Enforce a strict realistic taper for rugs
    ideal_taper_ratio = 0.55
    target_top_w = bot_w * ideal_taper_ratio

    left_top_x = top_center - (target_top_w / 2.0)
    right_top_x = top_center + (target_top_w / 2.0)

    quad = np.array(
        [
            [left_top_x, floor_top_y],
            [right_top_x, floor_top_y],
            [right_bottom_x, H - 1],
            [left_bottom_x, H - 1],
        ],
        dtype=np.float32,
    )

    # Scale quad back to original dimensions if we downsampled
    if proc_scale != 1.0:
        quad[:, 0] /= proc_scale
        quad[:, 1] /= proc_scale
        quad[2, 1] = H_orig - 1
        quad[3, 1] = H_orig - 1
        floor_top_y = int(round(floor_top_y / proc_scale))

    return quad, floor_top_y


def _find_nearest_mask_pixel(
    mask: np.ndarray, start_x: int, start_y: int, radius: int = 36
) -> tuple[int, int] | None:
    height, width = mask.shape[:2]
    if 0 <= start_x < width and 0 <= start_y < height and mask[start_y, start_x] > 0:
        return start_x, start_y

    for delta in range(1, radius + 1):
        y0 = max(0, start_y - delta)
        y1 = min(height - 1, start_y + delta)
        x0 = max(0, start_x - delta)
        x1 = min(width - 1, start_x + delta)

        for y in range(y0, y1 + 1):
            if mask[y, x0] > 0:
                return x0, y
            if mask[y, x1] > 0:
                return x1, y
        for x in range(x0, x1 + 1):
            if mask[y0, x] > 0:
                return x, y0
            if mask[y1, x] > 0:
                return x, y1

    return None


def estimate_floor_masks(room_img: np.ndarray, floor_quad: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Estimate which parts of the detected floor remain visibly exposed.
    The complement becomes a soft occlusion overlay so rugs can slide under
    beds, sofas, and other furniture in the client-side visualizer.

    Returns ``(visible_floor_mask, occluder_mask)``. The original Flask
    helper also returned the raw (unoccluded) floor-quad mask as a third
    value; that value isn't part of this module's exposed contract (the
    route only ever consumed the first element), so it's dropped here.
    """
    height, width = room_img.shape[:2]

    floor_mask = np.zeros((height, width), dtype=np.uint8)
    cv2.fillPoly(floor_mask, [floor_quad.astype(np.int32)], 255)

    blurred = cv2.GaussianBlur(room_img, (9, 9), 0)
    lab_img = cv2.cvtColor(blurred, cv2.COLOR_BGR2LAB).astype(np.float32)

    seed_samples = []
    seed_points = []
    sample_x = (0.08, 0.22, 0.50, 0.78, 0.92)
    sample_y = (0.97, 0.92, 0.87, 0.82)

    for nx in sample_x:
        for ny in sample_y:
            px = int(round(nx * (width - 1)))
            py = int(round(ny * (height - 1)))
            nearest = _find_nearest_mask_pixel(floor_mask, px, py)
            if nearest is None:
                continue

            sx, sy = nearest
            seed_points.append((sx, sy))

            x0 = max(0, sx - 6)
            x1 = min(width, sx + 7)
            y0 = max(0, sy - 6)
            y1 = min(height, sy + 7)
            patch_mask = floor_mask[y0:y1, x0:x1] > 0
            patch_lab = lab_img[y0:y1, x0:x1]
            if np.any(patch_mask):
                seed_samples.append(patch_lab[patch_mask])

    if not seed_samples:
        return floor_mask, np.zeros_like(floor_mask)

    sample_matrix = np.concatenate(seed_samples, axis=0)
    base_color = np.median(sample_matrix, axis=0)

    distances = np.linalg.norm(lab_img - base_color, axis=2)
    sample_distances = np.linalg.norm(sample_matrix - base_color, axis=1)
    dist_threshold = float(np.clip(np.percentile(sample_distances, 85) + 14.0, 18.0, 48.0))

    visible_candidates = np.where(
        (floor_mask > 0) & (distances <= dist_threshold),
        255,
        0,
    ).astype(np.uint8)

    kernel_small = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
    kernel_large = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15))
    visible_candidates = cv2.morphologyEx(visible_candidates, cv2.MORPH_OPEN, kernel_small)
    visible_candidates = cv2.morphologyEx(visible_candidates, cv2.MORPH_CLOSE, kernel_large)

    label_count, labels = cv2.connectedComponents(visible_candidates)
    keep_labels = set()

    for sx, sy in seed_points:
        label_id = int(labels[sy, sx])
        if label_id > 0:
            keep_labels.add(label_id)

    bottom_band = labels[max(0, height - 20) : height, :]
    for label_id in np.unique(bottom_band):
        if label_id > 0:
            keep_labels.add(int(label_id))

    visible_floor_mask = np.where(np.isin(labels, list(keep_labels)), 255, 0).astype(np.uint8)
    visible_floor_mask = cv2.morphologyEx(visible_floor_mask, cv2.MORPH_CLOSE, kernel_large)
    visible_floor_mask = cv2.bitwise_and(visible_floor_mask, floor_mask)

    occluder_mask = cv2.subtract(floor_mask, visible_floor_mask)
    label_count, labels, stats, _ = cv2.connectedComponentsWithStats(occluder_mask)
    filtered_occluders = np.zeros_like(occluder_mask)
    min_area = max(120, (height * width) // 1800)

    for label_id in range(1, label_count):
        area = int(stats[label_id, cv2.CC_STAT_AREA])
        if area < min_area:
            continue
        filtered_occluders[labels == label_id] = 255

    filtered_occluders = cv2.GaussianBlur(filtered_occluders, (0, 0), sigmaX=2.4, sigmaY=2.4)
    filtered_occluders = cv2.bitwise_and(filtered_occluders, floor_mask)

    # Fill holes inside occluder regions (e.g. bed frame with gaps) and
    # dilate downward so the bed bottom edge fully covers the rug edge.
    kernel_fill = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (25, 25))
    filtered_occluders = cv2.morphologyEx(filtered_occluders, cv2.MORPH_CLOSE, kernel_fill)

    # Anisotropic dilation: expand occluder DOWNWARD to seal the
    # bed-floor boundary so the rug edge is hidden behind the bed.
    down_px = max(10, int(height * 0.03))
    kernel_down = cv2.getStructuringElement(cv2.MORPH_RECT, (1, down_px * 2 + 1))
    dilated = cv2.dilate(filtered_occluders, kernel_down, anchor=(0, 0), iterations=1)
    filtered_occluders = cv2.bitwise_and(dilated, floor_mask)

    # ── Depth cutoff: clear occluder in the NEAR-CAMERA floor zone ──
    # The bottom portion of the floor (carpet, hardwood, etc.) must always
    # show the rug. Only the upper portion (where bed/furniture sits) should
    # occlude.
    floor_top_y = int(np.min(floor_quad[:, 1]))
    floor_bot_y = int(np.max(floor_quad[:, 1]))
    floor_depth = max(1, floor_bot_y - floor_top_y)
    cutoff_y = int(floor_top_y + floor_depth * 0.50)

    # Above the cutoff: EVERYTHING inside the floor quad is occluder.
    # This ensures the bed, blankets, throw, cushions, bench — all of it
    # fully hides the rug so no rug edge is visible near the bed.
    upper_occluder = np.zeros_like(filtered_occluders)
    cv2.fillPoly(upper_occluder, [floor_quad.astype(np.int32)], 255)
    upper_occluder[cutoff_y:, :] = 0  # only keep the top half

    # Merge: use full-quad occluder above cutoff, nothing below
    filtered_occluders = np.maximum(filtered_occluders, upper_occluder)
    filtered_occluders[cutoff_y:, :] = 0

    # Final soft edge
    filtered_occluders = cv2.GaussianBlur(filtered_occluders, (0, 0), sigmaX=3.0, sigmaY=3.0)

    return visible_floor_mask, filtered_occluders

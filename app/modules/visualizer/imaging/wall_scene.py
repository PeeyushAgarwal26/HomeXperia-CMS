"""Wall-art visualizer scene analysis: obstacle-aware clear-region detection
within an already-detected wall quad.

Mirrors rug_scene.py's role for the rug-visualizer-scene route — this module
holds scene-analysis functions consumed by wallart_visualizer_scene, kept
separate from wall.py's pattern-application functions (detect_wall_quad,
apply_pattern), which stay serving the unrelated wallpaper/paint apply flow.

detect_wall_quad already exists in wall.py and is reused directly here, not
re-implemented — this module only adds what wall.py doesn't have: finding an
obstruction-free sub-region (light switches, outlets, mirrors, existing wall
art) within a wall quad, the same way rug_scene.estimate_floor_masks finds
furniture-free floor within a floor quad. Uses the same technique (LAB-color
region growing from sampled seed points + connected components), not a
segmentation model — a wall is typically one fairly uniform paint
color/texture, same assumption floor detection already relies on.
"""

from __future__ import annotations

import cv2
import numpy as np


def _max_rect_in_binary(mask01: np.ndarray) -> tuple[int, int, int, int] | None:
    """Largest all-1s axis-aligned rectangle in a 0/1 matrix, via the
    classic per-row "largest rectangle in histogram" stack method (O(rows *
    cols)). Returns (x, y, w, h) in mask01's own coordinates, or None if the
    mask is entirely 0."""
    rows, cols = mask01.shape
    heights = np.zeros(cols, dtype=np.int32)
    best_area = 0
    best_rect: tuple[int, int, int, int] | None = None

    for row in range(rows):
        heights = np.where(mask01[row] > 0, heights + 1, 0)
        stack: list[int] = []
        for i in range(cols + 1):
            h = int(heights[i]) if i < cols else 0
            while stack and heights[stack[-1]] >= h:
                height = int(heights[stack.pop()])
                left = (stack[-1] + 1) if stack else 0
                width = i - left
                area = width * height
                if area > best_area:
                    best_area = area
                    best_rect = (left, row - height + 1, width, height)
            stack.append(i)

    return best_rect


def estimate_wall_clear_region(room_img: np.ndarray, wall_quad: np.ndarray) -> np.ndarray:
    """Find the largest obstruction-free axis-aligned rectangle within
    `wall_quad`. Heuristic, not pixel-perfect (same spirit as
    estimate_floor_masks) — works in `wall_quad`'s own bounding box rather
    than its exact (possibly perspective-skewed) polygon, since the
    downstream placement box needs an axis-aligned rectangle anyway.

    Returns a quad (4x2 float32, same coordinate space as `wall_quad`) —
    degrades to `wall_quad` itself if no clear area can be found (e.g. the
    quad is degenerate, or the whole thing reads as "obstacle").
    """
    height, width = room_img.shape[:2]
    wall_mask = np.zeros((height, width), dtype=np.uint8)
    cv2.fillPoly(wall_mask, [wall_quad.astype(np.int32)], 255)

    xs, ys = wall_quad[:, 0], wall_quad[:, 1]
    x0, x1 = int(max(0, xs.min())), int(min(width, xs.max()))
    y0, y1 = int(max(0, ys.min())), int(min(height, ys.max()))
    if x1 <= x0 or y1 <= y0:
        return wall_quad

    blurred = cv2.GaussianBlur(room_img, (9, 9), 0)
    lab_img = cv2.cvtColor(blurred, cv2.COLOR_BGR2LAB).astype(np.float32)

    # Sample the wall's dominant color from points spread across its
    # interior — for a typical single-color painted wall, obstacles
    # (switches, outlets, mirrors, existing frames) are the minority of the
    # sampled area, so the median sample color is a good proxy for "bare
    # wall" even without knowing where the obstacles are yet.
    sample_fracs = (0.15, 0.3, 0.5, 0.7, 0.85)
    samples = []
    for fx in sample_fracs:
        for fy in sample_fracs:
            px = int(x0 + fx * (x1 - x0))
            py = int(y0 + fy * (y1 - y0))
            if wall_mask[py, px] == 0:
                continue
            patch = lab_img[max(0, py - 5) : py + 6, max(0, px - 5) : px + 6]
            samples.append(patch.reshape(-1, 3))

    if not samples:
        return wall_quad

    sample_matrix = np.concatenate(samples, axis=0)
    base_color = np.median(sample_matrix, axis=0)

    distances = np.linalg.norm(lab_img - base_color, axis=2)
    sample_distances = np.linalg.norm(sample_matrix - base_color, axis=1)
    dist_threshold = float(np.clip(np.percentile(sample_distances, 85) + 14.0, 18.0, 48.0))

    clear_candidates = np.where((wall_mask > 0) & (distances <= dist_threshold), 255, 0).astype(np.uint8)

    kernel_small = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
    kernel_large = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15))
    clear_candidates = cv2.morphologyEx(clear_candidates, cv2.MORPH_OPEN, kernel_small)
    clear_candidates = cv2.morphologyEx(clear_candidates, cv2.MORPH_CLOSE, kernel_large)

    roi = clear_candidates[y0:y1, x0:x1]
    roi_h, roi_w = roi.shape
    if roi_h == 0 or roi_w == 0:
        return wall_quad

    # Downscale before the largest-inscribed-rectangle search — this only
    # needs to find approximate region bounds, not exact pixels, and the
    # per-row histogram scan is otherwise needlessly slow on a full-res mask.
    max_dim = 260
    scale = min(1.0, max_dim / max(roi_h, roi_w))
    if scale < 1.0:
        small = cv2.resize(
            roi, (max(1, int(roi_w * scale)), max(1, int(roi_h * scale))), interpolation=cv2.INTER_NEAREST
        )
    else:
        small = roi

    rect = _max_rect_in_binary((small > 127).astype(np.uint8))
    if rect is None:
        return wall_quad

    rx, ry, rw, rh = rect
    inv_scale = 1.0 / scale
    gx0 = x0 + rx * inv_scale
    gy0 = y0 + ry * inv_scale
    gx1 = gx0 + rw * inv_scale
    gy1 = gy0 + rh * inv_scale

    return np.array([[gx0, gy0], [gx1, gy0], [gx1, gy1], [gx0, gy1]], dtype=np.float32)


def largest_rect_in_mask(mask_gray: np.ndarray) -> np.ndarray:
    """Largest axis-aligned rectangle inscribed in a wall mask — a safe
    fallback wall_quad for when wall.detect_wall_quad's Hough-line/profile
    fit is too distorted to use as a homography basis. A wall mask's own
    boundary can include things that aren't the flat wall plane at all (a
    sloped vaulted-ceiling edge, an arched window cutout) — detect_wall_quad
    fits a single straight top/bottom edge to that whole boundary, so a
    strong straight segment along, say, the ceiling's slope can dominate the
    fit and produce a quad whose two vertical edges differ wildly in height.
    Reuses the same largest-inscribed-rectangle technique as
    estimate_wall_clear_region, just applied to the raw mask (not a
    color-similarity "clear" sub-mask) — always axis-aligned, so it can
    never carry that kind of distortion, at the cost of not "hugging" any
    real perspective the wall does have.
    """
    height, width = mask_gray.shape[:2]
    binary = (mask_gray > 127).astype(np.uint8)

    max_dim = 260
    scale = min(1.0, max_dim / max(height, width))
    if scale < 1.0:
        small = cv2.resize(
            binary, (max(1, int(width * scale)), max(1, int(height * scale))), interpolation=cv2.INTER_NEAREST
        )
    else:
        small = binary

    rect = _max_rect_in_binary(small)
    if rect is None:
        return np.array([[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]], dtype=np.float32)

    rx, ry, rw, rh = rect
    inv_scale = 1.0 / scale
    x0 = rx * inv_scale
    y0 = ry * inv_scale
    x1 = x0 + rw * inv_scale
    y1 = y0 + rh * inv_scale

    return np.array([[x0, y0], [x1, y0], [x1, y1], [x0, y1]], dtype=np.float32)


def wall_quad_is_reasonable(quad: np.ndarray, max_edge_ratio: float = 2.2) -> bool:
    """True if a detected wall quad's two vertical edges are within
    max_edge_ratio of each other's height — a sanity check on
    detect_wall_quad's output before trusting it as a homography basis (see
    largest_rect_in_mask's docstring for why it can go wrong). A real
    photographed wall, even at a noticeable angle, rarely shows one vertical
    edge more than ~2x taller than the other; well past that means the fit
    almost certainly latched onto something that isn't the wall's own flat
    plane.
    """
    left_h = float(np.hypot(*(quad[3] - quad[0])))
    right_h = float(np.hypot(*(quad[2] - quad[1])))
    if left_h <= 0 or right_h <= 0:
        return False
    return max(left_h, right_h) / min(left_h, right_h) <= max_edge_ratio

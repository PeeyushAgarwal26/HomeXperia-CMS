"""
Rug pattern application, ported verbatim from
`homexperia-client-backend/utils/old_rugs.py` — this is the file actually
used by `process_single_layer` for the `rugs` category (NOT
`utils/rugs.py`, which is a different module used elsewhere).
"""

from __future__ import annotations

import math
from pathlib import Path

import cv2
import numpy as np

from .shared import blend_hard_replace


def order_points_robust(pts: np.ndarray) -> np.ndarray:
    if len(pts) != 4:
        return pts
    sorted_y = pts[np.argsort(pts[:, 1])]
    top_pts = sorted_y[:2]
    bottom_pts = sorted_y[2:]
    top_pts = top_pts[np.argsort(top_pts[:, 0])]
    bottom_pts = bottom_pts[np.argsort(bottom_pts[:, 0])]
    tl, tr = top_pts[0], top_pts[1]
    bl, br = bottom_pts[0], bottom_pts[1]
    return np.array([tl, tr, br, bl], dtype="float32")


def get_global_corners(contours) -> np.ndarray:
    all_points = np.vstack(contours)
    hull = cv2.convexHull(all_points)
    epsilon = 0.02 * cv2.arcLength(hull, True)
    approx = cv2.approxPolyDP(hull, epsilon, True)
    if len(approx) == 4:
        pts_dst = np.squeeze(approx).astype(np.float32)
    else:
        rect = cv2.minAreaRect(hull)
        box = cv2.boxPoints(rect)
        pts_dst = box
    return order_points_robust(pts_dst)


def _fit_line_cv(pts_xy):
    """Return (x0, y0, vx, vy) from cv2.fitLine, or None."""
    if pts_xy is None or len(pts_xy) < 3:
        return None
    p = np.asarray(pts_xy, dtype=np.float32).reshape(-1, 1, 2)
    vx, vy, x0, y0 = cv2.fitLine(p, cv2.DIST_L2, 0, 0.01, 0.01)
    return float(x0.flat[0]), float(y0.flat[0]), float(vx.flat[0]), float(vy.flat[0])


def _intersect_lines_infinite(la, lb):
    """la, lb: (x0,y0,vx,vy). Return (x,y) or None if parallel."""
    p1 = np.array(la[:2], dtype=np.float64)
    d1 = np.array(la[2:4], dtype=np.float64)
    p2 = np.array(lb[:2], dtype=np.float64)
    d2 = np.array(lb[2:4], dtype=np.float64)
    det = d1[0] * d2[1] - d1[1] * d2[0]
    if abs(det) < 1e-9:
        return None
    diff = p2 - p1
    t = (diff[0] * d2[1] - diff[1] * d2[0]) / det
    q = p1 + t * d1
    return float(q[0]), float(q[1])


def _line_through_point_with_direction(px, py, vx, vy):
    """Infinite line (x0,y0,vx,vy) through (px,py) with same direction."""
    return float(px), float(py), float(vx), float(vy)


def _hough_segments_on_padded_mask(thresh_bin, pad):
    """Run HoughLinesP on mask embedded in a larger canvas (Suggestion 1)."""
    H, W = thresh_bin.shape[:2]
    canvas = np.zeros((H + 2 * pad, W + 2 * pad), dtype=np.uint8)
    canvas[pad:pad + H, pad:pad + W] = thresh_bin
    edges = cv2.Canny(canvas, 40, 120, apertureSize=3)
    lines = cv2.HoughLinesP(
        edges,
        1,
        np.pi / 180,
        threshold=40,
        minLineLength=max(30, min(H, W) // 25),
        maxLineGap=25,
    )
    segs = []
    if lines is None:
        return segs
    # cv2.HoughLinesP doesn't reliably return the documented (N,1,4) shape -
    # reshape defensively rather than assume [:, 0] unpacks.
    for x1, y1, x2, y2 in lines.reshape(-1, 4):
        segs.append(
            (
                float(x1 - pad),
                float(y1 - pad),
                float(x2 - pad),
                float(y2 - pad),
            )
        )
    return segs


def _hough_lr_bottom_from_segments(segments, x, y, w, h):
    """
    From Hough segments on an extended canvas, estimate left / right / bottom lines.
    Handles thin horizontal strips (mostly vertical sides + horizontal bottom).
    """
    cx = x + 0.5 * w
    cy = y + 0.5 * h
    vert_left, vert_right = [], []
    horiz = []
    for x1, y1, x2, y2 in segments:
        dx, dy = x2 - x1, y2 - y1
        ln = math.hypot(dx, dy)
        if ln < 1e-6:
            continue
        ang = abs(math.atan2(dy, dx))
        mx, my = (x1 + x2) * 0.5, (y1 + y2) * 0.5
        vx, vy = dx / ln, dy / ln
        if ang < 0.45 or ang > math.pi - 0.45:
            if my >= y + 0.4 * h:
                horiz.append((mx, my, vx, vy))
        elif abs(ang - math.pi * 0.5) < 0.45:
            if mx < cx:
                vert_left.append((mx, my, vx, vy))
            else:
                vert_right.append((mx, my, vx, vy))

    def _avg_line(rows):
        if len(rows) < 2:
            return None
        xs = [r[0] for r in rows]
        ys = [r[1] for r in rows]
        vxs = [r[2] for r in rows]
        vys = [r[3] for r in rows]
        vx = float(np.mean(vxs))
        vy = float(np.mean(vys))
        n = math.hypot(vx, vy)
        if n < 1e-9:
            return None
        vx /= n
        vy /= n
        return float(np.mean(xs)), float(np.mean(ys)), vx, vy

    Ll = _avg_line(vert_left)
    Lr = _avg_line(vert_right)
    Lb = _avg_line(horiz)
    return Ll, Lr, Lb


def mask_touches_image_bottom(contour, H, touch_px=6):
    """Rug mask sits against the bottom frame — extra Hough padding skews bottom edges."""
    _, y, _, h = cv2.boundingRect(contour)
    return (y + h) >= H - touch_px


def quad_from_extended_lines(contour, thresh_bin, W, H, pad_hough=200):
    """
    Build a full perspective quad by intersecting extended boundary lines (Suggestion 1).
    Occluded corners are recovered where the infinite lines meet. The warped rug should
    cover the logical rug plane; the original mask still clips furniture/occlusion.
    """
    pts = contour.reshape(-1, 2)
    x, y, w, h = cv2.boundingRect(contour)
    if w < 8 or h < 8:
        return None

    if mask_touches_image_bottom(contour, H):
        pad_hough = min(pad_hough, 12)

    dy = max(6, int(0.12 * h + 0.5))
    y0b, y1b = y + h - dy, y + h
    y0t, y1t = y, y + dy
    y_lo = int(np.percentile(pts[:, 1], 18))
    y_hi = int(np.percentile(pts[:, 1], 82))
    x_left_cut = float(np.percentile(pts[:, 0], 14))
    x_right_cut = float(np.percentile(pts[:, 0], 86))

    y_side_lo = max(y_lo, int(y + 0.20 * h))

    bottom = pts[(pts[:, 1] >= y0b) & (pts[:, 1] <= y1b)]
    top = pts[(pts[:, 1] >= y0t) & (pts[:, 1] <= y1t)]
    left = pts[(pts[:, 0] <= x_left_cut) & (pts[:, 1] >= y_side_lo) & (pts[:, 1] <= y_hi)]
    right = pts[(pts[:, 0] >= x_right_cut) & (pts[:, 1] >= y_side_lo) & (pts[:, 1] <= y_hi)]
    if len(left) < 4:
        left = pts[(pts[:, 0] <= x_left_cut) & (pts[:, 1] >= y_lo) & (pts[:, 1] <= y_hi)]
    if len(right) < 4:
        right = pts[(pts[:, 0] >= x_right_cut) & (pts[:, 1] >= y_lo) & (pts[:, 1] <= y_hi)]

    def _too_horizontal_side(line):
        if line is None:
            return True
        _, _, vx, vy = line
        return abs(vx) >= 0.86 and abs(vy) <= 0.38

    Lb = _fit_line_cv(bottom)
    Lt = _fit_line_cv(top) if len(top) >= 6 else None
    Ll = _fit_line_cv(left) if len(left) >= 4 else None
    Lr = _fit_line_cv(right) if len(right) >= 4 else None
    if _too_horizontal_side(Ll):
        Ll = None
    if _too_horizontal_side(Lr):
        Lr = None

    segs = _hough_segments_on_padded_mask(thresh_bin, pad_hough)
    if len(segs) > 0 and (Ll is None or Lr is None or Lb is None):
        hl, hr, hb = _hough_lr_bottom_from_segments(segs, x, y, w, h)
        if Ll is None:
            Ll = hl
        if Lr is None:
            Lr = hr
        if Lb is None:
            Lb = hb

    if Lb is None:
        return None
    if Ll is None:
        xm = float(np.min(pts[:, 0]))
        Ll = (xm, float(np.mean(pts[:, 1])), 0.0, 1.0)
    if Lr is None:
        xM = float(np.max(pts[:, 0]))
        Lr = (xM, float(np.mean(pts[:, 1])), 0.0, 1.0)

    bl = _intersect_lines_infinite(Ll, Lb)
    br = _intersect_lines_infinite(Lr, Lb)
    if bl is None or br is None:
        return None

    if Lt is not None:
        tl = _intersect_lines_infinite(Ll, Lt)
        tr = _intersect_lines_infinite(Lr, Lt)
        if tl is None or tr is None:
            Lt = None

    if Lt is None:
        _, _, vxb, vyb = Lb
        y_cut = y + min(dy, max(4, int(0.35 * h)))
        upper = pts[pts[:, 1] <= y_cut]
        if len(upper) < 1:
            upper = pts
        px = float(np.mean(upper[:, 0]))
        py = float(np.min(upper[:, 1]))
        t_line = _line_through_point_with_direction(px, py, vxb, vyb)
        tl = _intersect_lines_infinite(Ll, t_line)
        tr = _intersect_lines_infinite(Lr, t_line)
        if tl is None or tr is None:
            return None

    quad = np.array([tl, tr, br, bl], dtype=np.float32)
    quad = order_points_robust(quad)
    tl, tr, br, bl = quad
    top_w = float(np.linalg.norm(tr - tl))
    bot_w = float(np.linalg.norm(br - bl))
    if top_w > bot_w * 1.10:
        return None
    return quad


def adjust_quad_bottom_to_mask_floor(quad, contour, H, touch_px=6, overshoot=2.0):
    """
    If the mask meets the image bottom, nudge BL/BR down so the warp covers the lowest
    mask pixels (avoids a gap/clip at y = H-1).
    """
    if not mask_touches_image_bottom(contour, H, touch_px):
        return quad.astype(np.float32)
    q = quad.astype(np.float64).copy()
    pts = contour.reshape(-1, 2)
    ymax = float(np.max(pts[:, 1]))
    y_target = min(ymax + overshoot, H - 0.25)
    lo = min(q[2, 1], q[3, 1])
    dy = max(0.0, y_target - lo)
    if dy > 0:
        q[2, 1] += dy
        q[3, 1] += dy
    return q.astype(np.float32)


def expand_quad_to_cover_mask(quad, contour, margin_px=6.0):
    """Slightly grow the quad so warpPerspective does not leave holes vs the mask (Suggestion 2)."""
    q = quad.astype(np.float64)
    c = contour.reshape(-1, 2).astype(np.float64)
    cx = np.mean(c[:, 0])
    cy = np.mean(c[:, 1])
    out = []
    for i in range(4):
        p = q[i]
        v = p - np.array([cx, cy])
        n = np.linalg.norm(v)
        if n < 1e-9:
            out.append(p)
            continue
        v = v / n
        out.append(p + v * margin_px)
    return np.asarray(out, dtype=np.float32)


def is_reasonable_quad(pts, W, H) -> bool:
    """Loose bounds so extended intersections off-screen are still allowed (within a margin)."""
    if pts is None or len(pts) != 4:
        return False
    area = abs(cv2.contourArea(pts.astype(np.float32)))
    if area < 300:
        return False
    m = max(W, H) * 0.55
    for p in pts:
        if not (-m <= p[0] <= W + m and -m <= p[1] <= H + m):
            return False
    d01 = np.linalg.norm(pts[0] - pts[1])
    d12 = np.linalg.norm(pts[1] - pts[2])
    if min(d01, d12) < 5:
        return False
    tl, tr, br, bl = pts
    top_w = np.linalg.norm(tr - tl)
    bot_w = np.linalg.norm(br - bl)
    if top_w > bot_w * 1.12:
        return False
    return True


def save_debug_image(img, pts, room_id, hotspot_id, method_name, debug_dir: Path | None):
    """
    Port of `save_debug_image`. The original wrote unconditionally to
    `Debugs/debug_{room_id}({method_name}).jpg` and had no `hotspot_id`
    parameter (it was not needed since the Flask app processed one room
    at a time). This port takes `debug_dir` and only writes when it is
    not None. `hotspot_id` is folded into the filename so concurrent
    layers for the same room don't clobber each other's debug images —
    this is an additive, non-behavior-changing detail since the
    original had no notion of concurrent per-hotspot debug output for
    the same room_id at all.
    """
    if debug_dir is None:
        return
    debug_dir.mkdir(parents=True, exist_ok=True)
    debug_img = img.copy()
    cv2.polylines(debug_img, [np.int32(pts)], isClosed=True, color=(0, 255, 0), thickness=3)
    labels = ["TL", "TR", "BR", "BL"]
    colors = [(0, 0, 255), (0, 255, 255), (255, 0, 0), (255, 0, 255)]
    for i, pt in enumerate(pts):
        x, y = int(pt[0]), int(pt[1])
        cv2.circle(debug_img, (x, y), 8, colors[i], -1)
        cv2.putText(debug_img, f"{labels[i]}", (x + 15, y - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, colors[i], 2, cv2.LINE_AA)
    cv2.imwrite(str(debug_dir / f"debug_{room_id}_{hotspot_id}({method_name}).jpg"), debug_img)


def get_vanishing_point_trapezoid(mask_img: np.ndarray) -> np.ndarray | None:
    """
    Perspective quad from Hough lines on the mask (left / right receding edges).
    Returns None if lines are missing or degenerate — no synthetic trapezoid;
    quad_from_extended_lines() handles the next stage.
    """
    contours, _ = cv2.findContours(mask_img, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None

    largest_contour = max(contours, key=cv2.contourArea)
    x, y, w, h = cv2.boundingRect(largest_contour)

    y_top = y
    y_bottom = y + h

    edges = cv2.Canny(mask_img, 50, 150, apertureSize=3)
    lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=50, minLineLength=40, maxLineGap=20)

    left_lines = []
    right_lines = []

    if lines is not None:
        # cv2.HoughLinesP doesn't reliably return the documented (N,1,4)
        # shape - reshape defensively rather than assume line[0] indexes.
        for line in lines.reshape(-1, 4):
            x1, y1, x2, y2 = line
            if x2 - x1 == 0:
                continue
            slope = (y2 - y1) / (x2 - x1)
            intercept = y1 - slope * x1
            if slope < -0.15:
                left_lines.append((slope, intercept))
            elif slope > 0.15:
                right_lines.append((slope, intercept))

    if not left_lines or not right_lines:
        return None

    try:
        avg_m_left = np.mean([l[0] for l in left_lines])
        avg_b_left = np.mean([l[1] for l in left_lines])
        avg_m_right = np.mean([l[0] for l in right_lines])
        avg_b_right = np.mean([l[1] for l in right_lines])

        tl_x = (y_top - avg_b_left) / avg_m_left
        tr_x = (y_top - avg_b_right) / avg_m_right
        if tl_x >= tr_x:
            return None

        tl = [tl_x, y_top]
        tr = [tr_x, y_top]
        br = [x + w, y_bottom]
        bl = [x, y_bottom]
        pts_dst = np.array([tl, tr, br, bl], dtype="float32")
    except Exception:
        return None

    return order_points_robust(pts_dst)


def is_good_perspective(pts) -> bool:
    """
    Evaluates 4 corner points to ensure they form a valid 3D perspective trapezoid.
    Checks against flat rectangles, collapsed triangles, and extreme skew.
    """
    if pts is None or len(pts) != 4:
        return False

    tl, tr, br, bl = pts

    top_width = np.linalg.norm(tr - tl)
    bottom_width = np.linalg.norm(br - bl)
    left_height = np.linalg.norm(bl - tl)
    right_height = np.linalg.norm(br - tr)

    if top_width < (bottom_width * 0.15):
        return False

    if top_width > (bottom_width * 0.95):
        return False

    height_ratio = min(left_height, right_height) / max(1, max(left_height, right_height))
    if height_ratio < 0.4:
        return False

    return True


def apply_pattern(
    base_image: np.ndarray,
    mask: np.ndarray,
    texture_image: np.ndarray,
    settings: dict,
    room_id: str,
    hotspot_id: str,
    debug_dir: Path | None = None,
) -> np.ndarray:
    """
    Port of `utils/old_rugs.py::apply_pattern`.

    `settings` keys read (matching the original call site in
    `process_single_layer`, which always passes `repeat=1` for rugs
    regardless of `settings.get('repeat', ...)`, and forwards
    `rotation` from settings):
      - "rotation" (int, default 0) -> rotation_deg
      (repeat is intentionally NOT read from settings — the original
      call site `apply_rugs_pattern(current_image, texture, mask,
      repeat=1, rotation_deg=rotation, room_id=room_id)` hardcodes
      repeat=1 for rugs; `settings.get('repeat', 12)` upstream in
      `process_single_layer` is computed but never actually passed
      through to the rugs branch. Preserved verbatim here: `repeat` is
      fixed at 1.)

    Preserves the exact fallback chain: get_global_corners ->
    is_good_perspective check -> get_vanishing_point_trapezoid ->
    quad_from_extended_lines -> static default trapezoid, followed by
    the rotation-then-zoom-to-cover logic on the texture itself.

    Debug images (all of `save_debug_image`'s calls in the original,
    which wrote unconditionally to `Debugs/`) are only written if
    `debug_dir` is provided.
    """
    room_img = base_image
    rug_tex = texture_image
    mask_img = mask

    # settings.get("rotation", 0) doesn't actually default anything -
    # HotspotSettings.model_dump() always includes "rotation", set to None
    # when unconfigured, and .get()'s default only applies to a MISSING
    # key - so int(None) was throwing (silently swallowed upstream,
    # returning the room untouched) whenever the admin left it unset.
    rotation_raw = settings.get("rotation")
    rotation_deg = int(rotation_raw) if rotation_raw is not None else 0
    repeat = 1  # hardcoded at the original call site for the 'rugs' category

    H, W = room_img.shape[:2]

    if len(mask_img.shape) == 3:
        mask_gray = cv2.cvtColor(mask_img, cv2.COLOR_BGR2GRAY)
    else:
        mask_gray = mask_img

    mask_gray = cv2.resize(mask_gray, (W, H), interpolation=cv2.INTER_NEAREST)
    _, thresh = cv2.threshold(mask_gray, 127, 255, cv2.THRESH_BINARY)
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    if not contours:
        return room_img

    try:
        largest = max(contours, key=cv2.contourArea)

        pts_dst_basic = get_global_corners(contours)
        save_debug_image(room_img, pts_dst_basic, room_id, hotspot_id, "get_global_corners", debug_dir)

        if is_good_perspective(pts_dst_basic):
            pts_dst = expand_quad_to_cover_mask(pts_dst_basic, largest, margin_px=4.0)
        else:
            pts_vp = get_vanishing_point_trapezoid(thresh)
            if pts_vp is not None and is_good_perspective(pts_vp):
                pts_dst = expand_quad_to_cover_mask(pts_vp, largest, margin_px=4.0)
                save_debug_image(room_img, pts_dst, room_id, hotspot_id, "vanishing_point", debug_dir)
            else:
                pts_line = quad_from_extended_lines(largest, thresh, W, H)
                if pts_line is not None and is_reasonable_quad(pts_line, W, H):
                    pts_dst = expand_quad_to_cover_mask(pts_line, largest, margin_px=6.0)
                    save_debug_image(room_img, pts_dst, room_id, hotspot_id, "line_extended_quad", debug_dir)
                else:
                    pts_dst = np.array(
                        [[W * 0.2, H * 0.6], [W * 0.8, H * 0.6], [W, H], [0, H]],
                        dtype=np.float32,
                    )
                    save_debug_image(room_img, pts_dst, room_id, hotspot_id, "fallback_trapezoid", debug_dir)

        pts_dst = adjust_quad_bottom_to_mask_floor(pts_dst, largest, H)

        tex_h, tex_w = rug_tex.shape[:2]

        if rotation_deg != 0:
            angle_rad = math.radians(rotation_deg)
            cos_a = abs(math.cos(angle_rad))
            sin_a = abs(math.sin(angle_rad))

            new_w = tex_w * cos_a + tex_h * sin_a
            new_h = tex_w * sin_a + tex_h * cos_a

            scale = max(new_w / tex_w, new_h / tex_h)

            center = (tex_w / 2, tex_h / 2)
            M_rot = cv2.getRotationMatrix2D(center, rotation_deg, scale)

            rug_tex = cv2.warpAffine(rug_tex, M_rot, (tex_w, tex_h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)

        pts_src = np.array([
            [0, 0],
            [tex_w - 1, 0],
            [tex_w - 1, tex_h - 1],
            [0, tex_h - 1]
        ], dtype="float32")

        M = cv2.getPerspectiveTransform(pts_src, pts_dst)
        warped_tex = cv2.warpPerspective(
            rug_tex,
            M,
            (W, H),
            flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=(0, 0, 0),
        )

        src_alpha = np.full((tex_h, tex_w), 255, dtype=np.uint8)
        warped_alpha = cv2.warpPerspective(
            src_alpha,
            M,
            (W, H),
            flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=0,
        )
        effective_mask = cv2.bitwise_and(mask_gray, warped_alpha)

        return blend_hard_replace(room_img, warped_tex, effective_mask, shadow_strength=0.15)

    except Exception:
        return room_img

"""Depth-grounded wall geometry: fits a real 3D plane to a wall mask from a
metric depth map, and flags pixels protruding in front of that plane as
obstacles (a TV, shelf, or mounted object standing proud of the wall).

Port of the Flask client-backend's ``utils/wall_depth.py`` (``_backproject_mask``,
``_fit_plane``, ``_wall_quad_from_depth``, ``_quad_mask_containment``) and
``utils/wallart.py`` (``_plane_depth_map``, ``_protrusion_mask``,
``PROTRUSION_M``, ``WALL_FOCAL_RATIO``) — the piece of that repo's pipeline
that replaced its own earlier LAB-color-uniformity clear-region heuristic
(the same technique wall_scene.py still uses) once it moved to depth-based
detection. A TV panel reads as "uniform color" exactly like painted wall does,
so no amount of tuning a color threshold can tell them apart; a TV standing
even a few centimetres off the wall plane is unambiguous in depth regardless
of its color or texture, which is the actual invariant this needs.

Everything here is pure numpy/cv2 — no torch dependency of its own. The
metric depth map it consumes comes from depth.get_metric_depth.
"""

from __future__ import annotations

import cv2
import numpy as np

from app.modules.visualizer.imaging.rug_overlay import order_points_robust

# Pinhole-camera focal length, approximated as a fraction of the image's
# longer side (no camera calibration data is available) — same ratio the
# reference repo tuned this against.
WALL_FOCAL_RATIO = 0.8

# Depth closer to the camera than the fitted wall plane by more than this
# counts as an obstacle (a TV/shelf/mounted object standing off the wall).
PROTRUSION_M = 0.08


def quad_mask_containment(quad: np.ndarray, mask_gray: np.ndarray) -> float:
    """Fraction of mask_gray's on-pixels that fall inside quad — a sanity
    check that a depth-fitted quad actually covers the mask it was fit to,
    not a wildly wrong plane."""
    poly = np.zeros_like(mask_gray)
    cv2.fillPoly(poly, [quad.astype(np.int32)], 255)
    on = mask_gray > 0
    total = int(on.sum())
    if total == 0:
        return 0.0
    return int((poly[on] > 0).sum()) / float(total)


def _backproject_mask(depth_m: np.ndarray, mask: np.ndarray, focal_px: float, max_pts: int = 40000) -> np.ndarray | None:
    """Back-project a mask's on-pixels into 3D camera-space points using a
    pinhole model (X = (x-cx)*Z/f, Y = (y-cy)*Z/f), given their metric depth."""
    H, W = depth_m.shape[:2]
    cx, cy = W / 2.0, H / 2.0
    ys, xs = np.where(mask > 127)
    if len(xs) < 200:
        return None
    Z = depth_m[ys, xs].astype(np.float64)
    ok = np.isfinite(Z) & (Z > 0.1) & (Z < 30.0)
    xs, ys, Z = xs[ok], ys[ok], Z[ok]
    if len(xs) < 200:
        return None
    X = (xs - cx) * Z / focal_px
    Y = (ys - cy) * Z / focal_px
    P = np.stack([X, Y, Z], axis=1)
    if len(P) > max_pts:
        idx = np.linspace(0, len(P) - 1, max_pts).astype(np.int64)
        P = P[idx]
    return P


def _fit_plane(P: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Robust plane fit via iterative SVD with outlier rejection (2.5-sigma
    from the plane, up to 4 iterations). Returns (center, normal, inlier
    points)."""
    c = P.mean(axis=0)
    n = np.array([0.0, 0.0, 1.0])
    for _ in range(4):
        _, _, vt = np.linalg.svd(P - c, full_matrices=False)
        n = vt[-1]
        dist = (P - c) @ n
        keep = np.abs(dist) <= (2.5 * float(np.std(dist)) + 1e-9)
        if keep.sum() < 50:
            break
        P = P[keep]
        c = P.mean(axis=0)
    n = n / (np.linalg.norm(n) + 1e-9)
    return c, n, P


def wall_quad_from_depth(
    depth_m: np.ndarray, wall_mask: np.ndarray, focal_px: float, image_shape: tuple[int, ...], coverage: float = 0.99
) -> tuple[np.ndarray, dict] | None:
    """Fit the wall mask's real 3D plane from depth and project its extent
    back into a metric-accurate image-space quad. Returns (quad, info) where
    info has width_m/height_m/normal/center, or None if depth data for this
    mask is too sparse/degenerate to fit (caller should fall back to the
    classical 2D quad detection)."""
    if depth_m is None or wall_mask is None:
        return None
    H, W = depth_m.shape[:2]
    f = float(focal_px)
    cx, cy = W / 2.0, H / 2.0
    if wall_mask.shape[:2] != (H, W):
        wall_mask = cv2.resize(wall_mask, (W, H), interpolation=cv2.INTER_NEAREST)

    P0 = _backproject_mask(depth_m, wall_mask, f)
    if P0 is None:
        return None
    c, n, P = _fit_plane(P0)
    if len(P) < 50:
        return None

    up_img = np.array([0.0, -1.0, 0.0])
    u_up = up_img - (up_img @ n) * n
    nu = float(np.linalg.norm(u_up))
    if nu < 1e-6:
        return None
    u_up /= nu
    u_rt = np.cross(n, u_up)
    u_rt /= np.linalg.norm(u_rt) + 1e-9

    A = (P - c) @ u_rt  # in-plane horizontal, metres
    B = (P - c) @ u_up  # in-plane vertical, metres
    lo = max(0.0, (1.0 - coverage) * 50.0)
    a_lo, a_hi = np.percentile(A, [lo, 100 - lo])
    b_lo, b_hi = np.percentile(B, [lo, 100 - lo])
    if a_hi - a_lo < 1e-3 or b_hi - b_lo < 1e-3:
        return None

    img_pts = []
    for a, b in ((a_lo, b_hi), (a_hi, b_hi), (a_hi, b_lo), (a_lo, b_lo)):
        P3 = c + a * u_rt + b * u_up
        Zc = float(P3[2])
        if Zc <= 1e-3:
            return None
        img_pts.append([cx + f * float(P3[0]) / Zc, cy + f * float(P3[1]) / Zc])

    quad = order_points_robust(np.array(img_pts, dtype=np.float32))
    H_img, W_img = image_shape[:2]
    if cv2.contourArea(quad) < 0.005 * W_img * H_img:
        return None
    for x_, y_ in quad:
        if x_ < -0.7 * W_img or x_ > 1.7 * W_img or y_ < -0.7 * H_img or y_ > 1.7 * H_img:
            return None

    info = {
        "width_m": float(a_hi - a_lo),
        "height_m": float(b_hi - b_lo),
        "normal": [float(v) for v in n],
        "center": [float(v) for v in c],
    }
    return quad, info


def wall_folds_from_depth(depth_m: np.ndarray, mask_gray: np.ndarray, max_folds: int = 2) -> list[int]:
    """Detect up to `max_folds` corner folds in a wall mask from a depth-
    gradient discontinuity — a mask spanning a real room corner has TWO
    distinct planes, and averaging them into one plane fit produces a
    meaningless quad. Returns the fold x-coordinates (image columns), sorted;
    an empty list means the mask is (as far as this can tell) a single flat
    face. Multi-gate validation: the per-column inverse-depth profile must
    fit two segments meaningfully better than one, the two segments' slopes
    must point in OPPOSITE directions (a real corner bends the ceiling line
    in a V/Λ — a same-direction bend is an occlusion kink, not a corner),
    the fold must sit well inside the wall's span, and the mask must have
    substantial height at the fold column (real corners run floor-to-ceiling;
    occlusion kinks don't)."""
    H, W = mask_gray.shape[:2]
    x, y, w, h = cv2.boundingRect(mask_gray)
    if w < max(200, int(0.20 * W)):
        return []

    step = max(1, w // 300)
    xs, ds = [], []
    for col in range(x, x + w, step):
        ys_c = np.where(mask_gray[:, col] > 0)[0]
        if len(ys_c) < 5:
            continue
        z = depth_m[ys_c, col]
        z = z[np.isfinite(z) & (z > 0.1) & (z < 30.0)]
        if len(z) < 5:
            continue
        xs.append(col)
        ds.append(1.0 / float(np.median(z)))

    if len(xs) < 40:
        return []
    xs_arr, ds_arr = np.asarray(xs, np.float64), np.asarray(ds, np.float64)
    ds_arr = ds_arr / (np.median(ds_arr) + 1e-12)
    ds_arr = np.convolve(ds_arr, np.ones(5) / 5.0, mode="same")

    def _fit(sel: np.ndarray) -> tuple[float, float]:
        m, c2 = np.polyfit(xs_arr[sel], ds_arr[sel], 1)
        return m, float(np.sum(np.abs(ds_arr[sel] - (m * xs_arr[sel] + c2))))

    all_sel = np.ones(len(xs_arr), bool)
    _, r0 = _fit(all_sel)
    res0 = r0 / len(xs_arr)

    min_seg = 0.18 * w
    cands = [x + fr * w for fr in np.arange(0.20, 0.81, 0.04)]

    def _eval(folds: list[float]) -> tuple[float, list[float]] | None:
        bounds = [xs_arr[0] - 1] + list(folds) + [xs_arr[-1] + 1]
        total, slopes = 0.0, []
        for i in range(len(bounds) - 1):
            sel = (xs_arr > bounds[i]) & (xs_arr <= bounds[i + 1])
            if sel.sum() < 12 or xs_arr[sel].max() - xs_arr[sel].min() < min_seg:
                return None
            m, r = _fit(sel)
            total += r
            slopes.append(m)
        return total / len(xs_arr), slopes

    def _signif(m_a: float, m_b: float) -> bool:
        return abs(m_a - m_b) * w > 0.20

    best1 = None
    for f1 in cands:
        e = _eval([f1])
        if e and (best1 is None or e[0] < best1[0]):
            best1 = (e[0], e[1], [f1])

    folds: list[float] = []
    if best1 and best1[0] < 0.55 * res0 and _signif(best1[1][0], best1[1][1]):
        folds = best1[2]
        if max_folds >= 2:
            best2 = None
            for i, f1 in enumerate(cands):
                for f2 in cands[i + 1 :]:
                    if f2 - f1 < max(min_seg, 0.22 * w):
                        continue
                    e = _eval([f1, f2])
                    if e and (best2 is None or e[0] < best2[0]):
                        best2 = (e[0], e[1], [f1, f2])
            if (
                best2
                and best2[0] < 0.6 * best1[0]
                and _signif(best2[1][0], best2[1][1])
                and _signif(best2[1][1], best2[1][2])
            ):
                folds = best2[2]

    out = []
    for fx in folds:
        col = int(np.clip(fx, 0, W - 1))
        ys_c = np.where(mask_gray[:, col] > 0)[0]
        if len(ys_c) and (ys_c[-1] - ys_c[0]) >= 0.35 * h:
            out.append(int(fx))
    return sorted(out)


def plane_depth_map(depth_m: np.ndarray, normal: list[float], center: list[float], focal_px: float) -> np.ndarray:
    """Per-pixel depth the fitted wall plane WOULD have at every pixel
    (ray-plane intersection), for comparison against the actually-measured
    depth map."""
    H, W = depth_m.shape[:2]
    cx, cy = W / 2.0, H / 2.0
    n = np.asarray(normal, np.float64)
    c = np.asarray(center, np.float64)
    us, vs = np.meshgrid(np.arange(W, dtype=np.float64), np.arange(H, dtype=np.float64))
    ray_x = (us - cx) / focal_px
    ray_y = (vs - cy) / focal_px
    denom = n[0] * ray_x + n[1] * ray_y + n[2]
    denom = np.where(np.abs(denom) < 1e-9, np.nan, denom)
    return (n @ c) / denom


def protrusion_mask(
    depth_m: np.ndarray, wall_mask: np.ndarray, normal: list[float], center: list[float], focal_px: float
) -> np.ndarray:
    """Pixels inside wall_mask whose measured depth sits clearly in FRONT of
    the fitted wall plane — a TV, shelf, or mounted object the segmentation
    mask didn't already carve out. Returns a 0/255 mask, same shape as
    depth_m."""
    z_plane = plane_depth_map(depth_m, normal, center, focal_px)
    with np.errstate(invalid="ignore"):
        protrude = (z_plane - depth_m) > PROTRUSION_M
    protrude &= np.isfinite(z_plane) & np.isfinite(depth_m) & (depth_m > 0.1)
    protrude &= wall_mask > 0
    out = protrude.astype(np.uint8) * 255
    # Small open to kill single-pixel depth-noise speckle.
    out = cv2.morphologyEx(out, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)))
    return out

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

import math

import cv2
import numpy as np

from app.modules.visualizer.imaging.rug_overlay import order_points_robust
from app.modules.visualizer.imaging.wall import create_super_texture, detect_wall_quad

# Pinhole-camera focal length, approximated as a fraction of the image's
# longer side (no camera calibration data is available) — same ratio the
# reference repo tuned this against.
WALL_FOCAL_RATIO = 0.8

# Depth closer to the camera than the fitted wall plane by more than this
# counts as an obstacle (a TV/shelf/mounted object standing off the wall).
PROTRUSION_M = 0.08

# Auto-repeat target: roughly how many pattern tiles should span the full
# canvas width, independent of resolution or any real-world size — the old
# production tile scale at the frontend's default repeat, as an integer
# tile count.
TARGET_TILES_ACROSS_CANVAS = 12.0


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


def _find_corner_split(mask_gray: np.ndarray) -> int | None:
    """2D-only corner finder — used only when no depth map is available at
    all (wall_folds_from_depth above is the depth-grounded equivalent and
    is preferred whenever depth succeeds). Fits the mask's top (ceiling)
    boundary as one line vs. two, and accepts a two-line split only if it's
    a real room corner: a genuine slope-direction change (not a same-
    direction occlusion kink from furniture/curtains), explains the
    boundary meaningfully better than one line, sits well inside the wall's
    span, and runs floor-to-ceiling at the fold column."""
    H, W = mask_gray.shape
    x, y, w, h = cv2.boundingRect(mask_gray)
    if w < max(200, int(0.25 * W)):
        return None

    xs, tops = [], []
    step = max(1, w // 300)
    for col in range(x, x + w, step):
        ys = np.where(mask_gray[:, col] > 0)[0]
        if len(ys) and ys[0] > 2:
            xs.append(col)
            tops.append(ys[0])
    if len(xs) < 40:
        return None
    xs_arr = np.asarray(xs, np.float64)
    tops_raw = np.asarray(tops, np.float64)

    # Gate 0: the top boundary must be CONTINUOUS. A real ceiling line bends
    # at a corner but never jumps; a jump means an occlusion boundary
    # (curtain, furniture) is cutting the mask — untrustworthy for folds.
    if float(np.max(np.abs(np.diff(tops_raw)))) > max(20.0, 0.08 * h):
        return None
    tops_arr = np.convolve(tops_raw, np.ones(5) / 5.0, mode="same")

    def _fit(px: np.ndarray, py: np.ndarray) -> tuple[float, float, float]:
        m, c = np.polyfit(px, py, 1)
        return m, c, float(np.mean(np.abs(py - (m * px + c))))

    _, _, res_single = _fit(xs_arr, tops_arr)
    best = None
    for frac in np.arange(0.28, 0.73, 0.05):
        sx = x + frac * w
        li = xs_arr < sx
        n_l, n_r = int(li.sum()), int((~li).sum())
        if n_l < 15 or n_r < 15:
            continue
        if (xs_arr[li].max() - xs_arr[li].min()) < 0.22 * w or (xs_arr[~li].max() - xs_arr[~li].min()) < 0.22 * w:
            continue
        ml, cl, rl = _fit(xs_arr[li], tops_arr[li])
        mr, cr, rr = _fit(xs_arr[~li], tops_arr[~li])
        res_two = (rl * n_l + rr * n_r) / len(xs_arr)
        if best is None or res_two < best[0]:
            best = (res_two, ml, cl, mr, cr, sx)

    if best is None:
        return None
    res_two, ml, cl, mr, cr, best_sx = best

    # Gate 1: two segments must explain the top boundary far better than one.
    if res_two > 0.55 * res_single:
        return None
    # Gate 2: the fold must be a real slope change, both slopes architectural.
    if abs(ml - mr) < 0.07 or abs(ml) > 0.8 or abs(mr) > 0.8:
        return None
    # Gate 3: a real room corner bends the ceiling line in a V or Λ — the two
    # slopes point in OPPOSITE directions (one may be near-flat for a
    # frontal wall). A same-direction bend is an occlusion kink: reject.
    ml0, mr0 = (ml if abs(ml) >= 0.04 else 0.0), (mr if abs(mr) >= 0.04 else 0.0)
    if ml0 * mr0 > 0:
        return None
    # Gate 4: the fold (segment intersection) must sit inside the wall span.
    xi = (cr - cl) / (ml - mr)
    if not (x + 0.25 * w <= xi <= x + 0.75 * w):
        return None
    # Gate 5: the intersection must agree with the best split position — a
    # kink at one end (curtain/furniture cut) fits badly and drifts.
    if abs(xi - best_sx) > 0.15 * w:
        return None
    # Gate 6: the wall must have substantial height at the fold column; real
    # room corners run floor-to-ceiling, occlusion kinks don't.
    col = int(np.clip(xi, 0, W - 1))
    ys_at_fold = np.where(mask_gray[:, col] > 0)[0]
    if len(ys_at_fold) == 0 or (ys_at_fold[-1] - ys_at_fold[0]) < 0.35 * h:
        return None
    return int(xi)


def _planes_via_depth(
    mask_gray: np.ndarray, depth_map: np.ndarray, focal_px: float
) -> list[tuple[np.ndarray, tuple[int, int], float | None]] | None:
    """Split the mask at any depth-detected corner folds, fit each segment's
    own plane. Falls back to the classical 2D quad per-segment if a
    segment's depth fit doesn't contain it well."""
    H, W = mask_gray.shape[:2]
    if depth_map.shape[:2] != (H, W):
        depth_map = cv2.resize(depth_map.astype(np.float32), (W, H), interpolation=cv2.INTER_LINEAR)

    folds = wall_folds_from_depth(depth_map, mask_gray)
    edges = [0] + folds + [W]
    planes: list[tuple[np.ndarray, tuple[int, int], float | None]] = []

    for i in range(len(edges) - 1):
        x0, x1 = edges[i], edges[i + 1]
        seg = mask_gray.copy()
        seg[:, :x0] = 0
        seg[:, x1:] = 0
        if cv2.countNonZero(seg) < 500:
            if len(edges) > 2:
                continue
            return None

        res = wall_quad_from_depth(depth_map, seg, focal_px, (H, W))
        if res is not None:
            quad, info = res
            if quad_mask_containment(quad, seg) >= 0.85:
                planes.append((quad, (x0, x1), info["width_m"]))
                continue

        q2 = detect_wall_quad(seg)
        if q2 is None:
            return None
        planes.append((q2, (x0, x1), None))
    return planes if planes else None


def detect_wall_planes(
    mask_gray: np.ndarray, depth_map: np.ndarray | None = None, focal_px: float | None = None
) -> list[tuple[np.ndarray, tuple[int, int], float | None]]:
    """Every wall face in this mask, as (quad, (x0,x1) pixel band,
    width_m|None) tuples — a corner-spanning mask yields 2+ faces, each
    with its own perspective quad, instead of one plane averaged across
    both. Tries depth first (wall_folds_from_depth + wall_quad_from_depth
    per segment), falls back to a classical 2D corner split
    (_find_corner_split + detect_wall_quad per half), falls back again to a
    single whole-mask detect_wall_quad. Never raises — returns [] only if
    even the single-quad fallback fails."""
    H, W = mask_gray.shape
    if depth_map is not None:
        try:
            f = focal_px if focal_px else WALL_FOCAL_RATIO * max(H, W)
            planes = _planes_via_depth(mask_gray, depth_map, f)
            if planes:
                return planes
        except Exception:
            pass

    split_x = _find_corner_split(mask_gray)
    if split_x is not None:
        left, right = mask_gray.copy(), mask_gray.copy()
        left[:, split_x:], right[:, :split_x] = 0, 0
        quad_l = detect_wall_quad(left)
        quad_r = detect_wall_quad(right)
        if quad_l is not None and quad_r is not None:
            return [(quad_l, (0, split_x), None), (quad_r, (split_x, W), None)]

    quad = detect_wall_quad(mask_gray)
    if quad is None:
        return []
    return [(quad, (0, W), None)]


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


# ---- wallpaper/paint tiling: real, live reference implementation ----
#
# Supersedes wall.py::apply_pattern (and wall.py::blend_hard_replace via
# shared.py) for the wall category — the reference repo's own app.py has
# the import from utils/wall.py commented out and calls this module's
# apply_pattern instead. wall.py's own 2D quad detection is still reused
# directly (detect_wall_planes above, and solely for the 2D fallback path
# below) — only the single-quad flat application wall.py did is replaced.


def _get_lighting_map(img: np.ndarray, blur_k: int = 51) -> np.ndarray:
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    if blur_k % 2 == 0:
        blur_k += 1
    gray = cv2.GaussianBlur(gray, (blur_k, blur_k), 0)
    return gray.astype(np.float32) / 255.0


def blend_hard_replace(
    original: np.ndarray, texture: np.ndarray, mask_gray: np.ndarray, shadow_strength: float = 0.6
) -> np.ndarray:
    """Wall-scoped copy of shared.blend_hard_replace with one real fix:
    normalizes the lighting map by the MEAN LUMINANCE INSIDE THE MASK
    before shading, so only the RELATIVE shading (shadow gradients, corner
    darkening) transfers to the new texture. Without this, a dark or
    already-wallpapered wall imprints its overall darkness onto the
    product and the result comes out muddy. Kept as a separate copy here
    rather than patching shared.py, matching how the reference itself keeps
    this as its own copy in wall_depth.py rather than touching the old
    shared version floor/rug still use — this is a wall-specific fix, not
    a blanket relighting change."""
    orig_f = original.astype(np.float32) / 255.0
    tex_f = texture.astype(np.float32) / 255.0
    lighting_map = _get_lighting_map(original, blur_k=51)

    inside = mask_gray > 127
    if np.any(inside):
        mean_l = float(lighting_map[inside].mean())
        if mean_l > 1e-4:
            lighting_map = np.clip(lighting_map / mean_l, 0.0, 1.6)

    lighting_3ch = cv2.merge([lighting_map, lighting_map, lighting_map])
    shaded_texture = tex_f * (lighting_3ch**shadow_strength)
    mask_f = mask_gray.astype(np.float32) / 255.0
    mask_f = cv2.GaussianBlur(mask_f, (3, 3), 0)
    mask_3ch = cv2.merge([mask_f, mask_f, mask_f])
    result = (orig_f * (1.0 - mask_3ch)) + (shaded_texture * mask_3ch)
    return np.clip(result * 255, 0, 255).astype(np.uint8)


def _warp_plane(
    wall_tex: np.ndarray,
    tex_aspect: float,
    quad: np.ndarray,
    dst_w: float,
    dst_h: float,
    n_tiles: int,
    out_w: int,
    out_h: int,
    cover_pts: np.ndarray | None = None,
) -> np.ndarray:
    tex_h, tex_w = wall_tex.shape[:2]
    # Floor the tile at ~16px in both dimensions so absurd manual repeat
    # values can't degenerate into sub-pixel tiles.
    tile_size_w = max(dst_w / float(n_tiles), 16.0 * max(1.0, tex_aspect))

    # How far past the quad edges must the texture extend (in flat texture
    # space) to cover every masked pixel? Map the mask bounds back through
    # the inverse homography to find out.
    need_x = need_y = 0.0
    if cover_pts is not None and len(cover_pts) > 0:
        src0 = np.array([[0, 0], [dst_w, 0], [dst_w, dst_h], [0, dst_h]], dtype=np.float32)
        M0 = cv2.getPerspectiveTransform(src0, quad)
        try:
            Minv = np.linalg.inv(M0)
            pts = cv2.perspectiveTransform(np.asarray(cover_pts, dtype=np.float32).reshape(1, -1, 2), Minv)[0]
            if np.all(np.isfinite(pts)):
                # Memory cap; the void-fill net covers pathological leftovers.
                need_x = min(max(0.0, float(-pts[:, 0].min()), float(pts[:, 0].max() - dst_w)), 1.0 * dst_w)
                need_y = min(max(0.0, float(-pts[:, 1].min()), float(pts[:, 1].max() - dst_h)), 1.0 * dst_h)
        except np.linalg.LinAlgError:
            pass

    # Pre-crop the product image to its visible rows/columns when a tile
    # overflows the covered area: identical visible pixels, without
    # allocating an oversized tile in memory.
    tex_eff = wall_tex
    tile_h_px = tile_size_w / tex_aspect
    if tile_h_px > dst_h + need_y:
        crop_h = max(1, min(tex_h, int(round(tex_h * (dst_h + need_y) / tile_h_px))))
        tex_eff = tex_eff[:crop_h, :]
    if tile_size_w > dst_w + need_x:
        crop_w = max(1, min(tex_w, int(round(tex_w * (dst_w + need_x) / tile_size_w))))
        tex_eff = tex_eff[:, :crop_w]
        tile_size_w = dst_w + need_x

    ph_e, pw_e = tex_eff.shape[:2]
    tw = max(1, int(tile_size_w))
    th = max(1, int(ph_e * (tile_size_w / float(pw_e))))
    pad_x_tiles, pad_y_tiles = max(1, int(math.ceil(need_x / tw))), max(1, int(math.ceil(need_y / th)))

    super_tex, pts_src = create_super_texture(
        tex_eff, int(dst_w), int(dst_h), tile_size_w, pad_x_tiles=pad_x_tiles, pad_y_tiles=pad_y_tiles
    )
    M = cv2.getPerspectiveTransform(pts_src, quad)
    return cv2.warpPerspective(super_tex, M, (out_w, out_h), flags=cv2.INTER_LINEAR)


def _fill_uncovered(texture: np.ndarray, region_mask: np.ndarray) -> np.ndarray:
    """Fill masked pixels the plane warps missed with the nearest textured
    pixel. A masked pixel must never render as a black void."""
    empty = (texture.max(axis=2) == 0).astype(np.uint8)
    holes = (empty > 0) & (region_mask > 0)
    if not holes.any() or not (empty == 0).any():
        return texture
    try:
        _, labels = cv2.distanceTransformWithLabels(empty, cv2.DIST_L2, 3, labelType=cv2.DIST_LABEL_PIXEL)
        src_yx = np.argwhere(empty == 0)
        lab_at_src = labels[empty == 0]
        coord = np.zeros((int(lab_at_src.max()) + 1, 2), np.int32)
        coord[lab_at_src] = src_yx
        hy, hx = np.where(holes)
        nyx = coord[labels[hy, hx]]
        texture[hy, hx] = texture[nyx[:, 0], nyx[:, 1]]
    except Exception:
        pass
    return texture


def _split_counts(total: int, widths: list[float]) -> list[int]:
    k = len(widths)
    if k == 1:
        return [total]
    total = max(total, k)
    wsum = float(sum(widths))
    raw = [total * float(wd) / wsum for wd in widths]
    counts = [max(1, int(r + 0.5)) for r in raw]
    while sum(counts) > total:
        over = [(counts[j] - raw[j], j) for j in range(k) if counts[j] > 1]
        if not over:
            break
        _, j = max(over)
        counts[j] -= 1
    while sum(counts) < total:
        _, j = min((counts[j] - raw[j], j) for j in range(k))
        counts[j] += 1
    return counts


def apply_pattern(
    room_img: np.ndarray,
    wall_tex: np.ndarray,
    mask_img: np.ndarray,
    fallback_repeat: float | None = None,
    depth_map: np.ndarray | None = None,
    shadow_strength: float = 0.6,
) -> tuple[np.ndarray, int | None]:
    """Returns (result_image, auto_repeat) — auto_repeat is the INTEGER
    total repeat chosen by the auto logic (reported back for the frontend's
    step-1 slider), or None when a manual repeat was used / the layer was
    skipped.

    Repeat semantics (auto and manual share them, always integer):
      - repeat = total tiles across the wall's width. On corner walls (two
        detected planes) it is distributed proportionally to plane widths,
        each plane getting at least 1.
      - tile_width = plane_width / N_plane; tile height always follows the
        product image's aspect ratio; rows tile downward and overflow crops
        at the wall edges. The pattern is never stretched or compressed —
        the repeat only changes its scale.
      - Auto reproduces the old production tile scale (tile of roughly
        canvas_width / TARGET_TILES_ACROSS_CANVAS), converted to an integer
        count for the detected wall span.

    depth_map: optional metric depth (metres). When present, wall planes
    come from true 3D geometry: disparity creases give room-corner folds
    (up to 2 corners / 3 faces, even in one singular mask) and each face
    gets a depth-fitted perspective quad. Every depth failure falls back to
    the 2D pipeline — depth is advisory only, never required.
    """
    H, W = room_img.shape[:2]
    mask_gray = cv2.cvtColor(mask_img, cv2.COLOR_BGR2GRAY) if len(mask_img.shape) == 3 else mask_img
    mask_gray = cv2.resize(mask_gray, (W, H), interpolation=cv2.INTER_NEAREST)
    _, thresh = cv2.threshold(mask_gray, 127, 255, cv2.THRESH_BINARY)

    planes = detect_wall_planes(thresh, depth_map=depth_map, focal_px=WALL_FOCAL_RATIO * max(H, W))
    if not planes:
        return room_img, None

    try:
        tex_h, tex_w = wall_tex.shape[:2]
        tex_aspect = tex_w / float(tex_h)

        # Flat (pre-warp) size of each architectural plane.
        sized = []
        for quad, band, width_m in planes:
            dst_w = max(float(np.linalg.norm(quad[0] - quad[1])), float(np.linalg.norm(quad[3] - quad[2])))
            dst_h = max(float(np.linalg.norm(quad[0] - quad[3])), float(np.linalg.norm(quad[1] - quad[2])))
            if dst_w >= 2 and dst_h >= 2:
                sized.append((quad, band, dst_w, dst_h, width_m))

        if not sized:
            return room_img, None

        widths = [p[2] for p in sized]
        span_w = float(sum(widths))
        min_total = len(sized)

        # Distribute repeats by REAL metric widths when depth provided them —
        # a foreshortened plane is narrow in pixels but not in metres.
        metric_widths = [p[4] for p in sized]
        split_widths = metric_widths if len(sized) > 1 and all(wm is not None and wm > 0 for wm in metric_widths) else widths

        is_auto = fallback_repeat is None or float(fallback_repeat) == 2.0 or float(fallback_repeat) <= 0

        if is_auto:
            raw = TARGET_TILES_ACROSS_CANVAS * span_w / float(W)
            repeat_total = max(min_total, int(raw + 0.5))
        else:
            repeat_total = max(min_total, int(round(float(fallback_repeat))))

        per_plane = _split_counts(repeat_total, split_widths)

        warped_total = np.zeros((H, W, 3), dtype=np.uint8)

        def _mask_bounds(region: np.ndarray) -> np.ndarray | None:
            # Bounding corners of the masked pixels the warp must cover.
            bx, by, bw2, bh2 = cv2.boundingRect(np.ascontiguousarray(region))
            if bw2 == 0 or bh2 == 0:
                return None
            return np.array([[bx, by], [bx + bw2, by], [bx + bw2, by + bh2], [bx, by + bh2]], dtype=np.float32)

        if len(sized) > 1:
            # Underlay for corner walls: one single-quad warp over the whole
            # mask, so any pixel the per-plane warps miss falls back to
            # plausible pattern instead of a black void.
            base_quad = detect_wall_quad(thresh)
            if base_quad is not None:
                b_w = max(float(np.linalg.norm(base_quad[0] - base_quad[1])), float(np.linalg.norm(base_quad[3] - base_quad[2])))
                b_h = max(float(np.linalg.norm(base_quad[0] - base_quad[3])), float(np.linalg.norm(base_quad[1] - base_quad[2])))
                if b_w >= 2 and b_h >= 2:
                    warped_total = _warp_plane(
                        wall_tex, tex_aspect, base_quad, b_w, b_h, repeat_total, W, H, cover_pts=_mask_bounds(thresh)
                    )

        for (quad, band, dst_w, dst_h, _wm), n_tiles in zip(sized, per_plane):
            x0, x1 = band
            cover = _mask_bounds(thresh[:, x0:x1])
            if cover is not None:
                cover[:, 0] += x0
            warped = _warp_plane(wall_tex, tex_aspect, quad, dst_w, dst_h, n_tiles, W, H, cover_pts=cover)
            plane_slice = warped[:, x0:x1]
            covered = plane_slice.max(axis=2) > 0
            dest = warped_total[:, x0:x1]
            dest[covered] = plane_slice[covered]

        # Safety net: any masked pixel every warp missed gets filled from the
        # nearest textured pixel — a void inside the wall is never acceptable.
        warped_total = _fill_uncovered(warped_total, thresh)
        result = blend_hard_replace(room_img, warped_total, mask_gray, shadow_strength=shadow_strength)
        return result, (int(repeat_total) if is_auto else None)
    except Exception:
        return room_img, None

"""Wall-art placement engine: given a room image, ONE wall mask (holes =
carved obstacles: TV, paintings, windows...), the product image and optional
physical dimensions (cm), picks the best wall face, finds the clear area
(mask holes + depth protrusions), and computes WHERE the art should hang.

Port of the Flask client-backend's `utils/wallart.py::analyze_wallart_scene`
— the real, validated placement algorithm, not the naive "center the art in
whatever LAB-color clear region we found" logic this replaces in
VisualizerService.wallart_visualizer_scene. Placement rules (per the
reference's own docstring, "agreed 2026-07-15"):
  - Real-world sizing via the metric wall plane; no dimensions -> 75cm on
    the longer side at the product image's own aspect ratio.
  - Obstacles = wall-mask holes + pixels protruding in front of the fitted
    wall plane (depth check) — reuses wall_depth.protrusion_mask.
  - Vertical: percentage rule first (art centre ~57% down the wall face);
    if no clear spot there, fall back to 145cm above the wall's floor line;
    if that fails too, the nearest clear spot. Horizontal: centred in the
    widest clear run.
  - Art at true size; shrunk (aspect kept) only when it cannot fit ->
    response flags fitted=True.
  - Corner-spanning masks: the art goes on the SINGLE face with the largest
    clear area (art never folds across a corner) — see
    wall_depth.wall_folds_from_depth.

Everything degrades: no depth map -> 2D quad detection (wall.detect_wall_quad)
with an assumed 2.6m wall height for metric scale. Never raises for a
degraded/undetectable scene — returns None, and the caller falls back to the
classical (pre-depth) path, matching this endpoint's established
never-hard-fail principle.

Pure computation, same convention as every other imaging/ module: arrays in,
a result dict out (including the chosen face_mask, for the caller to encode)
— no I/O, no storage, no network calls.
"""

from __future__ import annotations

import cv2
import numpy as np

from app.modules.visualizer.imaging import wall, wall_depth

M_TO_FT = 3.280839895
DEFAULT_LONG_SIDE_M = 0.75  # default art size when no product dimensions
ASSUMED_WALL_HEIGHT_M = 2.6  # metric anchor for the no-depth fallback path
EYE_LEVEL_FRAC = 0.57  # percentage rule: art centre ~57% down the face
FLOOR_ANCHOR_M = 1.45  # fallback rule: art centre 145cm above the floor line
BAND_FRAC = 0.10  # vertical search band around the target row
MARGIN_M = 0.05  # clearance kept around the art (5cm)
MIN_SHRINK = 0.35  # never shrink below 35% of the requested size
PLANE_GRID_MAX = 900  # plane-space raster cap (px)


def _pick_wall_face(
    mask: np.ndarray, depth_map: np.ndarray | None, focal_px: float
) -> tuple[np.ndarray | None, np.ndarray | None, float | None, float | None, dict | None, bool]:
    """Choose the single wall face to hang on. Returns
    (face_mask, quad, width_m, height_m, plane_info|None, used_depth)."""
    H, W = mask.shape[:2]

    if depth_map is not None:
        try:
            folds = wall_depth.wall_folds_from_depth(depth_map, mask)
            edges = [0] + folds + [W]
            best = None
            for i in range(len(edges) - 1):
                x0, x1 = edges[i], edges[i + 1]
                seg = mask.copy()
                seg[:, :x0] = 0
                seg[:, x1:] = 0
                if cv2.countNonZero(seg) < 800:
                    continue
                res = wall_depth.wall_quad_from_depth(depth_map, seg, focal_px, (H, W))
                if res is None:
                    continue
                quad, info = res
                if wall_depth.quad_mask_containment(quad, seg) < 0.80:
                    continue
                prot = wall_depth.protrusion_mask(depth_map, seg, info["normal"], info["center"], focal_px)
                clear_px = cv2.countNonZero(seg) - cv2.countNonZero(prot)
                if best is None or clear_px > best[0]:
                    best = (clear_px, seg, quad, info)
            if best is not None:
                _, seg, quad, info = best
                return seg, quad, info["width_m"], info["height_m"], info, True
        except Exception:
            pass

    # 2D fallback: single quad over the whole mask, assumed wall height
    quad = wall.detect_wall_quad(mask)
    if quad is None:
        return None, None, None, None, None, False
    dst_w = max(float(np.linalg.norm(quad[0] - quad[1])), float(np.linalg.norm(quad[3] - quad[2])))
    dst_h = max(float(np.linalg.norm(quad[0] - quad[3])), float(np.linalg.norm(quad[1] - quad[2])))
    if dst_w < 2 or dst_h < 2:
        return None, None, None, None, None, False
    height_m = ASSUMED_WALL_HEIGHT_M
    width_m = height_m * (dst_w / dst_h)
    return mask, quad, width_m, height_m, None, False


def _largest_clear_rect_around(
    clear01: np.ndarray, cx: float, cy: float, half_w: float, half_h: float
) -> tuple[int, int, int, int]:
    """Grow a clear rectangle outward from the placement rect — a true
    on-plane clear region the frontend can use as drag bounds."""
    gh, gw = clear01.shape[:2]
    x0 = max(0, int(cx - half_w))
    x1 = min(gw - 1, int(cx + half_w))
    y0 = max(0, int(cy - half_h))
    y1 = min(gh - 1, int(cy + half_h))

    def row_clear(y: int, a: int, b: int) -> bool:
        return 0 <= y < gh and bool(clear01[y, a : b + 1].all())

    def col_clear(x: int, a: int, b: int) -> bool:
        return 0 <= x < gw and bool(clear01[a : b + 1, x].all())

    grown = True
    while grown:
        grown = False
        if col_clear(x0 - 1, y0, y1):
            x0 -= 1
            grown = True
        if col_clear(x1 + 1, y0, y1):
            x1 += 1
            grown = True
        if row_clear(y0 - 1, x0, x1):
            y0 -= 1
            grown = True
        if row_clear(y1 + 1, x0, x1):
            y1 += 1
            grown = True
    return x0, y0, x1, y1


def _find_center(valid: np.ndarray, gh: int, gw: int, target_ys: list[float]) -> tuple[int, int] | None:
    """Pick the placement centre from the valid-centre map: for each target
    row (in priority order) take the middle of the widest valid run inside
    the vertical band; else the valid pixel nearest to the first target."""
    band = max(2, int(BAND_FRAC * gh))
    for ty in target_ys:
        ty = int(np.clip(ty, 0, gh - 1))
        y_lo, y_hi = max(0, ty - band), min(gh, ty + band + 1)
        band_valid = valid[y_lo:y_hi].any(axis=0)
        if not band_valid.any():
            continue
        best_run, run_start, cur_start = None, None, None
        for xcol in range(gw + 1):
            on = xcol < gw and band_valid[xcol]
            if on and cur_start is None:
                cur_start = xcol
            elif not on and cur_start is not None:
                if best_run is None or (xcol - cur_start) > best_run:
                    best_run, run_start = xcol - cur_start, cur_start
                cur_start = None
        cx = run_start + best_run // 2
        ys_at_cx = np.where(valid[y_lo:y_hi, cx])[0]
        cy = y_lo + ys_at_cx[np.argmin(np.abs(ys_at_cx + y_lo - ty))]
        return int(cx), int(cy)

    ys, xs = np.where(valid)
    if len(xs) == 0:
        return None
    ty = int(np.clip(target_ys[0], 0, gh - 1))
    d2 = (xs - gw / 2.0) ** 2 + (ys - ty) ** 2
    i = int(np.argmin(d2))
    return int(xs[i]), int(ys[i])


def analyze_wallart_scene(
    room_img: np.ndarray,
    wall_mask: np.ndarray,
    product_img: np.ndarray,
    product_dims_cm: dict[str, float] | None = None,
    depth_map: np.ndarray | None = None,
) -> dict | None:
    """Returns a dict of normalized placement data, or None if no wall face
    could be analyzed. All *_norm values are normalized by the room image
    dimensions passed in (resolution-independent)."""
    H, W = room_img.shape[:2]
    focal_px = wall_depth.WALL_FOCAL_RATIO * max(H, W)

    mask = wall_mask
    if len(mask.shape) == 3:
        mask = cv2.cvtColor(mask, cv2.COLOR_BGR2GRAY)
    if mask.shape[:2] != (H, W):
        mask = cv2.resize(mask, (W, H), interpolation=cv2.INTER_NEAREST)
    _, mask = cv2.threshold(mask, 127, 255, cv2.THRESH_BINARY)
    if cv2.countNonZero(mask) < 0.005 * H * W:
        return None

    dmap = None
    if depth_map is not None:
        dmap = np.asarray(depth_map, np.float32)
        if dmap.shape[:2] != (H, W):
            dmap = cv2.resize(dmap, (W, H), interpolation=cv2.INTER_LINEAR)

    face_mask, quad, wall_w_m, wall_h_m, plane_info, used_depth = _pick_wall_face(mask, dmap, focal_px)
    if face_mask is None:
        return None

    # Clear map: mask holes are already obstacles (carved by segmentation);
    # add depth protrusions in front of the plane (missed TVs, shelves).
    clear_img = face_mask.copy()
    if used_depth and dmap is not None and plane_info is not None:
        prot = wall_depth.protrusion_mask(dmap, face_mask, plane_info["normal"], plane_info["center"], focal_px)
        clear_img[prot > 0] = 0

    # Rectify to wall-plane space (true metres on the wall).
    s = min(300.0, PLANE_GRID_MAX / max(wall_w_m, wall_h_m))  # px per metre
    gw = max(8, int(round(wall_w_m * s)))
    gh = max(8, int(round(wall_h_m * s)))
    rect_pts = np.array([[0, 0], [gw, 0], [gw, gh], [0, gh]], dtype=np.float32)
    H_plane = cv2.getPerspectiveTransform(quad.astype(np.float32), rect_pts)
    H_img = np.linalg.inv(H_plane)
    clear_plane = cv2.warpPerspective(clear_img, H_plane, (gw, gh), flags=cv2.INTER_NEAREST)
    clear01 = clear_plane > 127

    # Art physical size.
    if product_dims_cm and product_dims_cm.get("width") and product_dims_cm.get("length"):
        art_w_m = float(product_dims_cm["width"]) / 100.0
        art_h_m = float(product_dims_cm["length"]) / 100.0
        dims_given = True
    else:
        ph, pw = product_img.shape[:2]
        aspect = pw / float(ph)
        if aspect >= 1.0:
            art_w_m, art_h_m = DEFAULT_LONG_SIDE_M, DEFAULT_LONG_SIDE_M / aspect
        else:
            art_w_m, art_h_m = DEFAULT_LONG_SIDE_M * aspect, DEFAULT_LONG_SIDE_M
        dims_given = False

    # Find a spot: shrink only if the true size can't fit anywhere.
    clear_f = clear01.astype(np.float32)
    margin_px = MARGIN_M * s
    chosen = None
    for scale in np.arange(1.0, MIN_SHRINK - 1e-9, -0.1):
        aw = art_w_m * scale * s
        ah = art_h_m * scale * s
        win_w = max(1, int(aw + 2 * margin_px)) | 1
        win_h = max(1, int(ah + 2 * margin_px)) | 1
        if win_w > gw or win_h > gh:
            continue
        frac = cv2.boxFilter(clear_f, cv2.CV_32F, (win_w, win_h), normalize=True)
        valid = frac >= 0.995
        valid[: win_h // 2, :] = False
        valid[gh - win_h // 2 :, :] = False
        valid[:, : win_w // 2] = False
        valid[:, gw - win_w // 2 :] = False
        if not valid.any():
            continue

        target_ys = [EYE_LEVEL_FRAC * gh, gh - FLOOR_ANCHOR_M * s]
        center = _find_center(valid, gh, gw, target_ys)
        if center is not None:
            chosen = (scale, aw, ah, center)
            break

    if chosen is None:
        return None

    scale, aw, ah, (pcx, pcy) = chosen

    def to_img(pts_plane: list[list[float]]) -> np.ndarray:
        pts = np.asarray(pts_plane, np.float32).reshape(1, -1, 2)
        return cv2.perspectiveTransform(pts, H_img.astype(np.float32))[0]

    half_w, half_h = aw / 2.0, ah / 2.0
    art_rect_plane = [
        [pcx - half_w, pcy - half_h],
        [pcx + half_w, pcy - half_h],
        [pcx + half_w, pcy + half_h],
        [pcx - half_w, pcy + half_h],
    ]
    placement_quad = to_img(art_rect_plane)
    placement_center = to_img([[pcx, pcy]])[0]

    cr = _largest_clear_rect_around(clear01, pcx, pcy, half_w + margin_px, half_h + margin_px)
    clear_quad = to_img([[cr[0], cr[1]], [cr[2], cr[1]], [cr[2], cr[3]], [cr[0], cr[3]]])

    def norm_pts(pts) -> list[list[float]]:
        return [[round(float(px) / W, 6), round(float(py) / H, 6)] for px, py in pts]

    return {
        "wall_quad_norm": norm_pts(quad),
        "placement_quad_norm": norm_pts(placement_quad),
        "placement_center_norm": norm_pts([placement_center])[0],
        "clear_region_quad_norm": norm_pts(clear_quad),
        "wall_width_ft": round(float(wall_w_m) * M_TO_FT, 2),
        "wall_height_ft": round(float(wall_h_m) * M_TO_FT, 2),
        "art_width_ft": round(float(art_w_m) * float(scale) * M_TO_FT, 2),
        "art_height_ft": round(float(art_h_m) * float(scale) * M_TO_FT, 2),
        "fitted": bool(scale < 0.999),
        "used_depth": bool(used_depth),
        "dims_given": dims_given,
        "face_mask": face_mask,  # internal: caller encodes this for the response
    }

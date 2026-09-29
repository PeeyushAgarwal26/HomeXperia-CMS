"""
Curtain pattern application, ported verbatim from
`homexperia-client-backend/utils/curtain.py`.
"""

from __future__ import annotations

import re

import cv2
import numpy as np


def parse_width_to_cm(width_str) -> float | None:
    if not width_str:
        return None

    match = re.search(r"(\d+\.?\d*)", str(width_str))
    if not match:
        return None

    val = float(match.group(1))
    return val


def get_lighting_map(img: np.ndarray, blur_k: int = 3) -> np.ndarray:
    """Local variant used only by curtain's blend_realism (blur_k=3
    default, distinct from the shared blur_k=51 helper in shared.py)."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (blur_k, blur_k), 0)
    return gray.astype(np.float32) / 255.0


def fill_enclosed_holes(mask: np.ndarray) -> np.ndarray:
    """Fills spurious interior gaps in a SAM mask (isolated black islands
    fully surrounded by white) while leaving real occlusions intact — e.g. a
    plant pot sitting in front of a curtain correctly bites into the mask
    from the outside edge, but a small hole floating in the middle of an
    otherwise continuous curtain is virtually always a segmentation
    artifact, not a real gap in the fabric. Flood-filling the background
    from a corner and inverting isolates exactly those enclosed holes:
    anything the flood fill can't reach from outside must be enclosed.

    The flood-fill/bitwise steps need a clean 0/255 input, so they run on a
    throwaway binarized copy purely to find *which* pixels are enclosed —
    the returned mask keeps every other pixel's original continuous value
    (e.g. an anti-aliased edge ramp from a LINEAR-interpolated resize).
    Bitwise-OR'ing that ramp directly against a binary mask, as an earlier
    version of this function did, snapped every partial edge value to 255
    and silently re-introduced a jagged boundary."""
    h, w = mask.shape[:2]
    binary = np.where(mask > 10, np.uint8(255), np.uint8(0))
    flood = binary.copy()
    flood_fill_mask = np.zeros((h + 2, w + 2), np.uint8)
    cv2.floodFill(flood, flood_fill_mask, (0, 0), 255)
    enclosed_holes = cv2.bitwise_not(flood)
    return np.where(enclosed_holes > 0, np.uint8(255), mask)


def is_panel_product(product_data: dict | None) -> bool:
    """A "panel" product gets a single, non-repeating pattern warped into its
    real perspective quad (see warp_panel_texture) instead of being tiled
    flat and square — matching how the reference implementation flags it,
    via either of these two free-text fields containing the word "panel"."""
    if not isinstance(product_data, dict):
        return False
    for key in ("manufacture_type", "design_no"):
        value = product_data.get(key)
        if isinstance(value, str) and "panel" in value.lower():
            return True
    return False


def fill_voids(texture: np.ndarray, mask_gray: np.ndarray) -> np.ndarray:
    """Patch masked pixels the warp missed with the nearest textured pixel.
    A masked pixel must never render as a black hole."""
    empty = (texture.max(axis=2) == 0).astype(np.uint8)
    holes = (empty > 0) & (mask_gray > 0)
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


def warp_panel_texture(pattern: np.ndarray, quad: np.ndarray, area_w: int, area_h: int) -> np.ndarray:
    """Render one panel design into the perspective quad it actually hangs in.

    The design's height is fitted to the panel's full drop — rod to hem, which
    for an occluded panel runs past the furniture hiding it — and its width is
    centre-cropped. So the top border always lands at the rod and the bottom
    motif at the hem, on every panel of a window, whatever each panel's own
    width or depth in the room, and the design's aspect ratio is never
    distorted. The quad then puts it in the curtain's own perspective, so bands
    across the fabric run parallel to the rod instead of square to the frame.
    """
    quad = np.asarray(quad, dtype=np.float32).reshape(4, 2)

    # Rectified panel size: average the opposing edges, so the design is laid
    # out flat in the panel's own proportions before it goes into perspective.
    dst_w = max(8, int(round((np.linalg.norm(quad[1] - quad[0]) + np.linalg.norm(quad[2] - quad[3])) / 2.0)))
    dst_h = max(8, int(round((np.linalg.norm(quad[3] - quad[0]) + np.linalg.norm(quad[2] - quad[1])) / 2.0)))

    ph, pw = pattern.shape[:2]
    scaled_w = max(1, int(round(pw * (dst_h / float(ph)))))
    flat = cv2.resize(pattern, (scaled_w, dst_h), interpolation=cv2.INTER_LANCZOS4)

    if scaled_w >= dst_w:
        crop_x = (scaled_w - dst_w) // 2
        flat = flat[:, crop_x : crop_x + dst_w]
    else:
        # A design narrower than the panel it has to cover: hold the edge
        # columns out to the sides rather than leave the fabric bare.
        pad = dst_w - scaled_w
        flat = cv2.copyMakeBorder(flat, 0, 0, pad // 2, pad - pad // 2, cv2.BORDER_REPLICATE)

    src = np.array([[0, 0], [dst_w, 0], [dst_w, dst_h], [0, dst_h]], dtype=np.float32)
    M = cv2.getPerspectiveTransform(src, quad)
    # The quad is fitted to cover the mask, so the border mode only ever paints
    # a few pixels of slop. REFLECT is what it should paint: replicating an
    # edge row drags one line of the design out into streaks, while a mirrored
    # sliver still reads as fabric.
    return cv2.warpPerspective(flat, M, (area_w, area_h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)


def tile_texture(pattern: np.ndarray, area_w: int, area_h: int, tile_size_w: float) -> np.ndarray:
    ph, pw = pattern.shape[:2]
    scale = tile_size_w / float(pw)
    tile_size_h = int(ph * scale)
    tile = cv2.resize(pattern, (int(tile_size_w), int(tile_size_h)), interpolation=cv2.INTER_LANCZOS4)

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


def blend_realism(
    original: np.ndarray,
    texture: np.ndarray,
    mask_gray: np.ndarray,
    opacity: float = 1.0,
    shadow_strength: float = 0.7,
) -> np.ndarray:
    orig_f = original.astype(np.float32) / 255.0
    tex_f = texture.astype(np.float32) / 255.0

    lighting_map = get_lighting_map(original)

    # Normalize to the masked region's OWN average brightness before using
    # it as a shading multiplier. Unnormalized, the same product renders
    # inconsistently across hotspots — e.g. a bright, sunlit original spot
    # keeps the new texture true-to-color while a dim/shadowed or warm-toned
    # original spot darkens or discolors it, even though it's the identical
    # product. Dividing by the mask's local mean keeps relative variation
    # (folds, wrinkles, local shadow) while removing that absolute bias.
    mask_bool = mask_gray > 10
    local_mean = float(lighting_map[mask_bool].mean()) if np.any(mask_bool) else float(lighting_map.mean())
    normalized_lighting = np.clip(lighting_map / max(local_mean, 0.05), 0.4, 1.6)
    lighting_3ch = cv2.merge([normalized_lighting, normalized_lighting, normalized_lighting])

    shaded_texture = tex_f * (lighting_3ch ** shadow_strength)

    mask_f = mask_gray.astype(np.float32) / 255.0
    mask_f = cv2.GaussianBlur(mask_f, (3, 3), 0)
    mask_3ch = cv2.merge([mask_f, mask_f, mask_f])

    result = (orig_f * (1.0 - mask_3ch)) + (shaded_texture * mask_3ch * opacity + orig_f * mask_3ch * (1 - opacity))
    return np.clip(result * 255, 0, 255).astype(np.uint8)


def apply_pattern(
    base_image: np.ndarray,
    mask: np.ndarray,
    texture_image: np.ndarray,
    settings: dict,
    product_width_cm: float | None,
    is_panel: bool = False,
    panel_quad: list | None = None,
) -> tuple[np.ndarray, int]:
    """
    Port of `utils/curtain.py::apply_pattern`.

    `settings` keys read (same names as the original call site in
    `process_single_layer`):
      - "repeat" (int, default 12)
      - "shading" (float, default 0.6) -> shading_strength
      - "curtainWidthCm" (float|None) -> curtain_real_width, only used
        when repeat == 0 (per process_single_layer's own logic, which
        lives one layer up and decides curtain_real_width; this port
        keeps the same decision inline here for self-containment)

    `product_width_cm` corresponds to the original's `pattern_real_width`
    parameter (parsed from the product's `width` field upstream via
    `parse_width_to_cm`).

    `is_panel`/`panel_quad`: when a "panel" product (is_panel_product) is
    applied to a hotspot curtain_geometry.plan_panel_quads already found a
    perspective quad for (panel_quad, normalized 0..1, TL/TR/BR/BL), the
    design is warped into that real quad instead of tiled flat — see
    warp_panel_texture. Only the texture-building step below differs; the
    fold displacement and lighting blend after it are identical either way.

    Returns (final_img, calculated_repeat) exactly like the original.
    """
    room_img = base_image
    curtain_tex = texture_image
    mask_img = mask

    # settings.get(key, default) doesn't actually default anything here -
    # HotspotSettings.model_dump() always includes these keys, set to None
    # when unconfigured, and .get()'s default only applies to a MISSING
    # key - so int(None)/float(None) was throwing (silently swallowed
    # upstream, returning the room untouched) whenever the admin left
    # repeat/shading unset.
    repeat_raw = settings.get("repeat")
    repeat = int(repeat_raw) if repeat_raw is not None else 12
    shading_raw = settings.get("shading")
    shading_strength = float(shading_raw) if shading_raw is not None else 0.6

    if repeat == 0:
        raw_curtain_width = settings.get("curtainWidthCm")
        if raw_curtain_width:
            curtain_real_width = float(raw_curtain_width)
        else:
            curtain_real_width = 500.0
    else:
        curtain_real_width = None

    pattern_real_width = product_width_cm

    H, W = room_img.shape[:2]

    if len(mask_img.shape) == 3:
        mask_gray = cv2.cvtColor(mask_img, cv2.COLOR_BGR2GRAY)
    else:
        mask_gray = mask_img

    # INTER_NEAREST here produced a visibly jagged, stair-stepped mask
    # boundary once upscaled to full room-photo resolution (the source SAM
    # mask is much lower-res) — LINEAR gives the edge a proper anti-aliased
    # ramp, which both looks smoother and closes off the thin slivers of the
    # original curtain that used to peek through along a blocky edge.
    mask_gray = cv2.resize(mask_gray, (W, H), interpolation=cv2.INTER_LINEAR)
    mask_gray = fill_enclosed_holes(mask_gray)

    try:
        x, y, mask_w, mask_h = cv2.boundingRect(mask_gray)
        if mask_w == 0 or mask_h == 0:
            x, y, mask_w, mask_h = 0, 0, W, H

        aspect_ratio = W / float(H)

        if aspect_ratio < 1.2:
            standard_curtain_px = W * 0.55
        else:
            standard_curtain_px = W * 0.35

        if is_panel and panel_quad is not None:
            quad_px = np.asarray(panel_quad, dtype=np.float32).reshape(4, 2) * np.array([W, H], dtype=np.float32)
            tiled_clean = warp_panel_texture(curtain_tex, quad_px, W, H)
            tiled_clean = fill_voids(tiled_clean, mask_gray)
            calculated_repeat = max(1, int(repeat))
        else:
            if pattern_real_width and curtain_real_width:
                repeats_on_curtain = float(curtain_real_width) / float(pattern_real_width)
                tile_size = standard_curtain_px / max(1.0, repeats_on_curtain)

                calculated_repeat = max(1, int(round(repeats_on_curtain)))
            else:
                calculated_repeat = max(1, int(repeat))
                tile_size = mask_w / calculated_repeat

            local_tiled = tile_texture(curtain_tex, mask_w, mask_h, tile_size)

            tiled_clean = np.zeros((H, W, 3), dtype=np.uint8)

            tiled_clean[y:y + mask_h, x:x + mask_w] = local_tiled

        fold_strength = 15 * (2.0 / 1.5)

        gray = cv2.cvtColor(room_img, cv2.COLOR_BGR2GRAY)
        gray_masked = cv2.bitwise_and(gray, gray, mask=mask_gray)
        gray_blur = cv2.GaussianBlur(gray_masked, (31, 101), 0)

        disp_map = (gray_blur.astype(np.float32) - 127.5) / 127.5

        map_x, map_y = np.meshgrid(np.arange(W), np.arange(H))
        map_x = map_x.astype(np.float32) + (disp_map * fold_strength)
        map_y = map_y.astype(np.float32)

        displaced_tex = cv2.remap(tiled_clean, map_x, map_y, interpolation=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)

        final_img = blend_realism(room_img, displaced_tex, mask_gray, shadow_strength=shading_strength)

        return final_img, calculated_repeat

    except Exception:
        return room_img, max(1, int(repeat))

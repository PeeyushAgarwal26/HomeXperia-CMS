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

    Returns (final_img, calculated_repeat) exactly like the original.
    """
    room_img = base_image
    curtain_tex = texture_image
    mask_img = mask

    repeat = int(settings.get("repeat", 12))
    shading_strength = float(settings.get("shading", 0.6))

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

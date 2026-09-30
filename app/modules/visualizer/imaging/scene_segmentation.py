"""Full-scene room segmentation: given a room photo, detect every target
surface (wall/floor/curtain/rug/window/door) and cut a precise, occlusion-
aware mask for each.

Port of the Flask client-backend's `utils/segmentation.py` (post-model-load
logic) + `utils/mask_geometry.py` (imported here as `mask_geometry`, ported
separately). This is what used to be proxied to `api.homexperia.com/api/upload`
(see `external_clients.proxy_upload`/`proxy_upload_bytes`, which now call
`process_scene` below instead) — this module is the real thing, not a
placeholder.

Three models, strict ownership, never overlapping on one object:
- OneFormer (panoptic segmentation) — shared with imaging/depth.py's
  reference-object detection via `depth.get_oneformer()`; loaded once no
  matter which caller asks first.
- BiRefNet-lite — fine-structure occluders (plants, lamps, thin objects).
- SAM-HQ ViT-B — solid occluders (furniture) + per-surface refinement.

Pipeline shape per hotspot (surface -> heal -> edge-align -> cut -> validate
-> straighten -> rasterise) and every tuning constant below are ported
verbatim from the reference — each is justified there against a specific
measured failure on a real room; this file does not re-derive them.

Deliberate adaptations from the Flask original (both load-bearing, not
cosmetic):
- Pure computation: takes an already-decoded BGR image, returns in-memory
  PNG bytes per mask (plus the debug colour map) rather than writing to a
  Flask static folder. Persistence (storage URLs, room ids) is the caller's
  job — see external_clients.py — matching wall_depth.py/rug_depth.py's own
  image-in/structured-result-out convention.
- SAM-HQ's `SamPredictor` holds mutable per-image state between `set_image`
  and `predict` calls. The reference's Flask deployment never runs two
  requests through the same worker process concurrently; ours does (FastAPI
  + `anyio.to_thread.run_sync`), so a SHARED predictor would race two
  concurrent uploads' image embeddings against each other. Only the
  underlying model weights (`_sam_hq_model`) are a shared singleton; every
  call to `process_scene` wraps them in its own fresh, request-local
  `SamPredictor`.
- The final mask resize always targets the true original photo resolution,
  not conditionally (the reference only resizes back to original when a
  pre-segmentation downscale happened, otherwise leaving the mask at
  `rasterise_at_render_res`'s own ~4500px render canvas) — our own
  consumers expect every mask to align pixel-for-pixel with the original
  upload it was cut from, not a fixed render-canvas convention a specific
  downstream compositor assumed.
"""

from __future__ import annotations

import io
import uuid

import cv2
import numpy as np
from PIL import Image as PILImage

from app.core.config import settings
from app.modules.visualizer.imaging import depth as depth_module
from app.modules.visualizer.imaging import mask_geometry

# ---- surface / occluder taxonomy (verbatim) ----

TARGET_OBJECTS = {
    "wall": ["wall"],
    "floor": ["floor", "flooring"],
    "curtain": ["curtain", "blind", "drape"],
    "rug": ["rug", "carpet"],
    "window": ["window"],
    "door": ["door"],
}

TYPE_MAPPING = {
    "curtain": "window",
    "floor": "floor",
    "rug": "floor",
    "wall": "wall",
    "window": "window",
    "door": "door",
}

# Objects that commonly OCCLUDE surfaces. Segmented precisely and SUBTRACTED
# from surface masks, so an object yields a tight silhouette cut instead of a
# large rectangular bite.
OCCLUDER_OBJECTS = {
    "plant", "flora", "tree", "flower", "palm", "pot", "flowerpot", "vase",
    "lamp", "light", "floor lamp", "table lamp", "chandelier", "pendant", "pendent", "sconce",
    "fan", "sculpture", "ceiling fan",
    "wardrobe", "cabinet", "closet", "cupboard", "chest", "chest of drawers",
    "bookcase", "bookshelf", "shelf", "shelving",
    "refrigerator", "fridge", "washing machine",
    "sofa", "couch", "armchair", "chair", "bench",
    "table", "desk", "counter", "countertop",
    "bed", "headboard",
    "television", "tv", "monitor", "screen",
    "door", "sliding door",
    "radiator", "air conditioner", "ac unit",
}

# STRICT MODEL OWNERSHIP. Every occluder is handled by exactly one model,
# never both. FINE (genuinely fine structure) is owned by BiRefNet, whole
# object. Everything else in OCCLUDER_OBJECTS is SOLID and owned by
# OneFormer + a constrained SAM-HQ refinement — BiRefNet is a salient-object
# model whose failure mode is "nothing distinctly salient, return
# everything", exactly what a sofa filling most of a crop triggers.
FINE_OCCLUDER_LABELS = {
    "plant", "flora", "tree", "flower", "palm", "branch", "vine", "leaf", "leaves",
    "pot", "flowerpot", "vase", "sculpture", "statue", "figurine",
    "lamp", "light", "chandelier", "pendant", "pendent", "sconce", "fan",
    "candle", "candlestick", "tripod", "stand",
}

# SAM-HQ may sharpen or extend these surfaces' edges but may never carve them
# back: the result is OR-ed with OneFormer's own extent. These are large
# "stuff" surfaces whose extent OneFormer already gets right.
ONEFORMER_EXTENT_CLASSES = {"wall", "floor", "curtain", "rug"}

# Surfaces from which precise occluder silhouettes are subtracted.
OCCLUDER_SUBTRACT_CLASSES = {"curtain", "wall"}

# A surface the pipeline CUTS occluders out of may never be its own occluder
# (ADE20K hands one label, "blind, screen", to both a curtain's "blind" match
# and OCCLUDER_OBJECTS's "screen" match — refuse only that self-occlusion).
SELF_CUT_CLASSES = OCCLUDER_SUBTRACT_CLASSES & set(TARGET_OBJECTS)

# Occluder segments are admitted on an ABSOLUTE pixel floor, not a fraction
# of the image — a fraction scales the wrong way across upload resolutions.
OCCLUDER_MIN_PX = 100
SMALL_OBJECT_MIN_AREA = 0.005  # hotspot small-object filter (0.5% of the image)

# BiRefNet's matte is thresholded to binary HERE and nowhere else: soft alpha
# is produced exactly once, at the very end (rasterise_at_render_res).
BIREFNET_CUT_LEVEL = 115
BIREFNET_MODEL_ID = "ZhengPeng7/BiRefNet_lite"
BIREFNET_INPUT_SIZE = 512  # do NOT raise: OOMs under multi-worker deployment
# Contrast applied to BiRefNet's sigmoid before it is used as an alpha matte,
# so the soft band stays narrow (crisp silhouette, genuinely anti-aliased
# edge) instead of a mushy blob.
BIREFNET_MATTE_GAIN = 4.0

# What a void pocket must prove before any surface may claim it during heal:
# 1. OWNERSHIP — of the pocket's ring that belongs to a confidently-labelled
#    surface, at least this share must be THIS surface.
VOID_OWNERSHIP_MIN = 0.65
# 2. THINNESS — a halo is a shell around an object; furniture is solid. As a
#    fraction of the long side.
VOID_MAX_INRADIUS_FRAC = 0.015
# 3. SIZE FLOOR — below this it is segmentation seam speckle, not a halo.
VOID_MIN_POCKET_PX = 100

# Reject the heal if the final mask outgrew OneFormer's own surface by more
# than this — a backstop against catastrophic overreach, not a normal-growth
# policy.
MAX_HEAL_GROWTH_FRAC = 0.5

# Render canvas long side and the anti-aliased band width, in RENDER pixels.
RENDER_MAX_DIM = 4500
AA_RENDER_PX = 1.5

# Boundary straightening: classes eligible, and where straightening is
# permitted (a surface meeting these neighbours shares a genuinely straight
# architectural edge; meeting anything else it is bounded by that object's
# organic contour and must not be polygonised).
STRAIGHTEN_CLASSES = {"wall", "curtain"}
ARCHITECTURAL_NEIGHBOUR_LABELS = {
    "wall", "ceiling", "floor", "flooring", "window", "windowpane",
    "door", "doorframe", "column", "pillar", "stairs", "stairway", "staircase", "step",
}
STRAIGHTEN_REACH_FRAC = 0.015

# Classes that still get the guided-filter edge snap.
EDGE_REFINE_CLASSES = {"curtain", "floor", "rug", "window", "door"}

# Max enclosed-hole size to fill, as a fraction of the image area. Holes
# larger than this are real objects sitting on/in the surface and MUST stay
# cut out.
DEFAULT_HOLE_FILL_FRAC = 0.003
HOLE_FILL_FRAC = {
    "floor": 0.0015,
    "rug": 0.0015,
    "wall": 0.002,
    "curtain": 0.004,
    "window": 0.004,
}

# Pre-segmentation downscale ceiling — mirrors the reference's own MAX_SEG_DIM.
MAX_SEG_DIM = 1536

# Reuse depth.py's exact-token label matcher (identical logic to the
# reference's own label_matches/_label_tokens) rather than re-declaring it.
_label_matches = depth_module._label_matches

_sam_hq_model = None
_birefnet_model = None


def _load_sam_hq_if_needed() -> None:
    global _sam_hq_model
    if _sam_hq_model is not None:
        return
    import torch
    from segment_anything_hq import sam_model_registry

    device = depth_module.get_device()
    # sam_model_registry's checkpoint loader calls torch.load without
    # map_location; on a CPU-only machine loading a checkpoint saved under
    # CUDA raises unless this is forced. Same monkeypatch as the reference.
    orig_load = torch.load
    torch.load = lambda *a, **kw: orig_load(*a, **{**kw, "map_location": device})
    try:
        sam = sam_model_registry["vit_b"](checkpoint=settings.sam_hq_checkpoint_path)
    finally:
        torch.load = orig_load
    sam.to(device=device)
    _sam_hq_model = sam


def _load_birefnet_if_needed() -> None:
    global _birefnet_model
    if _birefnet_model is not None:
        return
    from transformers import AutoModelForImageSegmentation

    device = depth_module.get_device()
    _birefnet_model = AutoModelForImageSegmentation.from_pretrained(
        BIREFNET_MODEL_ID, trust_remote_code=True
    )
    _birefnet_model.eval().to(device)


def find_ade20k_id(label_name, id2label):
    """Substring match (deliberately looser than _label_matches' exact-token
    match — TARGET_OBJECTS entries like "flooring" are themselves substrings
    of longer ADE20K label strings)."""
    possible_names = TARGET_OBJECTS.get(label_name, [label_name])
    found_ids = []
    for id_key, model_label in id2label.items():
        try:
            curr_id = int(id_key)
        except ValueError:
            continue
        for key in possible_names:
            if key in model_label.lower():
                found_ids.append(curr_id)
    return found_ids


def get_label_from_id(id2label, valid_id):
    if valid_id in id2label:
        return id2label[valid_id]
    if str(valid_id) in id2label:
        return id2label[str(valid_id)]
    return f"Unknown ({valid_id})"


def generate_color_map(segmentation_map, found_objects):
    h, w = segmentation_map.shape
    color_map = np.zeros((h, w, 3), dtype=np.uint8)
    rng = np.random.RandomState(42)
    colors = rng.randint(50, 255, size=(300, 3))
    for obj in found_objects:
        obj_id = obj["id"]
        mask = segmentation_map == obj_id
        color_map[mask] = colors[obj_id % 300]
    return color_map


def fill_small_holes(mask_img, image_area, max_hole_frac=DEFAULT_HOLE_FILL_FRAC):
    """Fill enclosed holes ONLY if smaller than max_hole_frac of the image.
    Large enclosed holes are real objects sitting on/in the surface and must
    stay cut out."""
    _, binary = cv2.threshold(mask_img, 127, 255, cv2.THRESH_BINARY)
    padded = cv2.copyMakeBorder(binary, 1, 1, 1, 1, cv2.BORDER_CONSTANT, value=0)
    h, w = padded.shape[:2]
    flood_mask = np.zeros((h + 2, w + 2), np.uint8)
    flood = padded.copy()
    cv2.floodFill(flood, flood_mask, (0, 0), 255)
    flood = flood[1:h - 1, 1:w - 1]
    holes = cv2.bitwise_not(flood)

    num, labels, stats, _ = cv2.connectedComponentsWithStats((holes > 0).astype(np.uint8), connectivity=8)
    max_hole_area = max(1.0, max_hole_frac * float(image_area))
    fill = np.zeros_like(binary)
    for i in range(1, num):
        if stats[i, cv2.CC_STAT_AREA] <= max_hole_area:
            fill[labels == i] = 255
    return binary | fill


def keep_significant_components(mask_img, image_area, frac_image=0.0005, min_abs=200):
    """Keep the largest connected component plus any other component whose
    area is >= max(min_abs, frac_image * image_area)."""
    binary = (mask_img > 127).astype(np.uint8)
    num, labels, stats, _ = cv2.connectedComponentsWithStats(binary, connectivity=8)
    if num <= 1:
        return mask_img
    areas = stats[1:, cv2.CC_STAT_AREA]
    if len(areas) == 0:
        return np.zeros_like(mask_img)
    thresh = max(min_abs, frac_image * float(image_area))
    largest_label = int(np.argmax(areas)) + 1
    keep = labels == largest_label
    for i, a in enumerate(areas, start=1):
        if a >= thresh:
            keep |= labels == i
    # Copy the ORIGINAL values through rather than stamping 255 — this also
    # runs on masks carrying BiRefNet's soft alpha, and stamping would
    # flatten that matte back to a hard edge.
    return np.where(keep, mask_img, 0).astype(mask_img.dtype)


def _guided_filter(I, p, radius, eps):
    ksize = (2 * radius + 1, 2 * radius + 1)
    mean_I = cv2.boxFilter(I, cv2.CV_32F, ksize)
    mean_p = cv2.boxFilter(p, cv2.CV_32F, ksize)
    mean_Ip = cv2.boxFilter(I * p, cv2.CV_32F, ksize)
    cov_Ip = mean_Ip - mean_I * mean_p
    mean_II = cv2.boxFilter(I * I, cv2.CV_32F, ksize)
    var_I = mean_II - mean_I * mean_I
    a = cov_Ip / (var_I + eps)
    b = mean_p - a * mean_I
    mean_a = cv2.boxFilter(a, cv2.CV_32F, ksize)
    mean_b = cv2.boxFilter(b, cv2.CV_32F, ksize)
    return mean_a * I + mean_b


def refine_mask_edges(mask_img, image_bgr, radius_frac=0.004, eps=1e-3):
    """Snap mask boundaries onto true image edges via guided-filter matting,
    then re-threshold to binary."""
    h, w = mask_img.shape[:2]
    radius = max(3, int(radius_frac * max(h, w)))
    guide = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255.0
    src = mask_img.astype(np.float32) / 255.0
    q = _guided_filter(guide, src, radius, eps)
    return (q >= 0.5).astype(np.uint8) * 255


def sample_positive_points(of_bool, bbox, max_points=8):
    """Distance-transform peak + a spatial grid of interior points, so SAM-HQ
    is guided to cover the WHOLE region instead of one local blob."""
    of_uint8 = of_bool.astype(np.uint8) * 255
    pts = []
    dist = cv2.distanceTransform(of_uint8, cv2.DIST_L2, 5)
    _, _, _, max_loc = cv2.minMaxLoc(dist)
    pts.append([int(max_loc[0]), int(max_loc[1])])

    x0, y0, x1, y1 = bbox
    gx = gy = 3
    for iy in range(gy):
        for ix in range(gx):
            cx0 = x0 + (x1 - x0) * ix // gx
            cx1 = x0 + (x1 - x0) * (ix + 1) // gx
            cy0 = y0 + (y1 - y0) * iy // gy
            cy1 = y0 + (y1 - y0) * (iy + 1) // gy
            if cx1 <= cx0 or cy1 <= cy0:
                continue
            cell = of_bool[cy0:cy1, cx0:cx1]
            if int(cell.sum()) < 50:
                continue
            ys, xs = np.where(cell)
            mid = len(xs) // 2
            pts.append([int(cx0 + xs[mid]), int(cy0 + ys[mid])])

    uniq, seen = [], set()
    for px, py in pts:
        if (px, py) not in seen:
            seen.add((px, py))
            uniq.append([px, py])
    return uniq[:max_points]


def mask_to_sam_logits(of_bool, size=256, val=8.0):
    """Encode a binary mask as SAM low-res mask_input logits (fg=+val, bg=-val)."""
    small = cv2.resize(of_bool.astype(np.float32), (size, size), interpolation=cv2.INTER_LINEAR)
    logits = (small * 2.0 - 1.0) * val
    return logits[None, :, :].astype(np.float32)


def _sam_predict_safe(predictor, points, labels, box, mask_input):
    """Call SAM-HQ with graceful degradation if a kwarg combination is rejected."""
    pc = np.array(points) if points else None
    pl = np.array(labels) if labels else None
    try:
        return predictor.predict(point_coords=pc, point_labels=pl, box=box,
                                  mask_input=mask_input, multimask_output=True, hq_token_only=True)
    except Exception:
        try:
            return predictor.predict(point_coords=pc, point_labels=pl, box=box,
                                      multimask_output=True, hq_token_only=True)
        except Exception:
            return predictor.predict(box=box, multimask_output=True, hq_token_only=True)


def _best_iou_index(masks, of_bool):
    best_idx, best_iou = 0, -1.0
    for i, m in enumerate(masks):
        inter = np.logical_and(m, of_bool).sum()
        union = np.logical_or(m, of_bool).sum()
        iou = inter / union if union > 0 else 0.0
        if iou > best_iou:
            best_iou, best_idx = iou, i
    return best_idx


def refine_with_sam(predictor, of_bool, bbox, neg_points, image_shape, shrink_guard=0.7):
    """SAM-HQ boundary refinement seeded by OneFormer. Constrained to a
    dilated OneFormer region so it cannot bleed into neighbours, and falls
    back to OneFormer if SAM-HQ collapses (shrink guard)."""
    H, W = image_shape
    of_area = int(of_bool.sum())
    if of_area == 0:
        return of_bool.astype(np.uint8) * 255

    pos_points = sample_positive_points(of_bool, bbox, max_points=8)
    if not pos_points:
        return of_bool.astype(np.uint8) * 255

    points = pos_points + list(neg_points)
    labels = [1] * len(pos_points) + [0] * len(neg_points)

    pad = int(0.02 * max(H, W))
    box = np.array([
        max(0, bbox[0] - pad), max(0, bbox[1] - pad),
        min(W - 1, bbox[2] + pad), min(H - 1, bbox[3] + pad),
    ])

    try:
        masks, _, _ = _sam_predict_safe(predictor, points, labels, box, mask_to_sam_logits(of_bool))
    except Exception:
        return of_bool.astype(np.uint8) * 255

    sam_bool = masks[_best_iou_index(masks, of_bool)].astype(bool)

    k = max(3, int(0.02 * max(H, W)))
    of_dilated = cv2.dilate(of_bool.astype(np.uint8) * 255, np.ones((k, k), np.uint8)) > 127
    constrained = np.logical_and(sam_bool, of_dilated)

    refined = of_bool if int(constrained.sum()) < shrink_guard * of_area else constrained
    return refined.astype(np.uint8) * 255


def birefnet_fg_mask(image_pil, out_hw):
    """Run BiRefNet on a PIL crop; return a SOFT uint8 alpha matte resized to
    out_hw. Kept as a matte rather than thresholded at 0.5 — BiRefNet
    predicts a genuinely sub-pixel silhouette, and thresholding early throws
    that away."""
    import torch
    import torchvision.transforms.functional as TF

    device = depth_module.get_device()
    s = BIREFNET_INPUT_SIZE
    img = image_pil.convert("RGB").resize((s, s))
    t = torch.tensor(np.array(img)).float().permute(2, 0, 1) / 255.0
    t = TF.normalize(t, [0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
    t = t.unsqueeze(0).to(device)
    with torch.no_grad():
        preds = _birefnet_model(t)
    pred = preds[-1].sigmoid().cpu().squeeze().numpy()
    alpha = np.clip((pred - 0.5) * BIREFNET_MATTE_GAIN + 0.5, 0.0, 1.0)
    soft = (alpha * 255.0 + 0.5).astype(np.uint8)
    return cv2.resize(soft, (out_hw[1], out_hw[0]), interpolation=cv2.INTER_LINEAR)


def birefnet_detect_object(image_pil, raw_component_mask, obj_bbox, known_area, width, height):
    """BiRefNet foreground detection for one object, with expand-and-retry.

    A labelled object can be much smaller than the real visual occluder it
    belongs to, so a too-tight first crop truncates it — but a tiny confident
    nub can be non-empty without touching the crop border, so "done" requires
    covering a meaningful share of what is already known to be labelled
    there, not just ">0 px".

    Returns (cx1, cy1, cx2, cy2, fg_crop) in image coordinates.
    """
    ox1, oy1, ox2, oy2 = obj_bbox
    best_fg_crop, best_box, best_area = None, None, -1
    min_good_area = max(50, int(0.4 * known_area))
    pad_frac = 0.15
    first_box = None
    for _ in range(4):
        pad = max(10, int(pad_frac * max(ox2 - ox1, oy2 - oy1)))
        cx1 = max(0, ox1 - pad)
        cy1 = max(0, oy1 - pad)
        cx2 = min(width, ox2 + pad)
        cy2 = min(height, oy2 + pad)
        if first_box is None:
            first_box = (cx1, cy1, cx2, cy2)
        fg_crop = birefnet_fg_mask(image_pil.crop((cx1, cy1, cx2, cy2)), (cy2 - cy1, cx2 - cx1))
        fg_bin = fg_crop > 127
        area = int(fg_bin.sum())
        crop_pixels = (cy2 - cy1) * (cx2 - cx1)
        degenerate = area > 0.85 * crop_pixels
        if area > best_area and not degenerate:
            best_fg_crop, best_box, best_area = fg_crop, (cx1, cy1, cx2, cy2), area
        touches_edge = area > 0 and (
            fg_bin[0, :].any() or fg_bin[-1, :].any() or fg_bin[:, 0].any() or fg_bin[:, -1].any()
        )
        full_frame = cx1 == 0 and cy1 == 0 and cx2 == width and cy2 == height
        if not degenerate and ((area >= min_good_area and not touches_edge) or full_frame):
            break
        pad_frac *= 2.2

    if best_box is None:
        cx1, cy1, cx2, cy2 = first_box
        return cx1, cy1, cx2, cy2, np.zeros((cy2 - cy1, cx2 - cx1), np.uint8)

    cx1, cy1, cx2, cy2 = best_box
    area_ratio = best_area / max(1, known_area)
    fys, fxs = np.where(best_fg_crop > 127)
    known_h, known_w = max(1, oy2 - oy1), max(1, ox2 - ox1)
    if len(fys) == 0:
        extent_frac = 0.0
    else:
        extent_frac = min((fys.max() - fys.min()) / known_h, (fxs.max() - fxs.min()) / known_w)
    if area_ratio < 0.2 or extent_frac < 0.5:
        best_fg_crop = raw_component_mask[cy1:cy2, cx1:cx2].copy()
    return cx1, cy1, cx2, cy2, best_fg_crop


def build_unified_occluder_mask(sam_predictor, occluder_segments, segmentation_map, image_pil, id2label):
    """ONE binary occluder mask for the whole image, strict model ownership:
    BiRefNet owns fine occluders whole-object, SAM-HQ owns solid ones — never
    both on the same object. Returns (union_uint8_or_None, stats)."""
    H, W = segmentation_map.shape[:2]
    if not occluder_segments:
        return None, {}

    fine, solid = [], []
    for occ in occluder_segments:
        lbl = get_label_from_id(id2label, occ["label_id"])
        (fine if _label_matches(lbl, FINE_OCCLUDER_LABELS) else solid).append(occ)

    union = np.zeros((H, W), dtype=np.uint8)
    st = {"fine_objects": 0, "fine_fallback": 0, "solid_objects": 0,
          "fine_segments": len(fine), "solid_segments": len(solid)}

    if fine:
        _load_birefnet_if_needed()
    for occ in fine:
        seg_bool = segmentation_map == occ["segment_id"]
        if int(seg_bool.sum()) == 0:
            continue
        # Split by connected component: the panoptic model merges instances
        # of one class under a single id.
        num_cc, labels_cc = cv2.connectedComponents(seg_bool.astype(np.uint8))
        for cc in range(1, num_cc):
            comp = labels_cc == cc
            area = int(comp.sum())
            if area < OCCLUDER_MIN_PX:
                continue
            ys, xs = np.where(comp)
            obj_bbox = (int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max()))
            raw = comp.astype(np.uint8) * 255
            try:
                cx1, cy1, cx2, cy2, fg = birefnet_detect_object(image_pil, raw, obj_bbox, area, W, H)
            except Exception:
                union = np.maximum(union, raw)
                st["fine_fallback"] += 1
                continue
            cut = (fg >= BIREFNET_CUT_LEVEL).astype(np.uint8) * 255
            union[cy1:cy2, cx1:cx2] = np.maximum(union[cy1:cy2, cx1:cx2], cut)
            st["fine_objects"] += 1

    for occ in solid:
        of_bool = segmentation_map == occ["segment_id"]
        if int(of_bool.sum()) == 0:
            continue
        bbox = occ["bbox"]
        pad = int(0.01 * max(H, W))
        box = np.array([
            max(0, bbox[0] - pad), max(0, bbox[1] - pad),
            min(W - 1, bbox[2] + pad), min(H - 1, bbox[3] + pad),
        ])
        pos_points = sample_positive_points(of_bool, bbox, max_points=4)
        try:
            masks, _, _ = _sam_predict_safe(sam_predictor, pos_points, [1] * len(pos_points),
                                             box, mask_to_sam_logits(of_bool))
            sam_bool = masks[_best_iou_index(masks, of_bool)].astype(bool)
            k = max(3, int(0.015 * max(H, W)))
            of_dilated = cv2.dilate(of_bool.astype(np.uint8) * 255, np.ones((k, k), np.uint8)) > 127
            constrained = np.logical_and(sam_bool, of_dilated)
            refined = (np.logical_or(constrained, of_bool)
                       if int(constrained.sum()) < 0.5 * int(of_bool.sum()) else constrained)
        except Exception:
            refined = of_bool
        union = np.maximum(union, refined.astype(np.uint8) * 255)
        st["solid_objects"] += 1

    return (union if union.any() else None), st


def find_enclosed_holes(mask_img):
    """Fully-enclosed interior holes of mask_img — pixels that are 0 but
    unreachable from the image border without crossing a 255 pixel."""
    _, binary_mask = cv2.threshold(mask_img, 127, 255, cv2.THRESH_BINARY)
    padded = cv2.copyMakeBorder(binary_mask, 1, 1, 1, 1, cv2.BORDER_CONSTANT, value=0)
    h, w = padded.shape[:2]
    flood_mask = np.zeros((h + 2, w + 2), np.uint8)
    flood = padded.copy()
    cv2.floodFill(flood, flood_mask, (0, 0), 255)
    flood = flood[1:h - 1, 1:w - 1]
    return cv2.bitwise_not(flood)


def occluders_in_front_of(occluder_union, surface_uint8, labelled_bool=None, ring_frac=0.012, share=0.25):
    """The occluder components that actually sit IN FRONT OF this surface —
    measured by what SURROUNDS the object (a quarter of confidently-labelled
    ring pixels being this surface), since plain overlap is zero by
    construction (the occluder's own label already excluded it) and plain
    proximity is meaningless for a surface spanning most of the photo."""
    if occluder_union is None:
        return np.zeros_like(surface_uint8)
    h, w = surface_uint8.shape[:2]
    r = max(3, int(ring_frac * max(h, w)))
    ker = np.ones((2 * r + 1, 2 * r + 1), np.uint8)
    surf = surface_uint8 > 127
    known = labelled_bool if labelled_bool is not None else np.ones((h, w), bool)
    out = np.zeros_like(surface_uint8)
    num, labels = cv2.connectedComponents((occluder_union > 127).astype(np.uint8))
    for i in range(1, num):
        comp = labels == i
        ring = cv2.dilate(comp.astype(np.uint8), ker).astype(bool) & ~comp
        n_conf = int((ring & known).sum())
        if n_conf and int((ring & surf).sum()) / float(n_conf) >= share:
            out[comp] = 255
    return out


def heal_surface(surface_uint8, occ_front_uint8, structural_uint8, segmentation_map,
                  occluder_seg_ids, image_area, ownership_min=VOID_OWNERSHIP_MIN,
                  max_inradius_frac=VOID_MAX_INRADIUS_FRAC, min_pocket_px=VOID_MIN_POCKET_PX):
    """FILL ONCE: complete interior fill of the surface, protecting real
    openings. A pocket must clear three gates — big enough to be a halo,
    OWNED by this surface rather than contested, and THIN enough to be a
    shell rather than a solid object — before it may be claimed."""
    barrier = np.maximum(np.maximum(surface_uint8, occ_front_uint8), structural_uint8)
    holes = find_enclosed_holes(barrier)
    out = np.maximum(surface_uint8, occ_front_uint8)
    st = {"filled": 0, "speck": 0, "contested": 0, "too_thick": 0, "unrecognised": 0}
    if not holes.any():
        return out, st
    holes_bin = (holes > 0).astype(np.uint8)
    num, labels, cc_stats, _ = cv2.connectedComponentsWithStats(holes_bin, connectivity=8)
    dt = cv2.distanceTransform(holes_bin, cv2.DIST_L2, 5)
    h, w = surface_uint8.shape[:2]
    max_inradius = max(4.0, max_inradius_frac * float(max(h, w)))
    surf_bool = surface_uint8 > 127
    rival_bool = structural_uint8 > 127
    k3 = np.ones((3, 3), np.uint8)
    for i in range(1, num):
        area = int(cc_stats[i, cv2.CC_STAT_AREA])
        if area < min_pocket_px:
            st["speck"] += 1
            continue
        x0 = max(0, int(cc_stats[i, cv2.CC_STAT_LEFT]) - 2)
        y0 = max(0, int(cc_stats[i, cv2.CC_STAT_TOP]) - 2)
        x1 = min(w, x0 + int(cc_stats[i, cv2.CC_STAT_WIDTH]) + 4)
        y1 = min(h, y0 + int(cc_stats[i, cv2.CC_STAT_HEIGHT]) + 4)
        sub = labels[y0:y1, x0:x1] == i

        if float(dt[y0:y1, x0:x1][sub].max()) > max_inradius:
            st["too_thick"] += 1
            continue

        ring = cv2.dilate(sub.astype(np.uint8), k3).astype(bool) & ~sub
        own = int((ring & surf_bool[y0:y1, x0:x1]).sum())
        rival = int((ring & rival_bool[y0:y1, x0:x1]).sum())
        if own + rival == 0 or own / float(own + rival) < ownership_min:
            st["contested"] += 1
            continue

        vals, counts = np.unique(segmentation_map[y0:y1, x0:x1][sub], return_counts=True)
        dominant = int(vals[int(np.argmax(counts))])
        if dominant != 0 and dominant not in occluder_seg_ids:
            st["unrecognised"] += 1
            continue

        out[y0:y1, x0:x1][sub] = 255
        st["filled"] += 1
    return out, st


def refine_boundary_scoped(mask_uint8, image_bgr, occluder_union, guard_frac=0.004):
    """Guided-filter edge snap, restricted away from occluder silhouettes (a
    guided filter follows colour contrast only, and would re-thicken a cut
    edge back past the object it was cut around)."""
    refined = refine_mask_edges(mask_uint8, image_bgr)
    if occluder_union is None:
        return refined
    k = max(3, int(guard_frac * max(mask_uint8.shape[:2])))
    near = cv2.dilate(occluder_union, np.ones((k, k), np.uint8)) > 0
    return np.where(near, mask_uint8, refined).astype(np.uint8)


def validate_heal(final_uint8, source_uint8, forbidden_bool, image_area,
                   max_growth_frac=MAX_HEAL_GROWTH_FRAC, forbid_tol_frac=0.002):
    """Sanity gate on the healed result. Returns (ok, reason). Rejects and
    falls back to the unhealed mask if it grew implausibly or claimed pixels
    another surface confidently owns."""
    src = int((source_uint8 > 127).sum())
    fin = int((final_uint8 > 127).sum())
    if src == 0:
        return True, "empty source"
    growth = (fin - src) / float(src)
    if growth > max_growth_frac:
        return False, f"grew {growth * 100:.0f}% over OneFormer (cap {max_growth_frac * 100:.0f}%)"
    bad = int(((final_uint8 > 127) & forbidden_bool).sum())
    if bad > forbid_tol_frac * float(image_area):
        return False, f"claimed {bad}px belonging to another surface"
    return True, f"grew {growth * 100:.0f}%"


def postprocess_mask(mask_uint8, image_bgr, image_area, do_edge_refine=True,
                      max_hole_frac=DEFAULT_HOLE_FILL_FRAC, do_prune=True):
    """Shared cleanup: bridge small gaps, keep significant components, fill
    only small enclosed holes, snap edges to the image."""
    h, w = mask_uint8.shape[:2]
    k = max(3, int(0.004 * max(h, w)))
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
    mask_uint8 = cv2.morphologyEx(mask_uint8, cv2.MORPH_CLOSE, kernel)
    if do_prune:
        mask_uint8 = keep_significant_components(mask_uint8, image_area)
    mask_uint8 = fill_small_holes(mask_uint8, image_area, max_hole_frac)
    if do_edge_refine:
        mask_uint8 = refine_mask_edges(mask_uint8, image_bgr)
    return mask_uint8


def build_straighten_zone(arch_all_uint8, own_bool, occluder_union, shape, reach_frac=STRAIGHTEN_REACH_FRAC):
    """Mark where this surface's boundary may be straightened: dilated
    architectural-neighbour territory (own pixels removed first, so "wall"
    dilating into itself doesn't permit straightening everywhere), minus any
    occluder, plus the frame border (a boundary running off-frame is
    straight by definition)."""
    H, W = shape[:2]
    arch = arch_all_uint8.copy()
    arch[own_bool] = 0
    r = max(5, int(reach_frac * max(H, W)))
    zone = cv2.dilate(arch, np.ones((2 * r + 1, 2 * r + 1), np.uint8))
    b = max(3, int(0.004 * max(H, W)))
    zone[:b, :] = 255
    zone[-b:, :] = 255
    zone[:, :b] = 255
    zone[:, -b:] = 255
    if occluder_union is not None:
        k = max(3, int(0.01 * max(H, W)))
        zone = cv2.bitwise_and(zone, cv2.bitwise_not(cv2.dilate(occluder_union, np.ones((k, k), np.uint8))))
    return zone


def render_canvas_size(w, h, target=RENDER_MAX_DIM):
    """The canvas the mask is rasterised onto (so a later nearest-resize onto
    the real photo is a mild adjustment, not a multi-x magnification)."""
    m = max(w, h)
    if 4000 <= m <= target:
        return w, h
    sc = float(target) / float(m)
    return max(1, int(w * sc)), max(1, int(h * sc))


def rasterise_at_render_res(mask_uint8, target=RENDER_MAX_DIM, aa_px=AA_RENDER_PX):
    """Resample the boundary as a signed distance FIELD, then rasterise at
    render resolution — fixes both the upscale staircase and the alternative
    (feathering in mask space, which only spreads the staircase into a
    banded gradient). Anti-aliasing is applied ONCE, here, ~1.5 render px —
    everything upstream of this is binary."""
    binary = (mask_uint8 > 127).astype(np.uint8)
    h, w = binary.shape[:2]
    rw, rh = render_canvas_size(w, h, target)
    if not binary.any() or binary.all():
        return cv2.resize(mask_uint8, (rw, rh), interpolation=cv2.INTER_NEAREST)
    d_in = cv2.distanceTransform(binary, cv2.DIST_L2, 5)
    d_out = cv2.distanceTransform(1 - binary, cv2.DIST_L2, 5)
    sdf = d_in - d_out
    sc = float(rw) / float(w)
    big = cv2.resize(sdf, (rw, rh), interpolation=cv2.INTER_CUBIC) * sc
    alpha = np.clip(0.5 + big / max(1e-6, float(aa_px)), 0.0, 1.0)
    return (alpha * 255.0 + 0.5).astype(np.uint8)


def _encode_png(mask_uint8: np.ndarray) -> bytes:
    ok, buf = cv2.imencode(".png", mask_uint8)
    if not ok:
        raise RuntimeError("Failed to encode mask as PNG")
    return buf.tobytes()


def process_scene(image_bgr: np.ndarray) -> dict:
    """Detect and cut every target surface in a room photo.

    Returns:
        {
            "hotspots": [{"image_hotspots_id", "type", "label", "x", "y",
                          "bbox", "segment_id", "mask_png_bytes"}, ...],
            "found_objects": [{"id": segment_id}, ...],
            "image_dims": {"width": int, "height": int},  # original resolution
            "map_png_bytes": bytes,  # debug colour-coded segment visualisation
        }
    """
    import torch
    from segment_anything_hq import SamPredictor

    depth_module._load_oneformer_if_needed()
    processor, segmenter = depth_module.get_oneformer()
    _load_sam_hq_if_needed()
    device = depth_module.get_device()

    orig_height, orig_width = image_bgr.shape[:2]
    image_pil = PILImage.fromarray(cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB))

    scale_factor = 1.0
    if max(orig_width, orig_height) > MAX_SEG_DIM:
        scale_factor = MAX_SEG_DIM / max(orig_width, orig_height)
        new_w, new_h = int(orig_width * scale_factor), int(orig_height * scale_factor)
        image_pil = image_pil.resize((new_w, new_h), PILImage.Resampling.LANCZOS)

    width, height = image_pil.size
    image_area = width * height

    inputs = processor(images=image_pil, task_inputs=["panoptic"], return_tensors="pt").to(device)
    with torch.no_grad():
        outputs = segmenter(**inputs)
    panoptic_result = processor.post_process_panoptic_segmentation(outputs, target_sizes=[image_pil.size[::-1]])[0]

    segmentation_map = panoptic_result["segmentation"].cpu().numpy()
    segments_info = panoptic_result["segments_info"]
    id2label = segmenter.config.id2label

    target_ids = {ul: set(find_ade20k_id(ul, id2label)) for ul in TARGET_OBJECTS}
    self_cut_label_ids = set()
    for cls in SELF_CUT_CLASSES:
        self_cut_label_ids |= target_ids.get(cls, set())

    found_objects = []
    hotspots = []
    occluder_segments = []

    for segment in segments_info:
        segment_id = segment["id"]
        label_id = segment["label_id"]
        model_label = get_label_from_id(id2label, label_id)

        seg_bool = segmentation_map == segment_id
        seg_count = int(seg_bool.sum())
        if seg_count == 0:
            continue
        seg_area_ratio = seg_count / float(image_area)

        if _label_matches(model_label, OCCLUDER_OBJECTS) and seg_count >= OCCLUDER_MIN_PX:
            if label_id not in self_cut_label_ids:
                rows_o, cols_o = np.where(seg_bool)
                occluder_segments.append({
                    "segment_id": segment_id,
                    "label_id": label_id,
                    "bbox": [int(np.min(cols_o)), int(np.min(rows_o)), int(np.max(cols_o)), int(np.max(rows_o))],
                    "label": model_label,
                })

        matched_user_label = next((ul for ul in TARGET_OBJECTS if label_id in target_ids[ul]), None)
        if not matched_user_label or seg_area_ratio < SMALL_OBJECT_MIN_AREA:
            continue

        rows, cols = np.where(seg_bool)
        y_min, y_max = int(np.min(rows)), int(np.max(rows))
        x_min, x_max = int(np.min(cols)), int(np.max(cols))
        bbox = [x_min, y_min, x_max, y_max]
        bbox_original = [int(c / scale_factor) for c in bbox] if scale_factor != 1.0 else bbox

        object_mask_uint8 = seg_bool.astype(np.uint8) * 255
        dist_transform = cv2.distanceTransform(object_mask_uint8, cv2.DIST_L2, 5)
        _, _, _, max_loc = cv2.minMaxLoc(dist_transform)
        cx, cy = max_loc
        perc_x = max(0.03, min(0.97, round(cx / width, 4)))
        perc_y = max(0.03, min(0.97, round(cy / height, 4)))

        found_objects.append({"id": segment_id})
        display_label = "Rugs" if matched_user_label == "rug" else matched_user_label.capitalize()
        hotspots.append({
            "image_hotspots_id": str(uuid.uuid4()),
            "type": TYPE_MAPPING.get(matched_user_label, "unknown"),
            "label": display_label,
            "x": perc_x,
            "y": perc_y,
            "bbox": bbox_original,
            "segment_id": segment_id,
            "mask_image": "",
            "_seg_class": matched_user_label,
        })

    color_map_np = generate_color_map(segmentation_map, found_objects)

    image_cv = cv2.cvtColor(np.array(image_pil), cv2.COLOR_RGB2BGR)
    sam_predictor = SamPredictor(_sam_hq_model)  # request-local: see module docstring
    sam_predictor.set_image(cv2.cvtColor(image_cv, cv2.COLOR_BGR2RGB))

    occluder_union, _ = build_unified_occluder_mask(
        sam_predictor, occluder_segments, segmentation_map, image_pil, id2label
    )

    arch_all = np.zeros((height, width), np.uint8)
    for seg in segments_info:
        if _label_matches(get_label_from_id(id2label, seg["label_id"]), ARCHITECTURAL_NEIGHBOUR_LABELS):
            arch_all[segmentation_map == seg["id"]] = 255

    occ_ids = {o["segment_id"] for o in occluder_segments}
    occ_labelled_bool = np.isin(segmentation_map, list(occ_ids)) if occ_ids else np.zeros(segmentation_map.shape, bool)

    for hotspot in hotspots:
        segment_id = hotspot["segment_id"]
        seg_class = hotspot["_seg_class"]
        bbox = hotspot["bbox"]
        of_bool = segmentation_map == segment_id
        of_uint8 = of_bool.astype(np.uint8) * 255

        current_area = (bbox[2] - bbox[0]) * (bbox[3] - bbox[1])
        neg_points = []
        for other in hotspots:
            if other["image_hotspots_id"] == hotspot["image_hotspots_id"]:
                continue
            ob = other["bbox"]
            ocx, ocy = int(other["x"] * width), int(other["y"] * height)
            oarea = (ob[2] - ob[0]) * (ob[3] - ob[1])
            if oarea < current_area and bbox[0] <= ocx <= bbox[2] and bbox[1] <= ocy <= bbox[3]:
                neg_points.append([ocx, ocy])

        structural_bool = (segmentation_map != 0) & (segmentation_map != segment_id) & ~occ_labelled_bool
        structural_uint8 = structural_bool.astype(np.uint8) * 255

        try:
            if seg_class == "wall":
                # Wall keeps raw OneFormer pixels — both SAM-HQ refinement and
                # the guided filter measurably degraded it upstream.
                surface = of_uint8
            else:
                refined = refine_with_sam(sam_predictor, of_bool, bbox, neg_points, (height, width))
                surface = cv2.bitwise_or(refined, of_uint8) if seg_class in ONEFORMER_EXTENT_CLASSES else refined

            do_cut = seg_class in OCCLUDER_SUBTRACT_CLASSES and occluder_union is not None
            max_hole_frac = 0.0 if do_cut else HOLE_FILL_FRAC.get(seg_class, DEFAULT_HOLE_FILL_FRAC)
            surface = postprocess_mask(surface, image_cv, image_area, max_hole_frac=max_hole_frac,
                                        do_edge_refine=False, do_prune=not do_cut)
            surface = cv2.bitwise_and(surface, cv2.bitwise_not(structural_uint8))

            if do_cut:
                occ_front = occluders_in_front_of(occluder_union, surface, labelled_bool=(segmentation_map != 0))
                healed, _ = heal_surface(surface, occ_front, structural_uint8, segmentation_map, occ_ids, image_area)
                healed = cv2.bitwise_and(healed, cv2.bitwise_not(structural_uint8))
            else:
                healed = surface

            if seg_class in EDGE_REFINE_CLASSES:
                healed = refine_boundary_scoped(healed, image_cv, occluder_union)
                healed = cv2.bitwise_and(healed, cv2.bitwise_not(structural_uint8))

            candidate = cv2.bitwise_and(healed, cv2.bitwise_not(occluder_union)) if do_cut else healed
            candidate = keep_significant_components(candidate, image_area)

            ok, _ = validate_heal(candidate, of_uint8, structural_bool, image_area)
            if ok:
                mask_uint8 = candidate
            else:
                fb = cv2.bitwise_and(of_uint8, cv2.bitwise_not(structural_uint8))
                if do_cut:
                    fb = cv2.bitwise_and(fb, cv2.bitwise_not(occluder_union))
                mask_uint8 = keep_significant_components(fb, image_area)
        except Exception:
            mask_uint8 = of_uint8

        if seg_class in STRAIGHTEN_CLASSES:
            try:
                zone = build_straighten_zone(arch_all, of_bool, occluder_union, mask_uint8.shape)
                mask_uint8 = mask_geometry.regularize_mask(mask_uint8, straighten_zone=zone)
            except Exception:
                pass

        mask_uint8 = rasterise_at_render_res(mask_uint8)
        # Always land on the true original resolution — see module docstring
        # ("Deliberate adaptations") for why this isn't conditional here.
        mask_uint8 = cv2.resize(mask_uint8, (orig_width, orig_height), interpolation=cv2.INTER_NEAREST)

        hotspot["mask_png_bytes"] = _encode_png(mask_uint8)
        del hotspot["mask_image"]
        del hotspot["_seg_class"]

    return {
        "hotspots": hotspots,
        "found_objects": found_objects,
        "image_dims": {"width": orig_width, "height": orig_height},
        "map_png_bytes": _encode_png(cv2.cvtColor(color_map_np, cv2.COLOR_RGB2BGR)),
    }

"""Metric depth estimation and reference-object detection.

Port of two pieces of the Flask client-backend's ``utils/segmentation.py``:

- ``get_metric_depth`` (``DEPTH_MODEL_ID``/``load_depth_model_if_needed``) —
  the model both the rug and wall-art pipelines use to ground real-world
  sizing and obstacle detection in actual geometry instead of a vision-LLM
  guess.
- ``detect_reference_objects`` (``load_oneformer_if_needed``) — panoptic
  segmentation used ONLY to find known-size objects (bed/door/chair) for the
  rug pipeline's reference-object depth-scale calibration (see
  imaging/rug_depth.py::reference_scale_factor). Split from the depth model
  on purpose, same as upstream: a caller that only needs metric depth (the
  wall-art path) never has to load this second, separate model.

Split into its own module here since our codebase has no single
"segmentation.py". Both models are loaded lazily, once, into module-level
globals and kept resident for the life of the process — loading either per-
request would dominate latency. Device selection is automatic (``cuda`` if
available, else ``cpu``) so this needs no code change to pick up a GPU
later; only the installed torch build (CPU vs CUDA wheel) differs between
environments.
"""

from __future__ import annotations

import re

import numpy as np

DEPTH_MODEL_ID = "depth-anything/Depth-Anything-V2-Metric-Indoor-Large-hf"
ONEFORMER_MODEL_ID = "shi-labs/oneformer_ade20k_swin_large"

# Real-world sizes for these live in imaging/rug_depth.py::REFERENCE_OBJECTS;
# this only maps those canonical names onto ADE20k label vocabulary. Matching
# is exact-token (see _label_matches), so "chair" also picks up "swivel
# chair"/"armchair" without substring accidents (e.g. "chairman").
REFERENCE_LABELS = {
    "bed": {"bed"},
    "chair": {"chair", "armchair"},
    "door": {"door"},
}
REFERENCE_MIN_AREA = 0.004  # ignore references under 0.4% of the frame

_depth_processor = None
_depth_model = None
_oneformer_processor = None
_oneformer_model = None
_device: str | None = None


def _get_device() -> str:
    global _device
    if _device is None:
        import torch

        _device = "cuda" if torch.cuda.is_available() else "cpu"
    return _device


def _load_depth_model_if_needed() -> None:
    global _depth_processor, _depth_model
    if _depth_model is not None:
        return
    from transformers import AutoImageProcessor, AutoModelForDepthEstimation

    device = _get_device()
    _depth_processor = AutoImageProcessor.from_pretrained(DEPTH_MODEL_ID)
    _depth_model = AutoModelForDepthEstimation.from_pretrained(DEPTH_MODEL_ID).to(device).eval()


def get_metric_depth(image_bgr: np.ndarray) -> np.ndarray:
    """Per-pixel METRIC depth map (HxW float32, metres) for a BGR image."""
    import cv2
    import torch
    import torch.nn.functional as F
    from PIL import Image as PILImage

    _load_depth_model_if_needed()
    device = _get_device()

    image_rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
    pil_image = PILImage.fromarray(image_rgb)
    inputs = _depth_processor(images=pil_image, return_tensors="pt").to(device)
    with torch.no_grad():
        predicted = _depth_model(**inputs).predicted_depth

    h, w = image_bgr.shape[:2]
    depth = F.interpolate(predicted.unsqueeze(1), size=(h, w), mode="bicubic", align_corners=False)[0, 0]
    return depth.cpu().numpy().astype(np.float32)


def _load_oneformer_if_needed() -> None:
    global _oneformer_processor, _oneformer_model
    if _oneformer_model is not None:
        return
    from transformers import OneFormerForUniversalSegmentation, OneFormerProcessor

    device = _get_device()
    _oneformer_processor = OneFormerProcessor.from_pretrained(ONEFORMER_MODEL_ID)
    _oneformer_model = OneFormerForUniversalSegmentation.from_pretrained(ONEFORMER_MODEL_ID).to(device)


def get_device() -> str:
    """Public accessor for the shared cuda/cpu device string (cached once)."""
    return _get_device()


def get_oneformer():
    """Public accessor for the shared OneFormer (processor, model) singleton.

    Both detect_reference_objects below (rug reference-object calibration)
    and scene_segmentation.py's full-scene panoptic pass share this one
    lazily-loaded instance — whichever runs first pays the load cost."""
    _load_oneformer_if_needed()
    return _oneformer_processor, _oneformer_model


def _label_tokens(label: str) -> set[str]:
    return {t for t in re.split(r"[^a-z]+", str(label).lower()) if t}


def _label_matches(model_label: str, keywords: set[str]) -> bool:
    return bool(_label_tokens(model_label) & keywords)


def detect_reference_objects(image_bgr: np.ndarray, max_dim: int = 1280, min_area_frac: float = REFERENCE_MIN_AREA):
    """Find known-size objects (bed/chair/door) for depth-scale calibration.

    Returns a list of {"label": canonical name, "mask": uint8 0/255 at the
    original image's resolution, "bbox": [x1,y1,x2,y2], "area_frac": float}.
    """
    import cv2
    import torch
    from PIL import Image as PILImage

    _load_oneformer_if_needed()
    device = _get_device()

    h0, w0 = image_bgr.shape[:2]
    scale = min(1.0, float(max_dim) / float(max(h0, w0)))
    if scale < 1.0:
        proc = cv2.resize(image_bgr, (max(1, int(w0 * scale)), max(1, int(h0 * scale))), interpolation=cv2.INTER_AREA)
    else:
        proc = image_bgr

    pil_image = PILImage.fromarray(cv2.cvtColor(proc, cv2.COLOR_BGR2RGB))
    inputs = _oneformer_processor(images=pil_image, task_inputs=["panoptic"], return_tensors="pt").to(device)
    with torch.no_grad():
        outputs = _oneformer_model(**inputs)
    result = _oneformer_processor.post_process_panoptic_segmentation(outputs, target_sizes=[pil_image.size[::-1]])[0]

    seg_map = result["segmentation"].cpu().numpy()
    id2label = _oneformer_model.config.id2label
    proc_area = float(seg_map.shape[0] * seg_map.shape[1])

    found = []
    for segment in result["segments_info"]:
        label_id = segment["label_id"]
        model_label = id2label.get(label_id, id2label.get(str(label_id), f"Unknown ({label_id})"))
        canonical = next((name for name, kw in REFERENCE_LABELS.items() if _label_matches(model_label, kw)), None)
        if canonical is None:
            continue

        seg_bool = seg_map == segment["id"]
        area_frac = float(seg_bool.sum()) / proc_area
        if area_frac < min_area_frac:
            continue

        rows, cols = np.where(seg_bool)
        mask = seg_bool.astype(np.uint8) * 255
        if scale < 1.0:
            mask = cv2.resize(mask, (w0, h0), interpolation=cv2.INTER_NEAREST)

        found.append(
            {
                "label": canonical,
                "mask": mask,
                "bbox": [int(cols.min() / scale), int(rows.min() / scale), int(cols.max() / scale), int(rows.max() / scale)],
                "area_frac": round(area_frac, 5),
            }
        )

    return found

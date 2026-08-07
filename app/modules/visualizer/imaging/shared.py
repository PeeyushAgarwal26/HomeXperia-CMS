"""
Shared image-processing helpers ported from the legacy Flask app
(`homexperia-client-backend/app.py`).

These are pure OpenCV/NumPy functions with no Flask or global-state
dependency. They are synchronous by design — callers (the async layer)
are expected to invoke them from a thread pool, not `await` them
directly.
"""

from __future__ import annotations

import base64
import hashlib
from pathlib import Path

import cv2
import httpx
import numpy as np

from app.common.storage import resolve_uploaded_file_path


def download_image(url: str, cache_dir: Path) -> np.ndarray:
    """
    Load an image from `url`. Root-relative URLs (no http(s) scheme) are
    read straight off local disk instead of round-tripping through HTTP —
    this is exactly the shape `LocalDiskStorage.save_bytes` returns for
    anything uploaded via our own admin, so those files are already sitting
    on disk; there's no server on the other end of an HTTP GET to a relative
    path anyway (see `resolve_uploaded_file_path` for why this isn't just
    `Path(url.lstrip("/"))`). Absolute http(s) URLs are downloaded and
    disk-cached under `cache_dir` keyed by md5(url).hexdigest(), mirroring
    the Flask app's `image_cache/` behavior (minus the in-process
    thundering-herd locks, which belong to the calling layer, not this pure
    helper).
    """
    if not url:
        return None

    if not url.startswith(("http://", "https://")):
        local_path = resolve_uploaded_file_path(url)
        if local_path is None or not local_path.exists():
            return None
        return cv2.imread(str(local_path), cv2.IMREAD_COLOR)

    cache_dir.mkdir(parents=True, exist_ok=True)
    url_hash = hashlib.md5(url.encode("utf-8")).hexdigest()
    cache_path = cache_dir / f"{url_hash}.jpg"

    if cache_path.exists():
        img = cv2.imread(str(cache_path), cv2.IMREAD_COLOR)
        if img is not None:
            return img
        cache_path.unlink()

    try:
        with httpx.Client(timeout=30) as client:
            resp = client.get(url)
            resp.raise_for_status()
            content = resp.content

        image_array = np.asarray(bytearray(content), dtype=np.uint8)
        img = cv2.imdecode(image_array, cv2.IMREAD_COLOR)
        if img is None:
            raise ValueError("Could not decode image")

        try:
            cv2.imwrite(str(cache_path), img)
        except Exception:
            pass

        return img
    except Exception:
        return None


def find_category(category: str) -> str:
    if "curtain" in category:
        return "curtain"
    if "floor" in category:
        return "floor"
    if "wall" in category:
        return "wall"
    if "rug" in category:
        return "rugs"
    return "curtain"


def preprocess_image(image: np.ndarray, debug_dir: Path | None, room_id: str) -> np.ndarray:
    """
    Denoise + sharpen. Same bilateral filter / unsharp-mask math as the
    Flask original. Debug JPEGs are only written if `debug_dir` is not
    None (the original hardcoded `DEBUG_IMAGES = True`; here the caller
    controls it explicitly).
    """
    if image is None:
        return None

    denoised = cv2.bilateralFilter(image, d=9, sigmaColor=75, sigmaSpace=75)
    gaussian_blur = cv2.GaussianBlur(denoised, (0, 0), 2.0)
    sharpened = cv2.addWeighted(denoised, 1.5, gaussian_blur, -0.5, 0)

    if debug_dir is not None:
        debug_dir.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(debug_dir / f"debug_sharpened_{room_id}.jpg"), sharpened)

    return sharpened


def upscale_image(image: np.ndarray, target_max_dim: int = 4000) -> np.ndarray:
    """
    Upscale so the largest dimension approaches ~4500px, matching the
    Flask original's real scale target (note: the *target* scale is
    always computed against 4500, independent of `target_max_dim`,
    which only gates whether upscaling happens at all — preserved
    verbatim from the original).
    """
    if image is None:
        return None

    h, w = image.shape[:2]
    current_max = max(h, w)

    if current_max >= target_max_dim:
        return image

    scale = 4500 / current_max
    new_w = int(w * scale)
    new_h = int(h * scale)

    upscaled = cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_LANCZOS4)
    return upscaled


def encode_for_sam(image: np.ndarray) -> tuple[str, bool, float]:
    """Downscales to SAM's max input dim (2040px) before base64-encoding —
    any coordinates sent alongside must be scaled by the same factor.
    Returns (image_b64, was_downscaled, scale)."""
    max_dim = 2040
    height, width = image.shape[0], image.shape[1]
    longest = max(height, width)
    if longest <= max_dim:
        _, buffer = cv2.imencode(".jpg", image)
        return base64.b64encode(buffer).decode(), False, 1.0
    scale = max_dim / longest
    resized = cv2.resize(image, (int(width * scale), int(height * scale)), interpolation=cv2.INTER_AREA)
    _, buffer = cv2.imencode(".jpg", resized)
    return base64.b64encode(buffer).decode(), True, scale


def b64_to_cv2(b64_str: str) -> np.ndarray:
    if b64_str and "," in b64_str:
        b64_str = b64_str.split(",")[1]
    image_bytes = base64.b64decode(b64_str)
    image_array = np.frombuffer(image_bytes, dtype=np.uint8)
    return cv2.imdecode(image_array, cv2.IMREAD_COLOR)


def get_lighting_map(img: np.ndarray, blur_k: int = 51) -> np.ndarray:
    """Shared lighting-map helper duplicated verbatim across floor.py,
    wall.py and old_rugs.py in the original (all with default blur_k=51,
    except curtain.py's variant which uses blur_k=3 and stays local to
    curtain.py since its signature/default differs)."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    if blur_k % 2 == 0:
        blur_k += 1
    gray = cv2.GaussianBlur(gray, (blur_k, blur_k), 0)
    return gray.astype(np.float32) / 255.0


def blend_hard_replace(
    original: np.ndarray,
    texture: np.ndarray,
    mask_gray: np.ndarray,
    shadow_strength: float = 0.15,
) -> np.ndarray:
    """
    Shared "hard replace" blend, duplicated (with varying default
    shadow_strength) across floor.py (0.15), wall.py (0.6) and
    old_rugs.py (0.1). Callers pass their own shadow_strength explicitly
    at each call site in the ported code, so the default here is a
    no-op fallback.
    """
    orig_f = original.astype(np.float32) / 255.0
    tex_f = texture.astype(np.float32) / 255.0

    lighting_map = get_lighting_map(original, blur_k=51)
    lighting_3ch = cv2.merge([lighting_map, lighting_map, lighting_map])

    shaded_texture = tex_f * (lighting_3ch ** shadow_strength)
    mask_f = mask_gray.astype(np.float32) / 255.0
    mask_f = cv2.GaussianBlur(mask_f, (3, 3), 0)
    mask_3ch = cv2.merge([mask_f, mask_f, mask_f])

    result = (orig_f * (1.0 - mask_3ch)) + (shaded_texture * mask_3ch)
    return np.clip(result * 255, 0, 255).astype(np.uint8)

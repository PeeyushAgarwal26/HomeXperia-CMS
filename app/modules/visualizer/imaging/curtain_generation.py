"""GenAI curtain-generation pipeline: fetch room/mask assets, pad them to
OpenAI's 1024x1024 edit-endpoint requirement, call the image-edit endpoint,
and crop the result back to the original aspect ratio.

Ported from the Flask client-backend's ``utils/curtain_generation.py``. The
only intentional behavior change is the OpenAI call itself: the destination
codebase is fully async, so this module takes an injected ``AsyncOpenAI``
client and awaits ``images.edit(...)`` instead of using a module-level sync
``OpenAI()`` singleton. Everything else — the padding math, the prompt, the
token-usage extraction, and the "tokens were already spent, let the caller
log them" exception behavior — is preserved exactly.

The disk-bound helpers (``fetch_download_asset``, ``combine_masks``,
``prepare_images_for_openai``) stay plain synchronous functions using
``httpx``'s sync convenience API (``httpx.get``) and are called directly (not
off-loaded to a thread pool) from inside ``run_generation_pipeline`` — the porting brief scoped the async
conversion specifically to the OpenAI call, and the real caller
(``VisualizerService.curtain_generation`` in ``app/modules/visualizer/service.py``)
already `await`s this function directly without wrapping it in
``anyio.to_thread.run_sync``, confirming that's the intended shape.
"""

from __future__ import annotations

import base64
import io
import uuid
from pathlib import Path

import cv2
import httpx
from openai import AsyncOpenAI
from PIL import Image, ImageOps

from app.common.storage import resolve_uploaded_file_path


class CurtainGenerationError(RuntimeError):
    """Raised when the post-OpenAI finalization step (padding removal) fails
    after OpenAI tokens have already been spent.

    Carries ``.openai_token_usage`` so the caller can still log spent tokens
    on partial failure. The original Flask pipeline did this by monkey-patching
    an ``openai_token_usage`` attribute directly onto whatever exception
    instance the failure happened to raise (``e.openai_token_usage = token_usage;
    raise``) — which works because Python exceptions accept arbitrary
    attribute assignment, but produces an untyped, ad-hoc contract. This
    dedicated exception type carries the same attribute in a way callers can
    rely on (``getattr(e, "openai_token_usage", None)`` still works
    identically against it).
    """

    def __init__(self, message: str, openai_token_usage: dict):
        super().__init__(message)
        self.openai_token_usage = openai_token_usage


def fetch_download_asset(url: str, uploads_dir: Path, masks_dir: Path) -> Path | None:
    if not url:
        return None

    # Root-relative URLs (no http(s) scheme) are read straight off local
    # disk instead of round-tripping through HTTP — same reasoning as
    # `imaging.shared.download_image`: this is exactly the shape
    # `LocalDiskStorage.save_bytes` returns for anything saved by our own
    # admin (e.g. a RoomCategoryImage/hotspot mask generated locally, as
    # opposed to the customer-facing curtain-generation flow's own inputs,
    # which are always already-absolute URLs from the segmentation
    # service). The legacy filename/uploads-or-masks-dir guessing below is
    # kept for that original (always-absolute-URL) caller; a relative path
    # already encodes its own correct subfolder, so it's resolved directly.
    if not url.startswith(("http://", "https://")):
        local_path = resolve_uploaded_file_path(url)
        return local_path if local_path is not None and local_path.exists() else None

    parts = url.split("/")
    filename = parts[-1]
    parent_dir = parts[-2] if len(parts) >= 2 else ""

    if parent_dir == "uploads":
        target_dir = uploads_dir
    elif parent_dir == "masks":
        target_dir = masks_dir
    else:
        target_dir = uploads_dir

    local_path = target_dir / filename

    # Use local file if it exists
    if local_path.exists():
        print(f"[INFO] Found local asset: {filename}")
        return local_path

    # Else, download directly to the target folder
    print(f"[INFO] Downloading missing asset: {filename}")
    resp = httpx.get(url, timeout=30)
    resp.raise_for_status()

    local_path.write_bytes(resp.content)

    return local_path


def combine_masks(mask_paths: list[Path], cache_dir: Path) -> Path | None:
    if not mask_paths:
        return None
    if len(mask_paths) == 1:
        return mask_paths[0]

    combined_mask = None
    for path in mask_paths:
        img = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
        if combined_mask is None:
            combined_mask = img
        else:
            combined_mask = cv2.bitwise_or(combined_mask, img)

    combined_path = cache_dir / f"combined_mask_{uuid.uuid4().hex}.png"
    cv2.imwrite(str(combined_path), combined_mask)
    return combined_path


def prepare_images_for_openai(
    room_path: Path, mask_path: Path, output_room_path: Path, output_mask_path: Path
) -> None:
    target_size = (1024, 1024)

    with Image.open(room_path) as room_img:
        room_img = room_img.convert("RGBA")
        room_square = ImageOps.pad(room_img, target_size, color=(0, 0, 0, 0))
        room_square.save(output_room_path, format="PNG")

    with Image.open(mask_path) as mask_img:
        mask_img = mask_img.convert("RGBA")
        mask_square = ImageOps.pad(mask_img, target_size, color=(0, 0, 0, 255))

        data = mask_square.getdata()
        new_data = [(255, 255, 255, 0) if item[0] > 200 else (0, 0, 0, 255) for item in data]

        mask_square.putdata(new_data)
        mask_square.save(output_mask_path, format="PNG")


def remove_padding(generated_image_bytes: bytes, original_path: Path) -> bytes:
    """Crop the letterbox padding OpenAI's 1024x1024 canvas added and resize
    back to the original room image's exact dimensions. Returns PNG bytes via
    an in-memory buffer instead of writing a final file — the caller (the
    async storage layer) persists the bytes however it sees fit.
    """
    with Image.open(original_path) as orig_img:
        orig_w, orig_h = orig_img.size

    target_size = 1024

    scale = min(target_size / orig_w, target_size / orig_h)
    new_w = int(orig_w * scale)
    new_h = int(orig_h * scale)

    pad_x = (target_size - new_w) // 2
    pad_y = (target_size - new_h) // 2

    with Image.open(io.BytesIO(generated_image_bytes)) as gen_img:
        cropped_img = gen_img.crop((pad_x, pad_y, pad_x + new_w, pad_y + new_h))  # Crop out the padded bars

        final_img = cropped_img.resize((orig_w, orig_h), Image.Resampling.LANCZOS)  # Resize to exact original size

        buffer = io.BytesIO()
        final_img.save(buffer, format="PNG")
        return buffer.getvalue()


async def run_generation_pipeline(
    image_url: str,
    mask_urls: list[str],
    curtain_style: str,
    openai_client: AsyncOpenAI,
    cache_dir: Path,
    uploads_dir: Path,
    masks_dir: Path,
) -> tuple[bytes, dict]:
    print(f"[INFO] Starting GenAI Curtain Pipeline for style: {curtain_style}")

    # Download Assets and combine masks
    local_room_path = fetch_download_asset(image_url, uploads_dir, masks_dir)
    local_mask_paths = [fetch_download_asset(url, uploads_dir, masks_dir) for url in mask_urls]
    combined_mask_path = combine_masks(local_mask_paths, cache_dir)

    if not combined_mask_path:
        raise ValueError("Failed to process masks for generation.")

    # Prepare formatting for OpenAI
    random_suffix = uuid.uuid4().hex
    ready_room_path = cache_dir / f"ready_room_{random_suffix}.png"
    ready_mask_path = cache_dir / f"ready_mask_{random_suffix}.png"

    prepare_images_for_openai(local_room_path, combined_mask_path, ready_room_path, ready_mask_path)

    # Call OpenAI
    prompt = f"A realistic, high-quality window dressing featuring {curtain_style} style curtains. Natural lighting matching the room. Use the masked area as the window location for the curtains. Don't alter the rest of the room."

    with open(ready_room_path, "rb") as room_f, open(ready_mask_path, "rb") as mask_f:
        response = await openai_client.images.edit(
            model="gpt-image-2",
            image=room_f,
            mask=mask_f,
            prompt=prompt,
            n=1,
            size="1024x1024",
        )

    usage = getattr(response, "usage", None)
    token_usage = {
        "input_tokens": getattr(usage, "input_tokens", 0) or 0,
        "output_tokens": getattr(usage, "output_tokens", 0) or 0,
        "total_tokens": getattr(usage, "total_tokens", 0) or 0,
    }
    print(f"[INFO] OpenAI token usage: {token_usage}")

    try:
        raw_gen_bytes = base64.b64decode(response.data[0].b64_json)

        # Remove padding and restore the original resolution
        print("[INFO] Removing padding and restoring original resolution...")
        final_bytes = remove_padding(raw_gen_bytes, local_room_path)
    except Exception as e:
        # Tokens were already consumed at this point — let the caller log them
        raise CurtainGenerationError(
            f"Padding removal failed after OpenAI generation: {e}", openai_token_usage=token_usage
        ) from e

    print(f"[SUCCESS] Final hi-res image ready ({len(final_bytes)} bytes)")

    return final_bytes, token_usage

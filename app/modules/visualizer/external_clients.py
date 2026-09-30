import base64
import logging
import uuid

import cv2
import httpx
import numpy as np
from anyio import to_thread
from openai import AsyncOpenAI

from app.common.storage import resolve_uploaded_file_path
from app.core.config import settings
from app.exceptions.http_exceptions import BadRequestException
from app.modules.visualizer import storage_paths
from app.modules.visualizer.imaging import scene_segmentation

logger = logging.getLogger(__name__)

# First httpx/openai precedent in this codebase — every other module is
# entirely internal (DB + local disk), so these two external integrations
# have no existing convention to follow beyond "use the natural async client".


def get_openai_client() -> AsyncOpenAI:
    return AsyncOpenAI(api_key=settings.openai_api_key)


class SamApiTimeoutError(Exception):
    """SAM took too long to respond. Its response time is genuinely highly
    variable (observed anywhere from a few seconds to ~150s for the same
    kind of request) — this is Segmind's own load/queueing, not a
    deterministic per-point failure, so a retry is actually likely to
    succeed. Kept distinct from a real "no mask" result so callers can tell
    users to retry rather than "click somewhere else"."""


async def call_sam_api(image_b64: str, coordinates: list[float]) -> bytes | None:
    """Ported from get_or_create_mask's SAM API branch. coordinates is sent as
    a stringified Python list (e.g. "[512, 300]"), matching the original —
    the SAM API expects that exact string shape, not a JSON array.

    Raises SamApiTimeoutError on a timeout specifically (see above). Returns
    None on any other failure (connection error, non-2xx status, or a
    response with no mask) — callers treat that as "couldn't get a mask for
    this point" and surface a clean 4xx, so a genuine SAM outage or a point
    it can't segment should never bubble up as an unhandled 500."""
    try:
        async with httpx.AsyncClient(timeout=240.0) as client:
            response = await client.post(
                settings.sam_api_url,
                headers={"x-api-key": settings.sam_api_key, "Content-Type": "application/json"},
                json={
                    "base64": True,
                    "image": image_b64,
                    "overlay_mask": False,
                    "refine_mask": True,
                    "coordinates": str(coordinates),
                },
            )
            response.raise_for_status()
            data = response.json()
    except httpx.TimeoutException as exc:
        logger.warning("SAM API call timed out")
        raise SamApiTimeoutError() from exc
    except httpx.HTTPError:
        logger.exception("SAM API call failed")
        return None

    mask_b64 = data.get("image")
    if not mask_b64 and data.get("masks"):
        mask_b64 = data["masks"][0]
    if not mask_b64:
        return None
    return base64.b64decode(mask_b64)


def _write_bytes(path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


async def _run_scene_segmentation(image_bytes: bytes) -> dict:
    """Decode the image, run the real local segmentation pipeline
    (imaging/scene_segmentation.py) off the event loop, persist the original
    photo + every hotspot's mask + the debug colour map under this module's
    own storage_paths convention, and assemble the same response shape the
    four existing callers already expect. This used to be a pass-through to
    api.homexperia.com/api/upload — it no longer calls out anywhere."""
    image_array = np.frombuffer(image_bytes, dtype=np.uint8)
    image_bgr = await to_thread.run_sync(cv2.imdecode, image_array, cv2.IMREAD_COLOR)
    if image_bgr is None:
        raise BadRequestException("Could not decode the uploaded image")

    result = await to_thread.run_sync(scene_segmentation.process_scene, image_bgr)

    room_id = str(uuid.uuid4())
    upload_path = storage_paths.upload_path(room_id)
    await to_thread.run_sync(_write_bytes, upload_path, image_bytes)

    hotspots = []
    for spot in result["hotspots"]:
        mask_path = storage_paths.mask_path(room_id, spot["image_hotspots_id"])
        await to_thread.run_sync(_write_bytes, mask_path, spot["mask_png_bytes"])
        hotspots.append(
            {
                "image_hotspots_id": spot["image_hotspots_id"],
                "type": spot["type"],
                "label": spot["label"],
                "x": spot["x"],
                "y": spot["y"],
                "bbox": spot["bbox"],
                "segment_id": spot["segment_id"],
                "mask_image": storage_paths.mask_url(room_id, spot["image_hotspots_id"]),
            }
        )

    map_path = storage_paths.scene_map_path(room_id)
    await to_thread.run_sync(_write_bytes, map_path, result["map_png_bytes"])

    return {
        "status": "success",
        "room_category_image_id": room_id,
        "image_url": storage_paths.upload_url(room_id),
        "hotspots": hotspots,
        "found_objects": result["found_objects"],
        "image_dims": result["image_dims"],
        "map_image_url": storage_paths.scene_map_url(room_id),
    }


async def proxy_upload(payload: dict) -> dict:
    """Decode the incoming image (base64 or a URL — mirrors the Flask
    reference's analyze_scene() branches; this codebase's callers only ever
    send imageBase64, but imageUrl is supported for parity) and run it
    through our own local segmentation pipeline. Used to forward to
    api.homexperia.com/api/upload — see _run_scene_segmentation."""
    if "imageBase64" in payload:
        b64 = payload["imageBase64"]
        if "," in b64:
            b64 = b64.split(",", 1)[1]
        image_bytes = base64.b64decode(b64)
    elif "imageUrl" in payload:
        image_bytes = await download_bytes(payload["imageUrl"])
    else:
        raise BadRequestException("No image provided (imageBase64 or imageUrl)")
    return await _run_scene_segmentation(image_bytes)


async def proxy_upload_bytes(image_bytes: bytes) -> dict:
    """Same local pipeline as proxy_upload, for callers that already have
    raw image bytes (curtain-generation's re-segmentation step, admin's
    auto-detect-hotspots, curtain hotspot panel-splitting)."""
    return await _run_scene_segmentation(image_bytes)


async def download_bytes(url: str, *, timeout: float = 30.0, spoof_user_agent: bool = False) -> bytes:
    """Reads one of our own already-stored files (get_storage()'s or
    storage_paths' root-relative "/uploads/..." URLs, e.g. a segmentation
    mask the local pipeline above just wrote) directly off disk instead of
    over HTTP — a plain GET on a root-relative URL isn't even a valid
    request, and even for an absolute self-URL it would be a pointless
    round-trip for a file this same process already has (same idiom as
    pdf_generator.py's download_image_as_pil). Only a genuinely external URL
    goes over HTTP."""
    local_path = resolve_uploaded_file_path(url)
    if local_path is not None and local_path.exists():
        return await to_thread.run_sync(local_path.read_bytes)
    headers = {"User-Agent": "Mozilla/5.0"} if spoof_user_agent else {}
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.get(url, headers=headers)
        response.raise_for_status()
        return response.content

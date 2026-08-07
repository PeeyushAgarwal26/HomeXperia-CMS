import base64
import logging

import httpx
from openai import AsyncOpenAI

from app.core.config import settings

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


async def proxy_upload(payload: dict) -> dict:
    """Ported from /api/upload's pass-through to the production segmentation
    service — the entire incoming JSON body is forwarded as-is."""
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            settings.prod_segmentation_api_url,
            headers={
                "Origin": "https://dev.homexperia.com",
                "x-api-key": settings.prod_segmentation_api_key,
                "Content-Type": "application/json",
            },
            json=payload,
        )
        response.raise_for_status()
        return response.json()


async def proxy_upload_bytes(image_bytes: bytes) -> dict:
    """Ported from /api/curtain-generation's re-upload-for-segmentation step —
    same prod proxy, but with a freshly generated image sent as base64."""
    return await proxy_upload({"imageBase64": base64.b64encode(image_bytes).decode()})


async def download_bytes(url: str, *, timeout: float = 30.0, spoof_user_agent: bool = False) -> bytes:
    headers = {"User-Agent": "Mozilla/5.0"} if spoof_user_agent else {}
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.get(url, headers=headers)
        response.raise_for_status()
        return response.content

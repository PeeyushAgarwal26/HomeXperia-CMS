import base64
import hashlib
import json
import logging
import shutil
import uuid
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from anyio import to_thread
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.storage import get_storage
from app.exceptions.http_exceptions import BadRequestException, NotFoundException
from app.modules.ai_credits.service import AiCreditService
from app.modules.visualizer import cache, external_clients, storage_paths
from app.modules.visualizer.imaging import (
    curtain,
    curtain_generation as curtain_generation_pipeline,
    curtain_geometry,
    depth,
    floor,
    pdf_generator,
    rug_depth,
    rug_overlay,
    rug_scene,
    shared,
    wall,
    wall_depth,
    wall_scene,
    wallart_placement,
)
from app.modules.visualizer.repository import UsageLogRepository
from app.modules.visualizer.schemas import (
    CacheClearResponse,
    CacheFileEntry,
    CacheStatsResponse,
    CleanupResponse,
    CurtainGenerationRequest,
    HotspotLayer,
    HotspotSettings,
    MaskGenerationRequest,
    MaskGenerationResponse,
    ProcessRoomRequest,
    ProcessRoomResponse,
    ResetRoomRequest,
    ResetRoomResponse,
    RoomDetailResponse,
    RoomListItem,
    RoomListResponse,
    RugVisualizerSceneRequest,
    RugVisualizerSceneResponse,
    WallArtVisualizerSceneRequest,
    WallArtVisualizerSceneResponse,
)

logger = logging.getLogger(__name__)

M_TO_FT = 3.280839895

ROOM_DIMENSION_PROMPT = """Estimate the room floor width and length from this single interior image.
Return only a JSON object with:
- estimated_width_ft
- estimated_length_ft
- estimated_width_cm
- estimated_length_cm
Use visible furniture, floor tiles, and room proportions for estimation.
This is an estimate, not an exact measurement."""

ROOM_DIMENSION_SCHEMA = {
    "type": "json_schema",
    "name": "room_dimension_estimate",
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "estimated_width_ft": {"type": "number"},
            "estimated_length_ft": {"type": "number"},
        },
        "required": ["estimated_width_ft", "estimated_length_ft"],
    },
}

WALL_DIMENSION_PROMPT = """Estimate the real-world width and height, in feet, of the single wall
visible in this interior photo (the flat vertical surface the wall region
covers - not the whole room). Use visible furniture, doors, windows, and
typical ceiling height for scale.
Return only a JSON object with:
- estimated_width_ft
- estimated_height_ft
This is an estimate, not an exact measurement."""

WALL_DIMENSION_SCHEMA = {
    "type": "json_schema",
    "name": "wall_dimension_estimate",
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "estimated_width_ft": {"type": "number"},
            "estimated_height_ft": {"type": "number"},
        },
        "required": ["estimated_width_ft", "estimated_height_ft"],
    },
}

ALLOWED_CLEANUP_FOLDERS = {
    "uploads": storage_paths.UPLOADS_DIR,
    "generated": storage_paths.GENERATED_DIR,
    "masks": storage_paths.MASKS_DIR,
}

# Flask hardcodes this literal hotspot id for every /mask-generation call —
# every call for a given room overwrites the same file, regardless of which
# point was clicked. Preserved as-is for parity.
MASK_GENERATION_HOTSPOT_ID = "hotspotId"

ROOM_DATA_FILE = Path("data/rooms_data.json")


def _room_image_url(filename: str) -> str:
    return f"/static/room-images/{filename}"


class VisualizerService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.usage_repo = UsageLogRepository(session)
        self.ai_credit_service = AiCreditService(session)
        storage_paths.ensure_dirs()

    # ---- upload (thin proxy) ----

    async def upload(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not payload:
            raise BadRequestException("No payload provided")
        return await external_clients.proxy_upload(payload)

    # ---- process-room ----

    async def process_room(
        self, customer_id: uuid.UUID | None, request: ProcessRoomRequest
    ) -> ProcessRoomResponse:
        room_id = request.roomId
        base_image_url = request.baseImageUrl

        existing_hotspots = list(request.appliedHotspots)
        full_layer_stack = self._merge_hotspots(existing_hotspots, request.applyHotspot)

        layer_hash = self._layer_hash(full_layer_stack)
        output_key = (room_id, base_image_url, layer_hash)

        cached_url = cache.get_output(output_key)
        if cached_url is not None:
            await self._record_usage(customer_id, room_id, full_layer_stack)
            return ProcessRoomResponse(
                success=True,
                finalImageUrl=cached_url,
                appliedHotspots=full_layer_stack,
                remainingHotspots=request.remainingHotspots,
            )

        async with cache.output_lock(output_key):
            cached_url = cache.get_output(output_key)
            if cached_url is not None:
                await self._record_usage(customer_id, room_id, full_layer_stack)
                return ProcessRoomResponse(
                    success=True,
                    finalImageUrl=cached_url,
                    appliedHotspots=full_layer_stack,
                    remainingHotspots=request.remainingHotspots,
                )

            try:
                current_image = await self._get_or_build_base_image(room_id, base_image_url)
            except Exception:
                logger.exception("process_room: failed to download base image for room %s", room_id)
                return ProcessRoomResponse(
                    success=False,
                    error="Failed to download base image",
                    finalImageUrl=base_image_url,
                    appliedHotspots=existing_hotspots,
                    remainingHotspots=request.remainingHotspots,
                )

            try:
                panel_quads = await self._build_curtain_geometry(full_layer_stack, current_image, room_id)
                for layer in full_layer_stack:
                    quad_plan = panel_quads.get(layer.hotspotId) if layer.hotspotId else None
                    current_image = await self._process_single_layer(
                        current_image, layer, room_id, panel_quad=quad_plan["quad_norm"] if quad_plan else None
                    )

                final_bytes = await to_thread.run_sync(self._encode_jpeg, current_image)
                final_url = await get_storage().save_bytes(
                    f"{room_id}.jpg", final_bytes, storage_paths.GENERATED_SUBFOLDER
                )
                cache.set_output(output_key, final_url)
                await self._record_usage(customer_id, room_id, full_layer_stack)
                return ProcessRoomResponse(
                    success=True,
                    finalImageUrl=final_url,
                    appliedHotspots=full_layer_stack,
                    remainingHotspots=request.remainingHotspots,
                )
            except Exception as e:
                logger.exception("process_room: render failed for room %s", room_id)
                return ProcessRoomResponse(
                    success=False,
                    error=str(e),
                    finalImageUrl=base_image_url,
                    appliedHotspots=existing_hotspots,
                    remainingHotspots=request.remainingHotspots,
                )

    def _merge_hotspots(
        self, existing: list[HotspotLayer], new_layers: list[HotspotLayer] | HotspotLayer | None
    ) -> list[HotspotLayer]:
        if new_layers is None:
            return existing
        new_list = new_layers if isinstance(new_layers, list) else [new_layers]
        merged = list(existing)
        by_id = {h.hotspotId: i for i, h in enumerate(merged) if h.hotspotId}
        for layer in new_list:
            if layer.hotspotId and layer.hotspotId in by_id:
                merged[by_id[layer.hotspotId]] = layer
            else:
                merged.append(layer)
                if layer.hotspotId:
                    by_id[layer.hotspotId] = len(merged) - 1
        return merged

    def _layer_hash(self, layers: list[HotspotLayer]) -> str:
        payload = json.dumps(
            [layer.model_dump(mode="json") for layer in layers], sort_keys=True, default=str
        )
        return hashlib.md5(payload.encode()).hexdigest()

    async def _get_or_build_base_image(self, room_id: str, base_image_url: str) -> np.ndarray:
        cached = cache.get_processed_base(room_id)
        if cached is not None and cached[0] == base_image_url:
            return cached[1].copy()

        async with cache.room_lock(room_id):
            cached = cache.get_processed_base(room_id)
            if cached is not None and cached[0] == base_image_url:
                return cached[1].copy()

            image = await to_thread.run_sync(shared.download_image, base_image_url, storage_paths.CACHE_DIR)
            image = await to_thread.run_sync(shared.upscale_image, image)
            image = await to_thread.run_sync(
                shared.preprocess_image, image, storage_paths.DEBUG_DIR, room_id
            )
            cache.set_processed_base(room_id, base_image_url, image)
            return image.copy()

    async def _build_curtain_geometry(
        self, full_layer_stack: list[HotspotLayer], current_image: np.ndarray, room_id: str
    ) -> dict[str, dict]:
        """Measure every curtain in the stack together, before any layer is
        rendered, so sibling panels on one window share a rod/hem line
        instead of each being warped independently off its own noisy edges.
        Returns {} (skip planning entirely) unless at least one panel-
        flagged product is actually being applied this request — the joint
        fit costs real work, so it isn't run for an all-tiled curtain
        window. Never raises: a mask fetch failing for one hotspot here
        just drops it from the plan, same as _process_single_layer's own
        per-layer isolation."""
        curtain_masks: dict[str, np.ndarray] = {}
        panel_present = False
        height, width = current_image.shape[:2]

        for layer in full_layer_stack:
            if shared.find_category((layer.category or "").lower()) != "curtain":
                continue
            hotspot_id = layer.hotspotId
            if not hotspot_id:
                continue
            product_dict = layer.product.model_dump() if layer.product else None
            if curtain.is_panel_product(product_dict):
                panel_present = True
            coords = self._resolve_coords(layer.coords, current_image.shape)
            try:
                mask = await self._get_or_create_mask(room_id, hotspot_id, current_image, coords, layer.mask_image)
            except Exception:
                logger.exception("build_curtain_geometry: mask fetch failed for hotspot %s", hotspot_id)
                continue
            curtain_masks[hotspot_id] = mask

        if not panel_present or not curtain_masks:
            return {}

        return await to_thread.run_sync(curtain_geometry.plan_panel_quads, curtain_masks, width, height)

    async def _process_single_layer(
        self, current_image: np.ndarray, layer: HotspotLayer, room_id: str, panel_quad: list | None = None
    ) -> np.ndarray:
        hotspot_id = layer.hotspotId or "hotspotId"
        coords = self._resolve_coords(layer.coords, current_image.shape)
        mask = await self._get_or_create_mask(room_id, hotspot_id, current_image, coords, layer.mask_image)
        texture_image = await self._resolve_product_image(layer.product)
        category = shared.find_category((layer.category or "").lower())

        try:
            settings_dict = layer.settings.model_dump() if layer.settings else {}
            product_width_cm = (
                curtain.parse_width_to_cm(layer.product.width)
                if layer.product and layer.product.width
                else None
            )
            if category == "curtain":
                product_dict = layer.product.model_dump() if layer.product else None
                is_panel = curtain.is_panel_product(product_dict)
                result_image, _ = await to_thread.run_sync(
                    curtain.apply_pattern,
                    current_image,
                    mask,
                    texture_image,
                    settings_dict,
                    product_width_cm,
                    is_panel,
                    panel_quad,
                )
            elif category == "floor":
                detection = await to_thread.run_sync(floor.detect_floor_quad, current_image)
                if detection is None:
                    return current_image
                floor_quad, _ = detection
                result_image = await to_thread.run_sync(
                    floor.apply_pattern, current_image, mask, texture_image, floor_quad, settings_dict
                )
            elif category == "wall":
                # wall_depth.apply_pattern (the reference's real, live wall
                # handler — wall.apply_pattern below is the superseded
                # single-quad version their own app.py no longer calls) is
                # depth-grounded and multi-plane; it never reads a product's
                # real-world width the way the old algorithm did, so
                # product_width_cm (still used by the curtain branch above)
                # isn't threaded through here.
                wall_depth_map = None
                try:
                    wall_depth_map = await to_thread.run_sync(depth.get_metric_depth, current_image)
                except Exception:
                    logger.exception("wall apply_pattern: depth estimation failed, using 2D fallback")
                result_image, auto_repeat = await to_thread.run_sync(
                    wall_depth.apply_pattern,
                    current_image,
                    texture_image,
                    mask,
                    settings_dict.get("repeat"),
                    wall_depth_map,
                )
                if auto_repeat is not None:
                    if layer.settings is None:
                        layer.settings = HotspotSettings(repeat=auto_repeat)
                    else:
                        layer.settings.repeat = auto_repeat
            else:
                result_image = await to_thread.run_sync(
                    rug_overlay.apply_pattern,
                    current_image,
                    mask,
                    texture_image,
                    settings_dict,
                    room_id,
                    hotspot_id,
                    storage_paths.DEBUG_DIR,
                )
            return result_image
        except Exception:
            logger.exception("process_single_layer failed for hotspot %s (room %s)", hotspot_id, room_id)
            return current_image

    def _resolve_coords(self, coords: Any, shape: tuple[int, ...]) -> dict[str, float]:
        height, width = shape[0], shape[1]
        if isinstance(coords, dict):
            x, y = coords.get("x", 0), coords.get("y", 0)
        elif isinstance(coords, (list, tuple)) and len(coords) >= 2:
            x, y = coords[0], coords[1]
        else:
            x, y = 0, 0
        x, y = float(x), float(y)
        if 0 <= x <= 1 and 0 <= y <= 1:
            x, y = x * width, y * height
        return {"x": x, "y": y}

    async def _resolve_product_image(self, product: Any) -> np.ndarray:
        if product is None or not getattr(product, "productImageUrl", None):
            raise ValueError("Missing product image URL")
        return await to_thread.run_sync(shared.download_image, product.productImageUrl, storage_paths.CACHE_DIR)

    async def _get_or_create_mask(
        self,
        room_id: str,
        hotspot_id: str,
        current_image: np.ndarray,
        coords: dict[str, float],
        mask_url_hint: str | None,
    ) -> np.ndarray:
        path = storage_paths.mask_path(room_id, hotspot_id)
        if path.exists():
            mask = await to_thread.run_sync(cv2.imread, str(path), cv2.IMREAD_GRAYSCALE)
            if mask is not None:
                return mask

        if mask_url_hint:
            mask_bytes = await external_clients.download_bytes(mask_url_hint)
            mask = await to_thread.run_sync(self._decode_grayscale, mask_bytes)
            await to_thread.run_sync(self._write_mask, path, mask)
            return mask

        original_h, original_w = current_image.shape[0], current_image.shape[1]
        image_b64, was_downscaled, scale = await to_thread.run_sync(shared.encode_for_sam, current_image)
        sam_x = coords["x"] * scale if was_downscaled else coords["x"]
        sam_y = coords["y"] * scale if was_downscaled else coords["y"]
        try:
            mask_bytes = await external_clients.call_sam_api(image_b64, [sam_x, sam_y])
        except external_clients.SamApiTimeoutError:
            raise RuntimeError("SAM API took too long to respond — please try again")
        if mask_bytes is None:
            raise RuntimeError("SAM couldn't find a clear object at that point")
        mask = await to_thread.run_sync(self._decode_grayscale, mask_bytes)
        if was_downscaled:
            mask = await to_thread.run_sync(cv2.resize, mask, (original_w, original_h), cv2.INTER_LINEAR)
        await to_thread.run_sync(self._write_mask, path, mask)
        return mask

    @staticmethod
    def _decode_grayscale(data: bytes) -> np.ndarray:
        return cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_GRAYSCALE)

    @staticmethod
    def _write_mask(path: Path, mask: np.ndarray) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(path), mask)

    @staticmethod
    def _encode_jpeg(image: np.ndarray) -> bytes:
        _, buffer = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 85])
        return buffer.tobytes()

    async def _record_usage(
        self, customer_id: uuid.UUID | None, room_id: str, layers: list[HotspotLayer]
    ) -> None:
        if customer_id is None:
            return  # anonymous/service-key caller — no real identity to attribute usage to
        hotspots = [(layer.hotspotId, layer.category) for layer in layers if layer.hotspotId]
        newly_counted_ids = await self.usage_repo.record_tooltip_usage(customer_id, room_id, hotspots)
        await self._charge_tooltip_credits(customer_id, room_id, layers, newly_counted_ids)

    async def _charge_tooltip_credits(
        self,
        customer_id: uuid.UUID | None,
        room_id: str,
        layers: list[HotspotLayer],
        newly_counted_ids: set[str],
    ) -> None:
        """One AI credit per hotspot the first time it's ever applied by this
        customer (Step-6/7); re-applying the same hotspot afterwards is free.
        Billed to whoever is logged in and using the AI (resolved once for
        the whole call, since that's the same customer for every layer here),
        not to whichever supplier owns the product being rendered."""
        billed_account = await self.ai_credit_service.resolve_billing_account(customer_id)
        for layer in layers:
            if not layer.hotspotId or not layer.product or not layer.product.productId:
                continue
            is_curtain = (layer.category or "").lower() == "curtain"
            product_id = uuid.UUID(str(layer.product.productId))
            if layer.hotspotId in newly_counted_ids:
                await self.ai_credit_service.charge_credit(
                    billed_account,
                    customer_id,
                    room_id,
                    room_category_name=layer.category,
                    is_curtain_room=is_curtain,
                    action_type="first_tooltip_render",
                    tooltip_element_label=layer.product.productId,
                    product_id=product_id,
                )
            else:
                await self.ai_credit_service.log_free_event(
                    billed_account,
                    customer_id,
                    room_id,
                    room_category_name=layer.category,
                    is_curtain_room=is_curtain,
                    action_type="tooltip_free_rerender",
                    tooltip_element_label=layer.product.productId,
                    product_id=product_id,
                )

    # ---- curtain-generation ----

    async def curtain_generation(
        self, customer_id: uuid.UUID | None, request: CurtainGenerationRequest
    ) -> dict[str, Any]:
        log_id: uuid.UUID | None = None
        try:
            image_bytes, token_usage = await curtain_generation_pipeline.run_generation_pipeline(
                request.image_url,
                request.mask_urls,
                request.curtain_style,
                external_clients.get_openai_client(),
                storage_paths.CACHE_DIR,
                storage_paths.UPLOADS_DIR,
                storage_paths.MASKS_DIR,
            )
            if customer_id is not None:
                log_id = await self.usage_repo.log_generation_attempt(
                    customer_id, request.curtain_style, "success", **token_usage
                )
            segmentation_data = await external_clients.proxy_upload_bytes(image_bytes)
            new_room_id = (
                segmentation_data.get("room_category_image_id")
                or segmentation_data.get("roomId")
                or segmentation_data.get("room_id")
            )
            if log_id is not None:
                await self.usage_repo.set_segmentation_result(log_id, "success", room_id=new_room_id)
            await self._charge_curtain_credit(customer_id, new_room_id, request)
            segmentation_data["original_wo_curtain"] = request.image_url
            return segmentation_data
        except Exception as e:
            logger.exception("curtain_generation failed")
            token_usage = getattr(e, "openai_token_usage", None)
            if customer_id is not None:
                if log_id is not None:
                    await self.usage_repo.set_segmentation_result(log_id, "failed", error=str(e))
                else:
                    status = "success" if token_usage else "failed"
                    await self.usage_repo.log_generation_attempt(
                        customer_id, request.curtain_style, status, error=str(e), **(token_usage or {})
                    )
            return {"success": False, "error": str(e)}

    async def _charge_curtain_credit(
        self, customer_id: uuid.UUID | None, room_id: str | None, request: CurtainGenerationRequest
    ) -> None:
        billed_account = await self.ai_credit_service.resolve_billing_account(customer_id)
        await self.ai_credit_service.charge_credit(
            billed_account,
            customer_id,
            room_id,
            room_category_name=None,
            is_curtain_room=False,
            action_type="curtain_applied",
            tooltip_element_label=request.curtain_style,
        )

    # ---- wallart-visualizer-scene ----

    async def wallart_visualizer_scene(
        self, request: WallArtVisualizerSceneRequest
    ) -> WallArtVisualizerSceneResponse:
        if request.room_b64:
            image = await to_thread.run_sync(rug_scene.b64_to_cv2, request.room_b64)
        elif request.room_url:
            image = await to_thread.run_sync(shared.download_image, request.room_url, storage_paths.CACHE_DIR)
        else:
            raise BadRequestException("Could not load room image")

        height, width = image.shape[0], image.shape[1]

        wall_mask_gray = None
        if request.wall_mask_url:
            mask_bytes = await external_clients.download_bytes(request.wall_mask_url)
            wall_mask_gray = await to_thread.run_sync(self._decode_grayscale, mask_bytes)
            if wall_mask_gray.shape[:2] != (height, width):
                wall_mask_gray = await to_thread.run_sync(cv2.resize, wall_mask_gray, (width, height))

        product_image = None
        if request.product_url:
            product_image = await to_thread.run_sync(
                shared.download_image, request.product_url, storage_paths.CACHE_DIR
            )

        # The real placement engine (imaging/wallart_placement.py, ported
        # from the reference's utils/wallart.py — real-world eye-level/
        # floor-anchor placement priority on a metric-plane-rectified clear
        # search, not the naive centering below) needs both a real mask and
        # a real product image to run. When either is missing, or it can't
        # find a clear spot on the detected wall face, fall straight through
        # to the classical path — this endpoint has never hard-failed and
        # still doesn't.
        placement = None
        if wall_mask_gray is not None and product_image is not None:
            depth_map = None
            try:
                depth_map = await to_thread.run_sync(depth.get_metric_depth, image)
            except Exception:
                logger.exception("wallart_depth_estimation_failed")

            art_width_ft, art_height_ft = self._art_dimensions_ft(request.product_dimensions)
            product_dims_cm = None
            if art_width_ft and art_height_ft:
                # analyze_wallart_scene wants centimetres; _art_dimensions_ft
                # already resolved the feet-vs-inches ambiguity in the raw
                # product_dimensions payload, so reuse its output rather
                # than re-deriving that heuristic here.
                product_dims_cm = {"width": art_width_ft * 30.48, "length": art_height_ft * 30.48}

            try:
                placement = await to_thread.run_sync(
                    wallart_placement.analyze_wallart_scene,
                    image,
                    wall_mask_gray,
                    product_image,
                    product_dims_cm,
                    depth_map,
                )
            except Exception:
                logger.exception("wallart_placement_failed")

        if placement is not None:
            return await self._wallart_response_from_placement(placement, image, width, height)

        return await self._wallart_classical_fallback(request, image, width, height, wall_mask_gray, product_image)

    async def _wallart_response_from_placement(
        self, placement: dict, image: np.ndarray, width: int, height: int
    ) -> WallArtVisualizerSceneResponse:
        face_mask = placement["face_mask"]
        shadow_map = await to_thread.run_sync(rug_scene.extract_shadow_map, image, face_mask)
        shadow_map_b64 = await to_thread.run_sync(rug_scene.encode_shadow_map_b64, shadow_map)
        _, wall_mask_buffer = cv2.imencode(".png", face_mask)
        wall_mask_b64 = base64.b64encode(wall_mask_buffer).decode()

        return WallArtVisualizerSceneResponse(
            wall_quad_norm=placement["wall_quad_norm"],
            clear_region_quad_norm=placement["clear_region_quad_norm"],
            room_width=width,
            room_height=height,
            wall_width_ft=placement["wall_width_ft"],
            wall_height_ft=placement["wall_height_ft"],
            art_width_ft=placement["art_width_ft"],
            art_height_ft=placement["art_height_ft"],
            fitted=placement["fitted"],
            used_depth=placement["used_depth"],
            wall_mask_b64=wall_mask_b64,
            shadow_map_b64=shadow_map_b64,
            placement_quad_norm=placement["placement_quad_norm"],
            placement_center_norm=placement["placement_center_norm"],
        )

    async def _wallart_classical_fallback(
        self,
        request: WallArtVisualizerSceneRequest,
        image: np.ndarray,
        width: int,
        height: int,
        wall_mask_gray: np.ndarray | None,
        product_image: np.ndarray | None,
    ) -> WallArtVisualizerSceneResponse:
        """Pre-wallart_placement logic: classical 2D quad + LAB-color clear-
        region heuristic + naive centered sizing. Kept as the degrade path
        for when there's no mask/product image, or the real placement engine
        couldn't find a clear spot on the detected wall face."""
        full_frame_quad = np.array(
            [[0.0, 0.0], [width - 1.0, 0.0], [width - 1.0, height - 1.0], [0.0, height - 1.0]], dtype=np.float32
        )

        wall_quad = None
        if wall_mask_gray is not None:
            wall_quad = await to_thread.run_sync(wall.detect_wall_quad, wall_mask_gray)

        if wall_quad is None:
            # No mask, or detection failed on it — degrade to "the whole
            # frame is the wall" (matches the old placeholder's fallback
            # shape, but with a real all-white mask instead of a blank one,
            # since a full-white mask correctly means "nothing occludes"
            # rather than the old blank mask's backwards "nothing is wall").
            wall_quad = full_frame_quad
            wall_mask_for_encoding = np.full((height, width), 255, dtype=np.uint8)
        else:
            wall_mask_for_encoding = wall_mask_gray
            if not wall_scene.wall_quad_is_reasonable(wall_quad):
                # detect_wall_quad's straight-line fit latched onto something
                # that isn't the wall's own flat plane (e.g. a wall mask whose
                # boundary follows a sloped vaulted ceiling or an arched
                # window cutout) — its two vertical edges come out wildly
                # different heights, which reads as a dramatic, unrealistic
                # tilt on anything hung using it as the homography basis.
                # Fall back to a safe, always-axis-aligned sub-rectangle of
                # the same mask instead of trusting that fit.
                wall_quad = await to_thread.run_sync(wall_scene.largest_rect_in_mask, wall_mask_gray)

        # Depth-grounded obstacle detection: a TV/shelf/mounted object reads
        # as "color-uniform" exactly like bare painted wall does, which is
        # why estimate_wall_clear_region's LAB-color heuristic alone can
        # place art on top of a TV — confirmed on a real room this session.
        # Metric depth sidesteps that entirely: an object standing measurably
        # off the fitted wall plane is unambiguous regardless of its color.
        # Never allowed to hard-fail the request — any failure (model load,
        # too little depth signal, a degenerate plane) just falls back to
        # the classical color-only path exactly as it worked before.
        obstacle_mask = None
        used_depth = False
        wall_width_ft = wall_height_ft = None
        if wall_mask_gray is not None:
            depth_map, depth_result = None, None
            try:
                depth_map = await to_thread.run_sync(depth.get_metric_depth, image)
                focal_px = wall_depth.WALL_FOCAL_RATIO * max(height, width)
                depth_result = await to_thread.run_sync(
                    wall_depth.wall_quad_from_depth, depth_map, wall_mask_gray, focal_px, image.shape
                )
            except Exception:
                logger.exception("wallart_depth_estimation_failed")

            if depth_result is not None:
                depth_quad, plane_info = depth_result
                containment = wall_depth.quad_mask_containment(depth_quad, wall_mask_gray)
                if wall_scene.wall_quad_is_reasonable(depth_quad) and containment >= 0.80:
                    used_depth = True
                    wall_width_ft = plane_info["width_m"] * M_TO_FT
                    wall_height_ft = plane_info["height_m"] * M_TO_FT
                    obstacle_mask = await to_thread.run_sync(
                        wall_depth.protrusion_mask,
                        depth_map,
                        wall_mask_gray,
                        plane_info["normal"],
                        plane_info["center"],
                        focal_px,
                    )

        clear_region_quad = await to_thread.run_sync(
            wall_scene.estimate_wall_clear_region, image, wall_quad, obstacle_mask
        )
        shadow_map = await to_thread.run_sync(rug_scene.extract_shadow_map, image, wall_mask_for_encoding)
        if not used_depth:
            wall_width_ft, wall_height_ft = await self._estimate_wall_dimensions(image, request.room_b64)
        art_width_ft, art_height_ft = self._art_dimensions_ft(request.product_dimensions)

        # Only used as a fallback aspect ratio below when no real
        # product_dimensions were sent — the placement box must never take
        # its shape from clear_region_quad itself (that quad's own w:h ratio
        # is an artifact of whatever obstacle-free area was found, e.g. a
        # wide/short strip, and stretches the art image if used directly).
        product_image_aspect = 1.0
        if product_image is not None and product_image.shape[0] > 0:
            product_image_aspect = product_image.shape[1] / product_image.shape[0]

        wall_xs, wall_ys = wall_quad[:, 0], wall_quad[:, 1]
        wall_px_w = max(1.0, float(wall_xs.max() - wall_xs.min()))
        wall_px_h = max(1.0, float(wall_ys.max() - wall_ys.min()))

        clear_xs, clear_ys = clear_region_quad[:, 0], clear_region_quad[:, 1]
        cx0, cx1 = float(clear_xs.min()), float(clear_xs.max())
        cy0, cy1 = float(clear_ys.min()), float(clear_ys.max())
        clear_w_px = max(1.0, cx1 - cx0)
        clear_h_px = max(1.0, cy1 - cy0)

        if art_width_ft and art_height_ft and wall_width_ft > 0 and wall_height_ft > 0:
            px_per_ft_x = wall_px_w / wall_width_ft
            px_per_ft_y = wall_px_h / wall_height_ft
            art_w_px = art_width_ft * px_per_ft_x
            art_h_px = art_height_ft * px_per_ft_y

            fitted = art_w_px <= clear_w_px and art_h_px <= clear_h_px
            if not fitted:
                scale_down = min(clear_w_px / art_w_px, clear_h_px / art_h_px, 1.0)
                art_w_px *= scale_down
                art_h_px *= scale_down
        else:
            # No real product size known — size a box that occupies a
            # reasonable fraction of the clear region while preserving the
            # art image's own aspect ratio (classic "object-fit: contain"),
            # rather than independently scaling width/height to 60% of the
            # clear region's own w/h, which stretched the art to match
            # whatever shape the clear-region detection happened to find.
            fitted = True
            if clear_w_px / product_image_aspect <= clear_h_px:
                art_w_px = clear_w_px * 0.6
                art_h_px = art_w_px / product_image_aspect
            else:
                art_h_px = clear_h_px * 0.6
                art_w_px = art_h_px * product_image_aspect

        center_x = (cx0 + cx1) / 2.0
        center_y = (cy0 + cy1) / 2.0
        placement_quad = np.array(
            [
                [center_x - art_w_px / 2.0, center_y - art_h_px / 2.0],
                [center_x + art_w_px / 2.0, center_y - art_h_px / 2.0],
                [center_x + art_w_px / 2.0, center_y + art_h_px / 2.0],
                [center_x - art_w_px / 2.0, center_y + art_h_px / 2.0],
            ],
            dtype=np.float32,
        )

        def _norm_quad(quad: np.ndarray) -> list[list[float]]:
            return [[float(x) / width, float(y) / height] for x, y in quad]

        _, wall_mask_buffer = cv2.imencode(".png", wall_mask_for_encoding)
        wall_mask_b64 = base64.b64encode(wall_mask_buffer).decode()
        shadow_map_b64 = await to_thread.run_sync(rug_scene.encode_shadow_map_b64, shadow_map)

        return WallArtVisualizerSceneResponse(
            wall_quad_norm=_norm_quad(wall_quad),
            clear_region_quad_norm=_norm_quad(clear_region_quad),
            room_width=width,
            room_height=height,
            wall_width_ft=wall_width_ft,
            wall_height_ft=wall_height_ft,
            art_width_ft=art_width_ft,
            art_height_ft=art_height_ft,
            fitted=fitted,
            used_depth=used_depth,
            wall_mask_b64=wall_mask_b64,
            shadow_map_b64=shadow_map_b64,
            placement_quad_norm=_norm_quad(placement_quad),
            placement_center_norm=[center_x / width, center_y / height],
        )

    async def _estimate_wall_dimensions(self, image: np.ndarray, room_b64: str | None) -> tuple[float, float]:
        try:
            if room_b64:
                image_b64 = room_b64.split(",")[-1]
            else:
                _, buffer = cv2.imencode(".jpg", image)
                image_b64 = base64.b64encode(buffer).decode()

            client = external_clients.get_openai_client()
            response = await client.responses.create(
                model="gpt-4.1",
                input=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "input_text", "text": WALL_DIMENSION_PROMPT},
                            {"type": "input_image", "image_url": f"data:image/jpeg;base64,{image_b64}"},
                        ],
                    }
                ],
                text={"format": WALL_DIMENSION_SCHEMA},
            )
            result = json.loads(response.output_text)
            return float(result["estimated_width_ft"]), float(result["estimated_height_ft"])
        except Exception:
            logger.exception("wall dimension estimate failed, using fallback")
            return 8.0, 8.0

    @staticmethod
    def _art_dimensions_ft(product_dimensions: dict[str, Any] | None) -> tuple[float | None, float | None]:
        if not product_dimensions:
            return None, None
        raw_width = product_dimensions.get("width")
        raw_height = product_dimensions.get("height")
        if raw_width is None or raw_height is None:
            return None, None
        try:
            width, height = float(raw_width), float(raw_height)
        except (TypeError, ValueError):
            return None, None

        # No unit is sent alongside these numbers today (frontend gap — see
        # parseWallArtDimensions in the client) — treat a value too large to
        # plausibly already be feet (no wall-art piece is ~20ft wide/tall)
        # as inches instead.
        inches_threshold = 20.0
        width_ft = width / 12.0 if width > inches_threshold else width
        height_ft = height / 12.0 if height > inches_threshold else height
        return width_ft, height_ft

    # ---- reset ----

    async def reset(self, request: ResetRoomRequest) -> ResetRoomResponse:
        room_id = request.roomId
        cache.clear_for_room(room_id)
        substring = f"_{room_id}_"
        for directory in (storage_paths.GENERATED_DIR, storage_paths.MASKS_DIR):
            if not directory.exists():
                continue
            for entry in directory.iterdir():
                if entry.is_file() and substring in entry.name:
                    entry.unlink()
        return ResetRoomResponse(success=True)

    # ---- mask-generation ----

    async def mask_generation(self, request: MaskGenerationRequest) -> MaskGenerationResponse:
        room_id = request.roomId
        hotspot_id = MASK_GENERATION_HOTSPOT_ID
        try:
            image = await to_thread.run_sync(shared.download_image, request.baseImageUrl, storage_paths.CACHE_DIR)
        except Exception:
            return MaskGenerationResponse(
                success=False, roomId=room_id, error="Could not get the base image for this URL"
            )

        path = storage_paths.mask_path(room_id, hotspot_id)
        if path.exists():
            path.unlink()

        coords = self._resolve_coords(request.coords, image.shape)
        try:
            await self._get_or_create_mask(room_id, hotspot_id, image, coords, None)
        except Exception as e:
            return MaskGenerationResponse(success=False, roomId=room_id, error=str(e))
        return MaskGenerationResponse(
            success=True, roomId=room_id, maskImageUrl=storage_paths.mask_url(room_id, hotspot_id)
        )

    # ---- generate-pdf ----

    async def generate_pdf(self, data: dict[str, Any]) -> bytes:
        return await to_thread.run_sync(pdf_generator.generate_report_pdf, data)

    # ---- rug-visualizer-scene ----

    async def rug_visualizer_scene(self, request: RugVisualizerSceneRequest) -> RugVisualizerSceneResponse:
        if request.room_b64:
            image = await to_thread.run_sync(rug_scene.b64_to_cv2, request.room_b64)
        elif request.room_url:
            image = await to_thread.run_sync(shared.download_image, request.room_url, storage_paths.CACHE_DIR)
        else:
            raise BadRequestException("Could not load room image")

        combined_mask = None
        if request.floor_mask_urls:
            mask_images = []
            for url in request.floor_mask_urls:
                mask_bytes = await external_clients.download_bytes(url)
                mask_images.append(await to_thread.run_sync(self._decode_grayscale, mask_bytes))
            combined_mask = await to_thread.run_sync(rug_scene.combine_masks, mask_images)

        floor_quad, floor_top_y = await to_thread.run_sync(rug_scene.detect_floor_quad, image, combined_mask)

        if combined_mask is not None:
            visible_floor = await to_thread.run_sync(
                cv2.resize, combined_mask, (image.shape[1], image.shape[0])
            )
        else:
            visible_floor, _ = await to_thread.run_sync(rug_scene.estimate_floor_masks, image, floor_quad)

        height, width = image.shape[0], image.shape[1]

        # Depth-grounded room/quad sizing: replaces the classical 2D quad +
        # GPT-vision size guess with a real fitted floor plane, calibrated
        # against an object of known real-world size (bed/door/chair) found
        # in the photo — see imaging/rug_depth.py's module docstring for why.
        # Never allowed to hard-fail the request — any failure (model load,
        # no plane fit, no usable reference object) just falls back to the
        # classical path exactly as it worked before.
        used_depth = False
        width_ft = length_ft = None
        try:
            depth_map = await to_thread.run_sync(depth.get_metric_depth, image)
            focal_px = wall_depth.WALL_FOCAL_RATIO * max(height, width)
            floor_frame = await to_thread.run_sync(rug_depth.fit_floor_frame, depth_map, visible_floor, focal_px)

            scale_factor = 1.0
            if floor_frame is not None:
                detections = await to_thread.run_sync(depth.detect_reference_objects, image)
                scale_factor, _ = await to_thread.run_sync(
                    rug_depth.reference_scale_factor, depth_map, focal_px, floor_frame, detections
                )

                depth_quad_result = await to_thread.run_sync(
                    rug_depth.floor_quad_from_depth,
                    depth_map,
                    visible_floor,
                    focal_px,
                    image.shape,
                    0.99,
                    floor_frame,
                    scale_factor,
                )
                if depth_quad_result is not None:
                    floor_quad, floor_top_y, _quad_w_ft, _quad_l_ft = depth_quad_result
                    used_depth = True

                dims = await to_thread.run_sync(
                    rug_depth.room_dims_from_depth, depth_map, visible_floor, focal_px, scale_factor, floor_frame
                )
                if dims is not None:
                    width_ft, length_ft = dims["width_ft"], dims["length_ft"]
        except Exception:
            logger.exception("rug_depth_estimation_failed")

        if width_ft is None or length_ft is None:
            width_ft, length_ft = await self._estimate_room_dimensions(image, request.room_b64)

        shadow_map = await to_thread.run_sync(rug_scene.extract_shadow_map, image, visible_floor)
        _, mask_buffer = cv2.imencode(".png", visible_floor)
        floor_mask_b64 = base64.b64encode(mask_buffer).decode()
        shadow_map_b64 = await to_thread.run_sync(rug_scene.encode_shadow_map_b64, shadow_map)

        return RugVisualizerSceneResponse(
            room_width=width,
            room_height=height,
            room_width_ft=width_ft,
            room_length_ft=length_ft,
            floor_top_norm=(floor_top_y / height) if height else 0.0,
            floor_quad_norm=[[float(x) / width, float(y) / height] for x, y in floor_quad],
            floor_mask_b64=floor_mask_b64,
            shadow_map_b64=shadow_map_b64,
            used_depth=used_depth,
        )

    async def _estimate_room_dimensions(self, image: np.ndarray, room_b64: str | None) -> tuple[float, float]:
        try:
            if room_b64:
                image_b64 = room_b64.split(",")[-1]
            else:
                _, buffer = cv2.imencode(".jpg", image)
                image_b64 = base64.b64encode(buffer).decode()

            client = external_clients.get_openai_client()
            response = await client.responses.create(
                model="gpt-4.1",
                input=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "input_text", "text": ROOM_DIMENSION_PROMPT},
                            {"type": "input_image", "image_url": f"data:image/jpeg;base64,{image_b64}"},
                        ],
                    }
                ],
                text={"format": ROOM_DIMENSION_SCHEMA},
            )
            result = json.loads(response.output_text)
            return float(result["estimated_width_ft"]), float(result["estimated_length_ft"])
        except Exception:
            logger.exception("room dimension estimate failed, using fallback")
            return 15.0, 15.0

    # ---- rooms (data/rooms_data.json — absent today, matches Flask parity) ----

    def _load_room_data(self) -> dict[str, Any]:
        if not ROOM_DATA_FILE.exists():
            return {}
        return json.loads(ROOM_DATA_FILE.read_text())

    async def list_rooms(self) -> RoomListResponse:
        data = self._load_room_data()
        rooms = [
            RoomListItem(roomId=room_id, imageUrl=_room_image_url(details["filename"]))
            for room_id, details in data.items()
        ]
        return RoomListResponse(rooms=rooms)

    async def get_room(self, room_id: str) -> RoomDetailResponse:
        data = self._load_room_data()
        room = data.get(room_id)
        if room is None:
            raise NotFoundException("Room")
        room = dict(room)
        room["imageUrl"] = _room_image_url(room["filename"])
        return RoomDetailResponse(**room)

    # ---- admin: cleanup / cache ----

    async def cleanup_folder(self, folder: str) -> CleanupResponse:
        target = ALLOWED_CLEANUP_FOLDERS.get(folder)
        if target is None:
            raise BadRequestException(f"Invalid folder. Allowed: {list(ALLOWED_CLEANUP_FOLDERS)}")
        if not target.exists():
            raise NotFoundException("Folder")

        deleted = 0
        errors: list[str] = []
        for entry in target.iterdir():
            if entry.is_file() or entry.is_symlink():
                try:
                    entry.unlink()
                    deleted += 1
                except OSError as e:
                    errors.append(str(e))
        return CleanupResponse(success=True, folder=folder, deleted_files=deleted, errors=errors or None)

    async def cache_stats(self) -> CacheStatsResponse:
        directory = storage_paths.CACHE_DIR
        if not directory.exists():
            return CacheStatsResponse(
                cache_dir=str(directory), total_files=0, total_size_mb=0.0, total_size_gb=0.0, files=[]
            )
        entries = [(f.name, f.stat().st_size) for f in directory.iterdir() if f.is_file()]
        total_size = sum(size for _, size in entries)
        top20 = sorted(entries, key=lambda item: item[1], reverse=True)[:20]
        return CacheStatsResponse(
            cache_dir=str(directory),
            total_files=len(entries),
            total_size_mb=round(total_size / (1024 * 1024), 2),
            total_size_gb=round(total_size / (1024**3), 4),
            files=[CacheFileEntry(name=name, size_mb=round(size / (1024 * 1024), 2)) for name, size in top20],
        )

    async def cache_clear(self) -> CacheClearResponse:
        if storage_paths.CACHE_DIR.exists():
            shutil.rmtree(storage_paths.CACHE_DIR)
        storage_paths.CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache.clear_all()
        return CacheClearResponse(success=True, message="Image cache cleared")

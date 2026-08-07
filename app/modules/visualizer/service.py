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
    floor,
    pdf_generator,
    rug_overlay,
    rug_scene,
    shared,
    wall,
)
from app.modules.visualizer.repository import UsageLogRepository
from app.modules.visualizer.schemas import (
    CacheClearResponse,
    CacheFileEntry,
    CacheStatsResponse,
    CleanupResponse,
    CurtainGenerationRequest,
    HotspotLayer,
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
                for layer in full_layer_stack:
                    current_image = await self._process_single_layer(current_image, layer, room_id)

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

    async def _process_single_layer(
        self, current_image: np.ndarray, layer: HotspotLayer, room_id: str
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
                result_image, _ = await to_thread.run_sync(
                    curtain.apply_pattern, current_image, mask, texture_image, settings_dict, product_width_cm
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
                # wall.apply_pattern reads product width from settings["productWidthCm"]
                # (computed upstream from product.width, not a raw settings key).
                wall_settings = {**settings_dict, "productWidthCm": product_width_cm}
                result_image = await to_thread.run_sync(
                    wall.apply_pattern, current_image, mask, texture_image, wall_settings, storage_paths.DEBUG_DIR
                )
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

    # ---- wallart-visualizer-scene (placeholder — no real spec exists yet) ----

    async def wallart_visualizer_scene(
        self, request: WallArtVisualizerSceneRequest
    ) -> WallArtVisualizerSceneResponse:
        width, height = 1200, 800
        if request.room_url:
            try:
                image = await to_thread.run_sync(shared.download_image, request.room_url, storage_paths.CACHE_DIR)
                height, width = image.shape[0], image.shape[1]
            except Exception:
                logger.exception("wallart_visualizer_scene: failed to load room_url, using placeholder size")

        blank_mask = np.zeros((height, width), dtype=np.uint8)
        _, mask_buffer = cv2.imencode(".png", blank_mask)
        blank_mask_b64 = base64.b64encode(mask_buffer).decode()

        full_frame_quad = [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]]
        centered_quad = [[0.35, 0.35], [0.65, 0.35], [0.65, 0.65], [0.35, 0.65]]

        return WallArtVisualizerSceneResponse(
            wall_quad_norm=full_frame_quad,
            room_width=width,
            room_height=height,
            wall_mask_b64=blank_mask_b64,
            shadow_map_b64=blank_mask_b64,
            placement_quad_norm=centered_quad,
            placement_center_norm=[0.5, 0.5],
        )

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

        shadow_map = await to_thread.run_sync(rug_scene.extract_shadow_map, image, visible_floor)
        width_ft, length_ft = await self._estimate_room_dimensions(image, request.room_b64)

        height, width = image.shape[0], image.shape[1]
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

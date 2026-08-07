import uuid

import cv2
import numpy as np
from anyio import to_thread
from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy import select

from app.common.pagination import PaginationParams, SortParams
from app.common.storage import get_storage, resolve_uploaded_file_path
from app.exceptions.http_exceptions import BadRequestException, NotFoundException
from app.modules.categories.models import ChildCategory, ParentCategory
from app.modules.room_categories.repository import RoomCategoryRepository
from app.modules.room_category_images.models import RoomCategoryImage, RoomCategoryImageHotspot
from app.modules.room_category_images.repository import (
    RoomCategoryImageHotspotRepository,
    RoomCategoryImageRepository,
)
from app.modules.room_category_images.schemas import (
    HotspotCreateRequest,
    HotspotUpdateRequest,
    LegacyHotspotItem,
    PreviewedCurtainHotspot,
    RoomCategoryImageCreateRequest,
    RoomCategoryImageUpdateRequest,
)
from app.modules.room_category_images.suppliers_repository import RoomCategoryImageSupplierRepository
from app.modules.suppliers.repository import SupplierRepository
from app.modules.visualizer import external_clients
from app.modules.visualizer import storage_paths as visualizer_storage_paths
from app.modules.visualizer.imaging import curtain_generation as curtain_generation_pipeline
from app.modules.visualizer.imaging import shared as visualizer_shared

# Subfolder under the shared uploads root — same public-serving mount the
# visualizer module already uses, just its own subfolder.
HOTSPOT_MASKS_SUBFOLDER = "room-category-hotspots"
# Generated curtain photos become normal room category images — stored
# alongside every other admin-uploaded image (same subfolder the generic
# /files/upload endpoint behind the image-upload field already uses), not a
# dedicated "generated" bucket, since nothing downstream needs to tell them
# apart from a manually uploaded photo.
GENERATED_ROOM_IMAGES_SUBFOLDER = "admin-users"


class RoomCategoryImageService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = RoomCategoryImageRepository(session)
        self.room_category_repository = RoomCategoryRepository(session)
        self.supplier_map_repository = RoomCategoryImageSupplierRepository(session)
        self.supplier_repository = SupplierRepository(session)
        self.hotspot_repository = RoomCategoryImageHotspotRepository(session)

    async def _ensure_room_category_exists(self, room_category_id: uuid.UUID) -> None:
        if await self.room_category_repository.get_by_id(room_category_id) is None:
            raise NotFoundException("Room category")

    async def list_images(
        self, room_category_id: uuid.UUID, pagination: PaginationParams, sort: SortParams
    ) -> tuple[list[RoomCategoryImage], int]:
        await self._ensure_room_category_exists(room_category_id)
        return await self.repository.get_all(
            filters={"room_category_id": room_category_id},
            sort_by=sort.sort_by,
            sort_order=sort.sort_order,
            offset=pagination.offset,
            limit=pagination.limit,
        )

    async def get_supplier_names_map(self, image_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[str]]:
        return await self.supplier_map_repository.get_supplier_names_map(image_ids)

    async def get_image(self, room_category_id: uuid.UUID, image_id: uuid.UUID) -> RoomCategoryImage:
        image = await self.repository.get_by_id(image_id)
        if image is None or image.room_category_id != room_category_id:
            raise NotFoundException("Room category image")
        return image

    async def create(
        self, room_category_id: uuid.UUID, data: RoomCategoryImageCreateRequest
    ) -> RoomCategoryImage:
        await self._ensure_room_category_exists(room_category_id)
        payload = data.model_dump()
        payload["room_category_id"] = room_category_id
        image = await self.repository.create(payload)
        return await self.get_image(room_category_id, image.id)

    async def update(
        self, room_category_id: uuid.UUID, image_id: uuid.UUID, data: RoomCategoryImageUpdateRequest
    ) -> RoomCategoryImage:
        await self.get_image(room_category_id, image_id)
        await self.repository.update(image_id, data.model_dump())
        return await self.get_image(room_category_id, image_id)

    async def delete(self, room_category_id: uuid.UUID, image_id: uuid.UUID) -> None:
        await self.get_image(room_category_id, image_id)
        await self.repository.hard_delete(image_id)

    async def get_supplier_ids(self, room_category_id: uuid.UUID, image_id: uuid.UUID) -> list[uuid.UUID]:
        await self.get_image(room_category_id, image_id)
        return await self.supplier_map_repository.get_supplier_ids(image_id)

    async def set_suppliers(
        self,
        room_category_id: uuid.UUID,
        image_id: uuid.UUID,
        supplier_ids: list[uuid.UUID],
        mapped_by: uuid.UUID,
    ) -> None:
        await self.get_image(room_category_id, image_id)

        unique_ids = list(dict.fromkeys(supplier_ids))
        existing_ids = await self.supplier_repository.get_existing_ids(unique_ids)
        unknown_ids = set(unique_ids) - existing_ids
        if unknown_ids:
            raise BadRequestException(f"Unknown supplier id(s): {', '.join(str(i) for i in unknown_ids)}")

        await self.supplier_map_repository.replace(image_id, unique_ids, mapped_by=mapped_by)

    # ---- hotspots ----

    async def get_hotspot(
        self, room_category_id: uuid.UUID, image_id: uuid.UUID, hotspot_id: uuid.UUID
    ) -> RoomCategoryImageHotspot:
        await self.get_image(room_category_id, image_id)
        hotspot = await self.hotspot_repository.get_by_id(hotspot_id)
        if hotspot is None or hotspot.room_category_image_id != image_id:
            raise NotFoundException("Hotspot")
        return hotspot

    async def list_hotspots(
        self, room_category_id: uuid.UUID, image_id: uuid.UUID
    ) -> list[RoomCategoryImageHotspot]:
        await self.get_image(room_category_id, image_id)
        items, _ = await self.hotspot_repository.get_all(
            filters={"room_category_image_id": image_id},
            sort_by="order_no",
            sort_order="asc",
            limit=None,
        )
        return items

    async def list_hotspots_for_customer(self, image_id: uuid.UUID) -> list[LegacyHotspotItem]:
        """GET /room/image-hotspots — customer-facing, no room_category_id in
        the request (the real client only ever sends the image id), and a
        different response shape than the admin's HotspotDetail (see
        LegacyHotspotItem's docstring)."""
        image = await self.repository.get_by_id(image_id)
        if image is None:
            raise NotFoundException("Room category image")
        items, _ = await self.hotspot_repository.get_all(
            filters={"room_category_image_id": image_id}, sort_by="order_no", sort_order="asc", limit=None
        )

        # Best-effort sub_category_id resolution: hotspot.type/sub_type are
        # lowercased category *names* (matching the admin hotspot editor's
        # dropdowns), not ids — resolve them against the real category tree
        # in one query rather than per-hotspot, and simply omit the field
        # (already optional on the client side) when nothing matches.
        rows = (
            await self.session.execute(
                select(ChildCategory.id, ChildCategory.name, ParentCategory.name).join(
                    ParentCategory, ParentCategory.id == ChildCategory.parent_category_id
                )
            )
        ).all()
        child_id_by_names = {
            (parent_name.strip().lower(), child_name.strip().lower()): child_id
            for child_id, child_name, parent_name in rows
        }

        return [
            LegacyHotspotItem(
                image_hotspots_id=item.id,
                label=item.label,
                type=item.type,
                mask_image=item.mask_image_url,
                x=item.x,
                y=item.y,
                sub_category_id=child_id_by_names.get((item.type, item.sub_type)) if item.sub_type else None,
            )
            for item in items
        ]

    async def create_hotspot(
        self, room_category_id: uuid.UUID, image_id: uuid.UUID, data: HotspotCreateRequest
    ) -> RoomCategoryImageHotspot:
        await self.get_image(room_category_id, image_id)
        payload = data.model_dump()
        payload["room_category_image_id"] = image_id
        hotspot = await self.hotspot_repository.create(payload)
        return await self.get_hotspot(room_category_id, image_id, hotspot.id)

    async def update_hotspot(
        self,
        room_category_id: uuid.UUID,
        image_id: uuid.UUID,
        hotspot_id: uuid.UUID,
        data: HotspotUpdateRequest,
    ) -> RoomCategoryImageHotspot:
        await self.get_hotspot(room_category_id, image_id, hotspot_id)
        await self.hotspot_repository.update(hotspot_id, data.model_dump())
        return await self.get_hotspot(room_category_id, image_id, hotspot_id)

    async def delete_hotspot(
        self, room_category_id: uuid.UUID, image_id: uuid.UUID, hotspot_id: uuid.UUID
    ) -> None:
        await self.get_hotspot(room_category_id, image_id, hotspot_id)
        await self.hotspot_repository.hard_delete(hotspot_id)

    @staticmethod
    async def _read_local_or_remote_bytes(url: str) -> bytes:
        """Every mask/photo URL this module deals with is either an
        external service's own URL (segmentation results, before we've
        re-hosted them) or one of our own root-relative storage paths —
        same "which kind is this" branch auto_detect_hotspots already
        needed for the room photo itself, now shared with preview_curtain's
        re-segmentation step, which needs it for a hotspot's mask."""
        if url.startswith(("http://", "https://")):
            return await external_clients.download_bytes(url)
        local_path = resolve_uploaded_file_path(url)
        if local_path is None or not local_path.exists():
            raise BadRequestException("Could not find the referenced image file on disk.")
        return local_path.read_bytes()

    @staticmethod
    def _mask_bbox_normalized(mask_bytes: bytes) -> tuple[float, float, float, float] | None:
        """The area a curtain was just painted into, as a 0-1 normalized
        (x_min, y_min, x_max, y_max) box — used to tell which of a
        re-segmentation's freshly detected hotspots are the new curtain's
        OWN panels vs. some other window/door elsewhere in the same photo.
        None if the mask has no foreground pixels to bound (shouldn't
        normally happen, but a mask this degenerate can't be used to filter
        anything reliably)."""
        mask = cv2.imdecode(np.frombuffer(mask_bytes, np.uint8), cv2.IMREAD_GRAYSCALE)
        if mask is None:
            return None
        ys, xs = np.where(mask > 10)
        if xs.size == 0 or ys.size == 0:
            return None
        height, width = mask.shape[:2]
        return xs.min() / width, ys.min() / height, xs.max() / width, ys.max() / height

    async def generate_hotspot_mask(
        self, room_category_id: uuid.UUID, image_id: uuid.UUID, x: float, y: float
    ) -> str:
        """Download the room category image, call SAM at the clicked point
        (reusing the exact same integration the visualizer's own
        mask-generation uses), save the resulting mask, return its URL.
        Does not create a hotspot row — generating a preview and committing
        it are deliberately separate actions."""
        image = await self.get_image(room_category_id, image_id)

        room_image = await to_thread.run_sync(
            visualizer_shared.download_image, image.image_url, visualizer_storage_paths.CACHE_DIR
        )
        if room_image is None:
            raise BadRequestException("Could not download the room category image.")

        height, width = room_image.shape[0], room_image.shape[1]
        pixel_x, pixel_y = x * width, y * height

        image_b64, was_downscaled, scale = await to_thread.run_sync(
            visualizer_shared.encode_for_sam, room_image
        )
        sam_x = pixel_x * scale if was_downscaled else pixel_x
        sam_y = pixel_y * scale if was_downscaled else pixel_y

        try:
            mask_bytes = await external_clients.call_sam_api(image_b64, [sam_x, sam_y])
        except external_clients.SamApiTimeoutError:
            raise BadRequestException("SAM API took too long to respond — please try again.")
        if mask_bytes is None:
            raise BadRequestException("SAM couldn't find a clear object at that point — try clicking a more distinct edge.")

        mask = await to_thread.run_sync(self._decode_and_resize_mask, mask_bytes, was_downscaled, width, height)
        return await get_storage().save_bytes(f"{uuid.uuid4()}.png", mask, HOTSPOT_MASKS_SUBFOLDER)

    async def preview_curtain(
        self,
        room_category_id: uuid.UUID,
        image_id: uuid.UUID,
        hotspot_id: uuid.UUID,
        curtain_style: str,
        base_image_url: str | None = None,
    ) -> tuple[str, list[PreviewedCurtainHotspot]]:
        """Reuses the exact OpenAI inpainting pipeline the customer-facing
        "Add Curtain" flow (VisualizerService.curtain_generation) already
        calls, and saves the result to our own storage — but, unlike
        commit_curtain, does NOT touch RoomCategoryImage/Hotspot. Trying a
        curtain style is exploratory: an admin who generates one, then picks
        a different style, or never finishes the QR mapping at all, must not
        have silently overwritten a shared catalog photo every other
        filter-value/customer/QR mapping already points at. `base_image_url`
        lets a second curtain on the SAME photo (e.g. two windows) build on
        top of the first one's still-uncommitted preview instead of the
        original bare-window pixels.

        A bare window is one opening, but a rendered curtain is usually 1-3
        separate fabric panels (left drape / sheer / right drape) — each
        needs its OWN product later, same as the real client. So, exactly
        like that same client's own "Add Curtain" flow, the freshly
        generated image is re-segmented via the same external service and
        the panels found INSIDE the window's own mask area are returned as
        the hotspots this curtain should actually have — the one bare-window
        hotspot the admin clicked "Add Curtain" on is never the final
        answer, only ever a placeholder for however many panels the curtain
        turns out to have."""
        window_hotspot = await self.get_hotspot(room_category_id, image_id, hotspot_id)
        window_image = await self.get_image(room_category_id, image_id)

        image_bytes, _token_usage = await curtain_generation_pipeline.run_generation_pipeline(
            base_image_url or window_image.image_url,
            [window_hotspot.mask_image_url],
            curtain_style,
            external_clients.get_openai_client(),
            visualizer_storage_paths.CACHE_DIR,
            visualizer_storage_paths.UPLOADS_DIR,
            visualizer_storage_paths.MASKS_DIR,
        )
        image_url = await get_storage().save_bytes(f"{uuid.uuid4()}.png", image_bytes, GENERATED_ROOM_IMAGES_SUBFOLDER)

        hotspots = await self._detect_curtain_panels(window_hotspot, image_bytes)
        return image_url, hotspots

    async def _detect_curtain_panels(
        self, window_hotspot: RoomCategoryImageHotspot, curtain_image_bytes: bytes
    ) -> list[PreviewedCurtainHotspot]:
        """Re-segments a just-generated curtain image (mirroring
        VisualizerService.curtain_generation's own re-segmentation step) and
        keeps only the window/door hotspots that fall inside the ORIGINAL
        window's own mask area — everything else in the photo (floor, wall,
        another window elsewhere) is a pre-existing hotspot this curtain has
        nothing to do with. Falls back to the original hotspot's own
        geometry (just relabeled) if the mask has no usable bounding box or
        nothing detected lands inside it, so a curtain never ends up with
        zero hotspots to assign a product to."""
        fallback = [
            PreviewedCurtainHotspot(
                label="curtain",
                type=window_hotspot.type,
                x=window_hotspot.x,
                y=window_hotspot.y,
                mask_image_url=window_hotspot.mask_image_url,
            )
        ]

        mask_bytes = await self._read_local_or_remote_bytes(window_hotspot.mask_image_url)
        bbox = self._mask_bbox_normalized(mask_bytes)
        if bbox is None:
            return fallback
        x_min, y_min, x_max, y_max = bbox
        pad = 0.03
        x_min, y_min, x_max, y_max = x_min - pad, y_min - pad, x_max + pad, y_max + pad

        segmentation_data = await external_clients.proxy_upload_bytes(curtain_image_bytes)
        detected = segmentation_data.get("hotspots") or []

        panels: list[PreviewedCurtainHotspot] = []
        for spot in detected:
            spot_type = (spot.get("type") or "").lower()
            mask_url = spot.get("mask_image") or spot.get("maskUrl") or spot.get("mask_url")
            x, y = spot.get("x"), spot.get("y")
            if spot_type not in ("window", "door") or not mask_url or x is None or y is None:
                continue
            if not (x_min <= x <= x_max and y_min <= y <= y_max):
                continue
            rehosted_mask_url = await get_storage().save_bytes(
                f"{uuid.uuid4()}.png", await external_clients.download_bytes(mask_url), HOTSPOT_MASKS_SUBFOLDER
            )
            panels.append(
                PreviewedCurtainHotspot(label="curtain", type=spot_type, x=x, y=y, mask_image_url=rehosted_mask_url)
            )

        return panels or fallback

    async def auto_detect_hotspots(
        self, room_category_id: uuid.UUID, image_id: uuid.UUID
    ) -> list[RoomCategoryImageHotspot]:
        """Calls the exact same external segmentation service the
        customer-facing upload flow uses (VisualizerService.upload ->
        external_clients.proxy_upload) against an already-uploaded room
        category image, and creates a real Hotspot row from each detected
        item — label/type/x/y straight from that response. The mask it
        returns is re-hosted on our own storage (matching every other
        hotspot's mask) rather than left depending on an external URL
        forever. Purely additive: existing hotspots are untouched, and the
        manual "click to add" flow still covers anything this misses or
        gets wrong."""
        image = await self.get_image(room_category_id, image_id)
        image_bytes = await self._read_local_or_remote_bytes(image.image_url)

        segmentation_data = await external_clients.proxy_upload_bytes(image_bytes)
        detected = segmentation_data.get("hotspots") or []
        if not detected:
            raise BadRequestException("No hotspots were detected on this photo.")

        existing = await self.list_hotspots(room_category_id, image_id)
        created: list[RoomCategoryImageHotspot] = []
        for offset, spot in enumerate(detected):
            mask_url = spot.get("mask_image") or spot.get("maskUrl") or spot.get("mask_url")
            spot_type = spot.get("type")
            if not mask_url or not spot_type:
                continue
            mask_bytes = await external_clients.download_bytes(mask_url)
            mask_image_url = await get_storage().save_bytes(
                f"{uuid.uuid4()}.png", mask_bytes, HOTSPOT_MASKS_SUBFOLDER
            )
            hotspot = await self.hotspot_repository.create(
                {
                    "room_category_image_id": image_id,
                    "label": spot.get("label") or spot_type,
                    "type": spot_type,
                    "sub_type": None,
                    "mask_image_url": mask_image_url,
                    "x": spot.get("x", 0.5),
                    "y": spot.get("y", 0.5),
                    "order_no": len(existing) + offset,
                }
            )
            created.append(hotspot)

        if not created:
            raise BadRequestException("The detected hotspots were missing a type or mask and could not be saved.")
        return created

    @staticmethod
    def _decode_and_resize_mask(mask_bytes: bytes, was_downscaled: bool, width: int, height: int) -> bytes:
        mask = cv2.imdecode(np.frombuffer(mask_bytes, np.uint8), cv2.IMREAD_GRAYSCALE)
        if was_downscaled:
            mask = cv2.resize(mask, (width, height), interpolation=cv2.INTER_LINEAR)
        _, buffer = cv2.imencode(".png", mask)
        return buffer.tobytes()

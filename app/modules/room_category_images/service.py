import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.common.pagination import PaginationParams, SortParams
from app.exceptions.http_exceptions import BadRequestException, NotFoundException
from app.modules.room_categories.repository import RoomCategoryRepository
from app.modules.room_category_images.models import RoomCategoryImage
from app.modules.room_category_images.repository import RoomCategoryImageRepository
from app.modules.room_category_images.schemas import (
    RoomCategoryImageCreateRequest,
    RoomCategoryImageUpdateRequest,
)
from app.modules.room_category_images.suppliers_repository import RoomCategoryImageSupplierRepository
from app.modules.suppliers.repository import SupplierRepository


class RoomCategoryImageService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = RoomCategoryImageRepository(session)
        self.room_category_repository = RoomCategoryRepository(session)
        self.supplier_map_repository = RoomCategoryImageSupplierRepository(session)
        self.supplier_repository = SupplierRepository(session)

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

    async def mark_uploaded_to_cdn(
        self, room_category_id: uuid.UUID, image_id: uuid.UUID
    ) -> RoomCategoryImage:
        """Flips the CDN flag only — no real AWS/CDN push wired up yet, deliberately
        deferred. Keeps the frontend's "Upload to CDN" action real rather than a
        dead facade while that infrastructure work is out of scope."""
        await self.get_image(room_category_id, image_id)
        await self.repository.update(image_id, {"is_uploaded_to_cdn": True})
        return await self.get_image(room_category_id, image_id)

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

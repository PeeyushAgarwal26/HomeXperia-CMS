import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.common.pagination import PaginationParams, SortParams
from app.exceptions.http_exceptions import ConflictException, NotFoundException
from app.modules.room_categories.models import RoomCategory
from app.modules.room_categories.repository import RoomCategoryRepository
from app.modules.room_categories.schemas import (
    RoomCategoryCreateRequest,
    RoomCategoryCustomerImage,
    RoomCategoryCustomerItem,
    RoomCategoryUpdateRequest,
)
from app.modules.room_category_images.repository import RoomCategoryImageRepository


class RoomCategoryService:
    """Add/Edit + Activate/Deactivate only — no Delete, matching the reference UI."""

    def __init__(self, session: AsyncSession) -> None:
        self.repository = RoomCategoryRepository(session)
        self.image_repository = RoomCategoryImageRepository(session)

    async def list_room_categories(
        self, pagination: PaginationParams, sort: SortParams, search: str | None
    ) -> tuple[list[RoomCategory], int]:
        return await self.repository.get_all(
            search=search,
            search_fields=["name"],
            sort_by=sort.sort_by,
            sort_order=sort.sort_order,
            offset=pagination.offset,
            limit=pagination.limit,
        )

    async def list_active_for_customer(self) -> list[RoomCategoryCustomerItem]:
        items, _ = await self.repository.get_all(
            filters={"is_active": True}, limit=None, sort_by="order_no", sort_order="asc"
        )
        result = []
        for item in items:
            images, _ = await self.image_repository.get_all(
                filters={"room_category_id": item.id}, limit=None, sort_by="order_no", sort_order="asc"
            )
            result.append(
                RoomCategoryCustomerItem(
                    room_category_id=item.id,
                    name=item.name,
                    icon=item.icon_url,
                    room_category_images=[
                        RoomCategoryCustomerImage(room_category_image_id=img.id, image_url=img.image_url)
                        for img in images
                    ],
                )
            )
        return result

    async def get_room_category(self, room_category_id: uuid.UUID) -> RoomCategory:
        item = await self.repository.get_by_id(room_category_id)
        if item is None:
            raise NotFoundException("Room category")
        return item

    async def create(self, data: RoomCategoryCreateRequest) -> RoomCategory:
        if await self.repository.name_taken(data.name):
            raise ConflictException("This room category name is already in use.")
        item = await self.repository.create(data.model_dump())
        return await self.get_room_category(item.id)

    async def update(self, room_category_id: uuid.UUID, data: RoomCategoryUpdateRequest) -> RoomCategory:
        await self.get_room_category(room_category_id)
        if await self.repository.name_taken(data.name, exclude_id=room_category_id):
            raise ConflictException("This room category name is already in use.")
        await self.repository.update(room_category_id, data.model_dump())
        return await self.get_room_category(room_category_id)

    async def set_status(self, room_category_id: uuid.UUID, is_active: bool) -> RoomCategory:
        await self.get_room_category(room_category_id)
        await self.repository.update(room_category_id, {"is_active": is_active})
        return await self.get_room_category(room_category_id)

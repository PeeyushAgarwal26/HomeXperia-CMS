import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.common.pagination import PaginationParams, SortParams
from app.exceptions.http_exceptions import ConflictException, NotFoundException
from app.modules.customers.models import Customer
from app.modules.customers.suppliers_repository import CustomerSupplierRepository
from app.modules.room_categories.models import RoomCategory
from app.modules.room_categories.repository import RoomCategoryRepository
from app.modules.room_categories.schemas import (
    RoomCategoryCreateRequest,
    RoomCategoryCustomerImage,
    RoomCategoryCustomerItem,
    RoomCategoryUpdateRequest,
)
from app.modules.room_category_images.repository import RoomCategoryImageRepository
from app.modules.room_category_images.suppliers_repository import RoomCategoryImageSupplierRepository


class RoomCategoryService:
    """Add/Edit + Activate/Deactivate only — no Delete, matching the reference UI."""

    def __init__(self, session: AsyncSession) -> None:
        self.repository = RoomCategoryRepository(session)
        self.image_repository = RoomCategoryImageRepository(session)
        self.image_supplier_repository = RoomCategoryImageSupplierRepository(session)
        self.customer_supplier_repository = CustomerSupplierRepository(session)

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

    async def list_active_for_customer(self, customer: Customer | None) -> list[RoomCategoryCustomerItem]:
        """Demo-room images are scoped to the logged-in customer's own
        supplier(s) (Map Suppliers on the image) — an image mapped to no
        supplier at all is excluded for everyone, and an anonymous request
        (no customer) sees none, same as a customer with no suppliers.
        "Own supplier(s)" = both the customer_suppliers ("buys from") map
        and the customer's own linked_supplier_id — a supplier's own linked
        customer account should see that supplier's images even on seed/
        legacy data where customer_suppliers was never populated for the
        link itself."""
        items, _ = await self.repository.get_all(
            filters={"is_active": True}, limit=None, sort_by="order_no", sort_order="asc"
        )
        customer_supplier_ids: list[uuid.UUID] = []
        if customer is not None:
            customer_supplier_ids = list(await self.customer_supplier_repository.get_supplier_ids(customer.id))
            if customer.linked_supplier_id is not None:
                customer_supplier_ids.append(customer.linked_supplier_id)
        result = []
        for item in items:
            images, _ = await self.image_repository.get_all(
                filters={"room_category_id": item.id}, limit=None, sort_by="order_no", sort_order="asc"
            )
            allowed_image_ids = await self.image_supplier_repository.get_image_ids_mapped_to_any(
                [img.id for img in images], customer_supplier_ids
            )
            result.append(
                RoomCategoryCustomerItem(
                    room_category_id=item.id,
                    name=item.name,
                    icon=item.icon_url,
                    room_category_images=[
                        RoomCategoryCustomerImage(room_category_image_id=img.id, image_url=img.image_url)
                        for img in images
                        if img.id in allowed_image_ids
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

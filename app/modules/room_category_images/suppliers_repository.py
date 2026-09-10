import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.room_category_images.models import RoomCategoryImageSupplier
from app.modules.suppliers.models import Supplier


class RoomCategoryImageSupplierRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_supplier_ids(self, room_category_image_id: uuid.UUID) -> list[uuid.UUID]:
        stmt = select(RoomCategoryImageSupplier.supplier_id).where(
            RoomCategoryImageSupplier.room_category_image_id == room_category_image_id
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_image_ids_mapped_to_any(
        self, room_category_image_ids: list[uuid.UUID], supplier_ids: list[uuid.UUID]
    ) -> set[uuid.UUID]:
        """Which of these images has at least one of these suppliers mapped
        to it — used to scope a customer's demo-room images down to only
        the ones their own supplier(s) actually offer. An image with no
        Map Suppliers rows at all matches nothing here (by design — see
        RoomCategoryService.list_active_for_customer)."""
        if not room_category_image_ids or not supplier_ids:
            return set()
        stmt = (
            select(RoomCategoryImageSupplier.room_category_image_id)
            .where(
                RoomCategoryImageSupplier.room_category_image_id.in_(room_category_image_ids),
                RoomCategoryImageSupplier.supplier_id.in_(supplier_ids),
            )
            .distinct()
        )
        result = await self.session.execute(stmt)
        return set(result.scalars().all())

    async def get_supplier_names_map(
        self, room_category_image_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, list[str]]:
        if not room_category_image_ids:
            return {}
        stmt = (
            select(RoomCategoryImageSupplier.room_category_image_id, Supplier.name)
            .join(Supplier, Supplier.id == RoomCategoryImageSupplier.supplier_id)
            .where(RoomCategoryImageSupplier.room_category_image_id.in_(room_category_image_ids))
            .order_by(Supplier.name)
        )
        result = await self.session.execute(stmt)
        names_by_image: dict[uuid.UUID, list[str]] = {}
        for image_id, supplier_name in result.all():
            names_by_image.setdefault(image_id, []).append(supplier_name)
        return names_by_image

    async def replace(
        self, room_category_image_id: uuid.UUID, supplier_ids: list[uuid.UUID], mapped_by: uuid.UUID
    ) -> None:
        await self.session.execute(
            delete(RoomCategoryImageSupplier).where(
                RoomCategoryImageSupplier.room_category_image_id == room_category_image_id
            )
        )
        for supplier_id in supplier_ids:
            self.session.add(
                RoomCategoryImageSupplier(
                    room_category_image_id=room_category_image_id,
                    supplier_id=supplier_id,
                    mapped_by=mapped_by,
                )
            )
        await self.session.flush()

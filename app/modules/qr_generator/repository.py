import uuid

from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.base_repository import BaseRepository
from app.modules.customers.models import Customer
from app.modules.qr_generator.models import QrCatalogueEntry, QrCatalogueEntryHotspot, SavedQrCode
from app.modules.room_categories.models import RoomCategory
from app.modules.room_category_images.models import RoomCategoryImage


class QrCatalogueEntryRepository(BaseRepository[QrCatalogueEntry]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(QrCatalogueEntry, session)

    async def list_by_customer(self, customer_id: uuid.UUID) -> list[QrCatalogueEntry]:
        items, _ = await self.get_all(filters={"customer_id": customer_id}, sort_by="created_at", limit=None)
        return items

    async def get_by_customer_and_filter_value(
        self, customer_id: uuid.UUID, filter_value: str
    ) -> QrCatalogueEntry | None:
        stmt = self._base_select().where(
            QrCatalogueEntry.customer_id == customer_id, QrCatalogueEntry.filter_value == filter_value
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list_room_images(self) -> list[tuple[RoomCategoryImage, str]]:
        stmt = (
            select(RoomCategoryImage, RoomCategory.name)
            .join(RoomCategory, RoomCategory.id == RoomCategoryImage.room_category_id)
            .order_by(RoomCategory.name, RoomCategoryImage.order_no)
        )
        rows = (await self.session.execute(stmt)).all()
        return [(row[0], row[1]) for row in rows]

    async def get_hotspot_products(self, entry_id: uuid.UUID) -> list[QrCatalogueEntryHotspot]:
        stmt = select(QrCatalogueEntryHotspot).where(QrCatalogueEntryHotspot.qr_catalogue_entry_id == entry_id)
        return list((await self.session.execute(stmt)).scalars().all())

    async def set_hotspot_products(self, entry_id: uuid.UUID, assignments: list[dict]) -> None:
        """Each dict has product_id plus EITHER hotspot_id (a real, shared
        room hotspot) OR inline_label/inline_type/inline_x/inline_y/
        inline_mask_image_url (a curtain panel scoped to this mapping only —
        see QrCatalogueEntryHotspot's docstring). Full delete-then-insert,
        same replace-on-save approach the rest of this codebase's junction
        tables use (e.g. RoomCategoryImageSupplier)."""
        await self.session.execute(
            delete(QrCatalogueEntryHotspot).where(QrCatalogueEntryHotspot.qr_catalogue_entry_id == entry_id)
        )
        self.session.add_all(
            [QrCatalogueEntryHotspot(qr_catalogue_entry_id=entry_id, **assignment) for assignment in assignments]
        )
        await self.session.flush()


class SavedQrCodeRepository(BaseRepository[SavedQrCode]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(SavedQrCode, session)

    async def list_with_search(
        self, search: str | None, offset: int, limit: int | None
    ) -> tuple[list[SavedQrCode], int]:
        """Search spans both the entry's own filter_values AND the
        customer's name/code — the generic BaseRepository.get_all only
        searches columns on this table itself, but "which customer" is at
        least as likely a search term here as "which filter value"."""
        stmt = select(SavedQrCode).join(Customer, Customer.id == SavedQrCode.customer_id)
        if search:
            pattern = f"%{search}%"
            stmt = stmt.where(
                or_(
                    SavedQrCode.filter_values.ilike(pattern),
                    Customer.name.ilike(pattern),
                    Customer.customer_code.ilike(pattern),
                )
            )

        total = await self.session.scalar(select(func.count()).select_from(stmt.subquery()))

        stmt = stmt.order_by(SavedQrCode.created_at.desc()).offset(offset)
        if limit is not None:
            stmt = stmt.limit(limit)

        result = await self.session.execute(stmt)
        return list(result.scalars().all()), total or 0

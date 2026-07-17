import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.base_repository import BaseRepository
from app.modules.suppliers.models import Supplier


class SupplierRepository(BaseRepository[Supplier]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Supplier, session)

    async def username_taken(self, username: str, exclude_id: uuid.UUID | None = None) -> bool:
        stmt = self._base_select().where(Supplier.username == username)
        if exclude_id is not None:
            stmt = stmt.where(Supplier.id != exclude_id)
        result = await self.session.execute(stmt.limit(1))
        return result.first() is not None

    async def phone_number_taken(self, phone_number: str, exclude_id: uuid.UUID | None = None) -> bool:
        stmt = self._base_select().where(Supplier.phone_number == phone_number)
        if exclude_id is not None:
            stmt = stmt.where(Supplier.id != exclude_id)
        result = await self.session.execute(stmt.limit(1))
        return result.first() is not None

    async def get_existing_ids(self, supplier_ids: list[uuid.UUID]) -> set[uuid.UUID]:
        if not supplier_ids:
            return set()
        stmt = select(Supplier.id).where(Supplier.id.in_(supplier_ids), Supplier.deleted_at.is_(None))
        result = await self.session.execute(stmt)
        return set(result.scalars().all())

    async def count_active(self) -> int:
        stmt = select(func.count()).select_from(Supplier).where(
            Supplier.deleted_at.is_(None), Supplier.is_active.is_(True)
        )
        return (await self.session.scalar(stmt)) or 0

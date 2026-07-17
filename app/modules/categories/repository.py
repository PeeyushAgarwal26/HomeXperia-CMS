import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.base_repository import BaseRepository
from app.modules.categories.models import ChildCategory, ParentCategory


class ParentCategoryRepository(BaseRepository[ParentCategory]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(ParentCategory, session)

    async def name_taken(self, name: str, exclude_id: uuid.UUID | None = None) -> bool:
        stmt = self._base_select().where(ParentCategory.name == name)
        if exclude_id is not None:
            stmt = stmt.where(ParentCategory.id != exclude_id)
        result = await self.session.execute(stmt.limit(1))
        return result.first() is not None


class ChildCategoryRepository(BaseRepository[ChildCategory]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(ChildCategory, session)

    async def name_taken(
        self, parent_category_id: uuid.UUID, name: str, exclude_id: uuid.UUID | None = None
    ) -> bool:
        stmt = self._base_select().where(
            ChildCategory.parent_category_id == parent_category_id, ChildCategory.name == name
        )
        if exclude_id is not None:
            stmt = stmt.where(ChildCategory.id != exclude_id)
        result = await self.session.execute(stmt.limit(1))
        return result.first() is not None


class CategoryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_parents(self) -> list[ParentCategory]:
        stmt = (
            select(ParentCategory)
            .where(ParentCategory.is_active.is_(True), ParentCategory.deleted_at.is_(None))
            .order_by(ParentCategory.sort_order)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_children(self) -> list[ChildCategory]:
        stmt = select(ChildCategory).where(ChildCategory.is_active.is_(True)).order_by(
            ChildCategory.sort_order
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_ids_for_ids(self, child_category_ids: list[uuid.UUID]) -> set[uuid.UUID]:
        if not child_category_ids:
            return set()
        stmt = select(ChildCategory.id).where(
            ChildCategory.id.in_(child_category_ids), ChildCategory.is_active.is_(True)
        )
        result = await self.session.execute(stmt)
        return set(result.scalars().all())

    async def get_names_for_ids(self, child_category_ids: list[uuid.UUID]) -> dict[uuid.UUID, str]:
        if not child_category_ids:
            return {}
        stmt = select(ChildCategory.id, ChildCategory.name).where(
            ChildCategory.id.in_(child_category_ids)
        )
        result = await self.session.execute(stmt)
        return dict(result.all())

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.categories.models import ChildCategory, ParentCategory


class CategoryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_parents(self) -> list[ParentCategory]:
        stmt = select(ParentCategory).where(ParentCategory.is_active.is_(True)).order_by(
            ParentCategory.sort_order
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

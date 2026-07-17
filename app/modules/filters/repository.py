import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.base_repository import BaseRepository
from app.modules.filters.models import Filter, FilterValue


class FilterRepository(BaseRepository[Filter]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Filter, session)

    async def name_taken(self, name: str, exclude_id: uuid.UUID | None = None) -> bool:
        stmt = self._base_select().where(Filter.name == name)
        if exclude_id is not None:
            stmt = stmt.where(Filter.id != exclude_id)
        result = await self.session.execute(stmt.limit(1))
        return result.first() is not None


class FilterValueRepository(BaseRepository[FilterValue]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(FilterValue, session)

    async def list_applicable(
        self, child_category_id: uuid.UUID, supplier_id: uuid.UUID
    ) -> list[FilterValue]:
        """Every active FilterValue scoped to this exact Child Category + Supplier pair —
        this is what drives Product's dynamic "Product Filters" section: which Filters
        even show up, and what options each one offers, depends entirely on this."""
        stmt = (
            self._base_select()
            .where(
                FilterValue.child_category_id == child_category_id,
                FilterValue.supplier_id == supplier_id,
                FilterValue.is_active.is_(True),
            )
            .order_by(FilterValue.value)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def value_taken(
        self,
        filter_id: uuid.UUID,
        child_category_id: uuid.UUID,
        supplier_id: uuid.UUID,
        value: str,
        exclude_id: uuid.UUID | None = None,
    ) -> bool:
        stmt = self._base_select().where(
            FilterValue.filter_id == filter_id,
            FilterValue.child_category_id == child_category_id,
            FilterValue.supplier_id == supplier_id,
            func.lower(FilterValue.value) == value.strip().lower(),
        )
        if exclude_id is not None:
            stmt = stmt.where(FilterValue.id != exclude_id)
        result = await self.session.execute(stmt.limit(1))
        return result.first() is not None

    async def list_distinct_filters_for_supplier(self, supplier_id: uuid.UUID) -> list[Filter]:
        """Every Filter this supplier has at least one value for, in any Child Category —
        used to build the bulk-upload template's filter columns, so a newly added Filter
        appears automatically the next time the template is downloaded."""
        stmt = (
            select(Filter)
            .join(FilterValue, FilterValue.filter_id == Filter.id)
            .where(
                FilterValue.supplier_id == supplier_id,
                FilterValue.is_active.is_(True),
                Filter.deleted_at.is_(None),
                Filter.is_active.is_(True),
            )
            .distinct()
            .order_by(Filter.name)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

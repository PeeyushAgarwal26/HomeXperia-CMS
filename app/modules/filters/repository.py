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

    async def get_by_name_ci(self, name: str) -> Filter | None:
        stmt = self._base_select().where(func.lower(Filter.name) == name.strip().lower())
        return (await self.session.execute(stmt.limit(1))).scalar_one_or_none()


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

    async def list_applicable_for_category(
        self, child_category_id: uuid.UUID, visible_supplier_ids: list[uuid.UUID] | None = None
    ) -> list[FilterValue]:
        """Same as list_applicable but across a customer's own visible
        suppliers rather than one specific supplier. visible_supplier_ids=None
        means unscoped (anonymous/Shopify-embed path); a real customer always
        passes a list, matching list_for_customer's scoping exactly — a filter
        value belonging to a supplier the customer can't see would otherwise
        dead-end into an empty product result when applied."""
        stmt = self._base_select().where(
            FilterValue.child_category_id == child_category_id, FilterValue.is_active.is_(True)
        )
        if visible_supplier_ids is not None:
            stmt = stmt.where(FilterValue.supplier_id.in_(visible_supplier_ids))
        stmt = stmt.order_by(FilterValue.value)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_value_ci(
        self, filter_id: uuid.UUID, child_category_id: uuid.UUID, supplier_id: uuid.UUID, value: str
    ) -> FilterValue | None:
        stmt = self._base_select().where(
            FilterValue.filter_id == filter_id,
            FilterValue.child_category_id == child_category_id,
            FilterValue.supplier_id == supplier_id,
            func.lower(FilterValue.value) == value.strip().lower(),
        )
        return (await self.session.execute(stmt.limit(1))).scalar_one_or_none()

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

    async def list_values_for_suppliers(self, filter_id: uuid.UUID, supplier_ids: list[uuid.UUID]) -> list[str]:
        """Distinct active values under one Filter across a set of suppliers,
        regardless of Child Category — used by the QR admin tool to surface a
        customer's already-existing "Catalogue Name" values (customers relate
        to FilterValue only indirectly, via their mapped suppliers) before any
        QR mapping has been saved for them."""
        if not supplier_ids:
            return []
        stmt = (
            select(FilterValue.value)
            .where(
                FilterValue.filter_id == filter_id,
                FilterValue.supplier_id.in_(supplier_ids),
                FilterValue.is_active.is_(True),
            )
            .distinct()
            .order_by(FilterValue.value)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

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

import uuid

from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.base_repository import BaseRepository
from app.modules.filters.models import Filter, FilterValue
from app.modules.products.models import Product, ProductFilterValue

CATALOGUE_NAME_FILTER = "catalogue name"


class ProductRepository(BaseRepository[Product]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Product, session)

    async def get_by_bar_code(self, bar_code: str) -> Product | None:
        """Bar codes are globally unique (see the model's ux_products_bar_code index),
        not just within one supplier's catalog — so this is the one lookup both the
        create/edit form's duplicate check and bulk upload's "is this the same
        product" natural key need. Bulk upload additionally has to check the result's
        own supplier_id itself (see product_uploads/service.py) to tell "re-uploading
        my own product, update it" apart from "this code is already someone else's"."""
        stmt = self._base_select().where(Product.bar_code == bar_code)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_for_customer(
        self,
        child_category_id: uuid.UUID | None,
        search: str | None,
        min_price: float | None,
        max_price: float | None,
        filter_value_ids: list[uuid.UUID],
        offset: int,
        limit: int | None,
        visible_supplier_ids: list[uuid.UUID] | None = None,
    ) -> tuple[list[Product], int]:
        """Active products only. visible_supplier_ids=None means unscoped (the
        anonymous/Shopify-embed path — no customer identity to scope by); a
        real customer always passes a list (their mapped suppliers plus their
        own, if they're a linked supplier identity) — an empty list correctly
        yields zero products, not everything. Each selected filter_value_id
        narrows the result further (a product must have ALL of them assigned,
        not any)."""
        stmt = self._base_select().where(Product.is_active.is_(True))
        if visible_supplier_ids is not None:
            stmt = stmt.where(Product.supplier_id.in_(visible_supplier_ids))
        if child_category_id is not None:
            stmt = stmt.where(Product.child_category_id == child_category_id)
        if search:
            stmt = stmt.where(
                or_(
                    Product.catalog_name.ilike(f"%{search}%"),
                    Product.design_no.ilike(f"%{search}%"),
                    Product.bar_code.ilike(f"%{search}%"),
                )
            )
        if min_price is not None:
            stmt = stmt.where(Product.rate >= min_price)
        if max_price is not None:
            stmt = stmt.where(Product.rate <= max_price)
        for filter_value_id in filter_value_ids:
            stmt = stmt.where(
                Product.id.in_(
                    select(ProductFilterValue.product_id).where(
                        ProductFilterValue.filter_value_id == filter_value_id
                    )
                )
            )

        total = await self.session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        stmt = stmt.order_by(Product.order_no.asc(), Product.created_at.desc()).offset(offset)
        if limit is not None:
            stmt = stmt.limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all()), total


class ProductFilterValueRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_filter_value_ids(self, product_id: uuid.UUID) -> list[uuid.UUID]:
        stmt = select(ProductFilterValue.filter_value_id).where(ProductFilterValue.product_id == product_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count_products_using(self, filter_value_id: uuid.UUID) -> int:
        stmt = (
            select(func.count(func.distinct(ProductFilterValue.product_id)))
            .join(Product, Product.id == ProductFilterValue.product_id)
            .where(ProductFilterValue.filter_value_id == filter_value_id, Product.deleted_at.is_(None))
        )
        return (await self.session.scalar(stmt)) or 0

    async def get_catalogue_names_map(self, product_ids: list[uuid.UUID]) -> dict[uuid.UUID, str]:
        """Batch lookup of each product's "Catalogue Name" Filter Value (a real,
        supplier-curated attribute), used to display it in place of the free-text
        Product.catalog_name column on the admin/supplier list pages."""
        if not product_ids:
            return {}
        stmt = (
            select(ProductFilterValue.product_id, FilterValue.value)
            .join(FilterValue, FilterValue.id == ProductFilterValue.filter_value_id)
            .join(Filter, Filter.id == FilterValue.filter_id)
            .where(
                ProductFilterValue.product_id.in_(product_ids),
                func.lower(Filter.name) == CATALOGUE_NAME_FILTER,
            )
        )
        result = await self.session.execute(stmt)
        return {row.product_id: row.value for row in result}

    async def replace(self, product_id: uuid.UUID, filter_value_ids: list[uuid.UUID]) -> None:
        await self.session.execute(
            delete(ProductFilterValue).where(ProductFilterValue.product_id == product_id)
        )
        for filter_value_id in dict.fromkeys(filter_value_ids):
            self.session.add(ProductFilterValue(product_id=product_id, filter_value_id=filter_value_id))
        await self.session.flush()

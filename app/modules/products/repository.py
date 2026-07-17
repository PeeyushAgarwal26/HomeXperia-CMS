import uuid

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.base_repository import BaseRepository
from app.modules.products.models import Product, ProductFilterValue


class ProductRepository(BaseRepository[Product]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Product, session)

    async def get_by_supplier_and_bar_code(self, supplier_id: uuid.UUID, bar_code: str) -> Product | None:
        """Bulk upload's natural key for "is this the same product" — lets a re-uploaded
        sheet update rather than duplicate a product it already created."""
        stmt = self._base_select().where(Product.supplier_id == supplier_id, Product.bar_code == bar_code)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()


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

    async def replace(self, product_id: uuid.UUID, filter_value_ids: list[uuid.UUID]) -> None:
        await self.session.execute(
            delete(ProductFilterValue).where(ProductFilterValue.product_id == product_id)
        )
        for filter_value_id in dict.fromkeys(filter_value_ids):
            self.session.add(ProductFilterValue(product_id=product_id, filter_value_id=filter_value_id))
        await self.session.flush()

import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.categories.models import ChildCategory
from app.modules.suppliers.models import SupplierChildCategory


class SupplierCategoryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_child_category_ids(self, supplier_id: uuid.UUID) -> list[uuid.UUID]:
        stmt = select(SupplierChildCategory.child_category_id).where(
            SupplierChildCategory.supplier_id == supplier_id
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_category_names_map(self, supplier_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[str]]:
        if not supplier_ids:
            return {}
        stmt = (
            select(SupplierChildCategory.supplier_id, ChildCategory.name)
            .join(ChildCategory, ChildCategory.id == SupplierChildCategory.child_category_id)
            .where(SupplierChildCategory.supplier_id.in_(supplier_ids))
            .order_by(ChildCategory.name)
        )
        result = await self.session.execute(stmt)
        names_by_supplier: dict[uuid.UUID, list[str]] = {}
        for supplier_id, category_name in result.all():
            names_by_supplier.setdefault(supplier_id, []).append(category_name)
        return names_by_supplier

    async def replace(
        self, supplier_id: uuid.UUID, child_category_ids: list[uuid.UUID], granted_by: uuid.UUID
    ) -> None:
        await self.session.execute(
            delete(SupplierChildCategory).where(SupplierChildCategory.supplier_id == supplier_id)
        )
        for child_category_id in child_category_ids:
            self.session.add(
                SupplierChildCategory(
                    supplier_id=supplier_id, child_category_id=child_category_id, granted_by=granted_by
                )
            )
        await self.session.flush()

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.customers.models import SupplierCustomerTheme


class SupplierCustomerThemeRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_for_customer(self, customer_id: uuid.UUID) -> list[SupplierCustomerTheme]:
        stmt = select(SupplierCustomerTheme).where(SupplierCustomerTheme.customer_id == customer_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get(self, supplier_id: uuid.UUID, customer_id: uuid.UUID) -> SupplierCustomerTheme | None:
        stmt = select(SupplierCustomerTheme).where(
            SupplierCustomerTheme.supplier_id == supplier_id,
            SupplierCustomerTheme.customer_id == customer_id,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def upsert(
        self,
        supplier_id: uuid.UUID,
        customer_id: uuid.UUID,
        primary_color: str | None,
        secondary_color: str | None,
    ) -> SupplierCustomerTheme:
        existing = await self.get(supplier_id, customer_id)
        if existing is not None:
            existing.primary_color = primary_color
            existing.secondary_color = secondary_color
            await self.session.flush()
            return existing
        theme = SupplierCustomerTheme(
            supplier_id=supplier_id,
            customer_id=customer_id,
            primary_color=primary_color,
            secondary_color=secondary_color,
        )
        self.session.add(theme)
        await self.session.flush()
        return theme

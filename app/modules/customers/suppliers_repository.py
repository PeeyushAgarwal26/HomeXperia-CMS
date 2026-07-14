import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.customers.models import Customer, CustomerSupplier
from app.modules.suppliers.models import Supplier


class CustomerSupplierRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_all_mappings(self) -> list[tuple[str, str, str]]:
        """One row per (customer, supplier) link — powers "Download Supplier's
        Mapping", a distinct report from the regular customer list export."""
        stmt = (
            select(Customer.name, Customer.customer_code, Supplier.name)
            .join(CustomerSupplier, CustomerSupplier.customer_id == Customer.id)
            .join(Supplier, Supplier.id == CustomerSupplier.supplier_id)
            .where(Customer.deleted_at.is_(None))
            .order_by(Customer.name, Supplier.name)
        )
        result = await self.session.execute(stmt)
        return list(result.all())

    async def get_supplier_ids(self, customer_id: uuid.UUID) -> list[uuid.UUID]:
        stmt = select(CustomerSupplier.supplier_id).where(CustomerSupplier.customer_id == customer_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_customer_ids(self, supplier_id: uuid.UUID) -> list[uuid.UUID]:
        stmt = select(CustomerSupplier.customer_id).where(CustomerSupplier.supplier_id == supplier_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_supplier_names_map(self, customer_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[str]]:
        if not customer_ids:
            return {}
        stmt = (
            select(CustomerSupplier.customer_id, Supplier.name)
            .join(Supplier, Supplier.id == CustomerSupplier.supplier_id)
            .where(CustomerSupplier.customer_id.in_(customer_ids))
            .order_by(Supplier.name)
        )
        result = await self.session.execute(stmt)
        names_by_customer: dict[uuid.UUID, list[str]] = {}
        for customer_id, supplier_name in result.all():
            names_by_customer.setdefault(customer_id, []).append(supplier_name)
        return names_by_customer

    async def replace(
        self, customer_id: uuid.UUID, supplier_ids: list[uuid.UUID], mapped_by: uuid.UUID
    ) -> None:
        await self.session.execute(
            delete(CustomerSupplier).where(CustomerSupplier.customer_id == customer_id)
        )
        for supplier_id in supplier_ids:
            self.session.add(
                CustomerSupplier(customer_id=customer_id, supplier_id=supplier_id, mapped_by=mapped_by)
            )
        await self.session.flush()

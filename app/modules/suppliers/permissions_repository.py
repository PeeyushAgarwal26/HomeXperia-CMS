import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.module_catalog.models import Module
from app.modules.suppliers.models import SupplierModulePermission


class SupplierPermissionRepository:
    """Mirrors AdminUserPermissionRepository exactly — see docs/02-database-schema.md
    for why suppliers get their own module-permission grant (inert, not enforced)."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_module_keys(self, supplier_id: uuid.UUID) -> list[str]:
        stmt = (
            select(Module.key)
            .join(SupplierModulePermission, SupplierModulePermission.module_id == Module.id)
            .where(SupplierModulePermission.supplier_id == supplier_id)
            .order_by(Module.sort_order)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def replace(
        self, supplier_id: uuid.UUID, module_ids: list[uuid.UUID], granted_by: uuid.UUID
    ) -> None:
        await self.session.execute(
            delete(SupplierModulePermission).where(SupplierModulePermission.supplier_id == supplier_id)
        )
        for module_id in module_ids:
            self.session.add(
                SupplierModulePermission(
                    supplier_id=supplier_id, module_id=module_id, granted_by=granted_by
                )
            )
        await self.session.flush()

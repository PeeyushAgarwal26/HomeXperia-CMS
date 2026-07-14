import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.admin_users.models import AdminUserModulePermission
from app.modules.module_catalog.models import Module


class AdminUserPermissionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_module_keys(self, admin_user_id: uuid.UUID) -> list[str]:
        stmt = (
            select(Module.key)
            .join(AdminUserModulePermission, AdminUserModulePermission.module_id == Module.id)
            .where(AdminUserModulePermission.admin_user_id == admin_user_id)
            .order_by(Module.sort_order)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def replace(
        self, admin_user_id: uuid.UUID, module_ids: list[uuid.UUID], granted_by: uuid.UUID
    ) -> None:
        await self.session.execute(
            delete(AdminUserModulePermission).where(
                AdminUserModulePermission.admin_user_id == admin_user_id
            )
        )
        for module_id in module_ids:
            self.session.add(
                AdminUserModulePermission(
                    admin_user_id=admin_user_id, module_id=module_id, granted_by=granted_by
                )
            )
        await self.session.flush()

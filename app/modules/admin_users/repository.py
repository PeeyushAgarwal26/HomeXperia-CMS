import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.common.base_repository import BaseRepository
from app.modules.admin_users.models import AdminUser


class AdminUserRepository(BaseRepository[AdminUser]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(AdminUser, session)

    async def get_by_username(self, username: str) -> AdminUser | None:
        stmt = self._base_select().where(AdminUser.username == username)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> AdminUser | None:
        stmt = self._base_select().where(AdminUser.email == email)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_sub_admin_by_id(self, admin_user_id: uuid.UUID) -> AdminUser | None:
        stmt = self._base_select().where(
            AdminUser.id == admin_user_id, AdminUser.is_super_admin.is_(False)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def username_taken(self, username: str, exclude_id: uuid.UUID | None = None) -> bool:
        stmt = self._base_select().where(AdminUser.username == username)
        if exclude_id is not None:
            stmt = stmt.where(AdminUser.id != exclude_id)
        result = await self.session.execute(stmt.limit(1))
        return result.first() is not None

    async def email_taken(self, email: str, exclude_id: uuid.UUID | None = None) -> bool:
        stmt = self._base_select().where(AdminUser.email == email)
        if exclude_id is not None:
            stmt = stmt.where(AdminUser.id != exclude_id)
        result = await self.session.execute(stmt.limit(1))
        return result.first() is not None

    async def phone_number_taken(self, phone_number: str, exclude_id: uuid.UUID | None = None) -> bool:
        stmt = self._base_select().where(AdminUser.phone_number == phone_number)
        if exclude_id is not None:
            stmt = stmt.where(AdminUser.id != exclude_id)
        result = await self.session.execute(stmt.limit(1))
        return result.first() is not None

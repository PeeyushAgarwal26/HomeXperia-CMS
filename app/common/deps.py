import uuid
from typing import Callable, Coroutine

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_token
from app.db.session import get_db_session
from app.exceptions.http_exceptions import ForbiddenException, UnauthorizedException
from app.modules.admin_users.models import AdminUser, AdminUserModulePermission
from app.modules.admin_users.repository import AdminUserRepository
from app.modules.module_catalog.models import Module

_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    session: AsyncSession = Depends(get_db_session),
) -> AdminUser:
    if not credentials:
        raise UnauthorizedException()

    payload = decode_token(credentials.credentials)
    if not payload or payload.get("type") != "access":
        raise UnauthorizedException("Invalid or expired token.")

    try:
        admin_user_id = uuid.UUID(payload["sub"])
    except (KeyError, ValueError):
        raise UnauthorizedException("Invalid or expired token.")

    admin_user = await AdminUserRepository(session).get_by_id(admin_user_id)
    if admin_user is None or not admin_user.is_active:
        raise UnauthorizedException("Account is no longer active.")

    return admin_user


def require_module_permission(
    module_key: str,
) -> Callable[..., Coroutine[None, None, AdminUser]]:
    """Live DB check every request, not a JWT claim — see docs/03-backend-architecture.md.

    is_super_admin bypasses the check entirely; everyone else needs a matching,
    active row in admin_user_module_permissions for this exact module_key.
    """

    async def _check(
        admin_user: AdminUser = Depends(get_current_user),
        session: AsyncSession = Depends(get_db_session),
    ) -> AdminUser:
        if admin_user.is_super_admin:
            return admin_user

        stmt = (
            select(Module.id)
            .join(AdminUserModulePermission, AdminUserModulePermission.module_id == Module.id)
            .where(
                AdminUserModulePermission.admin_user_id == admin_user.id,
                Module.key == module_key,
                Module.is_active.is_(True),
            )
        )
        result = await session.execute(stmt)
        if result.scalar_one_or_none() is None:
            raise ForbiddenException(f"Missing permission: {module_key}")
        return admin_user

    return _check

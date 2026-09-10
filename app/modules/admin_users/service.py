import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.common.pagination import PaginationParams, SortParams
from app.core.security import hash_password
from app.exceptions.http_exceptions import (
    BadRequestException,
    ConflictException,
    ForbiddenException,
    NotFoundException,
)
from app.modules.admin_users.models import AdminUser
from app.modules.admin_users.permissions_repository import AdminUserPermissionRepository
from app.modules.admin_users.repository import AdminUserRepository
from app.modules.admin_users.schemas import SubAdminCreateRequest, SubAdminUpdateRequest
from app.modules.auth.repository import RefreshTokenRepository
from app.modules.module_catalog.repository import ModuleRepository


# Granted to every new sub-admin regardless of what the super admin assigns —
# every admin needs a landing page and a way to change their own password / log off.
DEFAULT_MODULE_KEYS = ["dashboard", "setting.change_password", "setting.log_off"]


class AdminUserService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = AdminUserRepository(session)
        self.permission_repository = AdminUserPermissionRepository(session)
        self.module_repository = ModuleRepository(session)
        self.refresh_token_repository = RefreshTokenRepository(session)

    async def list_sub_admins(
        self, pagination: PaginationParams, sort: SortParams, search: str | None
    ) -> tuple[list[AdminUser], int]:
        return await self.repository.get_all(
            filters={"is_super_admin": False},
            search=search,
            search_fields=["name", "email", "city", "phone_number"],
            sort_by=sort.sort_by,
            sort_order=sort.sort_order,
            offset=pagination.offset,
            limit=pagination.limit,
        )

    async def get_sub_admin(self, admin_user_id: uuid.UUID) -> AdminUser:
        admin_user = await self.repository.get_sub_admin_by_id(admin_user_id)
        if admin_user is None:
            raise NotFoundException("Sub-admin")
        return admin_user

    async def _check_uniqueness(
        self,
        username: str,
        email: str | None,
        phone_number: str,
        exclude_id: uuid.UUID | None = None,
    ) -> None:
        if await self.repository.username_taken(username, exclude_id):
            raise ConflictException("This username is already in use.")
        if email and await self.repository.email_taken(email, exclude_id):
            raise ConflictException("This email is already in use.")
        if await self.repository.phone_number_taken(phone_number, exclude_id):
            raise ConflictException("This phone number is already in use.")

    async def create(self, data: SubAdminCreateRequest, created_by: uuid.UUID) -> AdminUser:
        await self._check_uniqueness(data.username, data.email, data.phone_number)

        payload = data.model_dump(exclude={"password", "confirm_password"})
        payload["password_hash"] = hash_password(data.password)
        payload["created_by"] = created_by
        payload["is_super_admin"] = False

        admin_user = await self.repository.create(payload)
        await self.set_permissions(admin_user.id, DEFAULT_MODULE_KEYS, granted_by=created_by)

        return await self.get_sub_admin(admin_user.id)

    async def update(self, admin_user_id: uuid.UUID, data: SubAdminUpdateRequest) -> AdminUser:
        await self.get_sub_admin(admin_user_id)  # 404 if missing/not a sub-admin
        await self._check_uniqueness(data.username, data.email, data.phone_number, exclude_id=admin_user_id)

        payload = data.model_dump(exclude={"password", "confirm_password"}, exclude_unset=False)
        if data.password:
            payload["password_hash"] = hash_password(data.password)

        await self.repository.update(admin_user_id, payload)
        return await self.get_sub_admin(admin_user_id)

    async def delete(self, admin_user_id: uuid.UUID) -> None:
        await self.get_sub_admin(admin_user_id)
        await self.repository.soft_delete(admin_user_id)
        await self.refresh_token_repository.revoke_all_for_admin_user(admin_user_id)

    async def set_status(self, admin_user_id: uuid.UUID, is_active: bool) -> AdminUser:
        await self.get_sub_admin(admin_user_id)
        await self.repository.update(admin_user_id, {"is_active": is_active})
        if not is_active:
            await self.refresh_token_repository.revoke_all_for_admin_user(admin_user_id)
        return await self.get_sub_admin(admin_user_id)

    async def get_permission_keys(self, admin_user_id: uuid.UUID) -> list[str]:
        await self.get_sub_admin(admin_user_id)
        return await self.permission_repository.get_module_keys(admin_user_id)

    async def set_permissions(
        self,
        admin_user_id: uuid.UUID,
        module_keys: list[str],
        granted_by: uuid.UUID,
        granted_by_is_super_admin: bool = True,
    ) -> None:
        """granted_by_is_super_admin defaults to True (unrestricted) so the
        DEFAULT_MODULE_KEYS baseline grant in create() — every admin's own
        dashboard/change-password/log-off access — is never blocked by this
        check; only the explicit Assign Access endpoint passes the caller's
        real is_super_admin, restricting a sub-admin to handing out modules
        it was itself granted."""
        await self.get_sub_admin(admin_user_id)

        unique_keys = set(dict.fromkeys(module_keys))
        known_keys = set((await self.module_repository.get_ids_for_keys(list(unique_keys))).keys())
        unknown_keys = unique_keys - known_keys
        if unknown_keys:
            raise BadRequestException(f"Unknown module key(s): {', '.join(sorted(unknown_keys))}")

        if not granted_by_is_super_admin:
            grantable_keys = set(await self.permission_repository.get_module_keys(granted_by))
            previous_keys = set(await self.permission_repository.get_module_keys(admin_user_id))
            out_of_scope_previous = previous_keys - grantable_keys
            newly_granted_out_of_scope = (unique_keys - grantable_keys) - out_of_scope_previous
            if newly_granted_out_of_scope:
                raise ForbiddenException(
                    "You can only grant modules you yourself have access to. Not permitted: "
                    f"{', '.join(sorted(newly_granted_out_of_scope))}."
                )
            # Modules outside the caller's own scope are invisible to them in the
            # UI, so they can neither grant nor revoke them — always carried
            # forward exactly as they were, regardless of what was submitted.
            unique_keys = unique_keys | out_of_scope_previous

        key_to_id = await self.module_repository.get_ids_for_keys(list(unique_keys))
        await self.permission_repository.replace(
            admin_user_id, list(key_to_id.values()), granted_by=granted_by
        )

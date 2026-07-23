import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.logging import get_logger
from app.core.config import settings
from app.core.security import (
    create_access_token,
    create_password_reset_token,
    decode_token,
    generate_refresh_token,
    hash_password,
    hash_token,
    verify_password,
)
from app.exceptions.http_exceptions import (
    BadRequestException,
    ConflictException,
    ForbiddenException,
    UnauthorizedException,
)
from app.modules.admin_users.models import AdminUser, AdminUserModulePermission
from app.modules.admin_users.repository import AdminUserRepository
from app.modules.auth.repository import PasswordResetTokenRepository, RefreshTokenRepository
from app.modules.auth.schemas import AdminUserProfile, LoginResponse, TokenPair, UpdateMyProfileRequest
from app.modules.logs.repository import AdminUserLoginEventRepository
from app.modules.module_catalog.models import Module
from app.services.email import send_email

logger = get_logger(__name__)

# A rotated-out refresh token is accepted again for a short window after its
# rotation, instead of a hard 401. Refresh tokens are single-use by design,
# but a hard page reload can fire two near-simultaneous /auth/refresh calls
# holding the same pre-rotation token from two separate JS runtimes (neither
# aware of the other, so the in-memory dedup in the frontend's client.ts can't
# help) — without this, the loser gets 401'd and logged out even though
# nothing malicious happened. Outside this window, reuse is treated as a real
# stolen/replayed token and still rejected.
REFRESH_TOKEN_REUSE_GRACE_PERIOD = timedelta(seconds=10)


class AuthService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.admin_user_repo = AdminUserRepository(session)
        self.refresh_token_repo = RefreshTokenRepository(session)
        self.reset_token_repo = PasswordResetTokenRepository(session)
        self.login_event_repo = AdminUserLoginEventRepository(session)

    async def _issue_token_pair(self, admin_user: AdminUser, ip_address: str | None, user_agent: str | None) -> TokenPair:
        access_token = create_access_token(
            str(admin_user.id), extra={"is_super_admin": admin_user.is_super_admin}
        )
        raw_refresh, refresh_hash = generate_refresh_token()
        expires_at = datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days)
        await self.refresh_token_repo.create(admin_user.id, refresh_hash, expires_at, ip_address, user_agent)
        return TokenPair(access_token=access_token, refresh_token=raw_refresh)

    async def login(
        self, username: str, password: str, ip_address: str | None, user_agent: str | None
    ) -> LoginResponse:
        admin_user = await self.admin_user_repo.get_by_username(username)
        if admin_user is None or not verify_password(password, admin_user.password_hash):
            raise UnauthorizedException("Invalid username or password.")
        if not admin_user.is_active:
            raise UnauthorizedException("Account is deactivated.")

        await self.login_event_repo.create(admin_user.id, ip_address, user_agent)
        tokens = await self._issue_token_pair(admin_user, ip_address, user_agent)
        return LoginResponse(
            access_token=tokens.access_token,
            refresh_token=tokens.refresh_token,
            admin_user=AdminUserProfile.model_validate(admin_user, from_attributes=True),
        )

    async def forgot_password(self, username: str, requested_ip: str | None) -> None:
        admin_user = await self.admin_user_repo.get_by_username(username)
        if admin_user is None or not admin_user.is_active:
            return  # generic success either way — controller never reveals which

        await self.reset_token_repo.expire_outstanding_for_admin_user(admin_user.id)

        raw_token = create_password_reset_token(str(admin_user.id))
        expires_at = datetime.now(timezone.utc) + timedelta(
            minutes=settings.password_reset_token_expire_minutes
        )
        await self.reset_token_repo.create(admin_user.id, hash_token(raw_token), expires_at, requested_ip)

        reset_link = f"{settings.frontend_url}/reset-password?token={raw_token}"
        try:
            await send_email(
                to=admin_user.email,
                subject="Reset your HomeXperia Admin password",
                body_html=f'<p>Click <a href="{reset_link}">here</a> to reset your password. '
                f"This link expires in {settings.password_reset_token_expire_minutes} minutes.</p>",
            )
        except Exception:
            logger.exception("password_reset_email_failed", admin_user_id=str(admin_user.id))

    async def reset_password(self, token: str, new_password: str) -> None:
        payload = decode_token(token)
        if not payload or payload.get("type") != "password_reset":
            raise BadRequestException("Invalid or expired token.")

        stored = await self.reset_token_repo.get_valid_by_hash(hash_token(token))
        if stored is None:
            raise BadRequestException("Invalid or expired token.")

        admin_user = await self.admin_user_repo.get_by_id(uuid.UUID(payload["sub"]))
        if admin_user is None:
            raise BadRequestException("Invalid or expired token.")

        await self.admin_user_repo.update(admin_user.id, {"password_hash": hash_password(new_password)})
        await self.reset_token_repo.mark_used(stored)
        await self.refresh_token_repo.revoke_all_for_admin_user(admin_user.id)

    async def refresh(self, raw_refresh_token: str, ip_address: str | None, user_agent: str | None) -> TokenPair:
        stored = await self.refresh_token_repo.get_unexpired_by_hash(hash_token(raw_refresh_token))
        if stored is None:
            raise UnauthorizedException("Invalid or expired refresh token.")

        if stored.revoked_at is not None:
            reused_within_grace_period = (
                datetime.now(timezone.utc) - stored.revoked_at <= REFRESH_TOKEN_REUSE_GRACE_PERIOD
            )
            if not reused_within_grace_period:
                raise UnauthorizedException("Invalid or expired refresh token.")
            # Within the grace period: a concurrent request already rotated this
            # token out — issue this caller its own new pair too, rather than
            # re-revoking (it's already revoked) or rejecting.
        else:
            await self.refresh_token_repo.revoke(stored)

        admin_user = await self.admin_user_repo.get_by_id(stored.admin_user_id)
        if admin_user is None or not admin_user.is_active:
            raise UnauthorizedException("Account is no longer active.")

        return await self._issue_token_pair(admin_user, ip_address, user_agent)

    async def logout(self, admin_user_id: uuid.UUID, raw_refresh_token: str) -> None:
        stored = await self.refresh_token_repo.get_valid_by_hash(hash_token(raw_refresh_token))
        if stored is None:
            return  # already revoked/unknown — logout is idempotent
        if stored.admin_user_id != admin_user_id:
            raise ForbiddenException("This refresh token does not belong to you.")
        await self.refresh_token_repo.revoke(stored)

    async def change_password(
        self, admin_user: AdminUser, current_password: str, new_password: str
    ) -> None:
        if not verify_password(current_password, admin_user.password_hash):
            raise UnauthorizedException("Current password is incorrect.")

        await self.admin_user_repo.update(admin_user.id, {"password_hash": hash_password(new_password)})
        # Schema has no session->refresh-token correlation, so this revokes every
        # session, including the caller's — the just-issued access token still
        # works until it naturally expires, but no refresh will succeed afterward
        # on any device. Simpler and still secure; see 04-api-reference.md note.
        await self.refresh_token_repo.revoke_all_for_admin_user(admin_user.id)

    async def update_my_profile(self, admin_user: AdminUser, data: UpdateMyProfileRequest) -> AdminUser:
        if await self.admin_user_repo.email_taken(data.email, exclude_id=admin_user.id):
            raise ConflictException("This email is already in use.")
        if await self.admin_user_repo.phone_number_taken(data.phone_number, exclude_id=admin_user.id):
            raise ConflictException("This phone number is already in use.")

        await self.admin_user_repo.update(admin_user.id, data.model_dump())
        updated = await self.admin_user_repo.get_by_id(admin_user.id)
        assert updated is not None
        return updated

    async def get_permitted_module_keys(self, admin_user: AdminUser) -> list[str]:
        if admin_user.is_super_admin:
            stmt = select(Module.key).where(Module.is_active.is_(True))
        else:
            stmt = (
                select(Module.key)
                .join(AdminUserModulePermission, AdminUserModulePermission.module_id == Module.id)
                .where(
                    AdminUserModulePermission.admin_user_id == admin_user.id,
                    Module.is_active.is_(True),
                )
            )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

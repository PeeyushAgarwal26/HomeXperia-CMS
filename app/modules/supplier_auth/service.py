import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import (
    create_access_token,
    generate_refresh_token,
    hash_password,
    hash_token,
    verify_password,
)
from app.exceptions.http_exceptions import ConflictException, ForbiddenException, UnauthorizedException
from app.modules.auth.schemas import TokenPair
from app.modules.categories.models import ChildCategory
from app.modules.logs.repository import SupplierLoginEventRepository
from app.modules.suppliers.categories_repository import SupplierCategoryRepository
from app.modules.suppliers.models import Supplier
from app.modules.suppliers.permissions_repository import SupplierPermissionRepository
from app.modules.suppliers.repository import SupplierRepository
from app.modules.supplier_auth.repository import SupplierRefreshTokenRepository
from app.modules.supplier_auth.schemas import (
    SupplierLoginResponse,
    SupplierProfile,
    UpdateSupplierMyProfileRequest,
)

# See AuthService's identical constant — same rationale: a hard page reload can
# fire two near-simultaneous refresh calls holding the same pre-rotation token.
REFRESH_TOKEN_REUSE_GRACE_PERIOD = timedelta(seconds=10)


def _to_profile(supplier: Supplier) -> SupplierProfile:
    return SupplierProfile(
        id=supplier.id,
        name=supplier.name,
        username=supplier.username,
        email=supplier.email,
        logo_url=supplier.logo_url,
    )


class SupplierAuthService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.supplier_repo = SupplierRepository(session)
        self.refresh_token_repo = SupplierRefreshTokenRepository(session)
        self.login_event_repo = SupplierLoginEventRepository(session)
        self.category_map_repo = SupplierCategoryRepository(session)
        self.permission_repo = SupplierPermissionRepository(session)

    async def _issue_token_pair(
        self, supplier: Supplier, ip_address: str | None, user_agent: str | None
    ) -> TokenPair:
        # "type": "supplier_access" (not the admin path's "access") so a supplier
        # token can never be accepted by get_current_user, or vice versa.
        access_token = create_access_token(str(supplier.id), extra={"type": "supplier_access"})
        raw_refresh, refresh_hash = generate_refresh_token()
        expires_at = datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days)
        await self.refresh_token_repo.create(supplier.id, refresh_hash, expires_at, ip_address, user_agent)
        return TokenPair(access_token=access_token, refresh_token=raw_refresh)

    async def login(
        self, username: str, password: str, ip_address: str | None, user_agent: str | None
    ) -> SupplierLoginResponse:
        supplier = await self.supplier_repo.get_by_username(username)
        if supplier is None or not verify_password(password, supplier.password_hash):
            raise UnauthorizedException("Invalid username or password.")
        if not supplier.is_active:
            raise UnauthorizedException("Account is deactivated.")

        await self.login_event_repo.create(supplier.id, ip_address, user_agent)
        tokens = await self._issue_token_pair(supplier, ip_address, user_agent)
        return SupplierLoginResponse(
            access_token=tokens.access_token,
            refresh_token=tokens.refresh_token,
            supplier=_to_profile(supplier),
        )

    async def refresh(
        self, raw_refresh_token: str, ip_address: str | None, user_agent: str | None
    ) -> TokenPair:
        stored = await self.refresh_token_repo.get_unexpired_by_hash(hash_token(raw_refresh_token))
        if stored is None:
            raise UnauthorizedException("Invalid or expired refresh token.")

        if stored.revoked_at is not None:
            reused_within_grace_period = (
                datetime.now(timezone.utc) - stored.revoked_at <= REFRESH_TOKEN_REUSE_GRACE_PERIOD
            )
            if not reused_within_grace_period:
                raise UnauthorizedException("Invalid or expired refresh token.")
        else:
            await self.refresh_token_repo.revoke(stored)

        supplier = await self.supplier_repo.get_by_id(stored.supplier_id)
        if supplier is None or not supplier.is_active:
            raise UnauthorizedException("Account is no longer active.")

        return await self._issue_token_pair(supplier, ip_address, user_agent)

    async def logout(self, supplier_id: uuid.UUID, raw_refresh_token: str) -> None:
        stored = await self.refresh_token_repo.get_valid_by_hash(hash_token(raw_refresh_token))
        if stored is None:
            return  # already revoked/unknown — logout is idempotent
        if stored.supplier_id != supplier_id:
            raise ForbiddenException("This refresh token does not belong to you.")
        await self.refresh_token_repo.revoke(stored)

    async def change_password(
        self, supplier: Supplier, current_password: str, new_password: str
    ) -> None:
        if not verify_password(current_password, supplier.password_hash):
            raise UnauthorizedException("Current password is incorrect.")

        await self.supplier_repo.update(supplier.id, {"password_hash": hash_password(new_password)})
        await self.refresh_token_repo.revoke_all_for_supplier(supplier.id)

    async def get_my_categories(self, supplier_id: uuid.UUID) -> list[ChildCategory]:
        """Read-only — which Parent/Child Category pairs admin has mapped this
        supplier to via "Supplier Categories Access". No self-editing here; that
        stays an admin-only action, same as today."""
        child_category_ids = await self.category_map_repo.get_child_category_ids(supplier_id)
        if not child_category_ids:
            return []
        stmt = (
            select(ChildCategory)
            .where(ChildCategory.id.in_(child_category_ids))
            .order_by(ChildCategory.name)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_my_module_keys(self, supplier_id: uuid.UUID) -> list[str]:
        return await self.permission_repo.get_module_keys(supplier_id)

    async def update_my_profile(
        self, supplier: Supplier, data: UpdateSupplierMyProfileRequest
    ) -> Supplier:
        if await self.supplier_repo.phone_number_taken(data.phone_number, exclude_id=supplier.id):
            raise ConflictException("This phone number is already in use.")
        await self.supplier_repo.update(supplier.id, data.model_dump())
        updated = await self.supplier_repo.get_by_id(supplier.id)
        assert updated is not None
        return updated

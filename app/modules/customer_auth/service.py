import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import create_access_token, generate_refresh_token, hash_token, verify_password
from app.exceptions.http_exceptions import ForbiddenException, UnauthorizedException
from app.modules.auth.schemas import TokenPair
from app.modules.customer_auth.repository import CustomerRefreshTokenRepository
from app.modules.customer_auth.schemas import CustomerLoginResponse, CustomerProfile
from app.modules.customers.models import Customer
from app.modules.customers.repository import CustomerRepository
from app.modules.customers.suppliers_repository import CustomerSupplierRepository
from app.modules.logs.repository import CustomerLoginEventRepository

# See AuthService's identical constant — same rationale: a hard page reload can
# fire two near-simultaneous refresh calls holding the same pre-rotation token.
REFRESH_TOKEN_REUSE_GRACE_PERIOD = timedelta(seconds=10)


def _to_profile(customer: Customer) -> CustomerProfile:
    return CustomerProfile(
        id=customer.id,
        name=customer.name,
        customer_code=customer.customer_code,
        email=customer.email,
        phone_number=customer.phone_number,
        profile_image_url=customer.profile_image_url,
    )


class CustomerAuthService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.customer_repo = CustomerRepository(session)
        self.refresh_token_repo = CustomerRefreshTokenRepository(session)
        self.login_event_repo = CustomerLoginEventRepository(session)
        self.supplier_repo = CustomerSupplierRepository(session)

    async def _get_supplier_logos(self, customer_id: uuid.UUID) -> list[str]:
        suppliers = await self.supplier_repo.get_suppliers(customer_id)
        return [s.logo_url for s in suppliers if s.logo_url]

    async def _issue_token_pair(
        self, customer: Customer, ip_address: str | None, user_agent: str | None
    ) -> TokenPair:
        # "type": "customer_access" (not "access"/"supplier_access") so a
        # customer token can never be accepted by get_current_user or
        # get_current_supplier, or vice versa.
        access_token = create_access_token(str(customer.id), extra={"type": "customer_access"})
        raw_refresh, refresh_hash = generate_refresh_token()
        expires_at = datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days)
        await self.refresh_token_repo.create(customer.id, refresh_hash, expires_at, ip_address, user_agent)
        return TokenPair(access_token=access_token, refresh_token=raw_refresh)

    async def login(
        self, customer_code: str, password: str, ip_address: str | None, user_agent: str | None
    ) -> CustomerLoginResponse:
        customer = await self.customer_repo.get_by_customer_code(customer_code)
        if customer is None or not verify_password(password, customer.password_hash):
            raise UnauthorizedException("Invalid customer code or password.")
        if not customer.is_active:
            raise UnauthorizedException("Account is deactivated.")

        await self.customer_repo.update(customer.id, {"last_login_at": datetime.now(timezone.utc)})
        await self.login_event_repo.create(customer.id, ip_address)
        tokens = await self._issue_token_pair(customer, ip_address, user_agent)
        return CustomerLoginResponse(
            access_token=tokens.access_token,
            refresh_token=tokens.refresh_token,
            customer=_to_profile(customer),
            supplier_logos=await self._get_supplier_logos(customer.id),
        )

    async def login_by_code(
        self, customer_code: str, ip_address: str | None, user_agent: str | None
    ) -> CustomerLoginResponse | None:
        """Passwordless login for the QR/deep-link scan flow — the QR itself
        (and the shared x_key header) is the possession factor, matching the
        real, already-live contract this mirrors (see qr_login_controller.py).
        Returns None rather than raising so the caller can shape its own
        response envelope around a plain not-found case."""
        customer = await self.customer_repo.get_by_customer_code(customer_code)
        if customer is None or not customer.is_active:
            return None

        await self.customer_repo.update(customer.id, {"last_login_at": datetime.now(timezone.utc)})
        await self.login_event_repo.create(customer.id, ip_address)
        tokens = await self._issue_token_pair(customer, ip_address, user_agent)
        return CustomerLoginResponse(
            access_token=tokens.access_token,
            refresh_token=tokens.refresh_token,
            customer=_to_profile(customer),
            supplier_logos=await self._get_supplier_logos(customer.id),
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

        customer = await self.customer_repo.get_by_id(stored.customer_id)
        if customer is None or not customer.is_active:
            raise UnauthorizedException("Account is no longer active.")

        return await self._issue_token_pair(customer, ip_address, user_agent)

    async def logout(self, customer_id: uuid.UUID, raw_refresh_token: str) -> None:
        stored = await self.refresh_token_repo.get_valid_by_hash(hash_token(raw_refresh_token))
        if stored is None:
            return  # already revoked/unknown — logout is idempotent
        if stored.customer_id != customer_id:
            raise ForbiddenException("This refresh token does not belong to you.")
        await self.refresh_token_repo.revoke(stored)

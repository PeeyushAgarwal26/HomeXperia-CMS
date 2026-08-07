import uuid

from fastapi import Depends
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import decode_token
from app.db.session import get_db_session
from app.exceptions.http_exceptions import UnauthorizedException
from app.modules.customers.models import Customer
from app.modules.customers.repository import CustomerRepository

_bearer = HTTPBearer(auto_error=False)
_visualizer_key_header = APIKeyHeader(name="x-visualizer-key", auto_error=False)


async def get_current_customer(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    session: AsyncSession = Depends(get_db_session),
) -> Customer:
    """Mirrors get_current_user/get_current_supplier, but deliberately a
    separate function rather than a shared/parameterized one — a customer
    token must never be accepted by either of those, even by accident. The
    "type" claim check below is the actual enforcement of that."""
    if not credentials:
        raise UnauthorizedException()

    payload = decode_token(credentials.credentials)
    if not payload or payload.get("type") != "customer_access":
        raise UnauthorizedException("Invalid or expired token.")

    try:
        customer_id = uuid.UUID(payload["sub"])
    except (KeyError, ValueError):
        raise UnauthorizedException("Invalid or expired token.")

    customer = await CustomerRepository(session).get_by_id(customer_id)
    if customer is None or not customer.is_active:
        raise UnauthorizedException("Account is no longer active.")

    return customer


async def get_current_customer_optional(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    service_key: str | None = Depends(_visualizer_key_header),
    session: AsyncSession = Depends(get_db_session),
) -> Customer | None:
    """For visualizer routes that must keep working for callers with no
    Homexperia login at all (the Shopify-embed pages — iframed with no
    customer account context, previously gated only by Flask's hardcoded
    x-api-key). Accepts either a real customer JWT (returns that Customer)
    or the shared visualizer service key (returns None — no real identity,
    so callers must skip any per-customer usage-tracking write, the same way
    Flask's own tracking was a no-op for a blank customer_code)."""
    if credentials:
        payload = decode_token(credentials.credentials)
        if not payload or payload.get("type") != "customer_access":
            raise UnauthorizedException("Invalid or expired token.")
        try:
            customer_id = uuid.UUID(payload["sub"])
        except (KeyError, ValueError):
            raise UnauthorizedException("Invalid or expired token.")
        customer = await CustomerRepository(session).get_by_id(customer_id)
        if customer is None or not customer.is_active:
            raise UnauthorizedException("Account is no longer active.")
        return customer

    if service_key and settings.visualizer_service_key and service_key == settings.visualizer_service_key:
        return None

    raise UnauthorizedException()

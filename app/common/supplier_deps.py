import uuid

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_token
from app.db.session import get_db_session
from app.exceptions.http_exceptions import UnauthorizedException
from app.modules.suppliers.models import Supplier
from app.modules.suppliers.repository import SupplierRepository

_bearer = HTTPBearer(auto_error=False)


async def get_current_supplier(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    session: AsyncSession = Depends(get_db_session),
) -> Supplier:
    """Mirrors get_current_user, but deliberately a separate function rather than
    a shared/parameterized one — an admin token and a supplier token must never
    be accepted by each other's dependency, even by accident. The "type" claim
    check below is the actual enforcement of that; keeping the functions apart
    is what makes it obvious at a glance which routes trust which identity."""
    if not credentials:
        raise UnauthorizedException()

    payload = decode_token(credentials.credentials)
    if not payload or payload.get("type") != "supplier_access":
        raise UnauthorizedException("Invalid or expired token.")

    try:
        supplier_id = uuid.UUID(payload["sub"])
    except (KeyError, ValueError):
        raise UnauthorizedException("Invalid or expired token.")

    supplier = await SupplierRepository(session).get_by_id(supplier_id)
    if supplier is None or not supplier.is_active:
        raise UnauthorizedException("Account is no longer active.")

    return supplier

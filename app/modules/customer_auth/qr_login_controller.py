"""POST /auth/validate-customer-code — the QR/deep-link auto-login call the
real, already-live client-frontend makes (VerifyToken.jsx -> verifyTokenService.js).
Confirmed live and working today against the real production backend (a direct
curl against https://homexperia.com/api/v1/auth/validate-customer-code with a
real catalogue customer code returned real tokens) — this is a same-contract
reimplementation against OUR customers table, not a new/invented shape.

Deliberately bypasses this codebase's own APIResponse envelope: the frontend's
existing, unmodified parsing code reads response.data.status (bool) and
response.data.data.{access_token,...} directly, and always expects HTTP 200
even for a "failed" outcome (confirmed by curl — an unauthorized request came
back as HTTP 200 with status_code:401 *inside* the body). Matching that
exactly is the only way this endpoint is a real drop-in for that frontend."""

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_db_session
from app.modules.customer_auth.service import CustomerAuthService
from app.modules.customers.repository import CustomerRepository
from app.modules.customers.suppliers_repository import CustomerSupplierRepository
from app.modules.suppliers.models import Supplier

router = APIRouter(prefix="/auth", tags=["Customer QR Login"])


class ValidateCustomerCodeRequest(BaseModel):
    customer_code: str


class ValidateCustomerCodeData(BaseModel):
    access_token: str
    refresh_token: str
    customer_code: str
    supplier_logos: list[str]
    supplier_web_links: list[str] | None
    # Real field, empty for now — the real system's per-customer allowed
    # category tree isn't wired up here; nothing in the QR scan -> room
    # preview flow this supports actually reads it back out.
    mapped_category: list = []


class ValidateCustomerCodeResponse(BaseModel):
    status: bool
    status_code: int
    message: str
    error_message: str | None = None
    data: ValidateCustomerCodeData | None = None


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


@router.post("/validate-customer-code", response_model=ValidateCustomerCodeResponse)
async def validate_customer_code(
    body: ValidateCustomerCodeRequest,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> ValidateCustomerCodeResponse:
    # Read directly rather than via FastAPI's Header() dependency — that
    # helper converts underscores to hyphens by default, which would look
    # for "X-Key" instead of the literal "x_key" the real frontend sends.
    provided_key = request.headers.get("x_key")
    if provided_key != settings.customer_code_login_key:
        return ValidateCustomerCodeResponse(status=False, status_code=401, message="Unauthorized")

    result = await CustomerAuthService(session).login_by_code(
        body.customer_code, _client_ip(request), request.headers.get("user-agent")
    )
    if result is None:
        return ValidateCustomerCodeResponse(status=False, status_code=404, message="Customer not found")

    customer = await CustomerRepository(session).get_by_customer_code(body.customer_code)
    supplier_ids = await CustomerSupplierRepository(session).get_supplier_ids(customer.id)
    logos: list[str] = []
    web_links: list[str] = []
    if supplier_ids:
        stmt = select(Supplier.logo_url, Supplier.web_link).where(Supplier.id.in_(supplier_ids))
        for logo_url, web_link in (await session.execute(stmt)).all():
            if logo_url:
                logos.append(logo_url)
            if web_link:
                web_links.append(web_link)

    return ValidateCustomerCodeResponse(
        status=True,
        status_code=200,
        message="Success",
        data=ValidateCustomerCodeData(
            access_token=result.access_token,
            refresh_token=result.refresh_token,
            customer_code=body.customer_code,
            supplier_logos=logos,
            supplier_web_links=web_links or None,
        ),
    )

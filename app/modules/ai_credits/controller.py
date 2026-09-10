import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.base_controller import BaseController
from app.common.deps import require_module_permission
from app.common.pagination import PaginationParams
from app.common.response import APIResponse
from app.db.session import get_db_session
from app.modules.admin_users.models import AdminUser
from app.modules.ai_credits.repository import AccountKey
from app.modules.ai_credits.schemas import (
    AuditLogItem,
    BalanceSheetResponse,
    DashboardResponse,
    RolloverRunResponse,
    SupplierCreditSettingsDetail,
    SupplierCreditSettingsRequest,
    TopUpRequest,
)
from app.modules.ai_credits.service import AiCreditService

router = APIRouter(prefix="/ai-credits", tags=["AI Credits"])
controller = BaseController()

_require_ai_credits_access = require_module_permission("ai_credits")


@router.get("/dashboard", response_model=APIResponse[DashboardResponse])
async def get_dashboard(
    _: AdminUser = Depends(_require_ai_credits_access),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    data = await AiCreditService(session).get_dashboard()
    return controller.success(data=data)


@router.get("/suppliers/{supplier_id}/balance-sheet", response_model=APIResponse[BalanceSheetResponse])
async def get_supplier_balance_sheet(
    supplier_id: uuid.UUID,
    _: AdminUser = Depends(_require_ai_credits_access),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    data = await AiCreditService(session).compute_balance_sheet(AccountKey.for_supplier(supplier_id))
    return controller.success(data=data)


@router.get("/suppliers/{supplier_id}/audit-log", response_model=APIResponse[list[AuditLogItem]])
async def get_supplier_audit_log(
    supplier_id: uuid.UUID,
    pagination: Annotated[PaginationParams, Depends()],
    _: AdminUser = Depends(_require_ai_credits_access),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    data, total = await AiCreditService(session).get_audit_log(
        AccountKey.for_supplier(supplier_id), pagination.offset, pagination.limit
    )
    return controller.paginated(data=data, total=total, page=pagination.page, page_size=pagination.page_size)


@router.post("/suppliers/{supplier_id}/settings", response_model=APIResponse[SupplierCreditSettingsDetail])
async def set_supplier_credit_settings(
    supplier_id: uuid.UUID,
    body: SupplierCreditSettingsRequest,
    current_admin: AdminUser = Depends(_require_ai_credits_access),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    data = await AiCreditService(session).create_or_update_settings(
        AccountKey.for_supplier(supplier_id), body, created_by=current_admin.id
    )
    return controller.success(data=data, message="Supplier AI credit settings saved.")


@router.post("/suppliers/{supplier_id}/topup", response_model=APIResponse[None], status_code=201)
async def add_supplier_topup(
    supplier_id: uuid.UUID,
    body: TopUpRequest,
    current_admin: AdminUser = Depends(_require_ai_credits_access),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    await AiCreditService(session).add_topup(AccountKey.for_supplier(supplier_id), body, created_by=current_admin.id)
    return controller.success(message="Credits added.")


@router.get("/customers/{customer_id}/balance-sheet", response_model=APIResponse[BalanceSheetResponse])
async def get_customer_balance_sheet(
    customer_id: uuid.UUID,
    _: AdminUser = Depends(_require_ai_credits_access),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    """A plain customer's own direct AI credit account — e.g. a retailer who
    never supplies anything but still uses the visualizer. No promotion to
    Supplier required. But if this customer HAS been promoted (linked_supplier_id
    set), this reads the linked Supplier's account instead — see
    AiCreditService.resolve_customer_account — so it shows the exact same
    numbers as opening that Supplier directly, matching real usage, which
    already bills the linked Supplier (resolve_billing_account)."""
    service = AiCreditService(session)
    account = await service.resolve_customer_account(customer_id)
    data = await service.compute_balance_sheet(account)
    return controller.success(data=data)


@router.get("/customers/{customer_id}/audit-log", response_model=APIResponse[list[AuditLogItem]])
async def get_customer_audit_log(
    customer_id: uuid.UUID,
    pagination: Annotated[PaginationParams, Depends()],
    _: AdminUser = Depends(_require_ai_credits_access),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    service = AiCreditService(session)
    account = await service.resolve_customer_account(customer_id)
    data, total = await service.get_audit_log(account, pagination.offset, pagination.limit)
    return controller.paginated(data=data, total=total, page=pagination.page, page_size=pagination.page_size)


@router.post("/customers/{customer_id}/settings", response_model=APIResponse[SupplierCreditSettingsDetail])
async def set_customer_credit_settings(
    customer_id: uuid.UUID,
    body: SupplierCreditSettingsRequest,
    current_admin: AdminUser = Depends(_require_ai_credits_access),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    service = AiCreditService(session)
    account = await service.resolve_customer_account(customer_id)
    data = await service.create_or_update_settings(account, body, created_by=current_admin.id)
    return controller.success(data=data, message="Customer AI credit settings saved.")


@router.post("/customers/{customer_id}/topup", response_model=APIResponse[None], status_code=201)
async def add_customer_topup(
    customer_id: uuid.UUID,
    body: TopUpRequest,
    current_admin: AdminUser = Depends(_require_ai_credits_access),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    service = AiCreditService(session)
    account = await service.resolve_customer_account(customer_id)
    await service.add_topup(account, body, created_by=current_admin.id)
    return controller.success(message="Credits added.")


@router.post("/rollover/run", response_model=APIResponse[RolloverRunResponse])
async def run_rollover_now(
    _: AdminUser = Depends(_require_ai_credits_access),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    """Manual safety-net trigger — idempotent, safe to call any time (e.g.
    ops confirming the automatic cron caught up after downtime)."""
    data = await AiCreditService(session).run_monthly_rollover()
    return controller.success(data=data, message="Rollover complete.")

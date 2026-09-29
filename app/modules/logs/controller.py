import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.base_controller import BaseController
from app.common.deps import require_module_permission
from app.common.pagination import FilterParams, PaginationParams
from app.common.response import APIResponse
from app.db.session import get_db_session
from app.modules.admin_users.models import AdminUser
from app.modules.logs.schemas import CustomerLoginEventDetail, CustomerLoginHistoryItem, LoginHistoryItem
from app.modules.logs.service import LogsService

router = APIRouter(prefix="/logs", tags=["Logs"])
controller = BaseController()

_require_logs_access = require_module_permission("logs.customer_login_history")
_require_supplier_login_history_access = require_module_permission("logs.supplier_login_history")
_require_sub_admin_login_history_access = require_module_permission("logs.sub_admin_login_history")


@router.get("/customer-login-history", response_model=APIResponse[list[CustomerLoginHistoryItem]])
async def list_customer_login_history(
    pagination: Annotated[PaginationParams, Depends()],
    filters: Annotated[FilterParams, Depends()],
    supplier_id: Annotated[uuid.UUID | None, Query()] = None,
    from_date: Annotated[date | None, Query()] = None,
    to_date: Annotated[date | None, Query()] = None,
    _: AdminUser = Depends(_require_logs_access),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    service = LogsService(session)
    rows, total = await service.list_customer_login_history(
        pagination, filters.search, supplier_id, from_date, to_date
    )
    start = pagination.offset + 1
    data = [
        CustomerLoginHistoryItem(
            customer_id=row.customer_id,
            sno=start + i,
            name=row.name,
            customer_code=row.customer_code,
            device_limit=row.device_limit,
            login_count=row.login_count,
            login_date=row.login_date,
        )
        for i, row in enumerate(rows)
    ]
    return controller.paginated(data=data, total=total, page=pagination.page, page_size=pagination.page_size)


@router.get(
    "/customer-login-history/{customer_id}/events",
    response_model=APIResponse[list[CustomerLoginEventDetail]],
)
async def list_customer_login_events(
    customer_id: uuid.UUID,
    day: Annotated[date, Query()],
    _: AdminUser = Depends(_require_logs_access),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    events = await LogsService(session).list_customer_login_events(customer_id, day)
    data = [
        CustomerLoginEventDetail(id=event.id, logged_in_at=event.logged_in_at, ip_address=event.ip_address)
        for event in events
    ]
    return controller.success(data=data)


async def _list_login_history_for_role(
    session: AsyncSession,
    role: str,
    pagination: PaginationParams,
    filters: FilterParams,
    from_date: date | None,
    to_date: date | None,
) -> APIResponse:
    service = LogsService(session)
    rows, total = await service.list_login_history(pagination, filters.search, role, from_date, to_date)
    start = pagination.offset + 1
    data = [
        LoginHistoryItem(
            id=row.id,
            sno=start + i,
            account_id=row.account_id,
            name=row.name,
            username=row.username,
            role=row.role,
            logged_in_at=row.logged_in_at,
            ip_address=row.ip_address,
        )
        for i, row in enumerate(rows)
    ]
    return controller.paginated(data=data, total=total, page=pagination.page, page_size=pagination.page_size)


@router.get("/supplier-login-history", response_model=APIResponse[list[LoginHistoryItem]])
async def list_supplier_login_history(
    pagination: Annotated[PaginationParams, Depends()],
    filters: Annotated[FilterParams, Depends()],
    from_date: Annotated[date | None, Query()] = None,
    to_date: Annotated[date | None, Query()] = None,
    _: AdminUser = Depends(_require_supplier_login_history_access),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    return await _list_login_history_for_role(session, "supplier", pagination, filters, from_date, to_date)


@router.get("/sub-admin-login-history", response_model=APIResponse[list[LoginHistoryItem]])
async def list_sub_admin_login_history(
    pagination: Annotated[PaginationParams, Depends()],
    filters: Annotated[FilterParams, Depends()],
    from_date: Annotated[date | None, Query()] = None,
    to_date: Annotated[date | None, Query()] = None,
    _: AdminUser = Depends(_require_sub_admin_login_history_access),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    return await _list_login_history_for_role(session, "sub_admin", pagination, filters, from_date, to_date)

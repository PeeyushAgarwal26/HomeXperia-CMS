import uuid
from datetime import date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.base_controller import BaseController
from app.common.deps import require_module_permission
from app.common.pagination import FilterParams, PaginationParams
from app.common.response import APIResponse
from app.common.xlsx_export import build_xlsx_response
from app.db.session import get_db_session
from app.modules.admin_users.models import AdminUser
from app.modules.orders.schemas import OrderDetail, OrderListItem
from app.modules.orders.service import OrderService

router = APIRouter(prefix="/orders", tags=["Orders"])
controller = BaseController()

_require_orders_access = require_module_permission("orders")


@router.get("", response_model=APIResponse[list[OrderListItem]])
async def list_orders(
    pagination: Annotated[PaginationParams, Depends()],
    filters: Annotated[FilterParams, Depends()],
    from_date: Annotated[date | None, Query()] = None,
    to_date: Annotated[date | None, Query()] = None,
    _: AdminUser = Depends(_require_orders_access),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    items, total = await OrderService(session).list_orders(
        pagination.offset, pagination.limit, filters.search, from_date, to_date
    )
    return controller.paginated(data=items, total=total, page=pagination.page, page_size=pagination.page_size)


@router.get("/export")
async def export_orders(
    filters: Annotated[FilterParams, Depends()],
    _: AdminUser = Depends(_require_orders_access),
    session: AsyncSession = Depends(get_db_session),
):
    rows = await OrderService(session).list_for_export(filters.search)
    headers = [
        "Sno", "Invoice Number", "Client Name", "Customer", "Customer Code",
        "Total Amount", "Order Date",
    ]
    export_rows = [
        [
            i + 1,
            order.invoice_number,
            order.client_name,
            customer.name,
            customer.customer_code,
            float(order.total_amount),
            order.created_at.strftime("%Y-%m-%d %H:%M"),
        ]
        for i, (order, customer) in enumerate(rows)
    ]
    filename = f"Orders_{datetime.now().strftime('%d-%b-%Y_%H.%M.%S')}.xlsx"
    return build_xlsx_response(filename, headers, export_rows)


@router.get("/{order_id}", response_model=APIResponse[OrderDetail])
async def get_order(
    order_id: uuid.UUID,
    _: AdminUser = Depends(_require_orders_access),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    data = await OrderService(session).get_order_detail(order_id)
    return controller.success(data=data)


@router.get("/{order_id}/invoice")
async def get_order_invoice(
    order_id: uuid.UUID,
    _: AdminUser = Depends(_require_orders_access),
    session: AsyncSession = Depends(get_db_session),
) -> Response:
    pdf_bytes = await OrderService(session).generate_invoice(order_id)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="invoice-{order_id}.pdf"'},
    )

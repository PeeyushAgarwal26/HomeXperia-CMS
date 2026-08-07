import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.base_controller import BaseController
from app.common.customer_deps import get_current_customer
from app.common.pagination import PaginationParams
from app.common.response import APIResponse
from app.db.session import get_db_session
from app.modules.customers.models import Customer
from app.modules.orders.schemas import (
    CartDetail,
    CartItemDeleteRequest,
    CartItemUpsertRequest,
    MyOrderListItem,
    OrderCreateRequest,
    OrderCreateResponse,
)
from app.modules.orders.service import OrderService

cart_router = APIRouter(prefix="/cart", tags=["Customer Cart"])
order_router = APIRouter(prefix="/order", tags=["Customer Orders"])
controller = BaseController()


@cart_router.post("/create", response_model=APIResponse[CartDetail])
async def create_cart(
    customer: Customer = Depends(get_current_customer),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    data = await OrderService(session).get_cart_detail(customer.id)
    return controller.success(data=data)


@cart_router.get("/get", response_model=APIResponse[CartDetail])
async def get_cart(
    customer: Customer = Depends(get_current_customer),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    data = await OrderService(session).get_cart_detail(customer.id)
    return controller.success(data=data)


@cart_router.post("/update", response_model=APIResponse[CartDetail])
async def update_cart_item(
    body: CartItemUpsertRequest,
    customer: Customer = Depends(get_current_customer),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    data = await OrderService(session).upsert_cart_item(customer.id, body)
    return controller.success(data=data, message="Cart updated.")


@cart_router.post("/delete", response_model=APIResponse[CartDetail])
async def delete_cart_item(
    body: CartItemDeleteRequest,
    customer: Customer = Depends(get_current_customer),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    data = await OrderService(session).delete_cart_item(customer.id, body)
    return controller.success(data=data, message="Cart updated.")


@order_router.post("/save-order", response_model=APIResponse[OrderCreateResponse], status_code=201)
async def save_order(
    body: OrderCreateRequest,
    customer: Customer = Depends(get_current_customer),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    data = await OrderService(session).save_order(customer.id, body)
    return controller.success(data=data, message="Order placed successfully.")


@order_router.get("/get-invoice")
async def get_invoice(
    order_id: uuid.UUID,
    customer: Customer = Depends(get_current_customer),
    session: AsyncSession = Depends(get_db_session),
) -> Response:
    pdf_bytes = await OrderService(session).generate_invoice(order_id, customer_id=customer.id)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="invoice-{order_id}.pdf"'},
    )


@order_router.get("/my-orders", response_model=APIResponse[list[MyOrderListItem]])
async def list_my_orders(
    pagination: Annotated[PaginationParams, Depends()],
    customer: Customer = Depends(get_current_customer),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    items, total = await OrderService(session).list_my_orders(customer.id, pagination.offset, pagination.limit)
    return controller.paginated(data=items, total=total, page=pagination.page, page_size=pagination.page_size)

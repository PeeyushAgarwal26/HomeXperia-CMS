import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.base_controller import BaseController
from app.common.customer_deps import get_current_customer_optional
from app.common.pagination import PaginationParams
from app.common.response import APIResponse
from app.db.session import get_db_session
from app.modules.customers.models import Customer
from app.modules.products.schemas import ApplicableFilterGroup, ProductCustomerItem
from app.modules.products.service import ProductService

router = APIRouter(prefix="/customer/products", tags=["Customer Products"])
controller = BaseController()


@router.get("", response_model=APIResponse[list[ProductCustomerItem]])
async def list_products_for_customer(
    pagination: Annotated[PaginationParams, Depends()],
    child_category_id: Annotated[uuid.UUID | None, Query()] = None,
    search: Annotated[str | None, Query()] = None,
    min_price: Annotated[float | None, Query(ge=0)] = None,
    max_price: Annotated[float | None, Query(ge=0)] = None,
    filter_value_ids: Annotated[list[uuid.UUID], Query()] = [],  # noqa: B006
    customer: Customer | None = Depends(get_current_customer_optional),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    data, total = await ProductService(session).list_customer_products(
        child_category_id,
        search,
        min_price,
        max_price,
        filter_value_ids,
        pagination.offset,
        pagination.limit,
        customer,
    )
    return controller.paginated(data=data, total=total, page=pagination.page, page_size=pagination.page_size)


@router.get("/filters", response_model=APIResponse[list[ApplicableFilterGroup]])
async def list_applicable_filters_for_customer(
    child_category_id: Annotated[uuid.UUID, Query()],
    customer: Customer | None = Depends(get_current_customer_optional),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    data = await ProductService(session).get_customer_applicable_filters(child_category_id, customer)
    return controller.success(data=data)

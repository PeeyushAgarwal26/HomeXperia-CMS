import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.base_controller import BaseController
from app.common.pagination import FilterParams, PaginationParams, SortParams
from app.common.response import APIResponse
from app.common.supplier_deps import get_current_supplier
from app.db.session import get_db_session
from app.modules.customers.models import Customer, SupplierCustomerTheme
from app.modules.customers.schemas import (
    CustomerThemeDetail,
    SupplierCustomerListItem,
    UpdateCustomerThemeRequest,
)
from app.modules.customers.service import CustomerService
from app.modules.suppliers.models import Supplier

router = APIRouter(prefix="/supplier/customers", tags=["Supplier Customers"])
controller = BaseController()


def _to_list_item(item: Customer, sno: int) -> SupplierCustomerListItem:
    return SupplierCustomerListItem(
        id=item.id, sno=sno, name=item.name, customer_code=item.customer_code, city=item.city
    )


def _to_theme_detail(customer_id: uuid.UUID, theme: SupplierCustomerTheme | None) -> CustomerThemeDetail:
    return CustomerThemeDetail(
        customer_id=customer_id, primary_color=theme.primary_color if theme else None
    )


@router.get("", response_model=APIResponse[list[SupplierCustomerListItem]])
async def list_my_customers(
    pagination: Annotated[PaginationParams, Depends()],
    sort: Annotated[SortParams, Depends()],
    filters: Annotated[FilterParams, Depends()],
    supplier: Supplier = Depends(get_current_supplier),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    service = CustomerService(session)
    items, total = await service.list_customers(pagination, sort, filters.search, supplier.id)
    start = pagination.offset + 1
    data = [_to_list_item(item, start + i) for i, item in enumerate(items)]
    return controller.paginated(data=data, total=total, page=pagination.page, page_size=pagination.page_size)


@router.get("/{customer_id}/theme", response_model=APIResponse[CustomerThemeDetail])
async def get_my_customer_theme(
    customer_id: uuid.UUID,
    supplier: Supplier = Depends(get_current_supplier),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    theme = await CustomerService(session).get_own_customer_theme(supplier.id, customer_id)
    return controller.success(data=_to_theme_detail(customer_id, theme))


@router.put("/{customer_id}/theme", response_model=APIResponse[CustomerThemeDetail])
async def update_my_customer_theme(
    customer_id: uuid.UUID,
    body: UpdateCustomerThemeRequest,
    supplier: Supplier = Depends(get_current_supplier),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    theme = await CustomerService(session).update_own_customer_theme(
        supplier.id, customer_id, body.primary_color
    )
    return controller.success(data=_to_theme_detail(customer_id, theme), message="Theme updated successfully.")

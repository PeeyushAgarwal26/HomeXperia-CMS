from typing import Annotated
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.base_controller import BaseController
from app.common.deps import require_module_permission
from app.common.pagination import FilterParams, PaginationParams, SortParams
from app.common.response import APIResponse
from app.db.session import get_db_session
from app.modules.admin_users.models import AdminUser
from app.modules.customers.models import Customer
from app.modules.customers.schemas import (
    CustomerListItem,
    CustomerSupplierThemeItem,
    UpdateCustomerSupplierThemeRequest,
)
from app.modules.customers.service import CustomerService

router = APIRouter(prefix="/theme-configuration", tags=["Theme Configuration"])
controller = BaseController()

_require_theme_config_access = require_module_permission("theme_configuration")


def _to_list_item(item: Customer, sno: int, suppliers: list[str]) -> CustomerListItem:
    return CustomerListItem(
        id=item.id,
        sno=sno,
        name=item.name,
        profile_image_url=item.profile_image_url,
        customer_code=item.customer_code,
        email=item.email,
        phone_number=item.phone_number,
        gst_number=item.gst_number,
        city=item.city,
        device_limit=item.device_limit,
        active_device_count=item.active_device_count,
        last_login_at=item.last_login_at,
        suppliers=suppliers,
        is_active=item.is_active,
    )


@router.get("/customers", response_model=APIResponse[list[CustomerListItem]])
async def list_customers_for_theme_configuration(
    pagination: Annotated[PaginationParams, Depends()],
    sort: Annotated[SortParams, Depends()],
    filters: Annotated[FilterParams, Depends()],
    _: AdminUser = Depends(_require_theme_config_access),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    service = CustomerService(session)
    items, total = await service.list_customers(pagination, sort, filters.search, None)
    start = pagination.offset + 1
    suppliers_by_id = await service.get_supplier_names_map([item.id for item in items])
    data = [_to_list_item(item, start + i, suppliers_by_id.get(item.id, [])) for i, item in enumerate(items)]
    return controller.paginated(data=data, total=total, page=pagination.page, page_size=pagination.page_size)


@router.get(
    "/customers/{customer_id}/supplier-themes",
    response_model=APIResponse[list[CustomerSupplierThemeItem]],
)
async def get_customer_supplier_themes(
    customer_id: uuid.UUID,
    _: AdminUser = Depends(_require_theme_config_access),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    items = await CustomerService(session).list_customer_supplier_themes(customer_id)
    data = [
        CustomerSupplierThemeItem(
            supplier_id=sid, supplier_name=sname, primary_color=primary, secondary_color=secondary
        )
        for sid, sname, primary, secondary in items
    ]
    return controller.success(data=data)


@router.put(
    "/customers/{customer_id}/supplier-themes/{supplier_id}",
    response_model=APIResponse[CustomerSupplierThemeItem],
)
async def update_customer_supplier_theme(
    customer_id: uuid.UUID,
    supplier_id: uuid.UUID,
    body: UpdateCustomerSupplierThemeRequest,
    _: AdminUser = Depends(_require_theme_config_access),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    supplier_name = await CustomerService(session).set_customer_supplier_theme(
        customer_id, supplier_id, body.primary_color, body.secondary_color
    )
    return controller.success(
        data=CustomerSupplierThemeItem(
            supplier_id=supplier_id,
            supplier_name=supplier_name,
            primary_color=body.primary_color,
            secondary_color=body.secondary_color,
        ),
        message="Theme updated successfully.",
    )

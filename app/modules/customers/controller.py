import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.base_controller import BaseController
from app.common.deps import require_module_permission
from app.common.pagination import FilterParams, PaginationParams, SortParams
from app.common.response import APIResponse
from app.common.xlsx_export import build_xlsx_response
from app.db.session import get_db_session
from app.modules.admin_users.models import AdminUser
from app.modules.customers.models import Customer
from app.modules.customers.schemas import (
    CustomerCreateRequest,
    CustomerDetail,
    CustomerListItem,
    CustomerUpdateRequest,
    MapSuppliersRequest,
    MapSuppliersResponse,
    StatusUpdateRequest,
)
from app.modules.customers.service import CustomerService

router = APIRouter(prefix="/customers", tags=["Customer Management"])
controller = BaseController()

_require_customer_access = require_module_permission("user_management.customer")


def _to_detail(customer: Customer) -> CustomerDetail:
    return CustomerDetail(
        id=customer.id,
        name=customer.name,
        date_of_start=customer.date_of_start,
        email=customer.email,
        phone_number=customer.phone_number,
        gst_number=customer.gst_number,
        address=customer.address,
        pin_code=customer.pin_code,
        state_code=customer.state_code,
        city=customer.city,
        profile_image_url=customer.profile_image_url,
        device_limit=customer.device_limit,
        customer_code=customer.customer_code,
        is_active=customer.is_active,
    )


@router.get("", response_model=APIResponse[list[CustomerListItem]])
async def list_customers(
    pagination: Annotated[PaginationParams, Depends()],
    sort: Annotated[SortParams, Depends()],
    filters: Annotated[FilterParams, Depends()],
    supplier_id: Annotated[uuid.UUID | None, Query()] = None,
    _: AdminUser = Depends(_require_customer_access),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    service = CustomerService(session)
    items, total = await service.list_customers(pagination, sort, filters.search, supplier_id)
    start = pagination.offset + 1
    suppliers_by_id = await service.get_supplier_names_map([item.id for item in items])
    data = [
        CustomerListItem(
            id=item.id,
            sno=start + i,
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
            suppliers=suppliers_by_id.get(item.id, []),
            is_active=item.is_active,
        )
        for i, item in enumerate(items)
    ]
    return controller.paginated(data=data, total=total, page=pagination.page, page_size=pagination.page_size)


@router.get("/export")
async def export_customers(
    filters: Annotated[FilterParams, Depends()],
    supplier_id: Annotated[uuid.UUID | None, Query()] = None,
    _: AdminUser = Depends(_require_customer_access),
    session: AsyncSession = Depends(get_db_session),
):
    service = CustomerService(session)
    items = await service.list_for_export(filters.search, supplier_id)
    suppliers_by_id = await service.get_supplier_names_map([item.id for item in items])
    headers = [
        "Sno", "Name", "Customer Code", "Email", "Phone Number", "GST Number",
        "Device Limit", "Active Device", "Last Login Date", "Suppliers", "Active",
    ]
    rows = [
        [
            i + 1,
            item.name,
            item.customer_code,
            item.email or "",
            item.phone_number,
            item.gst_number or "",
            item.device_limit,
            item.active_device_count,
            item.last_login_at.strftime("%Y-%m-%d %H:%M") if item.last_login_at else "",
            ", ".join(suppliers_by_id.get(item.id, [])),
            "Yes" if item.is_active else "No",
        ]
        for i, item in enumerate(items)
    ]
    filename = f"CustomerList_{datetime.now().strftime('%d-%b-%Y_%H.%M')}.xlsx"
    return build_xlsx_response(filename, headers, rows)


@router.get("/export-supplier-mapping")
async def export_customer_supplier_mapping(
    _: AdminUser = Depends(_require_customer_access),
    session: AsyncSession = Depends(get_db_session),
):
    mappings = await CustomerService(session).list_supplier_mappings_for_export()
    headers = ["Sno", "Customer Name", "Customer Code", "Supplier Name"]
    rows = [
        [i + 1, customer_name, customer_code, supplier_name]
        for i, (customer_name, customer_code, supplier_name) in enumerate(mappings)
    ]
    filename = f"CustomerSupplierMapping_{datetime.now().strftime('%d-%b-%Y_%H.%M')}.xlsx"
    return build_xlsx_response(filename, headers, rows)


@router.get("/{customer_id}", response_model=APIResponse[CustomerDetail])
async def get_customer(
    customer_id: uuid.UUID,
    _: AdminUser = Depends(_require_customer_access),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    customer = await CustomerService(session).get_customer(customer_id)
    return controller.success(data=_to_detail(customer))


@router.post("", response_model=APIResponse[CustomerDetail], status_code=201)
async def create_customer(
    body: CustomerCreateRequest,
    current_admin: AdminUser = Depends(_require_customer_access),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    customer = await CustomerService(session).create(body, created_by=current_admin.id)
    return controller.success(data=_to_detail(customer), message="Customer created successfully.")


@router.put("/{customer_id}", response_model=APIResponse[CustomerDetail])
async def update_customer(
    customer_id: uuid.UUID,
    body: CustomerUpdateRequest,
    _: AdminUser = Depends(_require_customer_access),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    customer = await CustomerService(session).update(customer_id, body)
    return controller.success(data=_to_detail(customer), message="Customer updated successfully.")


@router.delete("/{customer_id}", response_model=APIResponse[None])
async def delete_customer(
    customer_id: uuid.UUID,
    _: AdminUser = Depends(_require_customer_access),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    await CustomerService(session).delete(customer_id)
    return controller.success(message="Customer deleted.")


@router.patch("/{customer_id}/status", response_model=APIResponse[dict])
async def set_customer_status(
    customer_id: uuid.UUID,
    body: StatusUpdateRequest,
    _: AdminUser = Depends(_require_customer_access),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    customer = await CustomerService(session).set_status(customer_id, body.is_active)
    return controller.success(data={"id": customer.id, "is_active": customer.is_active})


@router.get("/{customer_id}/suppliers", response_model=APIResponse[MapSuppliersResponse])
async def get_customer_suppliers(
    customer_id: uuid.UUID,
    _: AdminUser = Depends(_require_customer_access),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    supplier_ids = await CustomerService(session).get_supplier_ids(customer_id)
    return controller.success(data=MapSuppliersResponse(supplier_ids=supplier_ids))


@router.put("/{customer_id}/suppliers", response_model=APIResponse[None])
async def set_customer_suppliers(
    customer_id: uuid.UUID,
    body: MapSuppliersRequest,
    current_admin: AdminUser = Depends(_require_customer_access),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    await CustomerService(session).set_suppliers(customer_id, body.supplier_ids, mapped_by=current_admin.id)
    return controller.success(message="Suppliers updated.")

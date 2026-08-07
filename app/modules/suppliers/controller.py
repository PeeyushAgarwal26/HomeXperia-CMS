import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.base_controller import BaseController
from app.common.deps import require_module_permission
from app.common.pagination import FilterParams, PaginationParams, SortParams
from app.common.response import APIResponse
from app.common.xlsx_export import build_xlsx_response
from app.db.session import get_db_session
from app.modules.admin_users.models import AdminUser
from app.modules.suppliers.models import Supplier
from app.modules.suppliers.schemas import (
    AssignAccessRequest,
    AssignAccessResponse,
    LinkedAccountCreatedResponse,
    StatusUpdateRequest,
    SupplierCategoriesRequest,
    SupplierCategoriesResponse,
    SupplierCreateRequest,
    SupplierCreateResponse,
    SupplierDetail,
    SupplierListItem,
    SupplierUpdateRequest,
)
from app.modules.suppliers.service import SupplierService

router = APIRouter(prefix="/suppliers", tags=["Supplier Management"])
controller = BaseController()

_require_supplier_access = require_module_permission("user_management.suppliers")


def _to_detail(supplier: Supplier) -> SupplierDetail:
    return SupplierDetail(
        id=supplier.id,
        name=supplier.name,
        start_of_subscription=supplier.start_of_subscription,
        email=supplier.email,
        phone_number=supplier.phone_number,
        gst_number=supplier.gst_number,
        address=supplier.address,
        pin_code=supplier.pin_code,
        state_code=supplier.state_code,
        city=supplier.city,
        web_link=supplier.web_link,
        logo_url=supplier.logo_url,
        username=supplier.username,
        is_active=supplier.is_active,
        linked_customer_id=supplier.linked_customer_id,
    )


@router.get("", response_model=APIResponse[list[SupplierListItem]])
async def list_suppliers(
    pagination: Annotated[PaginationParams, Depends()],
    sort: Annotated[SortParams, Depends()],
    filters: Annotated[FilterParams, Depends()],
    _: AdminUser = Depends(_require_supplier_access),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    service = SupplierService(session)
    items, total = await service.list_suppliers(pagination, sort, filters.search)
    start = pagination.offset + 1
    categories_by_id = await service.get_category_names_map([item.id for item in items])
    data = [
        SupplierListItem(
            id=item.id,
            sno=start + i,
            name=item.name,
            username=item.username,
            logo_url=item.logo_url,
            email=item.email,
            phone_number=item.phone_number,
            gst_number=item.gst_number,
            state=item.state.name,
            city=item.city,
            web_link=item.web_link,
            categories=categories_by_id.get(item.id, []),
            is_active=item.is_active,
        )
        for i, item in enumerate(items)
    ]
    return controller.paginated(data=data, total=total, page=pagination.page, page_size=pagination.page_size)


@router.get("/export")
async def export_suppliers(
    filters: Annotated[FilterParams, Depends()],
    _: AdminUser = Depends(_require_supplier_access),
    session: AsyncSession = Depends(get_db_session),
):
    service = SupplierService(session)
    items = await service.list_for_export(filters.search)
    categories_by_id = await service.get_category_names_map([item.id for item in items])
    headers = [
        "Sno", "Supplier Name", "Login User Name", "Email", "Phone Number", "GST Number",
        "State", "City", "Web Link", "Supplier Categories", "Active",
    ]
    rows = [
        [
            i + 1,
            item.name,
            item.username,
            item.email or "",
            item.phone_number,
            item.gst_number or "",
            item.state.name,
            item.city,
            item.web_link or "",
            ", ".join(categories_by_id.get(item.id, [])),
            "Yes" if item.is_active else "No",
        ]
        for i, item in enumerate(items)
    ]
    filename = f"SupplierList_{datetime.now().strftime('%d-%b-%Y_%H.%M')}.xlsx"
    return build_xlsx_response(filename, headers, rows)


@router.get("/{supplier_id}", response_model=APIResponse[SupplierDetail])
async def get_supplier(
    supplier_id: uuid.UUID,
    _: AdminUser = Depends(_require_supplier_access),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    supplier = await SupplierService(session).get_supplier(supplier_id)
    return controller.success(data=_to_detail(supplier))


@router.post("", response_model=APIResponse[SupplierCreateResponse], status_code=201)
async def create_supplier(
    body: SupplierCreateRequest,
    current_admin: AdminUser = Depends(_require_supplier_access),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    supplier, temp_password, linked_customer = await SupplierService(session).create(
        body, created_by=current_admin.id
    )
    data = SupplierCreateResponse(
        **_to_detail(supplier).model_dump(), temporary_password=temp_password, linked_customer=linked_customer
    )
    return controller.success(data=data, message="Supplier created successfully.")


@router.put("/{supplier_id}", response_model=APIResponse[SupplierDetail])
async def update_supplier(
    supplier_id: uuid.UUID,
    body: SupplierUpdateRequest,
    _: AdminUser = Depends(_require_supplier_access),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    supplier = await SupplierService(session).update(supplier_id, body)
    return controller.success(data=_to_detail(supplier), message="Supplier updated successfully.")


@router.delete("/{supplier_id}", response_model=APIResponse[None])
async def delete_supplier(
    supplier_id: uuid.UUID,
    _: AdminUser = Depends(_require_supplier_access),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    await SupplierService(session).delete(supplier_id)
    return controller.success(message="Supplier deleted.")


@router.post(
    "/{supplier_id}/create-customer-account",
    response_model=APIResponse[LinkedAccountCreatedResponse],
    status_code=201,
)
async def create_customer_account_for_supplier(
    supplier_id: uuid.UUID,
    current_admin: AdminUser = Depends(_require_supplier_access),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    data = await SupplierService(session).create_linked_customer(supplier_id, created_by=current_admin.id)
    return controller.success(data=data, message="Customer account created and credentials emailed.")


@router.patch("/{supplier_id}/status", response_model=APIResponse[dict])
async def set_supplier_status(
    supplier_id: uuid.UUID,
    body: StatusUpdateRequest,
    _: AdminUser = Depends(_require_supplier_access),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    supplier = await SupplierService(session).set_status(supplier_id, body.is_active)
    return controller.success(data={"id": supplier.id, "is_active": supplier.is_active})


@router.get("/{supplier_id}/categories", response_model=APIResponse[SupplierCategoriesResponse])
async def get_supplier_categories(
    supplier_id: uuid.UUID,
    _: AdminUser = Depends(_require_supplier_access),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    child_category_ids = await SupplierService(session).get_child_category_ids(supplier_id)
    return controller.success(data=SupplierCategoriesResponse(child_category_ids=child_category_ids))


@router.put("/{supplier_id}/categories", response_model=APIResponse[None])
async def set_supplier_categories(
    supplier_id: uuid.UUID,
    body: SupplierCategoriesRequest,
    current_admin: AdminUser = Depends(_require_supplier_access),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    await SupplierService(session).set_categories(
        supplier_id, body.child_category_ids, granted_by=current_admin.id
    )
    return controller.success(message="Categories updated.")


@router.get("/{supplier_id}/permissions", response_model=APIResponse[AssignAccessResponse])
async def get_supplier_permissions(
    supplier_id: uuid.UUID,
    _: AdminUser = Depends(_require_supplier_access),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    module_keys = await SupplierService(session).get_permission_keys(supplier_id)
    return controller.success(data=AssignAccessResponse(module_keys=module_keys))


@router.put("/{supplier_id}/permissions", response_model=APIResponse[None])
async def set_supplier_permissions(
    supplier_id: uuid.UUID,
    body: AssignAccessRequest,
    current_admin: AdminUser = Depends(_require_supplier_access),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    await SupplierService(session).set_permissions(
        supplier_id, body.module_keys, granted_by=current_admin.id
    )
    return controller.success(message="Permissions updated.")

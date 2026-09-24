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
from app.modules.products.models import Product
from app.modules.products.schemas import (
    ApplicableFilterGroup,
    ProductCreateRequest,
    ProductDetail,
    ProductFilterValueDetail,
    ProductListItem,
    ProductUpdateRequest,
    StatusUpdateRequest,
)
from app.modules.products.service import ProductService

router = APIRouter(prefix="/products", tags=["Products"])
controller = BaseController()

_require_product_access = require_module_permission("master.product")


CATALOGUE_NAME_FILTER = "catalogue name"


def _catalogue_name_from_filter_values(filter_values: list[ProductFilterValueDetail]) -> str | None:
    for filter_value in filter_values:
        if filter_value.filter_name.strip().lower() == CATALOGUE_NAME_FILTER:
            return filter_value.value
    return None


def _to_detail(
    item: Product,
    filter_value_ids: list[uuid.UUID],
    filter_values: list[ProductFilterValueDetail],
) -> ProductDetail:
    return ProductDetail(
        id=item.id,
        order_no=item.order_no,
        child_category_id=item.child_category_id,
        child_category_name=item.child_category.name,
        supplier_id=item.supplier_id,
        supplier_name=item.supplier.name,
        catalog_name=item.catalog_name,
        catalogue_name=_catalogue_name_from_filter_values(filter_values),
        design_no=item.design_no,
        bar_code=item.bar_code,
        image_url=item.image_url,
        available_quantity=item.available_quantity,
        rate=float(item.rate) if item.rate is not None else None,
        length=float(item.length) if item.length is not None else None,
        width=float(item.width) if item.width is not None else None,
        is_active=item.is_active,
        filter_value_ids=filter_value_ids,
        filter_values=filter_values,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _to_list_item(item: Product, sno: int, catalogue_name: str | None) -> ProductListItem:
    return ProductListItem(
        id=item.id,
        sno=sno,
        order_no=item.order_no,
        child_category_id=item.child_category_id,
        child_category_name=item.child_category.name,
        supplier_id=item.supplier_id,
        supplier_name=item.supplier.name,
        catalog_name=item.catalog_name,
        catalogue_name=catalogue_name,
        design_no=item.design_no,
        bar_code=item.bar_code,
        image_url=item.image_url,
        available_quantity=item.available_quantity,
        rate=float(item.rate) if item.rate is not None else None,
        length=float(item.length) if item.length is not None else None,
        width=float(item.width) if item.width is not None else None,
        is_active=item.is_active,
    )


@router.get("", response_model=APIResponse[list[ProductListItem]])
async def list_products(
    pagination: Annotated[PaginationParams, Depends()],
    sort: Annotated[SortParams, Depends()],
    filters: Annotated[FilterParams, Depends()],
    child_category_id: Annotated[uuid.UUID | None, Query()] = None,
    supplier_id: Annotated[uuid.UUID | None, Query()] = None,
    # Scopes the list to only the suppliers a given customer is mapped to
    # (Map Suppliers) - used by the QR code generator's product picker, so
    # an admin building a catalogue mapping for a customer only sees
    # products that customer's own storefront would actually offer them.
    customer_id: Annotated[uuid.UUID | None, Query()] = None,
    _: AdminUser = Depends(_require_product_access),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    service = ProductService(session)
    items, total = await service.list_products(
        pagination, sort, filters.search, child_category_id, supplier_id, customer_id
    )
    catalogue_names = await service.get_catalogue_names_map([item.id for item in items])
    start = pagination.offset + 1
    data = [_to_list_item(item, start + i, catalogue_names.get(item.id)) for i, item in enumerate(items)]
    return controller.paginated(data=data, total=total, page=pagination.page, page_size=pagination.page_size)


@router.post("", response_model=APIResponse[ProductDetail], status_code=201)
async def create_product(
    body: ProductCreateRequest,
    _: AdminUser = Depends(_require_product_access),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    service = ProductService(session)
    item = await service.create(body)
    filter_value_ids = await service.get_filter_value_ids(item.id)
    filter_values = await service.get_filter_value_details(filter_value_ids)
    return controller.success(
        data=_to_detail(item, filter_value_ids, filter_values), message="Product created successfully."
    )


@router.get("/applicable-filters", response_model=APIResponse[list[ApplicableFilterGroup]])
async def get_applicable_filters(
    child_category_id: Annotated[uuid.UUID, Query()],
    supplier_id: Annotated[uuid.UUID, Query()],
    _: AdminUser = Depends(_require_product_access),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    groups = await ProductService(session).get_applicable_filters(child_category_id, supplier_id)
    return controller.success(data=groups)


@router.get("/export")
async def export_products(
    filters: Annotated[FilterParams, Depends()],
    child_category_id: Annotated[uuid.UUID | None, Query()] = None,
    supplier_id: Annotated[uuid.UUID | None, Query()] = None,
    _: AdminUser = Depends(_require_product_access),
    session: AsyncSession = Depends(get_db_session),
):
    service = ProductService(session)
    items = await service.list_for_export(filters.search, child_category_id, supplier_id)
    headers = [
        "Sno", "Order No", "Category", "Catalog Name", "Design No", "Bar Code",
        "Available Quantity", "Rate", "Length", "Width", "Active",
    ]
    rows = [
        [
            i + 1,
            item.order_no,
            item.child_category.name,
            item.catalog_name or "",
            item.design_no or "",
            item.bar_code,
            item.available_quantity if item.available_quantity is not None else "",
            float(item.rate) if item.rate is not None else "",
            float(item.length) if item.length is not None else "",
            float(item.width) if item.width is not None else "",
            "Yes" if item.is_active else "No",
        ]
        for i, item in enumerate(items)
    ]
    filename = f"ProductList_{datetime.now().strftime('%d-%b-%Y_%H.%M.%S')}.xlsx"
    return build_xlsx_response(filename, headers, rows)


@router.get("/{product_id}", response_model=APIResponse[ProductDetail])
async def get_product(
    product_id: uuid.UUID,
    _: AdminUser = Depends(_require_product_access),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    service = ProductService(session)
    item = await service.get_product(product_id)
    filter_value_ids = await service.get_filter_value_ids(product_id)
    filter_values = await service.get_filter_value_details(filter_value_ids)
    return controller.success(data=_to_detail(item, filter_value_ids, filter_values))


@router.put("/{product_id}", response_model=APIResponse[ProductDetail])
async def update_product(
    product_id: uuid.UUID,
    body: ProductUpdateRequest,
    _: AdminUser = Depends(_require_product_access),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    service = ProductService(session)
    item = await service.update(product_id, body)
    filter_value_ids = await service.get_filter_value_ids(product_id)
    filter_values = await service.get_filter_value_details(filter_value_ids)
    return controller.success(
        data=_to_detail(item, filter_value_ids, filter_values), message="Product updated successfully."
    )


@router.patch("/{product_id}/status", response_model=APIResponse[dict])
async def set_product_status(
    product_id: uuid.UUID,
    body: StatusUpdateRequest,
    _: AdminUser = Depends(_require_product_access),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    item = await ProductService(session).set_status(product_id, body.is_active)
    return controller.success(data={"id": item.id, "is_active": item.is_active})


@router.delete("/{product_id}", response_model=APIResponse[None])
async def delete_product(
    product_id: uuid.UUID,
    _: AdminUser = Depends(_require_product_access),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    await ProductService(session).delete(product_id)
    return controller.success(message="Product deleted.")

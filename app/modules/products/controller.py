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
    ProductListItem,
    ProductUpdateRequest,
    StatusUpdateRequest,
)
from app.modules.products.service import ProductService

router = APIRouter(prefix="/products", tags=["Products"])
controller = BaseController()

_require_product_access = require_module_permission("master.product")


def _to_detail(item: Product, filter_value_ids: list[uuid.UUID]) -> ProductDetail:
    return ProductDetail(
        id=item.id,
        order_no=item.order_no,
        child_category_id=item.child_category_id,
        supplier_id=item.supplier_id,
        catalog_name=item.catalog_name,
        design_no=item.design_no,
        bar_code=item.bar_code,
        image_url=item.image_url,
        available_quantity=item.available_quantity,
        rate=float(item.rate) if item.rate is not None else None,
        length=float(item.length),
        width=float(item.width),
        is_active=item.is_active,
        filter_value_ids=filter_value_ids,
    )


def _to_list_item(item: Product, sno: int) -> ProductListItem:
    return ProductListItem(
        id=item.id,
        sno=sno,
        order_no=item.order_no,
        child_category_id=item.child_category_id,
        child_category_name=item.child_category.name,
        supplier_id=item.supplier_id,
        supplier_name=item.supplier.name,
        catalog_name=item.catalog_name,
        design_no=item.design_no,
        bar_code=item.bar_code,
        image_url=item.image_url,
        available_quantity=item.available_quantity,
        rate=float(item.rate) if item.rate is not None else None,
        length=float(item.length),
        width=float(item.width),
        is_active=item.is_active,
    )


@router.get("", response_model=APIResponse[list[ProductListItem]])
async def list_products(
    pagination: Annotated[PaginationParams, Depends()],
    sort: Annotated[SortParams, Depends()],
    filters: Annotated[FilterParams, Depends()],
    child_category_id: Annotated[uuid.UUID | None, Query()] = None,
    supplier_id: Annotated[uuid.UUID | None, Query()] = None,
    _: AdminUser = Depends(_require_product_access),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    service = ProductService(session)
    items, total = await service.list_products(
        pagination, sort, filters.search, child_category_id, supplier_id
    )
    start = pagination.offset + 1
    data = [_to_list_item(item, start + i) for i, item in enumerate(items)]
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
    return controller.success(data=_to_detail(item, filter_value_ids), message="Product created successfully.")


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
            item.catalog_name,
            item.design_no or "",
            item.bar_code,
            item.available_quantity if item.available_quantity is not None else "",
            float(item.rate) if item.rate is not None else "",
            float(item.length),
            float(item.width),
            "Yes" if item.is_active else "No",
        ]
        for i, item in enumerate(items)
    ]
    filename = f"ProductList_{datetime.now().strftime('%d-%b-%Y_%H.%M')}.xlsx"
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
    return controller.success(data=_to_detail(item, filter_value_ids))


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
    return controller.success(data=_to_detail(item, filter_value_ids), message="Product updated successfully.")


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

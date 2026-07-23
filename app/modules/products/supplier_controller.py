import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.base_controller import BaseController
from app.common.pagination import FilterParams, PaginationParams, SortParams
from app.common.response import APIResponse
from app.common.supplier_deps import get_current_supplier
from app.db.session import get_db_session
from app.exceptions.http_exceptions import BadRequestException
from app.modules.products.models import Product
from app.modules.products.schemas import (
    ApplicableFilterGroup,
    ProductCreateRequest,
    ProductDetail,
    ProductFilterValueDetail,
    ProductListItem,
    ProductUpdateRequest,
    StatusUpdateRequest,
    SupplierProductCreateRequest,
    SupplierProductUpdateRequest,
)
from app.modules.products.service import ProductService
from app.modules.suppliers.categories_repository import SupplierCategoryRepository
from app.modules.suppliers.models import Supplier

router = APIRouter(prefix="/supplier/products", tags=["Supplier Products"])
controller = BaseController()


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
        design_no=item.design_no,
        bar_code=item.bar_code,
        image_url=item.image_url,
        available_quantity=item.available_quantity,
        rate=float(item.rate) if item.rate is not None else None,
        length=float(item.length),
        width=float(item.width),
        is_active=item.is_active,
        filter_value_ids=filter_value_ids,
        filter_values=filter_values,
        created_at=item.created_at,
        updated_at=item.updated_at,
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


async def _ensure_category_allowed(
    session: AsyncSession, supplier_id: uuid.UUID, child_category_id: uuid.UUID
) -> None:
    """A supplier may only list products in categories admin has approved them
    for via Supplier Categories Access ("My Categories") — not the full global
    category tree, and not something a supplier can grant themselves."""
    allowed_ids = await SupplierCategoryRepository(session).get_child_category_ids(supplier_id)
    if child_category_id not in allowed_ids:
        raise BadRequestException("You are not approved to list products in this category.")


@router.get("", response_model=APIResponse[list[ProductListItem]])
async def list_my_products(
    pagination: Annotated[PaginationParams, Depends()],
    sort: Annotated[SortParams, Depends()],
    filters: Annotated[FilterParams, Depends()],
    child_category_id: Annotated[uuid.UUID | None, Query()] = None,
    supplier: Supplier = Depends(get_current_supplier),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    service = ProductService(session)
    items, total = await service.list_products(
        pagination, sort, filters.search, child_category_id, supplier.id
    )
    start = pagination.offset + 1
    data = [_to_list_item(item, start + i) for i, item in enumerate(items)]
    return controller.paginated(data=data, total=total, page=pagination.page, page_size=pagination.page_size)


@router.post("", response_model=APIResponse[ProductDetail], status_code=201)
async def create_my_product(
    body: SupplierProductCreateRequest,
    supplier: Supplier = Depends(get_current_supplier),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    await _ensure_category_allowed(session, supplier.id, body.child_category_id)
    service = ProductService(session)
    full_body = ProductCreateRequest(supplier_id=supplier.id, **body.model_dump())
    item = await service.create(full_body)
    filter_value_ids = await service.get_filter_value_ids(item.id)
    filter_values = await service.get_filter_value_details(filter_value_ids)
    return controller.success(
        data=_to_detail(item, filter_value_ids, filter_values), message="Product created successfully."
    )


@router.get("/applicable-filters", response_model=APIResponse[list[ApplicableFilterGroup]])
async def get_my_applicable_filters(
    child_category_id: Annotated[uuid.UUID, Query()],
    supplier: Supplier = Depends(get_current_supplier),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    groups = await ProductService(session).get_applicable_filters(child_category_id, supplier.id)
    return controller.success(data=groups)


@router.get("/{product_id}", response_model=APIResponse[ProductDetail])
async def get_my_product(
    product_id: uuid.UUID,
    supplier: Supplier = Depends(get_current_supplier),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    service = ProductService(session)
    item = await service.get_own_product(product_id, supplier.id)
    filter_value_ids = await service.get_filter_value_ids(product_id)
    filter_values = await service.get_filter_value_details(filter_value_ids)
    return controller.success(data=_to_detail(item, filter_value_ids, filter_values))


@router.put("/{product_id}", response_model=APIResponse[ProductDetail])
async def update_my_product(
    product_id: uuid.UUID,
    body: SupplierProductUpdateRequest,
    supplier: Supplier = Depends(get_current_supplier),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    service = ProductService(session)
    await service.get_own_product(product_id, supplier.id)
    await _ensure_category_allowed(session, supplier.id, body.child_category_id)
    full_body = ProductUpdateRequest(supplier_id=supplier.id, **body.model_dump())
    item = await service.update(product_id, full_body)
    filter_value_ids = await service.get_filter_value_ids(product_id)
    filter_values = await service.get_filter_value_details(filter_value_ids)
    return controller.success(
        data=_to_detail(item, filter_value_ids, filter_values), message="Product updated successfully."
    )


@router.patch("/{product_id}/status", response_model=APIResponse[dict])
async def set_my_product_status(
    product_id: uuid.UUID,
    body: StatusUpdateRequest,
    supplier: Supplier = Depends(get_current_supplier),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    service = ProductService(session)
    await service.get_own_product(product_id, supplier.id)
    item = await service.set_status(product_id, body.is_active)
    return controller.success(data={"id": item.id, "is_active": item.is_active})


@router.delete("/{product_id}", response_model=APIResponse[None])
async def delete_my_product(
    product_id: uuid.UUID,
    supplier: Supplier = Depends(get_current_supplier),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    service = ProductService(session)
    await service.get_own_product(product_id, supplier.id)
    await service.delete(product_id)
    return controller.success(message="Product deleted.")

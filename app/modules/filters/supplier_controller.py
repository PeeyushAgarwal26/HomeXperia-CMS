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
from app.modules.filters.models import FilterValue
from app.modules.filters.schemas import (
    FilterValueCreateRequest,
    FilterValueDetail,
    FilterValueListItem,
    FilterValueUpdateRequest,
    StatusUpdateRequest,
    SupplierFilterOption,
    SupplierFilterValueCreateRequest,
    SupplierFilterValueUpdateRequest,
)
from app.modules.filters.service import FilterService, FilterValueService
from app.modules.suppliers.categories_repository import SupplierCategoryRepository
from app.modules.suppliers.models import Supplier

router = APIRouter(prefix="/supplier/filter-values", tags=["Supplier Filter Values"])
controller = BaseController()


def _to_detail(item: FilterValue) -> FilterValueDetail:
    return FilterValueDetail(
        id=item.id,
        value=item.value,
        filter_id=item.filter_id,
        child_category_id=item.child_category_id,
        supplier_id=item.supplier_id,
        is_active=item.is_active,
    )


async def _ensure_category_allowed(
    session: AsyncSession, supplier_id: uuid.UUID, child_category_id: uuid.UUID
) -> None:
    """Same approval boundary as Supplier Products — a supplier may only add
    attribute values under categories admin has approved them for via Supplier
    Categories Access, not the full global category tree."""
    allowed_ids = await SupplierCategoryRepository(session).get_child_category_ids(supplier_id)
    if child_category_id not in allowed_ids:
        raise BadRequestException("You are not approved to add filter values in this category.")


# --- "/filters" must be registered before "/{value_id}" below — otherwise it would be
# swallowed by "/{value_id}" (matched as an invalid UUID) before it ever reaches this
# handler. Same reasoning as Filter/FilterValue's "/values" ordering in controller.py. ---


@router.get("/filters", response_model=APIResponse[list[SupplierFilterOption]])
async def list_available_filters(
    _: Supplier = Depends(get_current_supplier),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    items = await FilterService(session).list_active()
    return controller.success(data=[SupplierFilterOption(id=item.id, name=item.name) for item in items])


@router.get("", response_model=APIResponse[list[FilterValueListItem]])
async def list_my_filter_values(
    pagination: Annotated[PaginationParams, Depends()],
    sort: Annotated[SortParams, Depends()],
    filters: Annotated[FilterParams, Depends()],
    filter_id: Annotated[uuid.UUID | None, Query()] = None,
    child_category_id: Annotated[uuid.UUID | None, Query()] = None,
    supplier: Supplier = Depends(get_current_supplier),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    service = FilterValueService(session)
    items, total = await service.list_values(
        pagination, sort, filters.search, filter_id, child_category_id, supplier.id
    )
    start = pagination.offset + 1
    data = [
        FilterValueListItem(
            id=item.id,
            sno=start + i,
            value=item.value,
            filter_id=item.filter_id,
            filter_name=item.filter.name,
            child_category_id=item.child_category_id,
            child_category_name=item.child_category.name,
            supplier_id=item.supplier_id,
            supplier_name=item.supplier.name,
            is_active=item.is_active,
        )
        for i, item in enumerate(items)
    ]
    return controller.paginated(data=data, total=total, page=pagination.page, page_size=pagination.page_size)


@router.post("", response_model=APIResponse[FilterValueDetail], status_code=201)
async def create_my_filter_value(
    body: SupplierFilterValueCreateRequest,
    supplier: Supplier = Depends(get_current_supplier),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    await _ensure_category_allowed(session, supplier.id, body.child_category_id)
    full_body = FilterValueCreateRequest(supplier_id=supplier.id, **body.model_dump())
    item = await FilterValueService(session).create(full_body)
    return controller.success(data=_to_detail(item), message="Filter value created successfully.")


@router.get("/{value_id}", response_model=APIResponse[FilterValueDetail])
async def get_my_filter_value(
    value_id: uuid.UUID,
    supplier: Supplier = Depends(get_current_supplier),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    item = await FilterValueService(session).get_own_value(value_id, supplier.id)
    return controller.success(data=_to_detail(item))


@router.put("/{value_id}", response_model=APIResponse[FilterValueDetail])
async def update_my_filter_value(
    value_id: uuid.UUID,
    body: SupplierFilterValueUpdateRequest,
    supplier: Supplier = Depends(get_current_supplier),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    service = FilterValueService(session)
    await service.get_own_value(value_id, supplier.id)
    await _ensure_category_allowed(session, supplier.id, body.child_category_id)
    full_body = FilterValueUpdateRequest(supplier_id=supplier.id, **body.model_dump())
    item = await service.update(value_id, full_body)
    return controller.success(data=_to_detail(item), message="Filter value updated successfully.")


@router.patch("/{value_id}/status", response_model=APIResponse[dict])
async def set_my_filter_value_status(
    value_id: uuid.UUID,
    body: StatusUpdateRequest,
    supplier: Supplier = Depends(get_current_supplier),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    service = FilterValueService(session)
    await service.get_own_value(value_id, supplier.id)
    item = await service.set_status(value_id, body.is_active)
    return controller.success(data={"id": item.id, "is_active": item.is_active})


@router.delete("/{value_id}", response_model=APIResponse[None])
async def delete_my_filter_value(
    value_id: uuid.UUID,
    supplier: Supplier = Depends(get_current_supplier),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    service = FilterValueService(session)
    await service.get_own_value(value_id, supplier.id)
    await service.delete(value_id)
    return controller.success(message="Filter value deleted.")

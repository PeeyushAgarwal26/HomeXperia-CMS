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
from app.modules.filters.models import Filter, FilterValue
from app.modules.filters.schemas import (
    FilterCreateRequest,
    FilterDetail,
    FilterListItem,
    FilterUpdateRequest,
    FilterValueCreateRequest,
    FilterValueDetail,
    FilterValueListItem,
    FilterValueUpdateRequest,
    StatusUpdateRequest,
)
from app.modules.filters.service import FilterService, FilterValueService

router = APIRouter(prefix="/filters", tags=["Filters"])
controller = BaseController()

_require_filter_access = require_module_permission("master.filter")
_require_filter_value_access = require_module_permission("master.filter_value")


def _to_detail(item: Filter) -> FilterDetail:
    return FilterDetail(id=item.id, name=item.name, is_active=item.is_active)


def _value_to_detail(item: FilterValue) -> FilterValueDetail:
    return FilterValueDetail(
        id=item.id,
        value=item.value,
        filter_id=item.filter_id,
        child_category_id=item.child_category_id,
        supplier_id=item.supplier_id,
        is_active=item.is_active,
    )


# --- Filter Value routes are registered under the literal "/values" prefix, which must
# come before Filter's "/{filter_id}" routes below — otherwise "/filters/values" would be
# swallowed by "/filters/{filter_id}" (matched as an invalid UUID) before it ever reaches
# these handlers. ---


@router.get("/values", response_model=APIResponse[list[FilterValueListItem]])
async def list_filter_values(
    pagination: Annotated[PaginationParams, Depends()],
    sort: Annotated[SortParams, Depends()],
    filters: Annotated[FilterParams, Depends()],
    filter_id: Annotated[uuid.UUID | None, Query()] = None,
    child_category_id: Annotated[uuid.UUID | None, Query()] = None,
    supplier_id: Annotated[uuid.UUID | None, Query()] = None,
    _: AdminUser = Depends(_require_filter_value_access),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    service = FilterValueService(session)
    items, total = await service.list_values(
        pagination, sort, filters.search, filter_id, child_category_id, supplier_id
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


@router.post("/values", response_model=APIResponse[FilterValueDetail], status_code=201)
async def create_filter_value(
    body: FilterValueCreateRequest,
    _: AdminUser = Depends(_require_filter_value_access),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    item = await FilterValueService(session).create(body)
    return controller.success(data=_value_to_detail(item), message="Filter value created successfully.")


@router.get("/values/export")
async def export_filter_values(
    filters: Annotated[FilterParams, Depends()],
    filter_id: Annotated[uuid.UUID | None, Query()] = None,
    child_category_id: Annotated[uuid.UUID | None, Query()] = None,
    supplier_id: Annotated[uuid.UUID | None, Query()] = None,
    _: AdminUser = Depends(_require_filter_value_access),
    session: AsyncSession = Depends(get_db_session),
):
    service = FilterValueService(session)
    items = await service.list_for_export(filters.search, filter_id, child_category_id, supplier_id)
    headers = ["Sno", "Value", "Filter Name", "Child Category", "Supplier", "Active"]
    rows = [
        [
            i + 1,
            item.value,
            item.filter.name,
            item.child_category.name,
            item.supplier.name,
            "Yes" if item.is_active else "No",
        ]
        for i, item in enumerate(items)
    ]
    filename = f"FilterValueList_{datetime.now().strftime('%d-%b-%Y_%H.%M')}.xlsx"
    return build_xlsx_response(filename, headers, rows)


@router.get("/values/{value_id}", response_model=APIResponse[FilterValueDetail])
async def get_filter_value(
    value_id: uuid.UUID,
    _: AdminUser = Depends(_require_filter_value_access),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    item = await FilterValueService(session).get_value(value_id)
    return controller.success(data=_value_to_detail(item))


@router.put("/values/{value_id}", response_model=APIResponse[FilterValueDetail])
async def update_filter_value(
    value_id: uuid.UUID,
    body: FilterValueUpdateRequest,
    _: AdminUser = Depends(_require_filter_value_access),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    item = await FilterValueService(session).update(value_id, body)
    return controller.success(data=_value_to_detail(item), message="Filter value updated successfully.")


@router.patch("/values/{value_id}/status", response_model=APIResponse[dict])
async def set_filter_value_status(
    value_id: uuid.UUID,
    body: StatusUpdateRequest,
    _: AdminUser = Depends(_require_filter_value_access),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    item = await FilterValueService(session).set_status(value_id, body.is_active)
    return controller.success(data={"id": item.id, "is_active": item.is_active})


@router.delete("/values/{value_id}", response_model=APIResponse[None])
async def delete_filter_value(
    value_id: uuid.UUID,
    _: AdminUser = Depends(_require_filter_value_access),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    await FilterValueService(session).delete(value_id)
    return controller.success(message="Filter value deleted.")


# --- Filter routes ---


@router.get("", response_model=APIResponse[list[FilterListItem]])
async def list_filters(
    pagination: Annotated[PaginationParams, Depends()],
    sort: Annotated[SortParams, Depends()],
    filters: Annotated[FilterParams, Depends()],
    _: AdminUser = Depends(_require_filter_access),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    service = FilterService(session)
    items, total = await service.list_filters(pagination, sort, filters.search)
    start = pagination.offset + 1
    data = [
        FilterListItem(id=item.id, sno=start + i, name=item.name, is_active=item.is_active)
        for i, item in enumerate(items)
    ]
    return controller.paginated(data=data, total=total, page=pagination.page, page_size=pagination.page_size)


@router.post("", response_model=APIResponse[FilterDetail], status_code=201)
async def create_filter(
    body: FilterCreateRequest,
    _: AdminUser = Depends(_require_filter_access),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    item = await FilterService(session).create(body)
    return controller.success(data=_to_detail(item), message="Filter created successfully.")


@router.get("/{filter_id}", response_model=APIResponse[FilterDetail])
async def get_filter(
    filter_id: uuid.UUID,
    _: AdminUser = Depends(_require_filter_access),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    item = await FilterService(session).get_filter(filter_id)
    return controller.success(data=_to_detail(item))


@router.put("/{filter_id}", response_model=APIResponse[FilterDetail])
async def update_filter(
    filter_id: uuid.UUID,
    body: FilterUpdateRequest,
    _: AdminUser = Depends(_require_filter_access),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    item = await FilterService(session).update(filter_id, body)
    return controller.success(data=_to_detail(item), message="Filter updated successfully.")


@router.patch("/{filter_id}/status", response_model=APIResponse[dict])
async def set_filter_status(
    filter_id: uuid.UUID,
    body: StatusUpdateRequest,
    _: AdminUser = Depends(_require_filter_access),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    item = await FilterService(session).set_status(filter_id, body.is_active)
    return controller.success(data={"id": item.id, "is_active": item.is_active})


@router.delete("/{filter_id}", response_model=APIResponse[None])
async def delete_filter(
    filter_id: uuid.UUID,
    _: AdminUser = Depends(_require_filter_access),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    await FilterService(session).delete(filter_id)
    return controller.success(message="Filter deleted.")

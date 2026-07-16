import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.base_controller import BaseController
from app.common.deps import require_module_permission
from app.common.pagination import FilterParams, PaginationParams, SortParams
from app.common.response import APIResponse
from app.db.session import get_db_session
from app.modules.admin_users.models import AdminUser
from app.modules.room_categories.models import RoomCategory
from app.modules.room_categories.schemas import (
    RoomCategoryCreateRequest,
    RoomCategoryDetail,
    RoomCategoryListItem,
    RoomCategoryUpdateRequest,
    StatusUpdateRequest,
)
from app.modules.room_categories.service import RoomCategoryService

router = APIRouter(prefix="/room-categories", tags=["Room Categories"])
controller = BaseController()

_require_room_category_access = require_module_permission("master.room_category")


def _to_detail(item: RoomCategory) -> RoomCategoryDetail:
    return RoomCategoryDetail(
        id=item.id, name=item.name, order_no=item.order_no, icon_url=item.icon_url, is_active=item.is_active
    )


@router.get("", response_model=APIResponse[list[RoomCategoryListItem]])
async def list_room_categories(
    pagination: Annotated[PaginationParams, Depends()],
    sort: Annotated[SortParams, Depends()],
    filters: Annotated[FilterParams, Depends()],
    _: AdminUser = Depends(_require_room_category_access),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    service = RoomCategoryService(session)
    items, total = await service.list_room_categories(pagination, sort, filters.search)
    start = pagination.offset + 1
    data = [
        RoomCategoryListItem(
            id=item.id,
            sno=start + i,
            order_no=item.order_no,
            name=item.name,
            icon_url=item.icon_url,
            is_active=item.is_active,
        )
        for i, item in enumerate(items)
    ]
    return controller.paginated(data=data, total=total, page=pagination.page, page_size=pagination.page_size)


@router.post("", response_model=APIResponse[RoomCategoryDetail], status_code=201)
async def create_room_category(
    body: RoomCategoryCreateRequest,
    _: AdminUser = Depends(_require_room_category_access),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    item = await RoomCategoryService(session).create(body)
    return controller.success(data=_to_detail(item), message="Room category created successfully.")


@router.get("/{room_category_id}", response_model=APIResponse[RoomCategoryDetail])
async def get_room_category(
    room_category_id: uuid.UUID,
    _: AdminUser = Depends(_require_room_category_access),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    item = await RoomCategoryService(session).get_room_category(room_category_id)
    return controller.success(data=_to_detail(item))


@router.put("/{room_category_id}", response_model=APIResponse[RoomCategoryDetail])
async def update_room_category(
    room_category_id: uuid.UUID,
    body: RoomCategoryUpdateRequest,
    _: AdminUser = Depends(_require_room_category_access),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    item = await RoomCategoryService(session).update(room_category_id, body)
    return controller.success(data=_to_detail(item), message="Room category updated successfully.")


@router.patch("/{room_category_id}/status", response_model=APIResponse[dict])
async def set_room_category_status(
    room_category_id: uuid.UUID,
    body: StatusUpdateRequest,
    _: AdminUser = Depends(_require_room_category_access),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    item = await RoomCategoryService(session).set_status(room_category_id, body.is_active)
    return controller.success(data={"id": item.id, "is_active": item.is_active})

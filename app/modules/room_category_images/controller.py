import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.base_controller import BaseController
from app.common.deps import require_module_permission
from app.common.pagination import PaginationParams, SortParams
from app.common.response import APIResponse
from app.db.session import get_db_session
from app.modules.admin_users.models import AdminUser
from app.modules.room_category_images.models import RoomCategoryImage
from app.modules.room_category_images.schemas import (
    MapSuppliersRequest,
    MapSuppliersResponse,
    RoomCategoryImageCreateRequest,
    RoomCategoryImageDetail,
    RoomCategoryImageListItem,
    RoomCategoryImageUpdateRequest,
)
from app.modules.room_category_images.service import RoomCategoryImageService

router = APIRouter(prefix="/room-categories/{room_category_id}/images", tags=["Room Category Images"])
controller = BaseController()

# Same permission as the parent Room Category screen — "Manage Images" is a
# drill-down action from a Room Category row, not a separate sidebar module.
_require_room_category_access = require_module_permission("master.room_category")


def _to_detail(item: RoomCategoryImage) -> RoomCategoryImageDetail:
    return RoomCategoryImageDetail(
        id=item.id,
        room_category_id=item.room_category_id,
        order_no=item.order_no,
        image_url=item.image_url,
        is_uploaded_to_cdn=item.is_uploaded_to_cdn,
    )


@router.get("", response_model=APIResponse[list[RoomCategoryImageListItem]])
async def list_room_category_images(
    room_category_id: uuid.UUID,
    pagination: Annotated[PaginationParams, Depends()],
    sort: Annotated[SortParams, Depends()],
    _: AdminUser = Depends(_require_room_category_access),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    service = RoomCategoryImageService(session)
    items, total = await service.list_images(room_category_id, pagination, sort)
    start = pagination.offset + 1
    suppliers_by_id = await service.get_supplier_names_map([item.id for item in items])
    data = [
        RoomCategoryImageListItem(
            id=item.id,
            sno=start + i,
            order_no=item.order_no,
            image_url=item.image_url,
            is_uploaded_to_cdn=item.is_uploaded_to_cdn,
            suppliers=suppliers_by_id.get(item.id, []),
        )
        for i, item in enumerate(items)
    ]
    return controller.paginated(data=data, total=total, page=pagination.page, page_size=pagination.page_size)


@router.post("", response_model=APIResponse[RoomCategoryImageDetail], status_code=201)
async def create_room_category_image(
    room_category_id: uuid.UUID,
    body: RoomCategoryImageCreateRequest,
    _: AdminUser = Depends(_require_room_category_access),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    item = await RoomCategoryImageService(session).create(room_category_id, body)
    return controller.success(data=_to_detail(item), message="Image added successfully.")


@router.get("/{image_id}", response_model=APIResponse[RoomCategoryImageDetail])
async def get_room_category_image(
    room_category_id: uuid.UUID,
    image_id: uuid.UUID,
    _: AdminUser = Depends(_require_room_category_access),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    item = await RoomCategoryImageService(session).get_image(room_category_id, image_id)
    return controller.success(data=_to_detail(item))


@router.put("/{image_id}", response_model=APIResponse[RoomCategoryImageDetail])
async def update_room_category_image(
    room_category_id: uuid.UUID,
    image_id: uuid.UUID,
    body: RoomCategoryImageUpdateRequest,
    _: AdminUser = Depends(_require_room_category_access),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    item = await RoomCategoryImageService(session).update(room_category_id, image_id, body)
    return controller.success(data=_to_detail(item), message="Image updated successfully.")


@router.delete("/{image_id}", response_model=APIResponse[None])
async def delete_room_category_image(
    room_category_id: uuid.UUID,
    image_id: uuid.UUID,
    _: AdminUser = Depends(_require_room_category_access),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    await RoomCategoryImageService(session).delete(room_category_id, image_id)
    return controller.success(message="Image deleted.")


@router.patch("/{image_id}/cdn", response_model=APIResponse[RoomCategoryImageDetail])
async def mark_room_category_image_uploaded_to_cdn(
    room_category_id: uuid.UUID,
    image_id: uuid.UUID,
    _: AdminUser = Depends(_require_room_category_access),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    item = await RoomCategoryImageService(session).mark_uploaded_to_cdn(room_category_id, image_id)
    return controller.success(data=_to_detail(item), message="Marked as uploaded to CDN.")


@router.get("/{image_id}/suppliers", response_model=APIResponse[MapSuppliersResponse])
async def get_room_category_image_suppliers(
    room_category_id: uuid.UUID,
    image_id: uuid.UUID,
    _: AdminUser = Depends(_require_room_category_access),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    supplier_ids = await RoomCategoryImageService(session).get_supplier_ids(room_category_id, image_id)
    return controller.success(data=MapSuppliersResponse(supplier_ids=supplier_ids))


@router.put("/{image_id}/suppliers", response_model=APIResponse[None])
async def set_room_category_image_suppliers(
    room_category_id: uuid.UUID,
    image_id: uuid.UUID,
    body: MapSuppliersRequest,
    current_admin: AdminUser = Depends(_require_room_category_access),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    await RoomCategoryImageService(session).set_suppliers(
        room_category_id, image_id, body.supplier_ids, mapped_by=current_admin.id
    )
    return controller.success(message="Suppliers updated.")

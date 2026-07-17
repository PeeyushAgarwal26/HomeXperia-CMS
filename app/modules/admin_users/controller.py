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
from app.modules.admin_users.schemas import (
    AssignAccessRequest,
    AssignAccessResponse,
    StatusUpdateRequest,
    SubAdminCreateRequest,
    SubAdminDetail,
    SubAdminListItem,
    SubAdminUpdateRequest,
)
from app.modules.admin_users.service import AdminUserService

router = APIRouter(prefix="/admin-users", tags=["Sub Admin Management"])
controller = BaseController()

_require_sub_admin_access = require_module_permission("user_management.sub_admin")


def _to_list_item(admin_user: AdminUser, sno: int) -> SubAdminListItem:
    return SubAdminListItem(
        id=admin_user.id,
        sno=sno,
        name=admin_user.name,
        profile_image_url=admin_user.profile_image_url,
        email=admin_user.email,
        state=admin_user.state.name,
        phone_number=admin_user.phone_number,
        city=admin_user.city,
        is_active=admin_user.is_active,
    )


def _to_detail(admin_user: AdminUser) -> SubAdminDetail:
    return SubAdminDetail(
        id=admin_user.id,
        name=admin_user.name,
        date_of_birth=admin_user.date_of_birth,
        email=admin_user.email,
        address=admin_user.address,
        phone_number=admin_user.phone_number,
        pin_code=admin_user.pin_code,
        state_code=admin_user.state_code,
        city=admin_user.city,
        profile_image_url=admin_user.profile_image_url,
        username=admin_user.username,
        is_active=admin_user.is_active,
    )


@router.get("", response_model=APIResponse[list[SubAdminListItem]])
async def list_sub_admins(
    pagination: Annotated[PaginationParams, Depends()],
    sort: Annotated[SortParams, Depends()],
    filters: Annotated[FilterParams, Depends()],
    _: AdminUser = Depends(_require_sub_admin_access),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    service = AdminUserService(session)
    items, total = await service.list_sub_admins(pagination, sort, filters.search)
    start = pagination.offset + 1
    data = [_to_list_item(item, start + i) for i, item in enumerate(items)]
    return controller.paginated(data=data, total=total, page=pagination.page, page_size=pagination.page_size)


@router.get("/{admin_user_id}", response_model=APIResponse[SubAdminDetail])
async def get_sub_admin(
    admin_user_id: uuid.UUID,
    _: AdminUser = Depends(_require_sub_admin_access),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    admin_user = await AdminUserService(session).get_sub_admin(admin_user_id)
    return controller.success(data=_to_detail(admin_user))


@router.post("", response_model=APIResponse[SubAdminDetail], status_code=201)
async def create_sub_admin(
    body: SubAdminCreateRequest,
    current_admin: AdminUser = Depends(_require_sub_admin_access),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    admin_user = await AdminUserService(session).create(body, created_by=current_admin.id)
    return controller.success(data=_to_detail(admin_user), message="Sub-admin created successfully.")


@router.put("/{admin_user_id}", response_model=APIResponse[SubAdminDetail])
async def update_sub_admin(
    admin_user_id: uuid.UUID,
    body: SubAdminUpdateRequest,
    _: AdminUser = Depends(_require_sub_admin_access),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    admin_user = await AdminUserService(session).update(admin_user_id, body)
    return controller.success(data=_to_detail(admin_user), message="Sub-admin updated successfully.")


@router.delete("/{admin_user_id}", response_model=APIResponse[None])
async def delete_sub_admin(
    admin_user_id: uuid.UUID,
    _: AdminUser = Depends(_require_sub_admin_access),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    await AdminUserService(session).delete(admin_user_id)
    return controller.success(message="Sub-admin deleted.")


@router.patch("/{admin_user_id}/status", response_model=APIResponse[dict])
async def set_sub_admin_status(
    admin_user_id: uuid.UUID,
    body: StatusUpdateRequest,
    _: AdminUser = Depends(_require_sub_admin_access),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    admin_user = await AdminUserService(session).set_status(admin_user_id, body.is_active)
    return controller.success(data={"id": admin_user.id, "is_active": admin_user.is_active})


@router.get("/{admin_user_id}/permissions", response_model=APIResponse[AssignAccessResponse])
async def get_sub_admin_permissions(
    admin_user_id: uuid.UUID,
    _: AdminUser = Depends(_require_sub_admin_access),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    module_keys = await AdminUserService(session).get_permission_keys(admin_user_id)
    return controller.success(data=AssignAccessResponse(module_keys=module_keys))


@router.put("/{admin_user_id}/permissions", response_model=APIResponse[None])
async def set_sub_admin_permissions(
    admin_user_id: uuid.UUID,
    body: AssignAccessRequest,
    current_admin: AdminUser = Depends(_require_sub_admin_access),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    await AdminUserService(session).set_permissions(
        admin_user_id, body.module_keys, granted_by=current_admin.id
    )
    return controller.success(message="Permissions updated.")

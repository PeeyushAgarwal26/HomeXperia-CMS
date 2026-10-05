import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.base_controller import BaseController
from app.common.deps import get_current_user, require_module_permission
from app.common.pagination import FilterParams, PaginationParams, SortParams
from app.common.response import APIResponse
from app.db.session import get_db_session
from app.modules.admin_users.models import AdminUser
from app.modules.categories.models import ChildCategory, ParentCategory
from app.modules.categories.schemas import (
    ChildCategoryCreateRequest,
    ChildCategoryDetail,
    ChildCategoryListItem,
    ChildCategoryUpdateRequest,
    ParentCategoryCreateRequest,
    ParentCategoryDetail,
    ParentCategoryListItem,
    ParentCategoryNode,
    ParentCategoryUpdateRequest,
    StatusUpdateRequest,
)
from app.modules.categories.service import CategoryService, ChildCategoryService, ParentCategoryService

router = APIRouter(prefix="/categories", tags=["Categories"])
controller = BaseController()

_require_parent_category_access = require_module_permission("master.parent_category")
_require_child_category_access = require_module_permission("master.child_category")


@router.get("", response_model=APIResponse[list[ParentCategoryNode]])
async def get_categories(
    _: AdminUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    tree = await CategoryService(session).get_tree()
    return controller.success(data=tree)


def _parent_to_detail(parent: ParentCategory) -> ParentCategoryDetail:
    return ParentCategoryDetail(
        id=parent.id, name=parent.name, icon_url=parent.icon_url, is_active=parent.is_active
    )


@router.get("/parents", response_model=APIResponse[list[ParentCategoryListItem]])
async def list_parent_categories(
    pagination: Annotated[PaginationParams, Depends()],
    sort: Annotated[SortParams, Depends()],
    filters: Annotated[FilterParams, Depends()],
    _: AdminUser = Depends(_require_parent_category_access),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    service = ParentCategoryService(session)
    items, total = await service.list_parents(pagination, sort, filters.search)
    start = pagination.offset + 1
    data = [
        ParentCategoryListItem(
            id=item.id, sno=start + i, name=item.name, icon_url=item.icon_url, is_active=item.is_active
        )
        for i, item in enumerate(items)
    ]
    return controller.paginated(data=data, total=total, page=pagination.page, page_size=pagination.page_size)


@router.post("/parents", response_model=APIResponse[ParentCategoryDetail], status_code=201)
async def create_parent_category(
    body: ParentCategoryCreateRequest,
    _: AdminUser = Depends(_require_parent_category_access),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    parent = await ParentCategoryService(session).create(body)
    return controller.success(data=_parent_to_detail(parent), message="Category created successfully.")


@router.get("/parents/{parent_id}", response_model=APIResponse[ParentCategoryDetail])
async def get_parent_category(
    parent_id: uuid.UUID,
    _: AdminUser = Depends(_require_parent_category_access),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    parent = await ParentCategoryService(session).get_parent(parent_id)
    return controller.success(data=_parent_to_detail(parent))


@router.put("/parents/{parent_id}", response_model=APIResponse[ParentCategoryDetail])
async def update_parent_category(
    parent_id: uuid.UUID,
    body: ParentCategoryUpdateRequest,
    _: AdminUser = Depends(_require_parent_category_access),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    parent = await ParentCategoryService(session).update(parent_id, body)
    return controller.success(data=_parent_to_detail(parent), message="Category updated successfully.")


@router.patch("/parents/{parent_id}/status", response_model=APIResponse[dict])
async def set_parent_category_status(
    parent_id: uuid.UUID,
    body: StatusUpdateRequest,
    _: AdminUser = Depends(_require_parent_category_access),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    parent = await ParentCategoryService(session).set_status(parent_id, body.is_active)
    return controller.success(data={"id": parent.id, "is_active": parent.is_active})


@router.delete("/parents/{parent_id}", response_model=APIResponse[None])
async def delete_parent_category(
    parent_id: uuid.UUID,
    _: AdminUser = Depends(_require_parent_category_access),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    await ParentCategoryService(session).delete(parent_id)
    return controller.success(message="Category deleted.")


def _child_to_detail(child: ChildCategory) -> ChildCategoryDetail:
    return ChildCategoryDetail(
        id=child.id,
        name=child.name,
        icon_url=child.icon_url,
        parent_category_id=child.parent_category_id,
        is_active=child.is_active,
        visualizer_type=child.visualizer_type,
    )


@router.get("/children", response_model=APIResponse[list[ChildCategoryListItem]])
async def list_child_categories(
    pagination: Annotated[PaginationParams, Depends()],
    sort: Annotated[SortParams, Depends()],
    filters: Annotated[FilterParams, Depends()],
    parent_category_id: Annotated[uuid.UUID | None, Query()] = None,
    _: AdminUser = Depends(_require_child_category_access),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    service = ChildCategoryService(session)
    items, total = await service.list_children(pagination, sort, filters.search, parent_category_id)
    start = pagination.offset + 1
    data = [
        ChildCategoryListItem(
            id=item.id,
            sno=start + i,
            name=item.name,
            icon_url=item.icon_url,
            parent_category_id=item.parent_category_id,
            parent_category_name=item.parent_category.name,
            is_active=item.is_active,
            visualizer_type=item.visualizer_type,
        )
        for i, item in enumerate(items)
    ]
    return controller.paginated(data=data, total=total, page=pagination.page, page_size=pagination.page_size)


@router.get("/children/{child_id}", response_model=APIResponse[ChildCategoryDetail])
async def get_child_category(
    child_id: uuid.UUID,
    _: AdminUser = Depends(_require_child_category_access),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    child = await ChildCategoryService(session).get_child(child_id)
    return controller.success(data=_child_to_detail(child))


@router.post("/children", response_model=APIResponse[ChildCategoryDetail], status_code=201)
async def create_child_category(
    body: ChildCategoryCreateRequest,
    _: AdminUser = Depends(_require_child_category_access),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    child = await ChildCategoryService(session).create(body)
    return controller.success(data=_child_to_detail(child), message="Category created successfully.")


@router.put("/children/{child_id}", response_model=APIResponse[ChildCategoryDetail])
async def update_child_category(
    child_id: uuid.UUID,
    body: ChildCategoryUpdateRequest,
    _: AdminUser = Depends(_require_child_category_access),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    child = await ChildCategoryService(session).update(child_id, body)
    return controller.success(data=_child_to_detail(child), message="Category updated successfully.")


@router.patch("/children/{child_id}/status", response_model=APIResponse[dict])
async def set_child_category_status(
    child_id: uuid.UUID,
    body: StatusUpdateRequest,
    _: AdminUser = Depends(_require_child_category_access),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    child = await ChildCategoryService(session).set_status(child_id, body.is_active)
    return controller.success(data={"id": child.id, "is_active": child.is_active})


@router.delete("/children/{child_id}", response_model=APIResponse[None])
async def delete_child_category(
    child_id: uuid.UUID,
    _: AdminUser = Depends(_require_child_category_access),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    await ChildCategoryService(session).delete(child_id)
    return controller.success(message="Category deleted.")

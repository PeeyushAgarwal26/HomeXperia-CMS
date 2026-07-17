import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.base_controller import BaseController
from app.common.deps import require_module_permission
from app.common.pagination import FilterParams, PaginationParams, SortParams
from app.common.response import APIResponse
from app.db.session import get_db_session
from app.modules.admin_users.models import AdminUser
from app.modules.notifications.models import NotificationTemplate
from app.modules.notifications.schemas import (
    NotificationTemplateCreateRequest,
    NotificationTemplateDetail,
    NotificationTemplateListItem,
    NotificationTemplateUpdateRequest,
    StatusUpdateRequest,
)
from app.modules.notifications.service import NotificationTemplateService

router = APIRouter(prefix="/notification-templates", tags=["Notification Templates"])
controller = BaseController()

_require_template_access = require_module_permission("notification.template")


async def _to_detail(service: NotificationTemplateService, item: NotificationTemplate) -> NotificationTemplateDetail:
    supplier_ids = await service.get_supplier_ids(item.id)
    return NotificationTemplateDetail(
        id=item.id,
        heading=item.heading,
        message=item.message,
        image_url=item.image_url,
        scheduled_at=item.scheduled_at,
        is_sent=item.is_sent,
        is_active=item.is_active,
        supplier_ids=supplier_ids,
    )


@router.get("", response_model=APIResponse[list[NotificationTemplateListItem]])
async def list_notification_templates(
    pagination: Annotated[PaginationParams, Depends()],
    sort: Annotated[SortParams, Depends()],
    filters: Annotated[FilterParams, Depends()],
    supplier_id: Annotated[uuid.UUID | None, Query()] = None,
    from_date: Annotated[date | None, Query()] = None,
    to_date: Annotated[date | None, Query()] = None,
    _: AdminUser = Depends(_require_template_access),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    service = NotificationTemplateService(session)
    items, total = await service.list_templates(pagination, sort, filters.search, supplier_id, from_date, to_date)
    start = pagination.offset + 1
    labels = await service.get_suppliers_labels([item.id for item in items])
    data = [
        NotificationTemplateListItem(
            id=item.id,
            sno=start + i,
            heading=item.heading,
            image_url=item.image_url,
            message=item.message,
            is_sent=item.is_sent,
            scheduled_at=item.scheduled_at,
            suppliers_label=labels.get(item.id, ""),
            is_active=item.is_active,
        )
        for i, item in enumerate(items)
    ]
    return controller.paginated(data=data, total=total, page=pagination.page, page_size=pagination.page_size)


@router.post("", response_model=APIResponse[NotificationTemplateDetail], status_code=201)
async def create_notification_template(
    body: NotificationTemplateCreateRequest,
    _: AdminUser = Depends(_require_template_access),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    service = NotificationTemplateService(session)
    item = await service.create(body)
    return controller.success(
        data=await _to_detail(service, item), message="Notification template created successfully."
    )


@router.get("/{template_id}", response_model=APIResponse[NotificationTemplateDetail])
async def get_notification_template(
    template_id: uuid.UUID,
    _: AdminUser = Depends(_require_template_access),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    service = NotificationTemplateService(session)
    item = await service.get_template(template_id)
    return controller.success(data=await _to_detail(service, item))


@router.put("/{template_id}", response_model=APIResponse[NotificationTemplateDetail])
async def update_notification_template(
    template_id: uuid.UUID,
    body: NotificationTemplateUpdateRequest,
    _: AdminUser = Depends(_require_template_access),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    service = NotificationTemplateService(session)
    item = await service.update(template_id, body)
    return controller.success(
        data=await _to_detail(service, item), message="Notification template updated successfully."
    )


@router.patch("/{template_id}/status", response_model=APIResponse[dict])
async def set_notification_template_status(
    template_id: uuid.UUID,
    body: StatusUpdateRequest,
    _: AdminUser = Depends(_require_template_access),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    item = await NotificationTemplateService(session).set_status(template_id, body.is_active)
    return controller.success(data={"id": item.id, "is_active": item.is_active})


@router.delete("/{template_id}", response_model=APIResponse[None])
async def delete_notification_template(
    template_id: uuid.UUID,
    _: AdminUser = Depends(_require_template_access),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse:
    await NotificationTemplateService(session).delete(template_id)
    return controller.success(message="Notification template deleted.")

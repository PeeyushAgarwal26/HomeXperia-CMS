import uuid
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.common.pagination import PaginationParams, SortParams
from app.exceptions.http_exceptions import ConflictException, NotFoundException
from app.modules.notifications.models import NotificationTemplate
from app.modules.notifications.repository import (
    NotificationTemplateRepository,
    NotificationTemplateSupplierRepository,
)
from app.modules.notifications.schemas import NotificationTemplateCreateRequest, NotificationTemplateUpdateRequest
from app.modules.suppliers.repository import SupplierRepository


class NotificationTemplateService:
    def __init__(self, session: AsyncSession) -> None:
        self.repository = NotificationTemplateRepository(session)
        self.supplier_link_repository = NotificationTemplateSupplierRepository(session)
        self.supplier_repository = SupplierRepository(session)

    async def list_templates(
        self,
        pagination: PaginationParams,
        sort: SortParams,
        search: str | None,
        supplier_id: uuid.UUID | None,
        from_date: date | None,
        to_date: date | None,
    ) -> tuple[list[NotificationTemplate], int]:
        items, total = await self.repository.list_templates(
            search=search,
            supplier_id=supplier_id,
            from_date=from_date,
            to_date=to_date,
            sort_by=sort.sort_by,
            sort_order=sort.sort_order,
            offset=pagination.offset,
            limit=pagination.limit,
        )
        return list(items), total

    async def get_template(self, template_id: uuid.UUID) -> NotificationTemplate:
        item = await self.repository.get_by_id(template_id)
        if item is None:
            raise NotFoundException("Notification template")
        return item

    async def get_supplier_ids(self, template_id: uuid.UUID) -> list[uuid.UUID]:
        return await self.supplier_link_repository.get_supplier_ids(template_id)

    async def get_suppliers_labels(self, template_ids: list[uuid.UUID]) -> dict[uuid.UUID, str]:
        """"All" when a template's mapped suppliers cover every active supplier — matching the
        real reference site's list column — otherwise the actual comma-joined supplier names."""
        names_map = await self.supplier_link_repository.get_names_map(template_ids)
        active_supplier_count = await self.supplier_repository.count_active()
        labels: dict[uuid.UUID, str] = {}
        for template_id in template_ids:
            names = names_map.get(template_id, [])
            if active_supplier_count > 0 and len(names) == active_supplier_count:
                labels[template_id] = "All"
            else:
                labels[template_id] = ", ".join(names)
        return labels

    async def create(self, data: NotificationTemplateCreateRequest) -> NotificationTemplate:
        payload = data.model_dump(exclude={"supplier_ids"})
        item = await self.repository.create(payload)
        await self.supplier_link_repository.replace(item.id, data.supplier_ids)
        return await self.get_template(item.id)

    async def update(
        self, template_id: uuid.UUID, data: NotificationTemplateUpdateRequest
    ) -> NotificationTemplate:
        item = await self.get_template(template_id)
        if item.is_sent:
            raise ConflictException("This notification has already been sent and can no longer be edited.")
        payload = data.model_dump(exclude={"supplier_ids"})
        await self.repository.update(template_id, payload)
        await self.supplier_link_repository.replace(template_id, data.supplier_ids)
        return await self.get_template(template_id)

    async def set_status(self, template_id: uuid.UUID, is_active: bool) -> NotificationTemplate:
        item = await self.get_template(template_id)
        if item.is_sent:
            raise ConflictException("This notification has already been sent and can no longer be changed.")
        await self.repository.update(template_id, {"is_active": is_active})
        return await self.get_template(template_id)

    async def delete(self, template_id: uuid.UUID) -> None:
        item = await self.get_template(template_id)
        if item.is_sent:
            raise ConflictException("This notification has already been sent and can no longer be deleted.")
        await self.repository.soft_delete(template_id)

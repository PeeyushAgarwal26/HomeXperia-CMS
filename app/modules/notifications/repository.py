import uuid
from datetime import date, timedelta
from typing import Sequence

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.base_repository import BaseRepository
from app.modules.notifications.models import NotificationTemplate, NotificationTemplateSupplier
from app.modules.suppliers.models import Supplier


class NotificationTemplateRepository(BaseRepository[NotificationTemplate]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(NotificationTemplate, session)

    async def list_templates(
        self,
        *,
        search: str | None,
        supplier_id: uuid.UUID | None,
        from_date: date | None,
        to_date: date | None,
        sort_by: str,
        sort_order: str,
        offset: int,
        limit: int | None,
    ) -> tuple[Sequence[NotificationTemplate], int]:
        stmt = self._base_select()
        if supplier_id is not None:
            stmt = stmt.where(
                NotificationTemplate.id.in_(
                    select(NotificationTemplateSupplier.template_id).where(
                        NotificationTemplateSupplier.supplier_id == supplier_id
                    )
                )
            )
        if search:
            stmt = stmt.where(NotificationTemplate.heading.ilike(f"%{search}%"))
        if from_date:
            stmt = stmt.where(NotificationTemplate.scheduled_at >= from_date)
        if to_date:
            stmt = stmt.where(NotificationTemplate.scheduled_at < to_date + timedelta(days=1))

        total = await self.session.scalar(select(func.count()).select_from(stmt.subquery())) or 0

        sort_column = getattr(NotificationTemplate, sort_by, None) or NotificationTemplate.created_at
        stmt = stmt.order_by(sort_column.asc() if sort_order == "asc" else sort_column.desc())
        stmt = stmt.offset(offset)
        if limit is not None:
            stmt = stmt.limit(limit)

        result = await self.session.execute(stmt)
        return result.scalars().all(), total


class NotificationTemplateSupplierRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_supplier_ids(self, template_id: uuid.UUID) -> list[uuid.UUID]:
        stmt = select(NotificationTemplateSupplier.supplier_id).where(
            NotificationTemplateSupplier.template_id == template_id
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_names_map(self, template_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[str]]:
        if not template_ids:
            return {}
        stmt = (
            select(NotificationTemplateSupplier.template_id, Supplier.name)
            .join(Supplier, Supplier.id == NotificationTemplateSupplier.supplier_id)
            .where(NotificationTemplateSupplier.template_id.in_(template_ids))
            .order_by(Supplier.name)
        )
        result = await self.session.execute(stmt)
        names_by_template: dict[uuid.UUID, list[str]] = {}
        for template_id, supplier_name in result.all():
            names_by_template.setdefault(template_id, []).append(supplier_name)
        return names_by_template

    async def replace(self, template_id: uuid.UUID, supplier_ids: list[uuid.UUID]) -> None:
        await self.session.execute(
            delete(NotificationTemplateSupplier).where(
                NotificationTemplateSupplier.template_id == template_id
            )
        )
        for supplier_id in dict.fromkeys(supplier_ids):
            self.session.add(
                NotificationTemplateSupplier(template_id=template_id, supplier_id=supplier_id)
            )
        await self.session.flush()

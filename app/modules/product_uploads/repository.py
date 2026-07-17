import uuid
from datetime import date, timedelta
from typing import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.product_uploads.models import ProductUploadLog, ProductUploadLogItem


class ProductUploadLogRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_logs(
        self,
        *,
        supplier_id: uuid.UUID | None,
        search: str | None,
        from_date: date | None,
        to_date: date | None,
        offset: int,
        limit: int | None,
    ) -> tuple[Sequence[ProductUploadLog], int]:
        stmt = select(ProductUploadLog)
        if supplier_id is not None:
            stmt = stmt.where(ProductUploadLog.supplier_id == supplier_id)
        if search:
            stmt = stmt.where(ProductUploadLog.file_name.ilike(f"%{search}%"))
        if from_date:
            stmt = stmt.where(ProductUploadLog.created_at >= from_date)
        if to_date:
            stmt = stmt.where(ProductUploadLog.created_at < to_date + timedelta(days=1))

        total = await self.session.scalar(select(func.count()).select_from(stmt.subquery())) or 0

        stmt = stmt.order_by(ProductUploadLog.created_at.desc()).offset(offset)
        if limit is not None:
            stmt = stmt.limit(limit)

        result = await self.session.execute(stmt)
        return result.scalars().all(), total

    async def get_by_id(self, log_id: uuid.UUID) -> ProductUploadLog | None:
        stmt = select(ProductUploadLog).where(ProductUploadLog.id == log_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create(self, data: dict) -> ProductUploadLog:
        item = ProductUploadLog(**data)
        self.session.add(item)
        await self.session.flush()
        return item


class ProductUploadLogItemRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def bulk_create(self, log_id: uuid.UUID, rows: list[dict]) -> None:
        for row in rows:
            self.session.add(ProductUploadLogItem(log_id=log_id, **row))
        await self.session.flush()

    async def list_for_log(self, log_id: uuid.UUID) -> list[ProductUploadLogItem]:
        stmt = (
            select(ProductUploadLogItem)
            .where(ProductUploadLogItem.log_id == log_id)
            .order_by(ProductUploadLogItem.row_no)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

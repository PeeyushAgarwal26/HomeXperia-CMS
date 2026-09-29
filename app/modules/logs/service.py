import uuid
from datetime import date
from typing import Sequence

from sqlalchemy import Row
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.pagination import PaginationParams
from app.modules.logs.models import CustomerLoginEvent
from app.modules.logs.repository import CustomerLoginEventRepository, LoginHistoryRepository


class LogsService:
    def __init__(self, session: AsyncSession) -> None:
        self.repository = CustomerLoginEventRepository(session)
        self.login_history_repository = LoginHistoryRepository(session)

    async def list_customer_login_history(
        self,
        pagination: PaginationParams,
        search: str | None,
        supplier_id: uuid.UUID | None,
        from_date: date | None,
        to_date: date | None,
    ) -> tuple[Sequence[Row], int]:
        return await self.repository.get_day_wise(
            search=search,
            supplier_id=supplier_id,
            from_date=from_date,
            to_date=to_date,
            offset=pagination.offset,
            limit=pagination.limit,
        )

    async def list_customer_login_events(
        self, customer_id: uuid.UUID, day: date
    ) -> Sequence[CustomerLoginEvent]:
        return await self.repository.get_events_for_day(customer_id, day)

    async def list_login_history(
        self,
        pagination: PaginationParams,
        search: str | None,
        role: str | None,
        from_date: date | None,
        to_date: date | None,
    ) -> tuple[Sequence[Row], int]:
        return await self.login_history_repository.list_login_history(
            search=search,
            role=role,
            from_date=from_date,
            to_date=to_date,
            offset=pagination.offset,
            limit=pagination.limit,
        )

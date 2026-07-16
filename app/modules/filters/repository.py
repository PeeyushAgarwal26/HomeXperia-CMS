import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.common.base_repository import BaseRepository
from app.modules.filters.models import Filter, FilterValue


class FilterRepository(BaseRepository[Filter]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Filter, session)

    async def name_taken(self, name: str, exclude_id: uuid.UUID | None = None) -> bool:
        stmt = self._base_select().where(Filter.name == name)
        if exclude_id is not None:
            stmt = stmt.where(Filter.id != exclude_id)
        result = await self.session.execute(stmt.limit(1))
        return result.first() is not None


class FilterValueRepository(BaseRepository[FilterValue]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(FilterValue, session)

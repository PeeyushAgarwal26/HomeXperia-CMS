import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.common.base_repository import BaseRepository
from app.modules.room_categories.models import RoomCategory


class RoomCategoryRepository(BaseRepository[RoomCategory]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(RoomCategory, session)

    async def name_taken(self, name: str, exclude_id: uuid.UUID | None = None) -> bool:
        stmt = self._base_select().where(RoomCategory.name == name)
        if exclude_id is not None:
            stmt = stmt.where(RoomCategory.id != exclude_id)
        result = await self.session.execute(stmt.limit(1))
        return result.first() is not None

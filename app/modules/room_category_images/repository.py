from sqlalchemy.ext.asyncio import AsyncSession

from app.common.base_repository import BaseRepository
from app.modules.room_category_images.models import RoomCategoryImage, RoomCategoryImageHotspot


class RoomCategoryImageRepository(BaseRepository[RoomCategoryImage]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(RoomCategoryImage, session)


class RoomCategoryImageHotspotRepository(BaseRepository[RoomCategoryImageHotspot]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(RoomCategoryImageHotspot, session)

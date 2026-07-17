from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import BaseModel


class RoomCategory(BaseModel):
    """Master -> Room Category. Room types (BEDROOM, LIVING ROOM, ...) a customer
    picks when shopping/scanning — a level above Parent Category's AR-detectable
    zones (WALL/FLOOR/WINDOW/BED/SOFA/FURNITURE). Reference UI has no Delete on
    this list (Add/Edit + Activate/Deactivate only), matching Child Category's
    original scope — see docs/06-legacy-site-audit.md."""

    __tablename__ = "room_categories"

    name: Mapped[str] = mapped_column(String(250), nullable=False)
    order_no: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    icon_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

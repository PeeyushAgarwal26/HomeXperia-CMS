import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base, BaseModel


class RoomCategoryImage(BaseModel):
    """Room Category -> "Manage Images". One lifestyle photo per row, scoped to a
    single room category, with per-image supplier scoping ("Map Suppliers") and a
    CDN upload flag. The real site's shoppable-hotspot editor on this same screen
    (bounding boxes, labels, confidence scores, mask images) is deliberately not
    modeled yet — out of scope for this pass, see docs/06-legacy-site-audit.md."""

    __tablename__ = "room_category_images"

    room_category_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("room_categories.id", ondelete="CASCADE"), nullable=False
    )
    order_no: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    image_url: Mapped[str] = mapped_column(String(500), nullable=False)
    # Real AWS/CDN push isn't wired up yet — the frontend's "Upload to CDN" action
    # just flips this flag so the button/column aren't a dead facade while that
    # infrastructure work is deferred.
    is_uploaded_to_cdn: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class RoomCategoryImageSupplier(Base):
    """Junction table — "Map Suppliers" on a Room Category Image, full-replace-on-save."""

    __tablename__ = "room_category_image_suppliers"

    room_category_image_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("room_category_images.id", ondelete="CASCADE"), primary_key=True
    )
    supplier_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("suppliers.id", ondelete="CASCADE"), primary_key=True
    )
    mapped_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("admin_users.id"), nullable=True
    )
    mapped_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

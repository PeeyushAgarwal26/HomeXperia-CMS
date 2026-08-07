import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base, BaseModel


class RoomCategoryImage(BaseModel):
    """Room Category -> "Manage Images". One lifestyle photo per row, scoped to a
    single room category, with per-image supplier scoping ("Map Suppliers") and a
    CDN upload flag. Its shoppable-hotspot editor (AR product-zone markers,
    mask images) is modeled separately — see RoomCategoryImageHotspot below."""

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


class RoomCategoryImageHotspot(BaseModel):
    """Room Category Image -> Hotspots. AR product-zone markers the client
    visualizer needs to know where to composite textures (a window's
    curtain zone, a floor's rug zone, etc). Confirmed against the real
    .NET admin's live "Configure Hotspot" editor: `type`/`sub_type` mirror
    that screen's Category/Sub Category dropdowns (Parent/Child Category
    names, lowercased) — options/confidence/description are real editable
    fields there too, just empty on the specific hotspots inspected first;
    x/y are normalized (0-1) point coordinates, detected from wherever the
    admin clicks on the image — not manually entered.
    mask_image_url is generated via generate_hotspot_mask (reuses the same
    SAM integration as the visualizer's mask-generation), or can be
    replaced with a manually uploaded image."""

    __tablename__ = "room_category_image_hotspots"
    __table_args__ = (Index("ix_room_category_image_hotspots_image_id", "room_category_image_id"),)

    room_category_image_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("room_category_images.id", ondelete="CASCADE"), nullable=False
    )
    label: Mapped[str] = mapped_column(String(250), nullable=False)
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    sub_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    options: Mapped[str | None] = mapped_column(String(500), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Numeric(4, 3), nullable=True)
    description: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    mask_image_url: Mapped[str] = mapped_column(String(500), nullable=False)
    is_uploaded_to_cdn: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    x: Mapped[float] = mapped_column(Numeric(6, 4), nullable=False)
    y: Mapped[float] = mapped_column(Numeric(6, 4), nullable=False)
    order_no: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

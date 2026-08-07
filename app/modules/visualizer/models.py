import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base, BaseModel


class UsageLog(BaseModel):
    """Ported from the Flask visualizer's usage_logs table. One row per
    room-render (source='process_room') or per curtain-generation attempt
    (source='curtain_generation'), updated in place as later steps (mask
    lookup increments, segmentation result) complete. customer_id replaces
    Flask's bare customer_code string — every request is now authenticated,
    so there's a real Customer row behind every entry, not a loose tracking
    string. See docs/06-legacy-site-audit.md-equivalent research for the
    original schema this mirrors."""

    __tablename__ = "usage_logs"
    __table_args__ = (UniqueConstraint("room_id", "customer_id", name="uq_usage_logs_room_customer"),)

    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id", ondelete="CASCADE"), nullable=False
    )
    room_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    curtain_style: Mapped[str | None] = mapped_column(String(100), nullable=True)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    openai_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    segmentation_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    generation_units: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tooltip_units: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error: Mapped[str | None] = mapped_column(String(2000), nullable=True)


class TooltipUsage(Base):
    """Ported from the Flask visualizer's tooltip_usages table. Append-only —
    one row per (room, hotspot, customer) the first time that hotspot is
    applied; a repeat application is a no-op via the unique constraint.
    Matches CustomerLoginEvent's shape (bare Base, no updated_at) rather than
    BaseModel, for the same reason: nothing here is ever mutated."""

    __tablename__ = "tooltip_usages"
    __table_args__ = (
        UniqueConstraint(
            "room_id", "hotspot_id", "customer_id", name="uq_tooltip_usages_room_hotspot_customer"
        ),
        Index("ix_tooltip_usages_customer_id", "customer_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id", ondelete="CASCADE"), nullable=False
    )
    room_id: Mapped[str] = mapped_column(String(255), nullable=False)
    hotspot_id: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

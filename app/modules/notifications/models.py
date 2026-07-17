import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, BaseModel, SoftDeleteMixin


class NotificationTemplate(BaseModel, SoftDeleteMixin):
    """Notification -> Template. is_sent is always False today — see
    docs/06-legacy-site-audit.md: the real site's "Is Sync" flips once a
    background job actually pushes the notification at scheduled_at, but
    that delivery mechanism (SMS? push? email?) isn't decided yet, so this
    rebuild stores the template + targeting only and never sends anything.

    is_active is the eligibility gate for that future send job: a deactivated
    template must NOT be sent even once scheduled_at is reached, no matter how
    that job ends up checking for due notifications. Once is_sent is True the
    row is a fired, historical record — the service layer blocks update/
    delete/set_status on it (nothing about it should change after the fact)."""

    __tablename__ = "notification_templates"

    heading: Mapped[str] = mapped_column(String(250), nullable=False)
    message: Mapped[str] = mapped_column(String(2000), nullable=False)
    image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_sent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class NotificationTemplateSupplier(Base):
    """Junction table — the literal contents of one template's "Map Suppliers" selection."""

    __tablename__ = "notification_template_suppliers"

    template_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("notification_templates.id", ondelete="CASCADE"), primary_key=True
    )
    supplier_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("suppliers.id", ondelete="CASCADE"), primary_key=True
    )

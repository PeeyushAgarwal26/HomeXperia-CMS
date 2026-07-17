import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, SmallInteger, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base, BaseModel, SoftDeleteMixin
from app.modules.geo.models import State


class Customer(BaseModel, SoftDeleteMixin):
    """User Management -> Customer. See docs/02-database-schema.md."""

    __tablename__ = "customers"
    __table_args__ = (
        Index(
            "ix_customers_customer_code", "customer_code", unique=True, postgresql_where="deleted_at IS NULL"
        ),
        Index(
            "ix_customers_phone_number", "phone_number", unique=True, postgresql_where="deleted_at IS NULL"
        ),
        Index("ix_customers_email", "email", unique=True, postgresql_where="deleted_at IS NULL"),
        Index("ix_customers_is_active", "is_active"),
        Index("ix_customers_state_code", "state_code"),
    )

    name: Mapped[str] = mapped_column(String(250), nullable=False)
    date_of_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone_number: Mapped[str] = mapped_column(String(20), nullable=False)
    gst_number: Mapped[str | None] = mapped_column(String(20), nullable=True)
    address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    pin_code: Mapped[str | None] = mapped_column(String(10), nullable=True)
    state_code: Mapped[str | None] = mapped_column(String(10), ForeignKey("states.code"), nullable=True)
    state: Mapped[State | None] = relationship(State, lazy="joined")
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    profile_image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    device_limit: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1)
    active_device_count: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    customer_code: Mapped[str] = mapped_column(String(100), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("admin_users.id"), nullable=True
    )


class CustomerSupplier(Base):
    """Junction table — the literal contents of one customer's Map Suppliers selection."""

    __tablename__ = "customer_suppliers"

    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id", ondelete="CASCADE"), primary_key=True
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

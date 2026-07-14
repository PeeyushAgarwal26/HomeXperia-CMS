import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base, BaseModel, SoftDeleteMixin
from app.modules.geo.models import State


class Supplier(BaseModel, SoftDeleteMixin):
    """User Management -> Suppliers. See docs/02-database-schema.md."""

    __tablename__ = "suppliers"
    __table_args__ = (
        Index("ix_suppliers_username", "username", unique=True, postgresql_where="deleted_at IS NULL"),
        Index(
            "ix_suppliers_phone_number", "phone_number", unique=True, postgresql_where="deleted_at IS NULL"
        ),
        Index("ix_suppliers_is_active", "is_active"),
        Index("ix_suppliers_state_code", "state_code"),
    )

    name: Mapped[str] = mapped_column(String(150), nullable=False)
    start_of_subscription: Mapped[date | None] = mapped_column(Date, nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone_number: Mapped[str] = mapped_column(String(20), nullable=False)
    gst_number: Mapped[str | None] = mapped_column(String(20), nullable=True)
    address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    pin_code: Mapped[str | None] = mapped_column(String(10), nullable=True)
    state_code: Mapped[str] = mapped_column(String(10), ForeignKey("states.code"), nullable=False)
    state: Mapped[State] = relationship(State, lazy="joined")
    city: Mapped[str] = mapped_column(String(100), nullable=False)
    web_link: Mapped[str | None] = mapped_column(String(500), nullable=True)
    logo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    username: Mapped[str] = mapped_column(String(100), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("admin_users.id"), nullable=True
    )


class SupplierChildCategory(Base):
    """Junction table — "Supplier Categories Access", full-replace-on-save."""

    __tablename__ = "supplier_child_categories"

    supplier_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("suppliers.id", ondelete="CASCADE"), primary_key=True
    )
    child_category_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("child_categories.id", ondelete="CASCADE"), primary_key=True
    )
    granted_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("admin_users.id"), nullable=True
    )
    granted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class SupplierModulePermission(Base):
    """Junction table, structurally identical to admin_user_module_permissions — stored
    for a supplier-facing portal that isn't built in this rebuild. See
    docs/02-database-schema.md and docs/06-legacy-site-audit.md §6."""

    __tablename__ = "supplier_module_permissions"

    supplier_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("suppliers.id", ondelete="CASCADE"), primary_key=True
    )
    module_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("modules.id", ondelete="CASCADE"), primary_key=True
    )
    granted_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("admin_users.id"), nullable=True
    )
    granted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

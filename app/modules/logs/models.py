import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base


class CustomerLoginEvent(Base):
    """One row per customer app login. See docs/02-database-schema.md —
    inert in this rebuild, nothing writes here without a customer-facing
    app login flow, which is out of scope. Append-only, so no updated_at —
    matches RefreshToken's precedent, not the full BaseModel shape."""

    __tablename__ = "customer_login_events"
    __table_args__ = (Index("ix_customer_login_events_customer_id_logged_in_at", "customer_id", "logged_in_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id", ondelete="CASCADE"), nullable=False
    )
    logged_in_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)


class AdminUserLoginEvent(Base):
    """One row per successful admin_users login (super admin or sub-admin) — written
    by AuthService.login(), not on /refresh. Feeds the unified "Login History" list
    (Logs -> Login History), filtered to non-super-admin rows there by default."""

    __tablename__ = "admin_user_login_events"
    __table_args__ = (Index("ix_admin_user_login_events_admin_user_id_logged_in_at", "admin_user_id", "logged_in_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    admin_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("admin_users.id", ondelete="CASCADE"), nullable=False
    )
    logged_in_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)


class SupplierLoginEvent(Base):
    """One row per successful supplier login — written by SupplierAuthService.login(),
    not on /refresh. Feeds the same unified "Login History" list as AdminUserLoginEvent."""

    __tablename__ = "supplier_login_events"
    __table_args__ = (Index("ix_supplier_login_events_supplier_id_logged_in_at", "supplier_id", "logged_in_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    supplier_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("suppliers.id", ondelete="CASCADE"), nullable=False
    )
    logged_in_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)

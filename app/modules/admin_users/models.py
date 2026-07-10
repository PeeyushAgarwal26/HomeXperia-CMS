import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base, BaseModel, SoftDeleteMixin


class AdminUser(BaseModel, SoftDeleteMixin):
    """Both the super admin and every sub-admin — one table, distinguished by is_super_admin."""

    __tablename__ = "admin_users"
    __table_args__ = (
        Index(
            "ix_admin_users_username", "username", unique=True, postgresql_where="deleted_at IS NULL"
        ),
        Index("ix_admin_users_email", "email", unique=True, postgresql_where="deleted_at IS NULL"),
        Index(
            "ix_admin_users_phone_number",
            "phone_number",
            unique=True,
            postgresql_where="deleted_at IS NULL",
        ),
        Index("ix_admin_users_is_active", "is_active"),
        Index("ix_admin_users_state_code", "state_code"),
    )

    is_super_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    date_of_birth: Mapped[date | None] = mapped_column(Date, nullable=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    phone_number: Mapped[str] = mapped_column(String(20), nullable=False)
    address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    pin_code: Mapped[str] = mapped_column(String(10), nullable=False)
    state_code: Mapped[str] = mapped_column(String(10), ForeignKey("states.code"), nullable=False)
    city: Mapped[str] = mapped_column(String(100), nullable=False)
    profile_image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    username: Mapped[str] = mapped_column(String(100), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("admin_users.id"), nullable=True
    )


class AdminUserModulePermission(Base):
    """Junction table — the literal contents of one sub-admin's Assign Access selection.

    Composite PK, no separate id/updated_at — a full replace on save (delete all
    rows for admin_user_id, insert the checked set) is simpler than diffing.
    """

    __tablename__ = "admin_user_module_permissions"

    admin_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("admin_users.id", ondelete="CASCADE"), primary_key=True
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

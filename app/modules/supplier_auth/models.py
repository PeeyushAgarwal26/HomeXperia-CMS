import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base


class SupplierRefreshToken(Base):
    """Mirrors auth.models.RefreshToken but scoped to suppliers — kept in its own
    table rather than reusing `refresh_tokens` (whose FK is hard-wired to
    admin_users.id) so an admin session and a supplier session can never be
    interchangeable, even in principle."""

    __tablename__ = "supplier_refresh_tokens"
    __table_args__ = (Index("ix_supplier_refresh_tokens_supplier_id", "supplier_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    supplier_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("suppliers.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    issued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # See auth.models.RefreshToken.session_started_at — carried forward
    # unchanged on every rotation, used to enforce the absolute session cap
    # independent of how recently the token itself was rotated.
    session_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)

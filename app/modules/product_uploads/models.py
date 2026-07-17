import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base
from app.modules.suppliers.models import Supplier


class ProductUploadLog(Base):
    """Upload Product -> Log. One row per bulk-import run (an Excel + optional
    images zip submitted for one supplier). Append-only — a run's outcome
    doesn't change after the fact, so no updated_at/soft-delete."""

    __tablename__ = "product_upload_logs"
    __table_args__ = (Index("ix_product_upload_logs_supplier_id", "supplier_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    supplier_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("suppliers.id"), nullable=False
    )
    supplier: Mapped[Supplier] = relationship(Supplier, lazy="joined")
    uploaded_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("admin_users.id"), nullable=False
    )
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    total_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    success_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # "success" (every row imported) | "partial" (some rows imported, some failed) |
    # "failed" (nothing imported — either every row failed or the run itself errored,
    # e.g. a corrupt file; error_message explains the latter case).
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    error_message: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ProductUploadLogItem(Base):
    """One row per spreadsheet row processed by a run — success or the exact reason it failed."""

    __tablename__ = "product_upload_log_items"
    __table_args__ = (Index("ix_product_upload_log_items_log_id", "log_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    log_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("product_upload_logs.id", ondelete="CASCADE"), nullable=False
    )
    row_no: Mapped[int] = mapped_column(Integer, nullable=False)
    catalog_name: Mapped[str | None] = mapped_column(String(250), nullable=True)
    is_success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    # "created" | "updated" when is_success — an existing (supplier, bar_code) match is updated
    # in place rather than duplicated, so a re-uploaded sheet is safe to submit again. Null on failure.
    action: Mapped[str | None] = mapped_column(String(20), nullable=True)
    message: Mapped[str | None] = mapped_column(String(1000), nullable=True)

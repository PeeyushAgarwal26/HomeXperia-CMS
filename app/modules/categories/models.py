import uuid

from sqlalchemy import Boolean, ForeignKey, Index, SmallInteger, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import BaseModel


class ParentCategory(BaseModel):
    """Read-only reference data — see docs/02-database-schema.md. No CRUD surface yet;
    exists only so Suppliers -> Supplier Categories Access has real rows to grant."""

    __tablename__ = "parent_categories"

    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    icon_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    sort_order: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class ChildCategory(BaseModel):
    __tablename__ = "child_categories"
    __table_args__ = (Index("ix_child_categories_parent_category_id", "parent_category_id"),)

    parent_category_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("parent_categories.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    icon_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    sort_order: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

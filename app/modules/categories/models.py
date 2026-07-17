import uuid

from sqlalchemy import Boolean, ForeignKey, Index, SmallInteger, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import BaseModel, SoftDeleteMixin


class ParentCategory(BaseModel, SoftDeleteMixin):
    """Full Add/Edit/Delete + Activate/Deactivate — deliberately more open than
    the reference UI (which only allows Edit + Deactivate, see
    docs/06-legacy-site-audit.md §8); the client wants Parent Category
    fully self-service rather than locked to a fixed 6-row list."""

    __tablename__ = "parent_categories"
    __table_args__ = (
        Index("ix_parent_categories_name", "name", unique=True, postgresql_where="deleted_at IS NULL"),
    )

    name: Mapped[str] = mapped_column(String(250), nullable=False)
    icon_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    sort_order: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class ChildCategory(BaseModel, SoftDeleteMixin):
    __tablename__ = "child_categories"
    __table_args__ = (Index("ix_child_categories_parent_category_id", "parent_category_id"),)

    parent_category_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("parent_categories.id"), nullable=False
    )
    parent_category: Mapped[ParentCategory] = relationship(ParentCategory, lazy="joined")
    name: Mapped[str] = mapped_column(String(250), nullable=False)
    icon_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    sort_order: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

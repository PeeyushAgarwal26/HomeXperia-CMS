import uuid

from sqlalchemy import Boolean, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import BaseModel, SoftDeleteMixin
from app.modules.categories.models import ChildCategory
from app.modules.suppliers.models import Supplier


class Filter(BaseModel, SoftDeleteMixin):
    """Master -> Filter. An attribute type (e.g. "Shine Fabric"); its concrete values
    live in FilterValue, each scoped to a supplier and child category."""

    __tablename__ = "filters"
    __table_args__ = (Index("ix_filters_name", "name", unique=True, postgresql_where="deleted_at IS NULL"),)

    name: Mapped[str] = mapped_column(String(250), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class FilterValue(BaseModel, SoftDeleteMixin):
    """Master -> Filter Value. A supplier-specific product attribute value under one
    Filter and one Child Category — e.g. Filter "Shine Fabric", Child Category "Sofa",
    Supplier "Supplier2", Value "Glossy"."""

    __tablename__ = "filter_values"
    __table_args__ = (
        Index("ix_filter_values_filter_id", "filter_id"),
        Index("ix_filter_values_child_category_id", "child_category_id"),
        Index("ix_filter_values_supplier_id", "supplier_id"),
    )

    filter_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("filters.id"), nullable=False)
    filter: Mapped[Filter] = relationship(Filter, lazy="joined")
    child_category_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("child_categories.id"), nullable=False
    )
    child_category: Mapped[ChildCategory] = relationship(ChildCategory, lazy="joined")
    supplier_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("suppliers.id"), nullable=False
    )
    supplier: Mapped[Supplier] = relationship(Supplier, lazy="joined")
    value: Mapped[str] = mapped_column(String(250), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

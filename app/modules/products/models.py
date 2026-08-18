import uuid

from sqlalchemy import Boolean, ForeignKey, Index, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, BaseModel, SoftDeleteMixin
from app.modules.categories.models import ChildCategory
from app.modules.suppliers.models import Supplier


class Product(BaseModel, SoftDeleteMixin):
    """Master -> Product. The real product catalog — each product belongs to one
    supplier's catalog under one Child Category. Which attributes (Color, Brand,
    Pattern, etc.) apply is fully dynamic — driven by whatever Filter Values exist
    for this product's Child Category + Supplier — hence the ProductFilterValue
    junction table below, not fixed columns."""

    __tablename__ = "products"
    __table_args__ = (
        Index("ix_products_child_category_id", "child_category_id"),
        Index("ix_products_supplier_id", "supplier_id"),
        Index("ix_products_bar_code", "bar_code"),
        Index("ix_products_is_active", "is_active"),
    )

    child_category_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("child_categories.id"), nullable=False
    )
    child_category: Mapped[ChildCategory] = relationship(ChildCategory, lazy="joined")
    supplier_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("suppliers.id"), nullable=False
    )
    supplier: Mapped[Supplier] = relationship(Supplier, lazy="joined")
    order_no: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    catalog_name: Mapped[str | None] = mapped_column(String(250), nullable=True)
    design_no: Mapped[str | None] = mapped_column(String(100), nullable=True)
    bar_code: Mapped[str] = mapped_column(String(100), nullable=False)
    image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    available_quantity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rate: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    length: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    width: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class ProductFilterValue(Base):
    """Junction table — the literal contents of one product's dynamic "Product Filters"
    selections (Color, Brand, Pattern, etc.). Which Filters are even offered depends on
    the product's Child Category + Supplier, not a fixed set per product."""

    __tablename__ = "product_filter_values"

    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), primary_key=True
    )
    filter_value_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("filter_values.id", ondelete="CASCADE"), primary_key=True
    )

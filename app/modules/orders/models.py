import uuid

from sqlalchemy import ForeignKey, Index, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, BaseModel


class Cart(BaseModel):
    """A customer's (retailer/showroom account's) in-progress cart, persisted
    server-side for the storefront's "Lock Cart" step. Not read by, or
    written to, order placement — the real /order/save-order call takes its
    line items inline, independently of whatever's in here. One "open" cart
    per customer at a time (see the partial unique index below); placing an
    order never touches it."""

    __tablename__ = "carts"
    __table_args__ = (
        Index("ux_carts_customer_open", "customer_id", unique=True, postgresql_where="status = 'open'"),
    )

    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="open")


class CartItem(Base):
    """No rate/amount here on purpose — cart pricing is always computed live
    from the product's current rate when read, so it can never go stale
    while sitting in a cart. Only a placed Order freezes pricing."""

    __tablename__ = "cart_items"
    __table_args__ = (Index("ix_cart_items_cart_id", "cart_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cart_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("carts.id", ondelete="CASCADE"), nullable=False
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    uom: Mapped[str] = mapped_column(String(50), nullable=False)


class Order(BaseModel):
    """The real /order/save-order request conflates three distinct parties:
    the logged-in retailer/showroom account (customer_id, identified purely
    via JWT — never a body field), the end consumer the order is for
    ("client" — free-text, no table of its own today), and a showroom
    owner contact. Internally named owner_email/owner_whatsapp_no here
    (the real frontend payload calls these customer_email/
    customer_whatsapp_no, which is confusing since it's not the logged-in
    customer) — see OrderCreateRequest in schemas.py for the wire-format
    mapping."""

    __tablename__ = "orders"

    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id", ondelete="CASCADE"), nullable=False
    )
    invoice_number: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    client_name: Mapped[str] = mapped_column(String(250), nullable=False)
    client_email: Mapped[str] = mapped_column(String(255), nullable=False)
    client_whatsapp_no: Mapped[str] = mapped_column(String(20), nullable=False)
    owner_email: Mapped[str] = mapped_column(String(255), nullable=False)
    owner_whatsapp_no: Mapped[str] = mapped_column(String(20), nullable=False)
    total_amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    notes: Mapped[str | None] = mapped_column(String(1000), nullable=True)


class OrderItem(Base):
    """Snapshotted at order time — catalog_name/design_no/image_url/rate are
    copied from the product as it existed the moment the order was placed,
    so a later catalog edit (or deletion) never rewrites order history."""

    __tablename__ = "order_items"
    __table_args__ = (Index("ix_order_items_order_id", "order_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("orders.id", ondelete="CASCADE"), nullable=False
    )
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("products.id", ondelete="SET NULL"), nullable=True
    )
    catalog_name: Mapped[str] = mapped_column(String(250), nullable=False)
    design_no: Mapped[str | None] = mapped_column(String(100), nullable=True)
    image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Also snapshotted, same reasoning as catalog_name/design_no/rate above —
    # a product's supplier/category can change (or the product can be
    # deleted) without rewriting order history. "width" is the real Product
    # column shown as "Size" on the real .NET reference's order line items —
    # there's no single dedicated "size" field on Product to copy verbatim.
    supplier_name: Mapped[str | None] = mapped_column(String(250), nullable=True)
    category_name: Mapped[str | None] = mapped_column(String(250), nullable=True)
    width: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    uom: Mapped[str] = mapped_column(String(50), nullable=False)
    rate: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)

import uuid

from sqlalchemy import Float, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import BaseModel


class QrCatalogueEntry(BaseModel):
    """Replaces the old, hand-edited-per-QR customerCatalog.js static file —
    what a scanned QR's (customer_code, filter_value) pair actually resolves
    to: a room image + hotspot(s), each with its own product, to
    auto-select. One row per (customer, filter_value) combination, managed
    from the admin's QR Generator screen instead of a committed JS file +
    redeploy. Does NOT carry a single product_id — a room image can have
    several distinct hotspots (floor, wall, curtain, curtain...) that each
    need their own product, so the product lives per-hotspot on
    QrCatalogueEntryHotspot instead."""

    __tablename__ = "qr_catalogue_entries"
    __table_args__ = (
        UniqueConstraint("customer_id", "filter_value", name="uq_qr_catalogue_entry_customer_filter"),
    )

    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id", ondelete="CASCADE"), nullable=False
    )
    filter_value: Mapped[str] = mapped_column(String(250), nullable=False)
    catalog_name: Mapped[str] = mapped_column(String(250), nullable=False)
    room_category_image_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("room_category_images.id", ondelete="CASCADE"), nullable=False
    )
    # The room image's OWN photo/hotspots are shared master data — every
    # other customer/filter-value pointing at the same room_category_image_id
    # must keep seeing them exactly as uploaded. A curtain generated for
    # THIS mapping is scoped here instead, never written back onto the
    # shared row: NULL means "show the room's own photo as-is" (no curtain
    # needed for this mapping's hotspots).
    override_image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)


class SavedQrCode(BaseModel):
    """A QR code the admin explicitly chose to keep after generating it —
    separate from QrCatalogueEntry (which is the customer_code+filter_value
    -> room/product resolution data a scan reads); this is just a record of
    "this PNG, for this customer/filter-value(s)/logo, was generated on this
    date" for the admin's own "Generated QR Codes" list. Generating a QR
    doesn't save one automatically — only clicking Save does."""

    __tablename__ = "saved_qr_codes"

    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id", ondelete="CASCADE"), nullable=False
    )
    # Comma-joined, mirroring the exact same joining _build_verify_url uses
    # for the QR's own encoded URL — not a separate list table, since this
    # is a read-only record of what was generated, never queried per-value.
    filter_values: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    brand_logo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    image_url: Mapped[str] = mapped_column(String(500), nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("admin_users.id"), nullable=True
    )


class QrCatalogueEntryHotspot(BaseModel):
    """A catalogue entry can tie together more than one hotspot (e.g. curtain
    + rug changing together), and each gets its OWN product: a floor hotspot
    and a curtain hotspot on the same room image are never going to share
    one product, so the product is scoped per-hotspot here rather than once
    per entry.

    hotspot_id is NULLABLE: a real, pre-existing room hotspot (floor, wall —
    never needs a curtain) is referenced by id as normal, but a curtain
    generated for THIS mapping is never written into the shared
    room_category_image_hotspots table (see QrCatalogueEntry.
    override_image_url's docstring for why) — its geometry travels inline on
    this row instead via the x/y/type/label/mask_image_url columns, which
    are unused whenever hotspot_id is set."""

    __tablename__ = "qr_catalogue_entry_hotspots"
    __table_args__ = (Index("ix_qr_catalogue_entry_hotspots_entry_id", "qr_catalogue_entry_id"),)

    qr_catalogue_entry_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("qr_catalogue_entries.id", ondelete="CASCADE"), nullable=False
    )
    hotspot_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("room_category_image_hotspots.id", ondelete="CASCADE"), nullable=True
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )
    inline_label: Mapped[str | None] = mapped_column(String(250), nullable=True)
    inline_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    inline_x: Mapped[float | None] = mapped_column(Float, nullable=True)
    inline_y: Mapped[float | None] = mapped_column(Float, nullable=True)
    inline_mask_image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

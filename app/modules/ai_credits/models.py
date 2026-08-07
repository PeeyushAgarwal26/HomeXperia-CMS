import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base, BaseModel

# Every AI-credit-owning table below is owned by EITHER a Supplier OR a
# Customer directly — never both, never neither. A plain customer (a shop
# keeper who never supplies anything) can hold their own credit account
# exactly like a supplier does; nothing requires them to also become a
# supplier just to have a balance. Enforced by this one shared constraint
# on every such table, not just a naming convention.
_EXACTLY_ONE_OWNER = "(supplier_id IS NOT NULL) != (customer_id IS NOT NULL)"


class SupplierAiCreditSettings(BaseModel):
    """One row per account owner (a Supplier OR a Customer, never both) —
    the manually-entered monthly allocation the Homexperia team sets
    (Step-3), plus a purely descriptive Tier label used for reporting only.
    Kept as its own table rather than growing Supplier/Customer themselves,
    same precedent as SupplierCustomerTheme."""

    __tablename__ = "supplier_ai_credit_settings"
    __table_args__ = (
        CheckConstraint(_EXACTLY_ONE_OWNER, name="ck_ai_credit_settings_exactly_one_owner"),
        Index(
            "ix_ai_credit_settings_supplier_id", "supplier_id", unique=True, postgresql_where="supplier_id IS NOT NULL"
        ),
        Index(
            "ix_ai_credit_settings_customer_id", "customer_id", unique=True, postgresql_where="customer_id IS NOT NULL"
        ),
    )

    supplier_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("suppliers.id", ondelete="CASCADE"), nullable=True
    )
    customer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id", ondelete="CASCADE"), nullable=True
    )
    monthly_base_allocation: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tier: Mapped[str | None] = mapped_column(String(50), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class SupplierAiCreditBatch(BaseModel):
    """One dated 'batch' of credits per credit-adding event — either a
    monthly allocation (written by the rollover cron) or a manual top-up
    (Step-4) — owned by EITHER a Supplier OR a Customer directly, same as
    SupplierAiCreditSettings above. amount_remaining is decremented FIFO
    (oldest batch_date first) as usage events charge credits — see
    AiCreditService.charge_credit. This per-batch accounting (rather than
    one running total) is what makes Step-9's "only the last 3 months'
    unused credits carry into the next year" rule well-defined: at an
    annual rollover, batches from the closing year's months 1-9 that still
    hold any amount_remaining are explicitly lapsed, while months 10-12
    keep rolling forward untouched."""

    __tablename__ = "supplier_ai_credit_batches"
    __table_args__ = (
        CheckConstraint(_EXACTLY_ONE_OWNER, name="ck_ai_credit_batches_exactly_one_owner"),
        Index("ix_supplier_ai_credit_batches_supplier_date", "supplier_id", "batch_date"),
        Index("ix_supplier_ai_credit_batches_customer_date", "customer_id", "batch_date"),
    )

    supplier_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("suppliers.id", ondelete="CASCADE"), nullable=True
    )
    customer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id", ondelete="CASCADE"), nullable=True
    )
    batch_date: Mapped[date] = mapped_column(Date, nullable=False)
    amount_granted: Mapped[int] = mapped_column(Integer, nullable=False)
    amount_remaining: Mapped[int] = mapped_column(Integer, nullable=False)
    subscription_year_number: Mapped[int] = mapped_column(Integer, nullable=False)
    source: Mapped[str] = mapped_column(String(30), nullable=False)  # monthly_allocation | manual_topup
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("admin_users.id"), nullable=True
    )


class SupplierAiCreditLedgerEntry(BaseModel):
    """One frozen snapshot per account owner per closed calendar month,
    written once by the monthly rollover cron and never recomputed
    afterwards — this is what makes the Balance Sheet Matrix's "Previous
    Month" row a stable, auditable figure rather than something that could
    silently drift if later usage rows are corrected. Owned by EITHER a
    Supplier OR a Customer directly, same as the tables above. The
    UniqueConstraints are the cron's idempotency guard: safe to re-run for
    the same month any number of times."""

    __tablename__ = "supplier_ai_credit_ledger_entries"
    __table_args__ = (
        CheckConstraint(_EXACTLY_ONE_OWNER, name="ck_ai_credit_ledger_exactly_one_owner"),
        UniqueConstraint("supplier_id", "period_start", name="uq_ai_credit_ledger_supplier_period"),
        UniqueConstraint("customer_id", "period_start", name="uq_ai_credit_ledger_customer_period"),
    )

    supplier_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("suppliers.id", ondelete="CASCADE"), nullable=True
    )
    customer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id", ondelete="CASCADE"), nullable=True
    )
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    credits_allocated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    credits_carried_forward: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    credits_used_mask_generated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    credits_used_curtain_applied: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    credits_purchased: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    closing_balance: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    credits_lapsed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class AiCreditTransaction(Base):
    """Append-only, atomic per-event row backing the Real-Time Consumption
    Audit Log — logged for EVERY attempt, including free ones (a tooltip
    re-render is 0 credits but still shows up, per the wireframe's own
    sample rows). credits_charged is 0 or 1; action_type distinguishes what
    happened. Not a BaseModel row (no updated_at) — these are immutable
    facts, never edited after insert.

    Two distinct customer-shaped columns, deliberately not merged: `customer_id`
    is always the acting identity (whoever was actually logged in and using
    the visualizer); `billed_customer_id` is set only when that action was
    billed directly to that same customer's OWN credit account rather than
    to a supplier's (`supplier_id`) or left unattributed (both null). For a
    supplier's own linked-customer identity, `customer_id` is set but
    `billed_customer_id` stays null — the bill lands on `supplier_id`
    instead."""

    __tablename__ = "ai_credit_transactions"
    __table_args__ = (
        Index("ix_ai_credit_transactions_supplier_created", "supplier_id", "created_at"),
        Index("ix_ai_credit_transactions_billed_customer_created", "billed_customer_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    supplier_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("suppliers.id", ondelete="CASCADE"), nullable=True
    )
    billed_customer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id", ondelete="CASCADE"), nullable=True
    )
    customer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id"), nullable=True
    )
    room_id: Mapped[str | None] = mapped_column(String(250), nullable=True)
    room_category_name: Mapped[str | None] = mapped_column(String(250), nullable=True)
    is_curtain_room: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    action_type: Mapped[str] = mapped_column(String(30), nullable=False)
    tooltip_element_label: Mapped[str | None] = mapped_column(String(250), nullable=True)
    product_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("products.id"), nullable=True)
    credits_charged: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

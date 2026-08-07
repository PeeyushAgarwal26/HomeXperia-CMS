import uuid
from dataclasses import dataclass
from datetime import date
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.base_repository import BaseRepository
from app.modules.ai_credits.models import (
    AiCreditTransaction,
    SupplierAiCreditBatch,
    SupplierAiCreditLedgerEntry,
    SupplierAiCreditSettings,
)
from app.modules.customers.models import Customer
from app.modules.suppliers.models import Supplier

MASK_GENERATED_ACTIONS = ("first_tooltip_render",)
CURTAIN_APPLIED_ACTIONS = ("curtain_applied",)

OwnerType = Literal["supplier", "customer"]


@dataclass(frozen=True)
class AccountKey:
    """Every AI-credit-owning table is owned by EITHER a Supplier OR a
    Customer directly (see models.py's shared CHECK constraint) — this is
    the one place that distinction is represented in code, so every
    repository method below takes one of these instead of a bare
    supplier_id. Never construct owner_type/owner_id by hand elsewhere."""

    owner_type: OwnerType
    owner_id: uuid.UUID

    @property
    def supplier_id(self) -> uuid.UUID | None:
        return self.owner_id if self.owner_type == "supplier" else None

    @property
    def customer_id(self) -> uuid.UUID | None:
        return self.owner_id if self.owner_type == "customer" else None

    @staticmethod
    def for_supplier(supplier_id: uuid.UUID) -> "AccountKey":
        return AccountKey("supplier", supplier_id)

    @staticmethod
    def for_customer(customer_id: uuid.UUID) -> "AccountKey":
        return AccountKey("customer", customer_id)


def _owner_clause(model, account: AccountKey):
    return model.supplier_id == account.owner_id if account.owner_type == "supplier" else model.customer_id == account.owner_id


class SupplierAiCreditSettingsRepository(BaseRepository[SupplierAiCreditSettings]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(SupplierAiCreditSettings, session)

    async def get_by_account(self, account: AccountKey) -> SupplierAiCreditSettings | None:
        stmt = select(SupplierAiCreditSettings).where(_owner_clause(SupplierAiCreditSettings, account))
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def upsert(
        self, account: AccountKey, monthly_base_allocation: int, tier: str | None
    ) -> SupplierAiCreditSettings:
        existing = await self.get_by_account(account)
        if existing is not None:
            existing.monthly_base_allocation = monthly_base_allocation
            existing.tier = tier
            await self.session.flush()
            return existing
        return await self.create(
            {
                "supplier_id": account.supplier_id,
                "customer_id": account.customer_id,
                "monthly_base_allocation": monthly_base_allocation,
                "tier": tier,
            }
        )

    async def list_active_supplier_accounts(self) -> list[tuple[SupplierAiCreditSettings, Supplier]]:
        stmt = (
            select(SupplierAiCreditSettings, Supplier)
            .join(Supplier, Supplier.id == SupplierAiCreditSettings.supplier_id)
            .where(SupplierAiCreditSettings.is_active.is_(True), Supplier.deleted_at.is_(None))
        )
        rows = (await self.session.execute(stmt)).all()
        return [(row[0], row[1]) for row in rows]

    async def list_active_customer_accounts(self) -> list[tuple[SupplierAiCreditSettings, Customer]]:
        stmt = (
            select(SupplierAiCreditSettings, Customer)
            .join(Customer, Customer.id == SupplierAiCreditSettings.customer_id)
            .where(SupplierAiCreditSettings.is_active.is_(True), Customer.deleted_at.is_(None))
        )
        rows = (await self.session.execute(stmt)).all()
        return [(row[0], row[1]) for row in rows]


class SupplierAiCreditBatchRepository(BaseRepository[SupplierAiCreditBatch]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(SupplierAiCreditBatch, session)

    async def create_batch(
        self,
        account: AccountKey,
        batch_date: date,
        amount: int,
        subscription_year_number: int,
        source: str,
        note: str | None = None,
        created_by: uuid.UUID | None = None,
    ) -> SupplierAiCreditBatch:
        return await self.create(
            {
                "supplier_id": account.supplier_id,
                "customer_id": account.customer_id,
                "batch_date": batch_date,
                "amount_granted": amount,
                "amount_remaining": amount,
                "subscription_year_number": subscription_year_number,
                "source": source,
                "note": note,
                "created_by": created_by,
            }
        )

    async def deduct_oldest_available(self, account: AccountKey) -> bool:
        """Atomically finds the single oldest batch (by batch_date, then
        created_at as a tiebreaker) with amount_remaining > 0 and decrements
        it by 1 — the FIFO consumption rule. Uses a blocking row lock (not
        SKIP LOCKED): under concurrent charges for the same account, each
        caller must wait its turn on the SAME oldest batch rather than
        racing ahead to a newer one, or FIFO ordering would be violated.
        Returns False if the account has no credits left anywhere."""
        stmt = (
            select(SupplierAiCreditBatch)
            .where(_owner_clause(SupplierAiCreditBatch, account), SupplierAiCreditBatch.amount_remaining > 0)
            .order_by(SupplierAiCreditBatch.batch_date.asc(), SupplierAiCreditBatch.created_at.asc())
            .limit(1)
            .with_for_update()
        )
        batch = (await self.session.execute(stmt)).scalar_one_or_none()
        if batch is None:
            return False
        batch.amount_remaining -= 1
        await self.session.flush()
        return True

    async def get_remaining_total(self, account: AccountKey) -> int:
        """SUM(amount_remaining) across every batch IS the account's current
        real-time balance — every credit ever granted is a batch, every
        credit used decrements one, so this invariant always holds."""
        stmt = select(func.coalesce(func.sum(SupplierAiCreditBatch.amount_remaining), 0)).where(
            _owner_clause(SupplierAiCreditBatch, account)
        )
        return (await self.session.execute(stmt)).scalar_one()

    async def list_by_account_and_year(
        self, account: AccountKey, subscription_year_number: int
    ) -> list[SupplierAiCreditBatch]:
        stmt = select(SupplierAiCreditBatch).where(
            _owner_clause(SupplierAiCreditBatch, account),
            SupplierAiCreditBatch.subscription_year_number == subscription_year_number,
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def get_batch(self, account: AccountKey, batch_date: date, source: str) -> SupplierAiCreditBatch | None:
        stmt = select(SupplierAiCreditBatch).where(
            _owner_clause(SupplierAiCreditBatch, account),
            SupplierAiCreditBatch.batch_date == batch_date,
            SupplierAiCreditBatch.source == source,
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def sum_topups_in_range(self, account: AccountKey, since: date, until: date) -> int:
        stmt = select(func.coalesce(func.sum(SupplierAiCreditBatch.amount_granted), 0)).where(
            _owner_clause(SupplierAiCreditBatch, account),
            SupplierAiCreditBatch.source == "manual_topup",
            SupplierAiCreditBatch.batch_date >= since,
            SupplierAiCreditBatch.batch_date < until,
        )
        return (await self.session.execute(stmt)).scalar_one()


class SupplierAiCreditLedgerRepository(BaseRepository[SupplierAiCreditLedgerEntry]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(SupplierAiCreditLedgerEntry, session)

    async def get_by_period(self, account: AccountKey, period_start: date) -> SupplierAiCreditLedgerEntry | None:
        stmt = select(SupplierAiCreditLedgerEntry).where(
            _owner_clause(SupplierAiCreditLedgerEntry, account),
            SupplierAiCreditLedgerEntry.period_start == period_start,
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list_last_n_months_aggregate(self, n: int) -> list[dict]:
        """Across ALL accounts (supplier- and customer-owned alike), grouped
        by period_start — feeds the Master Analytics Dashboard's
        issued-vs-consumed trend chart."""
        stmt = (
            select(
                SupplierAiCreditLedgerEntry.period_start,
                func.sum(SupplierAiCreditLedgerEntry.credits_allocated).label("issued"),
                func.sum(
                    SupplierAiCreditLedgerEntry.credits_used_mask_generated
                    + SupplierAiCreditLedgerEntry.credits_used_curtain_applied
                ).label("used"),
            )
            .group_by(SupplierAiCreditLedgerEntry.period_start)
            .order_by(SupplierAiCreditLedgerEntry.period_start.desc())
            .limit(n)
        )
        rows = (await self.session.execute(stmt)).all()
        return [dict(row._mapping) for row in reversed(rows)]


class AiCreditTransactionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_transaction(
        self,
        billed_account: AccountKey | None,
        customer_id: uuid.UUID | None,
        room_id: str | None,
        room_category_name: str | None,
        is_curtain_room: bool,
        action_type: str,
        tooltip_element_label: str | None,
        product_id: uuid.UUID | None,
        credits_charged: int,
    ) -> AiCreditTransaction:
        """billed_account is who the credit lands on (a supplier, a
        customer's own account, or None if unattributed) — always distinct
        from `customer_id`, the acting identity who was actually logged in
        and using the visualizer. For a supplier's own linked-customer
        identity, these differ (customer_id = their customer row,
        billed_account = their supplier row); for a plain customer with
        their own direct account, they're the same person by definition."""
        transaction = AiCreditTransaction(
            supplier_id=billed_account.supplier_id if billed_account else None,
            billed_customer_id=billed_account.customer_id if billed_account else None,
            customer_id=customer_id,
            room_id=room_id,
            room_category_name=room_category_name,
            is_curtain_room=is_curtain_room,
            action_type=action_type,
            tooltip_element_label=tooltip_element_label,
            product_id=product_id,
            credits_charged=credits_charged,
        )
        self.session.add(transaction)
        await self.session.flush()
        return transaction

    async def sum_used_by_category(
        self, account: AccountKey, since: date, until: date | None = None
    ) -> dict[str, int]:
        billed_clause = (
            AiCreditTransaction.supplier_id == account.owner_id
            if account.owner_type == "supplier"
            else AiCreditTransaction.billed_customer_id == account.owner_id
        )
        stmt = select(
            func.coalesce(
                func.sum(AiCreditTransaction.credits_charged).filter(
                    AiCreditTransaction.action_type.in_(MASK_GENERATED_ACTIONS)
                ),
                0,
            ).label("mask_generated"),
            func.coalesce(
                func.sum(AiCreditTransaction.credits_charged).filter(
                    AiCreditTransaction.action_type.in_(CURTAIN_APPLIED_ACTIONS)
                ),
                0,
            ).label("curtain_applied"),
        ).where(billed_clause, AiCreditTransaction.created_at >= since)
        if until is not None:
            stmt = stmt.where(AiCreditTransaction.created_at < until)
        row = (await self.session.execute(stmt)).one()
        return dict(row._mapping)

    async def list_paginated(
        self, account: AccountKey, offset: int, limit: int | None
    ) -> tuple[list[tuple[AiCreditTransaction, str | None, str | None]], int]:
        """Each row also carries the acting customer's name/code — joined
        explicitly rather than assumed, so the audit log never has to guess
        who did what."""
        billed_clause = (
            AiCreditTransaction.supplier_id == account.owner_id
            if account.owner_type == "supplier"
            else AiCreditTransaction.billed_customer_id == account.owner_id
        )
        base_stmt = select(AiCreditTransaction).where(billed_clause)
        total = await self.session.scalar(select(func.count()).select_from(base_stmt.subquery())) or 0

        stmt = (
            select(AiCreditTransaction, Customer.name, Customer.customer_code)
            .outerjoin(Customer, Customer.id == AiCreditTransaction.customer_id)
            .where(billed_clause)
            .order_by(AiCreditTransaction.created_at.desc())
            .offset(offset)
        )
        if limit is not None:
            stmt = stmt.limit(limit)
        result = await self.session.execute(stmt)
        return [(row[0], row[1], row[2]) for row in result.all()], total

    async def category_breakdown_all_accounts(self) -> dict[str, int]:
        stmt = select(
            AiCreditTransaction.action_type, func.sum(AiCreditTransaction.credits_charged)
        ).group_by(AiCreditTransaction.action_type)
        rows = (await self.session.execute(stmt)).all()
        return {row[0]: row[1] for row in rows}


class AiCreditDashboardRepository:
    """Read-only aggregate queries spanning ALL accounts (supplier- and
    customer-owned), for the Master Analytics Dashboard — kept separate
    from the per-account repositories above since these joins cut across
    settings/batches/transactions."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def top_consumers(self, period_start: date, limit: int = 20) -> list[dict]:
        usage_by_supplier = (
            select(
                AiCreditTransaction.supplier_id.label("owner_id"),
                func.coalesce(func.sum(AiCreditTransaction.credits_charged), 0).label("used_this_month"),
            )
            .where(AiCreditTransaction.created_at >= period_start, AiCreditTransaction.supplier_id.is_not(None))
            .group_by(AiCreditTransaction.supplier_id)
            .subquery()
        )
        usage_by_customer = (
            select(
                AiCreditTransaction.billed_customer_id.label("owner_id"),
                func.coalesce(func.sum(AiCreditTransaction.credits_charged), 0).label("used_this_month"),
            )
            .where(
                AiCreditTransaction.created_at >= period_start,
                AiCreditTransaction.billed_customer_id.is_not(None),
            )
            .group_by(AiCreditTransaction.billed_customer_id)
            .subquery()
        )
        balance_by_supplier = (
            select(
                SupplierAiCreditBatch.supplier_id.label("owner_id"),
                func.coalesce(func.sum(SupplierAiCreditBatch.amount_remaining), 0).label("balance"),
            )
            .where(SupplierAiCreditBatch.supplier_id.is_not(None))
            .group_by(SupplierAiCreditBatch.supplier_id)
            .subquery()
        )
        balance_by_customer = (
            select(
                SupplierAiCreditBatch.customer_id.label("owner_id"),
                func.coalesce(func.sum(SupplierAiCreditBatch.amount_remaining), 0).label("balance"),
            )
            .where(SupplierAiCreditBatch.customer_id.is_not(None))
            .group_by(SupplierAiCreditBatch.customer_id)
            .subquery()
        )

        supplier_stmt = (
            select(
                Supplier.id,
                Supplier.name,
                SupplierAiCreditSettings.tier,
                SupplierAiCreditSettings.monthly_base_allocation,
                func.coalesce(usage_by_supplier.c.used_this_month, 0),
                func.coalesce(balance_by_supplier.c.balance, 0),
            )
            .join(SupplierAiCreditSettings, SupplierAiCreditSettings.supplier_id == Supplier.id)
            .outerjoin(usage_by_supplier, usage_by_supplier.c.owner_id == Supplier.id)
            .outerjoin(balance_by_supplier, balance_by_supplier.c.owner_id == Supplier.id)
            .where(SupplierAiCreditSettings.is_active.is_(True), Supplier.deleted_at.is_(None))
        )
        customer_stmt = (
            select(
                Customer.id,
                Customer.name,
                SupplierAiCreditSettings.tier,
                SupplierAiCreditSettings.monthly_base_allocation,
                func.coalesce(usage_by_customer.c.used_this_month, 0),
                func.coalesce(balance_by_customer.c.balance, 0),
            )
            .join(SupplierAiCreditSettings, SupplierAiCreditSettings.customer_id == Customer.id)
            .outerjoin(usage_by_customer, usage_by_customer.c.owner_id == Customer.id)
            .outerjoin(balance_by_customer, balance_by_customer.c.owner_id == Customer.id)
            .where(SupplierAiCreditSettings.is_active.is_(True), Customer.deleted_at.is_(None))
        )

        supplier_rows = (await self.session.execute(supplier_stmt)).all()
        customer_rows = (await self.session.execute(customer_stmt)).all()
        combined = [
            {
                "owner_id": r[0],
                "owner_name": r[1],
                "owner_type": "supplier",
                "tier": r[2],
                "monthly_base_allocation": r[3],
                "used_this_month": r[4],
                "balance": r[5],
            }
            for r in supplier_rows
        ] + [
            {
                "owner_id": r[0],
                "owner_name": r[1],
                "owner_type": "customer",
                "tier": r[2],
                "monthly_base_allocation": r[3],
                "used_this_month": r[4],
                "balance": r[5],
            }
            for r in customer_rows
        ]
        combined.sort(key=lambda row: row["used_this_month"], reverse=True)
        return combined[:limit]

    async def totals(self) -> tuple[int, int, int, int]:
        """(total_issued_all_time, total_used_all_time, total_carry_forward_now, active_accounts)."""
        issued = await self.session.scalar(select(func.coalesce(func.sum(SupplierAiCreditBatch.amount_granted), 0)))
        used = await self.session.scalar(select(func.coalesce(func.sum(AiCreditTransaction.credits_charged), 0)))
        carry_forward = await self.session.scalar(
            select(func.coalesce(func.sum(SupplierAiCreditBatch.amount_remaining), 0))
        )
        active_suppliers = await self.session.scalar(
            select(func.count())
            .select_from(SupplierAiCreditSettings)
            .join(Supplier, Supplier.id == SupplierAiCreditSettings.supplier_id)
            .where(SupplierAiCreditSettings.is_active.is_(True), Supplier.deleted_at.is_(None))
        )
        active_customers = await self.session.scalar(
            select(func.count())
            .select_from(SupplierAiCreditSettings)
            .join(Customer, Customer.id == SupplierAiCreditSettings.customer_id)
            .where(SupplierAiCreditSettings.is_active.is_(True), Customer.deleted_at.is_(None))
        )
        active = (active_suppliers or 0) + (active_customers or 0)
        return issued or 0, used or 0, carry_forward or 0, active

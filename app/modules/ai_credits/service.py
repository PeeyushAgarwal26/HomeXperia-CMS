import logging
import uuid
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions.http_exceptions import NotFoundException
from app.modules.ai_credits.repository import (
    AccountKey,
    AiCreditDashboardRepository,
    AiCreditTransactionRepository,
    SupplierAiCreditBatchRepository,
    SupplierAiCreditLedgerRepository,
    SupplierAiCreditSettingsRepository,
)
from app.modules.ai_credits.schemas import (
    AiPipelineStats,
    AuditLogItem,
    BalanceSheetResponse,
    BalanceSheetRow,
    CategoryBreakdownItem,
    DashboardResponse,
    RolloverRunResponse,
    SupplierCreditSettingsDetail,
    SupplierCreditSettingsRequest,
    TopConsumerItem,
    TopUpRequest,
    TrendPoint,
)
from app.modules.customers.models import Customer
from app.modules.suppliers.models import Supplier
from app.modules.visualizer.repository import UsageLogRepository

logger = logging.getLogger(__name__)

# Below this fraction of the monthly base allocation, an account is flagged
# "Low Balance Warning" on the Top Consuming Suppliers Log — a display
# concern only, not part of the credit engine itself.
LOW_BALANCE_THRESHOLD_RATIO = 0.10


def _month_start(d: date) -> date:
    return d.replace(day=1)


def _next_month_start(d: date) -> date:
    return date(d.year + 1, 1, 1) if d.month == 12 else date(d.year, d.month + 1, 1)


def _prev_month_start(d: date) -> date:
    return date(d.year - 1, 12, 1) if d.month == 1 else date(d.year, d.month - 1, 1)


def _months_between(start: date, until: date) -> int:
    return (until.year - start.year) * 12 + (until.month - start.month)


def _subscription_year_and_month_index(subscription_month_start: date, period_start: date) -> tuple[int, int]:
    """Subscription years are 12 calendar-month blocks starting from the
    calendar month containing the account's subscription start date — NOT
    the Jan-Dec calendar year. Returns (year_number starting at 1,
    month_index 1-12 within that year)."""
    months_elapsed = _months_between(subscription_month_start, period_start)
    return months_elapsed // 12 + 1, months_elapsed % 12 + 1


class AiCreditService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.settings_repo = SupplierAiCreditSettingsRepository(session)
        self.batch_repo = SupplierAiCreditBatchRepository(session)
        self.ledger_repo = SupplierAiCreditLedgerRepository(session)
        self.tx_repo = AiCreditTransactionRepository(session)
        self.dashboard_repo = AiCreditDashboardRepository(session)
        self.usage_log_repo = UsageLogRepository(session)

    # ---- owner resolution ----

    async def _get_owner_entity(self, account: AccountKey) -> Supplier | Customer:
        entity = await self.session.get(Supplier if account.owner_type == "supplier" else Customer, account.owner_id)
        if entity is None:
            raise NotFoundException("Supplier" if account.owner_type == "supplier" else "Customer")
        return entity

    @staticmethod
    def _subscription_start(account: AccountKey, entity: Supplier | Customer) -> date | None:
        return entity.start_of_subscription if account.owner_type == "supplier" else entity.date_of_start

    @staticmethod
    def _set_subscription_start(account: AccountKey, entity: Supplier | Customer, value: date) -> None:
        if account.owner_type == "supplier":
            entity.start_of_subscription = value
        else:
            entity.date_of_start = value

    @staticmethod
    def _entity_name(entity: Supplier | Customer) -> str:
        return entity.name

    # ---- attribution helpers ----

    async def resolve_billing_account(self, customer_id: uuid.UUID | None) -> AccountKey | None:
        """Billing follows whoever is actually logged in and using the AI —
        not whichever supplier owns the product being visualized.

        1. If that customer identity is itself a linked supplier (almost
           every real supplier's own usage flows through here) — bill their
           supplier account. This is a single, stable value per real
           business, which is also why AI Credits never double-counts a
           person who uses AI both "as a customer" and "as a supplier."
        2. Otherwise, if this customer has been given their own direct
           credit account (a plain customer — e.g. a retailer who never
           supplies anything, but still uses the visualizer) — bill that
           account directly. No promotion to Supplier required.
        3. Otherwise — a customer with neither — the event is logged for
           audit but billed to nobody.
        """
        if customer_id is None:
            return None
        customer = await self.session.get(Customer, customer_id)
        if customer is None:
            return None
        if customer.linked_supplier_id is not None:
            return AccountKey.for_supplier(customer.linked_supplier_id)
        own_account = AccountKey.for_customer(customer_id)
        if await self.settings_repo.get_by_account(own_account) is not None:
            return own_account
        return None

    async def resolve_customer_account(self, customer_id: uuid.UUID) -> AccountKey:
        """Which AccountKey a Customer's AI Credits admin screen (balance
        sheet, audit log, settings, top-up) actually reads and writes -
        the linked Supplier's account when one exists, so it shows the exact
        same numbers as opening that Supplier directly (mirrors
        resolve_billing_account, since real usage already bills there; the
        two accounts would otherwise silently drift apart). Unlike
        resolve_billing_account, this always resolves to *some* account
        (never None) even before any settings exist yet, so a plain,
        unlinked customer can still be configured for the first time."""
        customer = await self.session.get(Customer, customer_id)
        if customer is None:
            raise NotFoundException("Customer")
        if customer.linked_supplier_id is not None:
            return AccountKey.for_supplier(customer.linked_supplier_id)
        return AccountKey.for_customer(customer_id)

    # ---- charging (called from VisualizerService hooks) ----

    async def charge_credit(
        self,
        billed_account: AccountKey | None,
        customer_id: uuid.UUID | None,
        room_id: str | None,
        room_category_name: str | None,
        is_curtain_room: bool,
        action_type: str,
        tooltip_element_label: str | None = None,
        product_id: uuid.UUID | None = None,
    ) -> None:
        """Billing must never block the actual AI feature — every failure
        path here is caught and logged, never raised, matching the existing
        UsageLogRepository write-helper contract."""
        try:
            charged = False
            if billed_account is not None:
                charged = await self.batch_repo.deduct_oldest_available(billed_account)
            else:
                logger.warning(
                    "ai_credits: %s with no resolvable billing account — logged for audit, not billed", action_type
                )
            await self.tx_repo.create_transaction(
                billed_account=billed_account,
                customer_id=customer_id,
                room_id=room_id,
                room_category_name=room_category_name,
                is_curtain_room=is_curtain_room,
                action_type=action_type,
                tooltip_element_label=tooltip_element_label,
                product_id=product_id,
                credits_charged=1 if charged else 0,
            )
        except Exception:
            logger.exception("ai_credits.charge_credit failed for account %s", billed_account)

    async def log_free_event(
        self,
        billed_account: AccountKey | None,
        customer_id: uuid.UUID | None,
        room_id: str | None,
        room_category_name: str | None,
        is_curtain_room: bool,
        action_type: str,
        tooltip_element_label: str | None = None,
        product_id: uuid.UUID | None = None,
    ) -> None:
        try:
            await self.tx_repo.create_transaction(
                billed_account=billed_account,
                customer_id=customer_id,
                room_id=room_id,
                room_category_name=room_category_name,
                is_curtain_room=is_curtain_room,
                action_type=action_type,
                tooltip_element_label=tooltip_element_label,
                product_id=product_id,
                credits_charged=0,
            )
        except Exception:
            logger.exception("ai_credits.log_free_event failed for account %s", billed_account)

    # ---- onboarding / top-up (Steps 3 & 4) ----

    async def create_or_update_settings(
        self, account: AccountKey, request: SupplierCreditSettingsRequest, created_by: uuid.UUID | None
    ) -> SupplierCreditSettingsDetail:
        entity = await self._get_owner_entity(account)

        settings = await self.settings_repo.upsert(account, request.monthly_base_allocation, request.tier)
        self._set_subscription_start(account, entity, request.subscription_start_date)

        subscription_month_start = _month_start(request.subscription_start_date)
        year_number, _ = _subscription_year_and_month_index(subscription_month_start, subscription_month_start)
        if await self.batch_repo.get_batch(account, subscription_month_start, "monthly_allocation") is None:
            await self.batch_repo.create_batch(
                account,
                subscription_month_start,
                request.monthly_base_allocation,
                year_number,
                "monthly_allocation",
                created_by=created_by,
            )
        if request.initial_grant:
            await self.batch_repo.create_batch(
                account,
                date.today(),
                request.initial_grant,
                year_number,
                "manual_topup",
                note=request.note,
                created_by=created_by,
            )
        await self.session.flush()
        return SupplierCreditSettingsDetail(
            account_id=account.owner_id,
            account_type=account.owner_type,
            monthly_base_allocation=settings.monthly_base_allocation,
            tier=settings.tier,
            is_active=settings.is_active,
        )

    async def add_topup(self, account: AccountKey, request: TopUpRequest, created_by: uuid.UUID | None) -> None:
        entity = await self._get_owner_entity(account)
        subscription_start = self._subscription_start(account, entity)
        if subscription_start is None:
            raise NotFoundException("Account (subscription not yet configured)")
        subscription_month_start = _month_start(subscription_start)
        year_number, _ = _subscription_year_and_month_index(subscription_month_start, _month_start(date.today()))
        await self.batch_repo.create_batch(
            account,
            date.today(),
            request.amount,
            year_number,
            "manual_topup",
            note=request.note,
            created_by=created_by,
        )

    # ---- balance sheet (Section 3) ----

    async def compute_balance_sheet(self, account: AccountKey) -> BalanceSheetResponse:
        entity = await self._get_owner_entity(account)

        today = date.today()
        period_start = _month_start(today)
        prev_period_start = _prev_month_start(period_start)

        rows: list[BalanceSheetRow] = []

        prev_entry = await self.ledger_repo.get_by_period(account, prev_period_start)
        if prev_entry is not None:
            rows.append(
                BalanceSheetRow(
                    period_label="Previous Month",
                    credits_added=prev_entry.credits_allocated,
                    credits_carried_forward=prev_entry.credits_carried_forward,
                    total_used=prev_entry.credits_used_mask_generated + prev_entry.credits_used_curtain_applied,
                    credits_purchased=prev_entry.credits_purchased,
                    balance_as_of=prev_entry.closing_balance,
                )
            )

        current_balance = await self.batch_repo.get_remaining_total(account)
        current_allocation_batch = await self.batch_repo.get_batch(account, period_start, "monthly_allocation")
        credits_added_mtd = current_allocation_batch.amount_granted if current_allocation_batch else 0
        carried_forward_mtd = prev_entry.closing_balance if prev_entry is not None else 0
        purchased_mtd = await self.batch_repo.sum_topups_in_range(account, period_start, _next_month_start(period_start))
        # Every credit-charging action (rugs, tiles, wall color/paint, wallpaper,
        # curtains, etc.) rolls up into this one Total Used figure - there's no
        # per-product-category split shown here, just what was spent overall.
        usage_mtd = await self.tx_repo.sum_used_by_category(account, since=period_start)
        total_mtd = usage_mtd["mask_generated"] + usage_mtd["curtain_applied"]
        rows.append(
            BalanceSheetRow(
                period_label="Month Till Date",
                credits_added=credits_added_mtd,
                credits_carried_forward=carried_forward_mtd,
                total_used=total_mtd,
                credits_purchased=purchased_mtd,
                balance_as_of=current_balance,
            )
        )

        usage_today = await self.tx_repo.sum_used_by_category(account, since=today)
        total_today = usage_today["mask_generated"] + usage_today["curtain_applied"]
        rows.append(
            BalanceSheetRow(
                period_label="Today",
                credits_added=0,
                credits_carried_forward=None,
                total_used=total_today,
                credits_purchased=0,
                balance_as_of=current_balance,
            )
        )

        return BalanceSheetResponse(
            account_id=account.owner_id,
            account_type=account.owner_type,
            account_name=self._entity_name(entity),
            rows=rows,
            pipeline_stats=await self.get_pipeline_stats(account, entity),
        )

    async def get_pipeline_stats(self, account: AccountKey, entity: Supplier | Customer) -> AiPipelineStats | None:
        """Visualizer Admin's own token/generation numbers for whichever
        Customer identity actually drives this account's usage — the
        account's own linked_customer_id for a supplier account, or the
        customer themselves for a direct customer account. None if there's
        no such identity yet (nothing to report)."""
        if account.owner_type == "supplier":
            customer_id = entity.linked_customer_id  # type: ignore[union-attr]
        else:
            customer_id = entity.id
        if customer_id is None:
            return None
        totals = await self.usage_log_repo.get_usage_totals(customer_id)
        return AiPipelineStats(
            total_input_tokens=totals["total_input_tokens"],
            total_output_tokens=totals["total_output_tokens"],
            total_gen_tokens=totals["total_gen_tokens"],
            generations_success=totals["generations_success"],
            generations_failed=totals["generations_failed"],
            tooltip_units=totals["tooltip_units"],
        )

    # ---- audit log (Section 4) ----

    async def get_audit_log(self, account: AccountKey, offset: int, limit: int | None) -> tuple[list[AuditLogItem], int]:
        rows, total = await self.tx_repo.list_paginated(account, offset, limit)
        return [
            AuditLogItem(
                id=item.id,
                created_at=item.created_at,
                customer_name=customer_name,
                customer_code=customer_code,
                room_category_name=item.room_category_name,
                is_curtain_room=item.is_curtain_room,
                action_type=item.action_type,
                tooltip_element_label=item.tooltip_element_label,
                credits_charged=item.credits_charged,
            )
            for item, customer_name, customer_code in rows
        ], total

    # ---- master dashboard (Section 2.1) ----

    async def get_dashboard(self) -> DashboardResponse:
        period_start = _month_start(date.today())
        issued, used, carry_forward, active = await self.dashboard_repo.totals()
        trend_rows = await self.ledger_repo.list_last_n_months_aggregate(12)
        breakdown = await self.tx_repo.category_breakdown_all_accounts()
        top_rows = await self.dashboard_repo.top_consumers(period_start)

        top_consumers = []
        for row in top_rows:
            base = row["monthly_base_allocation"] or 0
            status = "low_balance" if base and row["balance"] <= base * LOW_BALANCE_THRESHOLD_RATIO else "active"
            top_consumers.append(
                TopConsumerItem(
                    account_id=row["owner_id"],
                    account_type=row["owner_type"],
                    account_name=row["owner_name"],
                    tier=row["tier"],
                    monthly_base_allocation=base,
                    used_this_month=row["used_this_month"],
                    balance=row["balance"],
                    status=status,
                )
            )

        return DashboardResponse(
            total_credits_issued=issued,
            total_credits_used=used,
            total_carry_forward=carry_forward,
            active_accounts=active,
            trend=[
                TrendPoint(
                    month_label=row["period_start"].strftime("%b %Y"),
                    credits_issued=row["issued"],
                    credits_used=row["used"],
                )
                for row in trend_rows
            ],
            category_breakdown=[
                CategoryBreakdownItem(category=category, credits_used=amount)
                for category, amount in breakdown.items()
            ],
            top_consumers=top_consumers,
        )

    # ---- monthly rollover cron (Steps 2 & 9) ----

    async def run_monthly_rollover(self, as_of: date | None = None) -> RolloverRunResponse:
        as_of = as_of or date.today()
        current_period_start = _month_start(as_of)
        processed = 0

        for settings, supplier in await self.settings_repo.list_active_supplier_accounts():
            if supplier.start_of_subscription is None:
                continue
            await self._catch_up_account(
                AccountKey.for_supplier(supplier.id), settings, supplier.start_of_subscription, current_period_start
            )
            processed += 1

        for settings, customer in await self.settings_repo.list_active_customer_accounts():
            if customer.date_of_start is None:
                continue
            await self._catch_up_account(
                AccountKey.for_customer(customer.id), settings, customer.date_of_start, current_period_start
            )
            processed += 1

        await self.session.flush()
        return RolloverRunResponse(processed_accounts=processed, period_start=current_period_start)

    async def _catch_up_account(
        self, account: AccountKey, settings, subscription_start: date, up_to_period_start: date
    ) -> None:
        subscription_month_start = _month_start(subscription_start)
        cursor = subscription_month_start

        if await self.batch_repo.get_batch(account, cursor, "monthly_allocation") is None:
            year_number, _ = _subscription_year_and_month_index(subscription_month_start, cursor)
            await self.batch_repo.create_batch(
                account, cursor, settings.monthly_base_allocation, year_number, "monthly_allocation"
            )

        while cursor < up_to_period_start:
            next_cursor = _next_month_start(cursor)
            await self._close_month_and_open_next(account, settings, subscription_month_start, cursor, next_cursor)
            cursor = next_cursor

    async def _close_month_and_open_next(
        self,
        account: AccountKey,
        settings,
        subscription_month_start: date,
        period_start: date,
        next_period_start: date,
    ) -> None:
        if await self.ledger_repo.get_by_period(account, period_start) is None:
            allocation_batch = await self.batch_repo.get_batch(account, period_start, "monthly_allocation")
            allocated = allocation_batch.amount_granted if allocation_batch else 0
            prior_entry = await self.ledger_repo.get_by_period(account, _prev_month_start(period_start))
            carried_forward = prior_entry.closing_balance if prior_entry is not None else 0
            purchased = await self.batch_repo.sum_topups_in_range(account, period_start, next_period_start)
            usage = await self.tx_repo.sum_used_by_category(account, since=period_start, until=next_period_start)
            total_used = usage["mask_generated"] + usage["curtain_applied"]

            year_number, month_index = _subscription_year_and_month_index(subscription_month_start, period_start)
            lapsed = 0
            if month_index == 12:
                lapsed = await self._lapse_stale_batches(account, subscription_month_start, year_number)

            # Computed algebraically (point-in-time, from this month's own
            # figures) rather than re-derived from a live SUM(amount_remaining)
            # snapshot — a catch-up run closing several missed months at once
            # must not let a *later* month's topup (always dated "today")
            # leak into an *earlier* month's closing balance.
            closing_balance = allocated + carried_forward + purchased - total_used - lapsed

            await self.ledger_repo.create(
                {
                    "supplier_id": account.supplier_id,
                    "customer_id": account.customer_id,
                    "period_start": period_start,
                    "period_end": next_period_start,
                    "credits_allocated": allocated,
                    "credits_carried_forward": carried_forward,
                    "credits_used_mask_generated": usage["mask_generated"],
                    "credits_used_curtain_applied": usage["curtain_applied"],
                    "credits_purchased": purchased,
                    "closing_balance": closing_balance,
                    "credits_lapsed": lapsed,
                }
            )

        if await self.batch_repo.get_batch(account, next_period_start, "monthly_allocation") is None:
            year_number, _ = _subscription_year_and_month_index(subscription_month_start, next_period_start)
            await self.batch_repo.create_batch(
                account, next_period_start, settings.monthly_base_allocation, year_number, "monthly_allocation"
            )

    async def _lapse_stale_batches(
        self, account: AccountKey, subscription_month_start: date, closing_year_number: int
    ) -> int:
        """Months 1-9 of the closing subscription year lapse whatever they
        still hold; months 10-12 are left alone (they keep rolling forward
        via ordinary FIFO consumption in the new year)."""
        batches = await self.batch_repo.list_by_account_and_year(account, closing_year_number)
        lapsed_total = 0
        for batch in batches:
            months_elapsed = _months_between(subscription_month_start, batch.batch_date)
            month_index = months_elapsed % 12 + 1
            if month_index <= 9 and batch.amount_remaining > 0:
                lapsed_total += batch.amount_remaining
                batch.amount_remaining = 0
        if lapsed_total:
            await self.session.flush()
        return lapsed_total

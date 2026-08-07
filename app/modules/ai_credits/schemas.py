import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel

AccountType = Literal["supplier", "customer"]


class SupplierCreditSettingsRequest(BaseModel):
    monthly_base_allocation: int
    tier: str | None = None
    subscription_start_date: date
    initial_grant: int = 0
    note: str | None = None


class SupplierCreditSettingsDetail(BaseModel):
    account_id: uuid.UUID
    account_type: AccountType
    monthly_base_allocation: int
    tier: str | None
    is_active: bool


class TopUpRequest(BaseModel):
    amount: int
    note: str | None = None


class BalanceSheetRow(BaseModel):
    period_label: str
    credits_added: int | None
    credits_carried_forward: int | None
    mask_generated_used: int
    curtain_applied_used: int | None
    total_used: int
    credits_purchased: int
    balance_as_of: int


class AiPipelineStats(BaseModel):
    """Visualizer Admin's own numbers (real OpenAI tokens, generation
    success/fail, tooltip applications) for whichever customer identity
    actually drives this account's AI Credit usage — the account's own
    linked_customer_id for a supplier account, or the customer themselves
    for a direct customer account. None if there's no such identity yet
    (nothing to report)."""

    total_input_tokens: int
    total_output_tokens: int
    total_gen_tokens: int
    generations_success: int
    generations_failed: int
    tooltip_units: int


class BalanceSheetResponse(BaseModel):
    account_id: uuid.UUID
    account_type: AccountType
    account_name: str
    shows_curtain_column: bool
    rows: list[BalanceSheetRow]
    pipeline_stats: AiPipelineStats | None


class AuditLogItem(BaseModel):
    id: uuid.UUID
    created_at: datetime
    customer_name: str | None
    customer_code: str | None
    room_category_name: str | None
    is_curtain_room: bool
    action_type: str
    tooltip_element_label: str | None
    credits_charged: int


class TopConsumerItem(BaseModel):
    account_id: uuid.UUID
    account_type: AccountType
    account_name: str
    tier: str | None
    monthly_base_allocation: int
    used_this_month: int
    balance: int
    status: str  # active | low_balance


class TrendPoint(BaseModel):
    month_label: str
    credits_issued: int
    credits_used: int


class CategoryBreakdownItem(BaseModel):
    category: str
    credits_used: int


class DashboardResponse(BaseModel):
    total_credits_issued: int
    total_credits_used: int
    total_carry_forward: int
    active_accounts: int
    trend: list[TrendPoint]
    category_breakdown: list[CategoryBreakdownItem]
    top_consumers: list[TopConsumerItem]


class RolloverRunResponse(BaseModel):
    processed_accounts: int
    period_start: date

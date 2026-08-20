"""add_session_started_at_to_customer_supplier_refresh_tokens

Revision ID: d41f816df2ab
Revises: af0d83a905d3
Create Date: 2026-08-18 17:11:26.740617

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd41f816df2ab'
down_revision: Union[str, None] = 'af0d83a905d3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    for table in ("customer_refresh_tokens", "supplier_refresh_tokens"):
        op.add_column(table, sa.Column("session_started_at", sa.DateTime(timezone=True), nullable=True))
        # Backfill from issued_at — see af0d83a905d3's identical admin-side
        # migration for the reasoning (safe under-approximation, never expires
        # a session prematurely).
        op.execute(f"UPDATE {table} SET session_started_at = issued_at WHERE session_started_at IS NULL")
        op.alter_column(table, "session_started_at", nullable=False)


def downgrade() -> None:
    for table in ("customer_refresh_tokens", "supplier_refresh_tokens"):
        op.drop_column(table, "session_started_at")

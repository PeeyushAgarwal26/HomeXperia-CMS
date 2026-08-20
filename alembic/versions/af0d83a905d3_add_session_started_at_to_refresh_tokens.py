"""add_session_started_at_to_refresh_tokens

Revision ID: af0d83a905d3
Revises: 474c43f633d6
Create Date: 2026-08-18 17:04:50.815951

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'af0d83a905d3'
down_revision: Union[str, None] = '474c43f633d6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "refresh_tokens", sa.Column("session_started_at", sa.DateTime(timezone=True), nullable=True)
    )
    # Backfill existing rows with issued_at — the closest available proxy for
    # "when this session-chain started" for tokens that predate this column.
    # Under-approximates the true absolute cap for anyone whose session was
    # already older than issued_at at the time of deploy, but never rejects a
    # session prematurely, since issued_at is always <= the real start.
    op.execute("UPDATE refresh_tokens SET session_started_at = issued_at WHERE session_started_at IS NULL")
    op.alter_column("refresh_tokens", "session_started_at", nullable=False)


def downgrade() -> None:
    op.drop_column("refresh_tokens", "session_started_at")

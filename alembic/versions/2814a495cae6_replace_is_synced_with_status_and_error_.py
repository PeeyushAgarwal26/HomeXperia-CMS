"""replace is_synced with status and error_message

Revision ID: 2814a495cae6
Revises: b320d0ac9533
Create Date: 2026-07-17 14:44:45.224867

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2814a495cae6'
down_revision: Union[str, None] = 'b320d0ac9533'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("product_upload_logs", sa.Column("status", sa.String(length=20), nullable=True))
    op.add_column("product_upload_logs", sa.Column("error_message", sa.String(length=1000), nullable=True))

    op.execute(
        """
        UPDATE product_upload_logs
        SET status = CASE
            WHEN is_synced THEN 'success'
            WHEN success_count > 0 THEN 'partial'
            ELSE 'failed'
        END
        """
    )

    op.alter_column("product_upload_logs", "status", nullable=False)
    op.drop_column("product_upload_logs", "is_synced")


def downgrade() -> None:
    op.add_column(
        "product_upload_logs", sa.Column("is_synced", sa.Boolean(), nullable=False, server_default=sa.false())
    )
    op.execute("UPDATE product_upload_logs SET is_synced = (status = 'success')")
    op.drop_column("product_upload_logs", "error_message")
    op.drop_column("product_upload_logs", "status")

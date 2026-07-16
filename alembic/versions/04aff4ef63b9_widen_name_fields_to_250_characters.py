"""widen name fields to 250 characters

Revision ID: 04aff4ef63b9
Revises: 1f50901c55f9
Create Date: 2026-07-16 10:55:16.730109

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '04aff4ef63b9'
down_revision: Union[str, None] = '1f50901c55f9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


COLUMNS = [
    ("parent_categories", "name", 100),
    ("child_categories", "name", 100),
    ("filters", "name", 100),
    ("filter_values", "value", 150),
    ("suppliers", "name", 150),
    ("products", "catalog_name", 150),
    ("customers", "name", 150),
    ("admin_users", "name", 150),
]


def upgrade() -> None:
    for table, column, _old_length in COLUMNS:
        op.alter_column(table, column, type_=sa.String(250), existing_nullable=False)


def downgrade() -> None:
    for table, column, old_length in COLUMNS:
        op.alter_column(table, column, type_=sa.String(old_length), existing_nullable=False)

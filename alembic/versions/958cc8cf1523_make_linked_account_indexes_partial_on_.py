"""make linked account indexes partial on deleted_at

Revision ID: 958cc8cf1523
Revises: 88c126524c55
Create Date: 2026-08-06 14:37:55.562332

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '958cc8cf1523'
down_revision: Union[str, None] = '88c126524c55'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Autogenerate doesn't detect predicate-only changes on an existing
    # index, so this is hand-written: both indexes need to become partial
    # (deleted_at IS NULL) like every other unique index on these two
    # tables, otherwise a soft-deleted linked account permanently blocks
    # re-linking to the same supplier/customer.
    op.drop_index("ix_suppliers_linked_customer_id", table_name="suppliers")
    op.create_index(
        "ix_suppliers_linked_customer_id",
        "suppliers",
        ["linked_customer_id"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.drop_index("ix_customers_linked_supplier_id", table_name="customers")
    op.create_index(
        "ix_customers_linked_supplier_id",
        "customers",
        ["linked_supplier_id"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_customers_linked_supplier_id", table_name="customers")
    op.create_index("ix_customers_linked_supplier_id", "customers", ["linked_supplier_id"], unique=True)
    op.drop_index("ix_suppliers_linked_customer_id", table_name="suppliers")
    op.create_index("ix_suppliers_linked_customer_id", "suppliers", ["linked_customer_id"], unique=True)

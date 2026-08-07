"""split login history module into supplier and sub admin

Revision ID: aca9d308d671
Revises: e2ca5400d014
Create Date: 2026-07-30 16:15:29.597824

"""
"""The admin's combined "Login History" module (one page, one role filter for
both supplier and sub-admin logins) becomes two separate sidebar entries with
independent permissions — matching how "Customer Login History" already gets
its own module. Module catalog rows only come from the seed script or a
migration (the seed script hard-skips once any row exists, so it never
retrofits an already-seeded DB) — this migration is the actual mechanism.

Renaming the existing row (rather than inserting two fresh ones and dropping
the old one) means every admin_user_module_permissions /
supplier_module_permissions grant that already points at this module_id
keeps working with zero data loss — it becomes the "supplier" entry for
free. The new "sub admin" row is a genuinely new grant, so anyone who held
the old combined permission has that grant explicitly copied to it too,
preserving what they could already see.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'aca9d308d671'
down_revision: Union[str, None] = 'e2ca5400d014'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE modules
        SET key = 'logs.supplier_login_history', name = 'Supplier Login History'
        WHERE key = 'logs.login_history'
        """
    )
    op.execute(
        """
        INSERT INTO modules (id, key, name, parent_id, sort_order, is_buildable, is_active, created_at, updated_at)
        SELECT gen_random_uuid(), 'logs.sub_admin_login_history', 'Sub Admin Login History',
               parent_id, sort_order + 1, is_buildable, is_active, now(), now()
        FROM modules
        WHERE key = 'logs.supplier_login_history'
        """
    )
    op.execute(
        """
        INSERT INTO admin_user_module_permissions (admin_user_id, module_id)
        SELECT admin_user_id, (SELECT id FROM modules WHERE key = 'logs.sub_admin_login_history')
        FROM admin_user_module_permissions
        WHERE module_id = (SELECT id FROM modules WHERE key = 'logs.supplier_login_history')
        """
    )
    op.execute(
        """
        INSERT INTO supplier_module_permissions (supplier_id, module_id)
        SELECT supplier_id, (SELECT id FROM modules WHERE key = 'logs.sub_admin_login_history')
        FROM supplier_module_permissions
        WHERE module_id = (SELECT id FROM modules WHERE key = 'logs.supplier_login_history')
        """
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM admin_user_module_permissions "
        "WHERE module_id = (SELECT id FROM modules WHERE key = 'logs.sub_admin_login_history')"
    )
    op.execute(
        "DELETE FROM supplier_module_permissions "
        "WHERE module_id = (SELECT id FROM modules WHERE key = 'logs.sub_admin_login_history')"
    )
    op.execute("DELETE FROM modules WHERE key = 'logs.sub_admin_login_history'")
    op.execute(
        """
        UPDATE modules
        SET key = 'logs.login_history', name = 'Login History'
        WHERE key = 'logs.supplier_login_history'
        """
    )

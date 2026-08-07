"""restructure qr generator module and add saved qr codes table

Revision ID: 0a1062aa081a
Revises: 79ed5fb3d0d1
Create Date: 2026-07-30 18:11:27.559812

The single top-level "QR Code Generator" sidebar item becomes a "QR Code"
parent with two children: the generator itself (same key, so every existing
permission grant keeps working unchanged) and a new "Generated QR Codes"
list. Same continuity approach as the earlier Login History module split —
insert the new parent + sibling, then copy every grant the generator already
had onto the new sibling too, so nobody's access silently narrows.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0a1062aa081a'
down_revision: Union[str, None] = '79ed5fb3d0d1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('saved_qr_codes',
    sa.Column('customer_id', sa.UUID(), nullable=False),
    sa.Column('filter_values', sa.String(length=1000), nullable=True),
    sa.Column('brand_logo_url', sa.String(length=500), nullable=True),
    sa.Column('image_url', sa.String(length=500), nullable=False),
    sa.Column('created_by', sa.UUID(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['created_by'], ['admin_users.id'], ),
    sa.ForeignKeyConstraint(['customer_id'], ['customers.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )

    op.execute(
        """
        INSERT INTO modules (id, key, name, parent_id, sort_order, is_buildable, is_active, created_at, updated_at)
        SELECT gen_random_uuid(), 'qr_code', 'QR Code', NULL, sort_order, false, is_active, now(), now()
        FROM modules
        WHERE key = 'qr_generator'
        """
    )
    op.execute(
        """
        UPDATE modules
        SET parent_id = (SELECT id FROM modules WHERE key = 'qr_code'), sort_order = 0
        WHERE key = 'qr_generator'
        """
    )
    op.execute(
        """
        INSERT INTO modules (id, key, name, parent_id, sort_order, is_buildable, is_active, created_at, updated_at)
        SELECT gen_random_uuid(), 'qr_generator.saved_list', 'Generated QR Codes',
               (SELECT id FROM modules WHERE key = 'qr_code'), 1, true, true, now(), now()
        """
    )
    op.execute(
        """
        INSERT INTO admin_user_module_permissions (admin_user_id, module_id)
        SELECT admin_user_id, (SELECT id FROM modules WHERE key = 'qr_generator.saved_list')
        FROM admin_user_module_permissions
        WHERE module_id = (SELECT id FROM modules WHERE key = 'qr_generator')
        """
    )
    op.execute(
        """
        INSERT INTO supplier_module_permissions (supplier_id, module_id)
        SELECT supplier_id, (SELECT id FROM modules WHERE key = 'qr_generator.saved_list')
        FROM supplier_module_permissions
        WHERE module_id = (SELECT id FROM modules WHERE key = 'qr_generator')
        """
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM admin_user_module_permissions "
        "WHERE module_id = (SELECT id FROM modules WHERE key = 'qr_generator.saved_list')"
    )
    op.execute(
        "DELETE FROM supplier_module_permissions "
        "WHERE module_id = (SELECT id FROM modules WHERE key = 'qr_generator.saved_list')"
    )
    op.execute("DELETE FROM modules WHERE key = 'qr_generator.saved_list'")
    op.execute(
        """
        UPDATE modules
        SET parent_id = NULL, sort_order = (SELECT sort_order FROM modules WHERE key = 'qr_code')
        WHERE key = 'qr_generator'
        """
    )
    op.execute("DELETE FROM modules WHERE key = 'qr_code'")
    op.drop_table('saved_qr_codes')

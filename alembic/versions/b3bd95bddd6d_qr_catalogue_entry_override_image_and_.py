"""qr_catalogue_entry_override_image_and_inline_hotspots

Revision ID: b3bd95bddd6d
Revises: 0a1062aa081a
Create Date: 2026-08-01 14:53:48.638300

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b3bd95bddd6d'
down_revision: Union[str, None] = '0a1062aa081a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Curtains generated for a QR catalogue mapping must never be written
    # back onto the shared room_category_images/hotspots rows — this override
    # image lives on the mapping itself instead.
    op.add_column('qr_catalogue_entries', sa.Column('override_image_url', sa.String(length=500), nullable=True))

    op.add_column('qr_catalogue_entry_hotspots', sa.Column('inline_label', sa.String(length=250), nullable=True))
    op.add_column('qr_catalogue_entry_hotspots', sa.Column('inline_type', sa.String(length=50), nullable=True))
    op.add_column('qr_catalogue_entry_hotspots', sa.Column('inline_x', sa.Float(), nullable=True))
    op.add_column('qr_catalogue_entry_hotspots', sa.Column('inline_y', sa.Float(), nullable=True))
    op.add_column('qr_catalogue_entry_hotspots', sa.Column('inline_mask_image_url', sa.String(length=500), nullable=True))
    op.add_column('qr_catalogue_entry_hotspots', sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False))
    op.add_column('qr_catalogue_entry_hotspots', sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False))

    # hotspot_id was part of the composite primary key — switching to a
    # nullable FK (a curtain-only row has no real shared hotspot to point
    # at) means the table needs a real surrogate primary key instead.
    op.add_column('qr_catalogue_entry_hotspots', sa.Column('id', sa.UUID(), nullable=True))
    op.execute("UPDATE qr_catalogue_entry_hotspots SET id = gen_random_uuid() WHERE id IS NULL")
    op.alter_column('qr_catalogue_entry_hotspots', 'id', nullable=False)

    op.drop_constraint('qr_catalogue_entry_hotspots_pkey', 'qr_catalogue_entry_hotspots', type_='primary')
    op.create_primary_key('qr_catalogue_entry_hotspots_pkey', 'qr_catalogue_entry_hotspots', ['id'])

    op.alter_column('qr_catalogue_entry_hotspots', 'hotspot_id', existing_type=sa.UUID(), nullable=True)


def downgrade() -> None:
    op.alter_column('qr_catalogue_entry_hotspots', 'hotspot_id', existing_type=sa.UUID(), nullable=False)

    op.drop_constraint('qr_catalogue_entry_hotspots_pkey', 'qr_catalogue_entry_hotspots', type_='primary')
    op.create_primary_key(
        'qr_catalogue_entry_hotspots_pkey', 'qr_catalogue_entry_hotspots', ['qr_catalogue_entry_id', 'hotspot_id']
    )

    op.drop_column('qr_catalogue_entry_hotspots', 'id')
    op.drop_column('qr_catalogue_entry_hotspots', 'updated_at')
    op.drop_column('qr_catalogue_entry_hotspots', 'created_at')
    op.drop_column('qr_catalogue_entry_hotspots', 'inline_mask_image_url')
    op.drop_column('qr_catalogue_entry_hotspots', 'inline_y')
    op.drop_column('qr_catalogue_entry_hotspots', 'inline_x')
    op.drop_column('qr_catalogue_entry_hotspots', 'inline_type')
    op.drop_column('qr_catalogue_entry_hotspots', 'inline_label')
    op.drop_column('qr_catalogue_entries', 'override_image_url')

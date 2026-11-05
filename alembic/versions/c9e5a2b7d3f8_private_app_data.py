"""private app data

Revision ID: c9e5a2b7d3f8
Revises: b8d4f1a6c2e7
Create Date: 2026-11-05 13:00:00

Per-app settings of a personal workspace as JSON (Pakkeliste, Madplan, Læge & tandlæge, Bil & syn, Pakker).
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = 'c9e5a2b7d3f8'
down_revision = 'b8d4f1a6c2e7'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'private_app_data',
        sa.Column('workspace_id', sa.UUID(), nullable=False),
        sa.Column('app_key', sa.String(length=40), nullable=False),
        sa.Column('data', postgresql.JSONB(astext_type=sa.Text()), server_default='{}', nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], name='fk_private_app_data_workspace_id',
                                ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('workspace_id', 'app_key', name='pk_private_app_data'),
    )


def downgrade() -> None:
    op.drop_table('private_app_data')

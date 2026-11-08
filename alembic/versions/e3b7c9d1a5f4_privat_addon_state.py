"""privat apps: per-app state for «Mine apps» (setup progress, switched off with data kept, «Giv mig besked»)

Revision ID: e3b7c9d1a5f4
Revises: d8e4a1c6f2b9
Create Date: 2026-11-08 15:00:00

Additive: one new table. Whether an app is on is still private_addon_enabled (unchanged).
"""
import sqlalchemy as sa

from alembic import op

revision = 'e3b7c9d1a5f4'
down_revision = 'd8e4a1c6f2b9'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'private_addon_state',
        sa.Column('workspace_id', sa.Uuid(), nullable=False),
        sa.Column('key', sa.String(length=40), nullable=False),
        sa.Column('setup_done', sa.Integer(), server_default='0', nullable=False),
        sa.Column('disabled_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('notify_requested_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('workspace_id', 'key'),
    )


def downgrade() -> None:
    op.drop_table('private_addon_state')

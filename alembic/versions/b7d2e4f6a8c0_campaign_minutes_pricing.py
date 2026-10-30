"""campaign calls priced per call plus started minute

Revision ID: b7d2e4f6a8c0
Revises: a1b2c3d4e5f6
Create Date: 2026-10-30 13:30:00
"""
from alembic import op
import sqlalchemy as sa


revision = 'b7d2e4f6a8c0'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 4 kr. per dialled call stays; from now on every started minute of conversation costs 2 kr. as well. As with the
    # move to per-call pricing, every existing campaign gets the new list price from now; calls already reported keep
    # minutes_net_minor = 0 because their minutes were never priced.
    op.add_column('campaigns', sa.Column('minute_net_minor', sa.Integer(), nullable=False, server_default='200'))
    op.add_column('campaign_calls', sa.Column('connected_seconds', sa.Integer(), nullable=True))
    op.add_column('campaign_calls', sa.Column('minutes_net_minor', sa.Integer(), nullable=False, server_default='0'))


def downgrade() -> None:
    op.drop_column('campaign_calls', 'minutes_net_minor')
    op.drop_column('campaign_calls', 'connected_seconds')
    op.drop_column('campaigns', 'minute_net_minor')

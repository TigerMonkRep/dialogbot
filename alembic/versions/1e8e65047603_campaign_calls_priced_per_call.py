"""campaign calls priced per call

Revision ID: 1e8e65047603
Revises: 2944b6976e59
Create Date: 2026-10-28 09:39:22.708895
"""
from alembic import op
import sqlalchemy as sa


revision = '1e8e65047603'
down_revision = '2944b6976e59'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('campaign_calls',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('workspace_id', sa.UUID(), nullable=False),
    sa.Column('campaign_id', sa.UUID(), nullable=False),
    sa.Column('contact_id', sa.UUID(), nullable=False),
    sa.Column('provider_call_id', sa.String(length=100), nullable=True),
    sa.Column('dialled_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('net_minor', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['campaign_id'], ['campaigns.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['contact_id'], ['campaign_contacts.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_campaign_calls_workspace_dialled', 'campaign_calls', ['workspace_id', 'dialled_at'], unique=False)
    # The per-contact package (9 kr.) becomes a price per call (4 kr.). Rename instead of add/drop and move every
    # existing campaign to the new list price from now on; charges already made stay on campaign_contacts.
    op.alter_column('campaigns', 'package_net_minor', new_column_name='call_net_minor')
    op.execute("UPDATE campaigns SET call_net_minor = 400")
    # ### end Alembic commands ###


def downgrade() -> None:
    op.alter_column('campaigns', 'call_net_minor', new_column_name='package_net_minor')
    op.execute("UPDATE campaigns SET package_net_minor = 900")
    op.drop_index('ix_campaign_calls_workspace_dialled', table_name='campaign_calls')
    op.drop_table('campaign_calls')
    # ### end Alembic commands ###

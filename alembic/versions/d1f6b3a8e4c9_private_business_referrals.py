"""private business referrals and assistant name

Revision ID: d1f6b3a8e4c9
Revises: c9e5a2b7d3f8
Create Date: 2026-11-06 09:00:00

Businesses a Privat user asked for a quote through Dialogbot, and whether the user chose them (lead revenue basis),
and the name the user gave the assistant (private_profiles.assistant_name).
"""
from alembic import op
import sqlalchemy as sa


revision = 'd1f6b3a8e4c9'
down_revision = 'c9e5a2b7d3f8'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'private_business_referrals',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('workspace_id', sa.UUID(), nullable=True),
        sa.Column('app_key', sa.String(length=40), nullable=False),
        sa.Column('job', sa.String(length=200), nullable=False),
        sa.Column('trade', sa.String(length=80), nullable=False),
        sa.Column('business_name', sa.String(length=200), nullable=False),
        sa.Column('business_phone_e164', sa.String(length=20), nullable=True),
        sa.Column('place_id', sa.String(length=300), nullable=True),
        sa.Column('call_id', sa.UUID(), nullable=True),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('chosen_at', sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('asked','chosen','not_chosen')", name='ck_private_business_referrals_status'),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], name='fk_private_business_referrals_workspace_id',
                                ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['call_id'], ['private_calls.id'], name='fk_private_business_referrals_call_id',
                                ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id', name='pk_private_business_referrals'),
    )
    op.create_index('ix_private_business_referrals_phone', 'private_business_referrals', ['business_phone_e164'])
    op.create_index('ix_private_business_referrals_ws', 'private_business_referrals', ['workspace_id'])
    op.add_column('private_profiles', sa.Column('assistant_name', sa.String(length=30), nullable=True))


def downgrade() -> None:
    op.drop_column('private_profiles', 'assistant_name')
    op.drop_index('ix_private_business_referrals_ws', table_name='private_business_referrals')
    op.drop_index('ix_private_business_referrals_phone', table_name='private_business_referrals')
    op.drop_table('private_business_referrals')

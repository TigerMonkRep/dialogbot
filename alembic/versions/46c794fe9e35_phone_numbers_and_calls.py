"""phone numbers and calls

Revision ID: 46c794fe9e35
Revises: 5a2d1bff4ed7
Create Date: 2026-09-25 21:40:58.152782
"""
from alembic import op
import sqlalchemy as sa


revision = '46c794fe9e35'
down_revision = '5a2d1bff4ed7'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('phone_numbers',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('workspace_id', sa.UUID(), nullable=False),
    sa.Column('e164', sa.String(length=20), nullable=False),
    sa.Column('provider', sa.String(length=16), nullable=False),
    sa.Column('provider_number_id', sa.String(length=100), nullable=True),
    sa.Column('label', sa.String(length=100), nullable=False),
    sa.Column('active', sa.Boolean(), nullable=False),
    sa.Column('greeting', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('e164', name='phone_numbers_e164_key'),
    sa.UniqueConstraint('provider_number_id', name='phone_numbers_provider_number_id_key')
    )
    op.create_table('calls',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('workspace_id', sa.UUID(), nullable=False),
    sa.Column('phone_number_id', sa.UUID(), nullable=True),
    sa.Column('conversation_id', sa.UUID(), nullable=True),
    sa.Column('provider', sa.String(length=16), nullable=False),
    sa.Column('provider_call_id', sa.String(length=100), nullable=False),
    sa.Column('from_number', sa.String(length=40), nullable=True),
    sa.Column('to_number', sa.String(length=40), nullable=True),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('ended_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('duration_seconds', sa.Integer(), nullable=True),
    sa.Column('ended_reason', sa.String(length=100), nullable=True),
    sa.Column('summary', sa.Text(), nullable=False),
    sa.Column('cost_usd_micros', sa.BigInteger(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['phone_number_id'], ['phone_numbers.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('provider_call_id', name='calls_provider_call_id_key')
    )
    op.create_index('ix_calls_workspace_started', 'calls', ['workspace_id', 'started_at'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_calls_workspace_started', table_name='calls')
    op.drop_table('calls')
    op.drop_table('phone_numbers')

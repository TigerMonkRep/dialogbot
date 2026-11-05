"""private bills

Revision ID: b8d4f1a6c2e7
Revises: a7c3e9f2b4d6
Create Date: 2026-11-05 12:00:00

The Regninger app: bills the user told the assistant about (name, amount, how often, next due date), reminded before
they are due. Dialogbot never pays and never sees the bank.
"""
from alembic import op
import sqlalchemy as sa


revision = 'b8d4f1a6c2e7'
down_revision = 'a7c3e9f2b4d6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'private_bills',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('workspace_id', sa.UUID(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('name_key', sa.String(length=100), nullable=False),
        sa.Column('amount_minor', sa.Integer(), nullable=True),
        sa.Column('frequency', sa.String(length=16), nullable=False),
        sa.Column('anchor_day', sa.Integer(), nullable=False),
        sa.Column('next_due', sa.Date(), nullable=False),
        sa.Column('remind_days_before', sa.Integer(), server_default='3', nullable=False),
        sa.Column('last_reminded_for', sa.Date(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("frequency in ('monthly','quarterly','half_yearly','yearly','once')",
                           name='ck_private_bills_frequency'),
        sa.CheckConstraint('anchor_day between 1 and 31', name='ck_private_bills_anchor_day'),
        sa.CheckConstraint('amount_minor is null or amount_minor >= 0', name='ck_private_bills_amount'),
        sa.CheckConstraint('remind_days_before between 0 and 30', name='ck_private_bills_remind'),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], name='fk_private_bills_workspace_id',
                                ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name='pk_private_bills'),
        sa.UniqueConstraint('workspace_id', 'name_key', name='uq_private_bills_name'),
    )
    op.create_index('ix_private_bills_ws_next_due', 'private_bills', ['workspace_id', 'next_due'])


def downgrade() -> None:
    op.drop_index('ix_private_bills_ws_next_due', table_name='private_bills')
    op.drop_table('private_bills')

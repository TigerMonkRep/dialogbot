"""private birthdays

Revision ID: a7c3e9f2b4d6
Revises: f5a9c2d7e3b1
Create Date: 2026-11-05 11:00:00

The Fødselsdage app: birthdays the user told the assistant, reminded once a year a chosen number of days before.
"""
from alembic import op
import sqlalchemy as sa


revision = 'a7c3e9f2b4d6'
down_revision = 'f5a9c2d7e3b1'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'private_birthdays',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('workspace_id', sa.UUID(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('name_key', sa.String(length=100), nullable=False),
        sa.Column('month', sa.Integer(), nullable=False),
        sa.Column('day', sa.Integer(), nullable=False),
        sa.Column('year', sa.Integer(), nullable=True),
        sa.Column('remind_days_before', sa.Integer(), server_default='7', nullable=False),
        sa.Column('last_reminded_for', sa.Date(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint('month between 1 and 12', name='ck_private_birthdays_month'),
        sa.CheckConstraint('day between 1 and 31', name='ck_private_birthdays_day'),
        sa.CheckConstraint('year is null or year between 1900 and 2100', name='ck_private_birthdays_year'),
        sa.CheckConstraint('remind_days_before between 0 and 60', name='ck_private_birthdays_remind'),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], name='fk_private_birthdays_workspace_id',
                                ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name='pk_private_birthdays'),
        sa.UniqueConstraint('workspace_id', 'name_key', name='uq_private_birthdays_name'),
    )
    op.create_index('ix_private_birthdays_ws_month_day', 'private_birthdays', ['workspace_id', 'month', 'day'])


def downgrade() -> None:
    op.drop_index('ix_private_birthdays_ws_month_day', table_name='private_birthdays')
    op.drop_table('private_birthdays')

"""privat subscriptions

Revision ID: e5a7c9d1b3f6
Revises: d4f6b8a0c2e7
Create Date: 2026-11-04 18:00:00

Dialogbot Privat subscriptions (14-day trial, Basis/Plus/Familie): the private_subscriptions table, 'plan' as a
paid_by value on private_tasks, and private_calls.paid_via (credits | plan). Existing rows are untouched: a call
without paid_via was paid with credits, and an account without a subscription row gets its trial row lazily on first
read (app/modules/privat/subscriptions.py).
"""
import sqlalchemy as sa

from alembic import op

revision = 'e5a7c9d1b3f6'
down_revision = 'd4f6b8a0c2e7'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('private_subscriptions',
    sa.Column('workspace_id', sa.UUID(), nullable=False),
    sa.Column('plan', sa.String(length=16), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('interval', sa.String(length=8), nullable=True),
    sa.Column('stripe_customer_id', sa.String(length=100), nullable=True),
    sa.Column('stripe_subscription_id', sa.String(length=100), nullable=True),
    sa.Column('trial_ends_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('current_period_end', sa.DateTime(timezone=True), nullable=True),
    sa.Column('cancel_at_period_end', sa.Boolean(), server_default='false', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("interval is null or interval in ('month','year')", name='ck_private_subscriptions_interval'),
    sa.CheckConstraint("plan in ('basis','plus','familie')", name='ck_private_subscriptions_plan'),
    sa.CheckConstraint("status in ('trial','active','past_due','canceled')", name='ck_private_subscriptions_status'),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('workspace_id'),
    sa.UniqueConstraint('stripe_subscription_id')
    )
    op.drop_constraint('ck_private_tasks_paid_by', 'private_tasks', type_='check')
    op.create_check_constraint('ck_private_tasks_paid_by', 'private_tasks',
                               "paid_by in ('free','credit','sponsor','none','call','plan')")
    op.add_column('private_calls', sa.Column('paid_via', sa.String(length=8), nullable=True))
    op.create_check_constraint('ck_private_calls_paid_via', 'private_calls',
                               "paid_via is null or paid_via in ('credits','plan')")
    op.create_index('ix_private_calls_ws_approved', 'private_calls', ['workspace_id', 'approved_at'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_private_calls_ws_approved', table_name='private_calls')
    op.drop_constraint('ck_private_calls_paid_via', 'private_calls', type_='check')
    op.drop_column('private_calls', 'paid_via')
    op.execute("update private_tasks set paid_by = 'free' where paid_by = 'plan'")
    op.drop_constraint('ck_private_tasks_paid_by', 'private_tasks', type_='check')
    op.create_check_constraint('ck_private_tasks_paid_by', 'private_tasks',
                               "paid_by in ('free','credit','sponsor','none','call')")
    op.drop_table('private_subscriptions')

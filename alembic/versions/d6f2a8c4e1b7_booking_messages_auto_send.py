"""E07 automatic booking messages: the SMS opt-in on booking settings, the message log and the customers' opt-outs

Revision ID: d6f2a8c4e1b7
Revises: c5e1f7a3d9b2
Create Date: 2026-11-13 14:00:00
"""
from alembic import op
import sqlalchemy as sa

revision = 'd6f2a8c4e1b7'
down_revision = 'c5e1f7a3d9b2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('booking_settings', sa.Column('sms_messages_enabled', sa.Boolean(), server_default=sa.text('false'),
                                                nullable=False))
    op.create_table(
        'booking_messages',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('workspace_id', sa.UUID(), nullable=False),
        sa.Column('booking_id', sa.UUID(), nullable=False),
        sa.Column('outbox_event_id', sa.UUID(), nullable=True),
        sa.Column('event_key', sa.String(length=80), nullable=False),
        sa.Column('variant', sa.String(length=32), nullable=False),
        sa.Column('audience', sa.String(length=8), nullable=False),
        sa.Column('channel', sa.String(length=8), nullable=False),
        sa.Column('recipient', sa.String(length=320), nullable=False),
        sa.Column('lang', sa.String(length=5), nullable=False),
        sa.Column('starts_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('status', sa.String(length=12), nullable=False),
        sa.Column('skip_reason', sa.String(length=40), nullable=True),
        sa.Column('error', sa.String(length=500), nullable=True),
        sa.Column('provider_ref', sa.String(length=100), nullable=True),
        sa.Column('segments', sa.SmallInteger(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("status in ('sending','retrying','sent','simulated','skipped','failed')",
                           name='ck_booking_messages_status'),
        sa.CheckConstraint("channel in ('email','sms')", name='ck_booking_messages_channel'),
        sa.CheckConstraint("audience in ('customer','owner')", name='ck_booking_messages_audience'),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['booking_id'], ['bookings.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['outbox_event_id'], ['outbox_events.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('outbox_event_id', name='uq_booking_messages_outbox_event'),
    )
    op.create_index('ix_booking_messages_booking', 'booking_messages', ['booking_id', 'created_at'])
    op.create_index('ix_booking_messages_workspace', 'booking_messages', ['workspace_id', 'created_at'])
    op.create_table(
        'customer_message_suppressions',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('workspace_id', sa.UUID(), nullable=False),
        sa.Column('channel', sa.String(length=8), nullable=False),
        sa.Column('value', sa.String(length=320), nullable=False),
        sa.Column('source', sa.String(length=24), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("channel in ('email','sms')", name='ck_customer_message_suppressions_channel'),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('workspace_id', 'channel', 'value', name='uq_customer_message_suppressions_value'),
    )


def downgrade() -> None:
    op.drop_table('customer_message_suppressions')
    op.drop_index('ix_booking_messages_workspace', table_name='booking_messages')
    op.drop_index('ix_booking_messages_booking', table_name='booking_messages')
    op.drop_table('booking_messages')
    op.drop_column('booking_settings', 'sms_messages_enabled')

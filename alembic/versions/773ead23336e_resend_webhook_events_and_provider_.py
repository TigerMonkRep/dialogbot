"""resend webhook events and provider delivery status

Revision ID: 773ead23336e
Revises: 94af55693109
Create Date: 2026-09-25 19:38:33.767481
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '773ead23336e'
down_revision = '94af55693109'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('webhook_events',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('provider', sa.String(length=32), nullable=False),
    sa.Column('event_id', sa.String(length=200), nullable=False),
    sa.Column('event_type', sa.String(length=64), nullable=False),
    sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('outcome', sa.String(length=16), nullable=False),
    sa.Column('received_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('provider', 'event_id', name='uq_webhook_events_provider_event')
    )
    op.add_column('email_deliveries', sa.Column('provider_message_id', sa.String(length=100), nullable=True))
    op.add_column('email_deliveries', sa.Column('provider_status', sa.String(length=32), nullable=True))
    op.add_column('email_deliveries', sa.Column('provider_status_at', sa.DateTime(timezone=True), nullable=True))
    op.create_unique_constraint('email_deliveries_provider_message_id_key', 'email_deliveries', ['provider_message_id'])


def downgrade() -> None:
    op.drop_constraint('email_deliveries_provider_message_id_key', 'email_deliveries', type_='unique')
    op.drop_column('email_deliveries', 'provider_status_at')
    op.drop_column('email_deliveries', 'provider_status')
    op.drop_column('email_deliveries', 'provider_message_id')
    op.drop_table('webhook_events')

"""customer links and verifications: W04 number code in the chat, W09 callback/preferences link, W13 booking link

Revision ID: c5e1f7a3d9b2
Revises: a7d3e9c2b5f1
Create Date: 2026-11-13 09:00:00
"""
from alembic import op
import sqlalchemy as sa

revision = 'c5e1f7a3d9b2'
down_revision = 'a7d3e9c2b5f1'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('leads', sa.Column('phone_verified_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('leads', sa.Column('callback_cancelled_at', sa.DateTime(timezone=True), nullable=True))
    op.create_table(
        'customer_links',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('workspace_id', sa.UUID(), nullable=False),
        sa.Column('purpose', sa.String(length=16), nullable=False),
        sa.Column('token_hash', sa.String(length=64), nullable=False),
        sa.Column('lead_id', sa.UUID(), nullable=True),
        sa.Column('booking_id', sa.UUID(), nullable=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("purpose in ('callback','booking')", name='ck_customer_links_purpose'),
        sa.CheckConstraint("(purpose = 'callback' and lead_id is not null) or (purpose = 'booking' and booking_id is not null)",
                           name='ck_customer_links_object'),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['lead_id'], ['leads.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['booking_id'], ['bookings.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('token_hash', name='uq_customer_links_token'),
    )
    op.create_index('ix_customer_links_lead', 'customer_links', ['lead_id'])
    op.create_index('ix_customer_links_booking', 'customer_links', ['booking_id'])
    op.create_table(
        'customer_verifications',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('workspace_id', sa.UUID(), nullable=False),
        sa.Column('purpose', sa.String(length=24), nullable=False),
        sa.Column('conversation_id', sa.UUID(), nullable=True),
        sa.Column('link_id', sa.UUID(), nullable=True),
        sa.Column('phone', sa.String(length=20), nullable=False),
        sa.Column('code_hash', sa.String(length=64), nullable=False),
        sa.Column('attempts', sa.Integer(), nullable=False),
        sa.Column('ip_hash', sa.String(length=64), nullable=False),
        sa.Column('sent_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('verified_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('session_hash', sa.String(length=64), nullable=True),
        sa.Column('session_expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("purpose in ('webchat_phone','booking_manage')", name='ck_customer_verifications_purpose'),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['link_id'], ['customer_links.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_customer_verifications_phone_sent', 'customer_verifications', ['phone', 'sent_at'])
    op.create_index('ix_customer_verifications_ip_sent', 'customer_verifications', ['ip_hash', 'sent_at'])
    op.create_index('ix_customer_verifications_conversation', 'customer_verifications', ['conversation_id'])
    op.create_index('ix_customer_verifications_link', 'customer_verifications', ['link_id'])
    op.create_index('ix_customer_verifications_session', 'customer_verifications', ['session_hash'])


def downgrade() -> None:
    op.drop_index('ix_customer_verifications_session', table_name='customer_verifications')
    op.drop_index('ix_customer_verifications_link', table_name='customer_verifications')
    op.drop_index('ix_customer_verifications_conversation', table_name='customer_verifications')
    op.drop_index('ix_customer_verifications_ip_sent', table_name='customer_verifications')
    op.drop_index('ix_customer_verifications_phone_sent', table_name='customer_verifications')
    op.drop_table('customer_verifications')
    op.drop_index('ix_customer_links_booking', table_name='customer_links')
    op.drop_index('ix_customer_links_lead', table_name='customer_links')
    op.drop_table('customer_links')
    op.drop_column('leads', 'callback_cancelled_at')
    op.drop_column('leads', 'phone_verified_at')

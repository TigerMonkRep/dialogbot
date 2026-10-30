"""sales channel phase 3

Revision ID: d5e7f9a1b3c6
Revises: c4d6e8f0a2b4
Create Date: 2026-10-30 15:08:54.418916
"""
from alembic import op
import sqlalchemy as sa


revision = 'd5e7f9a1b3c6'
down_revision = 'c4d6e8f0a2b4'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('sales_offers',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('company_id', sa.UUID(), nullable=False),
    sa.Column('contact_id', sa.UUID(), nullable=True),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('package', sa.String(length=20), nullable=False),
    sa.Column('monthly_net_minor', sa.Integer(), nullable=False),
    sa.Column('setup_kind', sa.String(length=10), nullable=False),
    sa.Column('setup_net_minor', sa.Integer(), nullable=False),
    sa.Column('campaign_call_net_minor', sa.Integer(), nullable=False),
    sa.Column('campaign_minute_net_minor', sa.Integer(), nullable=False),
    sa.Column('inbound_included_minutes', sa.Integer(), nullable=False),
    sa.Column('inbound_extra_minute_net_minor', sa.Integer(), nullable=False),
    sa.Column('terms_version', sa.String(length=40), nullable=False),
    sa.Column('tax_basis_points', sa.Integer(), nullable=False),
    sa.Column('valid_until', sa.DateTime(timezone=True), nullable=False),
    sa.Column('status', sa.String(length=10), nullable=False),
    sa.Column('accept_token_hash', sa.String(length=64), nullable=True),
    sa.Column('sent_via', sa.String(length=8), nullable=True),
    sa.Column('sent_to', sa.String(length=320), nullable=True),
    sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('accepted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('accepted_by', sa.UUID(), nullable=True),
    sa.Column('agreement_id', sa.UUID(), nullable=True),
    sa.Column('workspace_id', sa.UUID(), nullable=True),
    sa.Column('first_invoice_paid_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_by', sa.UUID(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("sent_via is null or sent_via in ('email','sms','manual')", name='ck_sales_offers_sent_via'),
    sa.CheckConstraint("setup_kind in ('diy','specialist')", name='ck_sales_offers_setup_kind'),
    sa.CheckConstraint("status in ('draft','sent','accepted','expired','cancelled')", name='ck_sales_offers_status'),
    sa.ForeignKeyConstraint(['accepted_by'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['agreement_id'], ['reception_agreements.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['company_id'], ['sales_companies.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['contact_id'], ['sales_contacts.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('accept_token_hash'),
    sa.UniqueConstraint('company_id', 'version', name='uq_sales_offers_company_version')
    )
    op.create_index('ix_sales_offers_status', 'sales_offers', ['status', 'created_at'], unique=False)
    op.create_table('sales_meetings',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('company_id', sa.UUID(), nullable=False),
    sa.Column('contact_id', sa.UUID(), nullable=True),
    sa.Column('booking_id', sa.UUID(), nullable=True),
    sa.Column('campaign_contact_id', sa.UUID(), nullable=True),
    sa.Column('starts_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('status', sa.String(length=10), nullable=False),
    sa.Column('calendar_confirmed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('note', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("status in ('proposed','confirmed','cancelled','held','no_show')", name='ck_sales_meetings_status'),
    sa.ForeignKeyConstraint(['booking_id'], ['bookings.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['campaign_contact_id'], ['campaign_contacts.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['company_id'], ['sales_companies.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['contact_id'], ['sales_contacts.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_sales_meetings_company', 'sales_meetings', ['company_id', 'created_at'], unique=False)
    op.create_table('sales_message_requests',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('company_id', sa.UUID(), nullable=False),
    sa.Column('contact_id', sa.UUID(), nullable=True),
    sa.Column('offer_id', sa.UUID(), nullable=True),
    sa.Column('campaign_contact_id', sa.UUID(), nullable=True),
    sa.Column('provider_call_id', sa.String(length=100), nullable=True),
    sa.Column('kind', sa.String(length=14), nullable=False),
    sa.Column('channel', sa.String(length=6), nullable=False),
    sa.Column('destination', sa.String(length=320), nullable=False),
    sa.Column('requested_quote', sa.Text(), nullable=False),
    sa.Column('status', sa.String(length=10), nullable=False),
    sa.Column('outbox_event_id', sa.UUID(), nullable=True),
    sa.Column('error', sa.String(length=300), nullable=True),
    sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("channel in ('email','sms')", name='ck_sales_message_requests_channel'),
    sa.CheckConstraint("kind in ('order_link','offer_summary')", name='ck_sales_message_requests_kind'),
    sa.CheckConstraint("status in ('requested','sent','failed','cancelled')", name='ck_sales_message_requests_status'),
    sa.ForeignKeyConstraint(['campaign_contact_id'], ['campaign_contacts.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['company_id'], ['sales_companies.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['contact_id'], ['sales_contacts.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['outbox_event_id'], ['outbox_events.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['offer_id'], ['sales_offers.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_sales_message_requests_status', 'sales_message_requests', ['status', 'created_at'], unique=False)
    op.add_column('reception_agreements', sa.Column('setup_net_minor', sa.Integer(), server_default='0', nullable=False))
    op.add_column('reception_agreements', sa.Column('sales_offer_id', sa.Uuid(), nullable=True))
    op.create_foreign_key('sales_scripts_offer_id_fkey', 'sales_scripts', 'sales_offers', ['offer_id'], ['id'],
                          ondelete='SET NULL')


def downgrade() -> None:
    op.drop_constraint('sales_scripts_offer_id_fkey', 'sales_scripts', type_='foreignkey')
    op.drop_column('reception_agreements', 'sales_offer_id')
    op.drop_column('reception_agreements', 'setup_net_minor')
    op.drop_index('ix_sales_message_requests_status', table_name='sales_message_requests')
    op.drop_table('sales_message_requests')
    op.drop_index('ix_sales_meetings_company', table_name='sales_meetings')
    op.drop_table('sales_meetings')
    op.drop_index('ix_sales_offers_status', table_name='sales_offers')
    op.drop_table('sales_offers')

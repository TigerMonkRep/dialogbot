"""platform managed telephony

Revision ID: e668ed509035
Revises: 527c5e36aced
Create Date: 2026-09-27 21:42:18.969148
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'e668ed509035'
down_revision = '527c5e36aced'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('telephony_accounts',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('provider', sa.String(length=16), nullable=False),
    sa.Column('kind', sa.String(length=16), nullable=False),
    sa.Column('workspace_id', sa.UUID(), nullable=True),
    sa.Column('external_id', sa.String(length=64), nullable=False),
    sa.Column('friendly_name', sa.String(length=120), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("kind in ('main','subaccount')", name='ck_telephony_accounts_kind'),
    sa.CheckConstraint("provider in ('twilio','vapi')", name='ck_telephony_accounts_provider'),
    sa.CheckConstraint("status in ('active','suspended','closed')", name='ck_telephony_accounts_status'),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('provider', 'external_id', name='uq_telephony_accounts_external')
    )
    op.create_index('uq_telephony_accounts_workspace_sub', 'telephony_accounts', ['workspace_id', 'provider'], unique=True, postgresql_where=sa.text("kind = 'subaccount'"))
    op.create_table('telephony_costs',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('workspace_id', sa.UUID(), nullable=False),
    sa.Column('provider', sa.String(length=16), nullable=False),
    sa.Column('kind', sa.String(length=32), nullable=False),
    sa.Column('reference', sa.String(length=120), nullable=False),
    sa.Column('amount_micros', sa.BigInteger(), nullable=True),
    sa.Column('currency', sa.String(length=3), nullable=False),
    sa.Column('details', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('occurred_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('provider', 'reference', 'kind', name='uq_telephony_costs_ref')
    )
    op.create_index('ix_telephony_costs_ws', 'telephony_costs', ['workspace_id', 'occurred_at'], unique=False)
    op.create_table('telephony_jobs',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('workspace_id', sa.UUID(), nullable=False),
    sa.Column('kind', sa.String(length=32), nullable=False),
    sa.Column('idempotency_key', sa.String(length=120), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('step', sa.String(length=32), nullable=False),
    sa.Column('state', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('attempts', sa.Integer(), nullable=False),
    sa.Column('last_error', sa.Text(), nullable=False),
    sa.Column('waiting_for', sa.String(length=40), nullable=False),
    sa.Column('next_attempt_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('locked_until', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("status in ('pending','running','waiting','succeeded','failed')", name='ck_telephony_jobs_status'),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('idempotency_key', name='uq_telephony_jobs_key')
    )
    op.create_index('ix_telephony_jobs_due', 'telephony_jobs', ['status', 'next_attempt_at'], unique=False)
    op.create_table('telephony_setups',
    sa.Column('workspace_id', sa.UUID(), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('business_number', sa.String(length=20), nullable=True),
    sa.Column('business_number_verified_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('business_number_verified_by', sa.String(length=60), nullable=True),
    sa.Column('verify_code_hash', sa.String(length=128), nullable=True),
    sa.Column('verify_expires_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('verify_attempts', sa.Integer(), nullable=False),
    sa.Column('verify_sent', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('subscription_type', sa.String(length=16), nullable=False),
    sa.Column('carrier', sa.String(length=80), nullable=False),
    sa.Column('forwarding_mode', sa.String(length=20), nullable=False),
    sa.Column('wants_new_number', sa.Boolean(), nullable=False),
    sa.Column('company_name', sa.String(length=200), nullable=False),
    sa.Column('cvr', sa.String(length=16), nullable=True),
    sa.Column('company_address', sa.String(length=300), nullable=False),
    sa.Column('document_key', sa.String(length=300), nullable=True),
    sa.Column('documents_status', sa.String(length=16), nullable=False),
    sa.Column('regulatory_bundle_sid', sa.String(length=64), nullable=True),
    sa.Column('regulatory_address_sid', sa.String(length=64), nullable=True),
    sa.Column('regulatory_note', sa.Text(), nullable=False),
    sa.Column('state', sa.String(length=16), nullable=False),
    sa.Column('destination_number_id', sa.UUID(), nullable=True),
    sa.Column('agreement_version', sa.Integer(), nullable=True),
    sa.Column('last_test_id', sa.UUID(), nullable=True),
    sa.Column('activated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('activated_by', sa.UUID(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("documents_status in ('not_required','missing','submitted','approved','rejected')", name='ck_telephony_setups_documents'),
    sa.CheckConstraint("forwarding_mode in ('always','no_answer','busy_or_no_answer')", name='ck_telephony_setups_forwarding'),
    sa.CheckConstraint("state in ('draft','provisioning','provisioned','active','paused')", name='ck_telephony_setups_state'),
    sa.CheckConstraint("subscription_type in ('mobile','landline','ip_pbx','unknown')", name='ck_telephony_setups_subscription'),
    sa.ForeignKeyConstraint(['activated_by'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['destination_number_id'], ['phone_numbers.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('workspace_id')
    )
    op.create_table('telephony_tests',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('workspace_id', sa.UUID(), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('simulated', sa.Boolean(), nullable=False),
    sa.Column('destination_number_id', sa.UUID(), nullable=True),
    sa.Column('called_business_number', sa.Boolean(), nullable=False),
    sa.Column('provider_call_id', sa.String(length=100), nullable=True),
    sa.Column('call_id', sa.UUID(), nullable=True),
    sa.Column('result', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('started_by', sa.UUID(), nullable=True),
    sa.Column('started_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint("status in ('waiting','passed','failed','expired')", name='ck_telephony_tests_status'),
    sa.ForeignKeyConstraint(['call_id'], ['calls.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['destination_number_id'], ['phone_numbers.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['started_by'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.add_column('phone_numbers', sa.Column('source', sa.String(length=24), server_default='legacy_customer', nullable=False))
    op.add_column('phone_numbers', sa.Column('status', sa.String(length=16), server_default='active', nullable=False))
    op.add_column('phone_numbers', sa.Column('telephony_account_id', sa.UUID(), nullable=True))
    op.add_column('phone_numbers', sa.Column('provider_sid', sa.String(length=64), nullable=True))
    op.add_column('phone_numbers', sa.Column('outbound_allowed', sa.Boolean(), server_default='false', nullable=False))
    op.create_unique_constraint('phone_numbers_provider_sid_key', 'phone_numbers', ['provider_sid'])
    op.create_foreign_key('fk_phone_numbers_telephony_account', 'phone_numbers', 'telephony_accounts',
                          ['telephony_account_id'], ['id'], ondelete='RESTRICT')
    op.create_foreign_key('fk_telephony_setups_last_test', 'telephony_setups', 'telephony_tests', ['last_test_id'], ['id'],
                          ondelete='SET NULL')
    op.create_check_constraint('ck_phone_numbers_source', 'phone_numbers', "source in ('platform','legacy_customer')")
    op.create_check_constraint('ck_phone_numbers_status', 'phone_numbers',
                               "status in ('provisioning','active','suspended','released')")
    # Keep existing (hand-mapped) numbers working: every workspace with an active legacy number gets an active setup
    # pointing at it, and numbers already used by a campaign keep the right to call out. New customers never take
    # this path. See docs/telephony/migration.md.
    op.execute("""
        INSERT INTO telephony_setups (workspace_id, version, state, destination_number_id, activated_at, subscription_type,
                                      forwarding_mode, documents_status, verify_attempts, verify_sent, wants_new_number,
                                      carrier, company_name, company_address, regulatory_note)
        SELECT DISTINCT ON (p.workspace_id) p.workspace_id, 1, 'active', p.id, now(), 'unknown', 'busy_or_no_answer',
               'not_required', 0, '[]'::jsonb, false, '', '', '', 'Migreret fra manuel nummeropsætning'
        FROM phone_numbers p WHERE p.active
        ORDER BY p.workspace_id, p.created_at
        ON CONFLICT (workspace_id) DO NOTHING
    """)
    op.execute("UPDATE phone_numbers SET outbound_allowed = true WHERE id IN (SELECT phone_number_id FROM campaigns "
               "WHERE phone_number_id IS NOT NULL)")


def downgrade() -> None:
    op.drop_constraint('fk_telephony_setups_last_test', 'telephony_setups', type_='foreignkey')
    op.drop_constraint('ck_phone_numbers_status', 'phone_numbers', type_='check')
    op.drop_constraint('ck_phone_numbers_source', 'phone_numbers', type_='check')
    op.drop_constraint('fk_phone_numbers_telephony_account', 'phone_numbers', type_='foreignkey')
    op.drop_constraint('phone_numbers_provider_sid_key', 'phone_numbers', type_='unique')
    op.drop_column('phone_numbers', 'outbound_allowed')
    op.drop_column('phone_numbers', 'provider_sid')
    op.drop_column('phone_numbers', 'telephony_account_id')
    op.drop_column('phone_numbers', 'status')
    op.drop_column('phone_numbers', 'source')
    op.drop_table('telephony_tests')
    op.drop_table('telephony_setups')
    op.drop_index('ix_telephony_jobs_due', table_name='telephony_jobs')
    op.drop_table('telephony_jobs')
    op.drop_index('ix_telephony_costs_ws', table_name='telephony_costs')
    op.drop_table('telephony_costs')
    op.drop_index('uq_telephony_accounts_workspace_sub', table_name='telephony_accounts', postgresql_where=sa.text("kind = 'subaccount'"))
    op.drop_table('telephony_accounts')

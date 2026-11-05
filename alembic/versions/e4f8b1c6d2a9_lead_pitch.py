"""lead pitch

Revision ID: e4f8b1c6d2a9
Revises: d3e7a2b5c9f1
Create Date: 2026-11-05 09:00:00

The lead loop: what happened to the fixed closing line of a Privat call (outcome, reason it was skipped, the closing excerpt),
and on `external_business_contacts` the consent behind a stored e-mail address and the lead it led to.
"""
from alembic import op
import sqlalchemy as sa


revision = 'e4f8b1c6d2a9'
down_revision = 'd3e7a2b5c9f1'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('external_business_contacts', sa.Column('consent_to_email', sa.Boolean(), server_default='false', nullable=False))
    op.add_column('external_business_contacts', sa.Column('consent_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('external_business_contacts', sa.Column('lead_id', sa.UUID(), nullable=True))
    op.create_foreign_key('fk_external_business_contacts_lead_id', 'external_business_contacts', 'leads', ['lead_id'], ['id'],
                          ondelete='SET NULL')
    op.add_column('private_calls', sa.Column('pitch_outcome', sa.String(length=16), nullable=True))
    op.add_column('private_calls', sa.Column('pitch_skipped_reason', sa.String(length=60), nullable=True))
    op.add_column('private_calls', sa.Column('pitch_transcript_excerpt', sa.String(length=500), nullable=True))
    op.add_column('private_calls', sa.Column('pitch_started_at', sa.DateTime(timezone=True), nullable=True))
    op.create_check_constraint('ck_private_calls_pitch_outcome', 'private_calls',
                              "pitch_outcome is null or pitch_outcome in ('interested','declined','skipped','not_asked')")


def downgrade() -> None:
    op.drop_constraint('ck_private_calls_pitch_outcome', 'private_calls', type_='check')
    op.drop_column('private_calls', 'pitch_started_at')
    op.drop_column('private_calls', 'pitch_transcript_excerpt')
    op.drop_column('private_calls', 'pitch_skipped_reason')
    op.drop_column('private_calls', 'pitch_outcome')
    op.drop_constraint('fk_external_business_contacts_lead_id', 'external_business_contacts', type_='foreignkey')
    op.drop_column('external_business_contacts', 'lead_id')
    op.drop_column('external_business_contacts', 'consent_at')
    op.drop_column('external_business_contacts', 'consent_to_email')

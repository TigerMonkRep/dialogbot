"""external business contacts

Revision ID: d3e7a2b5c9f1
Revises: c2d6e9f1a4b8
Create Date: 2026-11-04 23:00:00

Businesses that are not Dialogbot customers, as far as we know: the cache of what the assistant looked up about them (CVR
register, Google Places) so the same lookup is not paid for twice, and the base the lead loop (part B) builds on. Google
content is dropped after GOOGLE_PLACES_CACHE_DAYS; `place_id` stays.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'd3e7a2b5c9f1'
down_revision = 'c2d6e9f1a4b8'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('external_business_contacts',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('cvr', sa.String(length=8), nullable=True),
    sa.Column('phone_e164', sa.String(length=20), nullable=True),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('website', sa.String(length=500), nullable=True),
    sa.Column('booking_profile_id', sa.UUID(), nullable=True),
    sa.Column('is_dialogbot_customer', sa.Boolean(), server_default='false', nullable=False),
    sa.Column('blocklisted', sa.Boolean(), server_default='false', nullable=False),
    sa.Column('blocklist_reason', sa.String(length=40), nullable=True),
    sa.Column('last_pitch_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('pitch_count', sa.Integer(), server_default='0', nullable=False),
    sa.Column('last_outcome', sa.String(length=16), server_default='not_asked', nullable=False),
    sa.Column('email', sa.String(length=320), nullable=True),
    sa.Column('lookup_key', sa.String(length=300), nullable=True),
    sa.Column('address', sa.String(length=300), nullable=True),
    sa.Column('city', sa.String(length=100), nullable=True),
    sa.Column('place_id', sa.String(length=300), nullable=True),
    sa.Column('opening_hours', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('advertising_protected', sa.Boolean(), nullable=True),
    sa.Column('cvr_looked_up_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('google_looked_up_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("last_outcome in ('interested','declined','skipped','not_asked')", name='ck_external_business_contacts_outcome'),
    sa.ForeignKeyConstraint(['booking_profile_id'], ['business_booking_profiles.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('lookup_key')
    )
    op.create_index('uq_external_business_contacts_cvr', 'external_business_contacts', ['cvr'], unique=True, postgresql_where='cvr is not null')
    op.create_index('uq_external_business_contacts_phone', 'external_business_contacts', ['phone_e164'], unique=True, postgresql_where='phone_e164 is not null')


def downgrade() -> None:
    op.drop_index('uq_external_business_contacts_phone', table_name='external_business_contacts', postgresql_where='phone_e164 is not null')
    op.drop_index('uq_external_business_contacts_cvr', table_name='external_business_contacts', postgresql_where='cvr is not null')
    op.drop_table('external_business_contacts')

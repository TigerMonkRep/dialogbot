"""waitlist signups

Revision ID: c432350c7efd
Revises: 43c189532412
Create Date: 2026-09-25 20:19:29.157009
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'c432350c7efd'
down_revision = '43c189532412'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('waitlist_signups',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('email', sa.String(length=320), nullable=False),
    sa.Column('industry', sa.String(length=32), nullable=True),
    sa.Column('interests', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('source', sa.String(length=16), nullable=False),
    sa.Column('consent_version', sa.String(length=32), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('email', name='waitlist_signups_email_key')
    )


def downgrade() -> None:
    op.drop_table('waitlist_signups')

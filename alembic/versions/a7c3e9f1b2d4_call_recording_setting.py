"""telephony: customers choose per number whether calls are recorded, and for how long the audio is kept

Revision ID: a7c3e9f1b2d4
Revises: e3b7c9d1a5f4
Create Date: 2026-11-09 15:00:00

Additive: two columns on phone_numbers. Off by default – nothing is recorded until the customer turns it on.
"""
import sqlalchemy as sa

from alembic import op

revision = 'a7c3e9f1b2d4'
down_revision = 'e3b7c9d1a5f4'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('phone_numbers', sa.Column('record_calls', sa.Boolean(), server_default='false', nullable=False))
    op.add_column('phone_numbers', sa.Column('recording_retention_days', sa.Integer(), server_default='90',
                                             nullable=False))


def downgrade() -> None:
    op.drop_column('phone_numbers', 'recording_retention_days')
    op.drop_column('phone_numbers', 'record_calls')

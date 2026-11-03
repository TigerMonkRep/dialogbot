"""calls.recording_url: the provider's recording of the call (Vapi end-of-call report)

Revision ID: b8d4f0a2c6e1
Revises: a7c3e9d1f5b2
Create Date: 2026-11-03 15:35:00
"""
from alembic import op
import sqlalchemy as sa

revision = 'b8d4f0a2c6e1'
down_revision = 'a7c3e9d1f5b2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('calls', sa.Column('recording_url', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('calls', 'recording_url')

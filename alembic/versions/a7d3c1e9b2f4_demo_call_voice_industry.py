"""demo calls: chosen voice and industry

Revision ID: a7d3c1e9b2f4
Revises: bcc6a80d2f06
"""
from alembic import op
import sqlalchemy as sa

revision = 'a7d3c1e9b2f4'
down_revision = 'bcc6a80d2f06'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('demo_calls', sa.Column('voice_key', sa.String(length=40), nullable=True))
    op.add_column('demo_calls', sa.Column('industry', sa.String(length=40), nullable=True))


def downgrade() -> None:
    op.drop_column('demo_calls', 'industry')
    op.drop_column('demo_calls', 'voice_key')

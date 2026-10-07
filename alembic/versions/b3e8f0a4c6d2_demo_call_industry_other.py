"""demo calls: the visitor's own industry text

Revision ID: b3e8f0a4c6d2
Revises: a7d3c1e9b2f4
"""
from alembic import op
import sqlalchemy as sa

revision = 'b3e8f0a4c6d2'
down_revision = 'a7d3c1e9b2f4'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('demo_calls', sa.Column('industry_other', sa.String(length=80), nullable=True))


def downgrade() -> None:
    op.drop_column('demo_calls', 'industry_other')

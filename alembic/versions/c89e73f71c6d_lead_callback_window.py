"""lead callback window

Revision ID: c89e73f71c6d
Revises: 19a35ecb7df3
Create Date: 2026-09-25 22:02:23.570588
"""
from alembic import op
import sqlalchemy as sa


revision = 'c89e73f71c6d'
down_revision = '19a35ecb7df3'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('leads', sa.Column('callback_from', sa.DateTime(timezone=True), nullable=True))
    op.add_column('leads', sa.Column('callback_to', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('leads', 'callback_to')
    op.drop_column('leads', 'callback_from')

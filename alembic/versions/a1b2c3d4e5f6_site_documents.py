"""site documents

Revision ID: a1b2c3d4e5f6
Revises: 7c4e9b1a5d30
Create Date: 2026-10-29 10:40:00
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'a1b2c3d4e5f6'
down_revision = '7c4e9b1a5d30'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('site_documents',
    sa.Column('slug', sa.String(length=64), nullable=False),
    sa.Column('blob', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('updated_by', sa.UUID(), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['updated_by'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('slug'),
    )


def downgrade() -> None:
    op.drop_table('site_documents')

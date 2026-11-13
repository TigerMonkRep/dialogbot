"""social posts: pipeline trail

Revision ID: a7d3e9c1b5f2
Revises: c5e1f7a3d9b2
Create Date: 2026-11-13 12:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = 'a7d3e9c1b5f2'
down_revision = 'c5e1f7a3d9b2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Existing posts get an empty trail (they were made before the trail existed).
    op.add_column('social_posts', sa.Column('pipeline', postgresql.JSONB(astext_type=sa.Text()),
                                            server_default=sa.text("'[]'::jsonb"), nullable=False))


def downgrade() -> None:
    op.drop_column('social_posts', 'pipeline')

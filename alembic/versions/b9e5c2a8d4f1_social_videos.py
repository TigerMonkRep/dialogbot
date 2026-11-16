"""social videos: manuscripts, score, cost and metrics for short-form video

Revision ID: b9e5c2a8d4f1
Revises: d6f2a8c4e1b7
Create Date: 2026-11-16 20:30:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = 'b9e5c2a8d4f1'
down_revision = 'd6f2a8c4e1b7'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'social_videos',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('topic', sa.String(length=40), nullable=False),
        sa.Column('formula', sa.String(length=24), nullable=False),
        sa.Column('hook_formula', sa.String(length=24), nullable=True),
        sa.Column('status', sa.String(length=12), nullable=False),
        sa.Column('brief', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('score', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('generator', sa.String(length=16), nullable=False),
        sa.Column('generator_model', sa.String(length=80), nullable=True),
        sa.Column('note', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('est_cost_dkk', sa.Numeric(8, 2), server_default=sa.text('0'), nullable=False),
        sa.Column('approved_by_user_id', sa.UUID(), nullable=True),
        sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('post_ids', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column('metrics', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('metrics_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("status in ('draft','approved','rejected','rendered','published')", name='ck_social_videos_status'),
        sa.ForeignKeyConstraint(['approved_by_user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_social_videos_status_created', 'social_videos', ['status', 'created_at'])


def downgrade() -> None:
    op.drop_index('ix_social_videos_status_created', table_name='social_videos')
    op.drop_table('social_videos')

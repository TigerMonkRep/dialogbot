"""ai usage log

Revision ID: 43c189532412
Revises: 773ead23336e
Create Date: 2026-09-25 19:50:19.298059
"""
from alembic import op
import sqlalchemy as sa


revision = '43c189532412'
down_revision = '773ead23336e'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('ai_usage',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('workspace_id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=True),
    sa.Column('purpose', sa.String(length=32), nullable=False),
    sa.Column('provider', sa.String(length=32), nullable=False),
    sa.Column('requested_model', sa.String(length=100), nullable=False),
    sa.Column('served_model', sa.String(length=100), nullable=True),
    sa.Column('prompt_version', sa.String(length=32), nullable=False),
    sa.Column('knowledge_revision', sa.Integer(), nullable=False),
    sa.Column('outcome', sa.String(length=16), nullable=False),
    sa.Column('stop_reason', sa.String(length=32), nullable=True),
    sa.Column('input_tokens', sa.Integer(), nullable=False),
    sa.Column('output_tokens', sa.Integer(), nullable=False),
    sa.Column('cache_creation_input_tokens', sa.Integer(), nullable=False),
    sa.Column('cache_read_input_tokens', sa.Integer(), nullable=False),
    sa.Column('est_cost_usd_micros', sa.BigInteger(), nullable=True),
    sa.Column('latency_ms', sa.Integer(), nullable=False),
    sa.Column('provider_request_id', sa.String(length=100), nullable=True),
    sa.Column('error_code', sa.String(length=64), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_ai_usage_workspace_created', 'ai_usage', ['workspace_id', 'created_at'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_ai_usage_workspace_created', table_name='ai_usage')
    op.drop_table('ai_usage')

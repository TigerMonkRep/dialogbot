"""assistant requests («ønsker»)

Revision ID: c3e5a7f9b1d4
Revises: b8d4f0a2c6e1
Create Date: 2026-11-03 23:30:00

Additive: one new table for the wishes the assistant could not fulfil (or features customers asked for). Dialogbot's
operators see them in /app/operator/oensker.
"""
import sqlalchemy as sa
from alembic import op

revision = 'c3e5a7f9b1d4'
down_revision = 'b8d4f0a2c6e1'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('assistant_requests',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('workspace_id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=True),
    sa.Column('text', sa.Text(), nullable=False),
    sa.Column('page', sa.String(length=200), nullable=True),
    sa.Column('summary', sa.Text(), nullable=False),
    sa.Column('category', sa.String(length=20), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('admin_note', sa.Text(), nullable=False),
    sa.Column('times_asked', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("status in ('new','planned','done','declined')", name='ck_assistant_requests_status'),
    sa.CheckConstraint("category in ('phone','voice','knowledge','booking','webchat','campaigns','reports',"
                       "'integrations','account','other')", name='ck_assistant_requests_category'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_assistant_requests_ws_created', 'assistant_requests', ['workspace_id', 'created_at'], unique=False)
    op.create_index('ix_assistant_requests_status_updated', 'assistant_requests', ['status', 'updated_at'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_assistant_requests_status_updated', table_name='assistant_requests')
    op.drop_index('ix_assistant_requests_ws_created', table_name='assistant_requests')
    op.drop_table('assistant_requests')

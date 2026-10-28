"""assistant proposals

Revision ID: 7c4e9b1a5d30
Revises: 5b7e1c9a3d42
Create Date: 2026-10-28

Additive: one new table for the changes the assistant «Ændr noget» proposes (kept until the person approves).
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = '7c4e9b1a5d30'
down_revision = '5b7e1c9a3d42'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('assistant_proposals',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('workspace_id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=True),
    sa.Column('kind', sa.String(length=40), nullable=False),
    sa.Column('params', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('request_text', sa.Text(), nullable=False),
    sa.Column('summary', sa.Text(), nullable=False),
    sa.Column('before', sa.Text(), nullable=False),
    sa.Column('after', sa.Text(), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('decided_at', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint("status in ('proposed','applied','declined','expired')", name='ck_assistant_proposals_status'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_assistant_proposals_ws_created', 'assistant_proposals', ['workspace_id', 'created_at'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_assistant_proposals_ws_created', table_name='assistant_proposals')
    op.drop_table('assistant_proposals')

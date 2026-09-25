"""webchat conversations

Revision ID: 501a6eb0eaeb
Revises: c432350c7efd
Create Date: 2026-09-25 20:53:10.565928
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '501a6eb0eaeb'
down_revision = 'c432350c7efd'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('conversations',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('workspace_id', sa.UUID(), nullable=False),
    sa.Column('channel', sa.String(length=16), nullable=False),
    sa.Column('visitor_token_digest', sa.String(length=64), nullable=False),
    sa.Column('origin', sa.String(length=200), nullable=True),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('visitor_message_count', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('last_message_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_conversations_workspace_last', 'conversations', ['workspace_id', 'last_message_at'], unique=False)
    op.create_table('webchat_settings',
    sa.Column('workspace_id', sa.UUID(), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('enabled', sa.Boolean(), nullable=False),
    sa.Column('widget_key', sa.String(length=64), nullable=False),
    sa.Column('allowed_origins', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('greeting', sa.Text(), nullable=False),
    sa.Column('last_seen_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_seen_origin', sa.String(length=200), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('workspace_id'),
    sa.UniqueConstraint('widget_key', name='webchat_settings_widget_key_key')
    )
    op.create_table('conversation_messages',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('conversation_id', sa.UUID(), nullable=False),
    sa.Column('workspace_id', sa.UUID(), nullable=False),
    sa.Column('role', sa.String(length=16), nullable=False),
    sa.Column('text', sa.Text(), nullable=False),
    sa.Column('ai_usage_id', sa.UUID(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['ai_usage_id'], ['ai_usage.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_conversation_messages_conv_created', 'conversation_messages', ['conversation_id', 'created_at'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_conversation_messages_conv_created', table_name='conversation_messages')
    op.drop_table('conversation_messages')
    op.drop_table('webchat_settings')
    op.drop_index('ix_conversations_workspace_last', table_name='conversations')
    op.drop_table('conversations')

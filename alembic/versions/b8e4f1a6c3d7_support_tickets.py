"""support tickets: customer support (H01) and the operators' support queue (M06)

Revision ID: b8e4f1a6c3d7
Revises: a7d3e9c2b5f1
Create Date: 2026-11-13 10:00:00
"""
from alembic import op
import sqlalchemy as sa

revision = 'b8e4f1a6c3d7'
down_revision = 'a7d3e9c2b5f1'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'support_tickets',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('workspace_id', sa.UUID(), nullable=False),
        sa.Column('number', sa.Integer(), nullable=False),
        sa.Column('subject', sa.String(length=160), nullable=False),
        sa.Column('category', sa.String(length=20), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('priority', sa.String(length=10), server_default='normal', nullable=False),
        sa.Column('context_path', sa.String(length=200), server_default='', nullable=False),
        sa.Column('created_by', sa.UUID(), nullable=True),
        sa.Column('assigned_to', sa.UUID(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status in ('open', 'in_progress', 'waiting_customer', 'resolved')",
                           name='ck_support_tickets_status'),
        sa.CheckConstraint("category in ('reception', 'campaigns', 'calendar', 'billing', 'other')",
                           name='ck_support_tickets_category'),
        sa.CheckConstraint("priority in ('low', 'normal', 'high', 'critical')", name='ck_support_tickets_priority'),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['assigned_to'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('workspace_id', 'number', name='uq_support_tickets_workspace_number'),
    )
    op.create_index('ix_support_tickets_status_updated', 'support_tickets', ['status', 'updated_at'])
    op.create_index('ix_support_tickets_assigned', 'support_tickets', ['assigned_to'])
    op.create_table(
        'support_messages',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('ticket_id', sa.UUID(), nullable=False),
        sa.Column('workspace_id', sa.UUID(), nullable=False),
        sa.Column('author_user_id', sa.UUID(), nullable=True),
        sa.Column('author_kind', sa.String(length=10), nullable=False),
        sa.Column('visibility', sa.String(length=10), nullable=False),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("author_kind in ('customer','operator')", name='ck_support_messages_author_kind'),
        sa.CheckConstraint("visibility in ('public','internal')", name='ck_support_messages_visibility'),
        sa.CheckConstraint("author_kind = 'operator' or visibility = 'public'", name='ck_support_messages_customer_public'),
        sa.ForeignKeyConstraint(['ticket_id'], ['support_tickets.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['author_user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_support_messages_ticket_created', 'support_messages', ['ticket_id', 'created_at'])
    op.create_table(
        'support_attachments',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('ticket_id', sa.UUID(), nullable=False),
        sa.Column('message_id', sa.UUID(), nullable=False),
        sa.Column('workspace_id', sa.UUID(), nullable=False),
        sa.Column('filename', sa.String(length=120), nullable=False),
        sa.Column('content_type', sa.String(length=40), nullable=False),
        sa.Column('size_bytes', sa.Integer(), nullable=False),
        sa.Column('sha256', sa.String(length=64), nullable=False),
        sa.Column('storage_key', sa.String(length=250), nullable=False),
        sa.Column('uploaded_by', sa.UUID(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['ticket_id'], ['support_tickets.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['message_id'], ['support_messages.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['uploaded_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_support_attachments_message', 'support_attachments', ['message_id'])


def downgrade() -> None:
    op.drop_index('ix_support_attachments_message', table_name='support_attachments')
    op.drop_table('support_attachments')
    op.drop_index('ix_support_messages_ticket_created', table_name='support_messages')
    op.drop_table('support_messages')
    op.drop_index('ix_support_tickets_assigned', table_name='support_tickets')
    op.drop_index('ix_support_tickets_status_updated', table_name='support_tickets')
    op.drop_table('support_tickets')

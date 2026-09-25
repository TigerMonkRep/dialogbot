"""conversation mode and staff author

Revision ID: 19a35ecb7df3
Revises: 46c794fe9e35
Create Date: 2026-09-25 21:50:10.690777
"""
from alembic import op
import sqlalchemy as sa


revision = '19a35ecb7df3'
down_revision = '46c794fe9e35'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('conversation_messages', sa.Column('author_user_id', sa.UUID(), nullable=True))
    op.create_foreign_key('conversation_messages_author_user_id_fkey', 'conversation_messages', 'users', ['author_user_id'], ['id'], ondelete='SET NULL')
    op.add_column('conversations', sa.Column('mode', sa.String(length=8), server_default='ai', nullable=False))


def downgrade() -> None:
    op.drop_column('conversations', 'mode')
    op.drop_constraint('conversation_messages_author_user_id_fkey', 'conversation_messages', type_='foreignkey')
    op.drop_column('conversation_messages', 'author_user_id')

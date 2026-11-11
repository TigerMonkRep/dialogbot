"""privat: Familie household members and «Eksportér mine data»

Revision ID: c9e4a7d2b1f6
Revises: c8e4a1f6d2b9 (rebased onto main's head when origin/main was merged in)
Create Date: 2026-11-10 22:30:00

private_household_members: up to 4 people in a Familie subscriber's household (5 with the owner); rights are derived
from the owner's subscription when read. private_data_exports: the GDPR export the worker builds and the user fetches
with a link from an e-mail (only a hash of the token; the content is wiped when the link expires).
"""
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = 'c9e4a7d2b1f6'
down_revision = 'c8e4a1f6d2b9'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'private_household_members',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('owner_workspace_id', sa.UUID(), nullable=False),
        sa.Column('member_workspace_id', sa.UUID(), nullable=False),
        sa.Column('invite_id', sa.UUID(), nullable=True),
        sa.Column('joined_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint('owner_workspace_id <> member_workspace_id', name='ck_private_household_members_self'),
        sa.ForeignKeyConstraint(['owner_workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['member_workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['invite_id'], ['private_invites.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('member_workspace_id'),
    )
    op.create_index('ix_private_household_members_owner', 'private_household_members',
                    ['owner_workspace_id', 'joined_at'])
    op.create_table(
        'private_data_exports',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('token_hash', sa.String(length=64), nullable=True),
        sa.Column('data', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('requested_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('ready_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('downloaded_at', sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status in ('queued','ready','expired','failed')", name='ck_private_data_exports_status'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('token_hash'),
    )
    op.create_index('ix_private_data_exports_user', 'private_data_exports', ['user_id', 'requested_at'])


def downgrade() -> None:
    op.drop_index('ix_private_data_exports_user', table_name='private_data_exports')
    op.drop_table('private_data_exports')
    op.drop_index('ix_private_household_members_owner', table_name='private_household_members')
    op.drop_table('private_household_members')

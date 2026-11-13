"""workspace operator suspension (M03): pause a tenant's outbound work from the operations screen

Revision ID: c4e8a1f6d2b9
Revises: b8e4f1a6c3d7
Create Date: 2026-11-13 10:00:00
"""
from alembic import op
import sqlalchemy as sa

revision = 'c4e8a1f6d2b9'
down_revision = 'b8e4f1a6c3d7'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('workspaces', sa.Column('ops_suspended_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('workspaces', sa.Column('ops_suspended_reason', sa.String(length=300), nullable=True))
    op.add_column('workspaces', sa.Column('ops_suspended_by', sa.UUID(), nullable=True))
    op.create_foreign_key('fk_workspaces_ops_suspended_by_users', 'workspaces', 'users', ['ops_suspended_by'], ['id'],
                          ondelete='SET NULL')
    # the worker filters on it in every claim; almost every row is NULL, so a partial index stays tiny
    op.create_index('ix_workspaces_ops_suspended', 'workspaces', ['id'], postgresql_where=sa.text('ops_suspended_at IS NOT NULL'))


def downgrade() -> None:
    op.drop_index('ix_workspaces_ops_suspended', table_name='workspaces')
    op.drop_constraint('fk_workspaces_ops_suspended_by_users', 'workspaces', type_='foreignkey')
    op.drop_column('workspaces', 'ops_suspended_by')
    op.drop_column('workspaces', 'ops_suspended_reason')
    op.drop_column('workspaces', 'ops_suspended_at')

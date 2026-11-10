"""identity: «Se som kunde» sessions are scoped to one workspace and die with the operator

Revision ID: d6f1a4b8c3e5
Revises: c5e9f3a7b2d4
Create Date: 2026-11-10 14:00:00

- sessions.scope_workspace_id: a view-as session opened for one workspace only sees that workspace (QA F-EA-05-M02).
- sessions.impersonator_user_id ON DELETE CASCADE instead of SET NULL: deleting the operator must end the view-as
  session, never turn it into an ordinary (writable) session of the customer (QA F-EA-02-M02).
"""
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = 'd6f1a4b8c3e5'
down_revision = 'c5e9f3a7b2d4'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('sessions', sa.Column('scope_workspace_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key('fk_sessions_scope_workspace_id', 'sessions', 'workspaces', ['scope_workspace_id'], ['id'],
                          ondelete='CASCADE')
    op.drop_constraint('fk_sessions_impersonator_user_id', 'sessions', type_='foreignkey')
    op.create_foreign_key('fk_sessions_impersonator_user_id', 'sessions', 'users', ['impersonator_user_id'], ['id'],
                          ondelete='CASCADE')


def downgrade() -> None:
    op.drop_constraint('fk_sessions_impersonator_user_id', 'sessions', type_='foreignkey')
    op.create_foreign_key('fk_sessions_impersonator_user_id', 'sessions', 'users', ['impersonator_user_id'], ['id'],
                          ondelete='SET NULL')
    op.drop_constraint('fk_sessions_scope_workspace_id', 'sessions', type_='foreignkey')
    op.drop_column('sessions', 'scope_workspace_id')

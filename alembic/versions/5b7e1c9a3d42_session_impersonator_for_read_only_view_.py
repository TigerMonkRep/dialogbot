"""session impersonator for read only view as

Revision ID: 5b7e1c9a3d42
Revises: 64a2ddcb9a74
Create Date: 2026-10-28

Additive: one nullable column on sessions. A session with impersonator_user_id set is a read-only
"se som kunde" session opened by a platform operator (enforced in app.core.auth).
"""
import sqlalchemy as sa
from alembic import op

revision = '5b7e1c9a3d42'
down_revision = '64a2ddcb9a74'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('sessions', sa.Column('impersonator_user_id', sa.UUID(), nullable=True))
    op.create_foreign_key('fk_sessions_impersonator_user_id', 'sessions', 'users', ['impersonator_user_id'], ['id'],
                          ondelete='SET NULL')


def downgrade() -> None:
    op.drop_constraint('fk_sessions_impersonator_user_id', 'sessions', type_='foreignkey')
    op.drop_column('sessions', 'impersonator_user_id')

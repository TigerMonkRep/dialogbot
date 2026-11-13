"""merge heads: outreach to-do marks (#217) and social post pipeline (#218)

Both branched from c5e1f7a3d9b2, so main had two alembic heads and every CI job
that runs `alembic upgrade head` failed. No schema change – this only joins the
two lines so there is one head again.

Revision ID: e9a1c3b5d7f2
Revises: 1d2e6f8b0c4a, a7d3e9c1b5f2
"""

revision = "e9a1c3b5d7f2"
down_revision = ("1d2e6f8b0c4a", "a7d3e9c1b5f2")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass

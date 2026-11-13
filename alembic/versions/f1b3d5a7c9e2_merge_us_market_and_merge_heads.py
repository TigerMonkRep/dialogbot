"""merge heads: #219's US-market merge (2e3f7a9c1d5b) and #221's merge (e9a1c3b5d7f2)

#219 and #221 each joined the two heads left by #217/#218 with their own merge
revision, so main had two heads again. No schema change – only joins them.

Revision ID: f1b3d5a7c9e2
Revises: 2e3f7a9c1d5b, e9a1c3b5d7f2
"""

revision = "f1b3d5a7c9e2"
down_revision = ("2e3f7a9c1d5b", "e9a1c3b5d7f2")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass

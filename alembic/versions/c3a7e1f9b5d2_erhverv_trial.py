"""erhverv 14-day trial

Revision ID: c3a7e1f9b5d2
Revises: b9e5c2a8d4f1
Create Date: 2026-11-18 14:10:00
"""
from alembic import op
import sqlalchemy as sa

revision = 'c3a7e1f9b5d2'
down_revision = 'b9e5c2a8d4f1'
branch_labels = None
depends_on = None


def upgrade() -> None:
    for c in ("trial_started_at", "trial_ends_at", "trial_cancelled_at", "trial_mailed_at"):
        op.add_column("billing_accounts", sa.Column(c, sa.DateTime(timezone=True), nullable=True))
    op.create_table("trial_claims",
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("workspace_id", sa.UUID(), nullable=False),
        sa.Column("claimed_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("key"))


def downgrade() -> None:
    op.drop_table("trial_claims")
    for c in ("trial_mailed_at", "trial_cancelled_at", "trial_ends_at", "trial_started_at"):
        op.drop_column("billing_accounts", c)

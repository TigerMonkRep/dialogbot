"""privat: one free trial per card – private_trial_cards (Stripe card fingerprint, F-PBQ-02)

Revision ID: d7f2b9c4e1a8
Revises: c9e4a7d2b1f6
Create Date: 2026-11-11
"""
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = 'd7f2b9c4e1a8'
down_revision = 'c9e4a7d2b1f6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "private_trial_cards",
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("stripe_subscription_id", sa.String(length=100), nullable=True),
        sa.Column("first_trial_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("fingerprint"),
    )


def downgrade() -> None:
    op.drop_table("private_trial_cards")

"""demo calls: queue outside the calling hours (status scheduled, scheduled_for)

S0 «Erhverv døgnåbent»: a demo call asked for outside SALES_CALL_FROM/SALES_CALL_TO is queued for the next opening
instead of refused.

Revision ID: a16e24b7c9d1
Revises: f3a8c6d2b5e9
Create Date: 2026-11-11
"""
import sqlalchemy as sa

from alembic import op

revision = 'a16e24b7c9d1'
down_revision = 'f3a8c6d2b5e9'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("demo_calls", sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=True))
    op.drop_constraint("ck_demo_calls_status", "demo_calls", type_="check")
    op.create_check_constraint("ck_demo_calls_status", "demo_calls",
                               "status in ('scheduled','calling','done','no_answer','failed','skipped')")
    op.create_index("ix_demo_calls_scheduled", "demo_calls", ["scheduled_for"],
                    postgresql_where=sa.text("status = 'scheduled'"))


def downgrade() -> None:
    # Queued calls that were never placed cannot be represented without the column: they are dropped as skipped.
    op.execute("update demo_calls set status = 'skipped', error = 'Kø fjernet ved nedgradering' "
               "where status = 'scheduled'")
    op.drop_index("ix_demo_calls_scheduled", table_name="demo_calls")
    op.drop_constraint("ck_demo_calls_status", "demo_calls", type_="check")
    op.create_check_constraint("ck_demo_calls_status", "demo_calls",
                               "status in ('calling','done','no_answer','failed','skipped')")
    op.drop_column("demo_calls", "scheduled_for")

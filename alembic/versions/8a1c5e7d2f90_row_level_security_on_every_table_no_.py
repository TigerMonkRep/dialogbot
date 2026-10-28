"""row level security on every table, no rights for anon and authenticated

Revision ID: 8a1c5e7d2f90
Revises: 64a2ddcb9a74
Create Date: 2026-10-28

Enables RLS on every table of the application schema, gives the app role (`dialogbot_app`, which is not BYPASSRLS) one
explicit all-rows policy, and removes every right from `anon`/`authenticated` (tables, sequences, functions, schema,
default privileges). See app/core/rls.py. alembic/env.py repeats the same idempotent step after every upgrade, so later
tables are covered too. Downgrade switches RLS off again but leaves the revoked rights revoked (nothing relied on them).
"""
from __future__ import annotations

from alembic import op

revision = '8a1c5e7d2f90'
down_revision = '64a2ddcb9a74'
branch_labels = None
depends_on = None


def upgrade() -> None:
    from app.core.rls import secure_schema

    bind = op.get_bind()
    secure_schema(bind, bind.exec_driver_sql("select current_schema()").scalar())


def downgrade() -> None:
    op.execute("""
        DO $$ DECLARE t record; BEGIN
          FOR t IN SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
                   WHERE n.nspname = current_schema() AND c.relkind IN ('r','p') AND pg_get_userbyid(c.relowner) = current_user
          LOOP
            EXECUTE format('DROP POLICY IF EXISTS dialogbot_app_all ON %I.%I', current_schema(), t.relname);
            EXECUTE format('ALTER TABLE %I.%I DISABLE ROW LEVEL SECURITY', current_schema(), t.relname);
          END LOOP;
        END $$
    """)

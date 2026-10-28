"""Row Level Security for the application schema.

The app talks to Postgres as one role (`APP_ROLE`, via the pooler) – never through Supabase Auth or PostgREST – so RLS
is not how tenants are separated (the application's workspace checks do that). It is the safety net behind the
Supabase "Data API": with RLS on and no policy for `anon`/`authenticated`, a leaked anon key reads and writes nothing,
even if a grant is ever added by mistake. We also take every right away from those two roles.

`secure_schema()` is idempotent and is called by the migration that introduces RLS **and** by alembic/env.py after every
`upgrade`, so a table created by a later migration is covered automatically. tests/test_rls.py fails if one is not.

* Tables owned by someone else than the connecting role cannot be altered and are skipped with a NOTICE.
* Roles that do not exist (the test database has no Supabase roles) are skipped, not created.
"""
from __future__ import annotations

import re

from sqlalchemy import text

APP_ROLE = "dialogbot_app"
EXPOSED_ROLES = ("anon", "authenticated")
POLICY = "dialogbot_app_all"

_SQL = """
DO $rls$
DECLARE
    s text := '@SCHEMA@';
    t record;
    r text;
BEGIN
    -- 1) RLS on every table we own; the app role gets one explicit all-rows policy (it is not BYPASSRLS).
    FOR t IN SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
             WHERE n.nspname = s AND c.relkind IN ('r', 'p') AND pg_get_userbyid(c.relowner) = current_user
    LOOP
        EXECUTE format('ALTER TABLE %I.%I ENABLE ROW LEVEL SECURITY', s, t.relname);
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '@APP@')
           AND NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname = s AND tablename = t.relname AND policyname = '@POLICY@')
        THEN
            EXECUTE format('CREATE POLICY %I ON %I.%I AS PERMISSIVE FOR ALL TO %I USING (true) WITH CHECK (true)',
                           '@POLICY@', s, t.relname, '@APP@');
        END IF;
    END LOOP;
    FOR t IN SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
             WHERE n.nspname = s AND c.relkind IN ('r', 'p') AND pg_get_userbyid(c.relowner) <> current_user
    LOOP
        RAISE NOTICE 'rls: % not owned by %, skipped', t.relname, current_user;
    END LOOP;

    -- 2) The Data API roles get nothing: tables, sequences, functions, the schema itself, and future objects.
    FOREACH r IN ARRAY ARRAY[@EXPOSED@] LOOP
        CONTINUE WHEN NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r);
        FOR t IN SELECT c.relname, c.relkind FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
                 WHERE n.nspname = s AND c.relkind IN ('r', 'p', 'v', 'm', 'S', 'f')
                   AND pg_get_userbyid(c.relowner) = current_user
        LOOP
            IF t.relkind = 'S' THEN
                EXECUTE format('REVOKE ALL ON SEQUENCE %I.%I FROM %I', s, t.relname, r);
            ELSE
                EXECUTE format('REVOKE ALL ON TABLE %I.%I FROM %I', s, t.relname, r);
            END IF;
        END LOOP;
        FOR t IN SELECT p.oid::regprocedure::text AS sig FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
                 WHERE n.nspname = s AND pg_get_userbyid(p.proowner) = current_user
        LOOP
            EXECUTE format('REVOKE ALL ON FUNCTION %s FROM %I', t.sig, r);
        END LOOP;
        IF EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = s AND pg_get_userbyid(nspowner) = current_user) THEN
            EXECUTE format('REVOKE ALL ON SCHEMA %I FROM %I', s, r);
        END IF;
        EXECUTE format('ALTER DEFAULT PRIVILEGES IN SCHEMA %I REVOKE ALL ON TABLES FROM %I', s, r);
        EXECUTE format('ALTER DEFAULT PRIVILEGES IN SCHEMA %I REVOKE ALL ON SEQUENCES FROM %I', s, r);
        EXECUTE format('ALTER DEFAULT PRIVILEGES IN SCHEMA %I REVOKE ALL ON FUNCTIONS FROM %I', s, r);
    END LOOP;
END
$rls$
"""


def secure_schema(connection, schema: str) -> None:
    # A DO block cannot take bind parameters, so the (constant, validated) names are put into the text.
    if not re.fullmatch(r"[a-z_][a-z0-9_]*", schema):
        raise ValueError(f"unsafe schema name: {schema!r}")
    sql = (_SQL.replace("@SCHEMA@", schema).replace("@APP@", APP_ROLE).replace("@POLICY@", POLICY)
           .replace("@EXPOSED@", ", ".join(f"'{r}'" for r in EXPOSED_ROLES)))
    connection.execute(text(sql))

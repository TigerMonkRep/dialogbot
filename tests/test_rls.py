"""Row Level Security: every table of the application schema has it, and the Data API roles have no rights.

The test database has no Supabase roles, so the policy for `dialogbot_app` and the revokes for `anon`/`authenticated`
are exercised in the second test by creating temporary stand-in roles."""
from __future__ import annotations

import uuid

from sqlalchemy import text

from app.core.rls import APP_ROLE, POLICY, secure_schema


def _schema(db) -> str:
    return db.execute(text("select current_schema()")).scalar()


def test_every_table_has_row_level_security(db):
    off = db.execute(text("""select c.relname from pg_class c join pg_namespace n on n.oid = c.relnamespace
                             where n.nspname = current_schema() and c.relkind in ('r','p') and not c.relrowsecurity
                             order by 1""")).scalars().all()
    assert off == [], f"tables without RLS (alembic/env.py should have secured them): {off}"


def test_a_table_created_later_is_secured_by_the_same_step(db):
    db.execute(text("create table rls_probe (id int primary key)"))
    try:
        secure_schema(db.connection(), _schema(db))
        assert db.execute(text("select relrowsecurity from pg_class where relname = 'rls_probe'")).scalar() is True
    finally:
        db.execute(text("drop table rls_probe"))
        db.commit()


def test_policy_for_the_app_role_and_no_rights_for_the_data_api_roles(db):
    suffix = uuid.uuid4().hex[:6]
    import app.core.rls as rls

    names = {"app": f"app_{suffix}", "anon": f"anon_{suffix}", "auth": f"auth_{suffix}"}
    old = (rls.APP_ROLE, rls.EXPOSED_ROLES)
    conn = db.connection()
    conn.execute(text("create table rls_probe2 (id int primary key)"))
    for r in names.values():
        conn.execute(text(f'create role "{r}"'))
    conn.execute(text(f'grant all on rls_probe2 to "{names["anon"]}", "{names["auth"]}", "{names["app"]}"'))
    rls.APP_ROLE, rls.EXPOSED_ROLES = names["app"], (names["anon"], names["auth"])
    try:
        rls.secure_schema(conn, _schema(db))
        rls.secure_schema(conn, _schema(db))                                      # idempotent
        pol = conn.execute(text("select roles::text from pg_policies where tablename = 'rls_probe2' and policyname = :p"),
                           {"p": POLICY}).scalars().all()
        assert len(pol) == 1 and names["app"] in pol[0]
        for who in ("anon", "auth"):
            assert conn.execute(text("select has_table_privilege(:r, 'rls_probe2', 'select')"),
                                {"r": names[who]}).scalar() is False
        assert conn.execute(text("select has_table_privilege(:r, 'rls_probe2', 'select')"),
                            {"r": names["app"]}).scalar() is True                 # the app keeps its grant, plus the policy
    finally:
        rls.APP_ROLE, rls.EXPOSED_ROLES = old
        db.rollback()
    assert APP_ROLE == "dialogbot_app"

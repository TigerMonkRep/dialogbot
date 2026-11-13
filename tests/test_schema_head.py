"""Deploy safety: one Alembic head in the code, and the database the tests migrated sits on exactly that head.
The same comparison runs against production after every deploy (.github/workflows/deploy-check.yml)."""
from __future__ import annotations

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

from app.migrations_head import expected_head, schema_status


def test_the_code_has_exactly_one_alembic_head():
    cfg = Config(str(Path(__file__).resolve().parent.parent / "alembic.ini"))
    assert len(ScriptDirectory.from_config(cfg).get_heads()) == 1


def test_database_head_equals_code_head_after_migrating(db):
    st = schema_status(db)
    assert st == {"ok": True, "database": expected_head(), "code": expected_head()}


def test_a_mismatch_is_reported_and_pauses_the_worker_schedules(db, monkeypatch):
    from sqlalchemy import text

    from app.worker import runner

    db.execute(text("update alembic_version set version_num = 'deadbeef0000'"))
    db.commit()
    try:
        st = schema_status(db)
        assert st["ok"] is False and st["database"] == "deadbeef0000"
        called = []
        monkeypatch.setattr(runner, "run_outbox_once", lambda *a, **k: called.append(1), raising=False)
        assert runner.schema_ready() is False
    finally:
        db.execute(text("update alembic_version set version_num = :v"), {"v": expected_head()})
        db.commit()


def test_deploy_check_script_finds_the_same_single_head_as_alembic():
    """scripts/check_live_schema.py parses the revision files without Alembic (no install in the job). Merge revisions
    carry a tuple down_revision; the script missed them and reported five heads, so the scheduled Deploy check was red
    on main 8df2c99 although Alembic itself has one head."""
    import importlib.util

    root = Path(__file__).resolve().parent.parent
    spec = importlib.util.spec_from_file_location("check_live_schema", root / "scripts" / "check_live_schema.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    heads = ScriptDirectory.from_config(Config(str(root / "alembic.ini"))).get_heads()
    assert [mod.code_head()] == heads

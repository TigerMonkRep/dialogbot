from functools import lru_cache
from pathlib import Path


@lru_cache
def expected_head() -> str | None:
    """Read the head revision from alembic scripts (no DB access)."""
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    cfg = Config(str(Path(__file__).resolve().parent.parent / "alembic.ini"))
    return ScriptDirectory.from_config(cfg).get_current_head()


def schema_status(db) -> dict:
    """Database version vs. the version this code expects. `ok` only when they are equal.

    The API checks this in /health/ready; the worker checks it before every scheduled pass and pauses its jobs
    (with a clear log line) while they differ – which is the case for a minute or two in every rolling deploy, when the
    migration has run for the new release but an old worker is still up, or the other way round."""
    from sqlalchemy import text

    expected = expected_head()
    try:
        found = db.execute(text("select version_num from alembic_version")).scalar()
    except Exception:  # noqa: BLE001 - no version table, no connection: report as a mismatch, not a crash
        db.rollback()
        found = None
    return {"ok": found is not None and found == expected, "database": found, "code": expected}

from functools import lru_cache
from pathlib import Path


@lru_cache
def expected_head() -> str | None:
    """Read the head revision from alembic scripts (no DB access)."""
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    cfg = Config(str(Path(__file__).resolve().parent.parent / "alembic.ini"))
    return ScriptDirectory.from_config(cfg).get_current_head()

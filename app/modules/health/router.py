from fastapi import APIRouter, Depends, Response
from sqlalchemy import text
from sqlalchemy.orm import Session as OrmSession

from app.db import get_db

router = APIRouter(tags=["health"])


@router.get("/health/live")
def live():
    return {"status": "ok"}


@router.get("/health/ready")
def ready(response: Response, db: OrmSession = Depends(get_db)):
    """Real readiness: database reachable and migrations at head."""
    try:
        db.execute(text("select 1"))
        head = db.execute(text("select version_num from alembic_version")).scalar()
    except Exception as exc:  # noqa: BLE001
        response.status_code = 503
        return {"status": "unavailable", "database": "error", "detail": type(exc).__name__}
    from app.migrations_head import expected_head

    ok = head == expected_head()
    if not ok:
        response.status_code = 503
    return {"status": "ok" if ok else "migrations_pending", "database": "ok", "migration": head,
            "expected_migration": expected_head()}

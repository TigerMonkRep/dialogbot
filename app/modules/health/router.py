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
    out = {"status": "ok" if ok else "migrations_pending", "database": "ok", "migration": head,
           "expected_migration": expected_head()}
    warnings = _warnings(db) if ok else []
    if warnings:  # a warning never changes the status code: the service is up, something around it needs a human
        out["warnings"] = warnings
    return out


_WARNINGS_TTL_SECONDS = 60.0
_warnings_cache: tuple[float, list[dict]] | None = None


def _warnings(db: OrmSession) -> list[dict]:
    """Things that do not make the API unready but need attention. Cached for a minute (Render polls this often).
    `email_sender_rejected`: the mail key may not send from EMAIL_FROM's domain, so no mail leaves."""
    import time

    global _warnings_cache
    now = time.monotonic()
    if _warnings_cache and now - _warnings_cache[0] < _WARNINGS_TTL_SECONDS:
        return _warnings_cache[1]
    found: list[dict] = []
    try:
        from app.modules.integrations.email import sender_problem

        p = sender_problem(db)
        if p:
            found.append({"code": "email_sender_rejected", "domain": p["domain"], "failed": p["count"],
                          "since": p["since"].isoformat(),
                          "detail": f"E-mailnøglen må ikke sende fra {p['domain']}. Ret nøgle eller domæne i Resend."})
    except Exception:  # noqa: BLE001 – a warning must never take readiness down
        db.rollback()
    _warnings_cache = (now, found)
    return found

"""Dev-only endpoints. Mounted only when ENABLE_DEV_TOOLS=true and APP_ENV != prod.

They exist so the simulated e-mail flow (verification, reset, invitation) can be
walked end-to-end without a real mail provider. Access still requires a
logged-in user, and the mailbox only returns mail addressed to that user's own
address (so one developer cannot read another's tokens).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from app.core.auth import Principal, get_current_principal
from app.db import get_db
from app.models import EmailDelivery, OutboxEvent

router = APIRouter(prefix="/dev", tags=["dev (simulated)"])


@router.get("/mailbox")
def mailbox(principal: Principal = Depends(get_current_principal), db: OrmSession = Depends(get_db)):
    rows = db.scalars(select(EmailDelivery).where(EmailDelivery.to_email.ilike(principal.user.email))
                      .order_by(EmailDelivery.created_at.desc()).limit(50))
    return {"adapter": "simulated", "warning": "Simuleret postkasse. Intet er sendt.",
            "items": [{"id": str(r.id), "to": r.to_email, "subject": r.subject, "body_text": r.body_text,
                       "status": r.status, "created_at": r.created_at.isoformat()} for r in rows]}


@router.get("/outbox")
def outbox(principal: Principal = Depends(get_current_principal), db: OrmSession = Depends(get_db)):
    rows = db.scalars(select(OutboxEvent).order_by(OutboxEvent.created_at.desc()).limit(100))
    return {"items": [{"id": str(r.id), "event_type": r.event_type, "status": r.status, "attempts": r.attempts,
                       "next_attempt_at": r.next_attempt_at.isoformat(), "last_error": r.last_error,
                       "created_at": r.created_at.isoformat(),
                       "processed_at": r.processed_at.isoformat() if r.processed_at else None} for r in rows]}


@router.post("/operator/self")
def make_me_operator(principal: Principal = Depends(get_current_principal), db: OrmSession = Depends(get_db)):
    """Dev/test only (this router is not mounted in staging/prod): grant the current user the operator role so
    end-to-end tests can walk the voice publication flow. Production uses scripts/grant_operator.py."""
    principal.user.is_platform_operator = True
    db.commit()
    return {"is_platform_operator": True, "warning": "Kun udviklingsmiljø."}


@router.get("/telephony/verification-code")
def telephony_code(workspace_id: str, principal: Principal = Depends(get_current_principal),
                   db: OrmSession = Depends(get_db)):
    """Dev/test only, fake provider only: the code the simulated verification call read aloud, so the flow can be
    walked without a phone. The caller must be a member of the workspace."""
    import re
    import uuid

    from app.config import get_settings
    from app.core.errors import Forbidden, NotFound
    from app.models import Membership
    from app.modules.telephony.providers import WORLD

    if get_settings().telephony_provider != "fake":
        raise NotFound("Kun med simuleret telefoni")
    if db.scalar(select(Membership.id).where(Membership.user_id == principal.user.id,
                                             Membership.workspace_id == uuid.UUID(workspace_id))) is None:
        raise Forbidden("Ikke medlem af arbejdsrummet")
    for call in reversed(WORLD.calls):
        if (call.get("metadata") or {}).get("workspace_id") == workspace_id:
            digits = re.findall(r"\d", call["assistant"]["firstMessage"])[:6]
            return {"code": "".join(digits), "warning": "Simuleret kontrolopkald. Intet opkald er foretaget."}
    raise NotFound("Intet kontrolopkald")

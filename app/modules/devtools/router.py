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

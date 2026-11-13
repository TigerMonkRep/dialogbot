from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session as OrmSession

from app.config import get_settings
from app.core.body import raw_body
from app.core.errors import ValidationFailed
from app.db import get_db
from app.modules.webhooks import resend

router = APIRouter(prefix="/webhooks", tags=["webhooks"])
# Plain `def` endpoints (threadpool): the handlers do synchronous DB work; the raw body comes from `raw_body`.


@router.post("/resend")
def resend_webhook(request: Request, db: OrmSession = Depends(get_db), body: bytes = Depends(raw_body)):
    """Resend delivery events. Public, but every request must carry a valid Svix signature."""
    secret = get_settings().resend_webhook_secret
    if not secret:
        raise resend.WebhookNotConfigured("Resend-webhook er ikke konfigureret (RESEND_WEBHOOK_SECRET mangler)")
    h = request.headers
    msg_id = h.get("svix-id")
    resend.verify_signature(secret, msg_id, h.get("svix-timestamp"), h.get("svix-signature"), body)
    try:
        payload = json.loads(body)
    except ValueError as e:
        raise ValidationFailed("Ugyldig JSON") from e
    if not isinstance(payload, dict):
        raise ValidationFailed("Ugyldig hændelse")
    result = resend.process_event(db, msg_id, payload)
    if not result.get("duplicate"):
        from app.modules.outreach import replies

        # replies, bounces and complaints on cold e-mails; the answer names it only when something was done
        if (did := replies.on_resend_event(db, payload)) != "ignored":
            result["outreach"] = did
    db.commit()
    return {"received": True, **result}


@router.post("/stripe")
def stripe_webhook(request: Request, db: OrmSession = Depends(get_db), body: bytes = Depends(raw_body)):
    """Stripe events (card saved, invoice finalized/paid/failed). Every request must be signed."""
    from app.modules.billing import stripe

    secret = get_settings().stripe_webhook_secret
    if not secret:
        raise stripe.PaymentNotConfigured("Stripe-webhook er ikke konfigureret (STRIPE_WEBHOOK_SECRET mangler)")
    stripe.verify_signature(secret, request.headers.get("stripe-signature"), body)
    try:
        event = json.loads(body)
    except ValueError as e:
        raise ValidationFailed("Ugyldig JSON") from e
    if not isinstance(event, dict):
        raise ValidationFailed("Ugyldig hændelse")
    from sqlalchemy import select
    from sqlalchemy.exc import IntegrityError

    from app.models import WebhookEvent

    event_id = str(event.get("id") or "")[:200]
    if event_id and db.scalar(select(WebhookEvent.id).where(WebhookEvent.provider == "stripe",
                                                            WebhookEvent.event_id == event_id)) is not None:
        return {"received": True, "duplicate": True, "outcome": "duplicate"}  # a resent event changes nothing
    outcome = stripe.process_event(db, event)
    if event_id:
        # Recorded in the same transaction as its effect (e.g. a top-up of the Opkaldssaldo), so the effect happens once.
        obj = (event.get("data") or {}).get("object") or {}
        db.add(WebhookEvent(provider="stripe", event_id=event_id, event_type=str(event.get("type") or "")[:64] or "unknown",
                            payload={"type": event.get("type"), "object_id": obj.get("id"), "object": obj.get("object")},
                            outcome=outcome if outcome in ("applied", "ignored", "unmatched") else "ignored"))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return {"received": True, "duplicate": True, "outcome": "duplicate"}
    return {"received": True, "outcome": outcome}

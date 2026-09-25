"""Resend delivery webhooks (Milestone B).

Resend signs webhooks with Svix: headers `svix-id`, `svix-timestamp` and `svix-signature`
("v1,<base64 hmac> v1,<...>"), HMAC-SHA256 over "{id}.{timestamp}.{raw body}" with the
base64 part of the endpoint secret ("whsec_<base64>"). Timestamps outside a 5-minute
window are rejected (replay protection).

Processing is idempotent on the Svix message id: a redelivered event is acknowledged
without touching our records again. The provider status on an email delivery only moves
forward (a late "delivery_delayed" never overwrites "delivered").
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import time
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as OrmSession

from app.core.errors import ApiError, Unauthenticated
from app.models import EmailDelivery, WebhookEvent

TOLERANCE_SECONDS = 5 * 60
PROVIDER = "resend"

# Delivery events we apply, ranked; a lower rank never replaces a higher one.
STATUS_RANK: dict[str, int] = {
    "email.sent": 1,
    "email.delivery_delayed": 2,
    "email.delivered": 3,
    "email.failed": 4,
    "email.bounced": 5,
    "email.complained": 6,
}


class WebhookNotConfigured(ApiError):
    status_code = 503
    code = "webhook_not_configured"


def _secret_bytes(secret: str) -> bytes:
    raw = secret.split("_", 1)[1] if secret.startswith("whsec_") else secret
    return base64.b64decode(raw)


def verify_signature(secret: str, msg_id: str | None, timestamp: str | None, signature: str | None,
                     body: bytes, *, now: float | None = None) -> None:
    """Raise Unauthenticated unless the Svix signature and timestamp are valid."""
    if not (msg_id and timestamp and signature):
        raise Unauthenticated("Manglende signaturheadere", code="invalid_signature")
    try:
        ts = int(timestamp)
    except ValueError as e:
        raise Unauthenticated("Ugyldigt tidsstempel", code="invalid_signature") from e
    if abs((now if now is not None else time.time()) - ts) > TOLERANCE_SECONDS:
        raise Unauthenticated("Tidsstemplet er uden for det tilladte vindue", code="invalid_signature")
    signed = f"{msg_id}.{timestamp}.".encode() + body
    expected = base64.b64encode(hmac.new(_secret_bytes(secret), signed, hashlib.sha256).digest()).decode()
    for part in signature.split():
        version, _, sig = part.partition(",")
        if version == "v1" and hmac.compare_digest(sig, expected):
            return
    raise Unauthenticated("Signaturen matcher ikke", code="invalid_signature")


def sign(secret: str, msg_id: str, timestamp: str, body: bytes) -> str:
    """Produce a Svix v1 signature header value (used by tests and local tooling)."""
    signed = f"{msg_id}.{timestamp}.".encode() + body
    return "v1," + base64.b64encode(hmac.new(_secret_bytes(secret), signed, hashlib.sha256).digest()).decode()


def process_event(db: OrmSession, msg_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Store the event once and apply it to the matching email delivery."""
    if db.scalar(select(WebhookEvent.id).where(WebhookEvent.provider == PROVIDER, WebhookEvent.event_id == msg_id)):
        return {"duplicate": True}

    event_type = str(payload.get("type", ""))
    data = payload.get("data") or {}
    email_id = data.get("email_id") if isinstance(data, dict) else None
    outcome = "ignored"
    if event_type in STATUS_RANK:
        rec = db.scalar(select(EmailDelivery).where(EmailDelivery.provider_message_id == email_id)) if email_id else None
        if rec is None:
            outcome = "unmatched"
        else:
            outcome = "applied"
            current = STATUS_RANK.get(f"email.{rec.provider_status}", 0) if rec.provider_status else 0
            if STATUS_RANK[event_type] > current:
                rec.provider_status = event_type.removeprefix("email.")
                created = payload.get("created_at")
                try:
                    rec.provider_status_at = datetime.fromisoformat(str(created).replace("Z", "+00:00")) if created else datetime.now(UTC)
                except ValueError:
                    rec.provider_status_at = datetime.now(UTC)

    db.add(WebhookEvent(provider=PROVIDER, event_id=msg_id, event_type=event_type[:64] or "unknown",
                        payload=payload, outcome=outcome))
    try:
        db.flush()
    except IntegrityError:
        # A concurrent delivery of the same event won the race; treat as duplicate.
        db.rollback()
        return {"duplicate": True}
    return {"duplicate": False, "outcome": outcome}

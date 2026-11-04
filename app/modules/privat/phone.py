"""Verify the user's own mobile number with a 6-digit SMS code (10 minutes, 5 attempts, only an HMAC is stored).

Sent through connectors/sms.py on Dialogbot's main Twilio account with the sender "Dialogbot"; simulated (no real SMS)
when CONNECTORS_PROVIDER=fake or in dev/test without telephony. A verified number is what a call needs (needs_phone),
and it is only ever given to a business when the user ticks share_phone.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from app.config import get_settings
from app.core.errors import ApiError, Conflict, ValidationFailed
from app.models import PrivateProfile
from app.modules.privat import rules

CODE_TTL = timedelta(minutes=10)
MAX_ATTEMPTS = 5
RESEND_AFTER = timedelta(seconds=30)
SENDER = "Dialogbot"


def _hash(ws_id, phone: str, code: str) -> str:
    key = (get_settings().secret_key or "").encode()
    return hmac.new(key, f"{ws_id}:{phone}:{code}".encode(), hashlib.sha256).hexdigest()


def _simulated() -> bool:
    from app.modules.telephony.providers import providers

    s = get_settings()
    return s.connectors_provider == "fake" or (s.app_env in ("dev", "test") and providers() is None)


def start(db: OrmSession, ctx, raw_phone: str) -> None:
    from app.modules.campaigns.service import normalize_phone
    from app.modules.integrations.connectors import sms

    phone = normalize_phone(raw_phone or "")
    if phone is None:
        raise ValidationFailed("Skriv dit mobilnummer med 8 cifre", field_errors=[{"field": "phone"}])
    p = db.scalar(select(PrivateProfile).where(PrivateProfile.workspace_id == ctx.ws_id).with_for_update())
    now = rules.now()
    if p.phone_code_sent_at and now - p.phone_code_sent_at < RESEND_AFTER:
        raise Conflict("Vent et øjeblik, før du beder om en ny kode", code="too_soon")
    code = f"{secrets.randbelow(1_000_000):06d}"
    p.phone_pending_e164, p.phone_code_hash = phone, _hash(ctx.ws_id, phone, code)
    p.phone_code_attempts, p.phone_code_expires_at, p.phone_code_sent_at = 0, now + CODE_TTL, now
    try:
        sms.send(db, ctx.workspace, sender=SENDER, to=phone,
                 body=f"Din kode til Dialogbot er {code}. Den gælder i 10 minutter.", simulated=_simulated())
    except ApiError as e:
        raise ApiError("SMS kunne ikke sendes lige nu. Prøv igen om lidt.", code="sms_failed", status_code=502) from e
    except Exception as e:  # noqa: BLE001 - e.g. ActionError from the adapter
        raise ApiError("SMS kunne ikke sendes lige nu. Prøv igen om lidt.", code="sms_failed", status_code=502) from e


def verify(db: OrmSession, ctx, code: str) -> None:
    p = db.scalar(select(PrivateProfile).where(PrivateProfile.workspace_id == ctx.ws_id).with_for_update())
    now = rules.now()
    if not p.phone_code_hash or not p.phone_code_expires_at or p.phone_code_expires_at <= now:
        raise Conflict("Koden er udløbet. Bed om en ny.", code="code_expired")
    if p.phone_code_attempts >= MAX_ATTEMPTS:
        raise Conflict("For mange forsøg. Bed om en ny kode.", code="too_many_attempts")
    p.phone_code_attempts += 1
    if not hmac.compare_digest(p.phone_code_hash, _hash(ctx.ws_id, p.phone_pending_e164, (code or "").strip())):
        db.commit()  # the attempt counts even though the request fails
        raise ValidationFailed("Koden passer ikke", field_errors=[{"field": "code"}],
                               extra={"attempts_left": MAX_ATTEMPTS - p.phone_code_attempts})
    p.phone_e164, p.phone_verified_at = p.phone_pending_e164, now
    p.phone_pending_e164 = p.phone_code_hash = p.phone_code_expires_at = None
    p.phone_code_attempts = 0

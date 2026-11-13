"""SMS code before Peter rings: the public «Ring mig op nu» door (F-AUD26-02-P06, Fürster 12/11: «A, SMS-kode først»).

Why: the consent box is ticked by whoever types the number, so without proof one anonymous client could make Peter
ring other people – at any hour, since Dialogbot's own demo calls ring at once, day and night. Now:

1. POST /demo-call/code {phone, consent, …} → a 6-digit code by SMS to the number (10 minutes, 5 attempts; only an
   HMAC is stored). Nothing is sent to a number on the do-not-call list (same answer, so opt-outs stay secret).
2. POST /demo-call/verify {verification_id, code} → a one-time call token bound to that number (10 minutes).
3. POST /demo-call {phone, verification_token, …} → the token is used up and Peter rings at once.

Limits (on top of the existing one call per number per 24 hours and the global hourly cap): resend after 30 s; per
number SMS_PER_NUMBER_HOUR/DAY codes from any public door (shared with the /start quiz); per client IP
SMS_PER_IP_HOUR/DAY codes and CALLS_PER_IP_HOUR calls; SMS_GLOBAL_HOUR codes for all. The IP is
lookup_limits.client_ip (the BFF-signed address with CLIENT_IP_SECRET), stored only as a keyed hash.

The code text is GSM-7 in every language (one SMS segment) and tells a person who did not ask to ignore it. Sent
through the existing Twilio adapter (connectors/sms.py) on Dialogbot's main account; simulated with
CONNECTORS_PROVIDER=fake or in dev/test without telephony, like Privat and the quiz.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session as OrmSession

from app.config import get_settings
from app.core.errors import ApiError, Conflict, ValidationFailed
from app.models import DemoCallVerification, PrivateLookup

CODE_TTL = timedelta(minutes=10)
TOKEN_TTL = timedelta(minutes=10)
MAX_ATTEMPTS = 5
RESEND_AFTER = timedelta(seconds=30)
SMS_PER_NUMBER_HOUR, SMS_PER_NUMBER_DAY = 4, 8
SMS_PER_IP_HOUR, SMS_PER_IP_DAY = 5, 15
SMS_GLOBAL_HOUR = 200
CALLS_PER_IP_HOUR = 3
SENDER = "Dialogbot"
LANGUAGES = ("da", "en", "de", "es", "fr", "it", "no", "sv")

# GSM-7 only (tests/test_sales_demo_calls_sms_code.py checks every text): no ó/á/È, so one segment of ≤ 160 characters.
SMS_TEXTS = {
    "da": "Din kode til Dialogbot er {code}. Den gælder i 10 minutter. Har du ikke bedt om et opkald fra os, kan du se "
          "bort fra beskeden.",
    "en": "Your Dialogbot code is {code}. It is valid for 10 minutes. If you did not ask us to call you, please ignore "
          "this message.",
    "de": "Ihr Code für Dialogbot ist {code}. Er gilt 10 Minuten. Wenn Sie keinen Anruf angefordert haben, ignorieren "
          "Sie diese Nachricht.",
    "es": "Su codigo de Dialogbot es {code}. Vale durante 10 minutos. Si no ha pedido una llamada, ignore este mensaje.",
    "fr": "Votre code Dialogbot est {code}. Il est valable 10 minutes. Si vous n'avez pas demandé d'appel, ignorez ce "
          "message.",
    "it": "Il Suo codice Dialogbot è {code}. Vale per 10 minuti. Se non ha chiesto una chiamata, ignori questo messaggio.",
    "no": "Koden din til Dialogbot er {code}. Den gjelder i 10 minutter. Har du ikke bedt om en samtale fra oss, kan du "
          "se bort fra meldingen.",
    "sv": "Din kod till Dialogbot är {code}. Den gäller i 10 minuter. Har du inte bett om ett samtal från oss kan du "
          "bortse från meddelandet.",
}


class SmsRateLimited(ApiError):
    status_code = 429
    code = "sms_rate_limited"


def _now() -> datetime:
    from app.modules.sales import service

    return service._now()  # one clock for the whole door (tests move it)


def _key() -> bytes:
    return (get_settings().secret_key or "").encode()


def _code_hash(vid: uuid.UUID, phone: str, code: str) -> str:
    return hmac.new(_key(), f"demo-call-code:{vid}:{phone}:{code}".encode(), hashlib.sha256).hexdigest()


def _token_hash(token: str) -> str:
    return hmac.new(_key(), f"demo-call-token:{token}".encode(), hashlib.sha256).hexdigest()


def ip_hash(ip: str) -> str:
    return hmac.new(_key(), f"demo-call-ip:{ip}".encode(), hashlib.sha256).hexdigest()


def sms_text(code: str, lang: str | None) -> str:
    return SMS_TEXTS.get(lang or "da", SMS_TEXTS["da"]).format(code=code)


# --------------------------------------------------------------------------- per-number SMS budget (all public doors)

def _number_key(phone: str) -> str:
    return hmac.new(_key(), f"public-sms:phone:{phone}".encode(), hashlib.sha256).hexdigest()


def number_sms_budget(db: OrmSession, phone: str, now: datetime | None = None) -> None:
    """Spend one code SMS to `phone` from a public door (this one or the /start quiz), or raise 429: rotating drafts,
    browsers or addresses never buys more than SMS_PER_NUMBER_HOUR/DAY codes to one person. Rows live in
    private_lookups under a keyed hash (pruned after two days)."""
    now = now or _now()
    key = _number_key(phone)

    def n(since):
        return int(db.scalar(select(func.count()).select_from(PrivateLookup).where(
            PrivateLookup.ip_hash == key, PrivateLookup.created_at >= since)) or 0)

    if n(now - timedelta(hours=1)) >= SMS_PER_NUMBER_HOUR or n(now - timedelta(days=1)) >= SMS_PER_NUMBER_DAY:
        raise SmsRateLimited("Der er sendt for mange koder til dette nummer. Prøv igen senere.",
                             code="sms_rate_limited")
    db.add(PrivateLookup(ip_hash=key, outcome="hit", created_at=now))
    db.flush()


# --------------------------------------------------------------------------- 1. send the code

def _count(db: OrmSession, *where) -> int:
    return int(db.scalar(select(func.count()).select_from(DemoCallVerification).where(*where)) or 0)


def start(db: OrmSession, *, phone: str, ip: str, language: str | None) -> dict:
    """Validate, apply the limits and send the code. Returns what the page shows («Vi har sendt en kode til …»)."""
    from app.modules.integrations.connectors import sms
    from app.modules.privat import phone as privat_phone
    from app.modules.privat import rules
    from app.modules.sales import service

    now = _now()
    phone = service.danish_number(phone)
    if service.problem(db) is not None:
        raise service.DemoUnavailable("Demo-opkald er ikke åbnet endnu. Skriv dig på ventelisten, så hører du fra os.")
    ws = service.sales_workspace(db)
    service.check_not_called_today(db, phone, now)
    service._global_cap(db, ws, now)
    iph = ip_hash(ip)
    last = db.scalar(select(func.max(DemoCallVerification.sent_at)).where(DemoCallVerification.phone == phone))
    if last is not None and now - last < RESEND_AFTER:
        raise Conflict("Vent et øjeblik, før du beder om en ny kode", code="too_soon",
                       extra={"retry_after": max(1, int((RESEND_AFTER - (now - last)).total_seconds()))})
    hour, day = now - timedelta(hours=1), now - timedelta(days=1)
    if (_count(db, DemoCallVerification.ip_hash == iph, DemoCallVerification.sent_at >= hour) >= SMS_PER_IP_HOUR
            or _count(db, DemoCallVerification.ip_hash == iph, DemoCallVerification.sent_at >= day) >= SMS_PER_IP_DAY):
        raise SmsRateLimited("Der er sendt mange koder fra din forbindelse. Vent lidt, og prøv igen.")
    if _count(db, DemoCallVerification.sent_at >= hour) >= SMS_GLOBAL_HOUR:
        import structlog

        structlog.get_logger("dialogbot.sales").warning("sales.demo_sms_global_ceiling", limit=SMS_GLOBAL_HOUR)
        raise SmsRateLimited("Der er mange i kø lige nu. Prøv igen om lidt, eller ring selv til vores demonummer.")
    lang = language if language in LANGUAGES else "da"
    v = DemoCallVerification(id=uuid.uuid4(), phone=phone, attempts=0, language=lang, ip_hash=iph, sent_at=now,
                             expires_at=now + CODE_TTL)
    code = f"{secrets.randbelow(1_000_000):06d}"
    out = {"status": "code_sent", "verification_id": str(v.id), "phone_display": rules.phone_display(phone),
           "resend_after": int(RESEND_AFTER.total_seconds()), "expires_in": int(CODE_TTL.total_seconds())}
    # Spent for do-not-call numbers too, so the 429 comes at the same code either way (F-VER1112-01-P06).
    number_sms_budget(db, phone, now)
    if service._blocked(db, ws, phone):
        # Do-not-call: no SMS either, but the same answer (the row counts towards the limits; no code can match).
        v.code_hash = _code_hash(v.id, phone, secrets.token_hex(16))
        db.add(v)
        db.flush()
        return out
    v.code_hash = _code_hash(v.id, phone, code)
    db.add(v)
    db.flush()
    try:
        sms.send(db, ws, sender=SENDER, to=phone, body=sms_text(code, lang), simulated=privat_phone._simulated())
    except Exception as e:  # noqa: BLE001 - ApiError, or ActionError from the adapter
        raise ApiError("SMS kunne ikke sendes lige nu. Prøv igen om lidt.", code="sms_failed", status_code=502) from e
    return out


# --------------------------------------------------------------------------- 2. check the code

def verify(db: OrmSession, *, verification_id: str, code: str) -> dict:
    """The code → a one-time call token bound to the number. A wrong code counts (committed by the caller)."""
    try:
        vid = uuid.UUID(verification_id)
    except ValueError:
        raise Conflict("Koden er udløbet. Bed om en ny.", code="code_expired") from None
    v = db.scalar(select(DemoCallVerification).where(DemoCallVerification.id == vid).with_for_update())
    now = _now()
    if v is None or v.verified_at is not None or v.expires_at <= now:
        raise Conflict("Koden er udløbet. Bed om en ny.", code="code_expired")
    if v.attempts >= MAX_ATTEMPTS:
        raise Conflict("For mange forsøg. Bed om en ny kode.", code="too_many_attempts")
    v.attempts += 1
    if not hmac.compare_digest(v.code_hash, _code_hash(v.id, v.phone, (code or "").strip())):
        left = MAX_ATTEMPTS - v.attempts
        raise ValidationFailed("Koden passer ikke", code="code_invalid", field_errors=[{"field": "code"}],
                               extra={"attempts_left": left})
    token = secrets.token_urlsafe(32)
    v.verified_at, v.token_hash, v.token_expires_at = now, _token_hash(token), now + TOKEN_TTL
    return {"status": "verified", "verification_token": token}


# --------------------------------------------------------------------------- 3. use the token for the call

def consume(db: OrmSession, *, token: str | None, phone: str, ip: str) -> DemoCallVerification:
    """Use up a verified token for `phone` (normalised), or raise. Also the per-IP call limit. The row is locked, so
    two requests with one token give one call."""
    from app.modules.sales import service

    if not token:
        raise ValidationFailed("Bekræft dit nummer med koden fra SMS'en først", code="verification_required",
                               field_errors=[{"field": "verification_token", "message": "Påkrævet"}])
    phone = service.danish_number(phone)
    now = _now()
    v = db.scalar(select(DemoCallVerification).where(DemoCallVerification.token_hash == _token_hash(token))
                  .with_for_update())
    if (v is None or v.consumed_at is not None or v.phone != phone or v.token_expires_at is None
            or v.token_expires_at <= now):
        raise Conflict("Koden er brugt eller udløbet. Bed om en ny kode.", code="verification_invalid")
    iph = ip_hash(ip)
    if _count(db, DemoCallVerification.call_ip_hash == iph,
              DemoCallVerification.consumed_at >= now - timedelta(hours=1)) >= CALLS_PER_IP_HOUR:
        raise service.DemoRateLimited("Der er bestilt mange opkald fra din forbindelse. Prøv igen senere, eller ring "
                                      "selv til vores demonummer.")
    v.consumed_at, v.call_ip_hash = now, iph
    db.flush()
    return v


def purge(db: OrmSession) -> int:
    """Rows older than two days (the per-day limits need one): the number is personal data."""
    from sqlalchemy import delete

    r = db.execute(delete(DemoCallVerification).where(DemoCallVerification.created_at < _now() - timedelta(days=2)))
    return r.rowcount or 0

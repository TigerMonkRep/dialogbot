"""What a business's own customer can do without a login (W04, W09, W13; DB-016).

W04 – number verification in the chat's «Bliv kontaktet»: a phone number is only stored on the lead after the visitor
typed the 6-digit code the business sent to it. Same rules as the demo-call code (F-AUD26-02-P06, app/modules/sales/
verification.py): 10 minutes, 5 attempts, resend after 30 s, only HMACs stored; the per-number budget is shared with
every other public door (`number_sms_budget`), plus per-IP and per-workspace ceilings. The SMS is the business's own
text (sms_templates.code, the business as sender – no phone number needed: Denmark allows alphanumeric senders).

W09 / W13 – secure customer links. A `callback` link (after «Bliv kontaktet») lets the customer cancel the call back and
say «ring ikke til mig i kampagner» (the workspace's do-not-call list); a `booking` link (after a booking in the chat)
shows the appointment and lets the customer move or cancel it until the business's lead time before the start. Moving
or cancelling a booking that carries a phone number first needs a code sent to that number («verification where
needed»; a booking with only an e-mail is managed with the link alone). A token only opens its own purpose and object,
expires, and is replaced by the next link for the same object. Customer views never contain internal notes, tasks or
staff names.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session as OrmSession

from app.config import get_settings
from app.core.errors import ApiError, Conflict, NotFound, ValidationFailed
from app.models import Booking, Conversation, CustomerLink, CustomerVerification, DoNotCall, Lead, Task, Workspace

CODE_TTL = timedelta(minutes=10)
SESSION_TTL = timedelta(minutes=30)
MAX_ATTEMPTS = 5
RESEND_AFTER = timedelta(seconds=30)
SMS_PER_IP_HOUR, SMS_PER_IP_DAY = 5, 15
SMS_PER_WORKSPACE_HOUR = 60  # one business's SMS bill cannot be run up by rotating numbers and addresses
CALLBACK_LINK_TTL = timedelta(days=30)
PURPOSES = ("webchat_phone", "booking_manage")


def _now() -> datetime:
    return datetime.now(UTC)


def _key() -> bytes:
    return (get_settings().secret_key or "").encode()


def _h(kind: str, value: str) -> str:
    # The purpose is part of every hash, so a token or code of one kind never matches another (DB-016).
    return hmac.new(_key(), f"customer-{kind}:{value}".encode(), hashlib.sha256).hexdigest()


def ip_hash(ip: str) -> str:
    return _h("ip", ip)


def normalize(raw: str | None) -> str:
    """The number as E.164 (8 digits = Danish), or 422 `phone_invalid`. No premium-rate numbers."""
    from app.modules.campaigns.service import normalize_phone
    from app.modules.sales.service import PREMIUM

    n = normalize_phone(raw or "")
    if n is None or PREMIUM.match(n):
        raise ValidationFailed("Tjek telefonnummeret", code="phone_invalid", field_errors=[{"field": "phone"}])
    return n


def masked(e164: str | None) -> str | None:
    """+4520304050 → "20 •• •• 50": enough for the customer to recognise their number, not enough to learn it."""
    if not e164:
        return None
    d = e164[3:] if e164.startswith("+45") and len(e164) == 11 else e164.lstrip("+")
    return f"{d[:2]} •• •• {d[-2:]}" if len(d) >= 6 else "••"


# --------------------------------------------------------------------------- SMS code (W04, W13)

def _count(db: OrmSession, *where) -> int:
    return int(db.scalar(select(func.count()).select_from(CustomerVerification).where(*where)) or 0)


def _sender(db: OrmSession, ws: Workspace) -> str:
    """The sender the business set on its SMS connection, else its name (≤ 11 letters) – never a phone number of ours."""
    from app.modules.integrations import credentials
    from app.modules.integrations.connectors import sms

    conn = credentials.connection(db, ws.id, sms.SPEC.key)
    configured = str((conn.config or {}).get("sender") or "") if conn is not None else ""
    return configured if sms.SENDER_RE.match(configured) else sms.default_sender(ws)


def send_code(db: OrmSession, ws: Workspace, *, purpose: str, phone: str, ip: str,
              conversation: Conversation | None = None, link: CustomerLink | None = None) -> dict:
    """Validate, apply the limits and send the code. `phone` is already E.164."""
    from app.modules.integrations import sms_templates
    from app.modules.integrations.connectors import sms
    from app.modules.privat import phone as privat_phone
    from app.modules.sales.verification import SmsRateLimited, number_sms_budget

    assert purpose in PURPOSES
    now = _now()
    scope = (CustomerVerification.conversation_id == conversation.id if conversation is not None
             else CustomerVerification.link_id == link.id)  # type: ignore[union-attr]
    last = db.scalar(select(func.max(CustomerVerification.sent_at)).where(
        CustomerVerification.purpose == purpose, scope, CustomerVerification.phone == phone))
    if last is not None and now - last < RESEND_AFTER:
        raise Conflict("Vent et øjeblik, før du beder om en ny kode", code="too_soon",
                       extra={"retry_after": max(1, int((RESEND_AFTER - (now - last)).total_seconds()))})
    iph = ip_hash(ip)
    hour, day = now - timedelta(hours=1), now - timedelta(days=1)
    if (_count(db, CustomerVerification.ip_hash == iph, CustomerVerification.sent_at >= hour) >= SMS_PER_IP_HOUR
            or _count(db, CustomerVerification.ip_hash == iph, CustomerVerification.sent_at >= day) >= SMS_PER_IP_DAY):
        raise SmsRateLimited("Der er sendt mange koder fra din forbindelse. Vent lidt, og prøv igen.")
    if _count(db, CustomerVerification.workspace_id == ws.id, CustomerVerification.sent_at >= hour) >= SMS_PER_WORKSPACE_HOUR:
        raise SmsRateLimited("Der er sendt mange koder lige nu. Prøv igen om lidt, eller skriv din e-mail i stedet.")
    number_sms_budget(db, phone, now)  # shared with the demo call and the /start quiz
    v = CustomerVerification(id=uuid.uuid4(), workspace_id=ws.id, purpose=purpose,
                             conversation_id=conversation.id if conversation is not None else None,
                             link_id=link.id if link is not None else None, phone=phone, attempts=0, ip_hash=iph,
                             sent_at=now, expires_at=now + CODE_TTL)
    code = f"{secrets.randbelow(1_000_000):06d}"
    v.code_hash = _h(f"code:{purpose}", f"{v.id}:{phone}:{code}")
    db.add(v)
    db.flush()
    lang = sms.caller_language(db, ws)
    try:
        sms.send(db, ws, sender=_sender(db, ws), to=phone, body=sms_templates.code(ws.name, code, lang),
                 simulated=privat_phone._simulated())
    except Exception as e:  # noqa: BLE001 - ApiError, or ActionError from the adapter
        raise ApiError("SMS kunne ikke sendes lige nu. Prøv igen om lidt, eller skriv din e-mail i stedet.",
                       code="sms_failed", status_code=502) from e
    return {"status": "code_sent", "verification_id": str(v.id), "phone_display": masked(phone),
            "resend_after": int(RESEND_AFTER.total_seconds()), "expires_in": int(CODE_TTL.total_seconds())}


def check_code(db: OrmSession, *, purpose: str, verification_id: str, code: str,
               conversation: Conversation | None = None, link: CustomerLink | None = None) -> CustomerVerification:
    """The code → the row marked verified. A wrong code counts (the caller commits before re-raising). A code of
    another purpose, conversation or link is treated as unknown (409 `code_expired`)."""
    try:
        vid = uuid.UUID(verification_id)
    except ValueError:
        raise Conflict("Koden er udløbet. Bed om en ny.", code="code_expired") from None
    v = db.scalar(select(CustomerVerification).where(CustomerVerification.id == vid).with_for_update())
    now = _now()
    wrong_scope = v is not None and (
        v.purpose != purpose
        or (conversation is not None and v.conversation_id != conversation.id)
        or (link is not None and v.link_id != link.id))
    if v is None or wrong_scope or v.verified_at is not None or v.expires_at <= now:
        raise Conflict("Koden er udløbet. Bed om en ny.", code="code_expired")
    if v.attempts >= MAX_ATTEMPTS:
        raise Conflict("For mange forsøg. Bed om en ny kode.", code="too_many_attempts")
    v.attempts += 1
    if not hmac.compare_digest(v.code_hash, _h(f"code:{purpose}", f"{v.id}:{v.phone}:{(code or '').strip()}")):
        left = MAX_ATTEMPTS - v.attempts
        raise ValidationFailed("Koden passer ikke", code="code_invalid", field_errors=[{"field": "code"}],
                               extra={"attempts_left": left})
    v.verified_at = now
    return v


def verified_phone(db: OrmSession, conv: Conversation, phone: str) -> datetime | None:
    """When the visitor proved `phone` (E.164) in this conversation, or None."""
    return db.scalar(select(func.max(CustomerVerification.verified_at)).where(
        CustomerVerification.purpose == "webchat_phone", CustomerVerification.conversation_id == conv.id,
        CustomerVerification.phone == phone, CustomerVerification.verified_at.is_not(None)))


def open_session(db: OrmSession, v: CustomerVerification) -> str:
    """After a `booking_manage` code: a session for this link only, 30 minutes."""
    token = secrets.token_urlsafe(32)
    v.session_hash, v.session_expires_at = _h("session", token), _now() + SESSION_TTL
    return token


def session_valid(db: OrmSession, link: CustomerLink, session: str | None) -> bool:
    if not session:
        return False
    v = db.scalar(select(CustomerVerification).where(CustomerVerification.session_hash == _h("session", session)))
    return bool(v and v.link_id == link.id and v.purpose == "booking_manage" and v.session_expires_at
                and v.session_expires_at > _now())


# --------------------------------------------------------------------------- links (W09, W13)

def link_url(purpose: str, token: str) -> str:
    base = get_settings().frontend_base_url.rstrip("/")
    return f"{base}/kunde/{token}" if purpose == "callback" else f"{base}/booking/manage/{token}"


def issue_link(db: OrmSession, *, purpose: str, ws_id: uuid.UUID, lead: Lead | None = None,
               booking: Booking | None = None) -> str:
    """A new link for the object; earlier links for the same object stop working. Returns the URL (token inside)."""
    now = _now()
    if purpose == "callback":
        assert lead is not None
        same = CustomerLink.lead_id == lead.id
        expires = now + CALLBACK_LINK_TTL
    else:
        assert booking is not None
        same = CustomerLink.booking_id == booking.id
        expires = booking.ends_at
    for old in db.scalars(select(CustomerLink).where(CustomerLink.purpose == purpose, same,
                                                     CustomerLink.revoked_at.is_(None))):
        old.revoked_at = now
    token = secrets.token_urlsafe(32)
    db.add(CustomerLink(workspace_id=ws_id, purpose=purpose, token_hash=_h(f"link:{purpose}", token),
                        lead_id=lead.id if lead else None, booking_id=booking.id if booking else None,
                        expires_at=expires))
    db.flush()
    return link_url(purpose, token)


class LinkExpired(ApiError):
    status_code = 410
    code = "link_expired"


def resolve(db: OrmSession, purpose: str, token: str, *, lock: bool = False) -> CustomerLink:
    """The link for `token` and `purpose`: 404 `link_invalid` for unknown, replaced or other-purpose tokens, 410
    `link_expired` after its time."""
    q = select(CustomerLink).where(CustomerLink.token_hash == _h(f"link:{purpose}", token or ""))
    link = db.scalar(q.with_for_update() if lock else q) if token and len(token) <= 100 else None
    if link is None or link.purpose != purpose or link.revoked_at is not None:
        raise NotFound("Linket virker ikke. Brug det nyeste link, du har fået.", code="link_invalid")
    if link.expires_at <= _now():
        raise LinkExpired("Linket er udløbet.")
    return link


def _business(db: OrmSession, ws_id: uuid.UUID) -> str:
    ws = db.get(Workspace, ws_id)
    return ws.name if ws else ""


# --------------------------------------------------------------------------- W09 call back + preferences

def callback_view(db: OrmSession, link: CustomerLink) -> dict:
    """What the customer sees: the business, their first name, the call back and their preference. No notes."""
    from app.modules.reports.service import tz_of

    lead = db.get(Lead, link.lead_id)
    if lead is None:
        raise NotFound("Linket virker ikke.", code="link_invalid")
    phone = _lead_phone(lead)
    tz = tz_of(db, lead.workspace_id)
    status = "cancelled" if lead.callback_cancelled_at else (
        "done" if lead.pipeline_status in ("contacted", "won", "lost") else "requested")
    return {"business": _business(db, lead.workspace_id), "first_name": (lead.contact_name or "").strip().split(" ")[0],
            "status": status, "phone_display": masked(phone), "phone_verified": lead.phone_verified_at is not None,
            "window": {"from": lead.callback_from.isoformat(), "to": lead.callback_to.isoformat()}
            if lead.callback_from and lead.callback_to else None,
            "timezone": tz, "calls_opt_out": _opted_out(db, lead.workspace_id, phone),
            "can_opt_out": phone is not None, "expires_at": link.expires_at.isoformat()}


def _lead_phone(lead: Lead) -> str | None:
    try:
        return normalize(lead.contact_phone) if lead.contact_phone else None
    except ValidationFailed:
        return None


def _opted_out(db: OrmSession, ws_id: uuid.UUID, phone: str | None) -> bool:
    return bool(phone) and db.scalar(select(DoNotCall.id).where(DoNotCall.workspace_id == ws_id,
                                                               DoNotCall.phone == phone)) is not None


def cancel_callback(db: OrmSession, link: CustomerLink) -> Lead:
    """The customer no longer wants the call: the lead says so and its open tasks are closed (staff see «Aflyst af
    kunden» on the lead). Idempotent."""
    from app.core.audit import record_audit

    lead = db.scalar(select(Lead).where(Lead.id == link.lead_id).with_for_update())
    if lead is None:
        raise NotFound("Linket virker ikke.", code="link_invalid")
    if lead.callback_cancelled_at is None:
        now = _now()
        lead.callback_cancelled_at = now
        lead.version += 1
        for t in db.scalars(select(Task).where(Task.lead_id == lead.id, Task.status == "open")):
            t.status, t.completed_at, t.completed_by = "done", now, None
        record_audit(db, workspace_id=lead.workspace_id, actor_user_id=None, action="leads.callback_cancelled_by_customer",
                     object_type="lead", object_id=lead.id)
    return lead


def set_calls_opt_out(db: OrmSession, link: CustomerLink, opt_out: bool) -> None:
    """«Ring ikke til mig i kampagner»: the number on the workspace's do-not-call list (source `customer`). Turning it
    off again only removes what the customer added themselves, never a number staff put on the list."""
    from app.core.audit import record_audit

    lead = db.get(Lead, link.lead_id)
    phone = _lead_phone(lead) if lead else None
    if lead is None or phone is None:
        raise ValidationFailed("Der er ikke noget telefonnummer på din henvendelse", code="no_phone")
    row = db.scalar(select(DoNotCall).where(DoNotCall.workspace_id == lead.workspace_id, DoNotCall.phone == phone))
    if opt_out and row is None:
        db.add(DoNotCall(workspace_id=lead.workspace_id, phone=phone, source="customer",
                         reason="Kunden har selv frabedt sig opkald (link fra webchat)"))
    elif not opt_out and row is not None and row.source == "customer":
        db.delete(row)
    else:
        return
    record_audit(db, workspace_id=lead.workspace_id, actor_user_id=None,
                 action="do_not_call.customer_opt_out" if opt_out else "do_not_call.customer_opt_in",
                 object_type="lead", object_id=lead.id)
    db.flush()


# --------------------------------------------------------------------------- W13 booking

def _policy(db: OrmSession, b: Booking) -> dict:
    """Changes are allowed until the business's lead time (the same «tidligst om X timer» new bookings follow)."""
    from app.modules.bookings import service as bookings

    s = bookings.settings(db, b.workspace_id)
    cutoff = b.starts_at - timedelta(hours=s.lead_time_hours)
    reason = None
    if b.status != "confirmed":
        reason = "cancelled"
    elif b.starts_at <= _now():
        reason = "past"
    elif _now() >= cutoff:
        reason = "too_late"
    return {"can_change": reason is None, "reason": reason, "cutoff_hours": s.lead_time_hours,
            "cutoff_at": cutoff.isoformat()}


def booking_view(db: OrmSession, link: CustomerLink, session: str | None) -> dict:
    from app.modules.bookings import service as bookings
    from app.modules.reports.service import tz_of

    b = db.get(Booking, link.booking_id)
    if b is None:
        raise NotFound("Linket virker ikke.", code="link_invalid")
    tz = tz_of(db, b.workspace_id)
    phone = _booking_phone(b)
    from app.models import BookingType

    bt = db.get(BookingType, b.type_id) if b.type_id else None
    return {"business": _business(db, b.workspace_id), "what": bt.name if bt else b.title.split(":")[0],
            "first_name": (b.contact_name or "").strip().split(" ")[0], "starts_at": b.starts_at.isoformat(),
            "ends_at": b.ends_at.isoformat(), "label": bookings.label(b.starts_at, tz), "timezone": tz,
            "status": b.status, "confirmation": "pending" if b.confirmation == "pending" else "confirmed",
            "policy": _policy(db, b),
            "verification": {"required": phone is not None, "phone_display": masked(phone),
                             "verified": phone is None or session_valid(db, link, session)},
            "expires_at": link.expires_at.isoformat()}


def _booking_phone(b: Booking) -> str | None:
    try:
        return normalize(b.contact_phone) if b.contact_phone else None
    except ValidationFailed:
        return None


def booking_phone(db: OrmSession, link: CustomerLink) -> str:
    b = db.get(Booking, link.booking_id)
    phone = _booking_phone(b) if b else None
    if phone is None:
        raise Conflict("Aftalen har intet telefonnummer – der skal ingen kode til", code="verification_not_needed")
    return phone


def locked_booking(db: OrmSession, link: CustomerLink, session: str | None) -> Booking:
    """The booking, locked, after the verification and policy checks for a change."""
    b = db.scalar(select(Booking).where(Booking.id == link.booking_id).with_for_update())
    if b is None:
        raise NotFound("Linket virker ikke.", code="link_invalid")
    if _booking_phone(b) is not None and not session_valid(db, link, session):
        raise ApiError("Bekræft dit telefonnummer med koden fra SMS'en først", code="verification_required",
                       status_code=403)
    p = _policy(db, b)
    if not p["can_change"]:
        if p["reason"] == "cancelled":
            raise Conflict("Aftalen er aflyst", code="booking_cancelled")
        raise Conflict(f"Aftalen kan ikke ændres her mindre end {p['cutoff_hours']} timer før. Kontakt virksomheden.",
                       code="change_too_late", extra={"cutoff_hours": p["cutoff_hours"]})
    return b


def note_customer_change(db: OrmSession, b: Booking, what: str, tz: str) -> None:
    """Staff learn about a customer's own change in Opgaver (the booking's lead) and in the audit trail."""
    from app.core.audit import record_audit
    from app.modules.bookings import service as bookings
    from app.modules.leads import service as leads

    lead = db.get(Lead, b.lead_id) if b.lead_id else None
    who = b.contact_name.strip() or "Kunden"
    title = (f"{who} aflyste {b.title.split(':')[0].lower()} {bookings.label(b.starts_at, tz)} (via link)" if what == "cancel"
             else f"{who} flyttede {b.title.split(':')[0].lower()} til {bookings.label(b.starts_at, tz)} (via link)")
    if what == "move" and lead is not None:
        # the booking's own task follows the new time
        for t in db.scalars(select(Task).where(Task.lead_id == lead.id, Task.status == "open",
                                               Task.title.startswith(b.title.split(":")[0]))):
            t.due_at = b.starts_at
            t.title = f"{b.title.split(':')[0]} med {who} – {bookings.label(b.starts_at, tz)}"[:200]
    if what == "cancel" and lead is not None:
        for t in db.scalars(select(Task).where(Task.lead_id == lead.id, Task.status == "open",
                                               Task.title.startswith(b.title.split(":")[0]))):
            t.status, t.completed_at, t.completed_by = "done", _now(), None
    leads.create_task(db, b.workspace_id, title=title[:200], created_by=None, lead=lead, due_at=_now())
    record_audit(db, workspace_id=b.workspace_id, actor_user_id=None,
                 action="bookings.cancelled_by_customer" if what == "cancel" else "bookings.moved_by_customer",
                 object_type="booking", object_id=b.id, after={"starts_at": b.starts_at.isoformat(), "status": b.status})


# --------------------------------------------------------------------------- housekeeping

def purge(db: OrmSession) -> int:
    """Code rows after two days (the number is personal data) and links that expired more than 30 days ago."""
    now = _now()
    n = db.execute(delete(CustomerVerification).where(CustomerVerification.created_at < now - timedelta(days=2))).rowcount or 0
    n += db.execute(delete(CustomerLink).where(CustomerLink.expires_at < now - timedelta(days=30))).rowcount or 0
    return n

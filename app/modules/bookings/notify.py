"""E07 – booking messages sent automatically, through the outbox and the worker.

The decision (Fürster, 2026-11-13):
- To the customer, on request received, confirmed, moved and cancelled: e-mail when the booking has an address; SMS
  only when the business has turned SMS messages on (`BookingSettings.sms_messages_enabled`, off by default – each SMS
  counts in the business's usage). A reminder 24 hours before (a worker job), never for a cancelled booking or a time
  the booking has been moved away from, and only at a sensible local time: within the business's approved opening
  hours, or 08–21 when it has none.
- To the business (owners and admins): «kræver opmærksomhed» and «levering fejlede», by e-mail.
- Unsubscribed or blocked customers get nothing (the e-mail carries an unsubscribe link; a number on the business's
  spærreliste gets no SMS). Language: the business's caller language for the customer (a booking carries no language
  of its own), the member's interface language for the business.

Two stages, both outbox events, so the decision is taken after the booking's transaction committed (when the calendar
write's outcome is known) and each channel is retried on its own:

    booking.event    one per booking event (dedupe bkevt:<booking>:<event>:<time>) – decides which messages go out
    booking.message  one per message, channel and recipient (dedupe bkmsg:<booking>:<variant>:<time>:<channel>:<to>)

A `booking_messages` row per `booking.message` is the log, the idempotency record (unique outbox event) and what the
audit trail points to. «Confirmed» uses the same message key whichever event leads to it (booked straight away, a
staff member's confirmation, the calendar written after a failure), so the customer is told once per time.
"""
from __future__ import annotations

import hashlib
import hmac
import uuid
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

import structlog
from sqlalchemy import or_, select
from sqlalchemy.orm import Session as OrmSession

from app.config import get_settings
from app.core.audit import record_audit
from app.core.outbox import enqueue
from app.models import (
    ActionRun,
    Booking,
    BookingMessage,
    BookingType,
    CustomerMessageSuppression,
    DoNotCall,
    Membership,
    OutboxEvent,
    User,
    Workspace,
)

log = structlog.get_logger("dialogbot.bookings.notify")

EVENTS = ("created", "confirmed", "moved", "cancelled", "reminder")
REMINDER_BEFORE = timedelta(hours=24)
REMINDER_MIN_LEAD = timedelta(hours=2)  # later than this before the start, a reminder is no longer sent
FALLBACK_WINDOW = (time(8, 0), time(21, 0))  # local sending window when the business has no opening hours
FINAL = ("sent", "simulated", "skipped", "failed")
OWNER_ROLES = ("owner", "admin")


def _now() -> datetime:
    return datetime.now(UTC)


def _iso(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat()


# --------------------------------------------------------------------------- stage 1: an event happened

def queue(db: OrmSession, b: Booking, event: str, *, previous_start: datetime | None = None) -> OutboxEvent:
    """Called in the booking's own transaction (bookings.service). Idempotent per booking, event and time."""
    assert event in EVENTS
    at = "" if event == "cancelled" else f":{_iso(b.starts_at)}"
    payload = {"booking_id": str(b.id), "event": event, "starts_at": _iso(b.starts_at)}
    if previous_start is not None:
        payload["previous_start"] = _iso(previous_start)
    return enqueue(db, event_type="booking.event", dedupe_key=f"bkevt:{b.id}:{event}{at}", workspace_id=b.workspace_id,
                   payload=payload)


def _booking(db: OrmSession, ev: OutboxEvent) -> Booking | None:
    """The event's booking, only inside the event's own workspace (tenant isolation)."""
    try:
        bid = uuid.UUID(str(ev.payload.get("booking_id")))
    except ValueError:
        return None
    return db.scalar(select(Booking).where(Booking.id == bid, Booking.workspace_id == ev.workspace_id))


def _awaiting(b: Booking) -> bool:
    """The time is not final for the customer: a staff member must confirm it, or the calendar write failed."""
    return b.confirmation == "pending" or b.calendar_sync == "failed"


def handle_event(db: OrmSession, ev: OutboxEvent) -> None:
    """Decide the messages for one booking event and queue them (`booking.message`)."""
    from app.modules.bookings import service as bookings

    b = _booking(db, ev)
    if b is None:
        return
    p = ev.payload
    event = p["event"]
    starts = datetime.fromisoformat(p["starts_at"])
    if event != "cancelled" and (b.status != "confirmed" or b.starts_at != starts):
        return  # cancelled or moved since: that later event carries its own messages
    if event == "created":
        variant = "request_receipt" if _awaiting(b) else "confirmed"
    elif event == "confirmed":
        variant = None if b.confirmation == "pending" else "confirmed"
    elif event == "moved":
        variant = "request_receipt" if _awaiting(b) else "rescheduled"
    elif event == "reminder":
        variant = None if b.confirmation == "pending" else "reminder"
    else:
        variant = "cancelled"
    if variant is not None:
        s = bookings.settings(db, b.workspace_id)
        channels = (["email"] if b.contact_email else []) + (["sms"] if s.sms_messages_enabled and b.contact_phone else [])
        for ch in channels:
            _queue_message(db, b, variant=variant, channel=ch, audience="customer", to="customer", starts_at=b.starts_at,
                           extra={"previous_start": p.get("previous_start")})
    if event in ("created", "confirmed", "moved"):
        reason = ("needs_confirmation" if b.confirmation == "pending"
                  else "calendar_failed" if b.calendar_sync == "failed" else None)
        if reason:
            for user_id in _owner_ids(db, b.workspace_id):
                _queue_message(db, b, variant="owner_attention", channel="email", audience="owner", to=str(user_id),
                               starts_at=b.starts_at, extra={"reason": reason}, key_extra=reason)


def _owner_ids(db: OrmSession, ws_id: uuid.UUID) -> list[uuid.UUID]:
    return list(db.scalars(select(Membership.user_id).where(Membership.workspace_id == ws_id,
                                                            Membership.role.in_(OWNER_ROLES))
                           .order_by(Membership.user_id)))


def _queue_message(db: OrmSession, b: Booking, *, variant: str, channel: str, audience: str, to: str,
                   starts_at: datetime, extra: dict | None = None, key_extra: str = "") -> OutboxEvent:
    when = "" if variant == "cancelled" else f":{_iso(starts_at)}"
    if variant == "delivery_failure":
        when = ""
    key = f"bkmsg:{b.id}:{variant}{':' + key_extra if key_extra else ''}{when}:{channel}:{to}"
    payload = {"booking_id": str(b.id), "variant": variant, "channel": channel, "audience": audience, "to": to,
               "starts_at": _iso(starts_at),
               "event_key": f"{variant}{':' + key_extra if key_extra else ''}{when}"[:80],
               **{k: v for k, v in (extra or {}).items() if v is not None}}
    return enqueue(db, event_type="booking.message", dedupe_key=key[:200], workspace_id=b.workspace_id, payload=payload)


# --------------------------------------------------------------------------- stage 2: one message on one channel

class HandlerRetry(Exception):
    """A temporary provider error: the worker tries the event again (with backoff)."""


def handle_message(db: OrmSession, ev: OutboxEvent) -> None:
    p = ev.payload
    row = db.scalar(select(BookingMessage).where(BookingMessage.outbox_event_id == ev.id).with_for_update())
    if row is not None and row.status in FINAL:
        return  # redelivery: the message was dealt with
    b = _booking(db, ev)
    if b is None:
        return
    ws = db.get(Workspace, b.workspace_id)
    recipient, lang = _recipient(db, ws, b, p)
    if row is None:
        row = BookingMessage(workspace_id=b.workspace_id, booking_id=b.id, outbox_event_id=ev.id,
                             event_key=p["event_key"], variant=p["variant"], audience=p["audience"],
                             channel=p["channel"], recipient=(recipient or "–")[:320], lang=lang,
                             starts_at=datetime.fromisoformat(p["starts_at"]), status="sending")
        db.add(row)
        db.flush()
    elif row.status == "sending" and row.channel == "sms":
        # A worker died while the provider was being called: the SMS may have gone. It is never sent a second time.
        _finish(db, row, b, "failed", error="Afsendelsen blev afbrudt – det er uvist, om SMS'en kom frem")
        return
    reason = _skip_reason(db, ws, b, row, recipient)
    if reason is not None:
        _finish(db, row, b, "skipped", skip_reason=reason)
        return
    row.status = "sending"
    db.commit()  # from here an SMS counts as possibly sent (see above)
    try:
        if row.channel == "email":
            ref, simulated = _send_email(db, ev, ws, b, row, p)
            segments = None
        else:
            ref, simulated, segments = _send_sms(db, ws, b, row, p)
    except Exception as exc:  # noqa: BLE001 - ActionError/ApiError from the SMS adapter, RuntimeError from Resend
        message = str(getattr(exc, "message", "") or exc)[:500]
        if getattr(exc, "retryable", True) and ev.attempts < ev.max_attempts:
            row.status, row.error = "retrying", message
            db.commit()
            raise HandlerRetry(message) from exc
        _finish(db, row, b, "failed", error=message)
        return
    row.provider_ref, row.segments = (ref or None), segments
    _finish(db, row, b, "simulated" if simulated else "sent")


def _recipient(db: OrmSession, ws: Workspace, b: Booking, p: dict) -> tuple[str | None, str]:
    from app.modules.integrations.connectors.sms import caller_language
    from app.modules.integrations.email_texts import user_language

    if p["audience"] == "owner":
        u = db.get(User, uuid.UUID(p["to"]))
        member = u is not None and db.scalar(select(Membership.id).where(
            Membership.workspace_id == b.workspace_id, Membership.user_id == u.id, Membership.role.in_(OWNER_ROLES)))
        return (u.email if member else None), user_language(db, p["to"])
    lang = caller_language(db, ws)
    if p["channel"] == "email":
        return ((b.contact_email or "").strip().lower() or None), lang
    from app.core.errors import ValidationFailed
    from app.modules.customer.service import normalize

    try:
        return (normalize(b.contact_phone) if b.contact_phone else None), lang
    except ValidationFailed:
        return None, lang


def _skip_reason(db: OrmSession, ws: Workspace, b: Booking, row: BookingMessage, recipient: str | None) -> str | None:
    if recipient is None:
        return "no_recipient"
    if row.audience == "owner":
        return None
    if b.status != "confirmed" and row.variant != "cancelled":
        return "booking_cancelled"
    if row.variant != "cancelled" and b.starts_at != row.starts_at:
        return "superseded"  # moved since: the message about the new time replaces it
    if row.variant in ("confirmed", "reminder") and b.confirmation == "pending":
        return "awaiting_confirmation"
    if row.variant == "reminder" and _now() >= b.starts_at - REMINDER_MIN_LEAD:
        return "too_late"
    if suppressed(db, b.workspace_id, row.channel, recipient):
        return "unsubscribed"
    if row.channel == "sms":
        from app.modules.bookings import service as bookings

        if not bookings.settings(db, b.workspace_id).sms_messages_enabled:
            return "sms_off"
        if db.scalar(select(DoNotCall.id).where(DoNotCall.workspace_id == b.workspace_id, DoNotCall.phone == recipient)):
            return "blocked"
        if row.variant == "confirmed" and _assistant_sent_sms(db, b, recipient):
            return "assistant_sent"
    return None


def _assistant_sent_sms(db: OrmSession, b: Booking, phone: str) -> bool:
    """The assistant already sent the caller the booking SMS (send_sms_bekraeftelse) after this booking was made."""
    runs = db.scalars(select(ActionRun).where(ActionRun.workspace_id == b.workspace_id, ActionRun.status == "ok",
                                              ActionRun.action == "send_sms_bekraeftelse",
                                              ActionRun.created_at >= b.created_at))
    return any((r.output or {}).get("til") == phone and (r.input or {}).get("skabelon") == "booking" for r in runs)


def suppressed(db: OrmSession, ws_id: uuid.UUID, channel: str, value: str) -> bool:
    return db.scalar(select(CustomerMessageSuppression.id).where(
        CustomerMessageSuppression.workspace_id == ws_id, CustomerMessageSuppression.channel == channel,
        CustomerMessageSuppression.value == value.strip().lower())) is not None


def _context(db: OrmSession, ws: Workspace, b: Booking, row: BookingMessage, p: dict):
    from app.modules.bookings import messages
    from app.modules.reports.service import tz_of

    bt = db.get(BookingType, b.type_id) if b.type_id else None
    ctx = messages.Context(business=ws.name, customer=b.contact_name or "", what=bt.name if bt else b.title.split(":")[0],
                           when=row.starts_at, tz=tz_of(db, ws.id))
    if row.variant == "rescheduled":
        prev = p.get("previous_start")
        ctx.when = datetime.fromisoformat(prev) if prev else row.starts_at
        ctx.new_when = row.starts_at
    ctx.reason = p.get("reason") or "calendar_failed"
    ctx.failed_variant = p.get("failed_variant") or "confirmed"
    ctx.channel = p.get("failed_channel") or "sms"
    ctx.error = p.get("error") or ""
    return ctx


def _send_email(db: OrmSession, ev: OutboxEvent, ws: Workspace, b: Booking, row: BookingMessage,
                p: dict) -> tuple[str | None, bool]:
    from app.models import EmailDelivery
    from app.modules.bookings import messages
    from app.modules.integrations.email import OutgoingEmail, get_email_adapter

    done = db.scalar(select(EmailDelivery).where(EmailDelivery.outbox_event_id == ev.id))
    if done is None:
        ctx = _context(db, ws, b, row, p)
        customer = row.audience == "customer"
        if customer:
            ctx.unsubscribe_url = unsubscribe_url(row)
        mail = messages.render(row.variant, row.lang, ctx)["email"]
        headers = ({"List-Unsubscribe": f"<{ctx.unsubscribe_url}>", "List-Unsubscribe-Post": "List-Unsubscribe=One-Click"}
                   if customer else None)
        done = get_email_adapter().deliver(db, ev.id, OutgoingEmail(
            to_email=row.recipient, subject=mail.subject, body_text=mail.text(), body_html=mail.html(),
            workspace_id=ws.id, from_name=ws.name if customer else None, headers=headers))
    return done.provider_message_id or str(done.id), done.status == "simulated"


def _send_sms(db: OrmSession, ws: Workspace, b: Booking, row: BookingMessage, p: dict) -> tuple[str, bool, int]:
    from app.modules.bookings import messages
    from app.modules.customer.service import _sender
    from app.modules.integrations.connectors import sms
    from app.modules.privat.phone import _simulated

    text = messages.render(row.variant, row.lang, _context(db, ws, b, row, p))["sms"]["text"]
    simulated = _simulated()
    sid = sms.send(db, ws, sender=_sender(db, ws), to=row.recipient, body=text, simulated=simulated)
    return sid, simulated, messages.segments(text)["segments"]


def _finish(db: OrmSession, row: BookingMessage, b: Booking, status: str, *, skip_reason: str | None = None,
            error: str | None = None) -> None:
    row.status, row.skip_reason = status, skip_reason
    if error is not None:
        row.error = error[:500]
    record_audit(db, workspace_id=row.workspace_id, actor_user_id=None, action=f"bookings.message_{status}",
                 object_type="booking", object_id=b.id,
                 after={"message_id": str(row.id), "variant": row.variant, "audience": row.audience,
                        "channel": row.channel, "status": status, "skip_reason": skip_reason})
    if status == "failed" and row.audience == "customer":
        _tell_owner_delivery_failed(db, b, row)


def _tell_owner_delivery_failed(db: OrmSession, b: Booking, row: BookingMessage) -> None:
    for user_id in _owner_ids(db, b.workspace_id):
        _queue_message(db, b, variant="delivery_failure", channel="email", audience="owner", to=str(user_id),
                       starts_at=row.starts_at, key_extra=str(row.id),
                       extra={"failed_variant": row.variant, "failed_channel": row.channel, "error": row.error or ""})


def on_email_problem(db: OrmSession, delivery, status: str) -> None:
    """The mail provider reported a customer's booking e-mail as bounced, failed or complained about (Resend webhook):
    the message is marked failed and the business is told; a complaint also unsubscribes the address."""
    row = db.scalar(select(BookingMessage).where(BookingMessage.outbox_event_id == delivery.outbox_event_id))
    if row is None or row.audience != "customer":
        return
    if status == "complained":
        _suppress(db, row.workspace_id, "email", row.recipient, "complaint")
    if row.status in ("sent", "simulated"):
        b = db.get(Booking, row.booking_id)
        if b is not None:
            _finish(db, row, b, "failed", error={"bounced": "E-mailen kom retur (bounce)",
                                                 "complained": "Modtageren markerede e-mailen som spam",
                                                 "failed": "Mailudbyderen kunne ikke levere e-mailen"}.get(status, status))


# --------------------------------------------------------------------------- reminders (worker schedule)

def _window_open(db: OrmSession, ws_id: uuid.UUID, tz: str, now: datetime, cache: dict) -> bool:
    """Within the business's approved opening hours today, or 08–21 local time when it has none."""
    from app.modules.bookings import service as bookings

    if ws_id not in cache:
        cache[ws_id] = bookings.weekly_hours(db, ws_id)
    hours = cache[ws_id]
    local = now.astimezone(ZoneInfo(tz))
    if not any(hours.values()):
        return FALLBACK_WINDOW[0] <= local.time() < FALLBACK_WINDOW[1]
    return any(o <= local.time() < c for o, c in hours[bookings.DAYS[local.weekday()]])


def run_reminders(db: OrmSession, now: datetime | None = None, limit: int = 500) -> int:
    """Queue the reminder for bookings starting within 24 hours. Idempotent: the outbox dedupe key holds the booking
    and its time, so repeated runs and several workers queue each reminder once; a moved booking gets one for its new
    time. Not for cancelled bookings, bookings awaiting confirmation, bookings made less than 24 hours before their
    start (the customer was just told), less than two hours before the start, or outside the business's hours."""
    from app.modules.reports.service import tz_of

    now = now or _now()
    rows = db.scalars(select(Booking).where(
        Booking.status == "confirmed", or_(Booking.confirmation.is_(None), Booking.confirmation != "pending"),
        Booking.starts_at > now + REMINDER_MIN_LEAD, Booking.starts_at <= now + REMINDER_BEFORE,
        Booking.created_at <= Booking.starts_at - REMINDER_BEFORE,
        or_(Booking.contact_email.is_not(None), Booking.contact_phone.is_not(None)))
        .order_by(Booking.starts_at).limit(limit)).all()
    if not rows:
        return 0
    keys = {f"bkevt:{b.id}:reminder:{_iso(b.starts_at)}": b for b in rows}
    have = set(db.scalars(select(OutboxEvent.dedupe_key).where(OutboxEvent.dedupe_key.in_(list(keys)))))
    tzs: dict = {}
    hours: dict = {}
    n = 0
    for key, b in keys.items():
        if key in have:
            continue
        tz = tzs.setdefault(b.workspace_id, tz_of(db, b.workspace_id))
        if not _window_open(db, b.workspace_id, tz, now, hours):
            continue
        queue(db, b, "reminder")
        n += 1
    db.commit()
    return n


# --------------------------------------------------------------------------- unsubscribe

def _sig(row_id: uuid.UUID) -> str:
    key = (get_settings().secret_key or "").encode()
    return hmac.new(key, f"booking-unsubscribe:{row_id.hex}".encode(), hashlib.sha256).hexdigest()[:32]


def unsubscribe_token(row: BookingMessage) -> str:
    return f"{row.id.hex}.{_sig(row.id)}"


def unsubscribe_url(row: BookingMessage) -> str:
    base = get_settings().public_base_url.rstrip("/")
    return f"{base}/api/v1/public/booking-messages/unsubscribe/{unsubscribe_token(row)}"


def resolve_unsubscribe(db: OrmSession, token: str) -> BookingMessage | None:
    """The customer e-mail the link was in, or None for anything that is not a valid link."""
    rid, _, sig = (token or "").partition(".")
    try:
        row_id = uuid.UUID(hex=rid)
    except ValueError:
        return None
    if not hmac.compare_digest(sig, _sig(row_id)):
        return None
    row = db.get(BookingMessage, row_id)
    return row if row is not None and row.audience == "customer" and row.channel == "email" else None


def _suppress(db: OrmSession, ws_id: uuid.UUID, channel: str, value: str, source: str) -> bool:
    from sqlalchemy.dialects.postgresql import insert

    new_id = db.scalar(insert(CustomerMessageSuppression).values(
        id=uuid.uuid4(), workspace_id=ws_id, channel=channel, value=value.strip().lower(), source=source)
        .on_conflict_do_nothing(constraint="uq_customer_message_suppressions_value")
        .returning(CustomerMessageSuppression.id))
    return new_id is not None


def unsubscribe(db: OrmSession, row: BookingMessage, source: str) -> None:
    """The address gets no more booking e-mails from this business. Idempotent; audited without the address."""
    if _suppress(db, row.workspace_id, "email", row.recipient, source):
        record_audit(db, workspace_id=row.workspace_id, actor_user_id=None, action="bookings.messages_unsubscribed",
                     object_type="booking", object_id=row.booking_id, after={"channel": "email", "source": source})

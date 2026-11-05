"""The Kalender app of Dialogbot Privat: the times the user approved, in the user's own calendar.

An appointment exists only for an agreement the user approved: a call where the business confirmed a time (the user
approved the call and what the assistant may agree to), a browser booking the user said yes to, or a time the user
told the assistant themselves. It reaches the user's calendar three ways, all opt-in:

- a single `.ics` file per appointment («Tilføj til kalender»), which every calendar app opens;
- a secret subscription link (`/privat/calendar/feed/<token>.ics`); only a SHA-256 of the token is stored, the link
  is shown once and a new one replaces it;
- Google Calendar or Outlook, connected with OAuth (the same connectors and OAuth client as the business side). Every
  change is an outbox event `privat.calendar_sync`, so a provider outage never loses or blocks an appointment.

Times are parsed from what was agreed («torsdag kl. 15.30», «12. november kl. 9») against the date it was agreed, in
Europe/Copenhagen. When the time cannot be read with certainty, no appointment is made and the task keeps its text.
"""
from __future__ import annotations

import hashlib
import re
import secrets
import uuid
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from app.config import get_settings
from app.core import outbox
from app.core.errors import NotFound, ValidationFailed
from app.models import PrivateAppointment, PrivateProfile, PrivateTask
from app.modules.privat import addons, rules

ADDON = "kalender"
CALENDAR_CONNECTORS = ("google_calendar", "microsoft_calendar")
PROVIDER_CONNECTOR = {"google": "google_calendar", "microsoft": "microsoft_calendar"}
DEFAULT_MINUTES = 60
MAX_AHEAD = timedelta(days=400)
FEED_PAST = timedelta(days=60)
SYNC_EVENT = "privat.calendar_sync"

MONTHS = {"januar": 1, "jan": 1, "februar": 2, "feb": 2, "marts": 3, "mar": 3, "april": 4, "apr": 4, "maj": 5,
          "juni": 6, "jun": 6, "juli": 7, "jul": 7, "august": 8, "aug": 8, "september": 9, "sep": 9, "sept": 9,
          "oktober": 10, "okt": 10, "november": 11, "nov": 11, "december": 12, "dec": 12}
_MONTH_RX = "|".join(sorted(MONTHS, key=len, reverse=True))
_WEEKDAY_RX = "|".join(rules.WEEKDAYS)


# --------------------------------------------------------------------------- reading an agreed time

def _time_of(text: str) -> tuple[time | None, str]:
    """The clock time in `text` and the text without it. «kl.» first, then HH:MM, then HH.MM."""
    for rx in (r"\bkl\.?\s*([01]?\d|2[0-3])(?:[.:]([0-5]\d))?\b", r"\b([01]?\d|2[0-3]):([0-5]\d)\b"):
        m = re.search(rx, text)
        if m:
            return time(int(m.group(1)), int(m.group(2) or 0)), text[:m.start()] + " " + text[m.end():]
    m = re.search(r"(?<![\d.])([01]?\d|2[0-3])\.([0-5]\d)(?![\d.])", text)
    if m and not re.search(rf"\d\.?\s*(?:{_MONTH_RX})\b", text):
        return time(int(m.group(1)), int(m.group(2))), text[:m.start()] + " " + text[m.end():]
    return None, text


def _next_year_date(day: int, month: int, ref: date) -> date | None:
    for year in (ref.year, ref.year + 1):
        try:
            d = date(year, month, day)
        except ValueError:
            return None
        if d >= ref:
            return d
    return None


def _date_of(text: str, ref: date) -> date | None:
    low = text.lower()
    m = re.search(r"\b(20\d\d)-(\d\d)-(\d\d)\b", low)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    m = re.search(r"\b(\d{1,2})[./-](\d{1,2})(?:[./-](20\d\d|\d\d))?\b", low)
    if m:
        day, month = int(m.group(1)), int(m.group(2))
        if m.group(3):
            year = int(m.group(3)) + (2000 if len(m.group(3)) == 2 else 0)
            try:
                return date(year, month, day)
            except ValueError:
                return None
        return _next_year_date(day, month, ref)
    m = re.search(rf"\b(\d{{1,2}})\.?\s*({_MONTH_RX})\.?(?:\s+(20\d\d))?\b", low)
    if m:
        day, month = int(m.group(1)), MONTHS[m.group(2)]
        if m.group(3):
            try:
                return date(int(m.group(3)), month, day)
            except ValueError:
                return None
        return _next_year_date(day, month, ref)
    if re.search(r"\bi\s+overmorgen\b", low):
        return ref + timedelta(days=2)
    if re.search(r"\bi\s+morgen\b", low):
        return ref + timedelta(days=1)
    if re.search(r"\bi\s+dag\b", low):
        return ref
    m = re.search(rf"\b(næste\s+)?({_WEEKDAY_RX})\b", low)
    if m:
        target = rules.WEEKDAYS.index(m.group(2))
        ahead = (target - ref.weekday()) % 7
        if ahead == 0 and m.group(1):
            ahead = 7
        return ref + timedelta(days=ahead)
    return None


def parse_when(text: str | None, ref: datetime) -> datetime | None:
    """The start time agreed in `text`, read against `ref` (when it was agreed), as an aware UTC datetime. None when
    the text has no clock time or no date, or the result is not plausible (in the past or more than 400 days ahead)."""
    if not text:
        return None
    local_ref = rules.local(ref)
    at, rest = _time_of(text)
    if at is None:
        return None
    day = _date_of(rest, local_ref.date())
    if day is None:
        return None
    start = datetime.combine(day, at, tzinfo=rules.TZ)
    if start.date() == local_ref.date() and start < local_ref and not re.search(r"\bi\s+dag\b", rest.lower()):
        start += timedelta(days=7) if re.search(rf"\b({_WEEKDAY_RX})\b", rest.lower()) else timedelta(0)
    if start < local_ref - timedelta(hours=1) or start > local_ref + MAX_AHEAD:
        return None
    return start.astimezone(UTC)


def from_iso(value: str | None, ref: datetime) -> datetime | None:
    """A local ISO time from a model («2026-11-12T15:30»), checked like parse_when."""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).strip())
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=rules.TZ)
    local_ref = rules.local(ref)
    if dt < local_ref - timedelta(hours=1) or dt > local_ref + MAX_AHEAD:
        return None
    return dt.astimezone(UTC)


# --------------------------------------------------------------------------- appointments

def enabled(db: OrmSession, ws_id: uuid.UUID) -> bool:
    return addons.is_enabled(db, ws_id, ADDON)


def lands_in_calendar(db: OrmSession, ws_id: uuid.UUID) -> bool:
    """Whether a new appointment reaches a calendar of the user's: the app is on and Google/Outlook is connected or
    the subscription link exists. Only then may a message say «lagt i din kalender»."""
    if not enabled(db, ws_id):
        return False
    profile = db.get(PrivateProfile, ws_id)
    if profile is not None and profile.calendar_feed_token_hash:
        return True
    from app.modules.integrations import credentials

    return any((c := credentials.connection(db, ws_id, k)) is not None and c.status == "connected"
               for k in CALENDAR_CONNECTORS)


def _touch(a: PrivateAppointment) -> None:
    a.sequence += 1
    a.updated_at = rules.now()


def _sync_later(db: OrmSession, a: PrivateAppointment) -> None:
    outbox.enqueue(db, event_type=SYNC_EVENT, dedupe_key=f"privat.calsync:{a.id}:{a.sequence}",
                   payload={"appointment_id": str(a.id)}, workspace_id=a.workspace_id)


def record(db: OrmSession, ws_id: uuid.UUID, *, source: str, source_ref: str, title: str, starts_at: datetime,
           minutes: int | None = None, location: str = "", notes: str = "",
           task_id: uuid.UUID | None = None) -> PrivateAppointment:
    """Create (or, for the same errand, move) the appointment. The same `source_ref` never makes two."""
    minutes = minutes if minutes and 5 <= minutes <= 12 * 60 else DEFAULT_MINUTES
    ends_at = starts_at + timedelta(minutes=minutes)
    a = db.scalar(select(PrivateAppointment).where(PrivateAppointment.source_ref == source_ref).with_for_update())
    if a is None:
        a = PrivateAppointment(workspace_id=ws_id, task_id=task_id, source=source, source_ref=source_ref,
                               title=title[:300], location=location[:300], notes=notes[:2000], starts_at=starts_at,
                               ends_at=ends_at, status="confirmed", sequence=0, external={})
        db.add(a)
        db.flush()
    elif (a.starts_at, a.ends_at, a.status) != (starts_at, ends_at, "confirmed"):
        a.starts_at, a.ends_at, a.status = starts_at, ends_at, "confirmed"
        _touch(a)
    else:
        return a
    if enabled(db, ws_id):
        _sync_later(db, a)
    return a


def cancel(db: OrmSession, a: PrivateAppointment) -> PrivateAppointment:
    if a.status != "cancelled":
        a.status = "cancelled"
        _touch(a)
        _sync_later(db, a)
    return a


def own(db: OrmSession, ws_id: uuid.UUID, appointment_id: uuid.UUID) -> PrivateAppointment:
    a = db.get(PrivateAppointment, appointment_id)
    if a is None or a.workspace_id != ws_id:
        raise NotFound("Aftalen findes ikke")
    return a


def for_task(db: OrmSession, task_id: uuid.UUID) -> PrivateAppointment | None:
    return db.scalar(select(PrivateAppointment).where(PrivateAppointment.task_id == task_id,
                                                      PrivateAppointment.status == "confirmed")
                     .order_by(PrivateAppointment.created_at.desc()).limit(1))


def upcoming(db: OrmSession, ws_id: uuid.UUID, *, limit: int = 50) -> list[PrivateAppointment]:
    return list(db.scalars(select(PrivateAppointment).where(
        PrivateAppointment.workspace_id == ws_id, PrivateAppointment.status == "confirmed",
        PrivateAppointment.ends_at >= rules.now()).order_by(PrivateAppointment.starts_at).limit(limit)))


def out(a: PrivateAppointment) -> dict:
    sync = {k: {"synced": bool(v.get("event_id")) and not v.get("error"), "error": v.get("error")}
            for k, v in (a.external or {}).items()}
    return {"id": str(a.id), "task_id": str(a.task_id) if a.task_id else None, "source": a.source, "title": a.title,
            "location": a.location, "notes": a.notes, "starts_at": a.starts_at.isoformat(),
            "ends_at": a.ends_at.isoformat(), "status": a.status, "when_text": rules.when_text(a.starts_at),
            "ics_path": f"/api/v1/privat/appointments/{a.id}.ics", "sync": sync}


# --------------------------------------------------------------------------- where appointments come from

def from_call(db: OrmSession, call, task: PrivateTask, *, starts_iso: str | None, minutes: int | None,
              agreed_at: datetime) -> PrivateAppointment | None:
    """A call where the business confirmed a time. The model's ISO time is used when it is plausible, otherwise the
    confirmed text is read; when neither gives a certain time, there is no appointment."""
    start = from_iso(starts_iso, agreed_at) or parse_when(call.confirmed_text, agreed_at)
    if start is None:
        return None
    return record(db, call.workspace_id, source="call", source_ref=f"call:{call.id}", task_id=task.id,
                  title=_title(call.business_name, call.purpose), starts_at=start, minutes=minutes,
                  location=call.business_address or "", notes=_notes(call.confirmed_text, call.business_price_text))


def from_browser(db: OrmSession, run, task: PrivateTask, *, service: str | None, date_text: str | None,
                 time_text: str | None, business: str, price: str | None, agreed_at: datetime) -> PrivateAppointment | None:
    if not date_text or not time_text:
        return None
    start = parse_when(f"{date_text} kl. {time_text}", agreed_at)
    if start is None:
        return None
    return record(db, task.workspace_id, source="browser", source_ref=f"browser:{run.id}", task_id=task.id,
                  title=_title(business, service), starts_at=start,
                  location=str((run.goal or {}).get("business_address") or ""), notes=_notes(service, price))


def _title(business: str, what: str | None) -> str:
    what = (what or "").strip().rstrip(".")
    if what and len(what) <= 60:
        return f"{what[:1].upper() + what[1:]} – {business}"
    return business


def _notes(*parts: str | None) -> str:
    return "\n".join(p.strip() for p in parts if p and p.strip()) + "\n\nLagt i kalenderen af Dialogbot."


# --------------------------------------------------------------------------- iCalendar (RFC 5545)

def _esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\r\n", "\\n").replace("\n", "\\n")


def _fold(line: str) -> str:
    raw = line.encode("utf-8")
    if len(raw) <= 75:
        return line
    parts, cur = [], b""
    for ch in line:
        b = ch.encode("utf-8")
        if len(cur) + len(b) > (75 if not parts else 74):
            parts.append(cur.decode("utf-8"))
            cur = b""
        cur += b
    parts.append(cur.decode("utf-8"))
    return "\r\n ".join(parts)


def _utc(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")


def _vevent(a: PrivateAppointment, stamp: datetime) -> list[str]:
    lines = ["BEGIN:VEVENT", f"UID:{a.id}@dialogbot.dk", f"DTSTAMP:{_utc(stamp)}", f"SEQUENCE:{a.sequence}",
             f"DTSTART:{_utc(a.starts_at)}", f"DTEND:{_utc(a.ends_at)}", f"SUMMARY:{_esc(a.title)}",
             f"STATUS:{'CANCELLED' if a.status == 'cancelled' else 'CONFIRMED'}", "TRANSP:OPAQUE"]
    if a.location:
        lines.append(f"LOCATION:{_esc(a.location)}")
    if a.notes:
        lines.append(f"DESCRIPTION:{_esc(a.notes)}")
    if a.status == "confirmed":
        lines += ["BEGIN:VALARM", "ACTION:DISPLAY", f"DESCRIPTION:{_esc(a.title)}", "TRIGGER:-PT1H", "END:VALARM"]
    lines.append("END:VEVENT")
    return lines


def to_ics(appointments: list[PrivateAppointment], *, name: str = "Dialogbot", method: str | None = "PUBLISH") -> str:
    stamp = rules.now()
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Dialogbot//Privat//DA", "CALSCALE:GREGORIAN"]
    if method:
        lines.append(f"METHOD:{method}")
    lines += [f"X-WR-CALNAME:{_esc(name)}", "X-WR-TIMEZONE:Europe/Copenhagen", "REFRESH-INTERVAL;VALUE=DURATION:PT1H",
              "X-PUBLISHED-TTL:PT1H"]
    for a in appointments:
        lines += _vevent(a, stamp)
    lines.append("END:VCALENDAR")
    return "\r\n".join(_fold(x) for x in lines) + "\r\n"


# --------------------------------------------------------------------------- the subscription link

def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def feed_url(token: str) -> str:
    return f"{get_settings().public_base_url.rstrip('/')}/api/v1/privat/calendar/feed/{token}.ics"


def new_feed(db: OrmSession, profile: PrivateProfile) -> str:
    """A new secret link; the old one stops working. The token is returned once and never stored."""
    token = secrets.token_urlsafe(32)
    profile.calendar_feed_token_hash = _hash(token)
    profile.calendar_feed_created_at = rules.now()
    db.flush()
    return feed_url(token)


def drop_feed(db: OrmSession, profile: PrivateProfile) -> None:
    profile.calendar_feed_token_hash = None
    profile.calendar_feed_created_at = None
    db.flush()


def feed_for(db: OrmSession, token: str) -> str | None:
    """The feed body for a secret token, or None (unknown token, or the Kalender app is off)."""
    if not token or len(token) > 100:
        return None
    profile = db.scalar(select(PrivateProfile).where(PrivateProfile.calendar_feed_token_hash == _hash(token)))
    if profile is None or not enabled(db, profile.workspace_id):
        return None
    since = rules.now() - FEED_PAST
    rows = list(db.scalars(select(PrivateAppointment).where(
        PrivateAppointment.workspace_id == profile.workspace_id, PrivateAppointment.ends_at >= since)
        .order_by(PrivateAppointment.starts_at).limit(500)))
    return to_ics(rows, name="Dialogbot", method=None)


# --------------------------------------------------------------------------- Google / Outlook

def connection_status(db: OrmSession, ws_id: uuid.UUID) -> dict:
    from app.modules.integrations import connectors, credentials, oauth

    out_ = {}
    for provider, key in PROVIDER_CONNECTOR.items():
        sp = connectors.spec(key)
        row = credentials.connection(db, ws_id, key)
        available = sp.unavailable_reason() is None and (get_settings().connectors_provider == "fake"
                                                         or oauth.provider_for(provider).configured())
        out_[provider] = {"available": available, "connected": row is not None and row.status == "connected",
                          "status": row.status if row is not None else "not_connected",
                          "account_label": row.account_label if row is not None else "",
                          "error": row.error if row is not None else None}
    return out_


def connect_url(db: OrmSession, ctx, provider: str) -> str:
    """Where to send the user to give access. Uses the business connectors' OAuth client and callback; the callback
    sees the personal workspace and sends the user back to the Kalender app."""
    from app.modules.integrations import connectors, oauth

    key = PROVIDER_CONNECTOR.get(provider)
    if key is None:
        raise ValidationFailed("Ukendt kalender", field_errors=[{"field": "provider"}])
    if not connection_status(db, ctx.ws_id)[provider]["available"]:
        raise ValidationFailed("Den kalender kan ikke forbindes endnu", field_errors=[{"field": "provider"}],
                               code="calendar_unavailable")
    connectors.spec(key)
    if get_settings().connectors_provider == "fake":
        from app.modules.integrations.connections_router import oauth_state_row

        state = secrets.token_urlsafe(24)

        class _C:
            workspace = ctx.workspace
            user_id = ctx.user_id

        db.add(oauth_state_row(_C, key, state))
        db.flush()
        return f"{oauth.redirect_uri(key)}?state={state}&code=fake-code"
    return oauth.start(db, workspace_id=ctx.ws_id, connector=key, provider=oauth.provider_for(provider),
                       user_id=ctx.user_id)


def disconnect(db: OrmSession, ws_id: uuid.UUID, provider: str) -> None:
    from app.modules.integrations import credentials, oauth

    key = PROVIDER_CONNECTOR.get(provider)
    if key is None:
        raise ValidationFailed("Ukendt kalender", field_errors=[{"field": "provider"}])
    conn = credentials.connection(db, ws_id, key)
    if conn is None:
        return
    if conn.auth_kind == "oauth" and not conn.simulated:
        tok = (credentials.get_secret(conn) or {}).get("refresh_token") or (credentials.get_secret(conn) or {}).get("access_token")
        if tok:
            try:
                oauth.revoke(oauth.provider_for(provider), tok)
            except Exception:  # noqa: BLE001 – revoking is best effort; the stored secret is deleted either way
                pass
    db.delete(conn)
    db.flush()


def backfill(db: OrmSession, ws_id: uuid.UUID) -> int:
    """After a calendar is connected: queue the upcoming appointments so they appear there too."""
    rows = upcoming(db, ws_id, limit=200)
    for a in rows:
        outbox.enqueue(db, event_type=SYNC_EVENT, dedupe_key=f"privat.calsync:{a.id}:{a.sequence}:backfill:{uuid.uuid4().hex[:8]}",
                       payload={"appointment_id": str(a.id)}, workspace_id=ws_id)
    return len(rows)


def handle_sync(db: OrmSession, ev) -> None:
    """Worker: bring every connected Google/Outlook calendar in line with the appointment. A provider error is noted
    on the appointment (the app shows it); a temporary one is raised so the outbox retries."""
    from app.modules.integrations import connectors, credentials
    from app.modules.integrations.connectors.base import ActionError

    a = db.get(PrivateAppointment, uuid.UUID(str(ev.payload.get("appointment_id"))))
    if a is None or not enabled(db, a.workspace_id):
        return
    ext = dict(a.external or {})
    retry: ActionError | None = None
    for key in CALENDAR_CONNECTORS:
        conn = credentials.connection(db, a.workspace_id, key)
        if conn is None or conn.status != "connected":
            continue
        cur = dict(ext.get(key) or {})
        if cur.get("sequence") == a.sequence and not cur.get("error"):
            continue
        try:
            client = connectors.calendar_client(db, a.workspace_id, key)
            if a.status == "cancelled":
                if cur.get("event_id"):
                    client.delete_event(cur["event_id"])
                cur = {"event_id": None, "sequence": a.sequence, "error": None}
            elif cur.get("event_id"):
                client.update_event(cur["event_id"], start=a.starts_at, end=a.ends_at)
                cur.update(sequence=a.sequence, error=None)
            else:
                eid = client.create_event(title=a.title, start=a.starts_at, end=a.ends_at, description=a.notes,
                                          location=a.location)
                cur = {"event_id": eid, "sequence": a.sequence, "error": None}
            conn.last_ok_at = datetime.now(UTC)
        except ActionError as e:
            cur["error"] = e.message[:200]
            if e.code == "provider_unauthorized":
                credentials.mark_error(conn, e.message)
            elif getattr(e, "retryable", False) and (ev.attempts or 0) + 1 < (ev.max_attempts or 1):
                retry = e  # the outbox tries again later; on the last attempt the error is kept on the appointment
        ext[key] = cur
    a.external = ext
    db.flush()
    if retry is not None:
        raise retry

"""Online booking: free times from approved opening hours, minus bookings and calendar busy time.

- Opening hours come ONLY from approved `opening_hours` knowledge (the same source the assistant uses).
- The owner's own calendar is connected with its secret iCal address: only start/end of busy events
  are read (titles are never stored). Our bookings are published back as a secret iCal feed the
  owner subscribes to – two-way without an OAuth app.
- A booking creates a lead and a task, so it lands in Henvendelser and Opgaver like other contacts.
"""
from __future__ import annotations

import secrets
import uuid
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from app.core.errors import ApiError, Conflict, NotFound, ValidationFailed
from app.models import Booking, BookingSettings, BookingType, Conversation, Workspace
from app.modules.knowledge.service import active_knowledge

DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
WEEKDAY_DA = ("mandag", "tirsdag", "onsdag", "torsdag", "fredag", "lørdag", "søndag")
MONTH_DA = ("januar", "februar", "marts", "april", "maj", "juni", "juli", "august", "september", "oktober",
            "november", "december")
ICS_MAX_BYTES = 2_000_000


def _now() -> datetime:
    return datetime.now(UTC)


def settings(db: OrmSession, ws_id: uuid.UUID, *, lock: bool = False) -> BookingSettings:
    q = select(BookingSettings).where(BookingSettings.workspace_id == ws_id)
    s = db.scalar(q.with_for_update() if lock else q)
    if s is None:
        s = BookingSettings(workspace_id=ws_id, feed_token=secrets.token_urlsafe(32), busy_blocks=[])
        db.add(s)
        db.flush()
    return s


def weekly_hours(db: OrmSession, ws_id: uuid.UUID) -> dict[str, list[tuple[time, time]]]:
    out: dict[str, list[tuple[time, time]]] = {d: [] for d in DAYS}
    for item in active_knowledge(db, ws_id):
        if item["kind"] != "opening_hours":
            continue
        for row in (item["content"] or {}).get("weekly") or []:
            try:
                o, c = time.fromisoformat(row["open"]), time.fromisoformat(row["close"])
            except (KeyError, ValueError, TypeError):
                continue
            for d in row.get("days") or []:
                if d in out and o < c:
                    out[d].append((o, c))
    return out


def label(start: datetime, tz: str) -> str:
    local = start.astimezone(ZoneInfo(tz))
    return f"{WEEKDAY_DA[local.weekday()]} {local.day}. {MONTH_DA[local.month - 1]} kl. {local:%H.%M}"


def _busy(db: OrmSession, s: BookingSettings, ws_id: uuid.UUID, frm: datetime, to: datetime) -> list[tuple[datetime, datetime]]:
    pad = timedelta(minutes=s.buffer_minutes)
    out = [(b.starts_at - pad, b.ends_at + pad) for b in db.scalars(
        select(Booking).where(Booking.workspace_id == ws_id, Booking.status == "confirmed",
                              Booking.ends_at > frm, Booking.starts_at < to))]
    for blk in s.busy_blocks or []:
        try:
            out.append((datetime.fromisoformat(blk[0]), datetime.fromisoformat(blk[1])))
        except (ValueError, TypeError, IndexError):
            continue
    return out


def slots(db: OrmSession, ws: Workspace, bt: BookingType, tz: str, now: datetime | None = None, limit: int = 60) -> list[dict]:
    """Free start times for a booking type, earliest first."""
    s = settings(db, ws.id)
    now = now or _now()
    z = ZoneInfo(tz)
    earliest = now + timedelta(hours=s.lead_time_hours)
    end_all = now + timedelta(days=s.horizon_days)
    hours = weekly_hours(db, ws.id)
    busy = _busy(db, s, ws.id, now, end_all + timedelta(days=1))
    dur = timedelta(minutes=bt.duration_minutes)
    step = timedelta(minutes=max(15, min(bt.duration_minutes, 60)))
    out: list[dict] = []
    day: date = now.astimezone(z).date()
    while datetime.combine(day, time(0), tzinfo=z) < end_all and len(out) < limit:
        for o, c in hours[DAYS[day.weekday()]]:
            t = datetime.combine(day, o, tzinfo=z)
            close = datetime.combine(day, c, tzinfo=z)
            while t + dur <= close and len(out) < limit:
                st, en = t.astimezone(UTC), (t + dur).astimezone(UTC)
                if st >= earliest and en <= end_all and not any(st < b1 and en > b0 for b0, b1 in busy):
                    out.append({"start": st.isoformat(), "end": en.isoformat(), "label": label(st, tz)})
                t += step
        day += timedelta(days=1)
    return out


def active_types(db: OrmSession, ws_id: uuid.UUID) -> list[BookingType]:
    return list(db.scalars(select(BookingType).where(BookingType.workspace_id == ws_id, BookingType.active)
                           .order_by(BookingType.created_at)))


def book(db: OrmSession, ws: Workspace, *, type_id: uuid.UUID, start: str, name: str, phone: str | None,
         email: str | None, note: str, source: str, tz: str, conversation: Conversation | None = None,
         created_by: uuid.UUID | None = None) -> Booking:
    from app.modules.leads import service as leads

    s = settings(db, ws.id, lock=True)  # serialises concurrent bookings for the workspace
    if not s.enabled and source != "manual":
        raise Conflict("Online booking er ikke slået til", code="booking_disabled")
    bt = db.get(BookingType, type_id)
    if bt is None or bt.workspace_id != ws.id or not bt.active:
        raise NotFound("Bookingtypen findes ikke")
    try:
        st = datetime.fromisoformat(start).astimezone(UTC)
    except ValueError as e:
        raise ValidationFailed("Ugyldigt tidspunkt", field_errors=[{"field": "start"}]) from e
    if source != "manual" and st.isoformat() not in {x["start"] for x in slots(db, ws, bt, tz, limit=500)}:
        raise Conflict("Tiden er ikke længere ledig – vælg en anden", code="slot_taken")
    en = st + timedelta(minutes=bt.duration_minutes)
    if source == "manual" and any(st < b1 and en > b0 for b0, b1 in _busy(db, s, ws.id, st - timedelta(days=1), en + timedelta(days=1))):
        raise Conflict("Tiden overlapper en anden aftale", code="slot_taken")
    who = name.strip() or "kunden"
    b = Booking(workspace_id=ws.id, type_id=bt.id, title=f"{bt.name}: {who}", starts_at=st, ends_at=en, source=source,
                contact_name=name.strip(), contact_phone=(phone or "").strip() or None,
                contact_email=(email or "").strip().lower() or None, note=note.strip()[:1000],
                conversation_id=conversation.id if conversation else None, created_by=created_by)
    db.add(b)
    db.flush()
    lead = leads.lead_for_conversation(db, conversation.id) if conversation else None
    if lead is None:
        lead = leads.create_lead(db, ws.id, source=source, created_by=created_by, conversation=conversation,
                                 contact_name=name, contact_email=b.contact_email, contact_phone=b.contact_phone,
                                 need_summary=f"Booket {bt.name.lower()} {label(st, tz)}" + (f". {b.note}" if b.note else ""))
        leads._notify_new_lead(db, lead)
    b.lead_id = lead.id
    leads.create_task(db, ws.id, title=f"{bt.name} med {who} – {label(st, tz)}", created_by=created_by, lead=lead,
                      due_at=st)
    return b


def cancel(db: OrmSession, b: Booking) -> Booking:
    if b.status != "cancelled":
        b.status, b.cancelled_at = "cancelled", _now()
    return b


# --------------------------------------------------------------------------- calendar (iCal)

def sync_busy(db: OrmSession, s: BookingSettings) -> int:
    """Read busy time from the owner's secret iCal address. Stores [start, end] pairs only."""
    import httpx
    import icalendar
    import recurring_ical_events

    from app.modules.knowledge.importer import _allowed

    if not s.busy_ics_url:
        s.busy_blocks, s.busy_error = [], None
        return 0
    url = s.busy_ics_url.strip().replace("webcal://", "https://", 1)
    try:
        if not _allowed(url):
            raise ApiError("Kalenderadressen er ikke tilladt", code="calendar_url")
        with httpx.Client(timeout=15.0, follow_redirects=True) as c:
            r = c.get(url)
        if r.status_code != 200 or len(r.content) > ICS_MAX_BYTES:
            raise ApiError(f"Kalenderen kunne ikke hentes ({r.status_code})", code="calendar_fetch")
        cal = icalendar.Calendar.from_ical(r.content)
        now = _now()
        blocks = []
        for ev in recurring_ical_events.of(cal).between(now - timedelta(days=1), now + timedelta(days=s.horizon_days + 2)):
            if str(ev.get("TRANSP", "OPAQUE")).upper() == "TRANSPARENT" or str(ev.get("STATUS", "")).upper() == "CANCELLED":
                continue
            st, en = ev.get("DTSTART").dt, (ev.get("DTEND") or ev.get("DTSTART")).dt
            if not isinstance(st, datetime):  # all-day event blocks the whole local day(s)
                z = ZoneInfo("Europe/Copenhagen")
                st, en = datetime.combine(st, time(0), tzinfo=z), datetime.combine(en, time(0), tzinfo=z)
            st = st if st.tzinfo else st.replace(tzinfo=UTC)
            en = en if en.tzinfo else en.replace(tzinfo=UTC)
            blocks.append([st.astimezone(UTC).isoformat(), en.astimezone(UTC).isoformat()])
        s.busy_blocks, s.busy_error, s.busy_synced_at = blocks[:2000], None, now
        return len(blocks)
    except ApiError as e:
        s.busy_error, s.busy_synced_at = e.message[:300], _now()
        return 0
    except Exception:  # noqa: BLE001 - malformed calendar data
        s.busy_error, s.busy_synced_at = "Kalenderen kunne ikke læses. Tjek at adressen er kalenderens iCal-adresse.", _now()
        return 0


def feed(db: OrmSession, s: BookingSettings, ws: Workspace) -> bytes:
    import icalendar

    cal = icalendar.Calendar()
    cal.add("prodid", "-//Dialogbot//Bookinger//DA")
    cal.add("version", "2.0")
    cal.add("x-wr-calname", f"Dialogbot – {ws.name}")
    since = _now() - timedelta(days=30)
    for b in db.scalars(select(Booking).where(Booking.workspace_id == ws.id, Booking.ends_at >= since)):
        ev = icalendar.Event()
        ev.add("uid", f"{b.id}@dialogbot")
        ev.add("dtstamp", b.created_at)
        ev.add("dtstart", b.starts_at)
        ev.add("dtend", b.ends_at)
        ev.add("summary", b.title)
        ev.add("description", "\n".join(x for x in (b.contact_phone, b.contact_email, b.note) if x))
        ev.add("status", "CANCELLED" if b.status == "cancelled" else "CONFIRMED")
        cal.add_component(ev)
    return cal.to_ical()


def booking_out(b: Booking, tz: str) -> dict:
    return {"id": str(b.id), "type_id": str(b.type_id) if b.type_id else None, "title": b.title,
            "starts_at": b.starts_at.isoformat(), "ends_at": b.ends_at.isoformat(), "label": label(b.starts_at, tz),
            "status": b.status, "source": b.source, "contact_name": b.contact_name, "contact_phone": b.contact_phone,
            "contact_email": b.contact_email, "note": b.note, "lead_id": str(b.lead_id) if b.lead_id else None,
            "conversation_id": str(b.conversation_id) if b.conversation_id else None}

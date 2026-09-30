"""Calendar connectors: Google Calendar and Microsoft 365 (Outlook) via OAuth, plus the built-in Dialogbot calendar
(approved opening hours + the owner's secret iCal address) that every workspace has.

All three offer the same four actions – ledige_tider, book_tid, flyt_tid, aflys_tid – so the assistant's behaviour
does not change with the customer's calendar. A booking is always a `bookings` row in Dialogbot (it creates the
lead and the task, and it is what the inbox shows); when Google or Microsoft is connected, the booking is mirrored
as an event there and their busy time replaces the iCal feed. If the mirror call fails, the booking stands and the
connection shows the error – the customer in the call is never told a time is booked that is not.

Provider endpoints (read 29/9 2026):
- Google Calendar API v3: POST /freeBusy, POST/PATCH/DELETE /calendars/primary/events
  (developers.google.com/calendar/api/v3/reference).
- Microsoft Graph v1.0: GET /me/calendarView, POST /me/events, PATCH/DELETE /me/events/{id}
  (learn.microsoft.com/graph/api/resources/calendar).
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from app.core.errors import ApiError
from app.models import Booking, BookingSettings, Workspace
from app.modules.integrations.connectors.base import (
    ActionError,
    ActionRefused,
    ActionResult,
    ActionSpec,
    RunContext,
    obj,
)

MAX_SLOTS = 6


class CalendarClient(Protocol):
    simulated: bool

    def info(self) -> dict: ...
    def busy(self, frm: datetime, to: datetime) -> list[tuple[datetime, datetime]]: ...
    def create_event(self, *, title: str, start: datetime, end: datetime, description: str = "") -> str: ...
    def update_event(self, event_id: str, *, start: datetime, end: datetime) -> None: ...
    def delete_event(self, event_id: str) -> None: ...


# --------------------------------------------------------------------------- HTTP clients

def _http(method: str, url: str, token: str, *, headers: dict | None = None, **kw) -> dict:
    import httpx

    try:
        r = httpx.request(method, url, headers={**(headers or {}), "authorization": f"Bearer {token}"}, timeout=15.0, **kw)
    except httpx.TimeoutException as e:
        raise ActionError("Kalenderen svarede ikke i tide", code="provider_timeout", retryable=True) from e
    except httpx.HTTPError as e:
        raise ActionError("Kalenderen kunne ikke nås", code="provider_unavailable", retryable=True) from e
    if r.status_code in (401, 403):
        raise ActionError("Kalenderforbindelsen er ikke længere gyldig – forbind kalenderen igen",
                          code="provider_unauthorized")
    if r.status_code == 404:
        raise ActionError("Aftalen findes ikke længere i kalenderen", code="event_not_found")
    if r.status_code >= 400:
        raise ActionError(f"Kalenderen afviste kaldet ({r.status_code})", code="provider_rejected",
                          retryable=r.status_code == 429 or r.status_code >= 500)
    return r.json() if r.content and r.status_code != 204 else {}


def _iso(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _parse(v: str) -> datetime:
    dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


class GoogleCalendarClient:
    simulated = False
    BASE = "https://www.googleapis.com/calendar/v3"

    def __init__(self, token: str, calendar_id: str = "primary"):
        self._token = token
        self.calendar_id = calendar_id or "primary"

    def info(self) -> dict:
        # A freeBusy query needs only the calendar.freebusy scope and proves the token works for this calendar.
        now = datetime.now(UTC)
        self.busy(now, now + timedelta(hours=1))
        return {"calendar_id": self.calendar_id, "name": "Google Kalender", "email": ""}

    def busy(self, frm: datetime, to: datetime) -> list[tuple[datetime, datetime]]:
        out = _http("POST", f"{self.BASE}/freeBusy", self._token,
                    json={"timeMin": _iso(frm), "timeMax": _iso(to), "items": [{"id": self.calendar_id}]})
        periods = ((out.get("calendars") or {}).get(self.calendar_id) or {}).get("busy") or []
        return [(_parse(p["start"]), _parse(p["end"])) for p in periods if p.get("start") and p.get("end")]

    def create_event(self, *, title: str, start: datetime, end: datetime, description: str = "") -> str:
        ev = _http("POST", f"{self.BASE}/calendars/{self.calendar_id}/events", self._token,
                   json={"summary": title, "description": description,
                         "start": {"dateTime": _iso(start)}, "end": {"dateTime": _iso(end)}})
        return str(ev.get("id") or "")

    def update_event(self, event_id: str, *, start: datetime, end: datetime) -> None:
        _http("PATCH", f"{self.BASE}/calendars/{self.calendar_id}/events/{event_id}", self._token,
              json={"start": {"dateTime": _iso(start)}, "end": {"dateTime": _iso(end)}})

    def delete_event(self, event_id: str) -> None:
        try:
            _http("DELETE", f"{self.BASE}/calendars/{self.calendar_id}/events/{event_id}", self._token)
        except ActionError as e:
            if e.code != "event_not_found":
                raise


class MicrosoftCalendarClient:
    simulated = False
    BASE = "https://graph.microsoft.com/v1.0"

    def __init__(self, token: str, calendar_id: str = ""):
        self._token = token
        self.calendar_id = calendar_id  # empty = the default calendar

    def _cal(self) -> str:
        return f"/me/calendars/{self.calendar_id}" if self.calendar_id else "/me/calendar"

    def info(self) -> dict:
        me = _http("GET", f"{self.BASE}/me", self._token)
        cal = _http("GET", f"{self.BASE}{self._cal()}", self._token)
        return {"calendar_id": cal.get("id", ""), "name": cal.get("name", ""),
                "email": me.get("mail") or me.get("userPrincipalName") or ""}

    def busy(self, frm: datetime, to: datetime) -> list[tuple[datetime, datetime]]:
        out = _http("GET", f"{self.BASE}{self._cal()}/calendarView", self._token,
                    params={"startDateTime": _iso(frm), "endDateTime": _iso(to), "$top": 500,
                            "$select": "start,end,showAs,isCancelled"},
                    headers={"Prefer": 'outlook.timezone="UTC"'})
        res = []
        for ev in out.get("value") or []:
            if ev.get("isCancelled") or ev.get("showAs") in ("free", "workingElsewhere"):
                continue
            res.append((_parse(ev["start"]["dateTime"]), _parse(ev["end"]["dateTime"])))
        return res

    def create_event(self, *, title: str, start: datetime, end: datetime, description: str = "") -> str:
        ev = _http("POST", f"{self.BASE}{self._cal()}/events", self._token,
                   json={"subject": title, "body": {"contentType": "text", "content": description},
                         "start": {"dateTime": _iso(start), "timeZone": "UTC"},
                         "end": {"dateTime": _iso(end), "timeZone": "UTC"}})
        return str(ev.get("id") or "")

    def update_event(self, event_id: str, *, start: datetime, end: datetime) -> None:
        _http("PATCH", f"{self.BASE}/me/events/{event_id}", self._token,
              json={"start": {"dateTime": _iso(start), "timeZone": "UTC"},
                    "end": {"dateTime": _iso(end), "timeZone": "UTC"}})

    def delete_event(self, event_id: str) -> None:
        try:
            _http("DELETE", f"{self.BASE}/me/events/{event_id}", self._token)
        except ActionError as e:
            if e.code != "event_not_found":
                raise


# --------------------------------------------------------------------------- actions (shared)

def _summ_book(data: dict, out: dict) -> str:
    return f"Booket {out.get('type', 'tid')} {out.get('tidspunkt', '')}".strip()


ACTIONS: tuple[ActionSpec, ...] = (
    ActionSpec("ledige_tider", "Fandt ledige tider",
               "Find de næste ledige tider til en aftale. Brug den, før du foreslår tider. Læs højst tre tider op ad "
               "gangen. Returnerer tider med et 'start'-felt, som book_tid skal have uændret.",
               obj({"type": {"type": "string", "description": "Hvilken slags aftale (navn på bookingtypen)"},
                    "fra_dato": {"type": "string", "description": "Tidligste dato (ÅÅÅÅ-MM-DD), hvis kunden ønsker en bestemt dag"}}),
               obj({"tider": {"type": "array", "items": obj({"start": {"type": "string"}, "tekst": {"type": "string"}})},
                    "besked": {"type": "string"}}),
               summarize=lambda d, o: f"Fandt {len(o.get('tider') or [])} ledige tider"),
    ActionSpec("book_tid", "Booket tid",
               "Book en af de ledige tider til kunden, når kunden har valgt tiden og sagt sit navn. 'start' skal være "
               "præcis som fra ledige_tider.",
               obj({"start": {"type": "string", "description": "Starttidspunkt præcis som fra ledige_tider"},
                    "navn": {"type": "string", "minLength": 1, "description": "Kundens navn"},
                    "type": {"type": "string", "description": "Bookingtypen"},
                    "telefon": {"type": "string", "description": "Kundens telefonnummer, hvis det ikke er det, der ringes fra"},
                    "note": {"type": "string", "description": "Kort om, hvad kunden har brug for"}},
                   ["start", "navn"]),
               obj({"booking_id": {"type": "string"}, "type": {"type": "string"}, "tidspunkt": {"type": "string"},
                    "besked": {"type": "string"}}),
               confirm=True, summarize=_summ_book),
    ActionSpec("flyt_tid", "Flyttet tid",
               "Flyt kundens eksisterende aftale til en ny ledig tid (fra ledige_tider). Find først aftalen ud fra "
               "kundens telefonnummer eller navn; spørg, hvis der er flere.",
               obj({"ny_start": {"type": "string", "description": "Nyt starttidspunkt præcis som fra ledige_tider"},
                    "booking_id": {"type": "string", "description": "Aftalens id, hvis kendt fra en tidligere handling"},
                    "navn": {"type": "string", "description": "Kundens navn, bruges til at finde aftalen"}},
                   ["ny_start"]),
               obj({"booking_id": {"type": "string"}, "tidspunkt": {"type": "string"}, "besked": {"type": "string"}}),
               confirm=True, summarize=lambda d, o: f"Flyttet aftale til {o.get('tidspunkt', '')}"),
    ActionSpec("aflys_tid", "Aflyst tid",
               "Aflys kundens aftale. Find aftalen ud fra telefonnummer eller navn; bekræft hvilken, hvis der er flere.",
               obj({"booking_id": {"type": "string"}, "navn": {"type": "string"}}),
               obj({"booking_id": {"type": "string"}, "tidspunkt": {"type": "string"}, "besked": {"type": "string"}}),
               confirm=True, summarize=lambda d, o: f"Aflyst aftale {o.get('tidspunkt', '')}"),
)


class CalendarActions:
    """Runs the four actions against Dialogbot's bookings, mirroring to `client` when one is connected."""

    def __init__(self, db: OrmSession, workspace_id: uuid.UUID, client: CalendarClient | None, connector: str):
        from app.modules.bookings import service as bookings

        self.db, self.client, self.connector = db, client, connector
        self.ws = db.get(Workspace, workspace_id)
        self.bookings = bookings
        self.simulated = bool(client is not None and client.simulated)

    def test_connection(self) -> dict:
        return self.client.info() if self.client else {"name": "Dialogbots kalender"}

    # -- helpers
    def _type(self, name: str | None):
        types = self.bookings.active_types(self.db, self.ws.id)
        s = self.db.get(BookingSettings, self.ws.id)
        if not types or s is None or not s.enabled:
            raise ActionRefused("Online booking er ikke slået til hos virksomheden", code="booking_disabled")
        if name:
            for t in types:
                if t.name.lower() == name.strip().lower():
                    return t
        return types[0]

    def _find_booking(self, data: dict, ctx: RunContext) -> Booking:
        now = ctx.now or datetime.now(UTC)
        q = select(Booking).where(Booking.workspace_id == self.ws.id, Booking.status == "confirmed", Booking.ends_at > now)
        if data.get("booking_id"):
            try:
                b = self.db.get(Booking, uuid.UUID(str(data["booking_id"])))
            except ValueError:
                b = None
            if b is None or b.workspace_id != self.ws.id or b.status != "confirmed":
                raise ActionRefused("Aftalen kunne ikke findes", code="booking_not_found")
            return b
        cands = list(self.db.scalars(q.order_by(Booking.starts_at)))
        if ctx.caller_phone:
            by_phone = [b for b in cands if b.contact_phone and b.contact_phone == ctx.caller_phone]
            if by_phone:
                cands = by_phone
        if data.get("navn"):
            n = str(data["navn"]).strip().lower()
            by_name = [b for b in cands if n and n in (b.contact_name or "").lower()]
            if by_name:
                cands = by_name
        if not cands:
            raise ActionRefused("Der findes ingen kommende aftale på kundens navn eller nummer", code="booking_not_found")
        if len(cands) > 1 and not (ctx.caller_phone and all(b.contact_phone == ctx.caller_phone for b in cands)):
            raise ActionRefused("Der er flere mulige aftaler – spørg kunden hvilken (dato og navn)", code="ambiguous")
        return cands[0]

    # -- actions
    def run(self, action: str, data: dict, ctx: RunContext) -> ActionResult:
        tz = ctx.tz
        if action == "ledige_tider":
            bt = self._type(data.get("type"))
            frm = None
            if data.get("fra_dato"):
                try:
                    frm = datetime.fromisoformat(str(data["fra_dato"]))
                except ValueError:
                    frm = None
            free = self.bookings.slots(self.db, self.ws, bt, tz, limit=60)
            if frm is not None:
                free = [x for x in free if datetime.fromisoformat(x["start"]).date() >= frm.date()]
            free = free[:MAX_SLOTS]
            tider = [{"start": x["start"], "tekst": x["label"]} for x in free]
            msg = (f"Ledige tider til {bt.name.lower()}: " + "; ".join(f"{x['tekst']} (start {x['start']})" for x in tider)
                   if tider else "Der er ingen ledige tider i den periode. Tilbyd at en medarbejder ringer tilbage.")
            return ActionResult({"tider": tider, "besked": msg}, simulated=self.simulated)
        if action == "book_tid":
            bt = self._type(data.get("type"))
            from app.models import Conversation

            conv = self.db.get(Conversation, ctx.conversation_id) if ctx.conversation_id else None
            try:
                b = self.bookings.book(self.db, self.ws, type_id=bt.id, start=str(data["start"]), name=str(data["navn"]),
                                       phone=str(data.get("telefon") or ctx.caller_phone or ""), email=None,
                                       note=str(data.get("note") or ""), source=ctx.channel if ctx.channel in ("phone", "webchat") else "manual",
                                       tz=tz, conversation=conv, created_by=ctx.user_id)
            except ApiError as e:
                raise ActionRefused(e.message, code=e.code) from e
            b.provider_call_id = ctx.provider_call_id
            self._mirror_create(b, bt.name)
            when = self.bookings.label(b.starts_at, tz)
            return ActionResult({"booking_id": str(b.id), "type": bt.name, "tidspunkt": when,
                                 "besked": f"Booket: {bt.name} {when}. Bekræft tiden over for kunden."},
                                provider_ref=b.calendar_event_id, simulated=self.simulated)
        if action == "flyt_tid":
            b = self._find_booking(data, ctx)
            try:
                self.bookings.move(self.db, self.ws, b, start=str(data["ny_start"]), tz=tz)
            except ApiError as e:
                raise ActionRefused(e.message, code=e.code) from e
            self._mirror_update(b)
            when = self.bookings.label(b.starts_at, tz)
            return ActionResult({"booking_id": str(b.id), "tidspunkt": when, "besked": f"Aftalen er flyttet til {when}."},
                                provider_ref=b.calendar_event_id, simulated=self.simulated)
        if action == "aflys_tid":
            b = self._find_booking(data, ctx)
            when = self.bookings.label(b.starts_at, tz)
            self.bookings.cancel(self.db, b)
            self._mirror_delete(b)
            return ActionResult({"booking_id": str(b.id), "tidspunkt": when, "besked": f"Aftalen {when} er aflyst."},
                                provider_ref=b.calendar_event_id, simulated=self.simulated)
        raise ActionRefused("Ukendt handling", code="unknown_action")

    # -- mirroring (best effort; failures are recorded on the connection, never hidden from the owner)
    def _mirror_create(self, b: Booking, type_name: str) -> None:
        if self.client is None:
            return
        try:
            eid = self.client.create_event(title=f"{type_name}: {b.contact_name or 'kunde'}", start=b.starts_at, end=b.ends_at,
                                           description="\n".join(x for x in (b.contact_phone, b.note, "Booket via Dialogbot") if x))
            b.calendar_connector, b.calendar_event_id = self.connector, eid or None
        except ActionError as e:
            self._note(e)

    def _mirror_update(self, b: Booking) -> None:
        if self.client is None or not b.calendar_event_id:
            return
        try:
            self.client.update_event(b.calendar_event_id, start=b.starts_at, end=b.ends_at)
        except ActionError as e:
            self._note(e)

    def _mirror_delete(self, b: Booking) -> None:
        if self.client is None or not b.calendar_event_id:
            return
        try:
            self.client.delete_event(b.calendar_event_id)
        except ActionError as e:
            self._note(e)

    def _note(self, e: ActionError) -> None:
        from app.modules.integrations import credentials

        conn = credentials.connection(self.db, self.ws.id, self.connector)
        if conn is not None:
            credentials.mark_error(conn, f"Kalenderen kunne ikke opdateres: {e.message}")


def connected_busy(db: OrmSession, workspace_id: uuid.UUID, frm: datetime, to: datetime) -> list[tuple[datetime, datetime]] | None:
    """Busy time from the connected OAuth calendar, or None when none is connected (then iCal applies).
    A provider error is recorded on the connection and returns [] so booking still works from opening hours."""
    from app.modules.integrations import connectors, credentials

    for key in ("google_calendar", "microsoft_calendar"):
        conn = credentials.connection(db, workspace_id, key)
        if conn is None or conn.status != "connected":
            continue
        try:
            client = connectors.calendar_client(db, workspace_id, key)
            return client.busy(frm - timedelta(hours=1), to + timedelta(hours=1))
        except ActionError as e:
            credentials.mark_error(conn, f"Optaget tid kunne ikke hentes: {e.message}")
            return []
    return None

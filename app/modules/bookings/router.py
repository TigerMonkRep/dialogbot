from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session as OrmSession

from app.config import get_settings
from app.core.audit import record_audit
from app.core.auth import WorkspaceContext, get_scoped, require_capability
from app.core.errors import Conflict, NotFound, ValidationFailed
from app.db import get_db
from app.models import Booking, BookingSettings, BookingType, Workspace
from app.modules.bookings import service
from app.modules.integrations.connectors import calendar
from app.modules.setup.checks import invalidate_checks

router = APIRouter(prefix="/workspaces/{workspace_id}/bookings", tags=["bookings"])
public_router = APIRouter(prefix="/public", tags=["public"])


def _tz(db, ws_id) -> str:
    from app.modules.reports.service import tz_of

    return tz_of(db, ws_id)


def _connected_calendar(db: OrmSession, ws_id) -> dict | None:
    """The OAuth calendar (Google/Microsoft) the bookings are mirrored to, with its honest status."""
    from app.modules.integrations import credentials

    key = calendar.connected_calendar(db, ws_id)
    conn = credentials.connection(db, ws_id, key) if key else None
    if conn is None:
        return None
    return {"connector": key, "status": conn.status, "error": conn.error, "simulated": bool(conn.simulated),
            "last_ok_at": conn.last_ok_at.isoformat() if conn.last_ok_at else None,
            "sync_failed": db.scalar(select(func.count()).where(Booking.workspace_id == ws_id, Booking.status == "confirmed",
                                                                Booking.calendar_sync == "failed")) or 0,
            "pending_confirmation": db.scalar(select(func.count()).where(Booking.workspace_id == ws_id,
                                                                         Booking.status == "confirmed",
                                                                         Booking.confirmation == "pending")) or 0}


def settings_out(db: OrmSession, s: BookingSettings, ws_id) -> dict:
    return {"version": s.version, "calendar_connection": _connected_calendar(db, ws_id), "enabled": s.enabled, "lead_time_hours": s.lead_time_hours,
            "horizon_days": s.horizon_days, "buffer_minutes": s.buffer_minutes, "busy_ics_url": s.busy_ics_url,
            "busy_synced_at": s.busy_synced_at.isoformat() if s.busy_synced_at else None, "busy_error": s.busy_error,
            "busy_blocks": len(s.busy_blocks or []),
            "feed_url": f"{get_settings().public_base_url}/api/v1/public/calendar/{s.feed_token}.ics",
            "has_opening_hours": any(service.weekly_hours(db, ws_id).values()),
            "open_weekdays": [i for i, d in enumerate(service.DAYS) if service.weekly_hours(db, ws_id).get(d)],
            "opening_hours": {d: [f"{o:%H:%M}–{c:%H:%M}" for o, c in rows] for d, rows in service.weekly_hours(db, ws_id).items() if rows},
            "types": [{"id": str(t.id), "name": t.name, "duration_minutes": t.duration_minutes,
                       "description": t.description, "active": t.active}
                      for t in db.scalars(select(BookingType).where(BookingType.workspace_id == ws_id)
                                          .order_by(BookingType.created_at))]}


class SettingsIn(BaseModel):
    expected_version: int
    enabled: bool
    lead_time_hours: int = Field(ge=0, le=24 * 14)
    horizon_days: int = Field(ge=1, le=90)
    buffer_minutes: int = Field(ge=0, le=240)
    busy_ics_url: str | None = Field(default=None, max_length=1000)


class TypeIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    duration_minutes: int = Field(ge=15, le=480)
    description: str = Field(default="", max_length=1000)
    active: bool = True


class ManualIn(BaseModel):
    type_id: uuid.UUID
    start: str
    name: str = Field(min_length=1, max_length=200)
    phone: str | None = Field(default=None, max_length=40)
    email: EmailStr | None = None
    note: str = Field(default="", max_length=1000)


@router.get("/settings")
def get_settings_(ctx: WorkspaceContext = Depends(require_capability("bookings.read")), db: OrmSession = Depends(get_db)):
    s = service.settings(db, ctx.workspace.id)
    db.commit()
    return settings_out(db, s, ctx.workspace.id)


@router.put("/settings")
def put_settings(body: SettingsIn, request: Request, ctx: WorkspaceContext = Depends(require_capability("bookings.manage")),
                 db: OrmSession = Depends(get_db)):
    s = service.settings(db, ctx.workspace.id, lock=True)
    if body.expected_version != s.version:
        raise Conflict("Indstillingerne er ændret af en anden. Genindlæs.", code="version_conflict")
    url = (body.busy_ics_url or "").strip() or None
    if url and not url.lower().startswith(("https://", "http://", "webcal://")):
        raise ValidationFailed("Kalenderadressen skal begynde med https:// eller webcal://", field_errors=[{"field": "busy_ics_url"}])
    if body.enabled and not service.active_types(db, ctx.workspace.id):
        raise ValidationFailed("Opret mindst én bookingtype, før online booking slås til", field_errors=[{"field": "enabled"}])
    changed_url = url != s.busy_ics_url
    s.enabled, s.lead_time_hours, s.horizon_days, s.buffer_minutes, s.busy_ics_url = (
        body.enabled, body.lead_time_hours, body.horizon_days, body.buffer_minutes, url)
    s.version += 1
    if changed_url:
        service.sync_busy(db, s)
    record_audit(db, workspace_id=ctx.workspace.id, actor_user_id=ctx.user_id, action="bookings.settings_updated",
                 object_type="booking_settings", object_id=ctx.workspace.id,
                 after={"enabled": s.enabled, "calendar_connected": bool(url)}, request_id=request.state.request_id)
    invalidate_checks(db, ctx.workspace.id, changed_area="integrations", reason="bookings.settings_updated")
    db.commit()
    return settings_out(db, s, ctx.workspace.id)


@router.post("/calendar/sync")
def sync_calendar(ctx: WorkspaceContext = Depends(require_capability("bookings.manage")), db: OrmSession = Depends(get_db)):
    s = service.settings(db, ctx.workspace.id, lock=True)
    service.sync_busy(db, s)
    db.commit()
    return settings_out(db, s, ctx.workspace.id)


@router.post("/types", status_code=201)
def add_type(body: TypeIn, ctx: WorkspaceContext = Depends(require_capability("bookings.manage")), db: OrmSession = Depends(get_db)):
    t = BookingType(workspace_id=ctx.workspace.id, name=body.name.strip(), duration_minutes=body.duration_minutes,
                    description=body.description.strip(), active=body.active)
    db.add(t)
    db.commit()
    return {"id": str(t.id)}


@router.put("/types/{type_id}")
def put_type(type_id: uuid.UUID, body: TypeIn, ctx: WorkspaceContext = Depends(require_capability("bookings.manage")),
             db: OrmSession = Depends(get_db)):
    t = get_scoped(db, BookingType, type_id, ctx.workspace.id)
    t.name, t.duration_minutes, t.description, t.active = body.name.strip(), body.duration_minutes, body.description.strip(), body.active
    db.commit()
    return {"id": str(t.id)}


@router.get("/slots")
def list_slots(type_id: uuid.UUID, ctx: WorkspaceContext = Depends(require_capability("bookings.read")),
               db: OrmSession = Depends(get_db)):
    t = get_scoped(db, BookingType, type_id, ctx.workspace.id)
    return {"items": service.slots(db, ctx.workspace, t, _tz(db, ctx.workspace.id))}


@router.get("/messages")
def booking_messages(lang: str | None = Query(default=None, max_length=5), booking_id: uuid.UUID | None = None,
                     ctx: WorkspaceContext = Depends(require_capability("bookings.read")), db: OrmSession = Depends(get_db)):
    """E07: every booking message (customer SMS + e-mail, owner e-mail) rendered for preview. Read-only: nothing is
    queued or sent. With `booking_id` the workspace's own booking fills the texts; otherwise sample data does.
    The default language is the one the business serves its callers in."""
    from app.core.languages import LANGUAGES, normalize
    from app.modules.bookings import messages
    from app.modules.integrations.connectors.sms import caller_language

    ws = ctx.workspace
    default_lang = caller_language(db, ws)
    language = normalize(lang) if lang else default_lang
    tz = _tz(db, ws.id)
    ctx_ = messages.sample_context(language, business=ws.name, tz=tz)
    source = "sample"
    if booking_id is not None:
        b = db.scalar(select(Booking).where(Booking.id == booking_id, Booking.workspace_id == ws.id))
        if b is None:
            raise NotFound("Aftalen findes ikke")
        ctx_.customer, ctx_.what, ctx_.when = b.contact_name or "", b.title.split(":")[0], b.starts_at
        ctx_.new_when = b.starts_at + timedelta(days=1)
        source = "booking"
    items = []
    for v in messages.VARIANTS:
        r = messages.render(v, language, ctx_)
        mail = r["email"]
        items.append({"variant": v, "audience": r["audience"], "label": r["label"], "sms": r["sms"],
                      "email": {"subject": mail.subject, "preheader": mail.preheader, "html": mail.html(), "text": mail.text(),
                                "from_name": ws.name if r["audience"] == "customer" else "Dialogbot"}})
    return {"lang": language, "default_lang": default_lang, "languages": list(LANGUAGES), "source": source,
            "business": ws.name, "sends_nothing": True, "items": items}


@router.get("")
def list_bookings(days: int = Query(default=30, ge=1, le=120), include_cancelled: bool = False,
                  start: date | None = None, end: date | None = None,
                  ctx: WorkspaceContext = Depends(require_capability("bookings.read")), db: OrmSession = Depends(get_db)):
    """Default: from yesterday to `days` ahead. With `start` (and `end`, inclusive) the local calendar days in between instead."""
    now = datetime.now(UTC)
    tz = _tz(db, ctx.workspace.id)
    if start is not None:
        from app.modules.reports.service import day_bounds

        a = day_bounds(start, tz)[0]
        b = day_bounds(max(end or start, start), tz)[1]
        q = select(Booking).where(Booking.workspace_id == ctx.workspace.id, Booking.starts_at >= a, Booking.starts_at < b).order_by(Booking.starts_at)
    else:
        q = select(Booking).where(Booking.workspace_id == ctx.workspace.id, Booking.ends_at >= now - timedelta(days=1),
                                  Booking.starts_at <= now + timedelta(days=days)).order_by(Booking.starts_at)
    if not include_cancelled:
        q = q.where(Booking.status == "confirmed")
    return {"items": [service.booking_out(b, tz) for b in db.scalars(q)], "timezone": tz}


@router.post("", status_code=201)
def manual_booking(body: ManualIn, request: Request, ctx: WorkspaceContext = Depends(require_capability("bookings.create")),
                   db: OrmSession = Depends(get_db)):
    tz = _tz(db, ctx.workspace.id)
    b = service.book(db, ctx.workspace, type_id=body.type_id, start=body.start, name=body.name, phone=body.phone,
                     email=str(body.email) if body.email else None, note=body.note, source="manual", tz=tz,
                     created_by=ctx.user_id)
    calendar.mirror_create(db, ctx.workspace.id, b)  # failure → calendar_sync='failed'
    record_audit(db, workspace_id=ctx.workspace.id, actor_user_id=ctx.user_id, action="bookings.created",
                 object_type="booking", object_id=b.id, after={"starts_at": b.starts_at.isoformat()},
                 request_id=request.state.request_id)
    db.commit()
    return service.booking_out(b, tz)


class ConfirmIn(BaseModel):
    override_conflict: bool = False


@router.post("/{booking_id}/confirm")
def confirm(booking_id: uuid.UUID, request: Request, body: ConfirmIn | None = None,
            ctx: WorkspaceContext = Depends(require_capability("bookings.create")), db: OrmSession = Depends(get_db)):
    """A staff member confirms a booking «afventer bekræftelse» (made while the connected calendar could not be read).
    It is then written to the calendar through the shared mirror path; a write failure shows as «Ikke i kalenderen»."""
    b = get_scoped(db, Booking, booking_id, ctx.workspace.id)
    tz = _tz(db, ctx.workspace.id)
    was = b.confirmation
    service.confirm(db, b, actor=ctx.user_id, override_conflict=bool(body and body.override_conflict), tz=tz)
    if was == "pending":
        if b.calendar_event_id:
            calendar.mirror_update(db, ctx.workspace.id, b)
        else:
            calendar.mirror_create(db, ctx.workspace.id, b)
        record_audit(db, workspace_id=ctx.workspace.id, actor_user_id=ctx.user_id, action="bookings.confirmed",
                     object_type="booking", object_id=b.id,
                     after={"override_conflict": bool(body and body.override_conflict), "calendar_sync": b.calendar_sync},
                     request_id=request.state.request_id)
    db.commit()
    return service.booking_out(b, tz)


@router.post("/{booking_id}/cancel")
def cancel(booking_id: uuid.UUID, request: Request, ctx: WorkspaceContext = Depends(require_capability("bookings.create")),
           db: OrmSession = Depends(get_db)):
    b = get_scoped(db, Booking, booking_id, ctx.workspace.id)
    service.cancel(db, b)
    calendar.mirror_cancel(db, ctx.workspace.id, b)
    record_audit(db, workspace_id=ctx.workspace.id, actor_user_id=ctx.user_id, action="bookings.cancelled",
                 object_type="booking", object_id=b.id, request_id=request.state.request_id)
    db.commit()
    return service.booking_out(b, _tz(db, ctx.workspace.id))


# --------------------------------------------------------------------------- public

@public_router.get("/calendar/{token}.ics")
def calendar_feed(token: str, db: OrmSession = Depends(get_db)):
    """Secret, read-only iCal feed of the workspace's bookings for the owner's own calendar app."""
    s = db.scalar(select(BookingSettings).where(BookingSettings.feed_token == token))
    if s is None:
        raise NotFound("Ukendt kalender")
    ws = db.get(Workspace, s.workspace_id)
    return Response(content=service.feed(db, s, ws), media_type="text/calendar; charset=utf-8",
                    headers={"cache-control": "no-store"})


class VisitorBookingIn(BaseModel):
    type_id: uuid.UUID
    start: str
    name: str = Field(min_length=1, max_length=200)
    phone: str | None = Field(default=None, max_length=40, pattern=r"^[0-9+ ()-]{6,40}$")
    email: EmailStr | None = None
    note: str = Field(default="", max_length=1000)
    consent: bool


@public_router.get("/webchat/{key}/booking")
def visitor_booking_options(key: str, type_id: uuid.UUID | None = None, db: OrmSession = Depends(get_db)):
    """Booking types and free times for the chat widget. Empty when booking is off."""
    from app.modules.webchat import service as webchat

    wc = webchat.by_key(db, key)
    ws = db.get(Workspace, wc.workspace_id)
    s = service.settings(db, ws.id)
    db.commit()
    types = service.active_types(db, ws.id) if s.enabled else []
    chosen = next((t for t in types if t.id == type_id), types[0] if types else None)
    return {"enabled": bool(types), "types": [{"id": str(t.id), "name": t.name, "duration_minutes": t.duration_minutes,
                                               "description": t.description} for t in types],
            "type_id": str(chosen.id) if chosen else None,
            "slots": service.slots(db, ws, chosen, _tz(db, ws.id), limit=24) if chosen else []}


@public_router.post("/webchat/{key}/conversations/{conversation_id}/booking", status_code=201)
def visitor_book(key: str, conversation_id: uuid.UUID, body: VisitorBookingIn, origin: str | None = Header(default=None),
                 x_visitor_token: str | None = Header(default=None), db: OrmSession = Depends(get_db)):
    from app.modules.webchat import service as webchat
    from app.modules.webchat.public import _require_frame_origin

    _require_frame_origin(origin)
    wc = webchat.by_key(db, key)
    conv = webchat.visitor_conversation(db, wc, conversation_id, x_visitor_token)
    if not body.consent:
        raise ValidationFailed("Sæt flueben for at give os lov til at kontakte dig om aftalen", field_errors=[{"field": "consent"}])
    if not body.email and not body.phone:
        raise ValidationFailed("Angiv e-mail eller telefonnummer", field_errors=[{"field": "email"}, {"field": "phone"}])
    ws = db.get(Workspace, wc.workspace_id)
    tz = _tz(db, ws.id)
    b = service.book(db, ws, type_id=body.type_id, start=body.start, name=body.name, phone=body.phone,
                     email=str(body.email) if body.email else None, note=body.note, source="webchat", tz=tz,
                     conversation=conv)
    calendar.mirror_create(db, ws.id, b)  # the owner sees a failed write on the booking
    from app.modules.customer import service as customer

    url = customer.issue_link(db, purpose="booking", ws_id=ws.id, booking=b)  # W13: see, move or cancel
    db.commit()
    # confirmation 'pending': the connected calendar could not be read – the widget says a staff member confirms
    return {"booked": True, "label": service.label(b.starts_at, tz), "title": b.title,
            "confirmation": "pending" if b.confirmation == "pending" else "confirmed", "manage_url": url}

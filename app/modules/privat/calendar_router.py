"""Privat: the Kalender app (docs/privat-api.md «Kalender»).

Every route but the subscription feed resolves the caller's own personal workspace and needs the Kalender app on
(403 addon_disabled). The feed is public by design – calendar apps cannot log in – and is reached only with the
secret token, of which only a hash is stored; the token is redacted from request logs (app/core/logging.py).
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session as OrmSession

from app.core.audit import record_audit
from app.core.errors import NotFound
from app.db import get_db
from app.modules.privat import addons, appointments
from app.modules.privat.deps import PrivateCtx, private_ctx

router = APIRouter(prefix="/privat", tags=["privat-calendar"])
public_router = APIRouter(prefix="/privat/calendar", tags=["privat-calendar"])

ICS = "text/calendar; charset=utf-8"


def _need(db: OrmSession, ctx: PrivateCtx) -> None:
    addons.require(db, ctx.ws_id, appointments.ADDON)


def _audit(db: OrmSession, request: Request, ctx: PrivateCtx, action: str, after: dict | None = None) -> None:
    record_audit(db, workspace_id=ctx.ws_id, actor_user_id=ctx.user_id, action=action, object_type="private_calendar",
                 object_id=ctx.ws_id, after=after, request_id=getattr(request.state, "request_id", None))


@router.get("/calendar")
def calendar(ctx: PrivateCtx = Depends(private_ctx), db: OrmSession = Depends(get_db)):
    """The Kalender app's state: the subscription link (only whether it exists), Google/Outlook and upcoming times."""
    on = appointments.enabled(db, ctx.ws_id)
    return {"enabled": on,
            "feed": {"active": ctx.profile.calendar_feed_token_hash is not None,
                     "created_at": ctx.profile.calendar_feed_created_at.isoformat()
                     if ctx.profile.calendar_feed_created_at else None},
            "providers": appointments.connection_status(db, ctx.ws_id),
            "appointments": [appointments.out(a) for a in appointments.upcoming(db, ctx.ws_id)] if on else []}


@router.post("/calendar/feed")
def new_feed(request: Request, ctx: PrivateCtx = Depends(private_ctx), db: OrmSession = Depends(get_db)):
    """A new secret subscription link. It is shown this once; the previous link stops working."""
    _need(db, ctx)
    url = appointments.new_feed(db, ctx.profile)
    _audit(db, request, ctx, "privat.calendar.feed_created")
    db.commit()
    return {"url": url, "webcal_url": "webcal://" + url.split("://", 1)[1]}


@router.delete("/calendar/feed", status_code=204)
def drop_feed(request: Request, ctx: PrivateCtx = Depends(private_ctx), db: OrmSession = Depends(get_db)):
    appointments.drop_feed(db, ctx.profile)
    _audit(db, request, ctx, "privat.calendar.feed_removed")
    db.commit()
    return Response(status_code=204)


@router.post("/calendar/connect/{provider}")
def connect(provider: str, request: Request, ctx: PrivateCtx = Depends(private_ctx), db: OrmSession = Depends(get_db)):
    """Where to send the user to give access to Google Calendar or Outlook. They come back to /privat/kalender."""
    _need(db, ctx)
    url = appointments.connect_url(db, ctx, provider)
    _audit(db, request, ctx, "privat.calendar.connect_started", {"provider": provider})
    db.commit()
    return {"url": url}


@router.delete("/calendar/connect/{provider}", status_code=204)
def disconnect(provider: str, request: Request, ctx: PrivateCtx = Depends(private_ctx), db: OrmSession = Depends(get_db)):
    """Revokes the access at the provider (best effort) and deletes the stored credentials."""
    appointments.disconnect(db, ctx.ws_id, provider)
    _audit(db, request, ctx, "privat.calendar.disconnected", {"provider": provider})
    db.commit()
    return Response(status_code=204)


@router.get("/appointments")
def list_appointments(ctx: PrivateCtx = Depends(private_ctx), db: OrmSession = Depends(get_db)):
    _need(db, ctx)
    return {"items": [appointments.out(a) for a in appointments.upcoming(db, ctx.ws_id)]}


@router.get("/appointments/{appointment_id}.ics")
def appointment_ics(appointment_id: uuid.UUID, ctx: PrivateCtx = Depends(private_ctx), db: OrmSession = Depends(get_db)):
    """One appointment as a calendar file («Tilføj til kalender»)."""
    _need(db, ctx)
    a = appointments.own(db, ctx.ws_id, appointment_id)
    return Response(appointments.to_ics([a]), media_type=ICS,
                    headers={"Content-Disposition": 'attachment; filename="aftale.ics"', "Cache-Control": "no-store"})


@router.delete("/appointments/{appointment_id}")
def cancel_appointment(appointment_id: uuid.UUID, request: Request, ctx: PrivateCtx = Depends(private_ctx),
                       db: OrmSession = Depends(get_db)):
    """Removes the time from the user's calendars. It does NOT cancel anything at the business."""
    _need(db, ctx)
    a = appointments.cancel(db, appointments.own(db, ctx.ws_id, appointment_id))
    _audit(db, request, ctx, "privat.appointment.removed", {"appointment_id": str(a.id)})
    db.commit()
    return appointments.out(a)


@public_router.get("/feed/{token}.ics")
def feed(token: str, db: OrmSession = Depends(get_db)):
    body = appointments.feed_for(db, token)
    if body is None:
        raise NotFound("Kalenderen findes ikke")
    return Response(body, media_type=ICS, headers={"Cache-Control": "private, max-age=300"})

"""Public endpoints behind the customer's secure links (no login; the token in the path is the key). W09 + W13.

    GET  /public/customer/callback/{token}                 the call back + preferences
    POST /public/customer/callback/{token}/cancel          «Aflys opringningen»
    PUT  /public/customer/callback/{token}/preferences     {calls_opt_out}
    GET  /public/booking/manage/{token}                    the appointment, policy and whether a code is needed
    POST /public/booking/manage/{token}/code               SMS code to the booking's own number
    POST /public/booking/manage/{token}/verify             {verification_id, code} → {session} (30 minutes)
    GET  /public/booking/manage/{token}/slots              free times of the same type
    POST /public/booking/manage/{token}/move               {start, session}
    POST /public/booking/manage/{token}/cancel             {session}

Errors: 404 `link_invalid` (unknown, replaced or another purpose's token), 410 `link_expired`, 403
`verification_required`, 409 `change_too_late` / `booking_cancelled` / `slot_taken`.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session as OrmSession

from app.core.errors import NotFound, ValidationFailed
from app.db import get_db
from app.models import Booking, BookingType, Workspace
from app.modules.customer import service

router = APIRouter(prefix="/public", tags=["customer-public"])


# --------------------------------------------------------------------------- W09

@router.get("/customer/callback/{token}")
def callback(token: str, db: OrmSession = Depends(get_db)):
    """The customer's call back and communication preference. No internal notes, tasks or staff."""
    return service.callback_view(db, service.resolve(db, "callback", token))


@router.post("/customer/callback/{token}/cancel")
def cancel_callback(token: str, db: OrmSession = Depends(get_db)):
    """The customer cancels the call back: the lead is marked, its open tasks are closed. Idempotent."""
    link = service.resolve(db, "callback", token, lock=True)
    service.cancel_callback(db, link)
    db.commit()
    return service.callback_view(db, link)


class CustomerPreferencesIn(BaseModel):
    calls_opt_out: bool = Field(description="True = the number goes on the business's do-not-call list (campaigns)")


@router.put("/customer/callback/{token}/preferences")
def preferences(token: str, body: CustomerPreferencesIn, db: OrmSession = Depends(get_db)):
    link = service.resolve(db, "callback", token, lock=True)
    service.set_calls_opt_out(db, link, body.calls_opt_out)
    db.commit()
    return service.callback_view(db, link)


# --------------------------------------------------------------------------- W13

@router.get("/booking/manage/{token}")
def booking(token: str, db: OrmSession = Depends(get_db)):
    """The appointment, whether it can still be changed (`policy`) and whether a code is needed first."""
    return service.booking_view(db, service.resolve(db, "booking", token), None)


@router.post("/booking/manage/{token}/code", status_code=202)
def booking_code(token: str, request: Request, db: OrmSession = Depends(get_db)):
    """A code by SMS to the number the booking was made with (shown masked). Same limits as the chat's code."""
    from app.modules.privat.lookup_limits import client_ip

    link = service.resolve(db, "booking", token)
    phone = service.booking_phone(db, link)
    out = service.send_code(db, db.get(Workspace, link.workspace_id), purpose="booking_manage", phone=phone,
                            ip=client_ip(request), link=link)
    db.commit()
    return out


class CustomerVerifyIn(BaseModel):
    verification_id: str = Field(min_length=1, max_length=64)
    code: str = Field(min_length=1, max_length=12)


@router.post("/booking/manage/{token}/verify")
def booking_verify(token: str, body: CustomerVerifyIn, db: OrmSession = Depends(get_db)):
    """The code → a session for this link (30 minutes) that `move` and `cancel` need."""
    link = service.resolve(db, "booking", token)
    try:
        v = service.check_code(db, purpose="booking_manage", verification_id=body.verification_id, code=body.code,
                               link=link)
    except ValidationFailed:
        db.commit()  # the attempt counts even though the request fails
        raise
    session = service.open_session(db, v)
    db.commit()
    return {"status": "verified", "session": session}


@router.get("/booking/manage/{token}/slots")
def booking_slots(token: str, db: OrmSession = Depends(get_db)):
    from app.modules.bookings import service as bookings
    from app.modules.reports.service import tz_of

    link = service.resolve(db, "booking", token)
    b = db.get(Booking, link.booking_id)
    bt = db.get(BookingType, b.type_id) if b and b.type_id else None
    if b is None or bt is None:
        raise NotFound("Bookingtypen findes ikke længere")
    ws = db.get(Workspace, b.workspace_id)
    tz = tz_of(db, ws.id)
    free = bookings.slots(db, ws, bt, tz, limit=24)
    db.commit()
    return {"timezone": tz, "slots": [{"start": x["start"], "end": x["end"]} for x in free]}


class CustomerMoveIn(BaseModel):
    start: str = Field(min_length=10, max_length=40)
    session: str | None = Field(default=None, max_length=100)


@router.post("/booking/manage/{token}/move")
def move(token: str, body: CustomerMoveIn, db: OrmSession = Depends(get_db)):
    """Move to a free time of the same type. When the business's calendar cannot be written, the new time is noted and
    a staff member confirms it (`confirmation: pending`) – the customer is not told the calendar has it (DB-007)."""
    from app.modules.bookings import service as bookings
    from app.modules.integrations.connectors import calendar
    from app.modules.reports.service import tz_of

    link = service.resolve(db, "booking", token)
    b = service.locked_booking(db, link, body.session)
    ws = db.get(Workspace, b.workspace_id)
    tz = tz_of(db, ws.id)
    before = b.starts_at
    bookings.move(db, ws, b, start=body.start, tz=tz)
    if b.starts_at != before:
        if not calendar.mirror_update(db, ws.id, b) and b.confirmation != "pending":
            b.confirmation = "pending"
            bookings._ask_staff_to_confirm(db, b, tz)
        service.note_customer_change(db, b, "move", tz)
    db.commit()
    return service.booking_view(db, link, body.session)


class CustomerCancelIn(BaseModel):
    session: str | None = Field(default=None, max_length=100)


@router.post("/booking/manage/{token}/cancel")
def cancel(token: str, body: CustomerCancelIn, db: OrmSession = Depends(get_db)):
    from app.modules.bookings import service as bookings
    from app.modules.integrations.connectors import calendar
    from app.modules.reports.service import tz_of

    link = service.resolve(db, "booking", token)
    b = service.locked_booking(db, link, body.session)
    bookings.cancel(db, b)
    calendar.mirror_cancel(db, b.workspace_id, b)
    service.note_customer_change(db, b, "cancel", tz_of(db, b.workspace_id))
    db.commit()
    return service.booking_view(db, link, body.session)

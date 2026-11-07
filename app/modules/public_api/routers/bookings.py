from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from app.core.auth import get_scoped
from app.db import get_db
from app.models import Booking, BookingType
from app.modules.public_api import cursor
from app.modules.public_api.auth import PublicPrincipal, require_scope
from app.modules.public_api.schemas import v1

router = APIRouter(prefix="/workspaces/{workspace_id}", tags=["bookings"])


@router.get("/booking-types", response_model=v1.Page[v1.BookingType], summary="Aftaletyper")
def list_booking_types(include_inactive: bool = Query(default=False),
                       principal: PublicPrincipal = Depends(require_scope("bookings:read")),
                       db: OrmSession = Depends(get_db)):
    q = select(BookingType).where(BookingType.workspace_id == principal.workspace_id)
    if not include_inactive:
        q = q.where(BookingType.active.is_(True))
    rows = db.scalars(q.order_by(BookingType.created_at, BookingType.id)).all()
    return {"items": [v1.booking_type_out(t) for t in rows], "next_cursor": None}


@router.get("/bookings", response_model=v1.Page[v1.Booking], summary="Aftaler, senest oprettede først")
def list_bookings(p: cursor.CursorParams = Depends(),
                  starts_after: datetime | None = Query(default=None, alias="from", description="Starter efter (ISO 8601)"),
                  starts_before: datetime | None = Query(default=None, alias="to", description="Starter før"),
                  status: str | None = Query(default=None, pattern="^(confirmed|cancelled)$"),
                  principal: PublicPrincipal = Depends(require_scope("bookings:read")), db: OrmSession = Depends(get_db)):
    q = select(Booking).where(Booking.workspace_id == principal.workspace_id)
    if starts_after is not None:
        q = q.where(Booking.starts_at >= starts_after)
    if starts_before is not None:
        q = q.where(Booking.starts_at < starts_before)
    if status:
        q = q.where(Booking.status == status)
    rows = list(db.scalars(cursor.apply(q, p, Booking.created_at, Booking.id)))
    reveal = principal.has("contacts:read")
    return cursor.page(rows, p, lambda b: b.created_at, lambda b: b.id, lambda b: v1.booking_out(b, reveal))


@router.get("/bookings/{booking_id}", response_model=v1.Booking, summary="Én aftale")
def get_booking(booking_id: uuid.UUID, principal: PublicPrincipal = Depends(require_scope("bookings:read")),
                db: OrmSession = Depends(get_db)) -> v1.Booking:
    return v1.booking_out(get_scoped(db, Booking, booking_id, principal.workspace_id), principal.has("contacts:read"))

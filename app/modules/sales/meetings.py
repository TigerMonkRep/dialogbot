"""Intro meetings booked by Peter (phase 3). The booking in the sales workspace is the source of truth: a booking that
was cancelled (by the customer, the operator or the connected calendar) cancels the meeting the next time it is read."""
from __future__ import annotations

from sqlalchemy.orm import Session as OrmSession

from app.models import Booking, SalesMeeting


def sync(db: OrmSession, m: SalesMeeting) -> SalesMeeting:
    b = db.get(Booking, m.booking_id) if m.booking_id else None
    if b is not None:
        if b.status == "cancelled" and m.status in ("proposed", "confirmed"):
            m.status = "cancelled"
        if b.calendar_event_id and m.calendar_confirmed_at is None:
            m.calendar_confirmed_at = b.created_at
        m.starts_at = b.starts_at
    return m


def out(db: OrmSession, m: SalesMeeting) -> dict:
    sync(db, m)
    b = db.get(Booking, m.booking_id) if m.booking_id else None
    return {"id": str(m.id), "company_id": str(m.company_id), "status": m.status,
            "starts_at": m.starts_at.isoformat() if m.starts_at else None,
            "booking": {"id": str(b.id), "status": b.status, "contact_name": b.contact_name,
                        "contact_email": b.contact_email, "calendar": b.calendar_connector} if b else None,
            "calendar_confirmed": m.calendar_confirmed_at is not None,
            "campaign_contact_id": str(m.campaign_contact_id) if m.campaign_contact_id else None,
            "created_at": m.created_at.isoformat()}

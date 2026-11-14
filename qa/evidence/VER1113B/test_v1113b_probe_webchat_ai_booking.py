"""Probe (verifier 13/11 b): the webchat ASSISTANT's book_tid action with a phone number the visitor typed – is the
number proven with the W04 SMS code like the booking form (F-VER1113-04)?"""
import uuid

from sqlalchemy import select

from app.models import Booking, Lead, Workspace
from app.modules.integrations import actions
from app.modules.integrations.connectors.base import RunContext
from app.worker import runner
from tests.qa.test_qa_integ_E07 import _ready
from tests.test_booking_messages import fake  # noqa: F401  (fixture)

STRANGER = "+4522334455"


def test_probe_webchat_assistant_books_with_unproven_phone(api, client, fake, db):  # noqa: F811
    tok, ws = _ready(api, client, "v1113b-aibook")
    w = db.get(Workspace, uuid.UUID(ws))
    ctx = RunContext(workspace_id=w.id, channel="webchat")
    _, run = actions.execute(db, w, "ledige_tider", {}, ctx)
    db.commit()
    start = run.output["tider"][0]["start"]
    text, run = actions.execute(db, w, "book_tid", {"start": start, "navn": "Bo", "telefon": STRANGER,
                                                    "bekraeftet": True}, ctx)
    db.commit()
    print("book_tid status:", run.status, run.error, text[:120])
    b = db.scalar(select(Booking).where(Booking.workspace_id == w.id))
    lead = db.get(Lead, b.lead_id) if b and b.lead_id else None
    print("booking.phone:", b.contact_phone if b else None, "source:", b.source if b else None,
          "lead.phone:", getattr(lead, "contact_phone", None), "lead.phone_verified_at:", getattr(lead, "phone_verified_at", None))
    runner.drain()
    print("fake SMS to:", [getattr(s, "to", s) for s in fake.sms])
    from app.models import BookingMessage
    db.expire_all()
    rows = db.scalars(select(BookingMessage).where(BookingMessage.booking_id == b.id)).all()
    print("booking_messages:", [(r.variant, r.channel, r.status, getattr(r, "recipient", None)) for r in rows])
    print("fake world sms:", fake.sms)

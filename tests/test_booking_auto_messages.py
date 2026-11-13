"""E07 auto-send (app/modules/bookings/notify.py): booking messages go out through the outbox and the worker.

Decision 2026-11-13 (Fürster): customer e-mail by default when the booking has an address; SMS only with the business's
opt-in (off by default); reminder 24 h before at a sensible local time; owner e-mails for «kræver opmærksomhed» and
«levering fejlede»; unsubscribed/blocked customers get nothing; one message per event and channel; audited; per tenant;
the business's language. Nothing leaves the process: EMAIL_ADAPTER=simulated and CONNECTORS_PROVIDER=fake.
"""
from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime, timedelta
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import func, select

from app.config import get_settings
from app.models import (
    AuditLog,
    Booking,
    BookingMessage,
    CustomerMessageSuppression,
    DoNotCall,
    EmailDelivery,
    LanguageSettings,
    OutboxEvent,
    User,
    Workspace,
)
from app.modules.bookings import notify
from app.modules.bookings import service as bookings
from app.modules.integrations.connectors import fakes
from app.modules.integrations.connectors.base import ActionError
from app.modules.integrations.connectors.fakes import WORLD
from app.worker import runner

PHONE = "+4522334455"
CPH = ZoneInfo("Europe/Copenhagen")


@pytest.fixture
def fake(monkeypatch):
    monkeypatch.setenv("CONNECTORS_PROVIDER", "fake")
    monkeypatch.delenv("TELEPHONY_PROVIDER", raising=False)
    get_settings.cache_clear()
    WORLD.reset()
    yield WORLD
    WORLD.reset()
    get_settings.cache_clear()


ALL_DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


def _setup(api, client, tag: str, *, name: str = "Fjord Gulvservice ApS", calendar: bool = False, hours=("08:00", "20:00"),
           days=ALL_DAYS):
    tok = api.user(f"{tag}@testmail.dk")
    ws = api.workspace(tok, name)
    if hours:
        h = api.knowledge(tok, ws, "opening_hours", "Åbningstider",
                          {"weekly": [{"days": list(days), "open": hours[0], "close": hours[1]}]})
        api.submit(tok, ws, h["open_draft"]["id"])
        assert api.approve(tok, ws, h["open_draft"]["id"]).status_code == 200
    r = api.post(tok, f"/workspaces/{ws}/bookings/types", {"name": "Besigtigelse", "duration_minutes": 60})
    type_id = r.json()["id"]
    s = api.get(tok, f"/workspaces/{ws}/bookings/settings").json()
    assert api.put(tok, f"/workspaces/{ws}/bookings/settings",
                   {"enabled": bool(hours), "lead_time_hours": 0, "horizon_days": 7, "buffer_minutes": 0,
                    "expected_version": s["version"]}).status_code == 200
    if calendar:
        r = api.post(tok, f"/workspaces/{ws}/integrations/google_calendar/connect", {"config": {}, "secrets": {}})
        url = urlparse(r.json()["authorize_url"])
        client.get(url.path + "?" + url.query, follow_redirects=False)
    return tok, ws, type_id


def _slots(api, tok, ws, type_id) -> list[str]:
    return [x["start"] for x in api.get(tok, f"/workspaces/{ws}/bookings/slots?type_id={type_id}").json()["items"]]


def _book(api, tok, ws, type_id, start, *, email="mette@kunde.dk", phone=PHONE, name="Mette Nielsen") -> dict:
    body = {"type_id": type_id, "start": start, "name": name}
    if email:
        body["email"] = email
    if phone:
        body["phone"] = phone
    r = api.post(tok, f"/workspaces/{ws}/bookings", body)
    assert r.status_code == 201, r.text
    return r.json()


def _drain() -> None:
    runner.drain()


def _mails(db, to: str | None = None) -> list[EmailDelivery]:
    db.expire_all()
    q = select(EmailDelivery).order_by(EmailDelivery.created_at)
    if to:
        q = q.where(EmailDelivery.to_email == to)
    return list(db.scalars(q))


def _rows(db, booking_id=None) -> list[BookingMessage]:
    db.expire_all()
    q = select(BookingMessage).order_by(BookingMessage.created_at)
    if booking_id:
        q = q.where(BookingMessage.booking_id == uuid.UUID(str(booking_id)))
    return list(db.scalars(q))


def _sms_on(api, tok, ws, on=True):
    r = api.put(tok, f"/workspaces/{ws}/bookings/messages/settings", {"sms_enabled": on})
    assert r.status_code == 200, r.text
    return r.json()


# --------------------------------------------------------------------------- created / confirmed by channel

def test_booking_sends_the_confirmation_by_email_only_by_default(api, client, fake, db):
    tok, ws, tid = _setup(api, client, "e07a-default")
    start = _slots(api, tok, ws, tid)[0]
    b = _book(api, tok, ws, tid, start)
    _drain()
    mails = _mails(db, "mette@kunde.dk")
    assert [m.subject for m in mails] == ["Din tid er bekræftet – Fjord Gulvservice ApS"]
    body = mails[0].body_text
    assert "Hej Mette," in body and "Besigtigelse" in body and bookings.label(datetime.fromisoformat(start), "Europe/Copenhagen") in body
    assert re.search(r"Afmeld e-mails om aftaler fra Fjord Gulvservice ApS: http\S+/api/v1/public/booking-messages/unsubscribe/\S+", body)
    assert fake.sms == []  # no SMS without the business's opt-in
    rows = _rows(db, b["id"])
    assert [(r.variant, r.channel, r.audience, r.status, r.lang) for r in rows] == [("confirmed", "email", "customer", "simulated", "da")]
    audit = db.scalars(select(AuditLog.action).where(AuditLog.object_id == b["id"])).all()
    assert "bookings.message_simulated" in audit
    log = api.get(tok, f"/workspaces/{ws}/bookings/messages/log?booking_id={b['id']}").json()["items"]
    assert [(x["variant"], x["status"]) for x in log] == [("confirmed", "simulated")] and "recipient" not in log[0]


def test_sms_only_after_the_business_turns_it_on(api, client, fake, db):
    tok, ws, tid = _setup(api, client, "e07a-sms")
    slots = _slots(api, tok, ws, tid)
    m = api.get(tok, f"/workspaces/{ws}/bookings/messages").json()
    assert m["sending"]["sms_enabled"] is False and m["sending"]["email"] is True and m["sending"]["reminder_hours"] == 24
    _book(api, tok, ws, tid, slots[0], email=None)
    _drain()
    assert fake.sms == [] and _rows(db) == []  # phone only and SMS off: nothing at all
    out = _sms_on(api, tok, ws)
    assert out["sms_enabled"] is True
    assert db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == "bookings.message_settings_updated")) == 1
    b = _book(api, tok, ws, tid, slots[1], email="bo@kunde.dk", name="Bo Jensen")
    _drain()
    assert len(fake.sms) == 1 and fake.sms[0]["to"] == PHONE
    assert fake.sms[0]["body"].startswith("Hej Bo. Din tid hos Fjord Gulvservice ApS er bekræftet")
    rows = _rows(db, b["id"])
    assert sorted((r.channel, r.status, r.segments) for r in rows) == [("email", "simulated", None), ("sms", "simulated", 1)]
    # a reader cannot change it
    rtok = api.user("e07a-reader@testmail.dk")
    assert api.put(rtok, f"/workspaces/{ws}/bookings/messages/settings", {"sms_enabled": False}).status_code in (403, 404)
    _sms_on(api, tok, ws, False)
    _book(api, tok, ws, tid, slots[2], email=None, name="Ane")
    _drain()
    assert len(fake.sms) == 1


def test_one_message_per_event_and_channel_also_on_redelivery(api, client, fake, db):
    tok, ws, tid = _setup(api, client, "e07a-idem")
    _sms_on(api, tok, ws)
    b = _book(api, tok, ws, tid, _slots(api, tok, ws, tid)[0])
    _drain()
    assert len(_mails(db, "mette@kunde.dk")) == 1 and len(fake.sms) == 1
    booking = db.get(Booking, uuid.UUID(b["id"]))
    notify.queue(db, booking, "created")  # the same event again
    notify.queue(db, booking, "confirmed")  # «confirmed» for the same time is the same message
    db.commit()
    _drain()
    # every outbox event delivered again (a crashed worker, a replay): handlers are no-ops
    db.execute(OutboxEvent.__table__.update().where(OutboxEvent.event_type.in_(("booking.event", "booking.message")))
               .values(status="queued", next_attempt_at=datetime.now(UTC) - timedelta(seconds=1)))
    db.commit()
    _drain()
    assert len(_mails(db, "mette@kunde.dk")) == 1 and len(fake.sms) == 1
    assert len([r for r in _rows(db, b["id"]) if r.audience == "customer"]) == 2


def test_a_crashed_sms_send_is_never_repeated(api, client, fake, db):
    tok, ws, tid = _setup(api, client, "e07a-crash")
    _sms_on(api, tok, ws)
    b = _book(api, tok, ws, tid, _slots(api, tok, ws, tid)[0], email=None)
    ev = None
    while ev is None:  # process until booking.event has queued the SMS message (not yet sent)
        assert runner.process_once() is not None
        db.expire_all()
        ev = db.scalar(select(OutboxEvent).where(OutboxEvent.event_type == "booking.message"))
    db.add(BookingMessage(workspace_id=ev.workspace_id, booking_id=uuid.UUID(b["id"]), outbox_event_id=ev.id,
                          event_key=ev.payload["event_key"], variant="confirmed", audience="customer", channel="sms",
                          recipient=PHONE, lang="da", starts_at=datetime.fromisoformat(ev.payload["starts_at"]),
                          status="sending"))  # what a worker that died during the provider call leaves behind
    db.commit()
    _drain()
    assert fake.sms == []
    row = _rows(db, b["id"])[0]
    assert row.status == "failed" and "uvist" in row.error
    # the owner is told («levering fejlede»)
    owner = _mails(db, "e07a-crash@testmail.dk")
    assert [m.subject for m in owner if "kunne ikke leveres" in m.subject] == ["En besked til Mette Nielsen kunne ikke leveres"]


# --------------------------------------------------------------------------- moved / cancelled / awaiting confirmation

def test_moved_and_cancelled_messages(api, client, fake, db):
    tok, ws, tid = _setup(api, client, "e07a-move")
    _sms_on(api, tok, ws)
    slots = _slots(api, tok, ws, tid)
    b = _book(api, tok, ws, tid, slots[0])
    _drain()
    booking = db.get(Booking, uuid.UUID(b["id"]))
    w = db.get(Workspace, uuid.UUID(ws))
    bookings.move(db, w, booking, start=slots[3], tz="Europe/Copenhagen")
    db.commit()
    _drain()
    old_label = bookings.label(datetime.fromisoformat(slots[0]), "Europe/Copenhagen")
    new_label = bookings.label(datetime.fromisoformat(slots[3]), "Europe/Copenhagen")
    moved = _mails(db, "mette@kunde.dk")[-1]
    assert moved.subject == "Din tid er flyttet – Fjord Gulvservice ApS"
    assert f"fra {old_label} til {new_label}" in moved.body_text
    assert "er flyttet til" in fake.sms[-1]["body"] and new_label in fake.sms[-1]["body"]
    assert api.post(tok, f"/workspaces/{ws}/bookings/{b['id']}/cancel", {}).status_code == 200
    _drain()
    assert _mails(db, "mette@kunde.dk")[-1].subject == "Din tid er aflyst – Fjord Gulvservice ApS"
    assert "er aflyst" in fake.sms[-1]["body"]
    assert [r.variant for r in _rows(db, b["id"]) if r.channel == "email"] == ["confirmed", "rescheduled", "cancelled"]
    assert len(fake.sms) == 3
    # a cancelled booking's time is never reminded
    assert notify.run_reminders(db, now=datetime.fromisoformat(slots[3]) - timedelta(hours=20)) == 0


def test_calendar_unreadable_request_receipt_owner_attention_then_confirmed(api, client, fake, db, monkeypatch):
    tok, ws, tid = _setup(api, client, "e07a-pending", calendar=True)
    slot = _slots(api, tok, ws, tid)[0]

    def boom(self, frm, to):
        raise ActionError("calendar: freeBusy svarede ikke (simuleret)", code="provider_unavailable", retryable=True)

    with monkeypatch.context() as m:
        m.setattr(fakes.FakeCalendarClient, "busy", boom)
        b = _book(api, tok, ws, tid, slot)
    assert b["confirmation"] == "pending"
    _drain()
    assert [x.subject for x in _mails(db, "mette@kunde.dk")] == ["Vi har modtaget din forespørgsel – Fjord Gulvservice ApS"]
    owner = [x for x in _mails(db, "e07a-pending@testmail.dk") if "opmærksomhed" in x.subject]
    assert [x.subject for x in owner] == ["En aftale kræver din opmærksomhed – Mette Nielsen"]
    assert "skal bekræftes af en medarbejder" in owner[0].body_text
    assert api.post(tok, f"/workspaces/{ws}/bookings/{b['id']}/confirm", {}).status_code == 200
    _drain()
    assert [x.subject for x in _mails(db, "mette@kunde.dk")][-1] == "Din tid er bekræftet – Fjord Gulvservice ApS"
    assert len([x for x in _mails(db, "e07a-pending@testmail.dk") if "opmærksomhed" in x.subject]) == 1


def test_calendar_write_failure_owner_attention_and_confirmed_once_written(api, client, fake, db, monkeypatch):
    tok, ws, tid = _setup(api, client, "e07a-calfail", calendar=True)
    slot = _slots(api, tok, ws, tid)[0]

    def broken(self, **kw):
        raise ActionError("calendar: leverandøren svarede ikke (simuleret)", code="provider_unavailable", retryable=True)

    with monkeypatch.context() as m:
        m.setattr(fakes.FakeCalendarClient, "create_event", broken)
        b = _book(api, tok, ws, tid, slot)
    _drain()
    assert [x.subject for x in _mails(db, "mette@kunde.dk")] == ["Vi har modtaget din forespørgsel – Fjord Gulvservice ApS"]
    owner = [x for x in _mails(db, "e07a-calfail@testmail.dk") if "opmærksomhed" in x.subject]
    assert len(owner) == 1 and "kunne ikke skrives i jeres kalender" in owner[0].body_text
    # the calendar is written later (M03 «genkør» uses the same mirror path): now the customer gets the confirmation
    from app.modules.integrations.connectors import calendar

    booking = db.get(Booking, uuid.UUID(b["id"]))
    assert calendar.mirror_update(db, booking.workspace_id, booking) is True
    db.commit()
    _drain()
    assert [x.subject for x in _mails(db, "mette@kunde.dk")][-1] == "Din tid er bekræftet – Fjord Gulvservice ApS"
    assert len(_mails(db, "mette@kunde.dk")) == 2


# --------------------------------------------------------------------------- blocked / unsubscribed

def test_unsubscribe_link_stops_emails_for_that_business_only(api, client, fake, db):
    tok, ws, tid = _setup(api, client, "e07a-unsub")
    slots = _slots(api, tok, ws, tid)
    b = _book(api, tok, ws, tid, slots[0])
    _drain()
    link = re.search(r"(http\S+/api/v1/public/booking-messages/unsubscribe/\S+)", _mails(db, "mette@kunde.dk")[0].body_text).group(1)
    path = urlparse(link).path
    page = client.get(path)
    assert page.status_code == 200 and "Afmeld e-mails om aftaler" in page.text and "<form method=\"post\"" in page.text
    assert db.scalar(select(func.count()).select_from(CustomerMessageSuppression)) == 0  # opening the link is not enough
    assert client.get(path[:-3] + "xyz").status_code == 404 and client.post(path[:-3] + "xyz").status_code == 404
    done = client.post(path)
    assert done.status_code == 200 and "Du er afmeldt" in done.text
    assert client.post(path).status_code == 200  # idempotent
    assert db.scalar(select(func.count()).select_from(CustomerMessageSuppression)) == 1
    assert db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == "bookings.messages_unsubscribed")) == 1
    assert api.post(tok, f"/workspaces/{ws}/bookings/{b['id']}/cancel", {}).status_code == 200
    _book(api, tok, ws, tid, slots[2])
    _drain()
    assert len(_mails(db, "mette@kunde.dk")) == 1  # nothing more to this address from this business
    assert {r.skip_reason for r in _rows(db) if r.status == "skipped"} == {"unsubscribed"}
    # another business still writes to the same address (the opt-out is per business)
    tok2, ws2, tid2 = _setup(api, client, "e07a-unsub2", name="Havnebord Café")
    _book(api, tok2, ws2, tid2, _slots(api, tok2, ws2, tid2)[0])
    _drain()
    assert _mails(db, "mette@kunde.dk")[-1].subject == "Din tid er bekræftet – Havnebord Café"


def test_number_on_the_spaerreliste_gets_no_sms(api, client, fake, db):
    tok, ws, tid = _setup(api, client, "e07a-dnc")
    _sms_on(api, tok, ws)
    db.add(DoNotCall(workspace_id=uuid.UUID(ws), phone=PHONE, source="manual"))
    db.commit()
    _book(api, tok, ws, tid, _slots(api, tok, ws, tid)[0])
    _drain()
    assert fake.sms == []
    assert [(r.channel, r.status, r.skip_reason) for r in _rows(db) if r.channel == "sms"] == [("sms", "skipped", "blocked")]
    assert len(_mails(db, "mette@kunde.dk")) == 1  # the e-mail still goes


def test_sms_failure_retries_then_tells_the_owner(api, client, fake, db, monkeypatch):
    tok, ws, tid = _setup(api, client, "e07a-fail")
    _sms_on(api, tok, ws)

    def down(**kw):
        raise ActionError("sms: leverandøren svarede ikke (simuleret)", code="provider_unavailable", retryable=True)

    monkeypatch.setattr(fakes, "fake_send_sms", down)
    b = _book(api, tok, ws, tid, _slots(api, tok, ws, tid)[0], email=None)
    for _ in range(12):  # the worker's retries (backoff skipped)
        db.execute(OutboxEvent.__table__.update().where(OutboxEvent.status == "queued")
                   .values(next_attempt_at=datetime.now(UTC) - timedelta(seconds=1)))
        db.commit()
        _drain()
    row = _rows(db, b["id"])[0]
    assert row.status == "failed" and "simuleret" in row.error
    ev = db.get(OutboxEvent, row.outbox_event_id)
    assert ev.attempts == ev.max_attempts and ev.status == "done"
    owner = [x for x in _mails(db, "e07a-fail@testmail.dk") if "kunne ikke leveres" in x.subject]
    assert len(owner) == 1 and "«Aftale bekræftet»" in owner[0].body_text and "(SMS)" in owner[0].body_text


def test_bounced_customer_email_tells_the_owner_and_complaint_unsubscribes(api, client, fake, db):
    tok, ws, tid = _setup(api, client, "e07a-bounce")
    _book(api, tok, ws, tid, _slots(api, tok, ws, tid)[0])
    _drain()
    rec = _mails(db, "mette@kunde.dk")[0]
    notify.on_email_problem(db, rec, "complained")
    db.commit()
    _drain()
    assert db.scalar(select(func.count()).select_from(CustomerMessageSuppression)) == 1
    assert [r.status for r in _rows(db) if r.audience == "customer"] == ["failed"]
    assert any("kunne ikke leveres" in x.subject for x in _mails(db, "e07a-bounce@testmail.dk"))


# --------------------------------------------------------------------------- reminder timing

def _aged(db, b: dict, days: int = 3) -> Booking:
    booking = db.get(Booking, uuid.UUID(b["id"]))
    booking.created_at = datetime.now(UTC) - timedelta(days=days)
    db.commit()
    return booking


def test_reminder_24_hours_before_in_business_hours_once(api, client, fake, db):
    tok, ws, tid = _setup(api, client, "e07a-remind")
    slots = [s for s in _slots(api, tok, ws, tid) if datetime.fromisoformat(s).astimezone(CPH).hour == 10]
    b = _book(api, tok, ws, tid, slots[0])
    _drain()
    booking = _aged(db, b)
    start = booking.starts_at
    assert notify.run_reminders(db, now=start - timedelta(hours=25)) == 0  # too early
    assert notify.run_reminders(db, now=start - timedelta(hours=24)) == 1  # 10:00 the day before: open
    assert notify.run_reminders(db, now=start - timedelta(hours=23)) == 0  # idempotent
    with pytest.MonkeyPatch.context() as m:
        m.setattr(notify, "_now", lambda: start - timedelta(hours=23))
        _drain()
    mails = _mails(db, "mette@kunde.dk")
    assert [x.subject for x in mails][-1].startswith("Påmindelse: din tid ")
    assert len([r for r in _rows(db, b["id"]) if r.variant == "reminder"]) == 1


def test_reminder_waits_for_opening_hours_and_skips_late_or_fresh_bookings(api, client, fake, db):
    # open Monday–Saturday 09–17: a Monday 12:00 appointment is due on Sunday 12:00, when the shop is closed – the
    # reminder waits until Monday 09:00 (three hours before)
    tok, ws, tid = _setup(api, client, "e07a-window", hours=("09:00", "17:00"), days=ALL_DAYS[:6])
    slots = _slots(api, tok, ws, tid)
    monday = next(s for s in slots if datetime.fromisoformat(s).astimezone(CPH).weekday() == 0
                  and datetime.fromisoformat(s).astimezone(CPH).hour == 12)
    b = _book(api, tok, ws, tid, monday)
    start = _aged(db, b).starts_at
    assert notify.run_reminders(db, now=start - timedelta(hours=24)) == 0  # Sunday 12:00: closed
    assert notify.run_reminders(db, now=start - timedelta(hours=3, minutes=1)) == 0  # Monday 08:59
    assert notify.run_reminders(db, now=start - timedelta(hours=3)) == 1  # Monday 09:00
    # booked less than 24 hours before the start: no reminder (the confirmation was just sent)
    other = next(s for s in slots if s != monday and datetime.fromisoformat(s).astimezone(CPH).hour == 13)
    b3 = _book(api, tok, ws, tid, other)
    s3 = datetime.fromisoformat(b3["starts_at"])
    db.get(Booking, uuid.UUID(b3["id"])).created_at = s3 - timedelta(hours=10)
    db.commit()
    assert notify.run_reminders(db, now=s3 - timedelta(hours=5)) == 0
    # less than two hours before the start: too late
    db.get(Booking, uuid.UUID(b3["id"])).created_at = s3 - timedelta(days=3)
    db.commit()
    assert notify.run_reminders(db, now=s3 - timedelta(minutes=110)) == 0
    assert notify.run_reminders(db, now=s3 - timedelta(hours=4)) == 1


def test_reminder_fallback_window_pending_and_moved_booking(api, client, fake, db):
    # no opening hours: 08–21 local time (a manual booking needs none)
    tok, ws, tid = _setup(api, client, "e07a-fallback", hours=None)
    assert not any(bookings.weekly_hours(db, uuid.UUID(ws)).values())
    day = (datetime.now(CPH) + timedelta(days=3)).replace(hour=10, minute=0, second=0, microsecond=0)
    b = _book(api, tok, ws, tid, day.isoformat())
    booking = _aged(db, b)
    start = booking.starts_at
    late = start.astimezone(CPH).replace(hour=21, minute=30) - timedelta(days=1)
    assert notify.run_reminders(db, now=late) == 0  # 21:30: outside 08–21
    booking.confirmation = "pending"
    db.commit()
    assert notify.run_reminders(db, now=start - timedelta(hours=23)) == 0  # awaiting confirmation: no reminder
    booking.confirmation = None
    db.commit()
    assert notify.run_reminders(db, now=start - timedelta(hours=23)) == 1  # 11:00 the day before
    # the booking moves away from that time before the worker gets to the event: nothing is sent for the old time
    booking.starts_at, booking.ends_at = start + timedelta(days=1), booking.ends_at + timedelta(days=1)
    db.commit()
    with pytest.MonkeyPatch.context() as m:
        m.setattr(notify, "_now", lambda: start - timedelta(hours=23))
        _drain()
    assert [r for r in _rows(db, b["id"]) if r.variant == "reminder"] == []


# --------------------------------------------------------------------------- language, tenant isolation

def test_customer_language_is_the_business_language_owner_gets_his_own(api, client, fake, db, monkeypatch):
    tok, ws, tid = _setup(api, client, "e07a-lang", calendar=True)
    ls = db.get(LanguageSettings, uuid.UUID(ws))
    if ls is None:
        ls = LanguageSettings(workspace_id=uuid.UUID(ws))
        db.add(ls)
    ls.default_conversation_language = "de"
    db.scalar(select(User).where(User.email == "e07a-lang@testmail.dk")).interface_language = "en"
    db.commit()
    _sms_on(api, tok, ws)

    def broken(self, **kw):
        raise ActionError("calendar: leverandøren svarede ikke (simuleret)", code="provider_unavailable", retryable=True)

    monkeypatch.setattr(fakes.FakeCalendarClient, "create_event", broken)
    _book(api, tok, ws, tid, _slots(api, tok, ws, tid)[0])
    _drain()
    assert _mails(db, "mette@kunde.dk")[0].subject == "Wir haben Ihre Anfrage erhalten – Fjord Gulvservice ApS"
    assert "E-Mails zu Terminen von Fjord Gulvservice ApS abbestellen" in _mails(db, "mette@kunde.dk")[0].body_text
    assert fake.sms[0]["body"].endswith("Freundliche Grüße, Fjord Gulvservice ApS")
    owner = [x for x in _mails(db, "e07a-lang@testmail.dk") if "attention" in x.subject]
    assert [x.subject for x in owner] == ["A booking needs your attention – Mette Nielsen"]
    assert {r.lang for r in _rows(db)} == {"de", "en"}


def test_tenant_isolation(api, client, fake, db):
    tok, ws, tid = _setup(api, client, "e07a-ten-a")
    tok2, ws2, _ = _setup(api, client, "e07a-ten-b", name="Havnebord Café")
    b = _book(api, tok, ws, tid, _slots(api, tok, ws, tid)[0])
    _drain()
    # an event that names another workspace's booking does nothing
    from app.core.outbox import enqueue

    enqueue(db, event_type="booking.event", dedupe_key="test-cross", workspace_id=uuid.UUID(ws2),
            payload={"booking_id": b["id"], "event": "cancelled", "starts_at": b["starts_at"]})
    db.commit()
    _drain()
    assert len(_mails(db, "mette@kunde.dk")) == 1 and all(r.workspace_id == uuid.UUID(ws) for r in _rows(db))
    assert api.get(tok2, f"/workspaces/{ws2}/bookings/messages/log").json()["items"] == []
    assert api.get(tok2, f"/workspaces/{ws}/bookings/messages/log").status_code in (403, 404)
    assert api.put(tok2, f"/workspaces/{ws}/bookings/messages/settings", {"sms_enabled": True}).status_code in (403, 404)

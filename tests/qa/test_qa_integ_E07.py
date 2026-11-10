"""QA E07 (integrations-qa): booking communication templates.

Krav E07: "Request receipt, confirmed appointment, reminder, proposed change, rescheduled, cancelled and
owner-attention variants; delivery failure." DB-018: real external capability cannot be inferred from a demo.

What the code has today (proved below with CONNECTORS_PROVIDER=fake, nothing leaves the process):
- ONE customer message: the SMS template `booking` ("Din tid hos …"), sent only when the assistant (or a person on
  Integrationer) calls send_sms_bekraeftelse. Nothing is sent by the booking itself.
- After a move, the same template carries the new time; after a cancel no message is possible (no_booking).
- No reminder, no proposed-change, no cancellation message, no owner-attention message, no request receipt; no
  e-mail to the customer at all (even when the booking has contact_email). Delivery failure = the action run is
  'failed' with the reason (SMS accepted by Twilio is labelled «SMS sendt»; there is no delivery receipt).
The requirement test at the bottom is xfail(strict): E07 is not implemented.
"""
from __future__ import annotations

from datetime import UTC, datetime
from urllib.parse import urlparse

import pytest
from sqlalchemy import select

from app.config import get_settings
from app.models import Booking, OutboxEvent
from app.modules.integrations.connectors.fakes import WORLD
from app.worker import runner

PHONE = "+4522334455"


@pytest.fixture
def fake(monkeypatch):
    monkeypatch.setenv("CONNECTORS_PROVIDER", "fake")
    monkeypatch.delenv("TELEPHONY_PROVIDER", raising=False)
    get_settings.cache_clear()
    WORLD.reset()
    yield WORLD
    WORLD.reset()
    get_settings.cache_clear()


def _ready(api, client, tag: str):
    tok = api.user(f"{tag}@testmail.dk")
    ws = api.workspace(tok, "Fjord Gulvservice ApS")
    hours = api.knowledge(tok, ws, "opening_hours", "Åbningstider",
                          {"weekly": [{"days": ["mon", "tue", "wed", "thu", "fri", "sat", "sun"], "open": "08:00",
                                       "close": "20:00"}]})
    api.submit(tok, ws, hours["open_draft"]["id"])
    assert api.approve(tok, ws, hours["open_draft"]["id"]).status_code == 200
    assert api.post(tok, f"/workspaces/{ws}/bookings/types", {"name": "Besigtigelse", "duration_minutes": 60}).status_code == 201
    s = api.get(tok, f"/workspaces/{ws}/bookings/settings").json()
    assert api.put(tok, f"/workspaces/{ws}/bookings/settings",
                   {"enabled": True, "lead_time_hours": 0, "horizon_days": 7, "buffer_minutes": 0,
                    "expected_version": s["version"]}).status_code == 200
    r = api.post(tok, f"/workspaces/{ws}/integrations/google_calendar/connect", {"config": {}, "secrets": {}})
    url = urlparse(r.json()["authorize_url"])
    assert "connected=google_calendar" in client.get(url.path + "?" + url.query, follow_redirects=False).headers["location"]
    assert api.post(tok, f"/workspaces/{ws}/integrations/twilio_sms/connect", {"config": {}, "secrets": {}}).status_code == 200
    return tok, ws


def _run(api, tok, ws, key, action, inp):
    r = api.post(tok, f"/workspaces/{ws}/integrations/{key}/run", {"action": action, "input": inp})
    assert r.status_code == 200, r.text
    return r.json()


def _call(db, ws, name, args):
    """What the phone assistant does: one action in a call from PHONE (actions.execute, channel phone)."""
    import uuid as _uuid

    from app.models import Workspace
    from app.modules.integrations import actions
    from app.modules.integrations.connectors.base import RunContext

    w = db.get(Workspace, _uuid.UUID(ws))
    text, run = actions.execute(db, w, name, args, RunContext(workspace_id=w.id, channel="phone", caller_phone=PHONE))
    db.commit()
    return {"text": text, "run": {"status": run.status, "error": run.error, "output": run.output,
                                  "simulated": run.simulated}}


def _mail_subjects(api, tok) -> list[str]:
    runner.drain()
    return [m["subject"] for m in api.get(tok, "/dev/mailbox").json()["items"]]


def test_e07_inventory_of_booking_messages(api, client, fake, db):
    tok, ws = _ready(api, client, "e07-inv")
    mails_before = _mail_subjects(api, tok)
    slots = _call(db, ws, "ledige_tider", {})["run"]["output"]["tider"]
    assert len(slots) >= 2
    booked = _call(db, ws, "book_tid", {"start": slots[0]["start"], "navn": "Mette Nielsen", "bekraeftet": True})
    assert booked["run"]["status"] == "ok" and booked["run"]["simulated"] is True
    # 1) The booking itself sends nothing to the customer; exactly one calendar event is written.
    assert fake.sms == [] and len(fake.events) == 1
    rows = [(x.contact_phone, x.source, x.status) for x in db.scalars(select(Booking))]
    assert rows == [(PHONE, "phone", "confirmed")], (rows, booked)
    new_mails = [s for s in _mail_subjects(api, tok) if s not in mails_before]
    assert all("Fjord" in s or "henvendelse" in s.lower() for s in new_mails), new_mails  # owner: new-lead mail only
    # 2) «Confirmed appointment»: the SMS template, on request only, in Danish, with the booked time and no price.
    sms = _call(db, ws, "send_sms_bekraeftelse", {"skabelon": "booking"})
    assert sms["run"]["status"] == "ok" and len(fake.sms) == 1 and fake.sms[0]["to"] == PHONE
    body = fake.sms[0]["body"]
    assert body.startswith("Hej Mette") and "Fjord Gulvservice ApS" in body and "Besigtigelse" in body
    assert slots[0]["tekst"].split(" kl.")[0].lower() in body.lower() or "kl." in body
    assert "kr" not in body.lower()
    # 3) «Rescheduled»: moving sends nothing by itself; the same template then carries the new time.
    moved = _call(db, ws, "flyt_tid", {"ny_start": slots[1]["start"], "bekraeftet": True})
    assert moved["run"]["status"] == "ok" and len(fake.sms) == 1
    ev = next(iter(fake.events.values()))
    assert ev["start"] == datetime.fromisoformat(slots[1]["start"]).astimezone(UTC)
    _call(db, ws, "send_sms_bekraeftelse", {"skabelon": "booking"})
    assert moved["run"]["output"]["tidspunkt"] in fake.sms[-1]["body"]
    # 4) «Cancelled»: no message is sent and none can be: the template has no cancelled variant.
    cancelled = _call(db, ws, "aflys_tid", {"bekraeftet": True})
    assert cancelled["run"]["status"] == "ok" and fake.events == {}
    after = _call(db, ws, "send_sms_bekraeftelse", {"skabelon": "booking"})
    assert after["run"]["status"] == "refused" and len(fake.sms) == 2
    # 5) No reminder or customer e-mail is ever queued for a booking.
    types = set(db.scalars(select(OutboxEvent.event_type)))
    assert not {t for t in types if "remind" in t or t.startswith("email.booking")}, types
    assert not [h for h in runner.HANDLERS if "booking" in h]


def test_e07_delivery_failure_and_owner_attention(api, client, fake, db, monkeypatch):
    tok, ws = _ready(api, client, "e07-fail")
    slots = _run(api, tok, ws, "google_calendar", "ledige_tider", {})["run"]["output"]["tider"]
    # Calendar write fails: the booking stands in Dialogbot, the connection shows the error (owner sees it on
    # Integrationer) – but no message tells the owner (no owner-attention variant).
    from app.modules.integrations.connectors import fakes
    from app.modules.integrations.connectors.base import ActionError

    def broken_create(self, **kw):
        raise ActionError("calendar: leverandøren svarede ikke (simuleret)", code="provider_unavailable", retryable=True)

    monkeypatch.setattr(fakes.FakeCalendarClient, "create_event", broken_create)
    before = _mail_subjects(api, tok)
    r = _call(db, ws, "book_tid", {"start": slots[0]["start"], "navn": "Jens Poulsen", "bekraeftet": True})
    # Since c3bed12 (F-EB-05): the action is reported as failed so the assistant does not promise the time, but the
    # booking stands in Dialogbot, flagged calendar_sync='failed' for the owner.
    assert r["run"]["status"] == "failed", r
    assert "Booket" not in r["text"] and "kalender" in (r["run"]["error"] or "").lower(), r
    db.expire_all()
    b = db.scalar(select(Booking).where(Booking.contact_phone == PHONE))
    assert b is not None and b.calendar_event_id is None and b.calendar_sync == "failed", b
    g = {i["key"]: i for i in api.get(tok, f"/workspaces/{ws}/integrations").json()["items"]}["google_calendar"]
    assert g["status"] == "error" and "Kalenderen kunne ikke opdateres" in (g["error"] or "")
    owner_mails = [s for s in _mail_subjects(api, tok) if s not in before]
    assert not [s for s in owner_mails if "kalender" in s.lower()], owner_mails  # documents: no owner-attention mail
    # SMS delivery failure: the run is 'failed' with the reason and the assistant is told to say so.
    fake.fail_next.add("sms")
    f = _call(db, ws, "send_sms_bekraeftelse", {"skabelon": "booking"})
    assert f["run"]["status"] == "failed" and "simuleret" in f["run"]["error"]
    assert f["text"].startswith("Handlingen fejlede") and fake.sms == []


E07_VARIANTS = ("request_receipt", "confirmed", "reminder", "proposed_change", "rescheduled", "cancelled",
                "owner_attention", "delivery_failure")


@pytest.mark.xfail(strict=True, reason="E07: not-implemented – only the on-demand SMS 'booking' template exists")
def test_e07_requirement_all_booking_message_variants_exist():
    from app.modules.integrations import email_templates, sms_templates

    sms_keys = set(sms_templates.__dict__.get("TEXTS", {}).get("da", {})) if hasattr(sms_templates, "TEXTS") else set()
    mail_keys = set(email_templates.samples())
    have = {v for v in E07_VARIANTS if any(v in k for k in sms_keys | mail_keys)}
    assert have == set(E07_VARIANTS), f"missing: {sorted(set(E07_VARIANTS) - have)}"

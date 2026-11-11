"""S0 «Erhverv døgnåbent»: the calling hours (SALES_CALL_FROM/SALES_CALL_TO) never block anything.

Outside the hours a request for a demo call is queued for the next opening with an honest consent text, the visitor
is told when Peter rings and may sign up at once; the worker dials the queue when the hours open. The hours are read
correctly whatever their values (a window over midnight, or from == to = always open). The website chat points to
the self-service sign-up when the visitor wants to buy, sign up, know the price or get started."""
from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest

from app.config import get_settings
from app.models import DemoCall
from app.modules.ai import service as ai
from app.modules.sales import service
from tests.test_sales_demo_calls import SECRET, _web, sales  # noqa: F401 – the fixture

CPH = ZoneInfo("Europe/Copenhagen")
WED_2130 = datetime(2026, 11, 11, 21, 30, tzinfo=CPH).astimezone(UTC)
THU_0300 = datetime(2026, 11, 12, 3, 0, tzinfo=CPH).astimezone(UTC)
THU_0800 = datetime(2026, 11, 12, 8, 0, tzinfo=CPH).astimezone(UTC)
THU_0805 = datetime(2026, 11, 12, 8, 5, tzinfo=CPH).astimezone(UTC)


@pytest.mark.parametrize("now, when", [(WED_2130, "tomorrow"), (THU_0300, "today")])
def test_outside_hours_nothing_blocks_and_the_call_is_queued(client, sales, db, now, when):  # noqa: F811
    sales["clock"][0] = now
    info = client.get("/api/v1/demo-call").json()
    assert info["available"] is True and info["open_now"] is False
    assert info["next_open"] == THU_0800.isoformat()  # «i morgen fra kl. 8» at 21:30, «i dag fra kl. 8» at 03:00
    # the consent shown outside the hours says when Peter rings – never «nu»
    assert info["consent_version"] == service.CONSENT_VERSION_WEB_LATER
    assert "08:00" in info["consent_text"] and " nu " not in info["consent_text"]
    r = _web(client, name="Mette Hansen", company="Hansen Byg ApS", consent_version=info["consent_version"])
    assert r.status_code == 202, r.text
    assert r.json() == {"status": "scheduled", "scheduled_for": THU_0800.isoformat()}
    assert sales["calls"] == []  # nobody is rung at night
    d = db.query(DemoCall).one()
    assert (d.status, d.scheduled_for, d.consent_version) == ("scheduled", THU_0800, service.CONSENT_VERSION_WEB_LATER)
    assert "08:00" in d.consent_text
    # still the abuse limits: one request per number per day
    assert _web(client, consent_version=info["consent_version"]).json()["code"] == "demo_already_called"
    # the worker leaves the queue alone while the hours are closed …
    assert service.place_due(db) == 0 and sales["calls"] == []
    # … and rings when they open
    sales["clock"][0] = THU_0805
    assert service.place_due(db) == 1
    db.refresh(d)
    assert (d.status, d.provider_call_id) == ("calling", "demo_1")
    assert sales["calls"][0]["customer"]["number"] == "+4520304050"
    assert service.place_due(db) == 0  # once only


def test_a_now_consent_after_closing_is_not_used_for_a_later_call(client, sales, db):  # noqa: F811
    """The page was loaded at 19:59 («ring mig op nu»), the number sent at 20:01: not a dead end, but we ask for the
    consent that matches the time we will ring."""
    sales["clock"][0] = WED_2130
    r = _web(client, consent_version=service.CONSENT_VERSION_WEB)
    assert r.status_code == 409 and r.json()["code"] == "demo_consent_later"
    assert db.query(DemoCall).count() == 0 and sales["calls"] == []


def test_inside_hours_a_later_consent_rings_now(client, sales, db):  # noqa: F811
    sales["clock"][0] = THU_0805
    r = _web(client, consent_version=service.CONSENT_VERSION_WEB_LATER)
    assert r.status_code == 202 and r.json() == {"status": "calling"} and len(sales["calls"]) == 1


def test_do_not_call_stays_secret_outside_hours(client, sales, db):  # noqa: F811
    import uuid

    from app.models import DoNotCall

    db.add(DoNotCall(workspace_id=uuid.UUID(sales["ws"]), phone="+4520304050", source="call"))
    db.commit()
    sales["clock"][0] = WED_2130
    r = _web(client, consent_version=service.CONSENT_VERSION_WEB_LATER)
    assert r.json() == {"status": "scheduled", "scheduled_for": THU_0800.isoformat()}
    sales["clock"][0] = THU_0805
    assert service.place_due(db) == 0 and sales["calls"] == []


@pytest.mark.parametrize("frm, to, local, open_", [
    ("08:00", "20:00", (21, 30), False), ("08:00", "20:00", (3, 0), False), ("08:00", "20:00", (12, 0), True),
    ("20:00", "08:00", (21, 30), True), ("20:00", "08:00", (3, 0), True), ("20:00", "08:00", (12, 0), False),
    ("00:00", "00:00", (3, 0), True), ("08:00", "08:00", (21, 30), True),  # from == to: always open
    ("bad", "20:00", (21, 30), True),  # a broken value never closes the door
])
def test_hours_are_read_correctly_whatever_their_values(monkeypatch, frm, to, local, open_):
    monkeypatch.setenv("SALES_CALL_FROM", frm)
    monkeypatch.setenv("SALES_CALL_TO", to)
    get_settings.cache_clear()
    try:
        now = datetime(2026, 11, 11, *local, tzinfo=CPH).astimezone(UTC)
        assert service.in_hours(now) is open_
        nxt = service.next_open(now)
        assert (nxt == now) if open_ else (nxt > now and service.in_hours(nxt))
    finally:
        get_settings.cache_clear()


def test_chat_links_to_the_sign_up(client, sales, monkeypatch):  # noqa: F811
    seen: dict = {}
    real = ai.complete_logged

    def spy(db, ws, **kw):
        seen["instructions"] = kw.get("extra_instructions", "")
        return real(db, ws, **kw)

    monkeypatch.setattr(ai, "complete_logged", spy)
    sales["clock"][0] = WED_2130  # the chat answers at night too
    for q in ("Hvad koster det?", "Jeg vil gerne købe det", "Hvordan opretter jeg mig?", "Hvordan kommer vi i gang?"):
        r = client.post("/api/v1/demo-call/chat", json={"messages": [{"role": "user", "content": q}]})
        assert r.status_code == 200, r.text
        assert r.json()["signup_url"] == service.SIGNUP_PATH == "/signup?intent=reception", q
    # Peter is told to link to the sign-up, that it is open day and night, and that a call is never a condition
    assert "/signup?intent=reception" in seen["instructions"] and "døgnet rundt" in seen["instructions"]
    assert "aldrig en betingelse" in seen["instructions"]
    r = client.post("/api/v1/demo-call/chat", json={"messages": [{"role": "user", "content": "Kan den tale svensk?"}]})
    assert r.json()["signup_url"] is None  # no link pushed into an answer about something else


def test_a_queued_call_the_worker_missed_is_dropped_not_rung_late(client, sales, db):  # noqa: F811
    from datetime import timedelta

    sales["clock"][0] = WED_2130
    assert _web(client, consent_version=service.CONSENT_VERSION_WEB_LATER).json()["status"] == "scheduled"
    sales["clock"][0] = THU_0805 + timedelta(days=1)  # the worker was down until Friday morning
    assert service.place_due(db) == 0 and sales["calls"] == []
    assert db.query(DemoCall).one().status == "skipped"

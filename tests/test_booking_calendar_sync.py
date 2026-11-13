"""Bookings mirrored to a connected Google/Microsoft calendar from every path, with an honest sync state
(QA F-EB-04-W12, F-EB-05-BK15, F-EB-06-BK15)."""
from __future__ import annotations

import uuid
from urllib.parse import urlparse

import pytest

from app.config import get_settings
from app.core import safe_fetch
from app.models import Booking, IntegrationConnection
from app.modules.integrations.connectors import fakes
from app.modules.integrations.connectors.base import ActionError
from app.modules.integrations.connectors.fakes import WORLD
from tests.webchat_phone import prove_phone


@pytest.fixture
def fake(monkeypatch):
    monkeypatch.setattr(safe_fetch, "system_resolver", lambda host: ["93.184.216.34"])
    monkeypatch.setenv("CONNECTORS_PROVIDER", "fake")
    monkeypatch.setenv("AI_PROVIDER", "fake")
    get_settings.cache_clear()
    WORLD.reset()
    yield WORLD
    WORLD.reset()
    get_settings.cache_clear()


def _ready(api, client, t, *, connect: bool) -> str:
    tok, ws = t["tok_a"], t["ws_a"]
    hours = api.knowledge(tok, ws, "opening_hours", "Åbningstider",
                          {"weekly": [{"days": ["mon", "tue", "wed", "thu", "fri", "sat", "sun"], "open": "08:00", "close": "20:00"}]})
    api.submit(tok, ws, hours["open_draft"]["id"])
    api.approve(tok, ws, hours["open_draft"]["id"])
    typ = api.post(tok, f"/workspaces/{ws}/bookings/types", {"name": "Besigtigelse", "duration_minutes": 60}).json()
    s = api.get(tok, f"/workspaces/{ws}/bookings/settings").json()
    assert s["calendar_connection"] is None
    api.put(tok, f"/workspaces/{ws}/bookings/settings", {"enabled": True, "lead_time_hours": 0, "horizon_days": 7,
                                                         "buffer_minutes": 0, "expected_version": s["version"]})
    if connect:
        r = api.post(tok, f"/workspaces/{ws}/integrations/google_calendar/connect", {"config": {}, "secrets": {}})
        url = urlparse(r.json()["authorize_url"])
        assert client.get(f"{url.path}?{url.query}", follow_redirects=False).status_code == 303
    return typ["id"]


def test_without_calendar_nothing_is_mirrored(api, client, two_workspaces, fake):
    t = two_workspaces
    tok, ws = t["tok_a"], t["ws_a"]
    type_id = _ready(api, client, t, connect=False)
    start = api.get(tok, f"/workspaces/{ws}/bookings/slots?type_id={type_id}").json()["items"][0]["start"]
    b = api.post(tok, f"/workspaces/{ws}/bookings", {"type_id": type_id, "start": start, "name": "Mette"}).json()
    assert (b["calendar_sync"], b["calendar_event_id"]) == (None, None) and not WORLD.events


def test_manual_booking_and_cancel_are_mirrored_and_status_is_shown(api, client, two_workspaces, fake):
    t = two_workspaces
    tok, ws = t["tok_a"], t["ws_a"]
    type_id = _ready(api, client, t, connect=True)
    cal = api.get(tok, f"/workspaces/{ws}/bookings/settings").json()["calendar_connection"]
    assert cal["connector"] == "google_calendar" and cal["status"] == "connected" and cal["simulated"] is True
    start = api.get(tok, f"/workspaces/{ws}/bookings/slots?type_id={type_id}").json()["items"][0]["start"]
    b = api.post(tok, f"/workspaces/{ws}/bookings", {"type_id": type_id, "start": start, "name": "Mette"}).json()
    assert b["calendar_sync"] == "synced" and b["calendar_event_id"] in WORLD.events
    api.post(tok, f"/workspaces/{ws}/bookings/{b['id']}/cancel", {})
    assert b["calendar_event_id"] not in WORLD.events


def test_failed_mirror_is_flagged_not_hidden(api, client, two_workspaces, fake, db, monkeypatch):
    t = two_workspaces
    tok, ws = t["tok_a"], t["ws_a"]
    type_id = _ready(api, client, t, connect=True)

    def fail_create(self, **kw):
        raise ActionError("calendar: timeout (simuleret)", code="provider_unavailable", retryable=True)

    monkeypatch.setattr(fakes.FakeCalendarClient, "create_event", fail_create)
    start = api.get(tok, f"/workspaces/{ws}/bookings/slots?type_id={type_id}").json()["items"][0]["start"]
    r = api.post(tok, f"/workspaces/{ws}/bookings", {"type_id": type_id, "start": start, "name": "Mette"})
    assert r.status_code == 201
    b = r.json()
    assert b["calendar_sync"] == "failed" and "timeout" in b["calendar_sync_error"] and b["calendar_event_id"] is None
    cal = api.get(tok, f"/workspaces/{ws}/bookings/settings").json()["calendar_connection"]
    assert cal["status"] == "error" and cal["sync_failed"] == 1
    db.expire_all()
    assert db.get(Booking, uuid.UUID(b["id"])).calendar_sync == "failed"
    assert db.query(IntegrationConnection).filter_by(connector="google_calendar").one().status == "error"


# --------------------------------------------------------------------------- «afventer bekræftelse»
# Decision 2026-11-10 (Fürster) on F-EB-05-BK15: when the connected calendar's busy time cannot be read, free times
# still come from opening hours and Dialogbot's own bookings (fail-open), but every booking made then awaits a staff
# member's confirmation; the customer/caller never gets a final confirmation; the owner gets a task and confirms.

def _busy_down(monkeypatch):
    def boom(self, frm, to):
        raise ActionError("calendar: freeBusy svarede ikke (simuleret)", code="provider_unavailable", retryable=True)

    monkeypatch.setattr(fakes.FakeCalendarClient, "busy", boom)


def _widget(api, client, t):
    tok, ws = t["tok_a"], t["ws_a"]
    api.subscribe(tok, ws)  # the chat goes live only with a paid subscription
    wc = api.get(tok, f"/workspaces/{ws}/webchat").json()
    key = api.put(tok, f"/workspaces/{ws}/webchat", {"expected_version": wc["version"], "enabled": True,
                                                    "allowed_origins": ["https://fjord.dk"], "greeting": ""}).json()["widget_key"]
    frame = get_settings().public_base_url
    conv = client.post(f"/api/v1/public/webchat/{key}/conversations", json={"host_origin": "https://fjord.dk"},
                       headers={"origin": frame}).json()
    return key, conv["conversation_id"], {"origin": frame, "x-visitor-token": conv["visitor_token"]}


def _confirm_tasks(db, ws):
    from app.models import Task

    db.expire_all()
    return db.query(Task).filter(Task.workspace_id == uuid.UUID(ws), Task.title.startswith("Bekræft aftale")).all()


def test_calendar_down_widget_booking_awaits_confirmation_then_owner_confirms_and_it_is_mirrored(
        api, client, two_workspaces, fake, db, monkeypatch):
    t = two_workspaces
    tok, ws = t["tok_a"], t["ws_a"]
    type_id = _ready(api, client, t, connect=True)
    key, conv_id, h = _widget(api, client, t)
    with monkeypatch.context() as m:
        _busy_down(m)
        opts = client.get(f"/api/v1/public/webchat/{key}/booking").json()
        assert opts["slots"], "fail-open: free times still come from opening hours"
        prove_phone(client, key, conv_id, h, "+4520304050")
        r = client.post(f"/api/v1/public/webchat/{key}/conversations/{conv_id}/booking",
                        json={"type_id": type_id, "start": opts["slots"][0]["start"], "name": "Henrik Villumsen",
                              "phone": "+4520304050", "consent": True}, headers=h)
        assert r.status_code == 201, r.text
        assert r.json()["confirmation"] == "pending"  # the widget says «noteret – en medarbejder bekræfter»
    # nothing written to the calendar yet; the owner sees the label, the count and a task
    assert not WORLD.events
    items = api.get(tok, f"/workspaces/{ws}/bookings").json()["items"]
    assert [(b["confirmation"], b["calendar_sync"], b["calendar_event_id"]) for b in items] == [("pending", None, None)]
    cal = api.get(tok, f"/workspaces/{ws}/bookings/settings").json()["calendar_connection"]
    assert cal["pending_confirmation"] == 1 and cal["status"] == "error" and "Optaget tid" in cal["error"]
    tasks = _confirm_tasks(db, ws)
    assert len(tasks) == 1 and tasks[0].status == "open" and "Henrik Villumsen" in tasks[0].title
    # the calendar works again: the owner confirms → mirrored through the shared path, task done, connection ok
    c = api.post(tok, f"/workspaces/{ws}/bookings/{items[0]['id']}/confirm", {})
    assert c.status_code == 200, c.text
    out = c.json()
    assert out["confirmation"] == "confirmed" and out["calendar_sync"] == "synced" and out["calendar_event_id"] in WORLD.events
    assert [x.status for x in _confirm_tasks(db, ws)] == ["done"]
    assert api.get(tok, f"/workspaces/{ws}/bookings/settings").json()["calendar_connection"]["pending_confirmation"] == 0
    # confirming twice is harmless
    assert api.post(tok, f"/workspaces/{ws}/bookings/{items[0]['id']}/confirm", {}).json()["calendar_event_id"] == out["calendar_event_id"]
    assert len(WORLD.events) == 1


def test_confirm_shows_a_calendar_conflict_honestly(api, client, two_workspaces, fake, db, monkeypatch):
    t = two_workspaces
    tok, ws = t["tok_a"], t["ws_a"]
    type_id = _ready(api, client, t, connect=True)
    with monkeypatch.context() as m:
        _busy_down(m)
        start = api.get(tok, f"/workspaces/{ws}/bookings/slots?type_id={type_id}").json()["items"][0]["start"]
        b = api.post(tok, f"/workspaces/{ws}/bookings", {"type_id": type_id, "start": start, "name": "Mette"}).json()
    assert b["confirmation"] == "pending" and b["calendar_event_id"] is None
    # meanwhile the owner had something in Google at that time
    from datetime import datetime, timedelta

    st = datetime.fromisoformat(start)
    WORLD.events["owner"] = {"calendar": f"google_calendar:{ws}", "start": st + timedelta(minutes=30),
                             "end": st + timedelta(minutes=90), "title": "Tandlæge", "description": ""}
    r = api.post(tok, f"/workspaces/{ws}/bookings/{b['id']}/confirm", {})
    assert r.status_code == 409 and r.json()["code"] == "calendar_conflict" and "optaget tid" in r.json()["message"]
    assert len(r.json()["conflicts"]) == 1
    assert api.get(tok, f"/workspaces/{ws}/bookings").json()["items"][0]["confirmation"] == "pending"
    forced = api.post(tok, f"/workspaces/{ws}/bookings/{b['id']}/confirm", {"override_conflict": True}).json()
    assert forced["confirmation"] == "confirmed" and forced["calendar_sync"] == "synced"
    # a reader cannot confirm; another workspace cannot see it
    assert api.post(t["tok_b"], f"/workspaces/{ws}/bookings/{b['id']}/confirm", {}).status_code in (403, 404)


def test_cancelling_a_pending_booking_closes_the_task(api, client, two_workspaces, fake, db, monkeypatch):
    t = two_workspaces
    tok, ws = t["tok_a"], t["ws_a"]
    type_id = _ready(api, client, t, connect=True)
    with monkeypatch.context() as m:
        _busy_down(m)
        start = api.get(tok, f"/workspaces/{ws}/bookings/slots?type_id={type_id}").json()["items"][0]["start"]
        b = api.post(tok, f"/workspaces/{ws}/bookings", {"type_id": type_id, "start": start, "name": "Mette"}).json()
    api.post(tok, f"/workspaces/{ws}/bookings/{b['id']}/cancel", {})
    assert [x.status for x in _confirm_tasks(db, ws)] == ["done"] and not WORLD.events
    assert api.post(tok, f"/workspaces/{ws}/bookings/{b['id']}/confirm", {}).json()["code"] == "booking_cancelled"


def test_calendar_readable_books_as_before(api, client, two_workspaces, fake, db):
    t = two_workspaces
    tok, ws = t["tok_a"], t["ws_a"]
    type_id = _ready(api, client, t, connect=True)
    key, conv_id, h = _widget(api, client, t)
    start = client.get(f"/api/v1/public/webchat/{key}/booking").json()["slots"][0]["start"]
    prove_phone(client, key, conv_id, h, "+4520304050")
    r = client.post(f"/api/v1/public/webchat/{key}/conversations/{conv_id}/booking",
                    json={"type_id": type_id, "start": start, "name": "Henrik", "phone": "+4520304050", "consent": True},
                    headers=h)
    assert r.json()["confirmation"] == "confirmed"
    b = api.get(tok, f"/workspaces/{ws}/bookings").json()["items"][0]
    assert (b["confirmation"], b["calendar_sync"]) == (None, "synced") and b["calendar_event_id"] in WORLD.events
    assert _confirm_tasks(db, ws) == []


def test_assistant_book_tid_awaits_confirmation_and_never_confirms(api, client, two_workspaces, fake, db, monkeypatch):
    from app.models import ActionRun, Workspace
    from app.modules.integrations import actions
    from app.modules.integrations.connectors.base import RunContext

    t = two_workspaces
    _ready(api, client, t, connect=True)
    ws = db.get(Workspace, uuid.UUID(t["ws_a"]))
    ctx = RunContext(workspace_id=ws.id, channel="phone", caller_phone="+4520304050", provider_call_id="call-pending")
    _busy_down(monkeypatch)
    text, found = actions.execute(db, ws, "ledige_tider", {}, ctx)
    assert found.status == "ok" and found.output["tider"] and "bekræftes af en medarbejder" in text
    start = found.output["tider"][0]["start"]
    text, run = actions.execute(db, ws, "book_tid", {"start": start, "navn": "Mette Hansen", "bekraeftet": True}, ctx)
    db.commit()
    low = text.lower()
    assert run.status == "ok" and run.output["bekraeftelse"] == "afventer"
    assert "noteret" in low and "medarbejder" in low and "booket" not in low and "bekræft tiden over for kunden" not in low
    assert "afventer bekræftelse" in run.label
    b = db.query(Booking).one()
    assert b.confirmation == "pending" and b.calendar_event_id is None and not WORLD.events
    assert len(_confirm_tasks(db, str(ws.id))) == 1
    # moving it while the calendar is still down: still pending, never «er flyttet»
    text2, moved = actions.execute(db, ws, "flyt_tid", {"ny_start": found.output["tider"][2]["start"], "bekraeftet": True}, ctx)
    assert moved.status == "ok" and "er flyttet" not in text2.lower() and "noteret" in text2.lower()
    assert len(_confirm_tasks(db, str(ws.id))) == 1  # the same task, updated to the new time
    assert db.query(ActionRun).filter_by(workspace_id=ws.id, action="book_tid").one().status == "ok"


def test_connection_in_error_is_retried_and_recovers(api, client, two_workspaces, fake, db, monkeypatch):
    """A calendar marked `error` by an earlier failed read is read again (not skipped – that would book on opening
    hours only without anyone knowing); when it answers, booking is normal and the connection is ok again."""
    t = two_workspaces
    tok, ws = t["tok_a"], t["ws_a"]
    type_id = _ready(api, client, t, connect=True)
    with monkeypatch.context() as m:
        _busy_down(m)
        first = api.get(tok, f"/workspaces/{ws}/bookings/slots?type_id={type_id}").json()["items"][0]["start"]
        assert api.post(tok, f"/workspaces/{ws}/bookings", {"type_id": type_id, "start": first, "name": "Bo"}).json()["confirmation"] == "pending"
    assert api.get(tok, f"/workspaces/{ws}/bookings/settings").json()["calendar_connection"]["status"] == "error"
    start = api.get(tok, f"/workspaces/{ws}/bookings/slots?type_id={type_id}").json()["items"][0]["start"]
    b = api.post(tok, f"/workspaces/{ws}/bookings", {"type_id": type_id, "start": start, "name": "Mette"}).json()
    assert b["confirmation"] is None and b["calendar_sync"] == "synced"
    assert api.get(tok, f"/workspaces/{ws}/bookings/settings").json()["calendar_connection"]["status"] == "connected"


def test_calendar_down_is_recorded_by_a_read_only_slot_lookup(api, client, two_workspaces, fake, monkeypatch):
    """F-E2D-13-S03: a GET of free times (staff «Book for en kunde», the widget) never commits; the read error was
    rolled back and Integrationer kept saying «Forbundet». The status must stick – and clear again on the next good read."""
    t = two_workspaces
    tok, ws = t["tok_a"], t["ws_a"]
    type_id = _ready(api, client, t, connect=True)
    key, _conv, _h = _widget(api, client, t)
    with monkeypatch.context() as m:
        _busy_down(m)
        assert api.get(tok, f"/workspaces/{ws}/bookings/slots?type_id={type_id}").json()["items"]  # fail-open
        cal = api.get(tok, f"/workspaces/{ws}/integrations").json()
        g = next(i for i in (cal.get("items") or cal) if i.get("key", i.get("connector")) == "google_calendar")
        assert g["status"] == "error", g
    # the calendar answers again: the next look-up (the widget's, also a GET) clears it
    assert client.get(f"/api/v1/public/webchat/{key}/booking").status_code == 200
    s = api.get(tok, f"/workspaces/{ws}/bookings/settings").json()["calendar_connection"]
    assert s["status"] == "connected" and not s["error"], s


def test_recording_calendar_status_never_takes_a_second_pool_connection(api, client, two_workspaces, fake, monkeypatch):
    """F-E2D-13-S03 (reopened): the status was written through a second connection from the same pool while the
    request still held its own (hold-and-wait). With more concurrent look-ups than the pool during an outage (the
    widget's GET /booking is public) every API call got 500 «QueuePool limit … reached». With a pool of ONE
    connection a slot look-up during an outage must still answer 200 and record the error."""
    from sqlalchemy import create_engine

    import app.db as app_db

    t = two_workspaces
    tok, ws = t["tok_a"], t["ws_a"]
    type_id = _ready(api, client, t, connect=True)
    tiny = create_engine(get_settings().database_url, pool_size=1, max_overflow=0, pool_timeout=3, future=True)
    monkeypatch.setattr(app_db, "_engine", tiny)
    monkeypatch.setattr(app_db, "_session_factory", None)
    try:
        with monkeypatch.context() as m:
            _busy_down(m)
            r = api.get(tok, f"/workspaces/{ws}/bookings/slots?type_id={type_id}")
            assert r.status_code == 200 and r.json()["items"], r.text  # fail-open, no pool exhaustion
            assert tiny.pool.checkedout() == 0  # nothing left holding a connection
            with app_db.get_session_factory()() as s:
                g = s.query(IntegrationConnection).filter_by(connector="google_calendar").one()
                assert g.status == "error" and g.error.startswith("Optaget tid kunne ikke hentes"), (g.status, g.error)
    finally:
        tiny.dispose()

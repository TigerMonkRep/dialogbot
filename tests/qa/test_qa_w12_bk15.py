"""QA W12, W13, BK06, BK15 (e2e-erhverv B): public widget booking review, appointment management, calendar
connection honesty and sync/recovery – against the fake connector world (CONNECTORS_PROVIDER=fake).

W12: "Customer details, terms, edit, explicit submit, confirmed, pending, failed and slot-lost states."
W13: "Secure appointment management, verification where needed, reschedule/cancel, policy restrictions and
      invalid/expired links."
BK06: "Provider search, source identification, authorisation, other system/API, read-only feed and booking-link
       alternatives."  DB-018: real capability cannot be inferred from a demo or a button click.
BK15: "Sync health/history, external changes, duplicates, stale/uncertain actions and safe recovery."
DB-007/DB-011: no blind success; an unknown/failed external write must not be reported as done.
"""
from __future__ import annotations

import threading
import uuid
from datetime import datetime
from urllib.parse import urlparse

import pytest

from app.config import get_settings
from app.core import safe_fetch
from app.models import Booking, IntegrationConnection, Workspace
from app.modules.integrations import actions
from app.modules.integrations.connectors.base import RunContext
from app.modules.integrations.connectors.fakes import WORLD
from tests.webchat_phone import prove_phone

SECRET = "vapi-test-secret-0123456789abcdef"


@pytest.fixture
def fake(monkeypatch):
    monkeypatch.setattr(safe_fetch, "system_resolver", lambda host: ["93.184.216.34"])
    monkeypatch.setenv("CONNECTORS_PROVIDER", "fake")
    monkeypatch.setenv("AI_PROVIDER", "fake")
    monkeypatch.setenv("VAPI_SERVER_SECRET", SECRET)
    get_settings.cache_clear()
    WORLD.reset()
    yield WORLD
    WORLD.reset()
    get_settings.cache_clear()


def _booking_ready(api, t):
    tok, ws = t["tok_a"], t["ws_a"]
    hours = api.knowledge(tok, ws, "opening_hours", "Åbningstider",
                          {"weekly": [{"days": ["mon", "tue", "wed", "thu", "fri", "sat", "sun"], "open": "08:00", "close": "20:00"}]})
    api.submit(tok, ws, hours["open_draft"]["id"])
    api.approve(tok, ws, hours["open_draft"]["id"])
    typ = api.post(tok, f"/workspaces/{ws}/bookings/types", {"name": "Besigtigelse", "duration_minutes": 60}).json()
    s = api.get(tok, f"/workspaces/{ws}/bookings/settings").json()
    r = api.put(tok, f"/workspaces/{ws}/bookings/settings", {"enabled": True, "lead_time_hours": 0, "horizon_days": 7,
                                                              "buffer_minutes": 0, "expected_version": s["version"]})
    assert r.status_code == 200, r.text
    return typ["id"]


def _connect_google(api, client, t) -> None:
    r = api.post(t["tok_a"], f"/workspaces/{t['ws_a']}/integrations/google_calendar/connect", {"config": {}, "secrets": {}})
    assert r.status_code == 200, r.text
    url = r.json()["authorize_url"]
    back = client.get(urlparse(url).path + "?" + urlparse(url).query, follow_redirects=False)
    assert back.status_code == 303 and "connected=google_calendar" in back.headers["location"]


def _widget(api, client, t):
    tok, ws = t["tok_a"], t["ws_a"]
    api.subscribe(tok, ws)  # the chat goes live only with a paid subscription
    wc = api.get(tok, f"/workspaces/{ws}/webchat").json()
    r = api.put(tok, f"/workspaces/{ws}/webchat", {"expected_version": wc["version"], "enabled": True,
                                                  "allowed_origins": ["https://fjord.dk"], "greeting": ""})
    assert r.status_code == 200, r.text
    key = r.json()["widget_key"]
    frame = get_settings().public_base_url
    conv = client.post(f"/api/v1/public/webchat/{key}/conversations", json={"host_origin": "https://fjord.dk"},
                       headers={"origin": frame}).json()
    return key, conv["conversation_id"], {"origin": frame, "x-visitor-token": conv["visitor_token"]}


# --------------------------------------------------------------------------- W12

def test_w12_widget_booking_states(api, client, two_workspaces, fake, db):
    """Details + consent required, explicit submit, confirmed, slot lost; wrong visitor token denied."""
    t = two_workspaces
    type_id = _booking_ready(api, t)
    key, conv_id, h = _widget(api, client, t)
    opts = client.get(f"/api/v1/public/webchat/{key}/booking").json()
    url = f"/api/v1/public/webchat/{key}/conversations/{conv_id}/booking"
    body = {"type_id": type_id, "start": opts["slots"][0]["start"], "name": "Henrik Villumsen", "phone": "+4520304050", "consent": True}
    assert client.post(url, json=body | {"consent": False}, headers=h).status_code == 422
    assert client.post(url, json=body | {"phone": None}, headers=h).status_code == 422
    assert client.post(url, json=body, headers=h | {"x-visitor-token": "forkert"}).status_code in (401, 403, 404)
    assert client.post(url, json=body, headers={"x-visitor-token": h["x-visitor-token"], "origin": "https://evil.example"}).status_code in (400, 403)
    unproven = client.post(url, json=body, headers=h)  # W04 on the booking door (F-VER1113-04)
    assert unproven.status_code == 422 and unproven.json()["code"] == "verification_required", unproven.text
    prove_phone(client, key, conv_id, h, "+4520304050")
    ok = client.post(url, json=body, headers=h)
    assert ok.status_code == 201 and ok.json()["booked"] is True
    lost = client.post(url, json=body | {"name": "Anden"}, headers=h)
    assert lost.status_code == 409 and lost.json()["code"] == "slot_taken"
    assert db.query(Booking).filter(Booking.workspace_id == uuid.UUID(t["ws_a"])).count() == 1


def test_w12_concurrent_double_submit_books_once(api, client, two_workspaces, fake, db):
    t = two_workspaces
    type_id = _booking_ready(api, t)
    key, conv_id, h = _widget(api, client, t)
    start = client.get(f"/api/v1/public/webchat/{key}/booking").json()["slots"][1]["start"]
    url = f"/api/v1/public/webchat/{key}/conversations/{conv_id}/booking"
    body = {"type_id": type_id, "start": start, "name": "Dobbelt Klik", "phone": "+4520304051", "consent": True}
    prove_phone(client, key, conv_id, h, "+4520304051")
    codes: list[int] = []

    def go():
        codes.append(client.post(url, json=body, headers=h).status_code)

    threads = [threading.Thread(target=go) for _ in range(4)]
    [x.start() for x in threads]
    [x.join() for x in threads]
    assert sorted(codes).count(201) == 1, codes
    db.expire_all()
    assert db.query(Booking).filter(Booking.workspace_id == uuid.UUID(t["ws_a"]), Booking.status == "confirmed").count() == 1


def test_w12_widget_booking_reaches_connected_calendar(api, client, two_workspaces, fake, db):
    """With Google Kalender connected (description: 'opretter, flytter og aflyser aftaler direkte i den'),
    a booking the customer makes in the widget must end up in that calendar – or be shown as pending/failed.
    It must not stay silently only in Dialogbot while the owner's own calendar shows the time as free."""
    t = two_workspaces
    type_id = _booking_ready(api, t)
    _connect_google(api, client, t)
    key, conv_id, h = _widget(api, client, t)
    start = client.get(f"/api/v1/public/webchat/{key}/booking").json()["slots"][0]["start"]
    prove_phone(client, key, conv_id, h, "+4520304050")
    r = client.post(f"/api/v1/public/webchat/{key}/conversations/{conv_id}/booking",
                    json={"type_id": type_id, "start": start, "name": "Henrik Villumsen", "phone": "+4520304050", "consent": True},
                    headers=h)
    assert r.status_code == 201, r.text
    db.expire_all()
    b = db.query(Booking).filter(Booking.workspace_id == uuid.UUID(t["ws_a"])).one()
    google_events = [e for e in WORLD.events.values() if e["calendar"].startswith("google_calendar")]
    assert b.calendar_event_id is not None and len(google_events) == 1, (
        f"widget booking not written to connected Google calendar: calendar_connector={b.calendar_connector!r}, "
        f"calendar_event_id={b.calendar_event_id!r}, events in fake Google={len(google_events)}")


def test_w12_manual_booking_reaches_connected_calendar(api, client, two_workspaces, fake, db):
    """Same rule for «Book for en kunde» on /app/aftaler (POST /bookings)."""
    t = two_workspaces
    tok, ws = t["tok_a"], t["ws_a"]
    type_id = _booking_ready(api, t)
    _connect_google(api, client, t)
    start = api.get(tok, f"/workspaces/{ws}/bookings/slots?type_id={type_id}").json()["items"][0]["start"]
    r = api.post(tok, f"/workspaces/{ws}/bookings", {"type_id": type_id, "start": start, "name": "Mette", "phone": "+4520304050"})
    assert r.status_code == 201, r.text
    assert r.json()["calendar_event_id"] is not None, f"manual booking not written to Google: {r.json()}"


# --------------------------------------------------------------------------- W13 / BK15 (DB-007, DB-011)

def test_bk15_failed_external_move_is_not_reported_as_done(api, client, two_workspaces, fake, db, monkeypatch):
    """flyt_tid with the calendar provider failing: the customer must not be told 'Aftalen er flyttet' while the
    external event still sits at the old time, and the action trail must not say ok (DB-007/DB-011)."""
    t = two_workspaces
    _booking_ready(api, t)
    _connect_google(api, client, t)
    ws = db.get(Workspace, uuid.UUID(t["ws_a"]))
    ctx = RunContext(workspace_id=ws.id, channel="phone", caller_phone="+4520304050", provider_call_id="call-qa-eb")
    free = actions.execute(db, ws, "ledige_tider", {}, ctx)[1].output["tider"]
    _, booked = actions.execute(db, ws, "book_tid", {"start": free[0]["start"], "navn": "Bo", "bekraeftet": True}, ctx)
    assert booked.status == "ok"
    b = db.query(Booking).one()
    old_start = WORLD.events[b.calendar_event_id]["start"]
    from app.modules.integrations.connectors import fakes
    from app.modules.integrations.connectors.base import ActionError

    def fail_update(self, event_id, *, start, end):
        raise ActionError("calendar: leverandøren svarede ikke (simuleret)", code="provider_unavailable", retryable=True)

    monkeypatch.setattr(fakes.FakeCalendarClient, "update_event", fail_update)  # only the update fails
    text, moved = actions.execute(db, ws, "flyt_tid", {"ny_start": free[3]["start"], "bekraeftet": True}, ctx)
    db.commit()
    db.refresh(b)
    external_start = WORLD.events[b.calendar_event_id]["start"]
    conn = db.query(IntegrationConnection).filter_by(connector="google_calendar").one()
    assert conn.status == "error"  # recorded on the connection …
    diverged = external_start == old_start and b.starts_at == datetime.fromisoformat(free[3]["start"])
    assert diverged  # … but Dialogbot moved the booking while Google kept the old time
    assert moved.status != "ok" and "flyttet" not in text.lower(), (
        f"action status={moved.status!r}, text to caller={text!r}; Dialogbot={b.starts_at.isoformat()}, "
        f"Google={external_start.isoformat()}")


def test_bk15_failed_external_create_is_not_reported_as_done(api, client, two_workspaces, fake, db, monkeypatch):
    t = two_workspaces
    _booking_ready(api, t)
    _connect_google(api, client, t)
    ws = db.get(Workspace, uuid.UUID(t["ws_a"]))
    ctx = RunContext(workspace_id=ws.id, channel="phone", caller_phone="+4520304050", provider_call_id="call-qa-eb2")
    free = actions.execute(db, ws, "ledige_tider", {}, ctx)[1].output["tider"]
    from app.modules.integrations.connectors import fakes
    from app.modules.integrations.connectors.base import ActionError

    def fail_create(self, **kw):
        raise ActionError("calendar: timeout (simuleret)", code="provider_unavailable", retryable=True)

    monkeypatch.setattr(fakes.FakeCalendarClient, "create_event", fail_create)  # only the create fails
    text, run = actions.execute(db, ws, "book_tid", {"start": free[0]["start"], "navn": "Bo", "bekraeftet": True}, ctx)
    db.commit()
    b = db.query(Booking).one()
    assert b.calendar_event_id is None and not WORLD.events
    assert run.status != "ok" or "kalender" in text.lower(), (
        f"booking confirmed to caller ({text!r}, status={run.status}) though the Google write failed and no retry exists")


@pytest.mark.parametrize("req,pattern", [
    pytest.param("W13", r"/public/.*(booking/manage|bookings/\{)", id="W13-booking-manage-link"),
    pytest.param("W09", r"/public/.*(preferences|callback.*cancel)", id="W09-preferences-and-callback-cancel"),
    pytest.param("W04", r"/public/webchat/.*contact.*(verif|code|otp)", id="W04-contact-number-verification"),
])
def test_w13_w09_w04_customer_routes_exist(app, req, pattern):
    """W13/W09/W04 requirements: a customer-facing booking management link, preference/opt-out and call-back cancel
    views, and code verification of the number on «Bliv kontaktet» (built 13/11; behaviour in test_qa_w04_w09_w13.py).
    Routes are walked with all_routes (app.routes misses include_router() routes on FastAPI >= 0.140)."""
    import re

    from qa_sec_helpers import all_routes

    paths = sorted({p for _m, p, _r in all_routes(app)})
    assert [p for p in paths if re.search(pattern, p)], f"{req}: no route matching {pattern}"


# --------------------------------------------------------------------------- BK06 (DB-018)

def test_bk06_catalogue_is_honest(api, client, two_workspaces, fake, db):
    t = two_workspaces
    tok, ws = t["tok_a"], t["ws_a"]
    cat = api.get(tok, f"/workspaces/{ws}/integrations").json()
    items = {x["key"]: x for x in cat["items"]}
    assert cat["simulated"] is True
    # nothing is connected before an authorisation
    assert all(x["status"] != "connected" for x in cat["items"] if x["key"] != "bookings"), [
        (x["key"], x["status"]) for x in cat["items"] if x["status"] == "connected"]
    coming = [x for x in cat["items"] if x["availability"] != "ready"]
    assert coming and all(x["status"] == "not_implemented" for x in coming)
    for x in coming[:3]:
        r = api.post(tok, f"/workspaces/{ws}/integrations/{x['key']}/connect", {"config": {}, "secrets": {}})
        assert r.status_code in (404, 409, 501), (x["key"], r.status_code)
    # a denied authorisation does not connect
    r = api.post(tok, f"/workspaces/{ws}/integrations/google_calendar/connect", {"config": {}, "secrets": {}})
    state = dict(p.split("=") for p in urlparse(r.json()["authorize_url"]).query.split("&"))["state"]
    back = client.get(f"/api/v1/integrations/oauth/google_calendar/callback?state={state}&error=access_denied", follow_redirects=False)
    assert "error=oauth_denied" in back.headers["location"]
    assert api.get(tok, f"/workspaces/{ws}/integrations").json()["items"][0]["status"] != "connected"
    # after authorisation in the fake world: connected, but marked simulated (never a green stub without a label)
    _connect_google(api, client, t)
    g = next(x for x in api.get(tok, f"/workspaces/{ws}/integrations").json()["items"] if x["key"] == "google_calendar")
    assert g["status"] == "connected" and g["simulated"] is True
    # read-only feed alternative exists and is secret
    feed = api.get(tok, f"/workspaces/{ws}/bookings/settings").json()["feed_url"]
    assert len(feed.rsplit("/", 1)[1]) > 40
    assert client.get("/api/v1/public/calendar/guess.ics").status_code == 404
    assert items["google_calendar"]["auth_kind"] == "oauth"

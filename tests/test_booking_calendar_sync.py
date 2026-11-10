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

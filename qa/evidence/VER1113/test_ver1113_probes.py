"""Verifier probes 13/11 (F-VER1113-*). Copied into tests/qa/ of a worktree at 142e380 and run with the CI env."""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select
from test_qa_w12_bk15 import _connect_google, fake  # noqa: F401
from test_qa_w04_w09_w13 import PUB, _book, _clock, _session  # noqa: F401
from tests.test_leads import chat  # noqa: F401

from app.models import Booking
from app.modules.integrations.connectors import fakes
from app.modules.integrations.connectors.base import ActionError
from app.modules.integrations.connectors.fakes import WORLD


def test_probe_w13_customer_cancel_deletes_the_calendar_event_once(api, client, two_workspaces, fake, db, monkeypatch):  # noqa: F811
    """A cancelled booking's event should be deleted once. Google answers 410 Gone on a second DELETE of the same
    event (connectors/calendar._http maps every status >= 400 except 404 to provider_rejected)."""
    t = two_workspaces
    _connect_google(api, client, t)
    token, _ = _book(api, client, t)
    db.expire_all()
    b = db.scalar(select(Booking))
    assert b.calendar_event_id and b.calendar_sync == "synced"
    calls = []

    def delete_like_google(self, event_id):
        calls.append(event_id)
        if event_id not in WORLD.events:
            raise ActionError("Kalenderen afviste kaldet (410)", code="provider_rejected")
        WORLD.events.pop(event_id)

    monkeypatch.setattr(fakes.FakeCalendarClient, "delete_event", delete_like_google)
    session = _session(client, token)
    r = client.post(f"{PUB}/booking/manage/{token}/cancel", json={"session": session})
    assert r.status_code == 200, r.text
    db.expire_all()
    b = db.scalar(select(Booking))
    print("DELETE calls:", calls, "calendar_sync:", b.calendar_sync, "error:", b.calendar_sync_error)
    assert len(calls) == 1, f"event deleted {len(calls)} times: {calls}"
    assert b.calendar_sync != "failed", b.calendar_sync_error


def test_probe_w13_staff_cancel_deletes_the_calendar_event_once(api, client, two_workspaces, fake, db, monkeypatch):  # noqa: F811
    """Same pattern on the staff side (bookings/router.py cancel) – existed before #215."""
    t = two_workspaces
    _connect_google(api, client, t)
    _book(api, client, t)
    db.expire_all()
    b = db.scalar(select(Booking))
    calls = []

    def delete_like_google(self, event_id):
        calls.append(event_id)
        if event_id not in WORLD.events:
            raise ActionError("Kalenderen afviste kaldet (410)", code="provider_rejected")
        WORLD.events.pop(event_id)

    monkeypatch.setattr(fakes.FakeCalendarClient, "delete_event", delete_like_google)
    r = api.post(t["tok_a"], f"/workspaces/{t['ws_a']}/bookings/{b.id}/cancel", {})
    print("staff cancel:", r.status_code, r.text[:200])
    db.expire_all()
    b = db.scalar(select(Booking))
    print("DELETE calls:", calls, "calendar_sync:", b.calendar_sync, "error:", b.calendar_sync_error)
    assert len(calls) == 1, f"event deleted {len(calls)} times: {calls}"
    assert b.calendar_sync != "failed", b.calendar_sync_error


def test_probe_w13_link_follows_a_moved_booking(api, client, two_workspaces, fake, db, monkeypatch):  # noqa: F811
    """After the customer moves the appointment to a later day, the link should still open it until the new end."""
    t = two_workspaces
    token, _ = _book(api, client, t)
    before = client.get(f"{PUB}/booking/manage/{token}").json()
    slots = client.get(f"{PUB}/booking/manage/{token}/slots").json()["slots"]
    old_end = datetime.fromisoformat(before["ends_at"])
    later = [s for s in slots if datetime.fromisoformat(s["start"]) > old_end + timedelta(hours=2)]
    assert later, "need a later slot"
    session = _session(client, token)
    r = client.post(f"{PUB}/booking/manage/{token}/move", json={"start": later[-1]["start"], "session": session})
    assert r.status_code == 200, r.text
    moved = r.json()
    print("old ends_at", before["ends_at"], "new starts_at", moved["starts_at"], "link expires_at", moved["expires_at"])
    # one hour after the ORIGINAL appointment ended, before the new one starts
    delta = (old_end + timedelta(hours=1)) - datetime.now(old_end.tzinfo)
    _clock(monkeypatch, delta)
    r = client.get(f"{PUB}/booking/manage/{token}")
    print("GET after original end:", r.status_code, r.text[:160])
    assert r.status_code == 200, f"{r.status_code} {r.text[:160]}"


def test_probe_w04_ip_and_workspace_limits(client, chat, db):  # noqa: F811
    from tests.webchat_phone import request_code
    c = chat["conv"]
    got = []
    for i in range(7):
        r = request_code(client, chat["key"], c, f"+452030405{i}")
        got.append((r.status_code, r.json().get("code") or r.json().get("status")))
    print("IP limit:", got)
    assert [s for s, _ in got[:5]] == [202] * 5 and got[5][0] == 429, got


def test_probe_w04_workspace_limit(client, chat, db):  # noqa: F811
    """W04: at most 60 codes an hour per business (SMS_PER_WORKSPACE_HOUR), whatever IP or number."""
    c = chat["conv"]
    got = []
    for i in range(62):
        r = client.post(f"{PUB}/webchat/{chat['key']}/conversations/{c['conversation_id']}/contact/code",
                        json={"phone": f"+4521{i:06d}"},
                        headers={"origin": "http://localhost:8000", "x-visitor-token": c["visitor_token"],
                                 "x-forwarded-for": f"10.9.{i // 200}.{i % 200 + 1}"})
        got.append(r.status_code)
    print("workspace limit: first 429 at request", got.index(429) + 1 if 429 in got else None, "codes:", sorted(set(got)))
    assert got[:60] == [202] * 60 and got[60] == 429, got

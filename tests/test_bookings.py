"""Online booking: slots from approved opening hours, busy time, lead-time, webchat booking → lead + task,
manual booking, cancel, iCal feed and calendar busy import."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx

from app.config import get_settings
from app.models import BookingSettings, Lead, Task
from app.modules.bookings import service


def _setup(api, t, *, hours=None):
    tok, ws = t["tok_a"], t["ws_a"]
    week = hours or [{"days": ["mon", "tue", "wed", "thu", "fri", "sat", "sun"], "open": "08:00", "close": "16:00"}]
    it = api.knowledge(tok, ws, "opening_hours", "Åbningstider", {"weekly": week})
    api.submit(tok, ws, it["open_draft"]["id"])
    api.approve(tok, ws, it["open_draft"]["id"])
    typ = api.post(tok, f"/workspaces/{ws}/bookings/types", {"name": "Besigtigelse", "duration_minutes": 60}).json()
    s = api.get(tok, f"/workspaces/{ws}/bookings/settings").json()
    r = api.put(tok, f"/workspaces/{ws}/bookings/settings", {"expected_version": s["version"], "enabled": True,
                                                              "lead_time_hours": 0, "horizon_days": 7, "buffer_minutes": 0})
    assert r.status_code == 200, r.text
    return typ["id"]


def test_slots_follow_approved_hours_and_bookings(api, two_workspaces, db):
    t = two_workspaces
    tok, ws = t["tok_a"], t["ws_a"]
    s = api.get(tok, f"/workspaces/{ws}/bookings/settings").json()
    # cannot enable without a type
    bad = api.put(tok, f"/workspaces/{ws}/bookings/settings", {"expected_version": s["version"], "enabled": True,
                                                                "lead_time_hours": 0, "horizon_days": 7, "buffer_minutes": 0})
    assert bad.status_code == 422
    type_id = _setup(api, t)
    slots = api.get(tok, f"/workspaces/{ws}/bookings/slots?type_id={type_id}").json()["items"]
    assert slots and all("kl." in x["label"] for x in slots)
    first = slots[0]
    local = datetime.fromisoformat(first["start"]).astimezone(__import__("zoneinfo").ZoneInfo("Europe/Copenhagen"))
    assert 8 <= local.hour < 16
    r = api.post(tok, f"/workspaces/{ws}/bookings", {"type_id": type_id, "start": first["start"], "name": "Mette",
                                                     "phone": "+4520304050"})
    assert r.status_code == 201, r.text
    after = api.get(tok, f"/workspaces/{ws}/bookings/slots?type_id={type_id}").json()["items"]
    assert first["start"] not in {x["start"] for x in after}
    # the manual booking created a lead and a task at the booked time
    b = r.json()
    lead = db.get(Lead, __import__("uuid").UUID(b["lead_id"]))
    assert lead.contact_name == "Mette" and "besigtigelse" in lead.need_summary
    task = db.query(Task).filter(Task.lead_id == lead.id).one()
    assert task.due_at == datetime.fromisoformat(first["start"])
    # double booking the same time is refused; cancel frees it
    dup = api.post(tok, f"/workspaces/{ws}/bookings", {"type_id": type_id, "start": first["start"], "name": "X"})
    assert dup.status_code == 409
    assert api.post(tok, f"/workspaces/{ws}/bookings/{b['id']}/cancel", {}).json()["status"] == "cancelled"
    assert first["start"] in {x["start"] for x in api.get(tok, f"/workspaces/{ws}/bookings/slots?type_id={type_id}").json()["items"]}
    reader = api.add_member(tok, ws, "reader-book@testmail.dk", "reader")
    assert api.get(reader, f"/workspaces/{ws}/bookings").status_code == 403


def test_webchat_booking_and_feed(api, client, two_workspaces, db, monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "fake")
    get_settings.cache_clear()
    t = two_workspaces
    tok, ws = t["tok_a"], t["ws_a"]
    type_id = _setup(api, t)
    wc = api.get(tok, f"/workspaces/{ws}/webchat").json()
    r = api.put(tok, f"/workspaces/{ws}/webchat", {"expected_version": wc["version"], "enabled": True,
                                                  "allowed_origins": ["https://fjord.dk"], "greeting": ""})
    assert r.status_code == 200, r.text
    key = r.json()["widget_key"]
    frame = get_settings().public_base_url
    opts = client.get(f"/api/v1/public/webchat/{key}/booking").json()
    assert opts["enabled"] and opts["types"][0]["name"] == "Besigtigelse" and opts["slots"]
    conv = client.post(f"/api/v1/public/webchat/{key}/conversations", json={"host_origin": "https://fjord.dk"},
                       headers={"origin": frame})
    assert conv.status_code == 201, conv.text
    conv = conv.json() | {"id": conv.json()["conversation_id"]}
    h = {"origin": frame, "x-visitor-token": conv["visitor_token"]}
    body = {"type_id": type_id, "start": opts["slots"][0]["start"], "name": "Ole", "phone": "+4520304050", "consent": True}
    ok = client.post(f"/api/v1/public/webchat/{key}/conversations/{conv['id']}/booking", json=body, headers=h)
    assert ok.status_code == 201, ok.text
    assert "kl." in ok.json()["label"]
    again = client.post(f"/api/v1/public/webchat/{key}/conversations/{conv['id']}/booking", json=body, headers=h)
    assert again.status_code == 409 and again.json()["code"] == "slot_taken"
    assert client.post(f"/api/v1/public/webchat/{key}/conversations/{conv['id']}/booking",
                       json={**body, "consent": False}, headers=h).status_code == 422
    # the owner's calendar feed contains the booking; an unknown token does not exist
    feed_url = api.get(tok, f"/workspaces/{ws}/bookings/settings").json()["feed_url"]
    feed = client.get("/api/v1" + feed_url.split("/api/v1", 1)[1])
    assert feed.status_code == 200 and b"Besigtigelse: Ole" in feed.content and feed.headers["content-type"].startswith("text/calendar")
    assert client.get("/api/v1/public/calendar/nope.ics").status_code == 404
    get_settings.cache_clear()


ICS = b"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:test
BEGIN:VEVENT
UID:1
DTSTART:{start}
DTEND:{end}
SUMMARY:Privat aftale
END:VEVENT
BEGIN:VEVENT
UID:2
DTSTART:{start}
DTEND:{end}
TRANSP:TRANSPARENT
SUMMARY:Ledig
END:VEVENT
END:VCALENDAR
"""


def test_calendar_busy_time_blocks_slots(api, two_workspaces, db, monkeypatch):
    t = two_workspaces
    tok, ws = t["tok_a"], t["ws_a"]
    type_id = _setup(api, t)
    slots = api.get(tok, f"/workspaces/{ws}/bookings/slots?type_id={type_id}").json()["items"]
    first = datetime.fromisoformat(slots[0]["start"])
    fmt = "%Y%m%dT%H%M%SZ"
    body = ICS.replace(b"{start}", first.astimezone(UTC).strftime(fmt).encode()).replace(
        b"{end}", (first + timedelta(hours=1)).astimezone(UTC).strftime(fmt).encode())

    class FakeClient:
        def __init__(self, *a, **kw):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, url):
            return httpx.Response(200, content=body, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "Client", FakeClient)
    s = api.get(tok, f"/workspaces/{ws}/bookings/settings").json()
    r = api.put(tok, f"/workspaces/{ws}/bookings/settings", {"expected_version": s["version"], "enabled": True,
                                                              "lead_time_hours": 0, "horizon_days": 7, "buffer_minutes": 0,
                                                              "busy_ics_url": "webcal://calendar.example/private.ics"})
    out = r.json()
    assert out["busy_error"] is None and out["busy_blocks"] == 1  # the transparent event does not block
    after = api.get(tok, f"/workspaces/{ws}/bookings/slots?type_id={type_id}").json()["items"]
    assert slots[0]["start"] not in {x["start"] for x in after}
    stored = db.get(BookingSettings, __import__("uuid").UUID(ws))
    assert "Privat aftale" not in str(stored.busy_blocks)  # titles are never stored
    check = api.post(tok, f"/workspaces/{ws}/setup/checks/calendar.connection/run").json()
    assert check["evidence"]["calendar_connected"] is True


def test_label_is_danish():
    assert service.label(datetime(2026, 9, 28, 7, 0, tzinfo=UTC), "Europe/Copenhagen") == "mandag 28. september kl. 09.00"


def test_phone_booking_tools(api, client, two_workspaces, db, monkeypatch):
    t = two_workspaces
    tok, ws = t["tok_a"], t["ws_a"]
    secret = "vapi-test-secret-0123456789abcdef"
    monkeypatch.setenv("VAPI_SERVER_SECRET", secret)
    get_settings.cache_clear()
    _setup(api, t)
    api.post(tok, f"/workspaces/{ws}/phone-numbers", {"e164": "+4570123456", "provider_number_id": "pn_book"})
    h = {"authorization": f"Bearer {secret}"}
    a = client.post("/api/v1/webhooks/vapi", json={"message": {"type": "assistant-request", "call": {"phoneNumberId": "pn_book"}}},
                    headers=h).json()["assistant"]
    assert [x["function"]["name"] for x in a["model"]["tools"]] == ["ledige_tider", "book_tid"]
    call = {"id": "call_book_1", "phoneNumberId": "pn_book", "customer": {"number": "+4520304050"}}
    free = client.post("/api/v1/webhooks/vapi", json={"message": {"type": "tool-calls", "call": call, "toolCallList": [
        {"id": "t1", "type": "function", "function": {"name": "ledige_tider", "arguments": {}}}]}}, headers=h).json()
    text = free["results"][0]["result"]
    assert free["results"][0]["toolCallId"] == "t1" and "Ledige tider til besigtigelse" in text
    start = text.split("(start ")[1].split(")")[0]
    booked = client.post("/api/v1/webhooks/vapi", json={"message": {"type": "tool-calls", "call": call, "toolCallList": [
        {"id": "t2", "type": "function", "function": {"name": "book_tid", "arguments": f'{{"start": "{start}", "navn": "Bo"}}'}}]}},
                         headers=h).json()["results"][0]["result"]
    assert booked.startswith("Booket: Besigtigelse")
    items = api.get(tok, f"/workspaces/{ws}/bookings").json()["items"]
    assert items[0]["source"] == "phone" and items[0]["contact_phone"] == "+4520304050"
    # the end-of-call report links the call to the booking's lead instead of creating a second one
    report = {"type": "end-of-call-report", "call": call | {"startedAt": "2026-09-24T08:00:00Z", "endedAt": "2026-09-24T08:02:00Z"},
              "artifact": {"messages": [{"role": "user", "message": "Jeg vil gerne have en besigtigelse"}]}}
    assert client.post("/api/v1/webhooks/vapi", json={"message": report}, headers=h).json()["outcome"] == "applied"
    assert db.query(Lead).filter(Lead.workspace_id == __import__("uuid").UUID(ws)).count() == 1
    get_settings.cache_clear()

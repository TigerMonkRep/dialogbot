"""Web Push for the business PWA (app/modules/push): subscribe per workspace, a push on call.completed to every
subscribed member only, unsubscribe, and separation from Dialogbot Privat's subscriptions."""
from __future__ import annotations

import json

import pytest

from app.config import get_settings
from app.models import OutboxEvent, PushSubscription
from app.modules.privat import push
from app.worker import runner

SECRET = "vapi-test-secret-0123456789abcdef"
KEYS = {"p256dh": "BNcRdreALRFXTkOOUHK1EtK2wtaz5Ry4YfYCA_0QTpQtUbVlUls0VJXg7A8u-Ts1XbjhazAkj7I99e8QcYP7DkM",
        "auth": "tBHItJI5svbpez7KI4CCXg"}


@pytest.fixture
def vapid(monkeypatch):
    monkeypatch.setenv("VAPID_PUBLIC_KEY", "BPUBLICKEYxxxxxxxxxxxxxxxxxxxxxxxxx")
    monkeypatch.setenv("VAPID_PRIVATE_KEY", "privatekeyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx")
    monkeypatch.setenv("VAPI_SERVER_SECRET", SECRET)
    get_settings.cache_clear()
    sent: list[tuple[dict, str]] = []
    monkeypatch.setattr(push, "_webpush", lambda sub, data: sent.append((sub, data)))
    yield sent
    get_settings.cache_clear()


def _sub(api, tok, ws, endpoint):
    return api.post(tok, "/push/subscriptions", {"endpoint": endpoint, "keys": KEYS, "audience": "erhverv", "workspace_id": ws})


def _call(api, t, call_id="call_1", *, mapped=False):
    if not mapped:
        api.map_number(t["ws_a"], "+45 70 12 34 56", "pn_123")
    msg = {"type": "end-of-call-report", "endedReason": "customer-ended-call",
           "call": {"id": call_id, "phoneNumberId": "pn_123", "customer": {"number": "+4520304050"},
                    "startedAt": "2026-09-24T08:00:00Z", "endedAt": "2026-09-24T08:02:30Z"},
           "analysis": {"summary": "Kunden vil have tilbud på afslibning af 65 m²."},
           "artifact": {"messages": [{"role": "bot", "message": "Hej"}, {"role": "user", "message": "Hvad koster det?"}]}}
    r = api.c.post("/api/v1/webhooks/vapi", json={"message": msg}, headers={"authorization": f"Bearer {SECRET}"})
    assert r.status_code == 200 and r.json()["received"], r.text
    return r.json()


def test_not_configured_and_membership(api, two_workspaces, monkeypatch):
    t = two_workspaces
    monkeypatch.delenv("VAPID_PUBLIC_KEY", raising=False)
    get_settings.cache_clear()
    assert api.get(t["tok_a"], "/push/public-key").json()["code"] == "push_not_configured"
    assert _sub(api, t["tok_a"], t["ws_a"], "https://push.example.test/a").status_code == 501
    get_settings.cache_clear()


def test_subscribe_push_on_call_completed_and_unsubscribe(api, two_workspaces, vapid, db):
    t = two_workspaces
    tok, ws = t["tok_a"], t["ws_a"]
    assert api.get(tok, "/push/public-key").json() == {"public_key": "BPUBLICKEYxxxxxxxxxxxxxxxxxxxxxxxxx"}
    # must be a member of the workspace; a personal workspace id is refused
    assert _sub(api, tok, t["ws_b"], "https://push.example.test/a").status_code == 404
    assert _sub(api, tok, ws, "http://push.example.test/a").status_code == 422
    r = _sub(api, tok, ws, "https://push.example.test/a")
    assert r.status_code == 200 and r.json()["workspace_id"] == ws and r.json()["audience"] == "erhverv"
    staff = api.add_member(tok, ws, "staff-push@testmail.dk", "staff")
    assert _sub(api, staff, ws, "https://push.example.test/staff").status_code == 200
    # owner B of the other workspace subscribes too, and never hears about A's calls
    assert _sub(api, t["tok_b"], t["ws_b"], "https://push.example.test/b").status_code == 200
    # re-subscribing the same browser updates the row, it does not duplicate
    assert _sub(api, tok, ws, "https://push.example.test/a").status_code == 200
    assert db.query(PushSubscription).count() == 3
    _call(api, t)
    evs = db.query(OutboxEvent).filter_by(event_type="push.send").all()
    assert len(evs) == 2
    assert {e.payload["title"] for e in evs} == {"Nyt opkald"}
    p = evs[0].payload
    assert p["body"].startswith("Kunden vil have tilbud") and p["tag"].startswith("call-") and "/app/opkald/" in p["url"]
    runner.drain()
    endpoints = sorted(s["endpoint"] for s, _ in vapid)
    assert endpoints == ["https://push.example.test/a", "https://push.example.test/staff"]
    data = json.loads(vapid[0][1])
    assert data["title"] == "Nyt opkald" and data["url"].endswith(f"/app/opkald/{p['url'].rsplit('/', 1)[1]}")
    # the same call reported again is a duplicate: no second push
    assert _call(api, t, mapped=True)["duplicate"] is True
    assert db.query(OutboxEvent).filter_by(event_type="push.send").count() == 2
    # unsubscribe: only the caller's own row; afterwards nothing goes to that browser
    r = api.c.request("DELETE", "/api/v1/push/subscriptions", json={"endpoint": "https://push.example.test/staff"},
                      headers=api.h(tok))
    assert r.json() == {"removed": False}
    r = api.c.request("DELETE", "/api/v1/push/subscriptions", json={"endpoint": "https://push.example.test/a"},
                      headers=api.h(tok))
    assert r.json() == {"removed": True}
    _call(api, t, "call_2", mapped=True)
    evs = db.query(OutboxEvent).filter_by(event_type="push.send").all()
    assert len(evs) == 3
    latest = max(evs, key=lambda e: e.created_at)
    assert db.get(PushSubscription, __import__("uuid").UUID(latest.payload["subscription_id"])).endpoint.endswith("/staff")


def test_privat_and_erhverv_subscriptions_are_separate(api, two_workspaces, vapid, db, pv):
    t = two_workspaces
    tok, ws = t["tok_a"], t["ws_a"]
    assert _sub(api, tok, ws, "https://push.example.test/erhverv").status_code == 200
    # the same user has a private account; its reminders go only to privat subscriptions
    api.post(tok, "/privat/account")
    assert api.post(tok, "/privat/push/subscriptions", {"endpoint": "https://push.example.test/privat", "keys": KEYS}).status_code == 200
    assert push.subscriptions(db, db.query(PushSubscription).first().user_id) and len(push.subscriptions(
        db, db.query(PushSubscription).first().user_id)) == 1
    assert api.post(tok, "/privat/push/test").json() == {"sent": 1}
    ev = db.query(OutboxEvent).filter_by(event_type="push.send").one()
    sub = db.get(PushSubscription, __import__("uuid").UUID(ev.payload["subscription_id"]))
    assert sub.endpoint == "https://push.example.test/privat" and sub.audience == "privat"
    # subscribing the privat app from the erhverv browser moves the row (one endpoint, one owner app)
    assert api.post(tok, "/privat/push/subscriptions", {"endpoint": "https://push.example.test/erhverv", "keys": KEYS}).status_code == 200
    moved = db.query(PushSubscription).filter_by(endpoint="https://push.example.test/erhverv").one()
    db.refresh(moved)
    assert moved.audience == "privat" and moved.workspace_id is None

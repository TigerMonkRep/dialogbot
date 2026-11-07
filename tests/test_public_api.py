"""Public API v1 (api.dialogbot.app/v1, app/modules/public_api).

Acceptance: keys are issued only by admin/owner, shown once, at most two active per workspace, revoked at once;
bearer auth with 401/403/404 semantics; every read endpoint answers the canonical fixtures through the frozen v1
schemas (no cost, no provider ids, masked contacts without contacts:read); POST needs an Idempotency-Key and replays;
per-key rate limit answers 429 with Retry-After; webhook endpoints are CRUD'ed with a once-shown secret and events
are delivered signed from the outbox with retries and auto-disable; APP_SURFACE decides what a process mounts.
"""
from __future__ import annotations

import json
import uuid
from datetime import UTC, date, datetime, timedelta

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import get_settings
from app.core import safe_fetch
from app.models import ApiKey, AuditLog, Call, DailyReport, DoNotCall, OutboxEvent, WebhookEndpoint
from app.modules.public_api import ratelimit, scopes
from app.modules.public_api import webhook_delivery as wd
from app.worker import runner

V1 = "/v1"
ALL_SCOPES = list(scopes.BUSINESS_SCOPES)
HOOK = "https://hooks.example.dk/dialogbot"
PUBLIC_IP = "93.184.216.34"
DNS = {"hooks.example.dk": [PUBLIC_IP], "intern.example.dk": ["10.0.0.7"]}


def _issue(api, tok, ws, scopes=None, **extra):
    r = api.post(tok, f"/workspaces/{ws}/api-keys", {"name": "CRM", "scopes": scopes or ALL_SCOPES, **extra})
    assert r.status_code == 201, r.text
    return r.json()


def ph(key: str, **extra) -> dict:
    return {"Authorization": f"Bearer {key}", **extra}


@pytest.fixture
def keyed(api, two_workspaces):
    """Workspace A with an all-scope key, workspace B with a key of its own."""
    t = two_workspaces
    a = _issue(api, t["tok_a"], t["ws_a"])
    b = _issue(api, t["tok_b"], t["ws_b"], scopes=["calls:read"])
    return {**t, "key_a": a["key"], "key_a_id": a["id"], "key_b": b["key"]}


@pytest.fixture(autouse=True)
def _fresh_limiter():
    ratelimit.LIMITER = None
    yield
    ratelimit.LIMITER = None


# --------------------------------------------------------------------------- keys (internal management)

def test_key_issue_list_revoke_limits_and_roles(api, two_workspaces, db):
    t = two_workspaces
    tok, ws = t["tok_a"], t["ws_a"]
    cat = api.get(tok, f"/workspaces/{ws}/api-keys/scopes").json()
    assert {s["name"] for s in cat} == set(ALL_SCOPES)
    r = api.post(tok, f"/workspaces/{ws}/api-keys", {"name": "CRM", "scopes": ["calls:read", "bookings:read"]},
                 **{"Idempotency-Key": "k1"})
    assert r.status_code == 201, r.text
    k = r.json()
    assert k["key"].startswith("dbk_live_") and len(k["key"]) > 40 and k["last4"] == k["key"][-4:]
    assert k["scopes"] == ["calls:read", "bookings:read"] and k["status"] == "active" and k["expires_at"] is None
    # the replay of the same command does not hand the key out again; the stored row holds only the digest
    again = api.post(tok, f"/workspaces/{ws}/api-keys", {"name": "CRM", "scopes": ["calls:read", "bookings:read"]},
                     **{"Idempotency-Key": "k1"})
    assert again.status_code == 201 and again.json()["key"] is None and again.json()["id"] == k["id"]
    row = db.get(ApiKey, uuid.UUID(k["id"]))
    assert row.token_hash != k["key"] and k["key"] not in row.token_hash
    # unknown scope, scope of the other kind, test environment + expiry
    assert api.post(tok, f"/workspaces/{ws}/api-keys", {"name": "x", "scopes": ["tasks:read"]}).status_code == 422
    assert api.post(tok, f"/workspaces/{ws}/api-keys", {"name": "x", "scopes": ["nope"]}).status_code == 422
    k2 = _issue(api, tok, ws, ["leads:read"], environment="test", expires_in_days=30)
    assert k2["key"].startswith("dbk_test_") and k2["expires_at"] is not None
    # max two active
    r = api.post(tok, f"/workspaces/{ws}/api-keys", {"name": "third", "scopes": ["leads:read"]})
    assert r.status_code == 409 and r.json()["code"] == "api_key_limit"
    listed = api.get(tok, f"/workspaces/{ws}/api-keys").json()
    assert [x["name"] for x in listed] == ["CRM", "CRM"] and all("key" not in x and "token_hash" not in x for x in listed)
    # revoke frees a slot and takes effect at once
    assert api.delete(tok, f"/workspaces/{ws}/api-keys/{k2['id']}").status_code == 204
    assert api.c.get(f"{V1}/me", headers=ph(k2["key"])).json()["code"] == "api_key_invalid"
    assert _issue(api, tok, ws, ["leads:read"])["status"] == "active"
    actions = [a.action for a in db.scalars(select(AuditLog).where(AuditLog.workspace_id == uuid.UUID(ws)))]
    assert actions.count("api_key.created") == 3 and actions.count("api_key.revoked") == 1
    # staff cannot manage keys; other workspaces' keys are 404
    staff = api.add_member(tok, ws, "staff-api@testmail.dk", "staff")
    assert api.get(staff, f"/workspaces/{ws}/api-keys").status_code == 403
    assert api.post(staff, f"/workspaces/{ws}/api-keys", {"name": "x", "scopes": ["calls:read"]}).status_code == 403
    assert api.delete(t["tok_b"], f"/workspaces/{t['ws_b']}/api-keys/{k['id']}").status_code == 404


def test_privat_keys_use_personal_scopes(api, pv, db):
    tok = pv.account("peter@testmail.dk")
    cat = api.get(tok, "/privat/api-keys/scopes").json()
    assert {s["name"] for s in cat} == set(scopes.PERSONAL_SCOPES)
    assert api.post(tok, "/privat/api-keys", {"name": "Kalender", "scopes": ["bookings:read"]}).status_code == 422
    k = api.post(tok, "/privat/api-keys", {"name": "Kalender", "scopes": ["tasks:read", "calls:propose"]}).json()
    me = api.c.get(f"{V1}/me", headers=ph(k["key"])).json()
    assert me["workspace"]["kind"] == "personal" and me["scopes"] == ["calls:propose", "tasks:read"]
    # a personal key never reaches the business resources
    r = api.c.get(f"{V1}/workspaces/{me['workspace']['id']}/calls", headers=ph(k["key"]))
    assert r.status_code == 404
    assert api.delete(tok, f"/privat/api-keys/{k['id']}").status_code == 204
    assert api.get(tok, "/privat/api-keys").json()[0]["status"] == "revoked"


# --------------------------------------------------------------------------- auth

def test_auth_failures_scopes_and_workspace_binding(api, keyed, db):
    t = keyed
    c = api.c
    assert c.get(f"{V1}/me").status_code == 401
    assert c.get(f"{V1}/me", headers={"Authorization": "Basic abc"}).json()["code"] == "unauthenticated"
    assert c.get(f"{V1}/me", headers=ph("not-a-key")).json()["code"] == "api_key_invalid"
    assert c.get(f"{V1}/me", headers=ph("dbk_live_" + "x" * 43)).json()["code"] == "api_key_invalid"
    # a session token is not an API key
    assert c.get(f"{V1}/me", headers=ph(t["tok_a"])).status_code == 401
    me = c.get(f"{V1}/me", headers=ph(t["key_a"])).json()
    assert me["workspace"]["id"] == t["ws_a"] and me["key"]["id"] == t["key_a_id"] and "calls:read" in me["scopes"]
    assert db.get(ApiKey, uuid.UUID(t["key_a_id"])).last_used_at is not None
    # scope enforcement names the missing scope
    r = c.get(f"{V1}/workspaces/{t['ws_b']}/leads", headers=ph(t["key_b"]))
    assert r.status_code == 403 and r.json()["code"] == "insufficient_scope" and r.json()["required_scope"] == "leads:read"
    # the other workspace does not exist from a key's point of view
    assert c.get(f"{V1}/workspaces/{t['ws_a']}/calls", headers=ph(t["key_b"])).status_code == 404
    assert c.get(f"{V1}/workspaces/{uuid.uuid4()}/calls", headers=ph(t["key_a"])).status_code == 404
    # expired key
    row = db.get(ApiKey, uuid.UUID(t["key_a_id"]))
    row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db.commit()
    assert c.get(f"{V1}/me", headers=ph(t["key_a"])).json()["code"] == "api_key_invalid"


# --------------------------------------------------------------------------- read endpoints

SECRET = "vapi-test-secret-0123456789abcdef"


def _call_report(call_id="call_1", *, caller="+4520304050", number_id="pn_123"):
    return {"type": "end-of-call-report", "endedReason": "customer-ended-call",
            "call": {"id": call_id, "phoneNumberId": number_id, "customer": {"number": caller},
                     "startedAt": "2026-09-24T08:00:00Z", "endedAt": "2026-09-24T08:02:30Z"},
            "analysis": {"summary": "Kunden vil have tilbud på afslibning af 65 m²."}, "cost": 0.23,
            "artifact": {"messages": [{"role": "bot", "message": "Hej, du har ringet til Fjord."},
                                      {"role": "user", "message": "Hvad koster afslibning?"}]}}


@pytest.fixture
def telephony(monkeypatch):
    monkeypatch.setenv("VAPI_SERVER_SECRET", SECRET)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _phone_call(api, t, call_id="call_1", caller="+4520304050"):
    api.map_number(t["ws_a"], "+45 70 12 34 56", "pn_123")
    r = api.c.post("/api/v1/webhooks/vapi", json={"message": _call_report(call_id, caller=caller)},
                   headers={"authorization": f"Bearer {SECRET}"})
    assert r.json()["outcome"] == "applied", r.text


def test_calls_conversations_and_contact_masking(api, keyed, telephony, db):
    t = keyed
    _phone_call(api, t)
    base = f"{V1}/workspaces/{t['ws_a']}"
    masked = _issue(api, t["tok_a"], t["ws_a"], ["calls:read", "conversations:read"])["key"]
    page = api.c.get(f"{base}/calls", headers=ph(masked)).json()
    assert page["next_cursor"] is None and len(page["items"]) == 1
    call = page["items"][0]
    assert call["summary"].startswith("Kunden vil") and call["duration_seconds"] == 150 and call["direction"] == "inbound"
    assert call["from_number"] == "+45••••••50" and call["to_number"] == "+4570123456"
    assert not {"cost_usd_micros", "provider_call_id", "recording_url", "cost"} & set(call)
    full = api.c.get(f"{base}/calls/{call['id']}", headers=ph(t["key_a"])).json()  # contacts:read reveals
    assert full["from_number"] == "+4520304050"
    assert api.c.get(f"{base}/calls/{uuid.uuid4()}", headers=ph(t["key_a"])).status_code == 404
    # the other workspace sees nothing, even with the right scope
    assert api.c.get(f"{V1}/workspaces/{t['ws_b']}/calls", headers=ph(t["key_b"])).json()["items"] == []
    convs = api.c.get(f"{base}/conversations?channel=phone", headers=ph(masked)).json()["items"]
    assert len(convs) == 1 and convs[0]["origin"] == "+45••••••50" and convs[0]["id"] == call["conversation_id"]
    msgs = api.c.get(f"{base}/conversations/{convs[0]['id']}/messages", headers=ph(masked)).json()["items"]
    assert [m["role"] for m in msgs] == ["assistant", "visitor"] and msgs[1]["text"] == "Hvad koster afslibning?"
    # filters
    assert api.c.get(f"{base}/calls?direction=outbound", headers=ph(masked)).json()["items"] == []
    assert api.c.get(f"{base}/calls?since=2030-01-01T00:00:00Z", headers=ph(masked)).json()["items"] == []
    assert api.c.get(f"{base}/calls?direction=sideways", headers=ph(masked)).status_code == 422


def test_cursor_pagination_is_stable(api, keyed, db):
    t = keyed
    ws = uuid.UUID(t["ws_a"])
    base = datetime(2026, 9, 1, tzinfo=UTC)
    for i in range(7):
        db.add(Call(workspace_id=ws, provider="vapi", provider_call_id=f"c{i}", summary=f"nr {i}",
                    created_at=base + timedelta(minutes=i)))
    db.commit()
    seen, cursor_ = [], None
    for _ in range(5):
        url = f"{V1}/workspaces/{t['ws_a']}/calls?limit=3" + (f"&cursor={cursor_}" if cursor_ else "")
        page = api.c.get(url, headers=ph(t["key_a"])).json()
        seen += [x["summary"] for x in page["items"]]
        cursor_ = page["next_cursor"]
        if not cursor_:
            break
    assert seen == [f"nr {i}" for i in range(6, -1, -1)]
    assert api.c.get(f"{V1}/workspaces/{t['ws_a']}/calls?cursor=%%%", headers=ph(t["key_a"])).json()["code"] == "invalid_cursor"
    assert api.c.get(f"{V1}/workspaces/{t['ws_a']}/calls?limit=0", headers=ph(t["key_a"])).status_code == 422


def _booking_setup(api, t):
    tok, ws = t["tok_a"], t["ws_a"]
    it = api.knowledge(tok, ws, "opening_hours", "Åbningstider",
                       {"weekly": [{"days": ["mon", "tue", "wed", "thu", "fri", "sat", "sun"], "open": "08:00", "close": "16:00"}]})
    api.submit(tok, ws, it["open_draft"]["id"])
    api.approve(tok, ws, it["open_draft"]["id"])
    typ = api.post(tok, f"/workspaces/{ws}/bookings/types", {"name": "Besigtigelse", "duration_minutes": 60}).json()
    s = api.get(tok, f"/workspaces/{ws}/bookings/settings").json()
    api.put(tok, f"/workspaces/{ws}/bookings/settings", {"expected_version": s["version"], "enabled": True,
                                                         "lead_time_hours": 0, "horizon_days": 7, "buffer_minutes": 0})
    return typ["id"]


def test_bookings_types_leads_knowledge_and_reports(api, keyed, db):
    t = keyed
    tok, ws = t["tok_a"], t["ws_a"]
    base = f"{V1}/workspaces/{ws}"
    type_id = _booking_setup(api, t)
    slot = api.get(tok, f"/workspaces/{ws}/bookings/slots?type_id={type_id}").json()["items"][0]
    b = api.post(tok, f"/workspaces/{ws}/bookings", {"type_id": type_id, "start": slot["start"], "name": "Mette",
                                                     "phone": "+4520304050", "email": "mette@example.dk"}).json()
    types = api.c.get(f"{base}/booking-types", headers=ph(t["key_a"])).json()["items"]
    assert types == [{"id": type_id, "name": "Besigtigelse", "duration_minutes": 60, "description": "", "active": True,
                      "created_at": types[0]["created_at"]}]
    bookings = api.c.get(f"{base}/bookings", headers=ph(t["key_a"])).json()["items"]
    assert bookings[0]["id"] == b["id"] and bookings[0]["contact_phone"] == "+4520304050" and bookings[0]["lead_id"]
    assert not {"calendar_event_id", "provider_call_id", "calendar_connector"} & set(bookings[0])
    limited = _issue(api, tok, ws, ["bookings:read", "leads:read", "knowledge:read", "reports:read"])["key"]
    one = api.c.get(f"{base}/bookings/{b['id']}", headers=ph(limited)).json()
    assert one["contact_phone"] == "+45••••••50" and one["contact_email"] == "m•••@example.dk"
    assert api.c.get(f"{base}/bookings?status=cancelled", headers=ph(limited)).json()["items"] == []
    # leads: the booking's lead, without billing fields
    leads = api.c.get(f"{base}/leads", headers=ph(limited)).json()["items"]
    assert leads[0]["id"] == bookings[0]["lead_id"] and leads[0]["contact_name"] == "Mette"
    assert not {"billing_status", "fee_snapshot", "agreement_id", "billing_reason"} & set(leads[0])
    assert api.c.get(f"{base}/leads/{leads[0]['id']}", headers=ph(limited)).json()["pipeline_status"] == "new"
    assert api.c.get(f"{base}/leads?pipeline_status=won", headers=ph(limited)).json()["items"] == []
    # knowledge: only approved versions; a draft never shows
    api.knowledge(tok, ws, "fact", "HEMMELIG-KLADDE", {"text": "x"})
    kn = api.c.get(f"{base}/knowledge", headers=ph(limited)).json()["items"]
    assert [k["kind"] for k in kn] == ["opening_hours"] and kn[0]["content"]["weekly"] and kn[0]["approved_at"]
    assert "HEMMELIG" not in json.dumps(kn, ensure_ascii=False)
    assert api.c.get(f"{base}/knowledge/{kn[0]['item_id']}", headers=ph(limited)).json()["title"] == "Åbningstider"
    assert api.c.get(f"{base}/knowledge?kind=service", headers=ph(limited)).json()["items"] == []
    # reports: a finished day's snapshot, trimmed (no AI cost)
    db.add(DailyReport(workspace_id=uuid.UUID(ws), report_date=date(2026, 9, 24), timezone="Europe/Copenhagen",
                       data={"conversations": {"started": 3, "visitor_messages": 7}, "leads": {"new": 2, "approved": 1,
                             "rejected": 0, "approved_fee_net_minor": 14900}, "tasks": {"created": 1, "completed": 0,
                             "open_overdue_at_end": 2}, "ai": {"est_cost_usd_micros": 900}}))
    db.commit()
    reps = api.c.get(f"{base}/reports/daily?from=2026-09-01&to=2026-09-30", headers=ph(limited)).json()["items"]
    assert reps == [{"date": "2026-09-24", "timezone": "Europe/Copenhagen", "generated_at": reps[0]["generated_at"],
                     "conversations": {"started": 3, "visitor_messages": 7}, "leads": {"new": 2, "approved": 1, "rejected": 0},
                     "tasks": {"created": 1, "completed": 0, "open_overdue_at_end": 2}}]
    assert api.c.get(f"{base}/reports/daily/2026-09-24", headers=ph(limited)).json()["leads"]["new"] == 2
    assert api.c.get(f"{base}/reports/daily/2026-09-25", headers=ph(limited)).status_code == 404
    # scope boundaries of the limited key
    assert api.c.get(f"{base}/calls", headers=ph(limited)).status_code == 403
    assert api.c.get(f"{base}/webhooks", headers=ph(limited)).status_code == 403


def test_campaigns_and_do_not_call_idempotent_write(api, keyed, db):
    t = keyed
    tok, ws = t["tok_a"], t["ws_a"]
    base = f"{V1}/workspaces/{ws}"
    from app.modules.campaigns import service as campaigns

    c = api.post(tok, f"/workspaces/{ws}/campaigns", {"name": "Forårstilbud", "purpose": "Gulvafslibning",
                                                       "call_days": list(campaigns.DAYS), "call_from": "09:00", "call_to": "17:00"}).json()
    listed = api.c.get(f"{base}/campaigns", headers=ph(t["key_a"])).json()["items"]
    assert listed[0]["id"] == c["id"] and listed[0]["status"] == "draft"
    assert not {"call_net_minor", "minute_net_minor", "legal_confirmation", "budget_net_minor"} & set(listed[0])
    reader = _issue(api, tok, ws, ["campaigns:read"])["key"]
    # POST needs campaigns:write and an Idempotency-Key
    r = api.c.post(f"{base}/do-not-call", json={"phone": "21222324"}, headers=ph(reader, **{"Idempotency-Key": "a"}))
    assert r.status_code == 403 and r.json()["required_scope"] == "campaigns:write"
    r = api.c.post(f"{base}/do-not-call", json={"phone": "21222324"}, headers=ph(t["key_a"]))
    assert r.status_code == 422 and r.json()["code"] == "idempotency_key_required"
    r = api.c.post(f"{base}/do-not-call", json={"phone": "21 22 23 24", "reason": "Bad os lade være"},
                   headers=ph(t["key_a"], **{"Idempotency-Key": "dnc-1"}))
    assert r.status_code == 201, r.text
    assert r.json()["phone"] == "+4521222324" and r.json()["source"] == "api"
    # same key + same body → the same answer, nothing new; same key + other body → 409
    again = api.c.post(f"{base}/do-not-call", json={"phone": "21 22 23 24", "reason": "Bad os lade være"},
                       headers=ph(t["key_a"], **{"Idempotency-Key": "dnc-1"}))
    assert again.status_code == 201 and again.json() == r.json()
    other = api.c.post(f"{base}/do-not-call", json={"phone": "21222325"}, headers=ph(t["key_a"], **{"Idempotency-Key": "dnc-1"}))
    assert other.status_code == 409 and other.json()["code"] == "idempotency_payload_mismatch"
    assert db.query(DoNotCall).count() == 1
    # a number already on the list is 200, not a second row; invalid numbers are 422
    dup = api.c.post(f"{base}/do-not-call", json={"phone": "+4521222324"}, headers=ph(t["key_a"], **{"Idempotency-Key": "dnc-2"}))
    assert dup.status_code == 200 and db.query(DoNotCall).count() == 1
    assert api.c.post(f"{base}/do-not-call", json={"phone": "12"}, headers=ph(t["key_a"], **{"Idempotency-Key": "dnc-3"})).status_code == 422
    assert api.c.get(f"{base}/do-not-call", headers=ph(reader)).json()["items"][0]["phone"] == "+45••••••24"
    # the internal list shows the entry with its source, and the app's staff list is unchanged otherwise
    assert api.get(tok, f"/workspaces/{ws}/do-not-call").json()["items"][0]["source"] == "api"
    assert any(a.action == "do_not_call.added" for a in db.query(AuditLog).all())


# --------------------------------------------------------------------------- rate limit

def test_rate_limit_429_with_retry_after(api, keyed):
    t = keyed
    clock = {"t": 1000.0}
    ratelimit.LIMITER = ratelimit.TokenBucketLimiter(read_per_minute=3, write_per_minute=1, clock=lambda: clock["t"])
    for i in range(3):
        r = api.c.get(f"{V1}/me", headers=ph(t["key_a"]))
        assert r.status_code == 200 and r.headers["x-ratelimit-remaining"] == str(2 - i) and r.headers["x-ratelimit-limit"] == "3"
    r = api.c.get(f"{V1}/me", headers=ph(t["key_a"]))
    assert r.status_code == 429 and r.json()["code"] == "rate_limited" and int(r.headers["retry-after"]) >= 1
    # another key has its own bucket; writes have their own (smaller) bucket; time refills
    assert api.c.get(f"{V1}/me", headers=ph(t["key_b"])).status_code == 200
    base = f"{V1}/workspaces/{t['ws_a']}/do-not-call"
    assert api.c.post(base, json={"phone": "21222324"}, headers=ph(t["key_a"], **{"Idempotency-Key": "r1"})).status_code == 201
    assert api.c.post(base, json={"phone": "21222325"}, headers=ph(t["key_a"], **{"Idempotency-Key": "r2"})).status_code == 429
    clock["t"] += 61
    assert api.c.get(f"{V1}/me", headers=ph(t["key_a"])).status_code == 200
    assert api.c.post(base, json={"phone": "21222325"}, headers=ph(t["key_a"], **{"Idempotency-Key": "r2"})).status_code == 201
    # the internal API is not rate limited by this middleware
    for _ in range(5):
        assert api.get(t["tok_a"], f"/workspaces/{t['ws_a']}").status_code == 200


# --------------------------------------------------------------------------- webhooks

@pytest.fixture
def receiver(monkeypatch):
    """A fake public receiver behind safe_fetch: records signed requests, can fail on demand."""
    seen: list[httpx.Request] = []
    behaviour = {"status": 204, "fail_times": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if behaviour["fail_times"] > 0:
            behaviour["fail_times"] -= 1
            return httpx.Response(503)
        return httpx.Response(behaviour["status"])

    monkeypatch.setattr(safe_fetch, "system_resolver", lambda host: DNS[host])
    monkeypatch.setattr(wd, "TRANSPORT", httpx.MockTransport(handler))
    return seen, behaviour


def _hook(api, t, events=("call.completed", "lead.created", "booking.created"), url=HOOK, key="wh-1"):
    return api.c.post(f"{V1}/workspaces/{t['ws_a']}/webhooks", json={"url": url, "events": list(events), "description": "CRM"},
                      headers=ph(t["key_a"], **{"Idempotency-Key": key}))


def test_webhook_crud_secret_once_and_validation(api, keyed, receiver, db):
    t = keyed
    base = f"{V1}/workspaces/{t['ws_a']}/webhooks"
    ev = api.c.get(f"{base}/events", headers=ph(t["key_a"])).json()["items"]
    assert {e["type"] for e in ev} == set(wd.EVENTS)
    r = _hook(api, t)
    assert r.status_code == 201, r.text
    w = r.json()
    secret = w["secret"]
    assert secret.startswith("whsec_") and w["active"] is True and w["events"] == ["call.completed", "booking.created", "lead.created"]
    # the replay never hands the secret out again; it is nowhere readable afterwards
    again = _hook(api, t)
    assert again.status_code == 201 and again.json()["secret"] == "" and again.json()["id"] == w["id"]
    row = db.get(WebhookEndpoint, uuid.UUID(w["id"]))
    assert secret.encode() not in bytes(row.secret_blob) and wd.get_secret(row) == secret
    assert secret not in api.c.get(base, headers=ph(t["key_a"])).text
    assert api.c.get(f"{base}/{w['id']}", headers=ph(t["key_a"])).json()["url"] == HOOK
    # validation: unknown event, non-public url, missing Idempotency-Key
    bad = _hook(api, t, events=("call.completed", "nope"), key="wh-2")
    assert bad.status_code == 422 and "nope" in bad.json()["message"]
    for url in ("http://hooks.example.dk/x", "https://intern.example.dk/hook", "https://localhost/hook"):
        assert _hook(api, t, url=url, key=f"u-{url}").json().get("code") == "url_not_allowed", url
    assert api.c.post(base, json={"url": HOOK, "events": ["lead.created"]}, headers=ph(t["key_a"])).status_code == 422
    # patch events/active; delete; isolation
    p = api.c.patch(f"{base}/{w['id']}", json={"events": ["lead.created"], "active": False}, headers=ph(t["key_a"])).json()
    assert p["events"] == ["lead.created"] and p["active"] is False and p["disabled_at"]
    p = api.c.patch(f"{base}/{w['id']}", json={"active": True}, headers=ph(t["key_a"])).json()
    assert p["active"] is True and p["disabled_at"] is None and p["failure_count"] == 0
    assert api.c.get(f"{base}/{w['id']}", headers=ph(t["key_b"])).status_code == 404
    assert api.c.delete(f"{base}/{w['id']}", headers=ph(t["key_a"])).status_code == 204
    assert api.c.get(base, headers=ph(t["key_a"])).json()["items"] == []


def test_webhook_signed_delivery_retries_and_auto_disable(api, keyed, receiver, telephony, db, monkeypatch):
    t = keyed
    seen, behaviour = receiver
    w = _hook(api, t).json()
    secret = w["secret"]
    # a phone call → call.completed + lead.created (conversation.ended is not subscribed)
    _phone_call(api, t)
    queued = db.query(OutboxEvent).filter_by(event_type=wd.EVENT_TYPE).all()
    assert sorted(e.payload["type"] for e in queued) == ["call.completed", "lead.created"]
    runner.drain()
    assert len(seen) == 2
    by_type = {json.loads(r.content)["type"]: r for r in seen}
    req = by_type["call.completed"]
    body = json.loads(req.content)
    assert body["id"].startswith("evt_") and body["workspace_id"] == t["ws_a"] and body["created_at"]
    assert body["data"]["summary"].startswith("Kunden vil") and body["data"]["from_number"] == "+4520304050"
    assert req.url.host == PUBLIC_IP and req.headers["host"] == "hooks.example.dk"
    assert wd.verify(secret, req.content, req.headers[wd.SIGNATURE_HEADER])
    assert not wd.verify("whsec_other", req.content, req.headers[wd.SIGNATURE_HEADER])
    assert not wd.verify(secret, req.content, req.headers[wd.SIGNATURE_HEADER], now=int(datetime.now(UTC).timestamp()) + 600)
    ep = api.c.get(f"{V1}/workspaces/{t['ws_a']}/webhooks/{w['id']}", headers=ph(t["key_a"])).json()
    assert ep["last_delivery_at"] and ep["failure_count"] == 0 and ep["last_error"] is None
    dl = api.c.get(f"{V1}/workspaces/{t['ws_a']}/webhooks/{w['id']}/deliveries", headers=ph(t["key_a"])).json()["items"]
    assert {d["status"] for d in dl} == {"done"} and {d["type"] for d in dl} == {"call.completed", "lead.created"}
    # the same event id on every retry; a 503 is retried with backoff, the endpoint counts the failure
    behaviour["fail_times"] = 1
    lead = api.post(t["tok_a"], f"/workspaces/{t['ws_a']}/leads", {"contact_name": "Ole", "need_summary": "Tilbud"})
    assert lead.status_code == 201
    ev = runner.process_once()
    assert ev.event_type == wd.EVENT_TYPE and ev.status == "queued" and ev.attempts == 1
    assert db.get(WebhookEndpoint, uuid.UUID(w["id"])).failure_count == 1
    first_id = json.loads(seen[-1].content)["id"]
    db.query(OutboxEvent).filter_by(id=ev.id).update({"next_attempt_at": datetime.now(UTC)})
    db.commit()
    assert runner.process_once().status == "done"
    assert json.loads(seen[-1].content)["id"] == first_id
    db.expire_all()
    assert db.get(WebhookEndpoint, uuid.UUID(w["id"])).failure_count == 0
    # a 4xx is final (no retry); after N consecutive failures the endpoint is switched off
    monkeypatch.setattr(get_settings(), "public_api_webhook_disable_after", 2)
    behaviour["status"] = 400
    for name in ("A", "B"):
        api.post(t["tok_a"], f"/workspaces/{t['ws_a']}/leads", {"contact_name": name, "need_summary": "x"})
    assert runner.process_once().status == "done"  # final failure: recorded, not retried
    assert runner.process_once().status == "done"
    db.expire_all()
    row = db.get(WebhookEndpoint, uuid.UUID(w["id"]))
    assert row.active is False and row.failure_count == 2 and "400" in row.last_error and row.disabled_reason
    # nothing more is queued for a disabled endpoint
    n = db.query(OutboxEvent).filter_by(event_type=wd.EVENT_TYPE).count()
    api.post(t["tok_a"], f"/workspaces/{t['ws_a']}/leads", {"contact_name": "C", "need_summary": "x"})
    assert db.query(OutboxEvent).filter_by(event_type=wd.EVENT_TYPE).count() == n


def test_booking_and_knowledge_events_reach_subscribed_endpoints_only(api, keyed, receiver, db):
    t = keyed
    seen, _ = receiver
    _hook(api, t, events=("booking.created", "booking.cancelled", "knowledge.version_approved"))
    type_id = _booking_setup(api, t)  # approves opening hours → knowledge.version_approved
    runner.drain()
    assert [json.loads(r.content)["type"] for r in seen] == ["knowledge.version_approved"]
    assert json.loads(seen[0].content)["data"]["kind"] == "opening_hours"
    tok, ws = t["tok_a"], t["ws_a"]
    slot = api.get(tok, f"/workspaces/{ws}/bookings/slots?type_id={type_id}").json()["items"][0]
    b = api.post(tok, f"/workspaces/{ws}/bookings", {"type_id": type_id, "start": slot["start"], "name": "Mette"}).json()
    api.post(tok, f"/workspaces/{ws}/bookings/{b['id']}/cancel", {})
    runner.drain()
    types = [json.loads(r.content)["type"] for r in seen]
    assert types == ["knowledge.version_approved", "booking.created", "booking.cancelled"]
    assert json.loads(seen[1].content)["data"]["booking_id"] == b["id"]
    # the Zapier/Make sinks never receive knowledge events (their declared list is unchanged)
    assert db.query(OutboxEvent).filter_by(event_type="webhook.deliver").count() == 0


# --------------------------------------------------------------------------- APP_SURFACE

def _app_for(monkeypatch, surface: str):
    monkeypatch.setenv("APP_SURFACE", surface)
    get_settings.cache_clear()
    from app.main import create_app

    try:
        return create_app()
    finally:
        get_settings.cache_clear()


def test_app_surface_mounts_only_what_it_should(monkeypatch):
    pub = TestClient(_app_for(monkeypatch, "public"))
    assert pub.get("/health/live").status_code == 200
    assert pub.get("/v1/openapi.json").json()["info"]["title"] == "Dialogbot Public API"
    assert pub.get("/v1/docs").status_code == 200
    assert pub.get("/v1/me").status_code == 401
    assert pub.get("/api/v1/openapi.json").status_code == 404
    assert pub.post("/api/v1/auth/login", json={"email": "a@b.dk", "password": "x"}).status_code == 404
    assert pub.post("/api/v1/webhooks/vapi", json={}).status_code == 404
    internal = TestClient(_app_for(monkeypatch, "internal"))
    assert internal.get("/api/v1/openapi.json").json()["info"]["title"] == "Dialogbot API"
    assert internal.get("/v1/openapi.json").status_code == 404
    assert internal.get("/v1/me").status_code == 404
    both = TestClient(_app_for(monkeypatch, "all"))
    assert both.get("/v1/openapi.json").status_code == 200 and both.get("/api/v1/openapi.json").status_code == 200
    # the internal document never lists public routes, and the public one is the committed contract
    assert not any(p.startswith("/v1/") for p in both.get("/api/v1/openapi.json").json()["paths"])
    spec = both.get("/v1/openapi.json").json()
    assert spec["info"]["version"] == "1.0.0" and "/workspaces/{workspace_id}/calls" in spec["paths"]
    assert spec["components"]["securitySchemes"]["ApiKey"]["scheme"] == "bearer"

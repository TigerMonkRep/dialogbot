"""Web widget: settings and readiness, origin allowlist (CORS + CSP frame-ancestors), frame-only writes,
visitor tokens, multi-turn AI replies from approved knowledge, spend limits, tenant isolation, setup check."""
from __future__ import annotations

import pytest
from sqlalchemy import select

from app.config import get_settings
from app.models import AiUsage, AuditLog, Conversation, WebchatSettings
from app.modules.ai import provider as ai_provider
from app.modules.ai.provider import FakeProvider
from app.modules.webchat import service as webchat

SITE = "https://www.fjordgulv.example"
API = "http://localhost:8000"  # PUBLIC_BASE_URL default in tests
PUB = "/api/v1/public/webchat"


@pytest.fixture
def fake(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "fake")
    get_settings.cache_clear()
    p = FakeProvider(get_settings())
    ai_provider.set_provider_override(p)
    yield p
    ai_provider.set_provider_override(None)
    get_settings.cache_clear()


def _approve(api, tok, ws, title="Afslibning"):
    it = api.knowledge(tok, ws, "service", title, {"price_net_minor": 14500})
    api.submit(tok, ws, it["open_draft"]["id"])
    assert api.approve(tok, ws, it["open_draft"]["id"]).status_code == 200


def _settings(api, tok, ws):
    r = api.get(tok, f"/workspaces/{ws}/webchat")
    assert r.status_code == 200, r.text
    return r.json()


def _enable(api, tok, ws, origins=(SITE,), enabled=True, greeting=""):
    s = _settings(api, tok, ws)
    return api.put(tok, f"/workspaces/{ws}/webchat",
                   {"expected_version": s["version"], "enabled": enabled, "allowed_origins": list(origins), "greeting": greeting})


@pytest.fixture
def live(api, two_workspaces, fake):
    t = two_workspaces
    _approve(api, t["tok_a"], t["ws_a"])
    r = _enable(api, t["tok_a"], t["ws_a"], origins=[SITE + "/", "https://Shop.Fjordgulv.example"])
    assert r.status_code == 200, r.text
    return t | {"key": r.json()["widget_key"]}


def _start(client, key, origin=API):
    headers = {"origin": origin} if origin else {}
    return client.post(f"{PUB}/{key}/conversations", json={"host_origin": SITE}, headers=headers)


def _say(client, key, conv, text, token=None, origin=API):
    headers = {"x-visitor-token": token if token is not None else conv["visitor_token"]}
    if origin:
        headers["origin"] = origin
    return client.post(f"{PUB}/{key}/conversations/{conv['conversation_id']}/messages", json={"text": text}, headers=headers)


def test_settings_defaults_roles_and_readiness(api, two_workspaces, db):
    t = two_workspaces
    s = _settings(api, t["tok_a"], t["ws_a"])
    assert s["enabled"] is False and s["widget_key"].startswith("wk_") and s["allowed_origins"] == []
    assert "Fjord Gulvservice ApS" in s["effective_greeting"]
    assert s["widget_key"] in s["embed_code"] and "/api/v1/public/webchat/loader.js" in s["embed_code"]
    assert set(s["unavailable_reasons"]) == {"disabled", "no_allowed_origins", "ai_not_configured", "no_approved_knowledge"}
    # enabling without AI and approved knowledge is refused with reasons
    r = _enable(api, t["tok_a"], t["ws_a"])
    assert r.status_code == 409 and r.json()["code"] == "webchat_not_ready"
    assert set(r.json()["reasons"]) == {"ai_not_configured", "no_approved_knowledge"}
    staff = api.add_member(t["tok_a"], t["ws_a"], "staff@testmail.dk", "staff")
    reader = api.add_member(t["tok_a"], t["ws_a"], "reader@testmail.dk", "reader")
    assert api.get(staff, f"/workspaces/{t['ws_a']}/webchat").status_code == 200
    assert api.get(reader, f"/workspaces/{t['ws_a']}/webchat").status_code == 403
    assert _enable(api, staff, t["ws_a"], enabled=False).status_code == 403
    assert api.get(t["tok_a"], f"/workspaces/{t['ws_b']}/webchat").status_code == 404


def test_origin_validation_and_normalisation(api, two_workspaces):
    t = two_workspaces
    for bad in ("http://www.example.dk", "https://example.dk/side", "ftp://x.dk", "example.dk", "https://u:p@x.dk"):
        r = _enable(api, t["tok_a"], t["ws_a"], origins=[bad], enabled=False)
        assert r.status_code == 422, bad
    r = _enable(api, t["tok_a"], t["ws_a"], origins=["https://WWW.Example.dk/", "https://www.example.dk", "http://localhost:3000"],
                enabled=False)
    assert r.status_code == 200 and r.json()["allowed_origins"] == ["http://localhost:3000", "https://www.example.dk"]
    stale = api.put(t["tok_a"], f"/workspaces/{t['ws_a']}/webchat",
                    {"expected_version": 1, "enabled": False, "allowed_origins": [], "greeting": ""})
    assert stale.status_code == 409 and stale.json()["code"] == "version_conflict"


def test_enable_is_audited_and_status_uses_cors_allowlist(api, client, live, db):
    s = db.scalar(select(WebchatSettings))
    assert s.enabled and s.allowed_origins == ["https://shop.fjordgulv.example", SITE]
    assert db.scalar(select(AuditLog).where(AuditLog.action == "webchat.updated")).after["enabled"] is True
    ok = client.get(f"{PUB}/{live['key']}/status", headers={"origin": SITE})
    assert ok.json() == {"available": True} and ok.headers["access-control-allow-origin"] == SITE
    other = client.get(f"{PUB}/{live['key']}/status", headers={"origin": "https://evil.example"})
    assert other.json() == {"available": False} and "access-control-allow-origin" not in other.headers
    assert client.get(f"{PUB}/wk_doesnotexist123/status", headers={"origin": SITE}).json() == {"available": False}
    assert client.get(f"{PUB}/loader.js").headers["content-type"].startswith("application/javascript")


def test_frame_csp_and_install_evidence(client, live, db):
    r = client.get(f"{PUB}/{live['key']}/frame", headers={"referer": SITE + "/kontakt", "sec-fetch-dest": "document"})
    csp = r.headers["content-security-policy"]
    assert f"frame-ancestors https://shop.fjordgulv.example {SITE};" in csp and "script-src 'self'" in csp
    assert db.scalar(select(WebchatSettings)).last_seen_at is None  # top-level visit is not evidence
    client.get(f"{PUB}/{live['key']}/frame", headers={"referer": "https://evil.example/", "sec-fetch-dest": "iframe"})
    db.expire_all()
    assert db.scalar(select(WebchatSettings)).last_seen_at is None
    client.get(f"{PUB}/{live['key']}/frame", headers={"referer": SITE + "/", "sec-fetch-dest": "iframe"})
    db.expire_all()
    s = db.scalar(select(WebchatSettings))
    assert s.last_seen_origin == SITE and s.last_seen_at is not None


def test_conversation_multi_turn_from_approved_knowledge(client, api, live, fake, db):
    assert _start(client, live["key"], origin=None).status_code == 403
    assert _start(client, live["key"], origin=SITE).status_code == 403  # the customer's page itself cannot write
    r = _start(client, live["key"])
    assert r.status_code == 201, r.text
    conv = r.json()
    first = _say(client, live["key"], conv, "Hvad koster afslibning?")
    assert first.status_code == 200, first.text
    assert first.json()["reply"]["text"] == "[fake] svar på: Hvad koster afslibning?"
    assert "Afslibning" in fake.last_system and "14500" in fake.last_system
    _say(client, live["key"], conv, "Og lak?")
    assert [m["role"] for m in fake.last_messages] == ["user", "assistant", "user"]
    assert _say(client, live["key"], conv, "hej", token="forkert").status_code == 401
    assert _say(client, live["key"], conv, "hej", origin=SITE).status_code == 403
    hist = client.get(f"{PUB}/{live['key']}/conversations/{conv['conversation_id']}/messages",
                      headers={"x-visitor-token": conv["visitor_token"]}).json()
    assert [m["role"] for m in hist["messages"]] == ["visitor", "assistant", "visitor", "assistant"]
    assert hist["remaining_messages"] == webchat.MAX_VISITOR_MESSAGES - 2
    usage = db.scalars(select(AiUsage)).all()
    assert len(usage) == 2 and {u.purpose for u in usage} == {"webchat"} and all(u.user_id is None for u in usage)
    c = db.scalar(select(Conversation))
    assert c.origin == SITE and c.visitor_token_digest != conv["visitor_token"]
    # the workspace sees the conversation; the other workspace does not
    lst = api.get(live["tok_a"], f"/workspaces/{live['ws_a']}/conversations").json()
    assert lst["total"] == 1 and lst["items"][0]["preview"] == "Hvad koster afslibning?"
    detail = api.get(live["tok_a"], f"/workspaces/{live['ws_a']}/conversations/{conv['conversation_id']}").json()
    assert len(detail["messages"]) == 4
    assert api.get(live["tok_b"], f"/workspaces/{live['ws_b']}/conversations").json()["total"] == 0
    assert api.get(live["tok_b"], f"/workspaces/{live['ws_b']}/conversations/{conv['conversation_id']}").status_code == 404


def test_refusal_is_masked_in_widget(client, live):
    conv = _start(client, live["key"]).json()
    body = _say(client, live["key"], conv, "AFVIS dette").json()
    assert body["refused"] is True and "kan jeg desværre ikke" in body["reply"]["text"]


def test_other_widget_key_cannot_read_conversation(client, api, live, fake):
    _approve(api, live["tok_b"], live["ws_b"], "Kaffe")
    key_b = _enable(api, live["tok_b"], live["ws_b"], origins=["https://havnebord.example"]).json()["widget_key"]
    conv = _start(client, live["key"]).json()
    r = client.get(f"{PUB}/{key_b}/conversations/{conv['conversation_id']}/messages",
                   headers={"x-visitor-token": conv["visitor_token"]})
    assert r.status_code == 401


def test_limits(client, live, monkeypatch):
    monkeypatch.setattr(webchat, "MAX_VISITOR_MESSAGES", 2)
    conv = _start(client, live["key"]).json()
    assert _say(client, live["key"], conv, "1").status_code == 200
    assert _say(client, live["key"], conv, "2").status_code == 200
    r = _say(client, live["key"], conv, "3")
    assert r.status_code == 429 and r.json()["code"] == "conversation_limit"
    assert _say(client, live["key"], conv, "x" * 1001).status_code == 422
    monkeypatch.setenv("WEBCHAT_DAILY_REPLY_LIMIT", "2")
    get_settings.cache_clear()
    conv2 = _start(client, live["key"]).json()
    r = _say(client, live["key"], conv2, "hej")
    assert r.status_code == 429 and r.json()["code"] == "daily_limit"
    monkeypatch.setattr(webchat, "MAX_NEW_CONVERSATIONS_PER_HOUR", 2)
    r = _start(client, live["key"])
    assert r.status_code == 429 and r.json()["code"] == "rate_limited"


def test_disabled_and_rotated_widget_stop_working(client, api, live):
    conv = _start(client, live["key"]).json()
    assert _enable(api, live["tok_a"], live["ws_a"], enabled=False).status_code == 200
    assert _start(client, live["key"]).json()["code"] == "webchat_unavailable"
    assert _say(client, live["key"], conv, "hej").status_code == 409
    new_key = api.post(live["tok_a"], f"/workspaces/{live['ws_a']}/webchat/rotate-key").json()["widget_key"]
    assert new_key != live["key"]
    assert client.get(f"{PUB}/{live['key']}/frame").status_code == 404


def test_setup_check_needs_real_provider_and_evidence(client, api, live, monkeypatch):
    ws, tok = live["ws_a"], live["tok_a"]
    # simulated AI can never pass an integration check
    assert api.post(tok, f"/workspaces/{ws}/setup/checks/webchat.widget/run").status_code == 501
    monkeypatch.setenv("AI_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-not-a-real-key")
    get_settings.cache_clear()
    r = api.post(tok, f"/workspaces/{ws}/setup/checks/webchat.widget/run")
    assert r.status_code == 200 and r.json()["status"] == "failed"  # never opened on the site yet
    client.get(f"{PUB}/{live['key']}/frame", headers={"referer": SITE + "/", "sec-fetch-dest": "iframe"})
    r = api.post(tok, f"/workspaces/{ws}/setup/checks/webchat.widget/run")
    assert r.json()["status"] == "passed" and r.json()["evidence"]["last_seen_origin"] == SITE
    _enable(api, tok, ws, enabled=False)  # changing settings makes the result stale
    latest = next(c for c in api.get(tok, f"/workspaces/{ws}/setup/checks/history").json()["items"]
                  if c["check_key"] == "webchat.widget")
    assert latest["status"] == "stale" and latest["stale_reason"] == "webchat.updated"

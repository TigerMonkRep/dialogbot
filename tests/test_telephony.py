"""Vapi voice webhook: authentication, number→workspace mapping, transient assistant built only from
approved knowledge, idempotent end-of-call reports into phone conversations, leads and tasks."""
from __future__ import annotations

import pytest
from sqlalchemy import select

from app.config import get_settings
from app.models import Call, Conversation, ConversationMessage, Lead, Task, WebhookEvent

URL = "/api/v1/webhooks/vapi"
SECRET = "vapi-test-secret-0123456789abcdef"
NUMBER = "+4570123456"


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setenv("VAPI_SERVER_SECRET", SECRET)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _post(client, message, *, auth=f"Bearer {SECRET}", header=None):
    h = {"content-type": "application/json"}
    if auth:
        h["authorization"] = auth
    if header:
        h["x-vapi-secret"] = header
    return client.post(URL, json={"message": message}, headers=h)


def _setup(api, t, *, approve=True):
    tok, ws = t["tok_a"], t["ws_a"]
    if approve:
        it = api.knowledge(tok, ws, "service", "Afslibning", {"price_net_minor": 14500})
        api.submit(tok, ws, it["open_draft"]["id"])
        api.approve(tok, ws, it["open_draft"]["id"])
    api.knowledge(tok, ws, "fact", "HEMMELIG-KLADDE", {"text": "x"})
    r = api.post(tok, f"/workspaces/{ws}/phone-numbers", {"e164": "+45 70 12 34 56", "provider_number_id": "pn_123",
                                                          "label": "Hovednummer"})
    assert r.status_code == 201, r.text
    return r.json()


def _report(call_id="call_1", *, caller="+4520304050", messages=None, number_id="pn_123"):
    return {"type": "end-of-call-report", "endedReason": "customer-ended-call",
            "call": {"id": call_id, "phoneNumberId": number_id, "customer": {"number": caller},
                     "startedAt": "2026-09-24T08:00:00Z", "endedAt": "2026-09-24T08:02:30Z"},
            "analysis": {"summary": "Kunden vil have tilbud på afslibning af 65 m²."},
            "cost": 0.23,
            "artifact": {"messages": messages if messages is not None else [
                {"role": "system", "message": "SYSTEMPROMPT"},
                {"role": "bot", "message": "Hej, du har ringet til Fjord."},
                {"role": "user", "message": "Hvad koster afslibning?"},
                {"role": "tool_calls", "message": ""},
                {"role": "bot", "message": "145 kroner pr. kvadratmeter."}]}}


def test_not_configured_and_auth(client, api, two_workspaces, monkeypatch):
    monkeypatch.delenv("VAPI_SERVER_SECRET", raising=False)
    get_settings.cache_clear()
    assert _post(client, {"type": "status-update"}).status_code == 503
    caps = {c["key"]: c["status"] for c in api.get(two_workspaces["tok_a"], "/integrations/capabilities").json()["items"]}
    assert caps["telephony.inbound"] == "not_implemented"
    monkeypatch.setenv("VAPI_SERVER_SECRET", SECRET)
    get_settings.cache_clear()
    assert _post(client, {"type": "status-update"}, auth=None).status_code == 401
    assert _post(client, {"type": "status-update"}, auth="Bearer wrong").status_code == 401
    assert _post(client, {"type": "status-update"}).json()["outcome"] == "ignored"
    assert _post(client, {"type": "status-update"}, auth=None, header=SECRET).status_code == 200  # legacy header
    get_settings.cache_clear()


def test_number_management_roles_and_validation(api, two_workspaces, configured):
    t = two_workspaces
    n = _setup(api, t)
    assert n["e164"] == NUMBER and n["provider_number_id"] == "pn_123"
    assert api.post(t["tok_a"], f"/workspaces/{t['ws_a']}/phone-numbers", {"e164": "70123456"}).status_code == 422
    assert api.post(t["tok_b"], f"/workspaces/{t['ws_b']}/phone-numbers", {"e164": NUMBER}).json()["code"] == "number_taken"
    staff = api.add_member(t["tok_a"], t["ws_a"], "staff@testmail.dk", "staff")
    assert api.get(staff, f"/workspaces/{t['ws_a']}/phone-numbers").status_code == 200
    assert api.post(staff, f"/workspaces/{t['ws_a']}/phone-numbers", {"e164": "+4570999999"}).status_code == 403
    lst = api.get(t["tok_a"], f"/workspaces/{t['ws_a']}/phone-numbers").json()
    assert lst["configured"] is True and lst["webhook_url"].endswith("/api/v1/webhooks/vapi")
    assert api.get(t["tok_b"], f"/workspaces/{t['ws_b']}/phone-numbers").json()["items"] == []


def test_assistant_request_uses_only_approved_knowledge(client, api, two_workspaces, configured):
    _setup(api, two_workspaces)
    r = _post(client, {"type": "assistant-request", "call": {"id": "c", "phoneNumberId": "pn_123"}})
    a = r.json()["assistant"]
    system = a["model"]["messages"][0]["content"]
    assert "Afslibning" in system and "HEMMELIG-KLADDE" not in system and "telefonopkald" in system
    assert a["firstMessage"].startswith("Hej, du har ringet til Fjord Gulvservice ApS") and "digital assistent" in a["firstMessage"]
    assert a["model"]["provider"] == "anthropic" and a["model"]["model"] == get_settings().ai_model_id
    # mapping by E.164 works too; unknown numbers get an error the provider can speak/handle
    by_number = _post(client, {"type": "assistant-request", "phoneNumber": {"number": NUMBER}, "call": {"id": "c2"}})
    assert "assistant" in by_number.json()
    assert "error" in _post(client, {"type": "assistant-request", "phoneNumber": {"number": "+4511111111"}}).json()


def test_danish_transcriber_voice_and_speaking_style(client, api, two_workspaces, configured, monkeypatch):
    t = two_workspaces
    n = _setup(api, t)
    a = _post(client, {"type": "assistant-request", "call": {"phoneNumberId": "pn_123"}}).json()["assistant"]
    assert a["transcriber"] == {"provider": "deepgram", "model": "nova-3", "language": "da"}
    assert "voice" not in a  # no voice chosen and no VAPI_VOICE_JSON: provider default
    assert "dansk" in a["model"]["messages"][0]["content"] and n["voice"] is None
    url = f"/api/v1/workspaces/{t['ws_a']}/phone-numbers/{n['id']}"
    bad = api.c.patch(url, json={"voice_id": "not an id!"}, headers=api.h(t["tok_a"]))
    assert bad.status_code == 422 and bad.json()["field_errors"][0]["field"] == "voice_id"
    assert api.c.patch(url, json={"voice_model": "gpt-voice"}, headers=api.h(t["tok_a"])).status_code == 422
    r = api.c.patch(url, json={"voice_id": "AbCdEf1234567890", "speaking_style": "Brug gerne jyske vendinger."},
                    headers=api.h(t["tok_a"]))
    assert r.status_code == 200 and r.json()["voice"]["voiceId"] == "AbCdEf1234567890"
    a = _post(client, {"type": "assistant-request", "call": {"phoneNumberId": "pn_123"}}).json()["assistant"]
    assert a["voice"] == {"provider": "11labs", "voiceId": "AbCdEf1234567890", "model": "eleven_multilingual_v2"}
    assert "Brug gerne jyske vendinger." in a["model"]["messages"][0]["content"]
    api.c.patch(url, json={"voice_model": "eleven_flash_v2_5"}, headers=api.h(t["tok_a"]))
    a = _post(client, {"type": "assistant-request", "call": {"phoneNumberId": "pn_123"}}).json()["assistant"]
    assert a["voice"]["language"] == "da"  # only Flash v2.5 takes an explicit language
    # environment overrides: transcriber JSON replaces the default; a number's own voice beats VAPI_VOICE_JSON
    monkeypatch.setenv("VAPI_TRANSCRIBER_JSON", '{"provider": "azure", "language": "da-DK"}')
    monkeypatch.setenv("VAPI_VOICE_JSON", '{"provider": "azure", "voiceId": "da-DK-ChristelNeural"}')
    get_settings.cache_clear()
    a = _post(client, {"type": "assistant-request", "call": {"phoneNumberId": "pn_123"}}).json()["assistant"]
    assert a["transcriber"]["provider"] == "azure" and a["voice"]["provider"] == "11labs"
    api.c.patch(url, json={"voice_id": ""}, headers=api.h(t["tok_a"]))
    a = _post(client, {"type": "assistant-request", "call": {"phoneNumberId": "pn_123"}}).json()["assistant"]
    assert a["voice"]["voiceId"] == "da-DK-ChristelNeural"
    # a staff member cannot change the voice
    staff = api.add_member(t["tok_a"], t["ws_a"], "staff2@testmail.dk", "staff")
    assert api.c.patch(url, json={"voice_id": "AbCdEf1234567890"}, headers=api.h(staff)).status_code == 403


def test_assistant_request_without_knowledge_or_inactive_number(client, api, two_workspaces, configured):
    t = two_workspaces
    n = _setup(api, t, approve=False)
    assert "error" in _post(client, {"type": "assistant-request", "call": {"phoneNumberId": "pn_123"}}).json()
    api.c.patch(f"/api/v1/workspaces/{t['ws_a']}/phone-numbers/{n['id']}", json={"active": False}, headers=api.h(t["tok_a"]))
    assert "error" in _post(client, {"type": "assistant-request", "call": {"phoneNumberId": "pn_123"}}).json()


def test_end_of_call_creates_conversation_lead_task_idempotently(client, api, two_workspaces, configured, db):
    _setup(api, two_workspaces)
    r = _post(client, _report())
    assert r.json() == {"received": True, "duplicate": False, "outcome": "applied"}
    again = _post(client, _report())
    assert again.json()["duplicate"] is True
    call = db.scalar(select(Call))
    assert (call.duration_seconds, call.from_number, call.to_number, call.cost_usd_micros) == (150, "+4520304050", NUMBER, 230000)
    conv = db.scalar(select(Conversation))
    assert conv.channel == "phone" and conv.origin == "+4520304050" and conv.visitor_message_count == 1
    texts = [(m.role, m.text) for m in db.scalars(select(ConversationMessage).order_by(ConversationMessage.created_at))]
    assert ("visitor", "Hvad koster afslibning?") in texts and all("SYSTEMPROMPT" not in x for _, x in texts)
    lead = db.scalar(select(Lead))
    assert lead.source == "phone" and lead.contact_phone == "+4520304050" and "65 m²" in lead.need_summary
    assert db.scalar(select(Task)).title == "Ring tilbage til +4520304050"
    assert len(db.scalars(select(WebhookEvent).where(WebhookEvent.provider == "vapi")).all()) == 1
    # visible in the workspace inbox and lead list
    t = two_workspaces
    assert api.get(t["tok_a"], f"/workspaces/{t['ws_a']}/conversations").json()["items"][0]["channel"] == "phone"
    assert api.get(t["tok_a"], f"/workspaces/{t['ws_a']}/calls").json()["items"][0]["duration_seconds"] == 150
    assert api.get(t["tok_b"], f"/workspaces/{t['ws_b']}/calls").json()["items"] == []


def test_silent_or_anonymous_calls_make_no_lead_and_unknown_numbers_are_unmatched(client, api, two_workspaces, configured, db):
    _setup(api, two_workspaces)
    _post(client, _report("call_silent", messages=[{"role": "bot", "message": "Hej?"}]))
    _post(client, _report("call_anon", caller=None))
    assert db.scalars(select(Lead)).all() == []
    r = _post(client, _report("call_x", number_id="pn_unknown"))
    assert r.json()["outcome"] == "unmatched"
    assert len(db.scalars(select(Call)).all()) == 2


def test_setup_checks_need_a_real_call(client, api, two_workspaces, configured):
    t = two_workspaces
    _setup(api, t)
    base = f"/workspaces/{t['ws_a']}/setup/checks"
    assert api.post(t["tok_a"], f"{base}/telephony.test_call/run").json()["status"] == "failed"
    _post(client, _report())
    r = api.post(t["tok_a"], f"{base}/telephony.forwarding/run").json()
    assert r["status"] == "passed" and r["evidence"]["active_numbers"] == [NUMBER]


def test_voice_preview(api, two_workspaces, configured, monkeypatch):
    import httpx

    t = two_workspaces
    n = _setup(api, t)
    url = f"/workspaces/{t['ws_a']}/phone-numbers/{n['id']}/voice-preview"
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    get_settings.cache_clear()
    assert api.post(t["tok_a"], url, {"voice_id": "AbCdEf1234567890"}).json()["code"] == "voice_preview_not_configured"
    monkeypatch.setenv("ELEVENLABS_API_KEY", "el-test-key")
    get_settings.cache_clear()
    seen = {}

    def fake_post(u, **kw):
        seen.update(url=u, **kw)
        return httpx.Response(200, content=b"ID3-mp3", request=httpx.Request("POST", u))

    monkeypatch.setattr(httpx, "post", fake_post)
    assert api.post(t["tok_a"], url, {}).status_code == 422  # no voice chosen yet
    assert api.post(t["tok_a"], url, {"voice_id": "bad id"}).status_code == 422
    r = api.post(t["tok_a"], url, {"voice_id": "AbCdEf1234567890", "voice_model": "eleven_flash_v2_5"})
    assert r.status_code == 200 and r.headers["content-type"] == "audio/mpeg" and r.content == b"ID3-mp3"
    assert seen["url"].endswith("/v1/text-to-speech/AbCdEf1234567890") and seen["headers"]["xi-api-key"] == "el-test-key"
    assert seen["json"]["model_id"] == "eleven_flash_v2_5" and "Fjord Gulvservice" in seen["json"]["text"]
    staff = api.add_member(t["tok_a"], t["ws_a"], "staff3@testmail.dk", "staff")
    assert api.post(staff, url, {"voice_id": "AbCdEf1234567890"}).status_code == 403
    monkeypatch.setattr(httpx, "post", lambda u, **kw: httpx.Response(401, request=httpx.Request("POST", u)))
    assert api.post(t["tok_a"], url, {"voice_id": "AbCdEf1234567890"}).json()["code"] == "voice_preview_failed"
    get_settings.cache_clear()

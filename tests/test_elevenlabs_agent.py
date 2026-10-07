"""ElevenLabs Agents as a trial call engine: the initiation webhook builds the same prompt, greeting and voice as
Vapi gets; the HMAC-signed post-call webhook stores the call like a Vapi end-of-call report."""
from __future__ import annotations

import hashlib
import hmac
import json
import time

import pytest
from sqlalchemy import select

from app.config import get_settings
from app.models import Call, ConversationMessage, Lead

from .test_telephony import _setup

INIT = "/api/v1/webhooks/elevenlabs/init"
POST = "/api/v1/webhooks/elevenlabs/post-call"
AGENT_SECRET = "el-agent-secret-0123456789"
HOOK_SECRET = "wsec_el-hook-secret-0123456789"


@pytest.fixture
def el(monkeypatch):
    monkeypatch.setenv("VAPI_SERVER_SECRET", "vapi-test-secret-0123456789abcdef")
    monkeypatch.setenv("ELEVENLABS_AGENT_SECRET", AGENT_SECRET)
    monkeypatch.setenv("ELEVENLABS_WEBHOOK_SECRET", HOOK_SECRET)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _signed(body: dict, *, secret=HOOK_SECRET, ts=None) -> tuple[bytes, str]:
    raw = json.dumps(body).encode()
    ts = str(ts or int(time.time()))
    return raw, f"t={ts},v0=" + hmac.new(secret.encode(), f"{ts}.".encode() + raw, hashlib.sha256).hexdigest()


def test_initiation_gives_the_workspace_prompt_and_greeting(client, api, two_workspaces, el):
    _setup(api, two_workspaces)
    body = {"caller_id": "+4520304050", "called_number": "+4570123456", "call_sid": "CA1", "agent_id": "ag",
            "conversation_id": "conv_1"}
    assert client.post(INIT, json=body).status_code == 401
    assert client.post(INIT, json=body, headers={"x-dialogbot-secret": "wrong"}).status_code == 401
    r = client.post(INIT, json=body, headers={"x-dialogbot-secret": AGENT_SECRET}).json()
    assert r["type"] == "conversation_initiation_client_data"
    agent = r["conversation_config_override"]["agent"]
    assert agent["language"] == "da" and "Afslibning" in agent["prompt"]["prompt"]
    assert "HEMMELIG-KLADDE" not in agent["prompt"]["prompt"] and agent["first_message"]
    assert "tts" not in r["conversation_config_override"]  # the agent's own voice
    unknown = client.post(INIT, json=body | {"called_number": "+4511111111"}, headers={"x-dialogbot-secret": AGENT_SECRET})
    assert "ikke i brug" in unknown.json()["conversation_config_override"]["agent"]["first_message"]


def test_post_call_is_signed_and_stored_like_a_vapi_report(client, api, two_workspaces, el, db):
    _setup(api, two_workspaces)
    payload = {"type": "post_call_transcription", "event_timestamp": int(time.time()), "data": {
        "agent_id": "ag", "conversation_id": "conv_42", "status": "done",
        "transcript": [{"role": "agent", "message": "Hej, du har ringet til Fjord.", "time_in_call_secs": 0},
                       {"role": "user", "message": "Jeg vil gerne have et tilbud.", "time_in_call_secs": 3}],
        "metadata": {"start_time_unix_secs": 1_791_360_000, "call_duration_secs": 95,
                     "phone_call": {"type": "twilio", "direction": "inbound", "agent_number": "+4570123456",
                                    "external_number": "+4520304050", "call_sid": "CA42"}},
        "analysis": {"transcript_summary": "Kunden vil have et tilbud på afslibning."}}}
    raw, sig = _signed(payload)
    assert client.post(POST, content=raw, headers={"content-type": "application/json"}).status_code == 401
    bad = _signed(payload, secret="other")[1]
    assert client.post(POST, content=raw, headers={"elevenlabs-signature": bad}).status_code == 401
    old = _signed(payload, ts=int(time.time()) - 3 * 3600)
    assert client.post(POST, content=old[0], headers={"elevenlabs-signature": old[1]}).status_code == 401
    r = client.post(POST, content=raw, headers={"elevenlabs-signature": sig, "content-type": "application/json"})
    assert r.status_code == 200 and r.json()["outcome"] == "applied"
    call = db.scalar(select(Call).where(Call.provider_call_id == "el_conv_42"))
    assert call.duration_seconds == 95 and call.from_number == "+4520304050"
    assert call.summary == "Kunden vil have et tilbud på afslibning."
    texts = [m.text for m in db.scalars(select(ConversationMessage).where(
        ConversationMessage.conversation_id == call.conversation_id))]
    assert texts == ["Hej, du har ringet til Fjord.", "Jeg vil gerne have et tilbud."]
    assert db.scalar(select(Lead).where(Lead.conversation_id == call.conversation_id)) is not None
    again = client.post(POST, content=raw, headers={"elevenlabs-signature": sig, "content-type": "application/json"})
    assert again.json()["outcome"] == "duplicate"

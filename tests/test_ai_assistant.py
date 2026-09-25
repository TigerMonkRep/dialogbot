"""AI adapter: approved-knowledge-only prompt, per-workspace usage log, roles, tenant isolation,
not-configured and refusal handling. The Anthropic adapter is exercised with a stubbed SDK client."""
from __future__ import annotations

from types import SimpleNamespace

import anthropic
import httpx
import pytest
from sqlalchemy import select

from app.config import get_settings
from app.models import AiUsage
from app.modules.ai import provider as ai_provider
from app.modules.ai.provider import AnthropicProvider, FakeProvider
from app.modules.ai.service import PROMPT_VERSION


@pytest.fixture
def fake(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "fake")
    get_settings.cache_clear()
    p = FakeProvider(get_settings())
    ai_provider.set_provider_override(p)
    yield p
    ai_provider.set_provider_override(None)
    get_settings.cache_clear()


def _approved(api, tok, ws, kind, title, content):
    it = api.knowledge(tok, ws, kind, title, content)
    api.submit(tok, ws, it["open_draft"]["id"])
    assert api.approve(tok, ws, it["open_draft"]["id"]).status_code == 200
    return it


def _preview(api, tok, ws, msg="Hvad koster afslibning?"):
    return api.post(tok, f"/workspaces/{ws}/assistant/preview", {"message": msg})


def test_not_configured_is_501_and_logs_nothing(api, two_workspaces, db):
    t = two_workspaces
    get_settings.cache_clear()
    r = _preview(api, t["tok_a"], t["ws_a"])
    assert r.status_code == 501 and r.json()["code"] == "ai_not_configured"
    assert db.scalars(select(AiUsage)).all() == []
    caps = {c["key"]: c["status"] for c in api.get(t["tok_a"], "/integrations/capabilities").json()["items"]}
    assert caps["ai.assistant_preview"] == "not_implemented"
    assert caps["ai.conversation"] == "not_implemented"


def test_no_approved_knowledge_is_409_without_model_call(api, two_workspaces, fake, db):
    t = two_workspaces
    api.knowledge(t["tok_a"], t["ws_a"], "service", "Kladde", {"price_net_minor": 1})  # draft only
    r = _preview(api, t["tok_a"], t["ws_a"])
    assert r.status_code == 409 and r.json()["code"] == "no_approved_knowledge"
    assert fake.last_system is None
    assert db.scalars(select(AiUsage)).all() == []


def test_prompt_contains_only_approved_knowledge_and_usage_is_logged(api, two_workspaces, fake, db):
    t = two_workspaces
    tok, ws = t["tok_a"], t["ws_a"]
    item = _approved(api, tok, ws, "service", "Afslibning", {"price_net_minor": 14500})
    # a newer draft of the same item and a draft-only item must not reach the model
    api.post(tok, f"/workspaces/{ws}/knowledge/items/{item['id']}/drafts", {"title": "HEMMELIG-KLADDE", "content": {}})
    api.knowledge(tok, ws, "fact", "UGODKENDT-FAKTA", {"text": "x"})
    _approved(api, t["tok_b"], t["ws_b"], "fact", "ANDET-ARBEJDSRUM", {"text": "y"})

    r = _preview(api, tok, ws)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["reply"].startswith("[fake]") and body["refused"] is False
    assert body["prompt_version"] == PROMPT_VERSION
    assert "Afslibning" in fake.last_system and "14500" in fake.last_system
    for leaked in ("HEMMELIG-KLADDE", "UGODKENDT-FAKTA", "ANDET-ARBEJDSRUM"):
        assert leaked not in fake.last_system
    assert "Fjord Gulvservice ApS" in fake.last_system

    rows = db.scalars(select(AiUsage)).all()
    assert len(rows) == 1
    row = rows[0]
    assert str(row.workspace_id) == ws and row.outcome == "ok" and row.provider == "fake"
    assert row.prompt_version == PROMPT_VERSION and row.requested_model == "claude-opus-5"
    assert row.knowledge_revision == body["knowledge_revision"] and row.input_tokens > 0 and row.output_tokens == 12
    assert row.est_cost_usd_micros is not None and row.est_cost_usd_micros > 0


def test_usage_summary_is_per_workspace_and_admin_only(api, two_workspaces, fake):
    t = two_workspaces
    _approved(api, t["tok_a"], t["ws_a"], "fact", "Parkering", {"text": "Gratis"})
    _approved(api, t["tok_b"], t["ws_b"], "fact", "Åbent", {"text": "Altid"})
    for _ in range(2):
        assert _preview(api, t["tok_a"], t["ws_a"]).status_code == 200
    assert _preview(api, t["tok_b"], t["ws_b"]).status_code == 200

    a = api.get(t["tok_a"], f"/workspaces/{t['ws_a']}/ai/usage").json()
    b = api.get(t["tok_b"], f"/workspaces/{t['ws_b']}/ai/usage").json()
    assert a["totals"]["calls"] == 2 and b["totals"]["calls"] == 1
    assert a["groups"][0]["prompt_version"] == PROMPT_VERSION and a["groups"][0]["model"] == "claude-opus-5"
    # foreign workspace → 404, not a leak
    assert api.get(t["tok_a"], f"/workspaces/{t['ws_b']}/ai/usage").status_code == 404
    assert _preview(api, t["tok_a"], t["ws_b"]).status_code == 404

    staff = api.add_member(t["tok_a"], t["ws_a"], "staff@testmail.dk", "staff")
    reader = api.add_member(t["tok_a"], t["ws_a"], "reader@testmail.dk", "reader")
    assert api.get(staff, f"/workspaces/{t['ws_a']}/ai/usage").status_code == 403
    assert _preview(api, staff, t["ws_a"]).status_code == 200
    assert _preview(api, reader, t["ws_a"]).status_code == 403


def test_refusal_is_masked_and_logged(api, two_workspaces, fake, db):
    t = two_workspaces
    _approved(api, t["tok_a"], t["ws_a"], "fact", "Parkering", {"text": "Gratis"})
    body = _preview(api, t["tok_a"], t["ws_a"], "AFVIS dette").json()
    assert body["refused"] is True and body["stop_reason"] == "refusal"
    assert "kan jeg desværre ikke" in body["reply"]
    assert db.scalars(select(AiUsage.outcome)).all() == ["refused"]


def test_message_validation(api, two_workspaces, fake):
    t = two_workspaces
    assert _preview(api, t["tok_a"], t["ws_a"], "").status_code == 422
    assert _preview(api, t["tok_a"], t["ws_a"], "x" * 2001).status_code == 422


# --- Anthropic adapter with a stubbed SDK client ------------------------------------------------

class _StubMessages:
    def __init__(self, result):
        self.result, self.calls = result, []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def _stub_client(result):
    msgs = _StubMessages(result)
    return SimpleNamespace(beta=SimpleNamespace(messages=msgs)), msgs


def _response(text="Afslibning koster 145 kr.", stop="end_turn", model="claude-opus-5", iterations=None, details=None):
    usage = SimpleNamespace(input_tokens=1200, output_tokens=80, cache_creation_input_tokens=1000,
                            cache_read_input_tokens=0, iterations=iterations)
    content = [SimpleNamespace(type="thinking", thinking="..."), SimpleNamespace(type="text", text=text)]
    return SimpleNamespace(content=content, stop_reason=stop, model=model, usage=usage, stop_details=details,
                           _request_id="req_123")


@pytest.fixture
def anthropic_settings(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-not-a-real-key")
    get_settings.cache_clear()
    yield get_settings()
    ai_provider.set_provider_override(None)
    get_settings.cache_clear()


def test_anthropic_request_shape_and_usage(api, two_workspaces, anthropic_settings, db):
    t = two_workspaces
    _approved(api, t["tok_a"], t["ws_a"], "service", "Afslibning", {"price_net_minor": 14500})
    client, msgs = _stub_client(_response())
    ai_provider.set_provider_override(AnthropicProvider(anthropic_settings, client=client))

    body = _preview(api, t["tok_a"], t["ws_a"]).json()
    assert body["reply"] == "Afslibning koster 145 kr."  # thinking blocks are never returned
    kw = msgs.calls[0]
    assert kw["model"] == "claude-opus-5" and kw["max_tokens"] == 2048
    assert kw["system"][0]["cache_control"] == {"type": "ephemeral"} and "Afslibning" in kw["system"][0]["text"]
    assert kw["output_config"] == {"effort": "medium"}
    assert kw["betas"] == ["server-side-fallback-2026-07-01"] and kw["fallbacks"] == "default"
    assert "thinking" not in kw and kw["messages"] == [{"role": "user", "content": "Hvad koster afslibning?"}]

    row = db.scalars(select(AiUsage)).one()
    assert (row.provider, row.served_model, row.provider_request_id) == ("anthropic", "claude-opus-5", "req_123")
    assert (row.input_tokens, row.output_tokens, row.cache_creation_input_tokens) == (1200, 80, 1000)
    # 1200*5 + 1000*5*1.25 + 80*25 = 14250 µUSD
    assert row.est_cost_usd_micros == 14250


def test_anthropic_fallback_model_is_recorded_and_can_be_disabled(api, two_workspaces, anthropic_settings, db, monkeypatch):
    t = two_workspaces
    _approved(api, t["tok_a"], t["ws_a"], "fact", "Parkering", {"text": "Gratis"})
    it = [SimpleNamespace(type="message", model="claude-opus-5"), SimpleNamespace(type="fallback_message", model="claude-opus-4-8")]
    client, _ = _stub_client(_response(iterations=it))
    ai_provider.set_provider_override(AnthropicProvider(anthropic_settings, client=client))
    assert _preview(api, t["tok_a"], t["ws_a"]).json()["model"] == "claude-opus-4-8"
    row = db.scalars(select(AiUsage)).one()
    assert row.requested_model == "claude-opus-5" and row.served_model == "claude-opus-4-8"
    assert row.est_cost_usd_micros is None  # unpriced model → no guessed cost

    monkeypatch.setenv("AI_SERVER_FALLBACKS", "false")
    get_settings.cache_clear()
    client, msgs = _stub_client(_response())
    ai_provider.set_provider_override(AnthropicProvider(get_settings(), client=client))
    _preview(api, t["tok_a"], t["ws_a"])
    assert "fallbacks" not in msgs.calls[0] and "betas" not in msgs.calls[0]


def test_anthropic_refusal_and_errors(api, two_workspaces, anthropic_settings, db):
    t = two_workspaces
    _approved(api, t["tok_a"], t["ws_a"], "fact", "Parkering", {"text": "Gratis"})
    client, _ = _stub_client(_response(text="", stop="refusal", details=SimpleNamespace(category="general_harms")))
    ai_provider.set_provider_override(AnthropicProvider(anthropic_settings, client=client))
    assert _preview(api, t["tok_a"], t["ws_a"]).json()["refused"] is True

    req = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    rate = anthropic.RateLimitError("slow down", response=httpx.Response(429, request=req), body=None)
    client, _ = _stub_client(rate)
    ai_provider.set_provider_override(AnthropicProvider(anthropic_settings, client=client))
    r = _preview(api, t["tok_a"], t["ws_a"])
    assert r.status_code == 503 and r.json()["code"] == "ai_rate_limited"

    client, _ = _stub_client(anthropic.APIConnectionError(request=req))
    ai_provider.set_provider_override(AnthropicProvider(anthropic_settings, client=client))
    r = _preview(api, t["tok_a"], t["ws_a"])
    assert r.status_code == 502 and r.json()["code"] == "ai_provider_error"

    outcomes = [(o, e) for o, e in db.execute(select(AiUsage.outcome, AiUsage.error_code).order_by(AiUsage.created_at))]
    assert sorted(outcomes, key=str) == sorted([("refused", None), ("error", "ai_rate_limited"),
                                                ("error", "ai_provider_error")], key=str)


def test_config_fails_closed(monkeypatch):
    from app.config import Settings

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
        Settings(AI_PROVIDER="anthropic")
    with pytest.raises(ValueError, match="AI_PROVIDER=fake"):
        Settings(AI_PROVIDER="fake", APP_ENV="staging", SECRET_KEY="x" * 40, ENABLE_DEV_TOOLS=False)

"""Reception manuscript: roles, versioning, used in chat/phone prompts, AI disclosure in the greeting."""
from __future__ import annotations

import pytest

from app.config import get_settings
from app.modules.ai import provider as ai_provider
from app.modules.ai.provider import FakeProvider

SECRET = "vapi-test-secret-0123456789abcdef"


@pytest.fixture
def fake_ai(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "fake")
    monkeypatch.setenv("VAPI_SERVER_SECRET", SECRET)
    get_settings.cache_clear()
    p = FakeProvider(get_settings())
    ai_provider.set_provider_override(p)
    yield p
    ai_provider.set_provider_override(None)
    get_settings.cache_clear()


def test_script_roles_versioning_and_prompt(api, client, two_workspaces, fake_ai):
    t = two_workspaces
    tok, ws = t["tok_a"], t["ws_a"]
    base = f"/workspaces/{ws}/reception/script"
    assert api.get(tok, base).json()["version"] == 0
    sug = api.post(tok, f"{base}/suggestions", {}).json()
    assert sug["collect"] == ["navn", "adresse", "antal kvadratmeter"]
    body = {"expected_version": 0, "persona_name": "Sofie", "address_form": "De", "greeting": "Goddag, {virksomhed}.",
            "collect": ["navn", " ", "adresse"], "escalation": "vandskade", "avoid": "", "closing": "Tak."}
    staff = api.add_member(tok, ws, "staff-script@testmail.dk", "staff")
    assert api.c.put(f"/api/v1{base}", json=body, headers=api.h(staff)).status_code == 403
    r = api.c.put(f"/api/v1{base}", json=body, headers=api.h(tok))
    assert r.status_code == 200 and r.json()["version"] == 1 and r.json()["collect"] == ["navn", "adresse"]
    assert api.c.put(f"/api/v1{base}", json=body, headers=api.h(tok)).json()["code"] == "version_conflict"
    # The script shapes every channel's prompt …
    it = api.knowledge(tok, ws, "service", "Afslibning", {"price_net_minor": 14500})
    api.submit(tok, ws, it["open_draft"]["id"])
    api.approve(tok, ws, it["open_draft"]["id"])
    api.post(tok, f"/workspaces/{ws}/assistant/preview", {"message": "Hej"})
    assert "Sofie" in fake_ai.last_system and "De/Dem" in fake_ai.last_system and "vandskade" in fake_ai.last_system
    # … and the phone greeting, which always discloses that the caller talks to a machine.
    api.post(tok, f"/workspaces/{ws}/phone-numbers", {"e164": "+4570123456", "provider_number_id": "pn_script"})
    a = client.post("/api/v1/webhooks/vapi", json={"message": {"type": "assistant-request", "call": {"phoneNumberId": "pn_script"}}},
                    headers={"authorization": f"Bearer {SECRET}"}).json()["assistant"]
    assert a["firstMessage"] == "Goddag, Fjord Gulvservice ApS. Du taler med en digital assistent."
    ov = api.get(tok, f"/workspaces/{ws}/reception/overview").json()
    assert ov["script_configured"] is True and ov["channels"]["phone"]["numbers"][0]["e164"] == "+4570123456"
    assert api.get(t["tok_b"], f"/workspaces/{t['ws_b']}/reception/script").json()["version"] == 0

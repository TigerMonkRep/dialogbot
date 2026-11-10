"""QA X18 (voice-qa): "STT-sti: Soniox stt-rt-v6 konfigureret for alle virksomheder; replay af testoptagelser giver
korrekte navne/tal/tider".

Configuration and code path only – no network, no key, no call (qa-lead, wave 2). The production values of
VAPI_TRANSCRIBER_JSON / SONIOX_MODEL / SONIOX_API_KEY live on Render and are NOT read here (README: QA never reads
production config). What is proved:
  * with the documented switch (VAPI_TRANSCRIBER_JSON={"provider":"custom-transcriber","stt":"soniox"} +
    SONIOX_MODEL=stt-rt-v6) EVERY call path – inbound for any workspace, campaign, sales demo, Privat – routes the
    audio through our bridge with stt=soniox, and the bridge opens Soniox with model stt-rt-v6, Danish hints and the
    business's own terms;
  * what happens when the switch is off or the key is missing (the repo default).
Replay of the recorded fixtures through Soniox needs SONIOX_API_KEY and the network → blocked."""
from __future__ import annotations

import json
import uuid
from urllib.parse import parse_qs, urlparse

import pytest

from app.config import get_settings
from app.models import Workspace
from app.modules.stt import adapters
from app.modules.telephony import linden
from app.modules.telephony import vapi as vapi_mod
from tests.test_telephony import NUMBER, SECRET, _post, _setup  # noqa: F401

SONIOX_ALL = json.dumps({"provider": "custom-transcriber", "stt": "soniox"})


@pytest.fixture
def soniox_v6(monkeypatch):
    monkeypatch.setenv("VAPI_SERVER_SECRET", SECRET)
    monkeypatch.setenv("VAPI_TRANSCRIBER_JSON", SONIOX_ALL)
    monkeypatch.setenv("SONIOX_API_KEY", "soniox-test-key-not-real")
    monkeypatch.setenv("SONIOX_MODEL", "stt-rt-v6")
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://api.qa.invalid")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _bridge_params(transcriber: dict) -> dict:
    assert transcriber["provider"] == "custom-transcriber", transcriber
    url = transcriber["server"]["url"]
    assert urlparse(url).path.endswith("/api/v1/webhooks/vapi/transcriber"), url
    return parse_qs(urlparse(url).query)


def test_x18_every_workspace_inbound_goes_through_soniox_when_switched_on(client, api, two_workspaces, soniox_v6, db):
    t = two_workspaces
    _setup(api, t)  # ws A: approved knowledge + number pn_123
    it = api.knowledge(t["tok_b"], t["ws_b"], "service", "Brunch", {"price_net_minor": 19500})
    api.submit(t["tok_b"], t["ws_b"], it["open_draft"]["id"])
    api.approve(t["tok_b"], t["ws_b"], it["open_draft"]["id"])
    api.map_number(t["ws_b"], "+45 70 99 88 77", "pn_b")
    for pn, ws in (("pn_123", t["ws_a"]), ("pn_b", t["ws_b"])):
        r = _post(client, {"type": "assistant-request", "call": {"id": f"x18_{pn}", "phoneNumberId": pn,
                                                                    "customer": {"number": "+4520304050"}}})
        tr = r.json()["assistant"]["transcriber"]
        q = _bridge_params(tr)
        assert q.get("stt") == ["soniox"] and q.get("ws") == [ws], q
        assert "fallbackPlan" not in tr  # the bridge is the transcriber; no silent Deepgram path inside the call


def test_x18_campaign_sales_and_privat_paths_use_the_same_switch(client, api, two_workspaces, soniox_v6, db):
    ws = db.get(Workspace, uuid.UUID(two_workspaces["ws_a"]))
    for label, tr in (("campaign/sales demo", vapi_mod.transcriber_for(db, ws, extra=["Berle Pool", "Mette Hansen"])),
                      ("privat (no workspace)", vapi_mod.transcriber_for(db, None, extra=["Auto Centrum"]))):
        q = _bridge_params(tr)
        assert q.get("stt") == ["soniox"], (label, q)
    q = _bridge_params(vapi_mod.transcriber_for(db, ws, extra=["Berle Pool"]))
    assert "Berle Pool" in q.get("extra", []), "the call's own names must reach the recogniser"


def test_x18_bridge_opens_soniox_with_stt_rt_v6_danish_and_the_business_terms(soniox_v6):
    assert linden.chosen("soniox") == "soniox" and linden.configured("soniox")
    cfg = adapters.AdapterConfig(sample_rate=16000, vocabulary=[{"content": "Berle Pool"}, {"content": "Bærle"}],
                                 controlled=False, release_on_pause=True, language="da")
    a = adapters.make("soniox", cfg, on_event=lambda *_a, **_k: None)
    m = a.start_message()
    assert m["model"] == "stt-rt-v6", m["model"]
    assert m["language_hints"] == ["da"] and m["enable_endpoint_detection"] is True
    assert "Berle Pool" in m["context"]["terms"]
    assert a.supports_agent_text  # v6 feature available …
    assert "api_key" not in m  # key goes in the Authorization header, never in the start message


def test_x18_other_call_language_is_passed_to_soniox(soniox_v6, db, api, two_workspaces):
    ws = db.get(Workspace, uuid.UUID(two_workspaces["ws_a"]))
    q = _bridge_params(vapi_mod.transcriber_for(db, ws, lang="en"))
    assert q.get("lang") == ["en"]
    a = adapters.make("soniox", adapters.AdapterConfig(language="en"), on_event=lambda *_a, **_k: None)
    assert a.start_message()["language_hints"] == ["en"]


# --------------------------------------------------------------------------- the repo default (documented, not prod)

def test_x18_repo_default_is_not_soniox_v6(monkeypatch, db, api, two_workspaces):
    """Documents the code default: without the env switch every call uses Deepgram Nova-3 (+ Nova-2), and SONIOX_MODEL
    unset means stt-rt-v5. «Soniox stt-rt-v6 for alle» is therefore purely a Render env setting – see the report."""
    for k in ("VAPI_TRANSCRIBER_JSON", "SONIOX_MODEL", "VAPI_STT_BY_WORKSPACE_JSON"):
        monkeypatch.delenv(k, raising=False)
    get_settings.cache_clear()
    ws = db.get(Workspace, uuid.UUID(two_workspaces["ws_a"]))
    tr = vapi_mod.transcriber_for(db, ws)
    assert tr["provider"] == "deepgram" and tr["model"] == "nova-3"
    assert adapters.make("soniox", adapters.AdapterConfig(), api_key="x").requested_model == "stt-rt-v5"
    get_settings.cache_clear()


def test_x18_missing_soniox_key_falls_back_to_deepgram(monkeypatch, db, api, two_workspaces):
    """Switched on but without SONIOX_API_KEY: the call silently stays on Deepgram (documented: «Uden genkenderens
    nøgle forbliver opkaldet på produktionsruten»)."""
    monkeypatch.setenv("VAPI_TRANSCRIBER_JSON", SONIOX_ALL)
    monkeypatch.setenv("SONIOX_MODEL", "stt-rt-v6")
    monkeypatch.delenv("SONIOX_API_KEY", raising=False)
    get_settings.cache_clear()
    ws = db.get(Workspace, uuid.UUID(two_workspaces["ws_a"]))
    assert vapi_mod.transcriber_for(db, ws)["provider"] == "deepgram"
    get_settings.cache_clear()


# --------------------------------------------------------------------------- replay of the recorded fixtures

def test_x18_replay_of_recorded_fixtures_through_soniox_is_blocked_offline():
    pytest.skip("blocked: replay through Soniox needs SONIOX_API_KEY and the network (wave 2: no network). Fixtures: "
                "tests/fixtures/stemmetest/audio/*.wav + manifest.json; run with RUN_LIVE_STT=1 tests/test_stemmetest_live.py")

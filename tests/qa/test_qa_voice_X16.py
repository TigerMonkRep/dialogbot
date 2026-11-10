"""QA X16 (voice-qa): "Navne: ukendt navn bekræftes ved stavning og nævnes derefter højst én gang; udtalestavning
(Berle→Bærle) fra konfiguration."

Offline through the call engines' own code paths: Vapi assistant-request (inbound), ElevenLabs initiation (inbound,
trial engine) and the demo call Peter places from the sales workspace. What the model then actually says is scored
with qa/voice/run_cases.py against qa/voice/cases/X16.yaml; running the model itself needs the network or a live
call and is blocked in wave 1."""
from __future__ import annotations

import ast
import importlib.util
import json
from pathlib import Path

import pytest

from app.config import get_settings
from app.modules.telephony.vapi import spoken_first_message
from tests.test_sales_demo_calls import _web, sales  # noqa: F401  (fixture)
from tests.test_telephony import _post, _setup

ROOT = Path(__file__).resolve().parents[2]
SECRET = "vapi-test-secret-0123456789abcdef"
EL_SECRET = "el-agent-secret-0123456789"

# The rule text in app/modules/ai/service.py CHANNEL_INSTRUCTIONS["phone"] (phone-v8) that X16 depends on.
NAME_RULES = (
    "bed kunden stave det",
    "bekræft ved at stave det tilbage",
    "Et navn, kunden har bekræftet, ændrer du aldrig",
    "bekræft det første gang ved at STAVE det, bogstav for bogstav",
    "Når navnet er bekræftet, siger du det højst én gang mere i samtalen",
)


def _runner():
    spec = importlib.util.spec_from_file_location("qa_voice_run_cases", ROOT / "qa/voice/run_cases.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setenv("VAPI_SERVER_SECRET", SECRET)
    monkeypatch.setenv("ELEVENLABS_AGENT_SECRET", EL_SECRET)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _pronounce(api, tok, ws, entries):
    vs = api.get(tok, f"/workspaces/{ws}/voices").json()
    r = api.c.put(f"/api/v1/workspaces/{ws}/voices/settings",
                  json={"expected_version": vs["settings"]["version"], "pronunciations": entries}, headers=api.h(tok))
    assert r.status_code == 200, r.text


def _inbound(client, pid="pn_123", caller="+4520304050", cid="c1"):
    r = _post(client, {"type": "assistant-request",
                       "call": {"id": cid, "phoneNumberId": pid, "customer": {"number": caller}}})
    assert r.status_code == 200, r.text
    return r.json()["assistant"]


def _el(client, called="+4570123456", caller="+4520304050"):
    r = client.post("/api/v1/webhooks/elevenlabs/init", headers={"x-dialogbot-secret": EL_SECRET},
                    json={"caller_id": caller, "called_number": called, "call_sid": "CA1", "conversation_id": "cv1"})
    assert r.status_code == 200, r.text
    return r.json()


# --------------------------------------------------------------------------- the rule reaches every phone prompt

def test_x16_name_rules_are_in_every_phone_prompt(client, api, two_workspaces, configured):
    t = two_workspaces
    _setup(api, t)
    prompts = {"vapi_inbound": _inbound(client)["model"]["messages"][0]["content"],
               "elevenlabs_inbound": _el(client)["conversation_config_override"]["agent"]["prompt"]["prompt"]}
    # a foreign-language call keeps the (Danish-written) rules under the language directive
    ls = api.get(t["tok_a"], f"/workspaces/{t['ws_a']}/languages").json()
    api.put(t["tok_a"], f"/workspaces/{t['ws_a']}/languages", {
        "expected_version": ls["version"], "interface_language": "da", "default_conversation_language": "da",
        "enabled_conversation_languages": ["da", "en"], "report_language": "da"})
    prompts["vapi_inbound_en"] = _inbound(client, caller="+447700900123", cid="c2")["model"]["messages"][0]["content"]
    for path, p in prompts.items():
        for rule in NAME_RULES:
            assert rule in p, f"{path}: missing name rule {rule!r}"
    (ROOT / "qa/evidence/X16/prompt_paths.json").write_text(json.dumps(
        {k: {"chars": len(v), "rules_found": [r for r in NAME_RULES if r in v]} for k, v in prompts.items()},
        ensure_ascii=False, indent=1))


def test_x16_name_rules_are_in_peters_demo_call(client, sales):  # noqa: F811
    assert _web(client, name="Mette Hansen", company="Berle Pool").status_code == 202
    system = sales["calls"][-1]["assistant"]["model"]["messages"][0]["content"]
    for rule in NAME_RULES:
        assert rule in system, f"demo call: missing name rule {rule!r}"


# --------------------------------------------------------------------------- pronunciation from configuration

def test_x16_pronunciation_comes_from_the_workspace_configuration_only(client, api, two_workspaces, configured):
    """Berle → Bærle exists only where the business configured it (Stemmer → Udtale): in its voice's chunk plan and in
    its greeting. Without the entry – or in another workspace with the same greeting – "Bærle" appears nowhere."""
    t = two_workspaces
    n = _setup(api, t)
    greeting = "Goddag, du har ringet til Berle Pool. Du taler med en digital assistent."
    api.c.patch(f"/api/v1/workspaces/{t['ws_a']}/phone-numbers/{n['id']}", json={"greeting": greeting},
                headers=api.h(t["tok_a"]))
    # workspace B: same greeting, approved knowledge, no pronunciation entry
    it = api.knowledge(t["tok_b"], t["ws_b"], "service", "Kaffe", {"price_net_minor": 3000})
    api.submit(t["tok_b"], t["ws_b"], it["open_draft"]["id"])
    api.approve(t["tok_b"], t["ws_b"], it["open_draft"]["id"])
    nb = api.map_number(t["ws_b"], "+4570999888", "pn_b")
    api.c.patch(f"/api/v1/workspaces/{t['ws_b']}/phone-numbers/{nb['id']}", json={"greeting": greeting},
                headers=api.h(t["tok_b"]))

    assert "Bærle" not in json.dumps(_inbound(client, cid="a0"), ensure_ascii=False)  # nothing configured yet
    _pronounce(api, t["tok_a"], t["ws_a"], [{"term": "Berle", "say": "Bærle"}])
    a = _inbound(client, cid="a1")
    assert a["firstMessage"].startswith("Goddag, du har ringet til Bærle Pool.")
    reps = a["voice"]["chunkPlan"]["formatPlan"]["replacements"]
    assert {"regex": "Berle", "value": "Bærle"} in [{"regex": r["regex"], "value": r["value"]} for r in reps]
    b = _inbound(client, pid="pn_b", cid="b1")
    assert "Bærle" not in json.dumps(b, ensure_ascii=False), "workspace A's pronunciation leaked into workspace B"
    # the entry also applies on a non-Danish call of the same business
    ls = api.get(t["tok_a"], f"/workspaces/{t['ws_a']}/languages").json()
    api.put(t["tok_a"], f"/workspaces/{t['ws_a']}/languages", {
        "expected_version": ls["version"], "interface_language": "da", "default_conversation_language": "da",
        "enabled_conversation_languages": ["da", "en"], "report_language": "da"})
    en = _inbound(client, caller="+447700900123", cid="a2")
    assert any(r["value"] == "Bærle" for r in en["voice"]["chunkPlan"]["formatPlan"]["replacements"])
    # removing the entry removes it everywhere
    _pronounce(api, t["tok_a"], t["ws_a"], [])
    assert "Bærle" not in json.dumps(_inbound(client, cid="a3"), ensure_ascii=False)


def test_x16_peters_demo_call_uses_the_sales_workspaces_pronunciations(client, api, sales):  # noqa: F811
    _pronounce(api, sales["tok"], sales["ws"], [{"term": "Berle", "say": "Bærle"}])
    assert _web(client, name="Mette Hansen", company="Berle Pool").status_code == 202
    a = sales["calls"][-1]["assistant"]
    assert "Bærle Pool" in a["firstMessage"]  # the greeting names the company: said as configured
    assert any(r["value"] == "Bærle" for r in a["voice"]["chunkPlan"]["formatPlan"]["replacements"])
    assert "Berle Pool" in a["transcriber"]["keyterm"]  # what the transcriber listens for stays the written name


def test_x16_no_hardcoded_pronunciation_spelling_in_code():
    """"Bærle" may appear in comments/docstrings as an example, never as a string the code uses."""
    hits = []
    for f in (ROOT / "app").rglob("*.py"):
        tree = ast.parse(f.read_text(encoding="utf-8"))
        docstrings = {id(n.body[0].value) for n in ast.walk(tree)
                      if isinstance(n, ast.Module | ast.FunctionDef | ast.ClassDef | ast.AsyncFunctionDef)
                      and n.body and isinstance(n.body[0], ast.Expr) and isinstance(n.body[0].value, ast.Constant)}
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstrings \
                    and "Bærle" in node.value:
                hits.append(f"{f.relative_to(ROOT)}:{node.lineno}")
    assert hits == []


def test_x16_spelling_survives_the_pronunciation_dictionary():
    """The spelled confirmation ("B, E, R, L, E") and single letters are never rewritten by a whole-word entry."""
    voice = {"chunkPlan": {"enabled": True, "formatPlan": {"enabled": True, "replacements": [
        {"type": "regex", "regex": "Berle", "value": "Bærle",
         "options": [{"type": "ignore-case", "enabled": True}, {"type": "whole-word", "enabled": True}]},
        {"type": "regex", "regex": "AI", "value": "ej aj",
         "options": [{"type": "ignore-case", "enabled": True}, {"type": "whole-word", "enabled": True}]}]}}}
    out = spoken_first_message({"firstMessage": "Berle – B, E, R, L, E – Pool, og A, I, er det rigtigt?",
                                "voice": voice})["firstMessage"]
    assert out == "Bærle – B, E, R, L, E – Pool, og A, I, er det rigtigt?"


# --------------------------------------------------------------------------- ElevenLabs engine (F-VQ-04)

def test_x16_elevenlabs_engine_gets_the_pronunciation_dictionary_for_what_peter_says(client, api, two_workspaces,
                                                                                    configured):
    """On Vapi the dictionary is applied to every sentence the model speaks (voice.chunkPlan). On the ElevenLabs
    engine the override carries only prompt + first message, so "Berle" in the middle of the call (e.g. the spelled
    confirmation "Berle – B, E, R, L, E – Pool") is read without the configured pronunciation."""
    t = two_workspaces
    _setup(api, t)
    _pronounce(api, t["tok_a"], t["ws_a"], [{"term": "Berle", "say": "Bærle"}])
    out = _el(client)
    override = out["conversation_config_override"]
    tts = override.get("tts") or {}
    in_prompt = "Bærle" in override["agent"]["prompt"]["prompt"]
    assert tts.get("pronunciation_dictionary_locators") or in_prompt, (
        "ElevenLabs init carries no pronunciation dictionary and the prompt does not mention it: "
        f"override keys={sorted(override)}, agent keys={sorted(override['agent'])}")


# --------------------------------------------------------------------------- the eval cases and their scorer

def test_x16_eval_case_scorer_is_honest_on_the_reference_transcripts():
    run = _runner()
    for f in ("X05", "X15", "X16"):
        for case in run.load(ROOT / f"qa/voice/cases/{f}.yaml"):
            for kind, want in (("pass", True), ("fail", False)):
                for tr in case["reference_transcripts"][kind]:
                    ok, why = run.score(case, tr)
                    assert ok is want, (case["id"], kind, why)

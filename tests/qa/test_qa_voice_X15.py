"""QA X15 (voice-qa): "Opkald fra dansk nummer besvares på dansk; virksomhedens valgte sprog bruges ellers; stemme følger
sproget."

Offline through the same code path the call engines use: the Vapi assistant-request webhook
(telephony.router → vapi.assistant_config) and the ElevenLabs initiation webhook (telephony.elevenlabs_agent).
No live calls: the webhooks are posted with the test client, nothing leaves the process.

What "the call language" means is taken from app/modules/telephony/phone_languages.py: the greeting, the recogniser,
the dialogue model's language directive, the voice, the end-of-call phrases and the backchannels all follow it."""
from __future__ import annotations

import pytest

from app.config import get_settings
from app.modules.voices.standard import LANGUAGE_VOICES, STANDARD_VOICES
from tests.test_telephony import _post, _setup

SECRET = "vapi-test-secret-0123456789abcdef"
EL_INIT = "/api/v1/webhooks/elevenlabs/init"
EL_SECRET = "el-agent-secret-0123456789"


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setenv("VAPI_SERVER_SECRET", SECRET)
    monkeypatch.setenv("ELEVENLABS_AGENT_SECRET", EL_SECRET)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _languages(api, t, default: str, enabled: list[str]):
    ls = api.get(t["tok_a"], f"/workspaces/{t['ws_a']}/languages").json()
    r = api.put(t["tok_a"], f"/workspaces/{t['ws_a']}/languages", {
        "expected_version": ls["version"], "interface_language": "da", "default_conversation_language": default,
        "enabled_conversation_languages": enabled, "report_language": "da"})
    assert r.status_code == 200, r.text


def _assistant(client, caller: str | None, call_id: str = "c1") -> dict:
    call = {"id": call_id, "phoneNumberId": "pn_123", **({"customer": {"number": caller}} if caller else {})}
    r = _post(client, {"type": "assistant-request", "call": call})
    assert r.status_code == 200, r.text
    return r.json()["assistant"]


def _is_danish_call(a: dict) -> None:
    system = a["model"]["messages"][0]["content"]
    assert not system.startswith("LANGUAGE:"), "a Danish call must not carry a foreign-language directive"
    assert a["transcriber"]["language"] == "da"
    assert a["voice"].get("language") == "da", a["voice"]
    assert "hav en god dag" in a["endCallPhrases"]
    assert "javel" in a["stopSpeakingPlan"]["acknowledgementPhrases"]


def _is_english_call(a: dict) -> None:
    system = a["model"]["messages"][0]["content"]
    assert system.startswith("LANGUAGE: This phone call is in English.")
    assert a["transcriber"]["language"] == "en"
    assert a["voice"].get("language") == "en", a["voice"]
    assert a["voice"]["voiceId"] in {v["voiceId"] for v in LANGUAGE_VOICES["en"].values()}
    assert "have a good day" in a["endCallPhrases"]
    assert "uh-huh" in a["stopSpeakingPlan"]["acknowledgementPhrases"]


# --------------------------------------------------------------------------- the main rule (expected to pass)

def test_x15_danish_number_gets_a_fully_danish_call_even_when_the_business_default_is_english(
        client, api, two_workspaces, configured):
    t = two_workspaces
    _setup(api, t)
    _languages(api, t, "en", ["en", "da"])
    for caller in ("+4520304050", "+45 20 30 40 50", "004520304050"):  # the caller-id formats providers send
        a = _assistant(client, caller, call_id=f"c-{caller}")
        assert a["firstMessage"].startswith("Hej, du har ringet til"), (caller, a["firstMessage"])
        _is_danish_call(a)
        # the Danish voice is the business's chosen standard voice (default Camilla), never the English one
        assert a["voice"]["voiceId"] == STANDARD_VOICES["camilla"]["voice"]["voiceId"]


def test_x15_otherwise_the_business_language_is_used_and_the_voice_follows_it(client, api, two_workspaces, configured):
    t = two_workspaces
    _setup(api, t)
    _languages(api, t, "en", ["en", "da"])
    for caller in (None, "+46701234567", "+4915112345678", "20304050"):  # withheld, language not on, no country code
        a = _assistant(client, caller, call_id=f"c-{caller}")
        assert a["firstMessage"].startswith("Hello, you've reached"), (caller, a["firstMessage"])
        _is_english_call(a)
    # a Danish business with English switched on: a +44 caller is answered in English, a +45 caller in Danish
    _languages(api, t, "da", ["da", "en"])
    _is_english_call(_assistant(client, "+447700900123", "c-uk"))
    _is_danish_call(_assistant(client, "+4520304050", "c-dk"))


def test_x15_peters_gender_is_kept_in_the_foreign_language_voice(client, api, two_workspaces, configured):
    """The business picked Peter (male): the English call gets the male English voice, the Danish call Peter."""
    t = two_workspaces
    _setup(api, t)
    _languages(api, t, "en", ["en", "da"])
    vs = api.get(t["tok_a"], f"/workspaces/{t['ws_a']}/voices").json()
    r = api.c.put(f"/api/v1/workspaces/{t['ws_a']}/voices/settings",
                  json={"expected_version": vs["settings"]["version"], "standard_voice": "peter"}, headers=api.h(t["tok_a"]))
    assert r.status_code == 200, r.text
    assert _assistant(client, "+447700900123", "c-uk")["voice"]["voiceId"] == LANGUAGE_VOICES["en"]["male"]["voiceId"]
    assert _assistant(client, "+4520304050", "c-dk")["voice"]["voiceId"] == STANDARD_VOICES["peter"]["voice"]["voiceId"]


# --------------------------------------------------------------------------- what the caller hears FIRST (F-VQ-01)

def test_x15_a_written_greeting_does_not_override_the_call_language(client, api, two_workspaces, configured):
    """A business that wrote its own (Danish) greeting and also serves English callers: the +44 caller's first words
    must be English, like the rest of the call."""
    t = two_workspaces
    n = _setup(api, t)
    _languages(api, t, "da", ["da", "en"])
    r = api.c.patch(f"/api/v1/workspaces/{t['ws_a']}/phone-numbers/{n['id']}",
                    json={"greeting": "Goddag, du har ringet til Fjord Gulvservice. Hvad kan jeg hjælpe med?"},
                    headers=api.h(t["tok_a"]))
    assert r.status_code == 200, r.text
    uk = _assistant(client, "+447700900123", "c-uk")
    _is_english_call(uk)  # everything else is English ...
    assert not uk["firstMessage"].startswith("Goddag"), (
        "English call opens with the Danish written greeting: " + uk["firstMessage"])


def test_x15_an_english_written_greeting_is_not_said_to_a_danish_number(client, api, two_workspaces, configured):
    t = two_workspaces
    n = _setup(api, t)
    _languages(api, t, "en", ["en", "da"])
    api.c.patch(f"/api/v1/workspaces/{t['ws_a']}/phone-numbers/{n['id']}",
                json={"greeting": "Hello, you have reached Fjord Floors. How can I help?"}, headers=api.h(t["tok_a"]))
    dk = _assistant(client, "+4520304050", "c-dk")
    _is_danish_call(dk)
    assert not dk["firstMessage"].startswith("Hello"), (
        "Danish caller is greeted in English: " + dk["firstMessage"])


def test_x15_reception_script_greeting_does_not_override_the_call_language(client, api, two_workspaces, configured, db):
    """Same rule for the greeting from the reception manuscript (R05), which is written once, in Danish."""
    import uuid

    from app.models import ReceptionScript

    t = two_workspaces
    _setup(api, t)
    _languages(api, t, "da", ["da", "en"])
    ws_id = uuid.UUID(t["ws_a"])
    s = db.get(ReceptionScript, ws_id)
    if s is None:
        s = ReceptionScript(workspace_id=ws_id)
        db.add(s)
    s.greeting = "Velkommen til Fjord Gulvservice, du taler med vores digitale assistent."
    db.commit()
    uk = _assistant(client, "+447700900123", "c-uk")
    assert uk["model"]["messages"][0]["content"].startswith("LANGUAGE: This phone call is in English.")
    assert not uk["firstMessage"].startswith("Velkommen"), (
        "English call opens with the Danish manuscript greeting: " + uk["firstMessage"])


# --------------------------------------------------------------------------- the ElevenLabs engine (F-VQ-02)

def _el_init(client, caller: str) -> dict:
    body = {"caller_id": caller, "called_number": "+4570123456", "call_sid": "CA1", "agent_id": "ag",
            "conversation_id": f"conv_{caller}"}
    r = client.post(EL_INIT, json=body, headers={"x-dialogbot-secret": EL_SECRET})
    assert r.status_code == 200, r.text
    return r.json()["conversation_config_override"]["agent"]


def test_x15_elevenlabs_engine_speaks_and_listens_in_the_call_language(client, api, two_workspaces, configured):
    """ElevenLabs runs speech-to-text and the voice itself; its `language` override decides both. An English call
    (+44 caller, English on) must be initiated with language "en" – not with Danish ASR/TTS under an English prompt."""
    t = two_workspaces
    _setup(api, t)
    _languages(api, t, "da", ["da", "en"])
    dk = _el_init(client, "+4520304050")
    assert dk["language"] == "da"
    uk = _el_init(client, "+447700900123")
    assert uk["prompt"]["prompt"].startswith("LANGUAGE: This phone call is in English.")
    assert uk["first_message"].startswith("Hello")
    assert uk["language"] == "en", f"ElevenLabs is told language={uk['language']!r} for an English call"


# --------------------------------------------------------------------------- Dialogbot's own (Danish) voice (F-VQ-03)

def test_x15_a_danish_dialogbot_voice_is_not_used_for_a_foreign_language_call(client, api, two_workspaces, db,
                                                                               monkeypatch, tmp_path):
    """The workspace chose one of Dialogbot's own Danish voices (VoiceProfile.language = da-DK) for its number. An
    English call must get a voice that speaks English (the native English voice), not the Danish custom voice."""
    from tests import test_voices as tv

    monkeypatch.setenv("TTS_ENGINE", "fake")
    monkeypatch.setenv("VOICE_STORAGE_DIR", str(tmp_path / "store"))
    monkeypatch.setenv("VAPI_SERVER_SECRET", SECRET)
    monkeypatch.setenv("AI_PROVIDER", "fake")
    get_settings.cache_clear()
    t = two_workspaces
    op = tv._operator(api, db)
    pid, v1 = tv._voice(api, op, "coral-tts-qa", tv._rights(api, op))
    tv._publish(api, op, v1)
    tv._knowledge(api, t)
    nid = tv._number(api, t)
    assert api.put(t["tok_a"], f"/workspaces/{t['ws_a']}/voices/assignments/phone-numbers/{nid}",
                   {"voice_profile_id": pid}).status_code == 200
    _languages(api, t, "da", ["da", "en"])

    def ask(caller, cid):
        return client.post("/api/v1/webhooks/vapi", headers={"authorization": f"Bearer {SECRET}"},
                           json={"message": {"type": "assistant-request",
                                             "call": {"id": cid, "phoneNumberId": "pn_voice",
                                                      "customer": {"number": caller}}}}).json()["assistant"]

    assert ask("+4520304050", "c-dk")["voice"]["provider"] == "custom-voice"  # Danish call: the chosen Danish voice
    uk = ask("+447700900123", "c-uk")
    assert uk["model"]["messages"][0]["content"].startswith("LANGUAGE: This phone call is in English.")
    assert uk["voice"]["provider"] != "custom-voice", (
        "English call is spoken by the Danish (da-DK) Dialogbot voice (provider custom-voice)")

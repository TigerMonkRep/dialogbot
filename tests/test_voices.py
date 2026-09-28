"""Danish voice library: operator-only registry, immutable versions, publication checks that cannot be faked,
tenant isolation, preview limits, selection per workspace/assistant/campaign, pinning per call, the Vapi
custom-voice path, suspension/rollback/fallback, and that re-synthesis never repeats business actions.

The speech engine is the TTS_ENGINE=fake test double (a tone, labelled simulated) – these tests prove the
integration, not audio quality."""
from __future__ import annotations

import io
import uuid
import wave

import pytest

from app.config import get_settings
from app.core.errors import ValidationFailed
from app.models import Booking, Lead, User, VoiceSession, VoiceVersion, WorkspaceVoiceSettings

SECRET = "vapi-test-secret-0123456789abcdef"
REV = "a" * 40


def _wav(seconds=6.0, rate=24000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x10\x00\xf0\xff" * int(rate * seconds / 2))
    return buf.getvalue()


@pytest.fixture
def voice_env(monkeypatch, tmp_path):
    monkeypatch.setenv("TTS_ENGINE", "fake")
    monkeypatch.setenv("VOICE_STORAGE_DIR", str(tmp_path / "store"))
    monkeypatch.setenv("VAPI_SERVER_SECRET", SECRET)
    monkeypatch.setenv("AI_PROVIDER", "fake")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _operator(api, db, email="op-voice@testmail.dk"):
    tok = api.user(email)
    u = db.query(User).filter_by(email_normalized=email).one()
    u.is_platform_operator = True
    db.commit()
    return tok


def _rights(api, op, verify=True):
    ids = []
    for kind, subject in (("code", "chatterbox-tts 0.1.7"), ("model", "ResembleAI/chatterbox"), ("dataset", "CoRal-project/coral-tts")):
        r = api.post(op, "/operator/voice-rights", {"kind": kind, "subject": subject, "license": "x"})
        assert r.status_code == 201, r.text
        if verify:
            assert api.post(op, f"/operator/voice-rights/{r.json()['id']}/review",
                            {"status": "verified", "notes": "Licensteksten er læst i sin helhed (test)."}).status_code == 200
        ids.append(r.json()["id"])
    return ids


def _voice(api, op, slug, rights, *, workspace_id=None, name=None):
    body = {"slug": slug, "display_name": name or slug, "visibility": "workspace" if workspace_id else "platform"}
    if workspace_id:
        body["workspace_id"] = workspace_id
    p = api.post(op, "/operator/voices", body)
    assert p.status_code == 201, p.text
    pid = p.json()["id"]
    ref = api.c.post(f"{api.base}/operator/voices/{pid}/references?source_id=coral-tts:row-1", content=_wav(),
                     headers=api.h(op)).json()
    v = api.post(op, f"/operator/voices/{pid}/versions", {"model_repo": "ResembleAI/chatterbox", "model_revision": REV,
                                                           "references": [ref], "settings": {"exaggeration": 0.5},
                                                           "rights_record_ids": rights})
    assert v.status_code == 201, v.text
    return pid, v.json()["versions"][0]["id"]


def _publish(api, op, vid, *, human=True):
    assert api.post(op, f"/operator/voice-versions/{vid}/checks/run").status_code == 200
    assert api.post(op, f"/operator/voice-versions/{vid}/submit").status_code == 200
    if human:
        api.post(op, f"/operator/voice-versions/{vid}/checks/listening_test",
                 {"passed": True, "evidence": {"raters": 3, "intelligibility": 4.3, "naturalness": 4.1}})
        api.post(op, f"/operator/voice-versions/{vid}/checks/telephony_test",
                 {"passed": True, "evidence": {"provider_call_id": "call_test_1"}})
    r = api.post(op, f"/operator/voice-versions/{vid}/approve")
    assert r.status_code == 200, r.text
    r = api.post(op, f"/operator/voice-versions/{vid}/activate")
    assert r.status_code == 200, r.text
    return r.json()


def test_operator_only_and_checks_cannot_be_faked(api, two_workspaces, db, voice_env):
    t = two_workspaces
    assert api.get(t["tok_a"], "/operator/voices").status_code == 403
    op = _operator(api, db)
    rights = _rights(api, op, verify=False)
    pid, vid = _voice(api, op, "coral-tts-a", rights)
    # a version is immutable and pinned to a commit, never "main"
    bad = api.post(op, f"/operator/voices/{pid}/versions", {"model_repo": "ResembleAI/chatterbox", "model_revision": "main"})
    assert bad.status_code == 422
    stolen = api.post(op, f"/operator/voices/{pid}/versions", {"model_repo": "x/y", "model_revision": REV,
                                                                "references": [{"key": "platform/voices/other/refs/x.wav", "sha256": "0"}]})
    assert stolen.status_code == 422
    checks = api.post(op, f"/operator/voice-versions/{vid}/checks/run").json()["versions"][0]["checks"]
    assert checks["rights"]["status"] == "failed" and checks["normalization"]["status"] == "passed"
    assert checks["synthesis_smoke"]["status"] == "simulated"  # the fake engine never counts as real speech
    api.post(op, f"/operator/voice-versions/{vid}/submit")
    r = api.post(op, f"/operator/voice-versions/{vid}/approve")
    assert r.status_code == 409 and {"rights", "listening_test", "telephony_test"} <= set(r.json()["missing"])
    # a listening test below the bar is refused, not recorded as passed
    weak = api.post(op, f"/operator/voice-versions/{vid}/checks/listening_test",
                    {"passed": True, "evidence": {"raters": 2, "intelligibility": 4.5, "naturalness": 4.5}})
    assert weak.status_code == 422
    # nothing is selectable for customers
    assert api.get(t["tok_a"], f"/workspaces/{t['ws_a']}/voices").json()["items"] == []


def test_library_preview_selection_and_isolation(api, two_workspaces, db, voice_env, monkeypatch):
    t = two_workspaces
    op = _operator(api, db)
    rights = _rights(api, op)
    pid, vid = _voice(api, op, "coral-tts-a", rights, name="CoRal-TTS indtaler A")
    _publish(api, op, vid)
    private_pid, private_vid = _voice(api, op, "fjord-privat", rights, workspace_id=t["ws_a"])
    _publish(api, op, private_vid, human=False)  # a workspace pilot needs rights + automatic checks only
    a = api.get(t["tok_a"], f"/workspaces/{t['ws_a']}/voices").json()
    b = api.get(t["tok_b"], f"/workspaces/{t['ws_b']}/voices").json()
    assert {x["slug"] for x in a["items"]} == {"coral-tts-a", "fjord-privat"} and a["engine"] == "simulated"
    assert {x["slug"] for x in b["items"]} == {"coral-tts-a"}  # a private voice never becomes global
    assert next(x for x in a["items"] if x["slug"] == "fjord-privat")["active_version"]["pilot"] is True
    assert api.post(t["tok_b"], f"/workspaces/{t['ws_b']}/voices/{private_pid}/preview", {}).status_code == 404
    r = api.post(t["tok_a"], f"/workspaces/{t['ws_a']}/voices/{pid}/preview", {"text": "Det koster 1.495 kr."})
    assert r.status_code == 200 and r.headers["content-type"] == "audio/wav" and r.headers["x-simulated"] == "1"
    assert r.content[:4] == b"RIFF"
    too_long = api.post(t["tok_a"], f"/workspaces/{t['ws_a']}/voices/{pid}/preview", {"text": "a" * 201})
    assert too_long.status_code == 422
    # selection is validated server-side and tenant-scoped
    s = a["settings"]
    assert api.put(t["tok_b"], f"/workspaces/{t['ws_b']}/voices/settings",
                   {"expected_version": 1, "default_profile_id": private_pid}).status_code == 404
    reader = api.add_member(t["tok_a"], t["ws_a"], "reader-voice@testmail.dk", "reader")
    assert api.get(reader, f"/workspaces/{t['ws_a']}/voices").status_code == 403
    r = api.put(t["tok_a"], f"/workspaces/{t['ws_a']}/voices/settings",
                {"expected_version": s["version"], "default_profile_id": pid,
                 "pronunciations": [{"term": "Fjord", "say": "Fjor"}]})
    assert r.status_code == 200 and r.json()["pronunciation_version"] == 2
    # the setup check only passes after the standard sample of the chosen voice was played
    # with the simulated engine the check refuses to run (a tone is not a heard voice) …
    assert api.post(t["tok_a"], f"/workspaces/{t['ws_a']}/setup/checks/voice.heard/run").status_code == 501
    # … while its rule is: the standard sample of the *current* default voice version was played after the last change
    from app.modules.setup.checks import _evaluate

    ws_id = uuid.UUID(t["ws_a"])
    assert _evaluate(db, ws_id, "voice.heard")[0] is False
    api.post(t["tok_a"], f"/workspaces/{t['ws_a']}/voices/{pid}/preview", {})
    db.expire_all()
    ok, evidence = _evaluate(db, ws_id, "voice.heard")
    assert ok and evidence["simulated"] is True
    # daily preview limit
    monkeypatch.setenv("VOICE_PREVIEW_DAILY_LIMIT", "3")
    get_settings.cache_clear()
    codes = [api.post(t["tok_a"], f"/workspaces/{t['ws_a']}/voices/{pid}/preview", {"text": "Hej"}).status_code for _ in range(3)]
    assert codes[-1] == 429


def _number(api, t, voice_id=""):
    n = api.map_number(t["ws_a"], "+4570123456", "pn_voice")
    if voice_id:
        api.c.patch(f"{api.base}/workspaces/{t['ws_a']}/phone-numbers/{n['id']}", json={"voice_id": voice_id},
                    headers=api.h(t["tok_a"]))
    return n["id"]


def _knowledge(api, t):
    it = api.knowledge(t["tok_a"], t["ws_a"], "service", "Gulvafslibning", {"description": "Vi sliber gulve."})
    api.submit(t["tok_a"], t["ws_a"], it["open_draft"]["id"])
    api.approve(t["tok_a"], t["ws_a"], it["open_draft"]["id"])


def _assistant(api, client, call_id="call_v1"):
    return client.post("/api/v1/webhooks/vapi", headers={"authorization": f"Bearer {SECRET}"},
                       json={"message": {"type": "assistant-request", "call": {"id": call_id, "phoneNumberId": "pn_voice"}}}).json()


def _speak(client, url, text="Hej. Det koster 1.495 kr.", auth=True):
    path = url.split("/api/v1", 1)[1]
    h = {"x-vapi-secret": SECRET} if auth else {}
    return client.post(f"/api/v1{path}", headers=h, json={"message": {"type": "voice-request", "text": text, "sampleRate": 16000}})


def test_call_pins_voice_version_and_falls_back_honestly(api, client, two_workspaces, db, voice_env):
    t = two_workspaces
    op = _operator(api, db)
    rights = _rights(api, op)
    pid, v1 = _voice(api, op, "coral-tts-a", rights)
    _publish(api, op, v1)
    _knowledge(api, t)
    nid = _number(api, t, voice_id="elevenVoice0001")
    # no Dialogbot voice chosen → existing provider voice unchanged
    a0 = _assistant(api, client)["assistant"]
    assert a0["voice"]["provider"] == "11labs"
    api.put(t["tok_a"], f"/workspaces/{t['ws_a']}/voices/assignments/phone-numbers/{nid}", {"voice_profile_id": pid})
    a = _assistant(api, client, "call_v1")["assistant"]
    voice = a["voice"]
    assert voice["provider"] == "custom-voice" and voice["fallbackPlan"]["voices"][0]["voiceId"] == "elevenVoice0001"
    assert a["transcriber"]["language"] == "da"
    session = db.get(VoiceSession, uuid.UUID(a["metadata"]["voice_session_id"]))
    assert session.provider_call_id == "call_v1" and str(session.version_id) == v1
    assert _speak(client, voice["server"]["url"], auth=False).status_code == 401
    first = _speak(client, voice["server"]["url"])
    assert first.status_code == 200 and first.headers["x-sample-rate"] == "16000" and len(first.content) > 1000
    assert first.content[:4] != b"RIFF"  # raw PCM, no WAV header
    assert first.headers["x-simulated"] == "1" and int(first.headers["x-first-audio-ms"]) >= 0
    # streamed (default) and sentence-by-sentence delivery give the same audio
    from app.config import get_settings

    get_settings().tts_streaming = False
    try:
        assert _speak(client, voice["server"]["url"]).content == first.content
    finally:
        get_settings().tts_streaming = True
    # a new version is activated mid-call: the running call keeps v1, a new call gets v2
    pid_obj = api.c.post(f"{api.base}/operator/voices/{pid}/references", content=_wav(4.0), headers=api.h(op)).json()
    v2 = api.post(op, f"/operator/voices/{pid}/versions", {"model_repo": "ResembleAI/chatterbox", "model_revision": "b" * 40,
                                                            "references": [pid_obj], "rights_record_ids": rights}).json()["versions"][0]["id"]
    _publish(api, op, v2)
    assert _speak(client, voice["server"]["url"]).content == first.content
    a2 = _assistant(api, client, "call_v2")["assistant"]
    assert _speak(client, a2["voice"]["server"]["url"]).content != first.content
    # rollback reactivates v1 for new calls
    api.post(op, f"/operator/voices/{pid}/rollback")
    db.expire_all()
    assert db.get(VoiceVersion, uuid.UUID(v1)).status == "active"
    # suspension stops the voice immediately → 503 so Vapi plays the approved reserve voice
    api.post(op, f"/operator/voice-versions/{v1}/suspend")
    assert _speak(client, voice["server"]["url"]).status_code == 503
    a3 = _assistant(api, client, "call_v3")["assistant"]
    assert a3["voice"]["provider"] == "11labs"
    fallback = db.query(VoiceSession).filter(VoiceSession.version_id.is_(None)).one()
    assert fallback.fallback["reason"].startswith("assistant")


def test_resynthesis_never_repeats_business_actions(api, client, two_workspaces, db, voice_env):
    t = two_workspaces
    op = _operator(api, db)
    pid, vid = _voice(api, op, "coral-tts-a", _rights(api, op))
    _publish(api, op, vid)
    _knowledge(api, t)
    _number(api, t)
    ws = uuid.UUID(t["ws_a"])
    s = db.get(WorkspaceVoiceSettings, ws) or WorkspaceVoiceSettings(workspace_id=ws, pronunciations=[])
    s.default_profile_id = uuid.UUID(pid)
    db.add(s)
    db.commit()
    a = _assistant(api, client, "call_retry")["assistant"]
    before = (db.query(Booking).count(), db.query(Lead).count())
    for _ in range(3):  # Vapi retries the same utterance
        assert _speak(client, a["voice"]["server"]["url"], "Din tid er bekræftet den 28. oktober kl. 10.30.").status_code == 200
    assert (db.query(Booking).count(), db.query(Lead).count()) == before
    db.expire_all()
    stats = db.query(VoiceSession).filter_by(provider_call_id="call_retry").one().stats
    assert stats["requests"] == 3 and len(stats["ttfa_ms_list"]) == 3 and "text" not in str(stats)


def test_campaign_voice_is_separate_and_changes_nothing_else(api, two_workspaces, db, voice_env):
    t = two_workspaces
    op = _operator(api, db)
    pid, vid = _voice(api, op, "coral-tts-b", _rights(api, op))
    _publish(api, op, vid)
    c = api.post(t["tok_a"], f"/workspaces/{t['ws_a']}/campaigns", {"name": "Forår", "purpose": "Test"}).json()
    r = api.put(t["tok_a"], f"/workspaces/{t['ws_a']}/voices/assignments/campaigns/{c['id']}", {"voice_profile_id": pid})
    assert r.status_code == 200
    after = api.get(t["tok_a"], f"/workspaces/{t['ws_a']}/campaigns/{c['id']}").json()
    assert after["status"] == "draft" and after["max_cost"] == c["max_cost"]
    assert api.put(t["tok_b"], f"/workspaces/{t['ws_b']}/voices/assignments/campaigns/{c['id']}",
                   {"voice_profile_id": pid}).status_code == 404


def test_engine_not_configured_and_unreachable(api, two_workspaces, db, voice_env, monkeypatch):
    t = two_workspaces
    op = _operator(api, db)
    pid, vid = _voice(api, op, "coral-tts-a", _rights(api, op))
    _publish(api, op, vid)
    monkeypatch.setenv("TTS_ENGINE", "none")
    get_settings.cache_clear()
    assert api.post(t["tok_a"], f"/workspaces/{t['ws_a']}/voices/{pid}/preview", {}).status_code == 501
    monkeypatch.setenv("TTS_ENGINE", "http")
    monkeypatch.setenv("TTS_SERVICE_URL", "http://127.0.0.1:9")
    monkeypatch.setenv("TTS_SERVICE_TOKEN", "x" * 32)
    get_settings.cache_clear()
    r = api.post(t["tok_a"], f"/workspaces/{t['ws_a']}/voices/{pid}/preview", {"text": "Hej"})
    assert r.status_code == 503 and r.json()["code"] == "tts_unavailable"


def test_cache_keys_are_scoped_and_invalidated(two_workspaces, db, voice_env):
    from app.models import VoiceProfile
    from app.modules.voices import service, storage

    ws = uuid.UUID(two_workspaces["ws_a"])
    plat = VoiceProfile(id=uuid.uuid4(), slug="x-plat", display_name="x", visibility="platform")
    priv = VoiceProfile(id=uuid.uuid4(), slug="x-priv", display_name="y", visibility="workspace", workspace_id=ws)
    v = VoiceVersion(id=uuid.uuid4(), model_revision=REV, settings={})
    k1, k2 = service.cache_key(plat, v, "hej", 24000), service.cache_key(priv, v, "hej", 24000)
    assert k1.startswith(f"cache/platform/{plat.id}/") and k2.startswith(f"cache/ws/{ws}/{priv.id}/")
    assert service.cache_key(plat, VoiceVersion(id=uuid.uuid4(), model_revision=REV, settings={}), "hej", 24000) != k1
    storage.put(k1, b"RIFFxxxx")
    assert storage.get(k1) == b"RIFFxxxx"
    service.invalidate_cache(plat)
    assert storage.get(k1) is None
    with pytest.raises(ValidationFailed):
        storage.check_key("platform/../../etc/passwd")


def _checks(api, op, vid):
    r = api.post(op, f"/operator/voice-versions/{vid}/checks/run")
    assert r.status_code == 200, r.text
    return next(v for v in r.json()["versions"] if v["id"] == vid)["checks"]


def test_designed_voice_needs_sources_and_passes_distinctness_before_approval(api, db, voice_env):
    from app.modules.voices import storage

    op = _operator(api, db)
    rights = _rights(api, op)
    p = api.post(op, "/operator/voices", {"slug": "designet-jysk-mand", "display_name": "Designet: jysk mand",
                                          "gender": "male", "origin": "designed",
                                          "description": "Mandestemme designet ud fra 8 jyske oplæsere."})
    assert p.status_code == 201, p.text
    pid = p.json()["id"]
    key = "platform/voices/designet-jysk-mand/conds-1.pt"
    storage.put(key, b"conditioning", "application/octet-stream")
    base = {"method": "designed_blend", "model_repo": "CoRal-project/roest-v3-chatterbox-500m", "model_revision": REV,
            "checkpoint_key": key, "rights_record_ids": rights}
    # no sources -> refused
    r = api.post(op, f"/operator/voices/{pid}/versions", base | {"provenance": {}})
    assert r.status_code == 422
    sources = [{"speaker_id": str(i), "age": 30 + i, "region": "Vestjylland"} for i in range(8)]
    too_close = {"max_similarity_to_source": 0.93, "nearest_source": "3", "real_speaker_pairs_max": 0.84}
    r = api.post(op, f"/operator/voices/{pid}/versions", base | {"provenance": {"sources": sources, "distinctness": too_close}})
    assert r.status_code == 201, r.text
    v1 = r.json()["versions"][0]
    assert v1["provenance"]["checkpoint_sha256"]  # computed by the server from the stored file, not trusted input
    checks = _checks(api, op, v1["id"])
    assert checks["distinctness"]["status"] == "failed" and checks["distinctness"]["limit"] == 0.87
    assert api.post(op, f"/operator/voice-versions/{v1['id']}/submit").status_code == 200
    assert api.post(op, f"/operator/voice-versions/{v1['id']}/approve").status_code == 409  # resembles one person
    ok = {"max_similarity_to_source": 0.858, "nearest_source": "3", "real_speaker_pairs_max": 0.84}
    r = api.post(op, f"/operator/voices/{pid}/versions", base | {"provenance": {"sources": sources, "distinctness": ok}})
    v2 = [v for v in r.json()["versions"] if v["version"] == 2][0]
    checks = _checks(api, op, v2["id"])
    assert checks["distinctness"]["status"] == "passed"
    detail = api.get(op, "/operator/voices").json()
    assert any(x.get("origin") == "designed" and x.get("description") for x in detail.get("items", detail))

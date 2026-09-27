"""Own voice: personalised manuscript, consent in the speaker's own name, per-sentence recording with quality checks,
submission into a private workspace voice that waits for review of the consent, tenant isolation, and withdrawal that
deletes the recordings and stops the voice."""
from __future__ import annotations

import io
import math
import wave
from pathlib import Path

import pytest

from app.config import get_settings
from app.models import OwnVoiceProject, User, VoiceRightsRecord, VoiceVersion


def _wav(seconds=3.0, rate=48000, amp=0.3) -> bytes:
    buf = io.BytesIO()
    frames = bytearray()
    pad = int(0.3 * rate)
    for i in range(int(seconds * rate)):
        v = 0 if i < pad or i > seconds * rate - pad else int(amp * 32767 * math.sin(2 * math.pi * 180 * i / rate))
        frames += int(v).to_bytes(2, "little", signed=True)
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(bytes(frames))
    return buf.getvalue()


@pytest.fixture
def env(monkeypatch, tmp_path):
    monkeypatch.setenv("TTS_ENGINE", "fake")
    monkeypatch.setenv("VOICE_STORAGE_DIR", str(tmp_path / "store"))
    get_settings.cache_clear()
    yield tmp_path / "store"
    get_settings.cache_clear()


def _put(api, tok, ws, pid, sid, data):
    return api.c.put(f"{api.base}/workspaces/{ws}/own-voices/{pid}/recordings/{sid}", content=data,
                     headers=api.h(tok, **{"content-type": "audio/wav"}))


def test_own_voice_from_consent_to_review_and_withdrawal(api, two_workspaces, db, env):
    t = two_workspaces
    tok, ws = t["tok_a"], t["ws_a"]
    m = api.get(tok, f"/workspaces/{ws}/own-voices/manuscripts/kort?by=Aarhus").json()
    assert len(m["sentences"]) == 15 and "{" not in "".join(s["text"] for s in m["sentences"])
    assert "Fjord Gulvservice ApS" in m["sentences"][0]["text"] and m["values"]["by"] == "Aarhus"
    assert api.get(tok, f"/workspaces/{ws}/own-voices/manuscripts/standard").json()["sentences"].__len__() == 400

    base = {"speaker_name": "Mette Hansen", "manuscript": "kort"}
    assert api.post(tok, f"/workspaces/{ws}/own-voices", base | {"consent_typed_name": "Mette Hansen",
                                                                  "consent_accepted": False}).status_code == 422
    assert api.post(tok, f"/workspaces/{ws}/own-voices", base | {"consent_typed_name": "Hans Jensen",
                                                                  "consent_accepted": True}).status_code == 422
    r = api.post(tok, f"/workspaces/{ws}/own-voices", base | {"consent_typed_name": "mette hansen", "consent_accepted": True})
    assert r.status_code == 201, r.text
    pid = r.json()["id"]
    assert "Mette Hansen" in r.json()["consent"]["text"] and "trække samtykket tilbage" in r.json()["consent"]["text"]
    proj = db.get(OwnVoiceProject, __import__("uuid").UUID(pid))
    rights = db.get(VoiceRightsRecord, proj.rights_record_id)
    assert rights.kind == "speaker_agreement" and rights.status == "unreviewed"  # never approved by code

    # recordings: invalid, too quiet, unknown sentence, then all good
    assert _put(api, tok, ws, pid, "kort-001", b"not a wav").status_code == 422
    q = _put(api, tok, ws, pid, "kort-001", _wav(amp=0.004)).json()["qc"]
    assert "for_lav" in q["flags"] and not q["ok"]
    assert _put(api, tok, ws, pid, "kort-999", _wav()).status_code == 404
    assert api.post(tok, f"/workspaces/{ws}/own-voices/{pid}/submit").status_code == 409  # incomplete
    for s in m["sentences"]:
        r = _put(api, tok, ws, pid, s["id"], _wav())
        assert r.status_code == 200 and r.json()["qc"]["ok"], r.text
    audio = api.get(tok, f"/workspaces/{ws}/own-voices/{pid}/recordings/kort-003/audio")
    assert audio.status_code == 200 and audio.content[:4] == b"RIFF"
    # another workspace sees nothing
    assert api.get(t["tok_b"], f"/workspaces/{t['ws_b']}/own-voices").json()["items"] == []
    assert _put(api, t["tok_b"], t["ws_b"], pid, "kort-001", _wav()).status_code == 404

    r = api.post(tok, f"/workspaces/{ws}/own-voices/{pid}/submit")
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["status"] == "submitted" and out["voice"]["consent_review"] == "unreviewed"
    assert out["voice"]["version_status"] == "pending_review" and out["voice"]["active"] is False
    v = db.query(VoiceVersion).filter_by(profile_id=__import__("uuid").UUID(out["voice"]["profile_id"])).one()
    assert v.checks["rights"]["status"] == "failed"  # waits for a person to review the consent
    assert 7 <= v.references[0]["seconds"] <= 12.5
    # an operator cannot approve before the consent is reviewed
    op = api.user("op-own@testmail.dk")
    u = db.query(User).filter_by(email_normalized="op-own@testmail.dk").one()
    u.is_platform_operator = True
    db.commit()
    assert api.post(op, f"/operator/voice-versions/{v.id}/approve").status_code == 409
    # the customer's library shows nothing unapproved
    assert all(i["id"] != out["voice"]["profile_id"] for i in api.get(tok, f"/workspaces/{ws}/voices").json()["items"])

    files = [p for p in Path(env).rglob("*.wav")]
    assert any("own-voices" in str(p) for p in files)
    r = api.delete(tok, f"/workspaces/{ws}/own-voices/{pid}")
    assert r.status_code == 200 and r.json()["status"] == "withdrawn"
    assert not [p for p in Path(env).rglob("*.wav") if "own-voices" in str(p) or out["voice"]["profile_id"][:8] in str(p)]
    db.expire_all()
    assert db.get(VoiceRightsRecord, proj.rights_record_id).status == "blocked"
    assert db.get(VoiceVersion, v.id).status == "retired"


def test_own_voice_requires_admin(api, two_workspaces, db, env):
    t = two_workspaces
    staff = api.add_member(t["tok_a"], t["ws_a"], "staff-own@testmail.dk", "staff")
    assert api.get(staff, f"/workspaces/{t['ws_a']}/own-voices").status_code == 403

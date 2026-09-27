"""TTS service mechanics with the fake engine (no model weights needed): auth, Danish only, formats and
resampling, pinned model revision, backpressure, cancellation, voice isolation between interleaved sessions."""
from __future__ import annotations

import asyncio
import hashlib
import io
import wave

import pytest
from fastapi.testclient import TestClient

from tts_service.app import Config, create_app

TOKEN = "t" * 40
REV = "f" * 40


def _cfg(monkeypatch, **env):
    monkeypatch.setenv("TTS_SERVICE_TOKEN", TOKEN)
    monkeypatch.setenv("TTS_ENGINE", "fake")
    monkeypatch.setenv("MODEL_REVISION", REV)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    return Config()


@pytest.fixture
def ref(tmp_path, monkeypatch):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(24000)
        w.writeframes(b"\x00\x01" * 24000)
    data = buf.getvalue()
    key = "platform/voices/coral-tts-a/refs/x.wav"
    (tmp_path / "platform/voices/coral-tts-a/refs").mkdir(parents=True)
    (tmp_path / key).write_bytes(data)
    monkeypatch.setenv("VOICE_STORAGE_DIR", str(tmp_path))
    return {"key": key, "sha256": hashlib.sha256(data).hexdigest()}


def _body(ref, version="v1", **kw):
    b = {"voice": {"version_id": version, "engine": "chatterbox-multilingual", "model_repo": "CoRal-project/roest-v3-chatterbox-500m",
                   "model_revision": REV, "references": [ref], "settings": {"exaggeration": 0.5}},
         "text": "Hej, du taler med en digital assistent.", "language": "da", "format": "pcm_s16le",
         "sample_rate": 24000, "request_id": "req-00000001"}
    b.update(kw)
    return b


H = {"authorization": f"Bearer {TOKEN}"}


def test_auth_ready_and_danish_only(monkeypatch, ref):
    with TestClient(create_app(_cfg(monkeypatch))) as c:
        assert c.get("/health").json() == {"status": "ok"}
        assert c.get("/ready").status_code == 401
        r = c.get("/ready", headers=H).json()
        assert r["ready"] and r["simulated"] and r["model_revision"] == REV
        assert c.post("/v1/synthesize", json=_body(ref)).status_code == 401
        assert c.post("/v1/synthesize", json=_body(ref, language="sv"), headers=H).status_code == 422
        other = _body(ref)
        other["voice"]["model_revision"] = "0" * 40
        assert c.post("/v1/synthesize", json=other, headers=H).status_code == 409


def test_formats_and_resampling(monkeypatch, ref):
    with TestClient(create_app(_cfg(monkeypatch))) as c:
        r24 = c.post("/v1/synthesize", json=_body(ref), headers=H)
        r8 = c.post("/v1/synthesize", json=_body(ref, sample_rate=8000, request_id="req-00000002"), headers=H)
        assert r24.status_code == r8.status_code == 200
        assert r24.headers["x-sample-rate"] == "24000" and r8.headers["x-sample-rate"] == "8000"
        assert abs(len(r8.content) * 3 - len(r24.content)) <= 6  # same duration, a third of the samples
        wav = c.post("/v1/synthesize", json=_body(ref, format="wav", request_id="req-00000003"), headers=H)
        assert wav.content[:4] == b"RIFF" and wav.headers["content-type"] == "audio/wav"
        assert c.post("/v1/synthesize", json=_body(ref, sample_rate=12345), headers=H).status_code == 422
        m = c.get("/metrics", headers=H).json()
        assert m["requests"] == 3 and m["synth_ms_p95"] is not None


def test_bad_reference_checksum_is_refused(monkeypatch, ref):
    with TestClient(create_app(_cfg(monkeypatch)), raise_server_exceptions=False) as c:
        bad = dict(ref, sha256="0" * 64)
        assert c.post("/v1/synthesize", json=_body(bad), headers=H).status_code == 500


def test_cancel_before_start(monkeypatch, ref):
    with TestClient(create_app(_cfg(monkeypatch))) as c:
        assert c.delete("/v1/requests/req-cancel-1", headers=H).status_code == 200
        assert c.post("/v1/synthesize", json=_body(ref, request_id="req-cancel-1"), headers=H).status_code == 409


def test_backpressure(monkeypatch, ref):
    app = create_app(_cfg(monkeypatch, TTS_QUEUE_LIMIT="1", TTS_QUEUE_TIMEOUT="0.2"))
    with TestClient(app) as c:
        state = app.state.tts
        state.waiting = 1  # queue full
        r = c.post("/v1/synthesize", json=_body(ref), headers=H)
        assert r.status_code == 503 and r.headers["retry-after"] == "1"
        state.waiting = 0

        async def hold():
            await state.slot.acquire()

        asyncio.run(hold())  # the only generation slot is taken → queue wait times out
        r = c.post("/v1/synthesize", json=_body(ref, request_id="req-00000009"), headers=H)
        assert r.status_code == 503
        state.slot.release()


def test_interleaved_voices_do_not_leak(monkeypatch, ref):
    with TestClient(create_app(_cfg(monkeypatch))) as c:
        a1 = c.post("/v1/synthesize", json=_body(ref, version="voice-a"), headers=H).content
        b1 = c.post("/v1/synthesize", json=_body(ref, version="voice-b", request_id="req-00000011"), headers=H).content
        a2 = c.post("/v1/synthesize", json=_body(ref, version="voice-a", request_id="req-00000012"), headers=H).content
        assert a1 == a2 and a1 != b1

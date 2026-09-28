"""TTS service mechanics with the fake engine (no model weights needed): auth, Danish only, formats and
resampling, pinned model revision, backpressure, cancellation, voice isolation between interleaved sessions."""
from __future__ import annotations

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

        eng = state.pool.get_nowait()  # the only model instance is busy → queue wait times out
        r = c.post("/v1/synthesize", json=_body(ref, request_id="req-00000009"), headers=H)
        assert r.status_code == 503
        r = c.post("/v1/synthesize/stream", json=_body(ref, request_id="req-00000010"), headers=H)
        assert r.status_code == 503
        state.pool.put_nowait(eng)


def test_interleaved_voices_do_not_leak(monkeypatch, ref):
    with TestClient(create_app(_cfg(monkeypatch))) as c:
        a1 = c.post("/v1/synthesize", json=_body(ref, version="voice-a"), headers=H).content
        b1 = c.post("/v1/synthesize", json=_body(ref, version="voice-b", request_id="req-00000011"), headers=H).content
        a2 = c.post("/v1/synthesize", json=_body(ref, version="voice-a", request_id="req-00000012"), headers=H).content
        assert a1 == a2 and a1 != b1


def test_clean_trims_model_hiss_and_shortens_pauses_without_touching_speech(monkeypatch):
    import numpy as np

    from tts_service import engines
    from tts_service.engines import clean

    monkeypatch.setattr(engines, "speech_segments", lambda x, sr: None)  # level fallback: deterministic, no VAD model

    sr = 24000
    rng = np.random.default_rng(3)

    def hiss(sec):
        return (0.006 * rng.standard_normal(int(sr * sec))).astype(np.float32)  # ~ -44 dBFS, like the model's tails

    def speech(sec):
        t = np.arange(int(sr * sec)) / sr
        return (0.2 * np.sin(2 * np.pi * 180 * t) * (1 + 0.3 * np.sin(2 * np.pi * 4 * t))).astype(np.float32)

    x = np.concatenate([hiss(0.8), speech(1.0), hiss(1.3), speech(1.2), hiss(0.9)])
    y = clean(x, sr)
    assert 2.2 * sr < len(y) < 2.9 * sr  # tails cut, the 1.3 s gap shortened to <= 0.45 s
    loud = np.abs(y) > 0.1
    assert loud.sum() > 0.9 * (np.abs(x) > 0.1).sum()  # the speech itself survives
    first = int(np.argmax(loud))
    assert first < 0.1 * sr  # no long lead-in of hiss before the first word


def test_designed_voice_loads_verified_conditioning_file(monkeypatch, tmp_path):
    data = b"designed-conditioning-bytes"
    key = "platform/voices/designet-jysk-mand/conds-abc.pt"
    (tmp_path / "platform/voices/designet-jysk-mand").mkdir(parents=True)
    (tmp_path / key).write_bytes(data)
    monkeypatch.setenv("VOICE_STORAGE_DIR", str(tmp_path))
    good = hashlib.sha256(data).hexdigest()
    with TestClient(create_app(_cfg(monkeypatch))) as c:
        b = _body({"key": "unused", "sha256": "0" * 64})
        b["voice"].update(method="designed_blend", checkpoint_key=key, checkpoint_sha256=good, references=[])
        r = c.post("/v1/synthesize", headers=H, json=b)
        assert r.status_code == 200 and len(r.content) > 1000
        b["voice"].update(version_id="v2", checkpoint_sha256="1" * 64)  # tampered file / wrong checksum
        b["request_id"] = "req-00000002"
        with pytest.raises(ValueError, match="checksum"):
            c.post("/v1/synthesize", headers=H, json=b)
        b["voice"].update(version_id="v3", checkpoint_key=None)
        b["request_id"] = "req-00000003"
        assert c.post("/v1/synthesize", headers=H, json=b).status_code == 422


def test_stream_sends_the_same_audio_in_chunks(monkeypatch, ref):
    app = create_app(_cfg(monkeypatch, TTS_STREAM_FIRST_TOKENS="5", TTS_STREAM_STEP_TOKENS="5"))
    with TestClient(app) as c:
        whole = c.post("/v1/synthesize", json=_body(ref), headers=H).content
        with c.stream("POST", "/v1/synthesize/stream", json=_body(ref, request_id="req-00000020"), headers=H) as r:
            assert r.status_code == 200 and r.headers["x-simulated"] == "1"
            assert int(r.headers["x-first-audio-ms"]) >= 0
            chunks = list(r.iter_raw())
        assert b"".join(chunks) == whole
        m = c.get("/metrics", headers=H).json()
        assert m["first_audio_ms_p50"] is not None and m["replicas"] == 1
        # 16 kHz: chunk-wise resampling matches resampling the whole utterance (no seams, same length)
        import numpy as np

        w16 = np.frombuffer(c.post("/v1/synthesize", json=_body(ref, sample_rate=16000, request_id="req-00000021"),
                                   headers=H).content, dtype="<i2").astype(float)
        s16 = np.frombuffer(c.post("/v1/synthesize/stream", json=_body(ref, sample_rate=16000, request_id="req-00000022"),
                                   headers=H).content, dtype="<i2").astype(float)
        assert abs(len(s16) - len(w16)) <= 2
        n = min(len(s16), len(w16))
        assert np.max(np.abs(s16[:n] - w16[:n])) < 0.02 * 32767


def test_stream_validation_and_pool_release(monkeypatch, ref):
    app = create_app(_cfg(monkeypatch, TTS_REPLICAS="2"))
    with TestClient(app) as c:
        assert c.post("/v1/synthesize/stream", json=_body(ref, format="wav"), headers=H).status_code == 422
        assert c.post("/v1/synthesize/stream", json=_body(ref, language="sv"), headers=H).status_code == 422
        c.delete("/v1/requests/req-cancel-2", headers=H)
        assert c.post("/v1/synthesize/stream", json=_body(ref, request_id="req-cancel-2"), headers=H).status_code == 409
        for i in range(3):  # every request hands its model instance back, also after a refusal
            assert c.post("/v1/synthesize/stream", json=_body(ref, request_id=f"req-0000003{i}"), headers=H).status_code == 200
        assert app.state.tts.pool.qsize() == 2
        assert c.get("/metrics", headers=H).json()["replicas"] == 2


def test_decode_stitcher_is_seamless():
    import numpy as np

    from tts_service.streaming import DecodeStitcher

    rng = np.random.default_rng(1)
    full = rng.standard_normal(24000 * 3).astype(np.float32)
    st = DecodeStitcher()
    out = [st.feed(full[:n]) for n in (6000, 9000, 20000, 40000, 60000)]
    out.append(st.feed(full, final=True))
    y = np.concatenate(out)
    assert len(y) == len(full) and np.allclose(y, full, atol=1e-6)  # identical decodes → identical audio
    # decodes that disagree a little at the seam: nothing lost, nothing doubled
    st = DecodeStitcher()
    parts = [st.feed(full[:20000] * 1.01), st.feed(full[:50000] * 0.99), st.feed(full, final=True)]
    assert sum(len(p) for p in parts) == len(full)


def test_stream_resampler_matches_whole_file():
    import numpy as np

    from tts_service.engines import resample
    from tts_service.streaming import StreamResampler

    t = np.arange(24000 * 2) / 24000
    x = (0.3 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
    rs = StreamResampler(24000, 16000)
    y = np.concatenate([rs.feed(x[a:a + 5003]) for a in range(0, len(x), 5003)] + [rs.feed(np.zeros(0, np.float32), final=True)])
    ref_ = resample(x, 24000, 16000)
    assert abs(len(y) - len(ref_)) <= 2
    n = min(len(y), len(ref_))
    assert np.max(np.abs(y[100:n - 100] - ref_[100:n - 100])) < 0.01


def test_decode_stitcher_with_windowed_decodes():
    import numpy as np
    import pytest as _pytest

    from tts_service.streaming import SAMPLES_PER_TOKEN as T  # noqa: N811
    from tts_service.streaming import DecodeStitcher

    rng = np.random.default_rng(2)
    full = rng.standard_normal(T * 120).astype(np.float32)
    st = DecodeStitcher()
    out, window, step = [], 36, 20
    for n in range(12, 120, step):  # each decode covers only the newest `window` tokens
        start = max(0, n - window)
        out.append(st.feed(full[start * T:n * T], offset=start * T))
    start = 120 - window
    out.append(st.feed(full[start * T:], final=True, offset=start * T))
    y = np.concatenate(out)
    assert len(y) == len(full) and np.allclose(y, full, atol=1e-6)
    with _pytest.raises(ValueError):  # a window that starts after unsent audio would leave a gap
        DecodeStitcher().feed(full[T * 50:], offset=T * 50)

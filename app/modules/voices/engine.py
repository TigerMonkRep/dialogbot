"""Client for the separate speech-synthesis service (tts_service/).

The API process never loads a speech model. It sends a request with the pinned voice version, the
already-normalised Danish text, the wanted format and sample rate, a request ID and a session ID, and
receives raw audio. Requests can be cancelled by request ID.

TTS_ENGINE=fake (dev/test only) returns a short tone whose pitch depends on the voice version, so tests can
tell voices apart. Every fake result carries `simulated=True`; it must never be shown as real speech.
"""
from __future__ import annotations

import hashlib
import math
import struct
import time
import uuid
from collections.abc import Iterator
from dataclasses import dataclass

from app.config import get_settings
from app.core.errors import ApiError, NotImplementedYet

FORMATS = ("pcm_s16le", "wav")
SAMPLE_RATES = (8000, 16000, 22050, 24000, 44100, 48000)
LANGUAGE = "da"  # Chatterbox Multilingual language id for Danish – sent explicitly on every request


class EngineUnavailable(ApiError):
    status_code = 503
    code = "tts_unavailable"


class EngineBusy(ApiError):
    status_code = 503
    code = "tts_busy"


@dataclass
class Synthesis:
    pcm: bytes  # mono 16-bit little-endian
    sample_rate: int
    simulated: bool
    synth_ms: int
    model_revision: str


def status() -> str:
    s = get_settings()
    if s.tts_engine == "http":
        return "available"
    if s.tts_engine == "fake":
        return "simulated"
    return "not_configured"


def voice_payload(version) -> dict:
    return {"version_id": str(version.id), "engine": version.engine, "method": version.method,
            "model_repo": version.model_repo, "model_revision": version.model_revision,
            "checkpoint_key": version.checkpoint_key,
            "checkpoint_sha256": (version.provenance or {}).get("checkpoint_sha256"),
            "references": [{"key": r["key"], "sha256": r["sha256"]} for r in version.references or []],
            "settings": version.settings or {}}


def synthesize(version, text: str, *, sample_rate: int = 24000, request_id: str | None = None,
               session_id: str | None = None) -> Synthesis:
    if sample_rate not in SAMPLE_RATES:
        raise ApiError("Ikke-understøttet samplerate", code="unsupported_sample_rate", status_code=422)
    s = get_settings()
    request_id = request_id or uuid.uuid4().hex
    if s.tts_engine == "fake":
        return _fake(version, text, sample_rate)
    if s.tts_engine != "http":
        raise NotImplementedYet("Talemotoren er ikke sat op (TTS_ENGINE)", code="tts_not_configured")
    import httpx

    body = {"voice": voice_payload(version), "text": text, "language": LANGUAGE, "format": "pcm_s16le",
            "sample_rate": sample_rate, "request_id": request_id, "session_id": session_id}
    t0 = time.monotonic()
    try:
        r = httpx.post(f"{s.tts_service_url.rstrip('/')}/v1/synthesize", json=body, timeout=s.tts_timeout_seconds,
                       headers={"authorization": f"Bearer {s.tts_service_token}", "x-request-id": request_id})
    except httpx.TimeoutException as e:
        cancel(request_id)
        raise EngineUnavailable("Talemotoren svarede ikke i tide") from e
    except httpx.HTTPError as e:
        raise EngineUnavailable("Talemotoren kan ikke nås") from e
    if r.status_code in (429, 503):
        raise EngineBusy("Talemotoren er optaget. Prøv igen om lidt.")
    if r.status_code >= 400:
        raise EngineUnavailable(f"Talemotoren afviste forespørgslen ({r.status_code})")
    return Synthesis(pcm=r.content, sample_rate=int(r.headers.get("x-sample-rate", sample_rate)),
                     simulated=r.headers.get("x-simulated") == "1",  # a test engine behind HTTP stays labelled
                     synth_ms=int(r.headers.get("x-synthesis-ms") or (time.monotonic() - t0) * 1000),
                     model_revision=r.headers.get("x-model-revision", version.model_revision))


def synthesize_stream(version, text: str, *, sample_rate: int = 24000, request_id: str | None = None,
                      session_id: str | None = None) -> Iterator[bytes]:
    """Raw PCM chunks while the speech is generated (tts_service /v1/synthesize/stream).

    A generator: nothing is requested until the first next(). Errors before the first chunk raise the same
    EngineBusy/EngineUnavailable as synthesize(), so the caller can still fall back; a failure later ends the
    stream early (whole chunks only). Closing the generator closes the connection, which stops generation."""
    if sample_rate not in SAMPLE_RATES:
        raise ApiError("Ikke-understøttet samplerate", code="unsupported_sample_rate", status_code=422)
    s = get_settings()
    request_id = request_id or uuid.uuid4().hex
    if s.tts_engine == "fake":
        pcm = _fake(version, text, sample_rate).pcm
        step = sample_rate // 5 * 2  # 200 ms of 16-bit audio
        for i in range(0, len(pcm), step):
            yield pcm[i:i + step]
        return
    if s.tts_engine != "http":
        raise NotImplementedYet("Talemotoren er ikke sat op (TTS_ENGINE)", code="tts_not_configured")
    import httpx

    body = {"voice": voice_payload(version), "text": text, "language": LANGUAGE, "format": "pcm_s16le",
            "sample_rate": sample_rate, "request_id": request_id, "session_id": session_id}
    started = False
    try:
        with httpx.stream("POST", f"{s.tts_service_url.rstrip('/')}/v1/synthesize/stream", json=body,
                          timeout=httpx.Timeout(s.tts_timeout_seconds, connect=5.0),
                          headers={"authorization": f"Bearer {s.tts_service_token}", "x-request-id": request_id}) as r:
            if r.status_code in (429, 503):
                raise EngineBusy("Talemotoren er optaget. Prøv igen om lidt.")
            if r.status_code >= 400:
                raise EngineUnavailable(f"Talemotoren afviste forespørgslen ({r.status_code})")
            carry = b""
            for chunk in r.iter_bytes():
                data = carry + chunk
                cut = len(data) - len(data) % 2  # never split a 16-bit sample
                carry = data[cut:]
                if cut:
                    started = True
                    yield data[:cut]
    except httpx.TimeoutException as e:
        cancel(request_id)
        if not started:
            raise EngineUnavailable("Talemotoren svarede ikke i tide") from e
    except httpx.HTTPError as e:
        if not started:
            raise EngineUnavailable("Talemotoren kan ikke nås") from e


def cancel(request_id: str) -> None:
    s = get_settings()
    if s.tts_engine != "http":
        return
    import httpx

    try:
        httpx.delete(f"{s.tts_service_url.rstrip('/')}/v1/requests/{request_id}", timeout=3.0,
                     headers={"authorization": f"Bearer {s.tts_service_token}"})
    except httpx.HTTPError:
        pass


def health() -> dict:
    s = get_settings()
    if s.tts_engine == "fake":
        return {"status": "simulated"}
    if s.tts_engine != "http":
        return {"status": "not_configured"}
    import httpx

    try:
        r = httpx.get(f"{s.tts_service_url.rstrip('/')}/ready", timeout=5.0,
                      headers={"authorization": f"Bearer {s.tts_service_token}"})
        return r.json() | {"status": "ready" if r.status_code == 200 else "not_ready"}
    except (httpx.HTTPError, ValueError):
        return {"status": "unreachable"}


def _fake(version, text: str, sample_rate: int) -> Synthesis:
    """A tone (not speech): 60 ms per word, pitch from the version id. Clearly simulated."""
    # continuous pitch from 32 hash bits: two versions sharing a tone (and identical PCM) is ~2^-32, not 1/220
    h = int(hashlib.sha256(str(version.id).encode()).hexdigest()[:8], 16)
    freq = 180 + 220 * h / 2**32
    n = int(sample_rate * max(0.3, 0.06 * len(text.split())))
    pcm = b"".join(struct.pack("<h", int(3000 * math.sin(2 * math.pi * freq * i / sample_rate))) for i in range(n))
    return Synthesis(pcm=pcm, sample_rate=sample_rate, simulated=True, synth_ms=1, model_revision="fake")


def wav(pcm: bytes, sample_rate: int) -> bytes:
    """Wrap mono 16-bit PCM in a WAV container (browser preview)."""
    import io
    import wave

    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(pcm)
    return buf.getvalue()

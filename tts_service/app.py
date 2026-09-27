"""Dialogbot TTS service – a separate, always-warm process on CPU/GPU hardware.

    POST   /v1/synthesize          text → raw mono 16-bit PCM (or WAV) at the requested sample rate
    DELETE /v1/requests/{id}       cancel a queued/running request (its result is discarded)
    GET    /health                 process alive
    GET    /ready                  model loaded and warmed up (503 until then)
    GET    /metrics                queue depth and recent timings (no text)

Auth: Authorization: Bearer $TTS_SERVICE_TOKEN (the Dialogbot API is the only client).
Safety: bounded queue (503 + Retry-After when full), queue and generation timeouts, one generation at a time
per model instance (the model's voice state is shared), per-voice conditioning cache keyed by version id +
reference checksums, model revision must match the version's pinned revision, text is never logged.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import io
import os
import tempfile
import time
import wave
from collections import OrderedDict, deque
from contextlib import asynccontextmanager
from pathlib import Path

import anyio
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

from tts_service import engines, refs

SAMPLE_RATES = (8000, 16000, 22050, 24000, 44100, 48000)


class Config:
    def __init__(self) -> None:
        self.token = os.environ.get("TTS_SERVICE_TOKEN", "")
        self.engine = os.environ.get("TTS_ENGINE", "chatterbox")
        self.model_repo = os.environ.get("MODEL_REPO", "ResembleAI/chatterbox")
        self.model_revision = os.environ.get("MODEL_REVISION", "")
        self.device = os.environ.get("TTS_DEVICE", "cuda")
        self.queue_limit = int(os.environ.get("TTS_QUEUE_LIMIT", "8"))
        self.queue_timeout = float(os.environ.get("TTS_QUEUE_TIMEOUT", "10"))
        self.gen_timeout = float(os.environ.get("TTS_GENERATION_TIMEOUT", "20"))
        self.max_chars = int(os.environ.get("TTS_MAX_CHARS", "600"))
        self.voice_cache = int(os.environ.get("TTS_VOICE_CACHE", "32"))
        if len(self.token) < 32:
            raise RuntimeError("TTS_SERVICE_TOKEN (>=32 chars) is required")


class VoiceIn(BaseModel):
    version_id: str
    engine: str
    model_repo: str
    model_revision: str
    checkpoint_key: str | None = None
    references: list[dict] = Field(default_factory=list)
    settings: dict = Field(default_factory=dict)


class SynthIn(BaseModel):
    voice: VoiceIn
    text: str = Field(min_length=1)
    language: str
    format: str = "pcm_s16le"
    sample_rate: int = 24000
    request_id: str = Field(min_length=8, max_length=64)
    session_id: str | None = None


class State:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        if cfg.engine == "fake":
            self.engine = engines.FakeEngine(cfg.model_repo, cfg.model_revision or "f" * 40)
        else:
            self.engine = engines.ChatterboxEngine(cfg.model_repo, cfg.model_revision, cfg.device,
                                                   os.environ.get("HF_HOME"))
        self.ready = False
        self.waiting = 0
        self.slot = asyncio.Semaphore(1)
        self.cancelled: set[str] = set()
        self.voices: OrderedDict[str, engines.VoiceState] = OrderedDict()
        self.timings: deque[tuple[float, float]] = deque(maxlen=200)  # (synth_ms, audio_seconds)
        self.refdir = Path(tempfile.mkdtemp(prefix="tts-refs-"))

    def load(self) -> None:
        self.engine.load()
        # warm-up so the first customer request does not pay CUDA/graph initialisation
        if isinstance(self.engine, engines.FakeEngine):
            self.ready = True
            return
        with self.engine.lock:
            conds = self.engine.model.conds  # built-in default voice shipped with the model (conds.pt)
            if conds is not None:
                self.engine.generate(engines.VoiceState("warmup", conds, {}), "Hej.")
        self.ready = True


def create_app(cfg: Config | None = None) -> FastAPI:
    cfg = cfg or Config()
    state = State(cfg)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        await anyio.to_thread.run_sync(state.load)
        yield

    app = FastAPI(title="Dialogbot TTS", lifespan=lifespan)
    app.state.tts = state

    def auth(authorization: str | None) -> None:
        token = (authorization or "")[7:] if (authorization or "").lower().startswith("bearer ") else ""
        if not token or not hmac.compare_digest(token.encode(), cfg.token.encode()):
            raise HTTPException(401, "unauthorized")

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/ready")
    def ready(authorization: str | None = Header(default=None)):
        auth(authorization)
        body = {"ready": state.ready, "engine": state.engine.name, "model_repo": cfg.model_repo,
                "model_revision": state.engine.model_revision, "watermark": state.engine.watermark,
                "simulated": state.engine.simulated, "queue": state.waiting}
        return JSONResponse(body, status_code=200 if state.ready else 503)

    @app.get("/metrics")
    def metrics(authorization: str | None = Header(default=None)):
        auth(authorization)
        ms = sorted(t[0] for t in state.timings)
        rtf = sorted(t[0] / 1000 / t[1] for t in state.timings if t[1] > 0)

        def pct(xs, p):
            return round(xs[min(len(xs) - 1, int(len(xs) * p))], 3) if xs else None

        return {"requests": len(ms), "synth_ms_p50": pct(ms, 0.5), "synth_ms_p95": pct(ms, 0.95),
                "rtf_p50": pct(rtf, 0.5), "rtf_p95": pct(rtf, 0.95), "queue": state.waiting,
                "voices_cached": len(state.voices)}

    @app.delete("/v1/requests/{request_id}")
    def cancel(request_id: str, authorization: str | None = Header(default=None)):
        auth(authorization)
        state.cancelled.add(request_id)
        if len(state.cancelled) > 10_000:
            state.cancelled.clear()
        return {"cancelled": request_id}

    def voice_state(v: VoiceIn) -> engines.VoiceState:
        key = hashlib.sha256((v.version_id + "|" + "|".join(r.get("sha256", "") for r in v.references) + "|" +
                              repr(sorted(v.settings.items()))).encode()).hexdigest()
        if key in state.voices:
            state.voices.move_to_end(key)
            return state.voices[key]
        ref_path = None
        if v.references:
            ref_path = str(refs.fetch(v.references[0]["key"], v.references[0]["sha256"], state.refdir))
        vs = state.engine.prepare_voice(key, ref_path, v.settings)
        state.voices[key] = vs
        while len(state.voices) > cfg.voice_cache:
            state.voices.popitem(last=False)
        return vs

    def run(body: SynthIn) -> tuple[bytes, int, float]:
        t0 = time.monotonic()
        vs = voice_state(body.voice)  # prepares conditionals under the engine lock if not cached
        with state.engine.lock:  # the model's voice state is shared: one generation at a time
            if body.request_id in state.cancelled:
                raise HTTPException(409, "cancelled")
            audio = state.engine.generate(vs, body.text)
        seconds = len(audio) / state.engine.sample_rate
        audio = engines.resample(audio, state.engine.sample_rate, body.sample_rate)
        return engines.to_pcm16(audio), int((time.monotonic() - t0) * 1000), seconds

    @app.post("/v1/synthesize")
    async def synthesize(body: SynthIn, request: Request, authorization: str | None = Header(default=None)):
        auth(authorization)
        if not state.ready:
            raise HTTPException(503, "model not ready")
        if body.language != "da":
            raise HTTPException(422, "only Danish (da) is served")
        if body.format not in ("pcm_s16le", "wav") or body.sample_rate not in SAMPLE_RATES:
            raise HTTPException(422, "unsupported format or sample rate")
        if len(body.text) > cfg.max_chars:
            raise HTTPException(413, "text too long for one unit")
        if body.voice.model_repo != cfg.model_repo or body.voice.model_revision != state.engine.model_revision:
            raise HTTPException(409, "voice version was approved for another model revision")
        if body.voice.checkpoint_key:
            raise HTTPException(501, "fine-tuned checkpoints are not loaded by this service build")
        if state.waiting >= cfg.queue_limit:
            return JSONResponse({"detail": "busy"}, status_code=503, headers={"retry-after": "1"})
        state.waiting += 1
        try:
            try:
                await asyncio.wait_for(state.slot.acquire(), timeout=cfg.queue_timeout)
            except TimeoutError:
                return JSONResponse({"detail": "queue timeout"}, status_code=503, headers={"retry-after": "1"})
        finally:
            state.waiting -= 1
        try:
            if body.request_id in state.cancelled or await request.is_disconnected():
                raise HTTPException(409, "cancelled")
            try:
                pcm, synth_ms, seconds = await asyncio.wait_for(anyio.to_thread.run_sync(run, body),
                                                                timeout=cfg.gen_timeout)
            except TimeoutError as e:
                raise HTTPException(504, "generation timeout") from e
        finally:
            state.slot.release()
        if body.request_id in state.cancelled:
            raise HTTPException(409, "cancelled")
        state.timings.append((synth_ms, seconds))
        headers = {"x-sample-rate": str(body.sample_rate), "x-synthesis-ms": str(synth_ms),
                   "x-model-revision": state.engine.model_revision, "x-watermark": state.engine.watermark,
                   "x-simulated": "1" if state.engine.simulated else "0"}
        if body.format == "wav":
            buf = io.BytesIO()
            with wave.open(buf, "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(body.sample_rate)
                w.writeframes(pcm)
            return Response(buf.getvalue(), media_type="audio/wav", headers=headers)
        return Response(pcm, media_type="application/octet-stream", headers=headers)

    return app


app = create_app() if os.environ.get("TTS_SERVICE_TOKEN") else None

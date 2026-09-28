"""Dialogbot TTS service – a separate, always-warm process on CPU/GPU hardware.

    POST   /v1/synthesize          text → raw mono 16-bit PCM (or WAV) at the requested sample rate
    POST   /v1/synthesize/stream   same, but PCM is sent while it is generated (first audio after ~0.5 s speech)
    DELETE /v1/requests/{id}       cancel a queued/running request (its result is discarded)
    GET    /health                 process alive
    GET    /ready                  model loaded and warmed up (503 until then)
    GET    /metrics                queue depth and recent timings (no text)

Auth: Authorization: Bearer $TTS_SERVICE_TOKEN (the Dialogbot API is the only client).
Safety: bounded queue (503 + Retry-After when full), queue and generation timeouts, one generation at a time
per model instance (the model's voice state is shared; TTS_REPLICAS loads more instances on the same GPU), per-voice conditioning cache keyed by version id +
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
import numpy as np
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pydantic import BaseModel, Field

from tts_service import engines, refs, streaming

SAMPLE_RATES = (8000, 16000, 22050, 24000, 44100, 48000)


class Config:
    def __init__(self) -> None:
        self.token = os.environ.get("TTS_SERVICE_TOKEN", "")
        self.engine = os.environ.get("TTS_ENGINE", "chatterbox")
        self.model_repo = os.environ.get("MODEL_REPO", engines.DEFAULT_REPO)
        self.model_revision = os.environ.get("MODEL_REVISION", "")
        self.model_t3 = os.environ.get("MODEL_T3", engines.DEFAULT_T3)
        self.device = os.environ.get("TTS_DEVICE", "cuda")
        self.queue_limit = int(os.environ.get("TTS_QUEUE_LIMIT", "8"))
        self.queue_timeout = float(os.environ.get("TTS_QUEUE_TIMEOUT", "10"))
        self.gen_timeout = float(os.environ.get("TTS_GENERATION_TIMEOUT", "20"))
        self.max_chars = int(os.environ.get("TTS_MAX_CHARS", "600"))
        self.voice_cache = int(os.environ.get("TTS_VOICE_CACHE", "32"))
        self.replicas = max(1, int(os.environ.get("TTS_REPLICAS", "1")))
        self.first_tokens = int(os.environ.get("TTS_STREAM_FIRST_TOKENS", "12"))
        self.step_tokens = int(os.environ.get("TTS_STREAM_STEP_TOKENS", "20"))
        w = os.environ.get("TTS_STREAM_WINDOW_TOKENS", "")
        self.window_tokens = int(w) if w else None
        pt = os.environ.get("TTS_STREAM_PROMPT_TOKENS", "")
        self.prompt_tokens = int(pt) if pt else None
        self.cfm_steps = int(os.environ.get("TTS_STREAM_CFM_STEPS", "10"))
        if len(self.token) < 32:
            raise RuntimeError("TTS_SERVICE_TOKEN (>=32 chars) is required")


class VoiceIn(BaseModel):
    version_id: str
    engine: str
    method: str = "reference_conditioning"
    model_repo: str
    model_revision: str
    checkpoint_key: str | None = None
    checkpoint_sha256: str | None = None
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
    stream: dict | None = None  # streaming overrides for measurements: first, step, window, prompt_tokens, cfm_steps


class State:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        def make():
            if cfg.engine == "fake":
                return engines.FakeEngine(cfg.model_repo, cfg.model_revision or "f" * 40)
            return engines.ChatterboxEngine(cfg.model_repo, cfg.model_revision, cfg.device,
                                            os.environ.get("HF_HOME"), t3_file=cfg.model_t3)

        self.engines = [make() for _ in range(cfg.replicas)]
        self.engine = self.engines[0]  # model identity (repo, revision, watermark) is the same for all replicas
        self.ready = False
        self.waiting = 0
        self.pool: asyncio.Queue = asyncio.Queue()  # free model instances; holding one = exclusive use of it
        for e in self.engines:
            self.pool.put_nowait(e)
        self.cancelled: set[str] = set()
        self.voices: OrderedDict[str, engines.VoiceState] = OrderedDict()
        self.timings: deque[tuple[float, float]] = deque(maxlen=200)  # (synth_ms, audio_seconds)
        self.first_audio: deque[int] = deque(maxlen=200)  # streaming: ms until the first chunk was ready
        self.last_profile: dict | None = None  # where the time of the last streamed utterance went (no text)
        self.refdir = Path(tempfile.mkdtemp(prefix="tts-refs-"))

    def load(self) -> None:
        for e in self.engines:
            e.load()
            # warm-up so the first customer request does not pay CUDA/graph initialisation (and, for streaming,
            # the one-time capture of the token step as a CUDA graph)
            if isinstance(e, engines.FakeEngine):
                continue
            with e.lock:
                conds = e.model.conds  # built-in default voice shipped with the model (conds.pt)
                if conds is not None:
                    e.generate(engines.VoiceState("warmup", conds, {}), "Hej.")
                    for _ in range(2):
                        for _chunk in e.stream(engines.VoiceState("warmup", conds, {}), "Hej, det er en prøve."):
                            pass
                    e.model.conds = conds
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
                "model_revision": state.engine.model_revision, "model_t3": getattr(state.engine, "t3_file", None),
                "watermark": state.engine.watermark, "simulated": state.engine.simulated, "queue": state.waiting}
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
                "first_audio_ms_p50": pct(sorted(state.first_audio), 0.5),
                "first_audio_ms_p95": pct(sorted(state.first_audio), 0.95), "replicas": len(state.engines),
                "last_stream_profile": state.last_profile,
                "voices_cached": len(state.voices)}

    @app.delete("/v1/requests/{request_id}")
    def cancel(request_id: str, authorization: str | None = Header(default=None)):
        auth(authorization)
        state.cancelled.add(request_id)
        if len(state.cancelled) > 10_000:
            state.cancelled.clear()
        return {"cancelled": request_id}

    def voice_state(v: VoiceIn, eng) -> engines.VoiceState:
        key = hashlib.sha256((v.version_id + "|" + (v.checkpoint_sha256 or "") + "|" +
                              "|".join(r.get("sha256", "") for r in v.references) + "|" +
                              repr(sorted(v.settings.items()))).encode()).hexdigest()
        if key in state.voices:
            state.voices.move_to_end(key)
            return state.voices[key]
        if v.method == "designed_blend":  # precomputed conditioning (a voice that belongs to no one person)
            if not v.checkpoint_key or not v.checkpoint_sha256:
                raise HTTPException(422, "designed voice without checkpoint")
            path = refs.fetch(v.checkpoint_key, v.checkpoint_sha256, state.refdir, suffix=".pt")
            vs = eng.load_voice(key, str(path), v.settings)
        else:
            ref_path = None
            if v.references:
                ref_path = str(refs.fetch(v.references[0]["key"], v.references[0]["sha256"], state.refdir))
            vs = eng.prepare_voice(key, ref_path, v.settings)
        state.voices[key] = vs  # conditionals live on the device, so every replica can use them
        while len(state.voices) > cfg.voice_cache:
            state.voices.popitem(last=False)
        return vs

    def run(body: SynthIn, eng) -> tuple[bytes, int, float]:
        t0 = time.monotonic()
        vs = voice_state(body.voice, eng)  # prepares conditionals under the engine lock if not cached
        with eng.lock:  # the model's voice state is shared: one generation at a time per instance
            if body.request_id in state.cancelled:
                raise HTTPException(409, "cancelled")
            audio = eng.generate(vs, body.text)
        if not eng.simulated:
            audio = engines.clean(audio, eng.sample_rate)
        seconds = len(audio) / eng.sample_rate
        audio = engines.resample(audio, eng.sample_rate, body.sample_rate)
        return engines.to_pcm16(audio), int((time.monotonic() - t0) * 1000), seconds

    def check(body: SynthIn) -> None:
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
        if body.voice.checkpoint_key and body.voice.method != "designed_blend":
            raise HTTPException(501, "fine-tuned checkpoints are not loaded by this service build")
        if body.voice.method == "designed_blend" and not (body.voice.checkpoint_key and body.voice.checkpoint_sha256):
            raise HTTPException(422, "designed voice without checkpoint")

    async def acquire():
        """A free model instance, or None when the queue is full / the wait timed out (→ 503)."""
        if state.waiting >= cfg.queue_limit:
            return None
        state.waiting += 1
        try:
            return await asyncio.wait_for(state.pool.get(), timeout=cfg.queue_timeout)
        except TimeoutError:
            return None
        finally:
            state.waiting -= 1

    def busy(detail: str = "busy") -> JSONResponse:
        return JSONResponse({"detail": detail}, status_code=503, headers={"retry-after": "1"})

    def headers(body: SynthIn, synth_ms: int | None = None) -> dict:
        h = {"x-sample-rate": str(body.sample_rate), "x-model-revision": state.engine.model_revision,
             "x-watermark": state.engine.watermark, "x-simulated": "1" if state.engine.simulated else "0"}
        if synth_ms is not None:
            h["x-synthesis-ms"] = str(synth_ms)
        return h

    @app.post("/v1/synthesize")
    async def synthesize(body: SynthIn, request: Request, authorization: str | None = Header(default=None)):
        auth(authorization)
        check(body)
        eng = await acquire()
        if eng is None:
            return busy()
        if body.request_id in state.cancelled or await request.is_disconnected():
            state.pool.put_nowait(eng)
            raise HTTPException(409, "cancelled")
        task = asyncio.ensure_future(anyio.to_thread.run_sync(run, body, eng))
        task.add_done_callback(lambda _t: state.pool.put_nowait(eng))  # free the instance only when it is idle
        try:
            pcm, synth_ms, seconds = await asyncio.wait_for(asyncio.shield(task), timeout=cfg.gen_timeout)
        except TimeoutError as e:
            raise HTTPException(504, "generation timeout") from e
        if body.request_id in state.cancelled:
            raise HTTPException(409, "cancelled")
        state.timings.append((synth_ms, seconds))
        if body.format == "wav":
            buf = io.BytesIO()
            with wave.open(buf, "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(body.sample_rate)
                w.writeframes(pcm)
            return Response(buf.getvalue(), media_type="audio/wav", headers=headers(body, synth_ms))
        return Response(pcm, media_type="application/octet-stream", headers=headers(body, synth_ms))

    @app.post("/v1/synthesize/stream")
    async def synthesize_stream(body: SynthIn, request: Request, authorization: str | None = Header(default=None)):
        """Raw PCM sent while it is generated. The first chunk is produced before the response starts, so a
        failure is still an HTTP error (the API then falls back) and never half an utterance."""
        auth(authorization)
        check(body)
        if body.format != "pcm_s16le":
            raise HTTPException(422, "streaming is raw PCM only")
        eng = await acquire()
        if eng is None:
            return busy()
        t0 = time.monotonic()
        gen = None
        pending: asyncio.Future | None = None  # a generator step still running in a worker thread
        released = False

        async def release():
            """Close the generator and free the instance, but only once no thread is still inside it."""
            nonlocal released
            if released:
                return
            released = True
            if pending is not None and not pending.done():
                pending.add_done_callback(lambda _f: (gen.close(), state.pool.put_nowait(eng)))
                return
            if gen is not None:
                await anyio.to_thread.run_sync(gen.close)
            state.pool.put_nowait(eng)

        async def step():
            nonlocal pending
            pending = asyncio.ensure_future(anyio.to_thread.run_sync(next, gen, None))
            return await asyncio.wait_for(asyncio.shield(pending), timeout=cfg.gen_timeout)

        try:
            vs = await anyio.to_thread.run_sync(voice_state, body.voice, eng)
            opts = {"first": cfg.first_tokens, "step": cfg.step_tokens, "window": cfg.window_tokens,
                    "prompt_tokens": cfg.prompt_tokens, "cfm_steps": cfg.cfm_steps}
            for k, v in (body.stream or {}).items():
                if k not in opts or not (v is None or (isinstance(v, int) and 1 <= v <= 1000)):
                    raise HTTPException(422, f"invalid stream option {k}")
                opts[k] = v
            gen = eng.stream(vs, body.text, **opts)
            rs = streaming.StreamResampler(eng.sample_rate, body.sample_rate)

            async def pull():
                """Next PCM chunk (resampled), or None at the end."""
                while True:
                    x = await step()
                    if x is None:
                        tail = rs.feed(np.zeros(0, dtype=np.float32), final=True)
                        return engines.to_pcm16(tail) if len(tail) else None
                    y = rs.feed(x)
                    if len(y):
                        return engines.to_pcm16(y)

            if body.request_id in state.cancelled or await request.is_disconnected():
                raise HTTPException(409, "cancelled")
            first = await pull()
        except TimeoutError as e:
            with anyio.CancelScope(shield=True):
                await release()
            raise HTTPException(504, "generation timeout") from e
        except BaseException:
            with anyio.CancelScope(shield=True):
                await release()
            raise
        first_ms = int((time.monotonic() - t0) * 1000)

        async def body_iter():
            n = len(first or b"")
            try:
                if first:
                    yield first
                while True:
                    if body.request_id in state.cancelled or await request.is_disconnected():
                        break
                    chunk = await pull()
                    if chunk is None:
                        break
                    n += len(chunk)
                    yield chunk
            except TimeoutError:
                pass  # stop speaking rather than hang; what was sent is whole audio
            finally:
                with anyio.CancelScope(shield=True):
                    await release()
                seconds = n / 2 / body.sample_rate
                state.timings.append((int((time.monotonic() - t0) * 1000), seconds))
                state.first_audio.append(first_ms)
                state.last_profile = getattr(eng, "last_profile", None)

        h = headers(body) | {"x-first-audio-ms": str(first_ms)}
        return StreamingResponse(body_iter(), media_type="application/octet-stream", headers=h)

    return app


app = create_app() if os.environ.get("TTS_SERVICE_TOKEN") else None

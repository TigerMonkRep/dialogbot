"""Vapi custom-voice endpoint: Vapi sends each assistant utterance here and plays the audio we return.

Contract (Vapi "custom-voice"): POST {"message": {"type": "voice-request", "text": "...", "sampleRate": 24000, ...}}
authenticated with the same secret as the Vapi webhook (Authorization: Bearer … or X-Vapi-Secret). Response:
raw mono 16-bit little-endian PCM at the requested sample rate (application/octet-stream), no WAV header.

- The voice version, settings and pronunciation dictionary were pinned in a VoiceSession when the call's
  assistant was built; the session ID is in the URL, so an update or rollback never changes voice mid-call.
- Chatterbox does not stream natively: we synthesise one speech unit (sentence) at a time and send each as
  soon as it is ready. The first unit is synthesised before the response starts, so an engine failure
  becomes a 503 and Vapi switches to the configured fallback voice instead of playing silence.
- Barge-in: when the caller interrupts, Vapi drops the request and clears its playback buffer; we stop at the
  next unit and cancel the in-flight synthesis. Nothing from an old turn is sent afterwards.
- This endpoint only turns text into sound. It never books, bills or registers anything, so a retried
  voice-request can never repeat a business action.
- No utterance text is logged or stored; the session only accumulates counts and timings.
"""
from __future__ import annotations

import time
import uuid

import anyio
from fastapi import APIRouter, Header, Request
from fastapi.responses import Response, StreamingResponse

from app.core.errors import ApiError, NotFound, ValidationFailed
from app.db import get_session_factory
from app.models import VoiceProfile, VoiceSession, VoiceVersion
from app.modules.telephony import vapi
from app.modules.voices import danish, engine, service

router = APIRouter(prefix="/voice", tags=["voice-telephony"])


def _load(session_id: uuid.UUID, chars: int) -> tuple[VoiceSession, VoiceVersion]:
    from app.config import get_settings

    with get_session_factory()() as db:
        vs = db.get(VoiceSession, session_id)
        if vs is None:
            raise NotFound("Ukendt stemmesession")
        v = db.get(VoiceVersion, vs.version_id) if vs.version_id else None
        p = db.get(VoiceProfile, vs.profile_id) if vs.profile_id else None
        # a suspended/retired voice stops immediately (safety); Vapi then uses the fallback voice
        if v is None or p is None or v.status not in ("active", "approved") or not service.accessible(p, vs.workspace_id):
            _stat(db, vs, "refused")
            db.commit()
            raise ApiError("Stemmen er ikke længere tilgængelig", code="voice_not_active", status_code=503)
        service.count_usage(db, vs.workspace_id, "call", chars, limit_chars=get_settings().voice_call_daily_char_limit)
        db.commit()
        db.expunge(vs)
        db.expunge(v)
        return vs, v


def _stat(db, vs: VoiceSession, key: str, **values) -> None:
    st = dict(vs.stats or {})
    st[key] = st.get(key, 0) + 1
    for k, val in values.items():
        if k.endswith("_ms_list"):
            st[k] = (st.get(k, []) + [val])[-50:]
        else:
            st[k] = st.get(k, 0) + val
    vs.stats = st


def _record(session_id: uuid.UUID, **values) -> None:
    with get_session_factory()() as db:
        vs = db.get(VoiceSession, session_id)
        if vs is not None:
            _stat(db, vs, "requests", **values)
            db.commit()


@router.post("/vapi/{session_id}")
async def vapi_voice(session_id: uuid.UUID, request: Request, authorization: str | None = Header(default=None),
                     x_vapi_secret: str | None = Header(default=None)):
    vapi.verify(authorization, x_vapi_secret)
    t0 = time.monotonic()
    try:
        body = await request.json()
    except ValueError as e:
        raise ValidationFailed("Ugyldig JSON") from e
    msg = body.get("message") if isinstance(body, dict) else None
    if not isinstance(msg, dict) or msg.get("type") != "voice-request":
        raise ValidationFailed("Forventede en voice-request")
    try:
        rate = int(msg.get("sampleRate") or 24000)
    except (TypeError, ValueError) as e:
        raise ValidationFailed("Ugyldig sampleRate") from e
    if rate not in engine.SAMPLE_RATES:
        raise ValidationFailed("Ikke-understøttet sampleRate")
    text = str(msg.get("text") or "")[:4000]
    vs, v = await anyio.to_thread.run_sync(_load, session_id, len(text))
    units = danish.chunks(danish.normalize(text, vs.pronunciations))
    if not units:
        return Response(b"", media_type="application/octet-stream")
    request_ids = [uuid.uuid4().hex for _ in units]
    try:
        first = await anyio.to_thread.run_sync(
            lambda: engine.synthesize(v, units[0], sample_rate=rate, request_id=request_ids[0], session_id=str(vs.id)))
    except ApiError:
        await anyio.to_thread.run_sync(lambda: _record(session_id, errors=1))
        raise
    ttfa_ms = int((time.monotonic() - t0) * 1000)

    async def stream():
        sent, cancelled, synth_ms = 1, 0, first.synth_ms
        try:
            yield first.pcm
            for unit, rid in zip(units[1:], request_ids[1:], strict=True):
                if await request.is_disconnected():
                    cancelled = 1
                    break
                try:
                    s = await anyio.to_thread.run_sync(
                        lambda unit=unit, rid=rid: engine.synthesize(v, unit, sample_rate=rate, request_id=rid,
                                                                    session_id=str(vs.id)))
                except ApiError:
                    break  # stop speaking rather than play a wrong or partial sentence
                if await request.is_disconnected():
                    cancelled = 1
                    break
                synth_ms += s.synth_ms
                sent += 1
                yield s.pcm
        except anyio.get_cancelled_exc_class():
            cancelled = 1
            for rid in request_ids[sent:]:
                engine.cancel(rid)
            raise
        finally:
            with anyio.CancelScope(shield=True):
                await anyio.to_thread.run_sync(lambda: _record(session_id, units=sent, cancelled=cancelled,
                                                                synth_ms=synth_ms, ttfa_ms_list=ttfa_ms))

    return StreamingResponse(stream(), media_type="application/octet-stream",
                             headers={"x-sample-rate": str(rate), "x-first-audio-ms": str(ttfa_ms),
                                      "x-simulated": "1" if first.simulated else "0"})

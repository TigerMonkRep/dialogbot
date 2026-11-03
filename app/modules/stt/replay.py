"""Real-time replay of one recording through one recogniser profile.

The audio is sent at its own speed (100 ms chunks, paced against the wall clock, with the adapter's backpressure), so
timings are about streaming – a batch transcription afterwards would prove nothing about real-time quality. Two modes:

- controlled  The replay closes the turn itself, at the known end of the recording (+200 ms of silence). This isolates
              RECOGNITION from endpointing and is labelled a controlled STT test, not a natural conversation.
- natural     The provider's own endpointing decides, after the audio plus a short silence tail. Differences in
              endpointing show up in `turn_count` / `closed_by`; they are never credited to the recognition model.

The timeline: `at` on every event is seconds on the wall clock since the session opened; audio is paced in real time,
so audio second N is wall second ≈N plus connection setup. All latencies below are measured against the wall time at
which the LAST audio chunk was handed to the socket (`audio_end_s`) – one clock, no cross-server comparisons.
"""
from __future__ import annotations

import asyncio
import time
from collections.abc import Callable

from app.config import get_settings
from app.modules.stt import adapters, metrics
from app.modules.stt.events import SttEvent, TurnAssembler
from app.modules.stt.profiles import Profile

CHUNK_S = 0.1
CONTROL_SILENCE_S = 0.2   # Soniox: finalize only after ~200 ms of silence following speech
NATURAL_TAIL_S = 1.5      # silence after the recording so the provider's endpointing can fire
SETTLE_S = 6.0            # how long to wait for the provider after the last audio
QUIET_S = 1.0             # controlled: no new text for this long after the flush = done
MAX_EVENTS = 400


def _silence(seconds: float, rate: int) -> bytes:
    return bytes(int(seconds * rate) * 2)


async def run_audio(profile: Profile, pcm: bytes, rate: int, *, reference: str, expected: list[dict],
                    vocabulary: list[dict], mode: str = "controlled", chunk_s: float = CHUNK_S,
                    factory: Callable[..., adapters.Adapter] | None = None, realtime: bool = True,
                    settle_s: float = SETTLE_S) -> dict:
    """Run one recording; always returns a result dict (never raises for provider trouble)."""
    cfg = adapters.AdapterConfig(sample_rate=rate, vocabulary=vocabulary, controlled=(mode == "controlled"),
                                 model=profile.model)
    assembler = TurnAssembler()
    closed_at: dict[int, float] = {}

    def sink(ev: SttEvent) -> None:
        turn = assembler.feed(ev)
        if turn is not None:
            closed_at[id(turn)] = ev.at

    make = factory or adapters.make
    ad = make(profile.adapter, cfg)
    ad._sink = sink  # noqa: SLF001 – the replay owns the sink for this run
    base = {"profile": profile.id, "mode": mode, "adapter": profile.adapter, "requested_model": ad.requested_model,
            "turn_owner": ad.turn_owner, "reference": reference, "audio_rate": rate,
            "audio_seconds": round(len(pcm) / 2 / rate, 2),
            "vocabulary": {"offered": len(vocabulary), "used": _vocab_used(profile.adapter, len(vocabulary))}}
    try:
        await ad.open()
    except adapters.MissingAccess as e:
        return {**base, "status": "mangler_adgang", "error": str(e)}
    except Exception as e:  # noqa: BLE001
        return {**base, "status": "fejl", "error": f"forbindelse: {str(e)[:200]}"}

    t_audio_end = 0.0
    flush_at: float | None = None
    try:
        start = time.monotonic()
        step = int(rate * chunk_s) * 2
        n = 0
        for i in range(0, len(pcm), step):
            await ad.send_audio(pcm[i:i + step])
            n += 1
            if realtime:
                await asyncio.sleep(max(0.0, start + n * chunk_s - time.monotonic()))
        t_audio_end = ad.now()
        if mode == "controlled":
            await ad.send_audio(_silence(CONTROL_SILENCE_S, rate))
            if realtime:
                await asyncio.sleep(CONTROL_SILENCE_S)
            flush_at = ad.now()
            await ad.flush()
            await _quiet(ad, settle_s, QUIET_S if realtime else 0.05)
            assembler.close("external", at=ad.now())
        else:
            tail = _silence(NATURAL_TAIL_S, rate)
            for i in range(0, len(tail), step):
                await ad.send_audio(tail[i:i + step])
                if realtime:
                    await asyncio.sleep(chunk_s)
            await ad.finish()
            try:
                await asyncio.wait_for(ad.finished.wait(), timeout=settle_s)
            except TimeoutError:
                pass
            assembler.close("end_of_stream", at=ad.now())
    except Exception as e:  # noqa: BLE001 – a dropped session is a recorded result
        ad.emit("error", f"under afspilning: {str(e)[:200]}")
    finally:
        try:
            await ad.close()
        except Exception:  # noqa: BLE001
            pass

    return {**base, **_summarise(ad, assembler, closed_at, t_audio_end, flush_at, reference, expected,
                                 base["audio_seconds"])}


def _vocab_used(adapter_id: str | None, offered: int) -> int:
    cap = {"soniox": adapters.MAX_SONIOX_TERMS, "elevenlabs-scribe": adapters.MAX_ELEVENLABS_KEYTERMS,
           "speechmatics-rt": 1000, "speechmatics-agent": 1000}.get(adapter_id or "", offered)
    return min(offered, cap)


async def _quiet(ad: adapters.Adapter, settle_s: float, quiet_s: float) -> None:
    """Wait until the provider has been silent for `quiet_s`, ends the session, or `settle_s` runs out."""
    deadline = time.monotonic() + settle_s
    last = len(ad.events)
    quiet_since = time.monotonic()
    while time.monotonic() < deadline and not ad.finished.is_set():
        await asyncio.sleep(0.05)
        if len(ad.events) != last:
            last, quiet_since = len(ad.events), time.monotonic()
        elif time.monotonic() - quiet_since >= quiet_s and any(e.kind in ("final", "turn_ended") for e in ad.events):
            return


def _summarise(ad: adapters.Adapter, asm: TurnAssembler, closed_at: dict, t_end: float, flush_at: float | None,
               reference: str, expected: list[dict], audio_seconds: float) -> dict:
    events = ad.events
    errors = [e for e in events if e.kind == "error"]
    finals = [e for e in events if e.kind == "final" and e.text.strip()]
    partials = [e for e in events if e.kind == "partial" and e.text.strip()]
    transcript = asm.text
    turns = asm.turns
    last_turn = turns[-1] if turns else None
    timing = {
        "audio_end_s": round(t_end, 3),
        "first_partial_s": round(partials[0].at, 3) if partials else None,
        "first_final_s": round(finals[0].at, 3) if finals else None,
        "final_after_audio_s": round(finals[-1].at - t_end, 3) if finals else None,
        "turn_end_after_audio_s": (round(closed_at.get(id(last_turn), last_turn.closed_at or 0) - t_end, 3)
                                   if last_turn is not None and last_turn.closed_at is not None else None),
        "flush_sent_after_audio_s": round(flush_at - t_end, 3) if flush_at is not None else None,
        "note": "alle tider på ét vægur, målt fra sidste lydpakke afleveret til forbindelsen – ikke fra højttaler",
    }
    prices = get_settings().stemmetest_prices_json
    out = {
        "status": "fejl" if errors and not transcript else "ok",
        "error": errors[0].text if errors else None,
        "reported_model": ad.reported_model, "sdk": ad.sdk, "session_id": ad.session_id,
        "transcript_raw": transcript,
        "turns": [{"text": t.text, "segments": t.segments, "late": t.late, "closed_by": t.closed_by} for t in turns],
        "turn_count": len(turns),
        "premature_split": len(turns) > 1,
        "wer": metrics.wer(reference, transcript) if reference or transcript else metrics.wer("", ""),
        "entities": metrics.entities(expected, transcript), "timing": timing,
        "price": metrics.price(ad.id, audio_seconds, prices),
        "events": [e.as_dict() for e in events[:MAX_EVENTS]], "events_total": len(events),
    }
    if not reference and transcript:
        out["wer"] = {"errors": len(metrics.canon(transcript)), "ref_words": 0, "wer": None}  # words invented from silence
    return out

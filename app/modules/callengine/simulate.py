"""The call simulator: a recording plays the caller, the real engine (Soniox, Claude, ElevenLabs) answers, on a
virtual phone line with the same clock as a real call – and nobody's phone rings.

Peter's audio is "played" at real speed on that line: a sentence counts as heard when the caller's clock has passed
its end, a barge-in cuts it exactly there. So turn-taking, interruptions and latency behave as on a call, and the
result is the same two-track recording (left: the caller, right: Peter) plus a turn-by-turn log."""
from __future__ import annotations

import asyncio
import time
import uuid

from app.modules.callengine.audio import FRAME_BYTES, RATE, SILENCE, Recording
from app.modules.callengine.engine import CallEngine


class LineTransport:
    """A phone line on the caller's clock (see audio.Recording)."""

    def __init__(self, rec: Recording):
        self.rec = rec
        self.engine: CallEngine | None = None
        self.marks: list[tuple[int, str]] = []   # (position in Peter's track, mark name)
        self.hung_up = asyncio.Event()

    async def send_audio(self, ulaw: bytes) -> None:
        self.rec.add_peter(ulaw)

    async def mark(self, name: str) -> None:
        self.marks.append((max(len(self.rec.peter), self.rec.now), name))

    async def clear(self) -> None:
        self.rec.cut_peter()
        self.marks = [m for m in self.marks if m[0] <= self.rec.now]

    async def hangup(self) -> None:
        self.hung_up.set()

    def tick(self) -> None:
        """Called after every caller frame: report the marks the line has now played."""
        while self.marks and self.marks[0][0] <= self.rec.now:
            _, name = self.marks.pop(0)
            if self.engine is not None:
                self.engine.played(name)


async def run(engine_factory, caller_ulaw: bytes, *, speed: float = 1.0, tail_s: float = 15.0,
              settle_s: float = 3.0) -> dict:
    """Play `caller_ulaw` as the caller (20 ms frames on the real clock / `speed`), then silence until the conversation
    has settled (`settle_s` with nothing happening) or `tail_s` has passed. Returns the engine and the recording."""
    rec = Recording()
    line = LineTransport(rec)
    engine: CallEngine = engine_factory(line)
    line.engine = engine
    await engine.start()
    frame_s = FRAME_BYTES / RATE / speed
    t0 = time.monotonic()
    i = 0
    total = len(caller_ulaw)
    quiet_since: float | None = None
    tail_frames = int(tail_s * RATE / FRAME_BYTES)
    n = 0
    while not line.hung_up.is_set():
        if i < total:
            frame = caller_ulaw[i:i + FRAME_BYTES]
            frame += SILENCE * (FRAME_BYTES - len(frame))
            i += FRAME_BYTES
        else:
            frame = SILENCE * FRAME_BYTES
            n += 1
            busy = engine.speaking or (engine.response is not None and not engine.response.done())
            if busy:
                quiet_since = None
            else:
                quiet_since = quiet_since or time.monotonic()
                if time.monotonic() - quiet_since > settle_s / speed or n > tail_frames:
                    break
        rec.add_caller(frame)
        await engine.caller_audio(frame)
        line.tick()
        # keep the line on the real clock
        delay = t0 + (rec.now / FRAME_BYTES) * frame_s - time.monotonic()
        if delay > 0:
            await asyncio.sleep(delay)
    await engine.stop(engine.ended_reason or "simulation-ended")
    return {"engine": engine, "recording": rec}


def result(out: dict, sim_id: str | None = None) -> dict:
    engine: CallEngine = out["engine"]
    return {"id": sim_id or uuid.uuid4().hex[:12], "summary": engine.summary(), "transcript": engine.transcript,
            "turns": [{"user": t.user, "reply": t.reply, "latency_ms": t.latency_ms, "interrupted": t.interrupted,
                       "tools": t.tools} for t in engine.turns]}

"""Dialogbot's own call engine: one conversation loop, with ONE owner of every decision.

    caller audio ─▶ STT (Soniox, owns end-of-turn) ─▶ LLM (Claude, streamed) ─▶ TTS (ElevenLabs, per sentence) ─▶ caller

Why not Vapi: with Vapi, our recogniser and Vapi both had a say in when the caller was done, and when they disagreed
Peter never answered (3 Nov 2026: Soniox only marked a turn final at its own endpoint, Vapi waited for a final that
never came, and the greeting kept being restarted). Here the recogniser's end-of-turn IS the turn, and everything the
engine does is in one place, logged per turn, and recorded on two tracks.

The engine is transport- and provider-agnostic (see `Stt`, `Llm`, `Tts`, `Transport`), so the same loop runs on a
Twilio call, in the operator simulator (a recording played in as the caller) and in tests (fakes, no network).

Turn-taking rules (Danish defaults; every number is in `Timing`):
- The caller's turn ends when the recogniser says so (`final`). Then Peter answers – immediately.
- Barge-in: while Peter is speaking, a partial with ≥ `interrupt_words` words that are not backchannels ("ja", "mm",
  "okay" …) stops him at once (Twilio `clear`), and what he managed to say is what goes into the history.
- A turn that is only backchannels while Peter speaks is ignored – he keeps talking.
- A new final while Peter is still preparing an answer (nothing played yet) replaces that answer: the caller's two
  turns are merged and answered together.
- Silence: after `idle_s` without speech Peter asks once if the caller is still there; after another `idle_s` he says
  goodbye and hangs up. `max_call_s` is a hard ceiling.
- Peter hangs up himself through the `end_call` tool, or when he says one of `end_phrases`, after the audio has played.
"""
from __future__ import annotations

import asyncio
import re
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

import structlog

logger = structlog.get_logger(__name__)

END_CALL_TOOL = {"name": "end_call",
                 "description": "Læg på. Brug den, når samtalen er slut og du har sagt farvel, eller når kunden beder "
                                "om at afslutte. Sig farvel FØR du bruger den.",
                 "input_schema": {"type": "object", "properties": {}}}
ACK_WORDS = frozenset({"ja", "jo", "jah", "mm", "mhm", "mmm", "hm", "okay", "ok", "nå", "nåh", "præcis", "netop", "fint",
                       "godt", "javel", "jaja", "yes", "klart", "aha", "ah", "nej", "nårh", "super", "perfekt"})
STILL_THERE = "Er du der stadig?"
GOODBYE_IDLE = "Jeg lægger på nu, men du er altid velkommen til at ringe igen. Hav en god dag."
ANSWERED = "[Opkaldet blev besvaret]"
ABBREVIATIONS = ("kl.", "ca.", "f.eks.", "bl.a.", "evt.", "nr.", "osv.", "dvs.", "inkl.", "ekskl.", "tlf.", "mht.",
                 "pga.", "jf.", "st.", "th.", "tv.", "mv.", "hhv.", "iflg.", "vedr.")


# --------------------------------------------------------------------------- the pieces the engine is built from

class Stt(Protocol):
    async def open(self, on_event: Callable[[str, str], None]) -> None: ...
    async def send(self, ulaw: bytes) -> None: ...
    async def close(self) -> None: ...


class Llm(Protocol):
    def stream(self, system: str, messages: list[dict], tools: list[dict]) -> AsyncIterator[tuple[str, Any]]:
        """Yields ("text", delta) while generating and finally ("done", content_blocks)."""
        ...


class Tts(Protocol):
    def stream(self, text: str, previous_text: str | None) -> AsyncIterator[bytes]:
        """8 kHz µ-law chunks for one sentence."""
        ...


class Transport(Protocol):
    async def send_audio(self, ulaw: bytes) -> None: ...
    async def mark(self, name: str) -> None: ...   # the transport calls engine.played(name) when it has been heard
    async def clear(self) -> None: ...             # drop everything queued for playback (barge-in)
    async def hangup(self) -> None: ...


ToolRunner = Callable[[str, dict], Awaitable[str]]


@dataclass
class Timing:
    interrupt_words: int = 2
    idle_s: float = 12.0
    max_call_s: float = 900.0
    max_tool_rounds: int = 4


@dataclass
class CallConfig:
    greeting: str
    system: str
    tools: list[dict] = field(default_factory=list)      # Anthropic tool definitions (end_call is always added)
    end_phrases: tuple[str, ...] = ("hav en rigtig god dag", "hav en god dag")
    pronounce: Callable[[str], str] = staticmethod(lambda s: s)  # the voice's pronunciation dictionary
    timing: Timing = field(default_factory=Timing)


# --------------------------------------------------------------------------- text helpers

def words(text: str) -> list[str]:
    return re.findall(r"[\wæøåÆØÅ]+", (text or "").lower())


def only_backchannel(text: str) -> bool:
    w = words(text)
    return bool(w) and all(x in ACK_WORDS for x in w)


def is_interruption(text: str, min_words: int) -> bool:
    return len([x for x in words(text) if x not in ACK_WORDS]) >= min_words


class SentenceSplitter:
    """Cuts streamed text into speakable pieces: at . ! ? : (not after a Danish abbreviation or inside a number such as
    14.30) and, for long stretches, at a comma – so the first audio starts after the first clause, not the whole answer."""

    def __init__(self, comma_after: int = 60):
        self.buf = ""
        self.comma_after = comma_after

    def feed(self, delta: str) -> list[str]:
        self.buf += delta
        out: list[str] = []
        while True:
            cut = self._cut()
            if cut is None:
                return out
            piece, self.buf = self.buf[:cut].strip(), self.buf[cut:]
            if piece:
                out.append(piece)

    def _cut(self) -> int | None:
        for m in re.finditer(r"[.!?:…]+[\"”)]?\s", self.buf):
            end = m.end()
            before = self.buf[: m.start() + 1]
            tail = before.split()[-1].lower() if before.split() else ""
            if tail in ABBREVIATIONS or re.search(r"\d[.:]$", before) and re.match(r"\d", self.buf[end:end + 1] or ""):
                continue
            return end
        if len(self.buf) >= self.comma_after:
            i = self.buf.rfind(", ")
            if i >= 20:
                return i + 2
        return None

    def rest(self) -> str:
        piece, self.buf = self.buf.strip(), ""
        return piece


# --------------------------------------------------------------------------- the engine

@dataclass
class Turn:
    user: str
    reply: str = ""
    latency_ms: int | None = None  # caller's turn ended → first audio of the answer sent
    interrupted: bool = False
    tools: list[str] = field(default_factory=list)


class CallEngine:
    def __init__(self, cfg: CallConfig, stt: Stt, llm: Llm, tts: Tts, transport: Transport,
                 run_tool: ToolRunner | None = None, clock: Callable[[], float] = time.monotonic):
        self.cfg, self.stt, self.llm, self.tts, self.transport = cfg, stt, llm, tts, transport
        self.run_tool = run_tool
        self.clock = clock
        self.started = clock()
        # The greeting is spoken before anything else, so the history opens with it (the API wants a user turn first).
        self.history: list[dict] = [{"role": "user", "content": ANSWERED}, {"role": "assistant", "content": cfg.greeting}]
        self.transcript: list[dict] = []          # {"role": "user"|"bot", "message": str, "t": seconds}
        self.turns: list[Turn] = []
        self.pending_marks: dict[str, str] = {}    # mark → sentence, queued but not yet heard
        self.heard: list[str] = []                 # sentences of the current answer the caller has heard
        self.response: asyncio.Task | None = None
        self.watchdog: asyncio.Task | None = None
        self.last_activity = clock()
        self.idle_asked = False
        self.ended = asyncio.Event()
        self.ended_reason: str | None = None
        self._mark_seq = 0
        self._played = asyncio.Event()
        self._played.set()
        self.tools = [*cfg.tools, END_CALL_TOOL]
        self._tts_slots = asyncio.Semaphore(3)  # sentences synthesised ahead at most at once

    # ---- lifecycle ---------------------------------------------------------
    async def start(self) -> None:
        await self.stt.open(self.on_stt)
        self.response = asyncio.create_task(self._speak_fixed(self.cfg.greeting, as_history=True))
        self.watchdog = asyncio.create_task(self._watch())

    async def stop(self, reason: str = "customer-ended-call") -> None:
        if self.ended_reason is None:
            self.ended_reason = reason
        for t in (self.response, self.watchdog):
            if t is not None and not t.done():
                t.cancel()
        await asyncio.gather(*(t for t in (self.response, self.watchdog) if t is not None), return_exceptions=True)
        try:
            await self.stt.close()
        except Exception as e:  # noqa: BLE001 – the call is over either way
            logger.info("engine.stt_close", detail=str(e)[:200])
        self.ended.set()

    def elapsed(self) -> float:
        return round(self.clock() - self.started, 2)

    # ---- input -------------------------------------------------------------
    async def caller_audio(self, ulaw: bytes) -> None:
        await self.stt.send(ulaw)

    def played(self, name: str) -> None:
        """The transport heard a mark: that sentence has been played to the caller."""
        sentence = self.pending_marks.pop(name, None)
        if sentence is not None:
            self.heard.append(sentence)
        if not self.pending_marks:
            self.last_activity = self.clock()
            self._played.set()

    @property
    def speaking(self) -> bool:
        return bool(self.pending_marks)

    def on_stt(self, kind: str, text: str) -> None:
        asyncio.get_running_loop().create_task(self._on_stt(kind, text))

    async def _on_stt(self, kind: str, text: str) -> None:
        if self.ended.is_set():
            return
        if kind == "error":
            logger.warning("engine.stt_error", detail=text[:300])
            return
        text = (text or "").strip()
        if not text:
            return
        self.last_activity = self.clock()
        self.idle_asked = False
        if kind == "partial":
            if self.speaking and is_interruption(text, self.cfg.timing.interrupt_words):
                await self.interrupt("barge-in")
            return
        if kind != "final":
            return
        if self.speaking and only_backchannel(text):
            logger.info("engine.backchannel", text=text[:80], t=self.elapsed())
            return
        busy = self.response is not None and not self.response.done()
        if busy:
            await self.interrupt("new-turn")
        self.transcript.append({"role": "user", "message": text, "t": self.elapsed()})
        self._add_user(text)
        turn = Turn(user=text)
        self.turns.append(turn)
        self.response = asyncio.create_task(self._respond(turn, self.clock()))

    # ---- output ------------------------------------------------------------
    async def interrupt(self, why: str) -> None:
        task = self.response
        if task is not None and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        if self.pending_marks:
            await self.transport.clear()
            self.pending_marks.clear()
            self._played.set()
        if self.turns:
            self.turns[-1].interrupted = self.turns[-1].interrupted or why == "barge-in"
        logger.info("engine.interrupt", why=why, t=self.elapsed())

    def _add_user(self, text: str) -> None:
        """A caller turn. Two caller turns in a row (the answer to the first was cut before anything was heard) are
        merged into one, so the model answers both."""
        last = self.history[-1]
        if last["role"] == "user" and isinstance(last["content"], str) and last["content"] != ANSWERED:
            last["content"] = f"{last['content']}\n{text}"
        else:
            self.history.append({"role": "user", "content": text})

    async def _queue_sentence(self, sentence: str, audio: AsyncIterator[bytes], first: list,
                              on_first: Callable[[], None] | None = None) -> None:
        async for chunk in audio:
            if not chunk:
                continue
            if not first[0]:
                first[0] = True
                if on_first is not None:
                    on_first()
            await self.transport.send_audio(chunk)
        self._mark_seq += 1
        name = f"s{self._mark_seq}"
        self.pending_marks[name] = sentence
        self._played.clear()
        await self.transport.mark(name)

    async def _speak_fixed(self, text: str, as_history: bool = False) -> None:
        """A line that is not generated (greeting, idle prompt): straight to the voice."""
        self.heard = []
        first = [False]
        try:
            await self._queue_sentence(text, self.tts.stream(self.cfg.pronounce(text), None), first)
            self.transcript.append({"role": "bot", "message": text, "t": self.elapsed()})
            if not as_history and self.history[-1]["role"] == "assistant" and isinstance(self.history[-1]["content"], str):
                self.history[-1]["content"] = f"{self.history[-1]['content']} {text}"
            elif not as_history:
                self.history.append({"role": "assistant", "content": text})
            await self._played.wait()
        except asyncio.CancelledError:
            raise

    async def _respond(self, turn: Turn, turn_end: float) -> None:
        """Answer the caller: stream the model, speak sentence by sentence (TTS of the next sentence overlaps the
        playback of this one), run tools, and keep the history true to what the caller actually heard."""
        local: list[dict] = []          # this answer's messages (assistant/tool rounds) until committed
        said: list[str] = []            # sentences queued to the voice, in order
        tool_notes: list[str] = []
        hang_up = False
        first = [False]
        self.heard = []
        queue: asyncio.Queue = asyncio.Queue()

        def first_audio() -> None:
            turn.latency_ms = int((self.clock() - turn_end) * 1000)

        async def player() -> None:
            while True:
                item = await queue.get()
                if item is None:
                    return
                sentence, audio = item
                await self._queue_sentence(sentence, audio, first, first_audio)

        def say(sentence: str) -> None:
            if not sentence:
                return
            prev = said[-1] if said else None
            said.append(sentence)
            queue.put_nowait((sentence, self._prefetch(self.cfg.pronounce(sentence), prev)))

        play = asyncio.create_task(player())
        try:
            for _round in range(self.cfg.timing.max_tool_rounds):
                splitter = SentenceSplitter()
                content: list[dict] = []
                async for kind, value in self.llm.stream(self.cfg.system, self.history + local, self.tools):
                    if kind == "text":
                        for s in splitter.feed(value):
                            say(s)
                    elif kind == "done":
                        content = value or []
                say(splitter.rest())
                if content:
                    local.append({"role": "assistant", "content": content})
                uses = [b for b in content if b.get("type") == "tool_use"]
                if not uses:
                    break
                results = []
                for u in uses:
                    turn.tools.append(u["name"])
                    if u["name"] == "end_call":
                        hang_up = True
                        out = "Opkaldet afsluttes, når du har sagt farvel."
                    elif self.run_tool is None:
                        out = "Handlingen er ikke tilgængelig. Tilbyd i stedet, at en medarbejder følger op."
                    else:
                        try:
                            out = await self.run_tool(u["name"], u.get("input") or {})
                        except Exception as e:  # noqa: BLE001 – a failed action is a result the model must handle
                            logger.warning("engine.tool_failed", tool=u["name"], detail=str(e)[:200])
                            out = "Handlingen fejlede. Sig det ærligt og tilbyd, at en medarbejder følger op."
                    tool_notes.append(f"{u['name']}: {out[:200]}")
                    results.append({"type": "tool_result", "tool_use_id": u["id"], "content": out})
                local.append({"role": "user", "content": results})
                if hang_up:
                    break
            queue.put_nowait(None)
            await play
            await self._played.wait()
            self._commit(local, said, interrupted=False)
            turn.reply = " ".join(said)
            self.transcript.append({"role": "bot", "message": turn.reply, "t": self.elapsed()})
            logger.info("engine.turn", user=turn.user[:300], reply=turn.reply[:300], latency_ms=turn.latency_ms,
                        tools=turn.tools, t=self.elapsed())
            text = " ".join(said).lower()
            if hang_up or any(p in text for p in self.cfg.end_phrases):
                await self.end("assistant-ended-call")
        except asyncio.CancelledError:
            play.cancel()
            await asyncio.gather(play, return_exceptions=True)
            heard = list(self.heard)
            # the sentence that was playing when the caller cut in was partly heard: keep it, marked as cut off
            if len(heard) < len(said) and first[0]:
                heard.append(said[len(heard)] + " —")
            self._commit(local, heard, interrupted=True, tool_notes=tool_notes)
            turn.reply = " ".join(heard)
            turn.interrupted = True
            if heard:
                self.transcript.append({"role": "bot", "message": turn.reply, "t": self.elapsed()})
            logger.info("engine.turn", user=turn.user[:300], reply=turn.reply[:300], latency_ms=turn.latency_ms,
                        tools=turn.tools, interrupted=True, t=self.elapsed())
            raise

    def _prefetch(self, text: str, previous: str | None) -> AsyncIterator[bytes]:
        """Start synthesising now; the player reads it when the sentence before it is queued."""
        q: asyncio.Queue = asyncio.Queue()

        async def fill() -> None:
            try:
                async with self._tts_slots:
                    async for chunk in self.tts.stream(text, previous):
                        q.put_nowait(chunk)
            except Exception as e:  # noqa: BLE001 – a failed sentence is skipped, the call goes on
                logger.warning("engine.tts_failed", detail=str(e)[:200])
            finally:
                q.put_nowait(None)

        task = asyncio.create_task(fill())

        async def read() -> AsyncIterator[bytes]:
            try:
                while (chunk := await q.get()) is not None:
                    yield chunk
            finally:
                if not task.done():
                    task.cancel()
        return read()

    def _commit(self, local: list[dict], heard: list[str], interrupted: bool,
                tool_notes: list[str] | None = None) -> None:
        if not interrupted:
            if local:
                self.history.extend(local)
                if self.history[-1]["role"] == "user":  # the round ended on tool results (end_call): close it
                    self.history.append({"role": "assistant", "content": " ".join(heard) or "Farvel."})
            elif heard:
                self.history.append({"role": "assistant", "content": " ".join(heard)})
            return
        # Interrupted: tool blocks are dropped (they must be paired), but their effects are kept as notes, and the
        # assistant turn holds only what the caller heard.
        text = " ".join(heard)
        if tool_notes:
            text = (text + "\n" if text else "") + "\n".join(f"(Udført: {n})" for n in tool_notes)
        if text:
            self.history.append({"role": "assistant", "content": text})

    async def end(self, reason: str) -> None:
        await self._played.wait()
        self.ended_reason = self.ended_reason or reason
        await self.transport.hangup()

    async def _watch(self) -> None:
        t = self.cfg.timing
        while not self.ended.is_set():
            await asyncio.sleep(0.25)
            now = self.clock()
            if now - self.started > t.max_call_s:
                self.ended_reason = "exceeded-max-duration"
                await self.transport.hangup()
                return
            busy = self.speaking or (self.response is not None and not self.response.done())
            if busy or now - self.last_activity < t.idle_s:
                continue
            if not self.idle_asked:
                self.idle_asked = True
                self.response = asyncio.create_task(self._speak_fixed(STILL_THERE))
            else:
                self.response = asyncio.create_task(self._speak_fixed(GOODBYE_IDLE))
                await asyncio.gather(self.response, return_exceptions=True)
                await self.end("silence-timed-out")
                return
            self.last_activity = now

    def summary(self) -> dict:
        lat = [x.latency_ms for x in self.turns if x.latency_ms is not None]
        return {"turns": len(self.turns), "interrupted": sum(x.interrupted for x in self.turns),
                "latency_ms_median": sorted(lat)[len(lat) // 2] if lat else None,
                "latency_ms_max": max(lat) if lat else None, "ended_reason": self.ended_reason,
                "duration_s": self.elapsed()}

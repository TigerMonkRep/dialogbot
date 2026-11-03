"""Dialogbot's own call engine (app/modules/callengine): turn-taking, barge-in, tools, silence, the Twilio stream and
the stored report – with fake ears, brain and voice, on the simulator's virtual phone line (no network)."""
from __future__ import annotations

import asyncio
import base64
import json
import time

import pytest
from starlette.websockets import WebSocketDisconnect

from app.config import get_settings
from app.modules.callengine import audio, call, simulate
from app.modules.callengine.engine import CallConfig, CallEngine, SentenceSplitter, Timing, only_backchannel

from .test_telephony import SECRET, _setup

MS = audio.RATE // 1000  # µ-law bytes per millisecond


class ScriptedStt:
    """Fires recogniser events when the caller's audio reaches a given point (ms) – i.e. on the line's clock."""

    def __init__(self, script: list[tuple[int, str, str]]):
        self.script = sorted(script)
        self.pos = 0
        self.sink = None
        self.closed = False

    async def open(self, on_event):
        self.sink = on_event

    async def send(self, ulaw: bytes):
        self.pos += len(ulaw)
        while self.script and self.script[0][0] * MS <= self.pos:
            _, kind, text = self.script.pop(0)
            self.sink(kind, text)

    async def close(self):
        self.closed = True


class ScriptedLlm:
    """One scripted answer per call to stream(): a string, or a list of content blocks (tool use)."""

    def __init__(self, answers):
        self.answers = list(answers)
        self.seen: list[list[dict]] = []

    async def stream(self, system, messages, tools):
        self.seen.append([dict(m) for m in messages])
        a = self.answers.pop(0) if self.answers else "Ja."
        blocks = a if isinstance(a, list) else [{"type": "text", "text": a}]
        for b in blocks:
            if b["type"] == "text":
                for w in b["text"].split(" "):
                    await asyncio.sleep(0.001)
                    yield "text", w + " "
        yield "done", blocks


class FakeTts:
    """100 ms of audio per 10 characters, in 100 ms chunks."""

    def __init__(self):
        self.said: list[str] = []

    async def stream(self, text, previous_text):
        self.said.append(text)
        for _ in range(max(1, len(text) // 10)):
            await asyncio.sleep(0)
            yield b"\x00" * (100 * MS)


def _engine(stt, llm, tts=None, *, tools=None, run_tool=None, timing=None):
    cfg = CallConfig(greeting="Goddag, det er Peter.", system="Du er Peter.", tools=tools or [],
                     timing=timing or Timing(idle_s=30))

    def factory(line):
        return CallEngine(cfg, stt, llm, tts or FakeTts(), line, run_tool=run_tool)
    return factory


def _run(factory, seconds: float, **kw):
    return asyncio.run(simulate.run(factory, audio.SILENCE * int(seconds * audio.RATE), speed=50, **kw))


# --------------------------------------------------------------------------- text and audio helpers

def test_sentences_are_cut_for_speech_but_not_after_danish_abbreviations_or_inside_times():
    s = SentenceSplitter()
    out = s.feed("Vi har åbent kl. 14.30 i dag. Kom bare ")
    out += s.feed("forbi! Ring evt. igen")
    assert out == ["Vi har åbent kl. 14.30 i dag.", "Kom bare forbi!"]
    assert s.rest() == "Ring evt. igen"


def test_backchannels_are_recognised():
    assert only_backchannel("Ja ja.") and only_backchannel("mm, okay")
    assert not only_backchannel("Ja, men hvad koster det?")


def test_ulaw_roundtrip_and_two_track_recording():
    pcm = audio.pcm16_to_ulaw(b"\x00\x10\x00\xf0" * 10)
    back = audio.ulaw_to_pcm16(pcm)
    assert len(back) == 40
    rec = audio.Recording()
    rec.add_caller(b"\xff" * 800)
    rec.add_peter(b"\x00" * 800)       # queued ahead of the line
    rec.add_caller(b"\xff" * 400)
    rec.cut_peter()                    # barge-in: only what was played stays
    assert rec.now == 1200 and len(rec.peter) == 1200
    wav = rec.wav()
    assert wav[:4] == b"RIFF" and wav[22] == 2  # stereo


def test_tokens_are_signed_and_expire(monkeypatch):
    monkeypatch.setenv("VAPI_SERVER_SECRET", SECRET)
    get_settings.cache_clear()
    import uuid
    n = uuid.uuid4()
    t = call.sign(n, "test", 60)
    assert call.verify(t)["n"] == str(n)
    raw, sig = t.rsplit(".", 1)
    assert call.verify(raw + "." + ("0" * len(sig))) is None
    assert call.verify(call.sign(n, "test", -1)) is None
    assert call.verify(call.sign(n, "inbound"))["e"] == 0
    assert "<Parameter name=\"t\"" in call.twiml(t, "+4512345678") and "<Hangup/>" in call.twiml(t)
    get_settings.cache_clear()


# --------------------------------------------------------------------------- the conversation loop

def test_greeting_then_the_callers_turn_is_answered_at_once():
    stt = ScriptedStt([(2500, "partial", "Hvad koster"), (3000, "final", "Hvad koster en klipning?")])
    llm = ScriptedLlm(["En klipning koster 350 kroner. Vil du booke en tid?"])
    out = _run(_engine(stt, llm), 8)
    e = out["engine"]
    roles = [m["role"] for m in e.transcript]
    assert roles == ["bot", "user", "bot"]
    assert e.transcript[0]["message"] == "Goddag, det er Peter."
    t = e.turns[0]
    assert t.reply == "En klipning koster 350 kroner. Vil du booke en tid?" and not t.interrupted
    assert t.latency_ms is not None and t.latency_ms < 500
    # the model saw the greeting before the caller's question
    assert llm.seen[0][1] == {"role": "assistant", "content": "Goddag, det er Peter."}
    assert llm.seen[0][-1] == {"role": "user", "content": "Hvad koster en klipning?"}


def test_barge_in_stops_peter_and_the_history_holds_only_what_was_heard():
    long = ("Vi tilbyder klipning, farvning og permanent. " * 3).strip() + " Og vi har også en masse andre ting."
    stt = ScriptedStt([(2000, "final", "Hvad laver I?"),
                       (3500, "partial", "Vent lige et øjeblik"),
                       (4200, "final", "Vent lige et øjeblik, hvad med herreklip?")])
    llm = ScriptedLlm([long, "Herreklip koster 250 kroner."])
    out = _run(_engine(stt, llm), 9)
    e = out["engine"]
    first, second = e.turns
    assert first.interrupted and first.reply != long and first.reply.endswith("—")
    assert second.reply == "Herreklip koster 250 kroner."
    history = llm.seen[1]
    assert history[-2]["role"] == "assistant" and history[-2]["content"] == first.reply
    assert history[-1]["content"] == "Vent lige et øjeblik, hvad med herreklip?"
    # Peter's track was cut where the caller cut in (no audio of the long answer after 3.5 s … until the next answer)
    assert len(out["recording"].peter) < (9 * audio.RATE)


def test_backchannels_while_peter_speaks_do_not_stop_him():
    stt = ScriptedStt([(2000, "final", "Hvad har I af åbningstider?"),
                       (2600, "partial", "ja"), (2700, "final", "Ja.")])
    llm = ScriptedLlm(["Vi har åbent mandag til fredag fra otte til sytten, og lørdag fra ni til tretten."])
    e = _run(_engine(stt, llm), 8)["engine"]
    assert len(e.turns) == 1 and not e.turns[0].interrupted


def test_two_turns_before_peter_speaks_are_answered_together():
    class SlowLlm(ScriptedLlm):
        async def stream(self, system, messages, tools):
            await asyncio.sleep(0.05)  # thinking
            async for x in super().stream(system, messages, tools):
                yield x
    stt = ScriptedStt([(2000, "final", "Jeg hedder Anna."), (2010, "final", "Og jeg vil gerne booke.")])
    llm = SlowLlm(["Hej Anna, hvornår passer det dig?", "Hej Anna, hvornår passer det dig?"])
    _run(_engine(stt, llm), 6)
    assert llm.seen[-1][-1] == {"role": "user", "content": "Jeg hedder Anna.\nOg jeg vil gerne booke."}


def test_tools_run_and_end_call_hangs_up_after_the_goodbye():
    ran = []

    async def run_tool(name, args):
        ran.append((name, args))
        return "Booket tirsdag kl. 10."
    stt = ScriptedStt([(2000, "final", "Book mig tirsdag klokken ti.")])
    llm = ScriptedLlm([
        [{"type": "text", "text": "Et øjeblik."}, {"type": "tool_use", "id": "t1", "name": "book", "input": {"d": "tir"}}],
        [{"type": "text", "text": "Du er booket tirsdag klokken ti. Hav en god dag."},
         {"type": "tool_use", "id": "t2", "name": "end_call", "input": {}}],
    ])
    out = _run(_engine(stt, llm, tools=[{"name": "book", "description": "x", "input_schema": {"type": "object"}}],
                       run_tool=run_tool), 20)
    e = out["engine"]
    assert ran == [("book", {"d": "tir"})]
    assert e.ended_reason == "assistant-ended-call"
    assert e.turns[0].tools == ["book", "end_call"]
    # tool use and result stay paired in the history the model sees
    assert llm.seen[1][-1]["content"][0]["type"] == "tool_result"


def test_silence_gets_one_question_then_a_goodbye_and_a_hangup():
    tts = FakeTts()
    e = _run(_engine(ScriptedStt([]), ScriptedLlm([]), tts, timing=Timing(idle_s=0.1)), 30, tail_s=30)["engine"]
    assert e.ended_reason == "silence-timed-out"
    assert tts.said[1:] == ["Er du der stadig?", tts.said[2]] and "Hav en god dag" in tts.said[2]


# --------------------------------------------------------------------------- the Twilio stream, end to end

@pytest.fixture
def engine_env(monkeypatch, tmp_path):
    monkeypatch.setenv("VAPI_SERVER_SECRET", SECRET)
    monkeypatch.setenv("VOICE_STORAGE_DIR", str(tmp_path))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_a_twilio_call_runs_on_the_engine_and_is_stored_like_any_call(client, api, two_workspaces, engine_env,
                                                                     monkeypatch):
    from sqlalchemy import select

    from app.db import get_session_factory
    from app.models import Call, ConversationMessage, PhoneNumber

    _setup(api, two_workspaces)
    db = get_session_factory()()
    number = db.scalar(select(PhoneNumber).where(PhoneNumber.provider_number_id == "pn_123"))
    db.close()
    llm = ScriptedLlm(["Afslibning koster 145 kroner pr. kvadratmeter."])
    monkeypatch.setattr(call, "make_providers", lambda setup: (
        ScriptedStt([(1000, "final", "Hvad koster afslibning?")]), llm, FakeTts()))
    sid = "CA" + "1" * 32
    with client.websocket_connect("/api/v1/webhooks/engine/stream") as ws:
        ws.send_text(json.dumps({"event": "connected"}))
        ws.send_text(json.dumps({"event": "start", "streamSid": "MZ1", "start": {
            "streamSid": "MZ1", "callSid": sid,
            "customParameters": {"t": call.sign(number.id, "inbound"), "from": "+4520304050"}}}))
        sent: list[dict] = []
        frame = base64.b64encode(audio.SILENCE * 160).decode()
        for _ in range(150):  # 3 s of caller audio
            ws.send_text(json.dumps({"event": "media", "media": {"track": "inbound", "payload": frame}}))
        # Peter's greeting and answer come back as media + marks; acknowledge the marks like Twilio does
        deadline = time.time() + 5
        while time.time() < deadline:
            msg = json.loads(ws.receive_text())
            sent.append(msg)
            if msg["event"] == "mark":
                ws.send_text(json.dumps({"event": "mark", "mark": msg["mark"]}))
                if sum(m["event"] == "mark" for m in sent) == 2:
                    break
        time.sleep(0.3)  # let the engine finish the turn before the caller hangs up
        ws.send_text(json.dumps({"event": "stop"}))
    assert {m["event"] for m in sent} >= {"media", "mark"} and all(m["streamSid"] == "MZ1" for m in sent)
    assert llm.seen and llm.seen[0][-1]["content"] == "Hvad koster afslibning?"
    db = get_session_factory()()
    try:
        deadline = time.time() + 5
        c = None
        while time.time() < deadline and c is None:
            c = db.scalar(select(Call).where(Call.provider_call_id == sid))
            if c is None:
                time.sleep(0.1)
                db.rollback()
        assert c is not None and c.provider == "dialogbot" and c.from_number == "+4520304050"
        texts = [m.text for m in db.scalars(select(ConversationMessage).where(
            ConversationMessage.conversation_id == c.conversation_id).order_by(ConversationMessage.created_at))]
    finally:
        db.close()
    assert texts[1:] == ["Hvad koster afslibning?", "Afslibning koster 145 kroner pr. kvadratmeter."]
    from app.modules.voices import storage
    assert storage.get(call.recording_key(sid))[:4] == b"RIFF"


def test_a_stream_without_a_valid_token_is_closed(client, engine_env):
    with client.websocket_connect("/api/v1/webhooks/engine/stream") as ws:
        ws.send_text(json.dumps({"event": "start", "start": {"streamSid": "MZ1", "callSid": "CA1",
                                                             "customParameters": {"t": "nope.nope"}}}))
        with pytest.raises(WebSocketDisconnect):
            ws.receive_text()

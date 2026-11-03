"""Running the engine on a real phone call: Twilio Media Streams in and out, the call's setup from the database,
and the report afterwards (stored exactly like a Vapi call, so inbox, leads and reports need no changes).

Flow: Twilio (inbound number or our outbound test call) → TwiML `<Connect><Stream>` → WebSocket
`/webhooks/engine/stream` → CallEngine. Closing the socket ends `<Connect>`, and the TwiML's `<Hangup/>` ends the call.

Access: every stream carries a signed token (HMAC-SHA256 with VAPI_SERVER_SECRET) naming the number and the mode.
Twilio strips query strings from stream URLs, so the token rides as a `<Parameter>`; for inbound TwiML it is in the
webhook URL we set on the number."""
from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import time
import uuid
from datetime import UTC, datetime
from typing import Any
from xml.sax.saxutils import quoteattr

import structlog
from fastapi import WebSocket

from app.config import get_settings
from app.modules.callengine.audio import Recording
from app.modules.callengine.engine import CallConfig, CallEngine

logger = structlog.get_logger(__name__)

PROVIDER = "dialogbot"
ENGINE_NOTE = ("\n\nOpkaldet: Når samtalen er slut, siger du farvel og bruger værktøjet end_call. Svar altid kort, med "
               "én eller to sætninger ad gangen, som i en rigtig telefonsamtale. Skriv aldrig lister, overskrifter, "
               "emojis eller markdown – alt du skriver, bliver læst højt.")
TEST_TTL_S = 600


# --------------------------------------------------------------------------- tokens

def _secret() -> bytes:
    s = (get_settings().vapi_server_secret or "").strip()
    if not s:
        raise RuntimeError("VAPI_SERVER_SECRET mangler")
    return s.encode()


def sign(number_id: uuid.UUID, mode: str, ttl_s: int | None = None) -> str:
    """mode: inbound (no expiry – it lives in the number's webhook URL) | test (expires)."""
    body = {"n": str(number_id), "m": mode, "e": int(time.time()) + ttl_s if ttl_s else 0}
    raw = base64.urlsafe_b64encode(json.dumps(body, separators=(",", ":")).encode()).decode().rstrip("=")
    sig = hmac.new(_secret(), raw.encode(), hashlib.sha256).hexdigest()[:32]
    return f"{raw}.{sig}"


def verify(token: str | None) -> dict | None:
    if not token or "." not in token:
        return None
    raw, sig = token.rsplit(".", 1)
    try:
        good = hmac.new(_secret(), raw.encode(), hashlib.sha256).hexdigest()[:32]
    except RuntimeError:
        return None
    if not hmac.compare_digest(sig, good):
        return None
    try:
        body = json.loads(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)))
    except ValueError:
        return None
    if body.get("e") and body["e"] < time.time():
        return None
    return body


def stream_url() -> str:
    base = get_settings().public_base_url.rstrip("/").replace("https://", "wss://", 1).replace("http://", "ws://", 1)
    return f"{base}/api/v1/webhooks/engine/stream"


def twiml(token: str, caller: str | None = None) -> str:
    params = f"<Parameter name=\"t\" value={quoteattr(token)}/>"
    if caller:
        params += f"<Parameter name=\"from\" value={quoteattr(caller)}/>"
    return (f"<?xml version=\"1.0\" encoding=\"UTF-8\"?><Response><Connect><Stream url={quoteattr(stream_url())}>"
            f"{params}</Stream></Connect><Hangup/></Response>")


# --------------------------------------------------------------------------- setup from the database

def build(number_id: uuid.UUID, caller: str | None) -> dict:
    """Everything a call needs, read once at the start (sync – run in a thread)."""
    from app.db import get_session_factory
    from app.models import PhoneNumber, Workspace
    from app.modules.integrations import actions
    from app.modules.telephony import linden, vapi
    from app.modules.voices import standard

    db = get_session_factory()()
    try:
        number = db.get(PhoneNumber, number_id)
        if number is None or not number.active:
            raise LookupError("Nummeret findes ikke eller er ikke aktivt")
        ws = db.get(Workspace, number.workspace_id)
        assistant = vapi.assistant_config(db, number, caller)["assistant"]
        voice = standard.provider_voice(db, ws.id, number)
        tools = actions.to_anthropic(actions.tools_for(db, ws, "phone"))
        vocabulary = linden.additional_vocab(db, ws, [])
        db.commit()
        return {"workspace_id": ws.id, "number_id": number.id, "e164": number.e164,
                "greeting": assistant["firstMessage"], "system": assistant["model"]["messages"][0]["content"] + ENGINE_NOTE,
                "tools": tools, "voice": voice, "vocabulary": vocabulary,
                "end_phrases": tuple(assistant.get("endCallPhrases") or ())}
    finally:
        db.close()


def pronouncer(voice: dict):
    from app.modules.telephony import vapi

    def pronounce(text: str) -> str:
        return vapi.spoken_first_message({"firstMessage": text, "voice": voice})["firstMessage"]
    return pronounce


def call_config(setup: dict) -> CallConfig:
    cfg = CallConfig(greeting=setup["greeting"], system=setup["system"], tools=setup["tools"],
                     pronounce=pronouncer(setup["voice"]))
    if setup.get("end_phrases"):
        cfg.end_phrases = setup["end_phrases"]
    return cfg


def tool_runner(setup: dict, caller: str | None, call_id: str):
    async def run(name: str, args: dict) -> str:
        return await asyncio.to_thread(_run_tool, setup, caller, call_id, name, args)
    return run


def _run_tool(setup: dict, caller: str | None, call_id: str, name: str, args: dict) -> str:
    from app.db import get_session_factory
    from app.models import Workspace
    from app.modules.integrations import actions
    from app.modules.integrations.connectors.base import RunContext
    from app.modules.reports.service import tz_of

    db = get_session_factory()()
    try:
        ws = db.get(Workspace, setup["workspace_id"])
        ctx = RunContext(workspace_id=ws.id, channel="phone", caller_phone=caller, provider_call_id=call_id,
                         tz=tz_of(db, ws.id))
        out, _run = actions.execute(db, ws, name, args, ctx)
        db.commit()
        return out
    finally:
        db.close()


def make_providers(setup: dict):
    from app.modules.callengine import providers

    voice = setup["voice"] or {}
    stt = providers.SonioxStt(setup["vocabulary"], providers.soniox_endpoint())
    llm = providers.ClaudeLlm()
    tts = providers.ElevenTts(voice.get("voiceId"), voice.get("model") or "eleven_flash_v2_5")
    return stt, llm, tts


# --------------------------------------------------------------------------- the report

SUMMARY_PROMPT = ("Du er en erfaren referent. Du får udskriften af et telefonopkald til en dansk virksomhed. Opsummér "
                  "opkaldet på dansk i 2-3 sætninger: hvem ringede, hvad de ville, og hvad der blev aftalt. Returnér kun "
                  "resuméet.")


def summarise(transcript: list[dict]) -> str:
    lines = "\n".join(("Kontakt" if m["role"] == "user" else "Assistent") + ": " + m["message"] for m in transcript)
    if not lines or not get_settings().anthropic_api_key:
        return ""
    try:
        import anthropic

        from app.modules.callengine.providers import DEFAULT_MODEL

        c = anthropic.Anthropic(api_key=get_settings().anthropic_api_key, timeout=30.0)
        r = c.messages.create(model=DEFAULT_MODEL, max_tokens=300, system=SUMMARY_PROMPT,
                              messages=[{"role": "user", "content": f"Udskrift:\n\n{lines}"}])
        return "".join(b.text for b in r.content if getattr(b, "type", "") == "text").strip()
    except Exception as e:  # noqa: BLE001 – a call without a summary is still a call
        logger.warning("engine.summary_failed", detail=str(e)[:200])
        return ""


def recording_key(call_sid: str) -> str:
    return f"platform/engine-calls/{call_sid.lower()}.wav"  # storage keys are lower-case


def report(setup: dict, call_sid: str, caller: str | None, started: datetime, ended: datetime, reason: str,
           transcript: list[dict], rec: Recording, stats: dict) -> None:
    """Store the call like any other (sync – run in a thread): recording, summary, then the shared end-of-call path."""
    from sqlalchemy import select

    from app.db import get_session_factory
    from app.models import Call
    from app.modules.telephony import vapi
    from app.modules.voices import storage

    try:
        storage.put(recording_key(call_sid), rec.wav(), "audio/wav")
    except Exception as e:  # noqa: BLE001
        logger.warning("engine.recording_failed", detail=str(e)[:200])
    summary = summarise(transcript)
    message: dict[str, Any] = {
        "type": "end-of-call-report", "call": {"id": call_sid, "customer": {"number": caller} if caller else {}},
        "phoneNumber": {"number": setup["e164"]}, "startedAt": started.isoformat(), "endedAt": ended.isoformat(),
        "endedReason": reason, "analysis": {"summary": summary},
        "artifact": {"messages": [{"role": m["role"], "message": m["message"]} for m in transcript]}}
    db = get_session_factory()()
    try:
        outcome = vapi.end_of_call(db, message)
        call = db.scalar(select(Call).where(Call.provider_call_id == call_sid))
        if call is not None:
            call.provider = PROVIDER
        db.commit()
        logger.info("engine.call_stored", call_sid=call_sid, outcome=outcome, **stats)
    except Exception as e:  # noqa: BLE001
        db.rollback()
        logger.error("engine.report_failed", call_sid=call_sid, detail=str(e)[:300])
    finally:
        db.close()


# --------------------------------------------------------------------------- Twilio Media Streams

class TwilioTransport:
    def __init__(self, socket: WebSocket, rec: Recording):
        self.socket, self.rec = socket, rec
        self.stream_sid: str | None = None
        self.closed = False

    async def _send(self, msg: dict) -> None:
        if self.closed or self.stream_sid is None:
            return
        try:
            await self.socket.send_text(json.dumps({**msg, "streamSid": self.stream_sid}))
        except Exception:  # noqa: BLE001 – Twilio already hung up
            self.closed = True

    async def send_audio(self, ulaw: bytes) -> None:
        self.rec.add_peter(ulaw)
        await self._send({"event": "media", "media": {"payload": base64.b64encode(ulaw).decode()}})

    async def mark(self, name: str) -> None:
        await self._send({"event": "mark", "mark": {"name": name}})

    async def clear(self) -> None:
        self.rec.cut_peter()
        await self._send({"event": "clear"})

    async def hangup(self) -> None:
        if not self.closed:
            self.closed = True
            try:
                await self.socket.close()
            except Exception:  # noqa: BLE001
                pass


async def serve(socket: WebSocket) -> None:
    await socket.accept()
    rec = Recording()
    transport = TwilioTransport(socket, rec)
    engine: CallEngine | None = None
    setup: dict | None = None
    call_sid, caller, mode = "", None, ""
    started = datetime.now(UTC)
    early: list[bytes] = []   # caller audio that arrived while the call was being set up
    try:
        while True:
            try:
                raw = await socket.receive_text()
            except Exception:  # noqa: BLE001 – disconnect
                break
            try:
                msg = json.loads(raw)
            except ValueError:
                continue
            ev = msg.get("event")
            if ev == "media":
                if (msg.get("media") or {}).get("track", "inbound") != "inbound":
                    continue
                ulaw = base64.b64decode((msg.get("media") or {}).get("payload") or "")
                rec.add_caller(ulaw)
                if engine is not None:
                    await engine.caller_audio(ulaw)
                else:
                    early.append(ulaw)
            elif ev == "mark":
                if engine is not None:
                    engine.played((msg.get("mark") or {}).get("name") or "")
            elif ev == "start":
                start = msg.get("start") or {}
                params = start.get("customParameters") or {}
                tok = verify(params.get("t"))
                if tok is None:
                    logger.warning("engine.bad_token")
                    break
                transport.stream_sid = start.get("streamSid") or msg.get("streamSid")
                call_sid, mode = start.get("callSid") or "", tok["m"]
                caller = params.get("from") or None
                started = datetime.now(UTC)
                try:
                    setup = await asyncio.to_thread(build, uuid.UUID(tok["n"]), caller)
                except Exception as e:  # noqa: BLE001
                    logger.error("engine.setup_failed", detail=str(e)[:300])
                    break
                stt, llm, tts = make_providers(setup)
                engine = CallEngine(call_config(setup), stt, llm, tts, transport,
                                    run_tool=tool_runner(setup, caller, call_sid))
                try:
                    await engine.start()
                except Exception as e:  # noqa: BLE001 – the recogniser refused: say nothing rather than hang silent
                    logger.error("engine.start_failed", detail=str(e)[:300])
                    break
                logger.info("engine.started", call_sid=call_sid, mode=mode, number=setup["e164"])
                for chunk in early:
                    await engine.caller_audio(chunk)
                early.clear()
            elif ev == "stop":
                break
    finally:
        reason = "customer-ended-call"
        if engine is not None:
            reason = engine.ended_reason or reason
            await engine.stop(reason)
        await transport.hangup()
        if engine is not None and setup is not None and call_sid:
            ended = datetime.now(UTC)
            asyncio.get_running_loop().run_in_executor(
                None, report, setup, call_sid, caller if mode == "inbound" else None, started, ended, reason,
                list(engine.transcript), rec, {**engine.summary(), "mode": mode})

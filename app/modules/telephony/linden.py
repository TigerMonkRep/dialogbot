"""Speechmatics Agent STT ("Linden") as the call's transcriber, through Vapi's custom-transcriber protocol.

Vapi's built-in Speechmatics integration uses the general real-time model; the Agent STT model (`linden-1`) is a
separate service built for voice agents – names, numbers, 350 ms end-of-speech – and only reachable through
Speechmatics' `/v2/agent` endpoint. So the assistant's transcriber becomes `custom-transcriber` pointing at our
own WebSocket (`/api/v1/webhooks/vapi/transcriber`): Vapi streams the call's audio to us, we forward the caller's
channel to Speechmatics with the Danish names dictionary, and send each segment back as a transcript.

Protocol (Vapi → us): a text frame {"type": "start", "encoding": "linear16", "container": "raw", "sampleRate": N,
"channels": 2} (customer is channel 0, assistant channel 1), then binary frames of interleaved 16-bit PCM.
Us → Vapi: {"type": "transcriber-response", "transcription": "...", "channel": "customer",
"transcriptType": "partial" | "final"}.

Auth: the same bearer secret as the webhook (VAPI_SERVER_SECRET), sent by Vapi as a header on the upgrade.
The workspace and the call's own names ride in the URL's query string, because the protocol carries no call id.
"""
from __future__ import annotations

import array
import asyncio
import json
import uuid
from typing import Any
from urllib.parse import quote

import structlog
from fastapi import WebSocket
from sqlalchemy.orm import Session as OrmSession

from app.config import get_settings
from app.models import Workspace

logger = structlog.get_logger(__name__)

LANGUAGE = "da"
SUPPORTED_RATES = (8000, 16000)
# Which recogniser the bridge feeds. "speechmatics-agent" (Linden) is the original, tested path in this file; the
# others go through the shared adapters in app/modules/stt (Stemmetest, docs/voice/stemmetest.md). In every case VAPI
# closes the customer's turn – the bridge only sends partial and final text – so exactly one component owns endpointing.
DEFAULT_STT = "speechmatics-agent"
STT_CHOICES = ("speechmatics-agent", "speechmatics-rt", "soniox", "elevenlabs-scribe")

# Diagnostics: the raw audio Vapi sent at the start of the most recent call, exactly as received (interleaved PCM),
# so an operator can download it as WAV and hear/measure what the recogniser was given. Memory only, one call.
CAPTURE_SECONDS = 12
CAPTURE: dict[str, Any] = {"pcm": b"", "rate": 0, "channels": 0, "started_at": None}


def chosen(stt: str | None) -> str:
    return stt if stt in STT_CHOICES else DEFAULT_STT


def configured(stt: str | None = None) -> bool:
    """Is the key for the chosen recogniser present? (Linden and Speechmatics Realtime share one key.)"""
    from app.modules.stt import adapters

    return bool(adapters.key_for(chosen(stt)))


def transcriber_config(ws: Workspace | None, own: list[str], stt: str | None = None) -> dict:
    """The Vapi `transcriber` block that routes the call's audio through the bridge."""
    s = get_settings()
    base = s.public_base_url.rstrip("/").replace("https://", "wss://", 1).replace("http://", "ws://", 1)
    params = []
    if ws is not None:
        params.append(f"ws={ws.id}")
    if chosen(stt) != DEFAULT_STT:
        params.append(f"stt={chosen(stt)}")
    for x in own:
        params.append(f"extra={quote(x)}")
    url = f"{base}/api/v1/webhooks/vapi/transcriber" + (f"?{'&'.join(params)}" if params else "")
    server: dict[str, Any] = {"url": url}
    if s.vapi_server_secret:
        server["headers"] = {"Authorization": f"Bearer {s.vapi_server_secret}"}
    return {"provider": "custom-transcriber", "server": server}


def additional_vocab(db: OrmSession, ws: Workspace | None, own: list[str]) -> list[dict]:
    """The names dictionary in Speechmatics' wire form ({content, sounds_like})."""
    from app.modules.telephony import danish_names, vapi

    items = vapi.speechmatics_vocabulary(db, ws, own) if ws is not None else danish_names.vocabulary(
        vapi.SPEECHMATICS_MAX_VOCABULARY)
    return [{"content": i["content"], **({"sounds_like": i["soundsLike"]} if i.get("soundsLike") else {})}
            for i in items]


def customer_channel(pcm: bytes, channels: int, in_rate: int, out_rate: int, channel: int = 0) -> bytes:
    """One channel of interleaved 16-bit PCM (whole frames only – the caller keeps any trailing bytes so the
    interleaving never slips), resampled to `out_rate` when the rates differ (linear interpolation; phone audio is
    narrow-band, so nothing is lost that the recogniser would use)."""
    samples = array.array("h")
    samples.frombytes(pcm[: len(pcm) - len(pcm) % (2 * channels)])
    mono = samples[channel::channels] if channels > 1 else samples
    if in_rate == out_rate or not len(mono):
        return mono.tobytes()
    ratio = in_rate / out_rate
    n = int(len(mono) / ratio)
    out = array.array("h", bytes(2 * n))
    last = len(mono) - 1
    for i in range(n):
        pos = i * ratio
        j = int(pos)
        frac = pos - j
        a = mono[j]
        b = mono[j + 1] if j < last else a
        out[i] = int(a + (b - a) * frac)
    return out.tobytes()


class Session:
    """One Vapi call's bridge: a Speechmatics Agent STT session fed with the caller's audio."""

    def __init__(self, socket: WebSocket, db: OrmSession, ws: Workspace | None, own: list[str],
                 stt: str = DEFAULT_STT):
        self.socket, self.db, self.ws, self.own = socket, db, ws, own
        self.stt = stt
        self.adapter: Any = None  # a stt.adapters.Adapter when the recogniser is not Linden
        self.rate = 16000
        self.in_rate = 16000
        self.channels = 2
        self.channel = get_settings().speechmatics_customer_channel  # Vapi: customer is channel 0, assistant 1
        self.carry = b""  # bytes left over from the last frame that did not complete a whole interleaved frame
        self.levels = [0, 0, 0]  # sum |sample| per channel + frames, for the first seconds (diagnostics in the log)
        self.client: Any = None
        self.ready = asyncio.Event()
        self.sent: list[dict] = []  # what we told Vapi, for logs and tests

    async def send(self, text: str, final: bool) -> None:
        text = (text or "").strip()
        if not text:
            return
        msg = {"type": "transcriber-response", "transcription": text, "channel": "customer",
               "transcriptType": "final" if final else "partial"}
        self.sent.append(msg)
        await self.socket.send_text(json.dumps(msg))

    def _on_adapter_event(self, ev) -> None:
        """Adapter → Vapi: partial and final text only. Turn events are NOT forwarded; Vapi owns end-of-turn."""
        if ev.kind in ("partial", "final"):
            asyncio.get_running_loop().create_task(self.send(ev.text, ev.kind == "final"))
        elif ev.kind == "error":
            logger.warning("stt.error", stt=self.stt, detail=ev.text[:200])

    async def start_adapter(self, start: dict) -> None:
        from app.modules.stt import adapters

        self.channels = int(start.get("channels") or 2)
        self.in_rate = int(start.get("sampleRate") or 16000)
        self.rate = self.in_rate if self.in_rate in SUPPORTED_RATES else 16000
        vocab = [{"content": v["content"], **({"sounds_like": v["sounds_like"]} if v.get("sounds_like") else {})}
                 for v in additional_vocab(self.db, self.ws, self.own)]
        cfg = adapters.AdapterConfig(sample_rate=self.rate, vocabulary=vocab, controlled=False)
        self.adapter = adapters.make(self.stt, cfg, on_event=self._on_adapter_event)
        await self.adapter.open()
        self.client = self.adapter  # "started" for the receive loop
        self.ready.set()
        logger.info("stt.started", stt=self.stt, rate=self.rate, in_rate=self.in_rate, channels=self.channels,
                    vocab=len(vocab))

    async def start(self, start: dict) -> None:
        if self.stt != DEFAULT_STT:
            return await self.start_adapter(start)
        from speechmatics.agent_stt import (
            AgentSttAsyncClient,
            AudioEncoding,
            AudioFormat,
            ServerMessageType,
            TranscriptionConfig,
        )

        s = get_settings()
        self.channels = int(start.get("channels") or 2)
        in_rate = int(start.get("sampleRate") or 16000)
        self.in_rate = in_rate
        self.rate = in_rate if in_rate in SUPPORTED_RATES else 16000
        # Agent STT rejects the RT-only options (max_delay and friends): language, partials and the dictionary only
        config = TranscriptionConfig(language=LANGUAGE, enable_partials=True,
                                     additional_vocab=additional_vocab(self.db, self.ws, self.own))
        self.client = AgentSttAsyncClient(api_key=s.speechmatics_api_key, url=s.speechmatics_rt_url,
                                          app="dialogbot/1.0", transcription_config=config,
                                          audio_format=AudioFormat(encoding=AudioEncoding.PCM_S16LE,
                                                                   sample_rate=self.rate),
                                          record_events=False)
        loop = asyncio.get_running_loop()

        def on_segment(message: dict, final: bool) -> None:
            text = ((message.get("segment") or {}).get("transcript") or "")
            loop.create_task(self.send(text, final))

        self.client.on(ServerMessageType.ADD_SEGMENT, lambda m: on_segment(m, True))
        self.client.on(ServerMessageType.ADD_PARTIAL_SEGMENT, lambda m: on_segment(m, False))
        self.client.on(ServerMessageType.ERROR, lambda m: logger.warning("linden.error", detail=m))
        await self.client.__aenter__()
        self.ready.set()
        CAPTURE.update({"pcm": b"", "rate": in_rate, "channels": self.channels, "session": self,
                        "started_at": __import__("datetime").datetime.now(__import__("datetime").UTC).isoformat()})
        logger.info("linden.started", rate=self.rate, in_rate=in_rate, channels=self.channels, channel=self.channel,
                    vocab=len(config.additional_vocab or []))

    async def audio(self, pcm: bytes) -> None:
        if self.client is None:
            return
        if len(CAPTURE["pcm"]) < CAPTURE_SECONDS * self.in_rate * 2 * self.channels and CAPTURE.get("session") is self:
            CAPTURE["pcm"] += pcm
        data = self.carry + pcm
        frame = 2 * self.channels
        whole = len(data) - len(data) % frame
        self.carry = data[whole:]
        if not whole:
            return
        if self.channels > 1 and self.levels[2] < 5 * self.in_rate:  # the first ~5 s: which channel carries whom?
            samples = array.array("h")
            samples.frombytes(data[:whole])
            self.levels[0] += sum(abs(x) for x in samples[0::self.channels])
            self.levels[1] += sum(abs(x) for x in samples[1::self.channels])
            self.levels[2] += len(samples) // self.channels
            if self.levels[2] >= 5 * self.in_rate:
                n = max(1, self.levels[2])
                logger.info("linden.levels", ch0=round(self.levels[0] / n), ch1=round(self.levels[1] / n),
                            frames=self.levels[2], channel=self.channel)
        await self.client.send_audio(customer_channel(data[:whole], self.channels, self.in_rate, self.rate,
                                                      self.channel))  # Adapter.send_audio has the same signature

    async def close(self) -> None:
        if self.adapter is not None:
            try:
                await asyncio.wait_for(self.adapter.finish(), timeout=3)
            except Exception as e:  # noqa: BLE001 – the call is over either way
                logger.info("stt.finish", detail=str(e))
            try:
                await asyncio.wait_for(self.adapter.close(), timeout=3)
            except Exception as e:  # noqa: BLE001
                logger.info("stt.close", detail=str(e))
            self.adapter = self.client = None
            return
        if self.client is not None:
            try:
                await asyncio.wait_for(self.client.__aexit__(None, None, None), timeout=5)
            except Exception as e:  # noqa: BLE001 – the call is over either way
                logger.info("linden.close", detail=str(e))
            self.client = None


def authorized(socket: WebSocket) -> bool:
    secret = get_settings().vapi_server_secret
    if not secret:
        return False
    auth = socket.headers.get("authorization") or socket.headers.get("x-vapi-secret") or ""
    return auth == f"Bearer {secret}" or auth == secret


async def serve(socket: WebSocket) -> None:
    """The WebSocket endpoint's body: authenticate, read the start frame, bridge until Vapi hangs up."""
    from app.db import get_session_factory

    if not authorized(socket):
        await socket.close(code=4401)
        return
    stt = chosen(socket.query_params.get("stt"))
    if not configured(stt):
        await socket.close(code=4503)
        return
    await socket.accept()
    db = get_session_factory()()
    try:
        ws = None
        ws_id = socket.query_params.get("ws")
        if ws_id:
            try:
                ws = db.get(Workspace, uuid.UUID(ws_id))
            except ValueError:
                ws = None
        session = Session(socket, db, ws, socket.query_params.getlist("extra"), stt)
        try:
            while True:
                frame = await socket.receive()
                if frame.get("type") == "websocket.disconnect":
                    break
                if frame.get("bytes") is not None:
                    await session.audio(frame["bytes"])
                elif frame.get("text"):
                    try:
                        msg = json.loads(frame["text"])
                    except ValueError:
                        continue
                    if msg.get("type") == "start" and session.client is None:
                        try:
                            await session.start(msg)
                        except Exception as e:  # noqa: BLE001 – Speechmatics refused the session: log and hang up cleanly
                            logger.error("linden.start_failed", detail=str(e)[:300])
                            break
        finally:
            await session.close()
    finally:
        db.close()


async def replay(pcm16k_mono: bytes, db: OrmSession, ws: Workspace | None, own: list[str],
                 rate: int = 16000) -> list[dict]:
    """Run a known recording through the same Speechmatics session the bridge uses, without a phone call.
    Returns the final segments ({text, start, end}) – the offline test of "can Linden do Danish over our bridge"."""
    from speechmatics.agent_stt import (
        AgentSttAsyncClient,
        AudioEncoding,
        AudioFormat,
        ServerMessageType,
        TranscriptionConfig,
    )

    s = get_settings()
    config = TranscriptionConfig(language=LANGUAGE, enable_partials=False,
                                 additional_vocab=additional_vocab(db, ws, own))
    client = AgentSttAsyncClient(api_key=s.speechmatics_api_key, url=s.speechmatics_rt_url, app="dialogbot/replay",
                                 transcription_config=config,
                                 audio_format=AudioFormat(encoding=AudioEncoding.PCM_S16LE, sample_rate=rate),
                                 record_events=False)
    out: list[dict] = []

    def on_segment(message: dict) -> None:
        seg = message.get("segment") or {}
        meta = message.get("metadata") or {}
        out.append({"text": seg.get("transcript") or "", "start": meta.get("start_time"), "end": meta.get("end_time")})

    client.on(ServerMessageType.ADD_SEGMENT, on_segment)
    async with client:
        step = rate * 2 // 10  # 100 ms chunks, sent as fast as the service takes them
        for i in range(0, len(pcm16k_mono), step):
            await client.send_audio(pcm16k_mono[i:i + step])
        await client.send_audio(bytes(rate * 2))  # a second of silence so the last segment closes
    return out

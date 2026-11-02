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


def configured() -> bool:
    return bool(get_settings().speechmatics_api_key)


def transcriber_config(ws: Workspace | None, own: list[str]) -> dict:
    """The Vapi `transcriber` block that routes the call's audio through the bridge."""
    s = get_settings()
    base = s.public_base_url.rstrip("/").replace("https://", "wss://", 1).replace("http://", "ws://", 1)
    params = []
    if ws is not None:
        params.append(f"ws={ws.id}")
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

    def __init__(self, socket: WebSocket, db: OrmSession, ws: Workspace | None, own: list[str]):
        self.socket, self.db, self.ws, self.own = socket, db, ws, own
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

    async def start(self, start: dict) -> None:
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
        logger.info("linden.started", rate=self.rate, in_rate=in_rate, channels=self.channels, channel=self.channel,
                    vocab=len(config.additional_vocab or []))

    async def audio(self, pcm: bytes) -> None:
        if self.client is None:
            return
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
                                                      self.channel))

    async def close(self) -> None:
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
    if not configured():
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
        session = Session(socket, db, ws, socket.query_params.getlist("extra"))
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

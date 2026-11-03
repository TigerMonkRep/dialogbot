"""Streaming recognisers behind one small interface: Speechmatics Realtime, Speechmatics Agent STT (Linden),
Soniox and ElevenLabs Scribe v2 Realtime.

Every adapter has the same shape – `open()`, `send_audio(pcm)`, `flush()`, `finish()`, `close()` – and turns the
provider's own messages into `SttEvent`s through a PURE `handle(message)` method. The wire format is therefore tested
without a network, and the raw provider message is kept on every event so a run can show what was really said.

Verified against primary sources on 3 Nov 2026 (docs + installed SDKs):
- Speechmatics: `speechmatics-rt` 1.2.2 and `speechmatics-agent-stt` 0.3.0. Realtime model `enhanced` (RT `Model` also
  lists `standard`, `melia-1`, `oak-1`); Agent STT `linden-1` is a different API (`/v2/agent`), and its turn config
  (`vad` | `external`) sits beside the transcription config.
- Soniox: wss://stt-rt.soniox.com/transcribe-websocket, model `stt-rt-v5`, Authorization: Bearer header, start message
  JSON then binary audio, `{"type":"finalize"}` → `<fin>` token, endpoint detection → `<end>` token, an EMPTY TEXT
  frame ends the stream (an empty binary frame does not).
- ElevenLabs: wss://api.elevenlabs.io/v1/speech-to-text/realtime, model `scribe_v2_realtime`, xi-api-key header,
  `commit_strategy` manual | vad | turn_prediction, audio as JSON `input_audio_chunk` (base64), `commit: true` commits.
None of this proves one is better at Danish; that is what the measurements are for.
"""
from __future__ import annotations

import asyncio
import base64
import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlencode

from app.modules.stt.events import SttEvent

SONIOX_URL = "wss://stt-rt.soniox.com/transcribe-websocket"
ELEVENLABS_URL = "wss://api.elevenlabs.io/v1/speech-to-text/realtime"
ELEVENLABS_ERRORS = ("error", "rate_limited", "quota_exceeded", "throttled", "queue_overflow", "resource_exhausted",
                     "unaccepted_terms", "auth_error", "input_error", "chunk_size_exceeded", "transcriber_error",
                     "insufficient_audio_activity", "session_time_limit_exceeded", "invalid_request")
MAX_SONIOX_TERMS = 1000
MAX_ELEVENLABS_KEYTERMS = 50  # API maximum; each keyterm run adds a 20 % premium to the transcription price


class MissingAccess(Exception):
    """The adapter cannot run here (no key, no SDK). The profile is shown as 'Mangler adgang', never as a failure."""


@dataclass
class AdapterConfig:
    language: str = "da"
    sample_rate: int = 16000
    vocabulary: list[dict] = field(default_factory=list)  # [{"content": ..., "sounds_like": [...]?}]
    controlled: bool = False   # True = the replay closes each turn itself (flush); False = the provider endpoints
    model: str | None = None
    url: str | None = None
    # Soniox only: how aggressively it ends a turn. None = the provider default; never tuned silently.
    soniox_endpoint: dict | None = None
    # Soniox only: also release the finished words as a `final` whenever the caller pauses (every token final, none
    # pending) – not only at Soniox' own `<end>`. Needed when SOMEONE ELSE owns the turn (Vapi through the bridge):
    # Vapi only acts on final text, and waiting for `<end>` left it with partials only – Peter never answered.
    release_on_pause: bool = False
    # Soniox only: the wire format of the audio we send. Phone audio from Twilio is 8 kHz µ-law ("mulaw") and is sent
    # as it arrives – no conversion, nothing lost.
    audio_format: str = "pcm_s16le"


class Adapter:
    id = "base"
    requested_model: str | None = None
    turn_owner = ""  # filled in per adapter / mode
    sdk: dict[str, str]

    def __init__(self, cfg: AdapterConfig, api_key: str | None, on_event: Callable[[SttEvent], None] | None = None,
                 clock: Callable[[], float] = time.monotonic):
        self.cfg, self.api_key, self._sink, self._clock = cfg, api_key, on_event, clock
        self._t0 = clock()
        self.events: list[SttEvent] = []
        self.reported_model: str | None = None   # what the PROVIDER says it ran; None = unknown (never guessed)
        self.session_id: str | None = None
        self.sdk = {}
        self.finished = asyncio.Event()

    # -- plumbing -----------------------------------------------------------
    def now(self) -> float:
        return self._clock() - self._t0

    def emit(self, kind: str, text: str = "", *, start: float | None = None, end: float | None = None,
             source: str = "provider", raw: dict | None = None) -> SttEvent:
        ev = SttEvent(kind=kind, text=text, at=self.now(), audio_start=start, audio_end=end, source=source,
                      raw=raw or {})
        self.events.append(ev)
        if self._sink:
            self._sink(ev)
        return ev

    def handle(self, message: Any) -> None:  # pragma: no cover - overridden
        raise NotImplementedError

    def snapshot(self) -> dict:
        """What the run records about this adapter: requested vs reported model, SDK versions, endpoint settings."""
        return {"adapter": self.id, "requested_model": self.requested_model, "reported_model": self.reported_model,
                "sdk": self.sdk, "turn_owner": self.turn_owner, "controlled": self.cfg.controlled,
                "sample_rate": self.cfg.sample_rate, "language": self.cfg.language}

    async def open(self) -> None: ...
    async def send_audio(self, pcm: bytes) -> None: ...
    async def flush(self) -> None: ...
    async def finish(self) -> None: ...
    async def close(self) -> None: ...


def _sm_span(msg: dict) -> tuple[float | None, float | None, str]:
    meta = msg.get("metadata") or {}
    return meta.get("start_time"), meta.get("end_time"), (meta.get("transcript") or "")


def _sm_vocab(vocab: list[dict]) -> list[dict]:
    return [{"content": v["content"], **({"sounds_like": v["sounds_like"]} if v.get("sounds_like") else {})}
            for v in vocab]


# --------------------------------------------------------------------------- Speechmatics Realtime (profiles C, C+)

class SpeechmaticsRealtime(Adapter):
    """Speechmatics Realtime API with an explicit model (default `enhanced`), via the installed `speechmatics-rt`.
    Turn-taking: `EndOfUtterance` (silence-based, configurable trigger) – the provider reports it, it does not know
    the customer is finished. In controlled mode the replay sends ForceEndOfUtterance at the known end of speech."""

    id = "speechmatics-rt"

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.requested_model = self.cfg.model or "enhanced"
        self.turn_owner = "replay (ForceEndOfUtterance)" if self.cfg.controlled else "Speechmatics (EndOfUtterance, stilhed)"
        self.client: Any = None

    def handle(self, msg: dict) -> None:
        kind = msg.get("message")
        if kind == "RecognitionStarted":
            self.session_id = msg.get("id")
            self.reported_model = msg.get("model") or None  # the message carries the language pack, not a model name
            self.emit("status", "RecognitionStarted", raw=msg)
        elif kind == "AddPartialTranscript":
            s, e, text = _sm_span(msg)
            self.emit("partial", text, start=s, end=e, raw=msg)
        elif kind == "AddTranscript":
            s, e, text = _sm_span(msg)
            self.emit("final", text, start=s, end=e, raw=msg)
        elif kind == "EndOfUtterance":
            self.emit("turn_ended", source="provider", raw=msg)
        elif kind == "EndOfTranscript":
            self.finished.set()
        elif kind in ("Error",):
            self.emit("error", msg.get("reason") or msg.get("type") or "error", raw=msg)
            self.finished.set()
        elif kind in ("Warning", "Info"):
            self.emit("status", str(msg.get("reason") or msg.get("type") or kind), raw=msg)

    async def open(self) -> None:
        try:
            import speechmatics.rt as rt
            from speechmatics.rt import (
                AudioEncoding,
                AudioFormat,
                ConversationConfig,
                ServerMessageType,
                TranscriptionConfig,
            )
        except ImportError as e:  # pragma: no cover
            raise MissingAccess("speechmatics-rt er ikke installeret") from e
        if not self.api_key:
            raise MissingAccess("SPEECHMATICS_API_KEY mangler")
        import importlib.metadata as md

        self.sdk = {"speechmatics-rt": md.version("speechmatics-rt")}
        model = rt.Model(self.requested_model)
        config = TranscriptionConfig(language=self.cfg.language, model=model, enable_partials=True,
                                     additional_vocab=_sm_vocab(self.cfg.vocabulary) or None,
                                     conversation_config=None if self.cfg.controlled else ConversationConfig(
                                         end_of_utterance_silence_trigger=0.5))
        self.client = rt.AsyncClient(api_key=self.api_key, url=self.cfg.url)
        for t in ServerMessageType:
            self.client.on(t, self.handle)
        await self.client.start_session(
            transcription_config=config,
            audio_format=AudioFormat(encoding=AudioEncoding.PCM_S16LE, sample_rate=self.cfg.sample_rate))

    async def send_audio(self, pcm: bytes) -> None:
        await self.client.send_audio(pcm)

    async def flush(self) -> None:
        await self.client.force_end_of_utterance()

    async def finish(self) -> None:
        await self.client.stop_session()

    async def close(self) -> None:
        if self.client is not None:
            await self.client.close()


# --------------------------------------------------------------------------- Speechmatics Agent STT (profile D)

class SpeechmaticsAgent(Adapter):
    """Speechmatics Agent STT (`linden-1`, `/v2/agent`). Segments (AddSegment) are text pieces; StartOfTurn/EndOfTurn
    are the turn. In `vad` mode the SERVICE closes turns; in `external` mode the client must send ForceEndOfUtterance
    with an increasing audio timestamp – that is what `flush()` does. The service VAD is not configurable."""

    id = "speechmatics-agent"

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.requested_model = self.cfg.model or "linden-1"
        self.turn_owner = "replay (ForceEndOfUtterance, external)" if self.cfg.controlled else "Speechmatics (VAD, EndOfTurn)"
        self.client: Any = None

    def handle(self, msg: dict) -> None:
        kind = msg.get("message")
        if kind == "RecognitionStarted":
            self.session_id = msg.get("id")
            self.emit("status", "RecognitionStarted", raw=msg)
        elif kind in ("AddPartialSegment", "AddSegment"):
            seg = msg.get("segment") or {}
            meta = msg.get("metadata") or {}
            self.emit("partial" if kind == "AddPartialSegment" else "final", seg.get("transcript") or "",
                      start=meta.get("start_time"), end=meta.get("end_time"), raw=msg)
        elif kind == "SpeechStarted":
            self.emit("speech_started", raw=msg)
        elif kind == "SpeechEnded":
            self.emit("speech_ended", raw=msg)
        elif kind == "StartOfTurn":
            self.emit("turn_started", raw=msg)
        elif kind == "EndOfTurn":
            self.emit("turn_ended", source="provider", raw=msg)
        elif kind == "EndOfTranscript":
            self.finished.set()
        elif kind == "Error":
            self.emit("error", msg.get("reason") or msg.get("type") or "error", raw=msg)
            self.finished.set()
        elif kind in ("Warning", "Info"):
            self.emit("status", str(msg.get("reason") or msg.get("type") or kind), raw=msg)

    async def open(self) -> None:
        try:
            from speechmatics.agent_stt import (
                AgentSttAsyncClient,
                AudioEncoding,
                AudioFormat,
                ServerMessageType,
                TranscriptionConfig,
                TurnConfig,
                TurnDetectionMode,
            )
        except ImportError as e:  # pragma: no cover
            raise MissingAccess("speechmatics-agent-stt er ikke installeret") from e
        if not self.api_key:
            raise MissingAccess("SPEECHMATICS_API_KEY mangler")
        import importlib.metadata as md

        self.sdk = {"speechmatics-agent-stt": md.version("speechmatics-agent-stt"),
                    "speechmatics-rt": md.version("speechmatics-rt")}
        # Agent STT rejects the RT-only options (max_delay and friends): language, partials and the dictionary only
        config = TranscriptionConfig(language=self.cfg.language, enable_partials=True,
                                     additional_vocab=_sm_vocab(self.cfg.vocabulary) or None)
        mode = TurnDetectionMode.EXTERNAL if self.cfg.controlled else TurnDetectionMode.VAD
        self.client = AgentSttAsyncClient(api_key=self.api_key, url=self.cfg.url, app="dialogbot/stemmetest",
                                          transcription_config=config, turn_config=TurnConfig(turn_detection_mode=mode),
                                          audio_format=AudioFormat(encoding=AudioEncoding.PCM_S16LE,
                                                                   sample_rate=self.cfg.sample_rate),
                                          record_events=False)
        for t in ServerMessageType:
            self.client.on(t, self.handle)
        await self.client.connect()

    async def send_audio(self, pcm: bytes) -> None:
        await self.client.send_audio(pcm)

    async def flush(self) -> None:
        await self.client.force_end_of_utterance()  # timestamp = audio seconds sent so far (the audio timeline)

    async def finish(self) -> None:
        await self.client.disconnect()

    async def close(self) -> None:
        if self.client is not None:
            await self.client.close()


# --------------------------------------------------------------------------- Soniox (profile E)

class Soniox(Adapter):
    """Soniox real-time `stt-rt-v5`. Tokens stream in as non-final (replaced every message) and final (permanent).
    We buffer the final tokens of the current segment and release them as ONE `final` when Soniox ends the segment:
    `<end>` (its semantic endpoint – a control marker, never part of the customer's text) or `<fin>` (answer to our
    manual finalize). The context carries only the generic domain and the names dictionary – never a test answer."""

    id = "soniox"

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.requested_model = self.cfg.model or "stt-rt-v5"
        self.turn_owner = "replay (finalize → <fin>)" if self.cfg.controlled else "Soniox (semantisk endpoint, <end>)"
        self._final: list[dict] = []
        self.ws: Any = None
        self._reader: asyncio.Task | None = None

    def start_message(self) -> dict:
        msg: dict[str, Any] = {"model": self.requested_model, "audio_format": self.cfg.audio_format,
                               "sample_rate": self.cfg.sample_rate, "num_channels": 1,
                               "language_hints": [self.cfg.language],
                               "enable_endpoint_detection": not self.cfg.controlled}
        ctx: dict[str, Any] = {"general": [{"key": "domain", "value": "Telefonreception"},
                                           {"key": "language", "value": "Dansk"}]}
        terms = []
        for v in self.cfg.vocabulary[:MAX_SONIOX_TERMS]:
            terms.append(v["content"])
        if terms:
            ctx["terms"] = terms
        msg["context"] = ctx
        if self.cfg.soniox_endpoint and not self.cfg.controlled:
            msg.update({k: v for k, v in self.cfg.soniox_endpoint.items()
                        if k in ("max_endpoint_delay_ms", "endpoint_sensitivity", "endpoint_latency_adjustment_level")})
        return msg

    def _release(self, source_marker: str | None) -> None:
        if self._final:
            text = "".join(t["text"] for t in self._final).strip()
            starts = [t["start_ms"] for t in self._final if t.get("start_ms") is not None]
            ends = [t["end_ms"] for t in self._final if t.get("end_ms") is not None]
            self.emit("final", text, start=min(starts) / 1000 if starts else None,
                      end=max(ends) / 1000 if ends else None, raw={"tokens": len(self._final)})
            self._final = []
        if source_marker == "<end>":
            self.emit("turn_ended", source="provider", raw={"marker": "<end>"})
        elif source_marker == "<fin>":
            self.emit("status", "finalized", raw={"marker": "<fin>"})

    def handle(self, msg: dict) -> None:
        if msg.get("error_code"):
            self.emit("error", f'{msg.get("error_type")}: {msg.get("error_message")}', raw=msg)
            self.finished.set()
            return
        nonfinal: list[str] = []
        for tok in msg.get("tokens") or []:
            text = tok.get("text", "")
            if text in ("<end>", "<fin>"):  # control tokens: always final, never customer text
                self._release(text)
                nonfinal = []
            elif tok.get("is_final"):
                self._final.append(tok)
            else:
                nonfinal.append(text)
        if msg.get("tokens") and self.cfg.release_on_pause and self._final and not nonfinal:
            self._release(None)  # a pause: everything heard so far is final – hand it over now
            return
        if msg.get("tokens"):
            shown = ("".join(t["text"] for t in self._final) + "".join(nonfinal)).strip()
            if shown:
                self.emit("partial", shown, raw={"final_tokens": len(self._final), "nonfinal_tokens": len(nonfinal)})
        if msg.get("finished"):
            self._release(None)
            self.finished.set()

    async def open(self) -> None:
        if not self.api_key:
            raise MissingAccess("SONIOX_API_KEY mangler")
        try:
            import importlib.metadata as md

            import websockets
        except ImportError as e:  # pragma: no cover
            raise MissingAccess("websockets er ikke installeret") from e
        self.sdk = {"websockets": md.version("websockets"), "transport": "egen WebSocket-klient (ingen Soniox-SDK)"}
        self.ws = await websockets.connect(self.cfg.url or SONIOX_URL,
                                           additional_headers={"Authorization": f"Bearer {self.api_key}"})
        await self.ws.send(json.dumps(self.start_message()))
        self._reader = asyncio.create_task(self._read())

    async def _read(self) -> None:
        try:
            async for raw in self.ws:
                self.handle(json.loads(raw))
        except Exception as e:  # noqa: BLE001 – a dropped socket is a result, not a crash
            self.emit("error", f"forbindelse: {e}")
        finally:
            self.finished.set()

    async def send_audio(self, pcm: bytes) -> None:
        await self.ws.send(pcm)

    async def flush(self) -> None:
        await self.ws.send(json.dumps({"type": "finalize"}))

    async def finish(self) -> None:
        await self.ws.send("")  # an empty TEXT frame ends the stream; an empty binary frame is just empty audio

    async def close(self) -> None:
        if self.ws is not None:
            await self.ws.close()
        if self._reader:
            self._reader.cancel()


# --------------------------------------------------------------------------- ElevenLabs Scribe v2 Realtime (profile F)

class ElevenLabsScribe(Adapter):
    """ElevenLabs speech-to-text `scribe_v2_realtime` (NOT their voice generation, NOT batch Scribe v2).
    `partial_transcript` is interim; `committed_transcript` is stable for its segment. A commit is NOT proof that the
    customer finished: this adapter emits `final` only, and the profile says which component ends the turn. The raw
    committed text is what is scored – `transcript_edit` is deliberately never requested."""

    id = "elevenlabs-scribe"

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.requested_model = self.cfg.model or "scribe_v2_realtime"
        self.turn_owner = "replay (manuel commit)" if self.cfg.controlled else "lokal regel: første commit (VAD) efter lydens slutning"

    def query(self) -> dict:
        q: dict[str, Any] = {"model_id": self.requested_model, "audio_format": f"pcm_{self.cfg.sample_rate}",
                             "language_code": self.cfg.language,
                             "commit_strategy": "manual" if self.cfg.controlled else "vad"}
        return q

    def url(self) -> str:
        q = urlencode(self.query())
        keyterms = [v["content"] for v in self.cfg.vocabulary][:MAX_ELEVENLABS_KEYTERMS]
        if keyterms:
            q += "&" + urlencode([("keyterms", k) for k in keyterms])
        return f"{self.cfg.url or ELEVENLABS_URL}?{q}"

    def handle(self, msg: dict) -> None:
        kind = msg.get("message_type", "")
        if kind == "session_started":
            self.session_id = msg.get("session_id")
            self.reported_model = (msg.get("config") or {}).get("model_id")
            self.emit("status", "session_started", raw=msg)
        elif kind == "partial_transcript":
            self.emit("partial", msg.get("text", ""), raw=msg)
        elif kind == "committed_transcript":
            self.emit("final", msg.get("text", ""), raw=msg)
        elif kind == "warning":
            self.emit("status", str(msg.get("warning") or "warning"), raw=msg)
        elif kind in ELEVENLABS_ERRORS or kind.endswith("_error") or "error" in msg:
            self.emit("error", str(msg.get("error") or kind), raw=msg)
            self.finished.set()

    async def open(self) -> None:
        if not self.api_key:
            raise MissingAccess("ELEVENLABS_API_KEY mangler")
        try:
            import importlib.metadata as md

            import websockets
        except ImportError as e:  # pragma: no cover
            raise MissingAccess("websockets er ikke installeret") from e
        self.sdk = {"websockets": md.version("websockets"), "transport": "egen WebSocket-klient (ingen ElevenLabs-SDK)"}
        self.ws = await websockets.connect(self.url(), additional_headers={"xi-api-key": self.api_key})
        self._reader = asyncio.create_task(self._read())

    async def _read(self) -> None:
        try:
            async for raw in self.ws:
                self.handle(json.loads(raw))
        except Exception as e:  # noqa: BLE001
            self.emit("error", f"forbindelse: {e}")
        finally:
            self.finished.set()

    async def _chunk(self, pcm: bytes, commit: bool) -> None:
        await self.ws.send(json.dumps({"message_type": "input_audio_chunk",
                                       "audio_base_64": base64.b64encode(pcm).decode(), "commit": commit,
                                       "sample_rate": self.cfg.sample_rate}))

    async def send_audio(self, pcm: bytes) -> None:
        await self._chunk(pcm, False)

    async def flush(self) -> None:
        await self._chunk(bytes(self.cfg.sample_rate * 2 // 10), True)  # 100 ms silence carrying commit=true

    async def finish(self) -> None:
        if self.cfg.controlled:
            return  # the last flush already committed everything
        await self._chunk(bytes(self.cfg.sample_rate * 2), True)  # a second of silence so VAD can close the segment

    async def close(self) -> None:
        if getattr(self, "ws", None) is not None:
            await self.ws.close()
        if getattr(self, "_reader", None):
            self._reader.cancel()


ADAPTERS: dict[str, type[Adapter]] = {c.id: c for c in (SpeechmaticsRealtime, SpeechmaticsAgent, Soniox, ElevenLabsScribe)}


def key_for(adapter_id: str) -> str | None:
    from app.config import get_settings

    s = get_settings()
    return {"speechmatics-rt": s.speechmatics_api_key, "speechmatics-agent": s.speechmatics_api_key,
            "soniox": s.soniox_api_key, "elevenlabs-scribe": s.elevenlabs_api_key}.get(adapter_id)


def make(adapter_id: str, cfg: AdapterConfig, api_key: str | None = None, **kw) -> Adapter:
    if adapter_id not in ADAPTERS:
        raise KeyError(adapter_id)
    if adapter_id.startswith("speechmatics") and not cfg.url:
        from app.config import get_settings

        cfg.url = get_settings().speechmatics_rt_url
    return ADAPTERS[adapter_id](cfg, api_key if api_key is not None else key_for(adapter_id), **kw)

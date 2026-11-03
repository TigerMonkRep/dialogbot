"""The real providers behind the engine's three interfaces: Soniox (ears), Claude (thinking), ElevenLabs (voice).

All three speak the phone's own audio format (8 kHz µ-law), so nothing is converted on the live path."""
from __future__ import annotations

import json
from collections.abc import AsyncIterator, Callable
from typing import Any

import structlog

from app.config import get_settings
from app.modules.callengine.audio import RATE

logger = structlog.get_logger(__name__)

ELEVENLABS_TTS = "https://api.elevenlabs.io/v1/text-to-speech/{voice}/stream"
LANGUAGE_CODE_MODELS = ("eleven_flash_v2_5", "eleven_turbo_v2_5", "eleven_v4_turbo")
DEFAULT_MODEL = "claude-haiku-4-5-20251001"  # the same fast model the phone uses today (VAPI_MODEL overrides both)


class SonioxStt:
    """Soniox real-time, fed the caller's µ-law as it arrives. Soniox's own endpoint (`<end>`) is the end of the
    caller's turn – the engine has no second opinion. Partials go out for barge-in; the turn's text goes out once."""

    def __init__(self, vocabulary: list[dict], endpoint: dict | None = None, api_key: str | None = None):
        from app.modules.stt import adapters

        s = get_settings()
        cfg = adapters.AdapterConfig(sample_rate=RATE, audio_format="mulaw", vocabulary=vocabulary, controlled=False,
                                     soniox_endpoint=endpoint)
        self._key = api_key or s.soniox_api_key
        self._cfg = cfg
        self._adapter: Any = None
        self._turn: list[str] = []
        self._sink: Callable[[str, str], None] | None = None

    def _event(self, ev) -> None:
        if self._sink is None:
            return
        if ev.kind == "partial":
            self._sink("partial", ev.text)
        elif ev.kind == "final":
            self._turn.append(ev.text)
        elif ev.kind == "turn_ended":
            text = " ".join(t for t in self._turn if t).strip()
            self._turn = []
            if text:
                self._sink("final", text)
        elif ev.kind == "error":
            self._sink("error", ev.text)

    async def open(self, on_event: Callable[[str, str], None]) -> None:
        from app.modules.stt import adapters

        self._sink = on_event
        self._adapter = adapters.make("soniox", self._cfg, api_key=self._key, on_event=self._event)
        await self._adapter.open()

    async def send(self, ulaw: bytes) -> None:
        if self._adapter is not None:
            await self._adapter.send_audio(ulaw)

    async def close(self) -> None:
        if self._adapter is not None:
            try:
                await self._adapter.finish()
            finally:
                await self._adapter.close()
            self._adapter = None


class ClaudeLlm:
    def __init__(self, model: str | None = None, max_tokens: int = 220, temperature: float = 0.7):
        import anthropic

        s = get_settings()
        self.model = model or s.engine_model or s.vapi_model or DEFAULT_MODEL
        self.max_tokens, self.temperature = max_tokens, temperature
        self.client = anthropic.AsyncAnthropic(api_key=s.anthropic_api_key, timeout=30.0)

    async def stream(self, system: str, messages: list[dict], tools: list[dict]) -> AsyncIterator[tuple[str, Any]]:
        kw: dict[str, Any] = {"model": self.model, "max_tokens": self.max_tokens, "temperature": self.temperature,
                              # the system prompt is long and identical for the whole call: cache it
                              "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
                              "messages": messages}
        if tools:
            kw["tools"] = tools
        async with self.client.messages.stream(**kw) as st:
            async for ev in st:
                if ev.type == "content_block_delta" and getattr(ev.delta, "type", "") == "text_delta":
                    yield "text", ev.delta.text
            final = await st.get_final_message()
        yield "done", [b.model_dump(exclude_none=True) for b in final.content]


class ElevenTts:
    """ElevenLabs streaming TTS, one request per sentence, answered directly as 8 kHz µ-law for the phone.
    `previous_text` keeps the intonation continuous across sentences."""

    def __init__(self, voice_id: str, model: str, latency: int | None = 3, api_key: str | None = None):
        import httpx

        self.voice_id, self.model, self.latency = voice_id, model, latency
        self.key = api_key or get_settings().elevenlabs_api_key
        self.http = httpx.AsyncClient(timeout=httpx.Timeout(20.0, connect=5.0))

    async def stream(self, text: str, previous_text: str | None) -> AsyncIterator[bytes]:
        params: dict[str, Any] = {"output_format": "ulaw_8000"}
        if self.latency is not None:
            params["optimize_streaming_latency"] = self.latency
        body: dict[str, Any] = {"text": text, "model_id": self.model}
        if previous_text:
            body["previous_text"] = previous_text
        if self.model in LANGUAGE_CODE_MODELS:
            body["language_code"] = "da"
        async with self.http.stream("POST", ELEVENLABS_TTS.format(voice=self.voice_id), params=params, json=body,
                                    headers={"xi-api-key": self.key or ""}) as r:
            if r.status_code >= 400:
                detail = (await r.aread())[:300]
                raise RuntimeError(f"ElevenLabs {r.status_code}: {detail!r}")
            async for chunk in r.aiter_bytes(1600):  # 200 ms per chunk
                yield chunk

    async def aclose(self) -> None:
        await self.http.aclose()


def soniox_endpoint() -> dict | None:
    raw = get_settings().engine_soniox_endpoint_json
    if not raw:
        return None
    try:
        v = json.loads(raw)
        return v if isinstance(v, dict) else None
    except ValueError:
        return None


def configured() -> dict:
    """Which keys the engine has (booleans only, never values)."""
    s = get_settings()
    return {"soniox": bool(s.soniox_api_key), "anthropic": bool(s.anthropic_api_key),
            "elevenlabs": bool(s.elevenlabs_api_key), "secret": bool(s.vapi_server_secret)}

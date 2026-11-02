"""Speechmatics Agent STT (Linden) through Vapi's custom-transcriber protocol: telephony.linden."""
from __future__ import annotations

import array
import json

import pytest
from starlette.websockets import WebSocketDisconnect

from app.config import get_settings
from app.modules.telephony import linden, vapi

from .test_telephony import SECRET, _post, _setup


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setenv("VAPI_SERVER_SECRET", SECRET)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_customer_channel_is_split_and_resampled():
    stereo = array.array("h", [100, -100, 200, -200, 300, -300, 400, -400])  # L/R interleaved
    mono = array.array("h")
    mono.frombytes(linden.customer_channel(stereo.tobytes(), 2, 16000, 16000))
    assert list(mono) == [100, 200, 300, 400]
    down = array.array("h")
    down.frombytes(linden.customer_channel(stereo.tobytes(), 2, 24000, 16000))
    assert len(down) == 2 and down[0] == 100  # 4 samples at 24 kHz → 2 at 16 kHz (linear)
    assert linden.customer_channel(b"", 2, 16000, 16000) == b""


def test_without_a_speechmatics_key_calls_stay_on_deepgram(client, api, two_workspaces, configured, monkeypatch):
    _setup(api, two_workspaces)
    monkeypatch.setenv("VAPI_TRANSCRIBER_JSON", '{"provider": "custom-transcriber"}')
    monkeypatch.delenv("SPEECHMATICS_API_KEY", raising=False)
    get_settings.cache_clear()
    a = _post(client, {"type": "assistant-request", "call": {"phoneNumberId": "pn_123"}}).json()["assistant"]
    assert a["transcriber"]["provider"] == "deepgram" and "keyterm" in a["transcriber"]


def test_with_a_key_the_call_streams_to_our_bridge(client, api, two_workspaces, configured, monkeypatch):
    t = two_workspaces
    _setup(api, t)
    monkeypatch.setenv("VAPI_TRANSCRIBER_JSON", '{"provider": "custom-transcriber"}')
    monkeypatch.setenv("SPEECHMATICS_API_KEY", "sm-test")
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://api.dialogbot.dk")
    get_settings.cache_clear()
    a = _post(client, {"type": "assistant-request", "call": {"phoneNumberId": "pn_123"}}).json()["assistant"]
    tr = a["transcriber"]
    assert tr["provider"] == "custom-transcriber"
    assert tr["server"]["url"] == f"wss://api.dialogbot.dk/api/v1/webhooks/vapi/transcriber?ws={t['ws_a']}"
    assert tr["server"]["headers"]["Authorization"] == f"Bearer {SECRET}"
    # the call's own names ride along in the URL (demo calls, campaigns, the sales channel)
    import uuid

    from app.models import Workspace
    ws = Workspace(id=uuid.UUID(t["ws_a"]), name="x", slug="x")
    cfg = linden.transcriber_config(ws, ["Berle Pool", "René"])
    assert cfg["server"]["url"].endswith(f"?ws={t['ws_a']}&extra=Berle%20Pool&extra=Ren%C3%A9")


class FakeClient:
    """Stands in for AgentSttAsyncClient: records what it was built with, echoes a segment per audio chunk."""
    instances: list = []

    def __init__(self, **kw):
        self.kw, self.handlers, self.audio, self.closed = kw, {}, [], False
        FakeClient.instances.append(self)

    def on(self, event, handler):
        self.handlers[event] = handler

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        self.closed = True

    async def send_audio(self, chunk: bytes):
        from speechmatics.agent_stt import ServerMessageType

        self.audio.append(chunk)
        n = len(self.audio)
        self.handlers[ServerMessageType.ADD_PARTIAL_SEGMENT]({"segment": {"transcript": f"andr {n}"}})
        self.handlers[ServerMessageType.ADD_SEGMENT]({"segment": {"transcript": f"André {n}."}})


def test_bridge_speaks_vapis_protocol(client, api, two_workspaces, configured, monkeypatch):
    import speechmatics.agent_stt as sm

    t = two_workspaces
    _setup(api, t)
    monkeypatch.setenv("SPEECHMATICS_API_KEY", "sm-test")
    get_settings.cache_clear()
    monkeypatch.setattr(sm, "AgentSttAsyncClient", FakeClient)
    FakeClient.instances.clear()
    url = f"/api/v1/webhooks/vapi/transcriber?ws={t['ws_a']}&extra=Berle%20Pool"
    # no secret → refused before accept
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(url):
            pass
    with client.websocket_connect(url, headers={"Authorization": f"Bearer {SECRET}"}) as socket:
        socket.send_text(json.dumps({"type": "start", "encoding": "linear16", "container": "raw",
                                     "sampleRate": 16000, "channels": 2}))
        stereo = array.array("h", [1, 9, 2, 9, 3, 9]).tobytes()
        socket.send_bytes(stereo)
        partial = json.loads(socket.receive_text())
        final = json.loads(socket.receive_text())
    assert partial == {"type": "transcriber-response", "transcription": "andr 1", "channel": "customer",
                       "transcriptType": "partial"}
    assert final["transcription"] == "André 1." and final["transcriptType"] == "final"
    fake = FakeClient.instances[-1]
    assert fake.closed and fake.kw["api_key"] == "sm-test"
    assert array.array("h", fake.audio[0]).tolist() == [1, 2, 3]  # only the caller's channel went to Speechmatics
    cfg = fake.kw["transcription_config"]
    assert cfg.language == "da" and cfg.enable_partials is True and cfg.max_delay is None  # Agent STT rejects max_delay
    vocab = cfg.additional_vocab
    assert vocab[0] == {"content": "Berle Pool"} and {"content": "Fjord Gulvservice"} in vocab
    assert {"content": "Kjeld", "sounds_like": ["kell", "keld", "kjell"]} in vocab
    assert len(vocab) <= vapi.SPEECHMATICS_MAX_VOCABULARY


def test_odd_sized_frames_never_slip_the_channels():
    """Vapi's binary frames need not end on a whole stereo frame; leftover bytes carry over, so channel 0 stays
    the caller across frames instead of flipping to the assistant."""
    import asyncio

    class Sink:
        def __init__(self):
            self.chunks = []

        async def send_audio(self, chunk):
            self.chunks.append(chunk)

    s = linden.Session.__new__(linden.Session)
    s.client, s.channels, s.in_rate, s.rate, s.channel, s.carry = Sink(), 2, 16000, 16000, 0, b""
    s.levels = [0, 0, 0]
    stereo = array.array("h", [1, 9, 2, 9, 3, 9, 4, 9]).tobytes()  # 4 stereo frames = 16 bytes
    asyncio.run(s.audio(stereo[:6]))   # 1 whole frame + 2 bytes carried
    asyncio.run(s.audio(stereo[6:]))   # the rest
    got = array.array("h")
    for c in s.client.chunks:
        got.frombytes(c)
    assert got.tolist() == [1, 2, 3, 4] and s.carry == b""

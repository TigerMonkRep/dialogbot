"""Phone audio helpers: G.711 µ-law ↔ 16-bit PCM and the two-track call recording.

Twilio Media Streams carry 8 kHz mono µ-law both ways, Soniox accepts µ-law directly and ElevenLabs can answer in it
(`ulaw_8000`), so the live path never converts. Conversion is only needed for the recording (WAV is PCM) and for
operator uploads in the simulator. Pure Python (audioop is gone from Python 3.13)."""
from __future__ import annotations

import array
import io
import wave

RATE = 8000          # samples per second, one byte per µ-law sample
FRAME_BYTES = 160    # 20 ms – Twilio's own frame size

_BIAS = 0x84
_CLIP = 32635


def _ulaw_to_lin(u: int) -> int:
    u = ~u & 0xFF
    sign = u & 0x80
    exponent = (u >> 4) & 0x07
    mantissa = u & 0x0F
    sample = ((mantissa << 3) + _BIAS) << exponent
    sample -= _BIAS
    return -sample if sign else sample


_DECODE = array.array("h", [_ulaw_to_lin(i) for i in range(256)])


def _lin_to_ulaw(sample: int) -> int:
    sign = 0x80 if sample < 0 else 0
    if sign:
        sample = -sample
    sample = min(sample, _CLIP) + _BIAS
    exponent = 7
    mask = 0x4000
    while exponent > 0 and not (sample & mask):
        exponent -= 1
        mask >>= 1
    mantissa = (sample >> (exponent + 3)) & 0x0F
    return ~(sign | (exponent << 4) | mantissa) & 0xFF


_ENCODE = bytes(_lin_to_ulaw(i - 32768) for i in range(65536))
SILENCE = bytes([_lin_to_ulaw(0)])  # 0xFF


def ulaw_to_pcm16(data: bytes) -> bytes:
    out = array.array("h", (_DECODE[b] for b in data))
    return out.tobytes()


def pcm16_to_ulaw(data: bytes) -> bytes:
    samples = array.array("h")
    samples.frombytes(data[: len(data) - len(data) % 2])
    return bytes(_ENCODE[s + 32768] for s in samples)


def resample_pcm16(data: bytes, in_rate: int, out_rate: int) -> bytes:
    """Linear-interpolation resampling of mono 16-bit PCM (only used for operator uploads)."""
    samples = array.array("h")
    samples.frombytes(data[: len(data) - len(data) % 2])
    if in_rate == out_rate or not samples:
        return samples.tobytes()
    ratio = in_rate / out_rate
    n = int(len(samples) / ratio)
    last = len(samples) - 1
    out = array.array("h", bytes(2 * n))
    for i in range(n):
        pos = i * ratio
        j = int(pos)
        a = samples[j]
        b = samples[j + 1] if j < last else a
        out[i] = int(a + (b - a) * (pos - j))
    return out.tobytes()


def wav_to_ulaw8k(raw: bytes) -> bytes:
    """Any 16-bit PCM WAV (mono or stereo, any rate) → 8 kHz µ-law mono (first channel), as a phone would carry it."""
    with wave.open(io.BytesIO(raw), "rb") as w:
        if w.getsampwidth() != 2:
            raise ValueError("WAV skal være 16-bit PCM")
        ch, rate, frames = w.getnchannels(), w.getframerate(), w.readframes(w.getnframes())
    samples = array.array("h")
    samples.frombytes(frames[: len(frames) - len(frames) % (2 * ch)])
    mono = samples[0::ch] if ch > 1 else samples
    return pcm16_to_ulaw(resample_pcm16(mono.tobytes(), rate, RATE))


class Recording:
    """Two tracks on one clock: the caller (left) as it arrived, and Peter (right) where it was actually playing.

    The clock is the caller's audio: Twilio sends a 20 ms frame every 20 ms for the whole call, so the number of
    caller bytes received IS the call time in samples. Peter's audio is placed at max(now, end of what he already
    queued) – we send faster than real time and Twilio buffers – and a barge-in (`clear`) cuts his track at `now`,
    which is exactly what the caller heard."""

    def __init__(self) -> None:
        self.caller = bytearray()
        self.peter = bytearray()

    @property
    def now(self) -> int:
        return len(self.caller)

    def add_caller(self, ulaw: bytes) -> None:
        self.caller += ulaw

    def add_peter(self, ulaw: bytes) -> None:
        if len(self.peter) < self.now:
            self.peter += SILENCE * (self.now - len(self.peter))
        self.peter += ulaw

    def cut_peter(self) -> None:
        if len(self.peter) > self.now:
            del self.peter[self.now:]

    def queued_ms(self) -> int:
        """How much of Peter's audio is still waiting to be played (ms)."""
        return max(0, len(self.peter) - self.now) * 1000 // RATE

    def wav(self) -> bytes:
        n = max(len(self.caller), len(self.peter))
        left = ulaw_to_pcm16(bytes(self.caller) + SILENCE * (n - len(self.caller)))
        right = ulaw_to_pcm16(bytes(self.peter) + SILENCE * (n - len(self.peter)))
        a, b = array.array("h"), array.array("h")
        a.frombytes(left)
        b.frombytes(right)
        inter = array.array("h", bytes(4 * n))
        inter[0::2] = a
        inter[1::2] = b
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(2)
            w.setsampwidth(2)
            w.setframerate(RATE)
            w.writeframes(inter.tobytes())
        return buf.getvalue()

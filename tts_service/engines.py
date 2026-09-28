"""Speech engines for the TTS service.

ChatterboxEngine – the Chatterbox Multilingual architecture (Resemble AI, MIT code) with Danish weights: by default
Røst-v3 (CoRal-project/roest-v3-chatterbox-500m, the Alexandra Institute's Chatterbox finetuned on 2,000+ hours of
Danish; OpenRAIL-S licence with use restrictions, see docs/voice/rights.md). Voice given by reference-clip
conditioning, `language_id="da"`. MODEL_REPO/MODEL_T3 can point at another compatible checkpoint (e.g.
ResembleAI/chatterbox with t3_mtl23ls_v3.safetensors). The code is installed from GitHub at a pinned commit. Weights are downloaded from Hugging Face at a pinned commit (MODEL_REVISION) –
never "main". The model applies its built-in Perth watermark to all audio; we keep it.

Chatterbox keeps the active voice in `model.conds` (shared, mutable). The service therefore runs one
generation at a time per model instance under a lock and sets the voice's own cached Conditionals immediately
before each generation, so one customer's voice can never leak into another session.

FakeEngine – a deterministic tone for tests of the service mechanics; results are labelled simulated.
"""
from __future__ import annotations

import hashlib
import math
import os
import re
import threading
from dataclasses import dataclass

import numpy as np

DEFAULT_REPO = "CoRal-project/roest-v3-chatterbox-500m"
DEFAULT_T3 = "t3_mtl23ls_v2.safetensors"  # Røst-v3 ships its Danish T3 under the v2 file name
# Sampling defaults from the Røst-v3 model card's MOS evaluation (20 Danish raters).
DEFAULT_SETTINGS = {"temperature": 0.7, "cfg_weight": 0.5, "exaggeration": 0.5, "top_p": 0.95, "min_p": 0.05,
                    "repetition_penalty": 2.0}
BASE_FILES = ["ve.pt", "s3gen.pt", "grapheme_mtl_merged_expanded_v1.json", "conds.pt", "Cangjie5_TC.json"]


@dataclass
class VoiceState:
    key: str
    conds: object | None
    settings: dict


class FakeEngine:
    name = "fake"
    simulated = True
    watermark = "none"

    def __init__(self, model_repo: str, model_revision: str, sample_rate: int = 24000):
        self.model_repo, self.model_revision, self.sample_rate = model_repo, model_revision, sample_rate
        self.lock = threading.Lock()
        self.current: str | None = None  # which voice is loaded into the (fake) shared model state

    def load(self) -> None:
        return None

    def prepare_voice(self, key: str, ref_path: str | None, settings: dict) -> VoiceState:
        return VoiceState(key=key, conds={"freq": 180 + int(hashlib.sha256(key.encode()).hexdigest()[:4], 16) % 220},
                          settings=settings)

    def load_voice(self, key: str, conds_path: str, settings: dict) -> VoiceState:
        with open(conds_path, "rb") as f:
            digest = hashlib.sha256(f.read()).hexdigest()
        return VoiceState(key=key, conds={"freq": 180 + int(digest[:4], 16) % 220}, settings=settings)

    def generate(self, voice: VoiceState, text: str) -> np.ndarray:
        self.current = voice.key
        freq = voice.conds["freq"]
        n = int(self.sample_rate * max(0.3, 0.06 * len(text.split())))
        t = np.arange(n) / self.sample_rate
        assert self.current == voice.key  # the shared state belongs to this request for the whole generation
        return (0.1 * np.sin(2 * math.pi * freq * t)).astype(np.float32)

    def stream(self, voice: VoiceState, text: str, first: int = 12, step: int = 20, seed: int | None = None,
               **_tuning):
        wav = self.generate(voice, text)
        cut = [0, min(len(wav), first * self.sample_rate // 25)]
        while cut[-1] < len(wav):
            cut.append(min(len(wav), cut[-1] + step * self.sample_rate // 25))
        for a, b in zip(cut, cut[1:], strict=False):
            assert self.current == voice.key
            yield wav[a:b]


class ChatterboxEngine:
    name = "chatterbox-multilingual"
    simulated = False
    watermark = "perth"

    def __init__(self, model_repo: str, model_revision: str, device: str, cache_dir: str | None = None,
                 t3_file: str = DEFAULT_T3):
        if len(model_revision) != 40:
            raise ValueError("MODEL_REVISION must be a full 40-character commit hash")
        if not re.fullmatch(r"t3_mtl23ls_v\d+\.safetensors", t3_file):
            raise ValueError("MODEL_T3 must be a multilingual T3 checkpoint such as t3_mtl23ls_v3.safetensors")
        self.model_repo, self.model_revision, self.device, self.cache_dir = model_repo, model_revision, device, cache_dir
        self.t3_file = t3_file
        self.lock = threading.Lock()
        self.model = None
        self.stepper = None
        self.last_profile: dict | None = None
        self.sample_rate = 24000

    def load(self) -> None:
        from chatterbox.mtl_tts import ChatterboxMultilingualTTS  # heavy import only in the real service
        from huggingface_hub import snapshot_download

        path = snapshot_download(repo_id=self.model_repo, repo_type="model", revision=self.model_revision,
                                 allow_patterns=[*BASE_FILES, self.t3_file], cache_dir=self.cache_dir)
        self.model = ChatterboxMultilingualTTS.from_local(path, self.device, t3_model=self.t3_file)
        self.sample_rate = int(self.model.sr)

    def prepare_voice(self, key: str, ref_path: str | None, settings: dict) -> VoiceState:
        if ref_path is None:
            raise ValueError("reference clip required")
        with self.lock:
            self.model.prepare_conditionals(ref_path, exaggeration=float(settings.get("exaggeration", 0.5)))
            conds = self.model.conds
            self.model.conds = None
        return VoiceState(key=key, conds=conds, settings=settings)

    def load_voice(self, key: str, conds_path: str, settings: dict) -> VoiceState:
        """Precomputed conditioning (designed voices). torch.load runs with weights_only=True, so the file cannot
        execute code; the caller has already verified its sha256 against the voice version."""
        from chatterbox.mtl_tts import Conditionals

        conds = Conditionals.load(conds_path, map_location="cpu").to(self.device)
        return VoiceState(key=key, conds=conds, settings=settings)

    def generate(self, voice: VoiceState, text: str) -> np.ndarray:
        s = DEFAULT_SETTINGS | {k: float(v) for k, v in voice.settings.items() if k in DEFAULT_SETTINGS}
        self.model.conds = voice.conds  # caller holds self.lock
        wav = self.model.generate(text, language_id="da", **s)
        return wav.squeeze(0).detach().cpu().numpy().astype(np.float32)

    def stream(self, voice: VoiceState, text: str, first: int = 12, step: int = 20, seed: int | None = None,
               window: int | None = None, prompt_tokens: int | None = None, cfm_steps: int = 10):
        """Yield float32 audio at 24 kHz while the utterance is being generated (see tts_service.streaming).

        The first chunk is decoded after `first` speech tokens (~0.5 s of speech), then every `step` tokens. With
        `window`, each decode covers only the newest `window` tokens (must exceed step by the stitcher's holdback
        plus a margin; step + 16 is safe). Caller holds self.lock for the whole generator (shared voice state).
        Timings of the last utterance are kept in `last_profile`."""
        import time as _t

        import torch
        import torch.nn.functional as F
        from chatterbox.models.t3.modules.cond_enc import T3Cond
        from chatterbox.mtl_tts import punc_norm

        from tts_service import streaming

        if window is not None and window < step + 12:
            raise ValueError("window must exceed step by at least 12 tokens")
        m = self.model
        s = DEFAULT_SETTINGS | {k: float(v) for k, v in voice.settings.items() if k in DEFAULT_SETTINGS}
        m.conds = voice.conds
        if float(s["exaggeration"]) != float(m.conds.t3.emotion_adv[0, 0, 0].item()):
            c = m.conds.t3
            m.conds.t3 = T3Cond(speaker_emb=c.speaker_emb, cond_prompt_speech_tokens=c.cond_prompt_speech_tokens,
                                emotion_adv=s["exaggeration"] * torch.ones(1, 1, 1)).to(device=m.device)
        if self.stepper is None:
            self.stepper = streaming.T3Stepper(m.t3, m.device)
        tt = m.tokenizer.text_to_tokens(punc_norm(text), language_id="da").to(m.device)
        tt = torch.cat([tt, tt], dim=0)  # two rows for classifier-free guidance
        tt = F.pad(F.pad(tt, (1, 0), value=m.t3.hp.start_text_token), (0, 1), value=m.t3.hp.stop_text_token)
        stitch = streaming.DecodeStitcher()
        noise = streaming.utterance_noise(m, 1000, seed if seed is not None else int.from_bytes(os.urandom(4), "big"))
        tokens: list[int] = []
        next_at = first
        prof = {"t3_ms": 0.0, "decode_ms": 0.0, "post_ms": 0.0, "decodes": 0, "tokens": 0,
                "graph": bool(self.stepper.compiled)}
        opts = {"window": window, "prompt_tokens": prompt_tokens, "cfm_steps": cfm_steps}

        def emit(final: bool):
            t0 = _t.perf_counter()
            wav, off = streaming.decode(m, tokens, noise, finalize=final, **opts)
            if torch.cuda.is_available():
                torch.cuda.synchronize()
            t1 = _t.perf_counter()
            out = stitch.feed(self._post(wav), final=final, offset=off)
            prof["decode_ms"] += (t1 - t0) * 1000
            prof["post_ms"] += (_t.perf_counter() - t1) * 1000
            prof["decodes"] += 1
            return out

        with torch.inference_mode():
            t = _t.perf_counter()
            for tok in self.stepper.tokens(m.conds.t3, tt, temperature=s["temperature"], cfg_weight=s["cfg_weight"],
                                           repetition_penalty=s["repetition_penalty"], min_p=s["min_p"],
                                           top_p=s["top_p"]):
                prof["t3_ms"] += (_t.perf_counter() - t) * 1000
                tokens.append(tok)
                if len(tokens) >= next_at:
                    next_at += step
                    out = emit(False)
                    if len(out):
                        yield out
                t = _t.perf_counter()
            prof["tokens"], prof["graph"] = len(tokens), bool(self.stepper.compiled)
            out = emit(True)
            self.last_profile = {k: round(v, 1) if isinstance(v, float) else v for k, v in prof.items()}
            yield out

    def _post(self, wav: np.ndarray) -> np.ndarray:
        """What the stock generate does after S3Gen, on the audio so far: the model's Perth watermark, then rumble
        removal. (Pause shortening from clean() changes timing and cannot be applied to a stream.)"""
        if not len(wav):
            return wav
        wav = self.model.watermarker.apply_watermark(wav, sample_rate=self.sample_rate).astype(np.float32)
        return _highpass(wav, self.sample_rate, 60.0)


def _highpass(x: np.ndarray, sr: int, cutoff: float) -> np.ndarray:
    try:
        import torch
        import torchaudio.functional as taf

        return taf.highpass_biquad(torch.from_numpy(x.astype(np.float32)), sr, cutoff).numpy()
    except ImportError:  # test environment without torch: one-pole high-pass
        a = math.exp(-2 * math.pi * cutoff / sr)
        y = np.empty_like(x, dtype=np.float32)
        prev_x = prev_y = 0.0
        for i, v in enumerate(x):
            prev_y = a * (prev_y + v - prev_x)
            prev_x = v
            y[i] = prev_y
        return y


_VAD = None


def speech_segments(x: np.ndarray, sr: int) -> list[tuple[int, int]] | None:
    """Speech regions (sample indices) from Silero VAD (MIT), or None when it is not installed (tests)."""
    global _VAD
    try:
        import torch
        import torchaudio.functional as taf
        from silero_vad import get_speech_timestamps, load_silero_vad
    except ImportError:
        return None
    if _VAD is None:
        _VAD = load_silero_vad()
    x16 = taf.resample(torch.from_numpy(x.astype(np.float32)), sr, 16000)
    ts = get_speech_timestamps(x16, _VAD, sampling_rate=16000, threshold=0.5, min_silence_duration_ms=150,
                               speech_pad_ms=40)
    k = sr / 16000
    return [(int(t["start"] * k), min(len(x), int(t["end"] * k))) for t in ts]


def _level_segments(x: np.ndarray, sr: int, rel_db: float = 20.0) -> list[tuple[int, int]]:
    hop = max(1, int(sr * 0.01))
    frames = x[: len(x) // hop * hop].reshape(-1, hop)
    db = 20 * np.log10(np.sqrt((frames.astype(np.float64) ** 2).mean(axis=1)) + 1e-9)
    active = db > np.percentile(db, 95) - rel_db
    segs, start = [], None
    for i, a in enumerate(active):
        if a and start is None:
            start = i
        elif not a and start is not None:
            segs.append((start * hop, i * hop))
            start = None
    if start is not None:
        segs.append((start * hop, len(active) * hop))
    merged: list[tuple[int, int]] = []
    for s0, e0 in segs:  # quiet gaps shorter than 150 ms belong to the speech (unvoiced consonants)
        if merged and s0 - merged[-1][1] < 0.15 * sr:
            merged[-1] = (merged[-1][0], e0)
        else:
            merged.append((s0, e0))
    return merged


def clean(x: np.ndarray, sr: int, *, segments: list[tuple[int, int]] | None = None, lead: float = 0.05,
          tail: float = 0.1, max_pause: float = 0.45, pause_gain_db: float = -30.0) -> np.ndarray:
    """Remove what the model adds around and between words without touching the speech itself.

    Chatterbox leaves up to a second of hiss and breath before and after an utterance and can fill pauses with a
    noise floor (worse when the reference recording has room noise). Speech regions come from a voice activity
    detector (Silero VAD) when installed, otherwise from the utterance's own level. Then: rumble below 60 Hz is
    removed; audio before the first and after the last speech region is cut (short margins, fades); pauses
    between speech regions are lowered by `pause_gain_db` and shortened to at most `max_pause` seconds. The speech
    regions themselves are passed through unchanged.
    """
    if len(x) < sr // 10:
        return x
    x = _highpass(x, sr, 60.0)
    segs = segments if segments is not None else (speech_segments(x, sr) or _level_segments(x, sr))
    if not segs:
        return x
    quiet = np.float32(10 ** (pause_gain_db / 20))
    ramp = int(0.02 * sr)

    def pause(g: np.ndarray) -> np.ndarray:
        if len(g) > max_pause * sr:
            half = int(max_pause * sr / 2)
            g = np.concatenate([g[:half], g[-half:]])
        env = np.full(len(g), quiet, dtype=np.float32)
        r = min(ramp, len(g) // 2)
        if r:
            env[:r] = np.linspace(1, quiet, r)
            env[len(g) - r:] = np.linspace(quiet, 1, r)
        return g * env

    parts = [x[max(0, segs[0][0] - int(lead * sr)): segs[0][0]]]
    for i, (s0, e0) in enumerate(segs):
        parts.append(x[s0:e0])
        if i + 1 < len(segs):
            parts.append(pause(x[e0: segs[i + 1][0]]))
    parts.append(x[segs[-1][1]: min(len(x), segs[-1][1] + int(tail * sr))])
    y = np.concatenate(parts).astype(np.float32)
    fade_in, fade_out = min(len(y), int(0.01 * sr)), min(len(y), int(0.04 * sr))
    y[:fade_in] *= np.linspace(0, 1, fade_in, dtype=np.float32)
    y[len(y) - fade_out:] *= np.linspace(1, 0, fade_out, dtype=np.float32)
    return y


def resample(x: np.ndarray, sr_in: int, sr_out: int) -> np.ndarray:
    if sr_in == sr_out:
        return x
    try:
        import torch
        import torchaudio.functional as taf

        return taf.resample(torch.from_numpy(x), sr_in, sr_out).numpy()
    except ImportError:  # test environment without torch: linear interpolation on the output sample grid
        n = int(round(len(x) * sr_out / sr_in))
        return np.interp(np.arange(n) * (sr_in / sr_out), np.arange(len(x)), x).astype(np.float32)


def to_pcm16(x: np.ndarray) -> bytes:
    return (np.clip(x, -1.0, 1.0) * 32767.0).astype("<i2").tobytes()

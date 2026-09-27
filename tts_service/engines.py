"""Speech engines for the TTS service.

ChatterboxEngine – Chatterbox Multilingual (Resemble AI, MIT code) with Danish (`language_id="da"`), voice given by
reference-clip conditioning. Weights are downloaded from Hugging Face at a pinned commit (MODEL_REVISION) –
never "main". The model applies its built-in Perth watermark to all audio; we keep it.

Chatterbox keeps the active voice in `model.conds` (shared, mutable). The service therefore runs one
generation at a time per model instance under a lock and sets the voice's own cached Conditionals immediately
before each generation, so one customer's voice can never leak into another session.

FakeEngine – a deterministic tone for tests of the service mechanics; results are labelled simulated.
"""
from __future__ import annotations

import hashlib
import math
import threading
from dataclasses import dataclass

import numpy as np

CHATTERBOX_FILES = ["ve.pt", "t3_mtl23ls_v2.safetensors", "s3gen.pt", "grapheme_mtl_merged_expanded_v1.json",
                    "conds.pt", "Cangjie5_TC.json"]


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

    def generate(self, voice: VoiceState, text: str) -> np.ndarray:
        self.current = voice.key
        freq = voice.conds["freq"]
        n = int(self.sample_rate * max(0.3, 0.06 * len(text.split())))
        t = np.arange(n) / self.sample_rate
        assert self.current == voice.key  # the shared state belongs to this request for the whole generation
        return (0.1 * np.sin(2 * math.pi * freq * t)).astype(np.float32)


class ChatterboxEngine:
    name = "chatterbox-multilingual"
    simulated = False
    watermark = "perth"

    def __init__(self, model_repo: str, model_revision: str, device: str, cache_dir: str | None = None):
        if len(model_revision) != 40:
            raise ValueError("MODEL_REVISION must be a full 40-character commit hash")
        self.model_repo, self.model_revision, self.device, self.cache_dir = model_repo, model_revision, device, cache_dir
        self.lock = threading.Lock()
        self.model = None
        self.sample_rate = 24000

    def load(self) -> None:
        from chatterbox.mtl_tts import ChatterboxMultilingualTTS  # heavy import only in the real service
        from huggingface_hub import snapshot_download

        path = snapshot_download(repo_id=self.model_repo, repo_type="model", revision=self.model_revision,
                                 allow_patterns=CHATTERBOX_FILES, cache_dir=self.cache_dir)
        self.model = ChatterboxMultilingualTTS.from_local(path, self.device)
        self.sample_rate = int(self.model.sr)

    def prepare_voice(self, key: str, ref_path: str | None, settings: dict) -> VoiceState:
        if ref_path is None:
            raise ValueError("reference clip required")
        with self.lock:
            self.model.prepare_conditionals(ref_path, exaggeration=float(settings.get("exaggeration", 0.5)))
            conds = self.model.conds
            self.model.conds = None
        return VoiceState(key=key, conds=conds, settings=settings)

    def generate(self, voice: VoiceState, text: str) -> np.ndarray:
        s = voice.settings
        self.model.conds = voice.conds  # caller holds self.lock
        wav = self.model.generate(text, language_id="da", exaggeration=float(s.get("exaggeration", 0.5)),
                                  cfg_weight=float(s.get("cfg_weight", 0.5)), temperature=float(s.get("temperature", 0.8)))
        return wav.squeeze(0).detach().cpu().numpy().astype(np.float32)


def resample(x: np.ndarray, sr_in: int, sr_out: int) -> np.ndarray:
    if sr_in == sr_out:
        return x
    try:
        import torch
        import torchaudio.functional as taf

        return taf.resample(torch.from_numpy(x), sr_in, sr_out).numpy()
    except ImportError:  # test environment without torch: linear interpolation
        n = int(round(len(x) * sr_out / sr_in))
        return np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x).astype(np.float32)


def to_pcm16(x: np.ndarray) -> bytes:
    return (np.clip(x, -1.0, 1.0) * 32767.0).astype("<i2").tobytes()

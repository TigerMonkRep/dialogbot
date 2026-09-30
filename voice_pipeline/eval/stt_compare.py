"""Compare speech-to-text engines on Danish speech as it sounds on a phone line.

    python -m voice_pipeline.eval.stt_compare --dataset fleurs:100 --engine deepgram --engine azure \
        --engine coral --out eval-runs/stt-2026-09-30.json

Datasets (repeatable, each "name[:n]"):
- fleurs      Google FLEURS da_dk test split (real read speech, CC-BY-4.0, no login).
- coral       CoRal read_aloud test split (real Danish speakers incl. dialects; gated: needs HF_TOKEN and the terms
              accepted on huggingface.co/datasets/CoRal-project/coral).
- testset     voice_pipeline/eval/testset_da.jsonl – what a Danish receptionist actually hears (names, numbers,
              addresses) – with audio from --testset-audio (e.g. synthesized clips; label them as synthetic).
- dir:PATH    your own recordings: PATH/*.wav with the reference text in PATH/<same name>.txt (real calls are
              the best test there is).

Every clip is degraded like a phone call before it is sent (--no-phone to skip): 8 kHz, 300–3400 Hz band, G.711
μ-law. Engines:
- deepgram   Nova-3, language=da (DEEPGRAM_API_KEY). With --keyterms FILE also a second run "deepgram+keyterm".
- azure      Speech short-audio REST, da-DK (AZURE_SPEECH_KEY, AZURE_SPEECH_REGION).
- coral      CoRal-project/roest-v3-wav2vec2-315m, local (transformers + torch; CPU works, slowly).
- coral-whisper  CoRal-project/roest-v3-whisper-1.5b, local (a GPU is advisable).

Metrics per engine and dataset: WER and CER after the same Danish normalisation calls use (numbers and dates
spelled out), latency per clip, and "entities caught": digit groups and capitalised names from the reference that
appear in the transcript – the things a receptionist must get right. Keys are read from the environment and never
printed or written to the output.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import re
import statistics
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from app.modules.voices import danish
from voice_pipeline.eval.asr_check import canon, edit_distance

TESTSET = Path(__file__).with_name("testset_da.jsonl")
FLEURS_URL = "https://huggingface.co/datasets/google/fleurs/resolve/main/parquet-data/da_dk/test-00000-of-00001.parquet"
CORAL_URL = "https://huggingface.co/datasets/CoRal-project/coral/resolve/main/read_aloud/test-00000-of-00009.parquet"
CORAL_W2V = "CoRal-project/roest-v3-wav2vec2-315m"
CORAL_WHISPER = "CoRal-project/roest-v3-whisper-1.5b"
SR = 16000


@dataclass
class Clip:
    id: str
    dataset: str
    text: str
    audio: np.ndarray  # float32 mono at 16 kHz


# --------------------------------------------------------------------------- audio

def resample(x: np.ndarray, sr_from: int, sr_to: int) -> np.ndarray:
    if sr_from == sr_to:
        return x.astype(np.float32)
    from math import gcd

    from scipy.signal import resample_poly

    g = gcd(sr_from, sr_to)
    return resample_poly(x, sr_to // g, sr_from // g).astype(np.float32)


def phone_line(x: np.ndarray, sr: int = SR) -> np.ndarray:
    """What the caller's voice looks like after the PSTN: 8 kHz, 300–3400 Hz, μ-law (G.711), back at 16 kHz."""
    from scipy.signal import butter, sosfiltfilt

    y = resample(x, sr, 8000)
    y = sosfiltfilt(butter(6, [300, 3400], btype="bandpass", fs=8000, output="sos"), y)
    peak = float(np.max(np.abs(y))) or 1.0
    y = np.clip(y / peak * 0.9, -1, 1)
    mu = 255.0
    enc = np.sign(y) * np.log1p(mu * np.abs(y)) / np.log1p(mu)
    enc = np.round((enc + 1) / 2 * 255) / 255 * 2 - 1  # 8-bit quantisation
    dec = np.sign(enc) * (np.power(1 + mu, np.abs(enc)) - 1) / mu
    return resample(dec.astype(np.float32), 8000, sr)


def wav_bytes(x: np.ndarray, sr: int = SR) -> bytes:
    import soundfile as sf

    buf = io.BytesIO()
    sf.write(buf, x, sr, subtype="PCM_16", format="WAV")
    return buf.getvalue()


def decode(data: bytes) -> tuple[np.ndarray, int]:
    import soundfile as sf

    x, sr = sf.read(io.BytesIO(data), dtype="float32", always_2d=False)
    if x.ndim > 1:
        x = x.mean(axis=1)
    return x, sr


# --------------------------------------------------------------------------- datasets

def _download(url: str, cache: Path, token: str | None = None) -> Path:
    import httpx

    cache.mkdir(parents=True, exist_ok=True)
    out = cache / url.rsplit("/", 1)[-1]
    if out.exists() and out.stat().st_size > 0:
        return out
    headers = {"authorization": f"Bearer {token}"} if token else {}
    with httpx.stream("GET", url, headers=headers, follow_redirects=True, timeout=300) as r:
        if r.status_code in (401, 403):
            raise SystemExit(f"{url}: adgang nægtet ({r.status_code}). Datasættet kræver HF_TOKEN og accepterede vilkår.")
        r.raise_for_status()
        with open(out, "wb") as f:
            for chunk in r.iter_bytes():
                f.write(chunk)
    return out


def _every(rows: list, n: int) -> list:
    if n >= len(rows):
        return rows
    step = len(rows) / n
    return [rows[int(i * step)] for i in range(n)]  # deterministic spread over the split, no randomness


def load_parquet(url: str, name: str, n: int, cache: Path, text_cols: tuple[str, ...], token: str | None = None) -> list[Clip]:
    import pyarrow.parquet as pq

    table = pq.read_table(_download(url, cache, token)).to_pylist()
    rows = _every(table, n)
    clips = []
    for i, r in enumerate(rows):
        text = next((r[c] for c in text_cols if r.get(c)), "")
        audio = r.get("audio") or {}
        x, sr = decode(audio["bytes"]) if audio.get("bytes") else (np.asarray(audio["array"], dtype=np.float32), audio["sampling_rate"])
        clips.append(Clip(f"{name}-{r.get('id', i)}", name, str(text), resample(x, sr, SR)))
    return clips


def load_testset(n: int, audio_dir: Path | None) -> list[Clip]:
    if audio_dir is None:
        raise SystemExit("testset kræver --testset-audio DIR med <id>.wav (fx syntetiserede klip)")
    clips = []
    for line in TESTSET.read_text().splitlines():
        row = json.loads(line)
        wav = audio_dir / f"{row['id']}.wav"
        if not wav.exists():
            continue
        x, sr = decode(wav.read_bytes())
        # the clip may hold only the first spoken unit of the sentence (the streaming benchmark saved those)
        units = danish.chunks(danish.normalize(row["text"]))
        clips.append(Clip(row["id"], "testset", units[0] if units else row["text"], resample(x, sr, SR)))
    return clips[:n]


def load_dir(path: Path, n: int) -> list[Clip]:
    clips = []
    for wav in sorted(path.glob("*.wav"))[:n]:
        ref = wav.with_suffix(".txt")
        if ref.exists():
            x, sr = decode(wav.read_bytes())
            clips.append(Clip(wav.stem, f"dir:{path.name}", ref.read_text().strip(), resample(x, sr, SR)))
    return clips


# --------------------------------------------------------------------------- engines

class Engine:
    name = "?"

    def transcribe(self, wav: bytes, audio: np.ndarray) -> str:  # pragma: no cover - interface
        raise NotImplementedError


class Deepgram(Engine):
    def __init__(self, keyterms: list[str] | None = None):
        self.key = os.environ.get("DEEPGRAM_API_KEY")
        if not self.key:
            raise SystemExit("DEEPGRAM_API_KEY mangler i miljøet")
        self.keyterms = keyterms or []
        self.name = "deepgram-nova3" + ("+keyterm" if self.keyterms else "")

    def transcribe(self, wav: bytes, audio: np.ndarray) -> str:
        import httpx

        params: list[tuple[str, str]] = [("model", "nova-3"), ("language", "da"), ("smart_format", "false")]
        params += [("keyterm", t) for t in self.keyterms]
        r = httpx.post("https://api.deepgram.com/v1/listen", params=params, content=wav, timeout=60,
                       headers={"authorization": f"Token {self.key}", "content-type": "audio/wav"})
        r.raise_for_status()
        return r.json()["results"]["channels"][0]["alternatives"][0]["transcript"]


class Azure(Engine):
    name = "azure-da-DK"

    def __init__(self):
        self.key, self.region = os.environ.get("AZURE_SPEECH_KEY"), os.environ.get("AZURE_SPEECH_REGION")
        if not (self.key and self.region):
            raise SystemExit("AZURE_SPEECH_KEY og AZURE_SPEECH_REGION mangler i miljøet")

    def transcribe(self, wav: bytes, audio: np.ndarray) -> str:
        import httpx

        url = (f"https://{self.region}.stt.speech.microsoft.com/speech/recognition/conversation/cognitiveservices/v1")
        r = httpx.post(url, params={"language": "da-DK", "format": "simple"}, content=wav, timeout=60,
                       headers={"Ocp-Apim-Subscription-Key": self.key,
                                "content-type": "audio/wav; codecs=audio/pcm; samplerate=16000"})
        r.raise_for_status()
        out = r.json()
        return out.get("DisplayText", "") if out.get("RecognitionStatus") == "Success" else ""


class HFLocal(Engine):
    def __init__(self, model: str, name: str):
        from transformers import pipeline

        self.name = name
        self.pipe = pipeline("automatic-speech-recognition", model=model, device=_device())

    def transcribe(self, wav: bytes, audio: np.ndarray) -> str:
        out = self.pipe({"raw": audio, "sampling_rate": SR})
        return out["text"] if isinstance(out, dict) else str(out)


def _device() -> int:
    try:
        import torch

        return 0 if torch.cuda.is_available() else -1
    except ImportError:
        return -1


def engine(name: str, keyterms: list[str]) -> list[Engine]:
    if name == "deepgram":
        return [Deepgram()] + ([Deepgram(keyterms)] if keyterms else [])
    if name == "azure":
        return [Azure()]
    if name == "coral":
        return [HFLocal(CORAL_W2V, "coral-roest-v3-wav2vec2-315m")]
    if name == "coral-whisper":
        return [HFLocal(CORAL_WHISPER, "coral-roest-v3-whisper-1.5b")]
    raise SystemExit(f"Ukendt engine: {name}")


# --------------------------------------------------------------------------- metrics

def entities(text: str) -> list[str]:
    """Digit groups and capitalised words that are not sentence-initial: phone numbers, amounts, house numbers,
    names, streets and towns. Compared after the same normalisation as the transcripts."""
    out = re.findall(r"\d[\d .]*\d|\d", text)
    words = re.findall(r"(?<![.!?]\s)(?<!^)\b[A-ZÆØÅ][a-zæøå]+(?:[- ][A-ZÆØÅ][a-zæøå]+)*", text.strip())
    return [e.strip() for e in out + words if e.strip()]


def score(reference: str, heard: str) -> dict:
    e, h = canon(reference), canon(heard)
    ec, hc = " ".join(e), " ".join(h)
    ents = entities(reference)
    caught = [x for x in ents if " ".join(canon(x)) and " ".join(canon(x)) in hc]
    return {"wer": edit_distance(e, h) / max(1, len(e)), "cer": edit_distance(list(ec), list(hc)) / max(1, len(ec)),
            "ref_words": len(e), "entities": len(ents), "entities_caught": len(caught),
            "entities_missed": [x for x in ents if x not in caught]}


def summarize(rows: list[dict]) -> dict:
    words = sum(r["ref_words"] for r in rows) or 1
    ents = sum(r["entities"] for r in rows)
    lat = [r["latency_ms"] for r in rows]
    return {"clips": len(rows), "errors": sum(1 for r in rows if r.get("error")),
            "wer": round(sum(r["wer"] * r["ref_words"] for r in rows) / words, 4),  # word-weighted
            "cer": round(statistics.fmean(r["cer"] for r in rows), 4) if rows else None,
            "entities_caught": f"{sum(r['entities_caught'] for r in rows)}/{ents}",
            "entity_rate": round(sum(r["entities_caught"] for r in rows) / ents, 3) if ents else None,
            "latency_ms_p50": int(statistics.median(lat)) if lat else None}


# --------------------------------------------------------------------------- main

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dataset", action="append", required=True, help="fleurs[:n] | coral[:n] | testset[:n] | dir:PATH[:n]")
    ap.add_argument("--engine", action="append", required=True, choices=["deepgram", "azure", "coral", "coral-whisper"])
    ap.add_argument("--keyterms", type=Path, help="one term per line; adds a deepgram+keyterm run")
    ap.add_argument("--testset-audio", type=Path)
    ap.add_argument("--no-phone", action="store_true", help="send studio audio instead of a simulated phone line")
    ap.add_argument("--cache", type=Path, default=Path("var/stt-cache"))
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()

    clips: list[Clip] = []
    for spec in a.dataset:
        if spec.startswith("dir:"):
            path, _, n = spec[4:].partition(":")
            clips += load_dir(Path(path), int(n or 1000))
            continue
        name, _, n = spec.partition(":")
        n = int(n or 100)
        if name == "fleurs":
            clips += load_parquet(FLEURS_URL, "fleurs", n, a.cache, ("raw_transcription", "transcription"))
        elif name == "coral":
            clips += load_parquet(CORAL_URL, "coral", n, a.cache, ("text",), token=os.environ.get("HF_TOKEN"))
        elif name == "testset":
            clips += load_testset(n, a.testset_audio)
        else:
            raise SystemExit(f"Ukendt datasæt: {name}")
    keyterms = [t.strip() for t in a.keyterms.read_text().splitlines() if t.strip()] if a.keyterms else []
    engines = [e for name in a.engine for e in engine(name, keyterms)]
    print(f"{len(clips)} klip, motorer: {', '.join(e.name for e in engines)}, telefonlinje: {not a.no_phone}", flush=True)

    results: dict[str, list[dict]] = {e.name: [] for e in engines}
    for c in clips:
        audio = c.audio if a.no_phone else phone_line(c.audio)
        wav = wav_bytes(audio)
        for e in engines:
            t0 = time.monotonic()
            try:
                heard, err = e.transcribe(wav, audio), None
            except Exception as ex:  # noqa: BLE001 - one failed clip must not stop the comparison
                heard, err = "", f"{type(ex).__name__}: {str(ex)[:200]}"
            row = {"id": c.id, "dataset": c.dataset, "reference": c.text, "heard": heard,
                   "latency_ms": int((time.monotonic() - t0) * 1000), "error": err} | score(c.text, heard)
            results[e.name].append(row)
        print(c.id, " | ".join(f"{e.name}: {results[e.name][-1]['wer']:.2f}" for e in engines), flush=True)

    summary = {e: {ds: summarize([r for r in rows if r["dataset"] == ds]) for ds in sorted({r["dataset"] for r in rows})}
               for e, rows in results.items()}
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps({"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "phone_line": not a.no_phone,
                                 "keyterms": keyterms, "summary": summary, "clips": results},
                                ensure_ascii=False, indent=1))
    print("\n| motor | datasæt | klip | WER | CER | tal og navne fanget | median ms |\n|---|---|---|---|---|---|---|")
    for e, by_ds in summary.items():
        for ds, s in by_ds.items():
            print(f"| {e} | {ds} | {s['clips']} | {s['wer']:.1%} | {s['cer']:.1%} | {s['entities_caught']} | {s['latency_ms_p50']} |")


if __name__ == "__main__":
    main()

"""The Danish test manifest (tests/fixtures/stemmetest/manifest.json) and the audio that goes with it.

A case without audio is not a failure and not a result: it is listed as `mangler_optagelse` until audio exists.
Audio is looked up, in order: a human recording at `<STEMMETEST_AUDIO_DIR>/<id>.wav`, then
tests/fixtures/stemmetest/audio/<id>.wav, then the case's own `audio` path (repo-relative – synthetic ElevenLabs
stand-ins in tests/fixtures/stemmetest/synthetic/, 8 kHz phone band). A human recording therefore replaces its
synthetic stand-in without touching the manifest; `is_synthetic` says which one a result came from. Cases may carry
`reference_alts` (the same sentence with figures written as digits) – the scorer takes the closest, so a recogniser is
not punished for writing "2.495" where the speaker said the words. Mono 16-bit WAV, as recorded; nothing is
up-sampled to look better than the phone line it came from.
"""
from __future__ import annotations

import json
import wave
from functools import lru_cache
from pathlib import Path

from app.config import get_settings

ROOT = Path(__file__).resolve().parents[3]
MANIFEST = ROOT / "tests" / "fixtures" / "stemmetest" / "manifest.json"
DEFAULT_AUDIO = ROOT / "tests" / "fixtures" / "stemmetest" / "audio"

# Company words the production vocabulary would hold from the approved knowledge (names of places and businesses).
# Deliberately NOT per-case answers: no phone numbers, mails, times, counts or reference sentences.
COMPANY_TERMS = ["Gastro Hall", "Racehall", "Dialogbot", "Aarhus", "Viby", "Højbjerg", "Berle Pool", "Fjord Gulvservice"]


@lru_cache(maxsize=1)
def load() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def cases() -> list[dict]:
    return load()["cases"]


def scenarios() -> list[dict]:
    return load()["scenarios"]


def get(case_id: str) -> dict | None:
    return next((c for c in [*cases(), *scenarios()] if c["id"] == case_id), None)


def audio_path(case: dict) -> Path | None:
    """A human recording (STEMMETEST_AUDIO_DIR, then audio/<ID>.wav) always wins over the case's own `audio` file, so a
    synthetic stand-in is replaced just by dropping the real recording next to it – no manifest change."""
    cand: list[Path] = []
    d = get_settings().stemmetest_audio_dir
    if d:
        cand.append(Path(d) / f'{case["id"]}.wav')
    cand.append(DEFAULT_AUDIO / f'{case["id"]}.wav')
    if case.get("audio"):
        cand.append(ROOT / case["audio"])
    return next((p for p in cand if p.is_file()), None)


def is_synthetic(case: dict) -> bool:
    """True only while the file actually used is the case's synthetic stand-in (not once a human recording replaces it)."""
    own = case.get("audio")
    return bool(case.get("synthetic") and own and audio_path(case) == ROOT / own)


def status(case: dict) -> str:
    if case["kind"] == "scenarie":
        return "kræver_levende_samtale"
    return "klar" if audio_path(case) else "mangler_optagelse"


def read_wav(path: Path) -> tuple[bytes, int]:
    """(16-bit mono PCM, sample rate). Stereo is down-mixed; other sample widths are refused, not guessed."""
    import array

    with wave.open(str(path), "rb") as w:
        if w.getsampwidth() != 2:
            raise ValueError("kun 16-bit WAV understøttes")
        rate, ch, frames = w.getframerate(), w.getnchannels(), w.readframes(w.getnframes())
    if ch > 1:
        s = array.array("h")
        s.frombytes(frames[: len(frames) - len(frames) % (2 * ch)])
        mono = array.array("h", (sum(s[i:i + ch]) // ch for i in range(0, len(s), ch)))
        frames = mono.tobytes()
    return frames, rate


def vocabulary(limit: int = 300) -> list[dict]:
    """The one short dictionary every profile gets: company terms first (so a small cap such as ElevenLabs' 50 keyterms
    still holds them), then the most common Danish names. Adapter limits are recorded in the run, not hidden."""
    from app.modules.telephony import danish_names

    out = [{"content": t} for t in COMPANY_TERMS]
    seen = {t.lower() for t in COMPANY_TERMS}
    for v in danish_names.vocabulary(limit):
        if v["content"].lower() not in seen:
            seen.add(v["content"].lower())
            out.append({"content": v["content"], **({"sounds_like": v["soundsLike"]} if v.get("soundsLike") else {})})
    return out[:limit]


def overview() -> dict:
    cs = cases()
    return {"timezone": load().get("timezone"), "note": load().get("note"),
            "counts": {"kort": len(cs), "med_lyd": sum(1 for c in cs if audio_path(c)),
                       "tuning": sum(1 for c in cs if c["split"] == "tuning"),
                       "final": sum(1 for c in cs if c["split"] == "final"), "scenarier": len(scenarios())},
            "cases": [{"id": c["id"], "group": c["group"], "split": c["split"], "text": c["text"],
                       "status": status(c), "synthetic": is_synthetic(c), "note": c.get("note"),
                       "audio_rate": c.get("audio_rate")} for c in cs],
            "scenarios": [{"id": s["id"], "title": s["title"], "script": s["script"],
                           "expected_action": s["expected_action"], "tool_fault": s.get("tool_fault"),
                           "status": status(s)} for s in scenarios()]}

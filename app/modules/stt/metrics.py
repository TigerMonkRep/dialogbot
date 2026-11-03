"""Measurements for the recogniser comparison. Definitions follow the base prompt:

- Ordfejl: WER on the RAW finished recogniser text against the human-checked reference, after one documented Danish
  normalisation (the same one calls use: numbers, dates and times spelled out, case and punctuation dropped).
- Vigtige oplysninger: correct name / phone number / date / time / count, counted per type as hits/total. A hit means
  the expected value (in any listed spoken form) occurs as a whole-word run in the normalised transcript – a wrong
  time or a wrong digit is a miss, however nice the rest of the sentence looks.
- Timing: median and p95 WITH the sample size; fewer than 20 samples is flagged as uncertain, never hidden.

No composite quality score exists on purpose: hidden weights would hide a wrong phone number behind a fast answer.
"""
from __future__ import annotations

import json
import math
import re
import statistics

from app.modules.voices import danish

SMALL_SAMPLE = 20


def canon(text: str) -> list[str]:
    t = danish.normalize(text or "").lower()
    t = re.sub(r"[^\wæøå@ ]+", " ", t)
    return t.split()


def edit_distance(a: list, b: list) -> int:
    prev = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        cur = [i]
        for j, y in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (x != y)))
        prev = cur
    return prev[-1]


def wer(reference: str, hypothesis: str) -> dict:
    ref, hyp = canon(reference), canon(hypothesis)
    errors = edit_distance(ref, hyp)
    return {"errors": errors, "ref_words": len(ref), "wer": round(errors / len(ref), 4) if ref else None}


def _contains(haystack: list[str], needle: list[str]) -> bool:
    n = len(needle)
    return bool(n) and any(haystack[i:i + n] == needle for i in range(len(haystack) - n + 1))


def entities(expected: list[dict], transcript: str) -> dict:
    """expected: [{"type": "telefon", "value": "20 30 40 50", "alt": ["tyve tredive fyrre halvtreds"]}] →
    {"by_type": {type: {"hits": n, "total": m}}, "missed": [...]}."""
    hay = canon(transcript)
    by: dict[str, dict] = {}
    missed = []
    for e in expected or []:
        forms = [e["value"], *e.get("alt", [])]
        ok = any(_contains(hay, canon(f)) for f in forms)
        slot = by.setdefault(e["type"], {"hits": 0, "total": 0})
        slot["total"] += 1
        slot["hits"] += int(ok)
        if not ok:
            missed.append({"type": e["type"], "value": e["value"]})
    return {"by_type": by, "missed": missed}


def stats(values: list[float]) -> dict:
    vals = sorted(v for v in values if v is not None)
    if not vals:
        return {"n": 0, "median": None, "p95": None, "uncertain": True}
    p95 = vals[min(len(vals) - 1, math.ceil(0.95 * len(vals)) - 1)]
    return {"n": len(vals), "median": round(statistics.median(vals), 3), "p95": round(p95, 3),
            "uncertain": len(vals) < SMALL_SAMPLE}


def price(adapter_id: str, audio_seconds: float, prices_json: str | None) -> dict:
    """Cost from audio seconds × the operator's own price list (STEMMETEST_PRICES_JSON). No list → no number."""
    try:
        table = json.loads(prices_json) if prices_json else {}
    except ValueError:
        table = {}
    per_hour = table.get(adapter_id)
    if per_hour is None:
        return {"audio_seconds": round(audio_seconds, 2), "usd": None, "note": "pris ikke angivet"}
    return {"audio_seconds": round(audio_seconds, 2), "usd": round(audio_seconds / 3600 * float(per_hour), 5),
            "note": "estimat: lydsekunder × egen prisliste; STT alene (ikke LLM/TTS/telefoni)"}


def aggregate(results: list[dict]) -> dict:
    """Roll finished case results (each with `wer` and `entities`) up to one profile row, with the denominators."""
    errs = sum(r["wer"]["errors"] for r in results if r.get("wer"))
    words = sum(r["wer"]["ref_words"] for r in results if r.get("wer"))
    by: dict[str, dict] = {}
    for r in results:
        for t, v in ((r.get("entities") or {}).get("by_type") or {}).items():
            slot = by.setdefault(t, {"hits": 0, "total": 0})
            slot["hits"] += v["hits"]
            slot["total"] += v["total"]
    return {"cases": len(results), "wer": round(errs / words, 4) if words else None, "errors": errs, "ref_words": words,
            "entities": by,
            "first_final_s": stats([r["timing"].get("first_final_s") for r in results if r.get("timing")]),
            "final_after_audio_s": stats([r["timing"].get("final_after_audio_s") for r in results if r.get("timing")]),
            "turn_end_after_audio_s": stats([r["timing"].get("turn_end_after_audio_s") for r in results if r.get("timing")])}

"""Quality control of imported clips. Flags – never edits – so a person can review.

    python -m voice_pipeline.qc --import-dir /data/coral-tts

Per clip: empty/too short/too long, clipping, long internal silence, leading/trailing silence, noise floor,
duplicate text or audio within a speaker, and a heuristic for non-Danish text. Transcript accuracy cannot be
verified without an ASR pass; such clips are marked `transcript: unverified` rather than assumed correct.
Writes <import-dir>/qc.jsonl and prints a summary per speaker.
"""
from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path

DANISH_HINTS = set("æøå") | {"og", "det", "er", "en", "at", "jeg", "på", "ikke", "som", "med", "har", "til", "af", "den",
                             "for", "de", "vi", "du", "kan", "var", "om", "så", "men", "der"}
ENGLISH_HINTS = {"the", "and", "is", "you", "that", "with", "have", "this", "for", "are", "was", "what"}


def frame_db(x, sr, ms=25):
    import numpy as np

    n = max(1, int(sr * ms / 1000))
    frames = x[: len(x) // n * n].reshape(-1, n) if len(x) >= n else x.reshape(1, -1)
    rms = np.sqrt((frames.astype("float64") ** 2).mean(axis=1) + 1e-12)
    return 20 * np.log10(rms + 1e-12), ms / 1000


def language_flag(text: str) -> str | None:
    words = re.findall(r"[a-zæøå]+", text.lower())
    if not words:
        return "empty_text"
    da = sum(1 for w in words if w in DANISH_HINTS) + sum(1 for c in text.lower() if c in "æøå")
    en = sum(1 for w in words if w in ENGLISH_HINTS)
    return "possibly_not_danish" if en > da else None


def analyse(wav_path: Path, text: str) -> dict:
    import numpy as np
    import soundfile as sf

    x, sr = sf.read(wav_path, dtype="float32")
    flags = []
    dur = len(x) / sr if sr else 0
    if len(x) == 0 or dur < 0.5:
        flags.append("empty_or_too_short")
        return {"duration": dur, "flags": flags}
    if dur > 30:
        flags.append("too_long")
    clip_ratio = float((np.abs(x) >= 0.999).mean())
    if clip_ratio > 0.001:
        flags.append("clipping")
    db, step = frame_db(x, sr)
    silent = db < -45
    lead = int(np.argmax(~silent)) * step if (~silent).any() else dur
    trail = int(np.argmax(~silent[::-1])) * step if (~silent).any() else dur
    run, longest = 0, 0
    for s in silent:
        run = run + 1 if s else 0
        longest = max(longest, run)
    if lead > 1.0 or trail > 1.5:
        flags.append("long_edge_silence")
    if longest * step > 1.5:
        flags.append("long_internal_silence")
    noise_floor = float(np.percentile(db, 5))  # quietest frames ≈ pauses between words
    if noise_floor > -45:
        flags.append("noisy")
    if (lf := language_flag(text)):
        flags.append(lf)
    return {"duration": round(dur, 3), "clip_ratio": round(clip_ratio, 5), "noise_floor_db": round(noise_floor, 1),
            "lead_silence": round(lead, 2), "trail_silence": round(trail, 2), "longest_silence": round(longest * step, 2),
            "flags": flags, "transcript": "unverified"}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--import-dir", required=True, type=Path)
    args = ap.parse_args(argv)
    root = args.import_dir
    rows = [json.loads(x) for x in (root / "manifest.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
    seen_text, seen_audio = defaultdict(dict), defaultdict(dict)
    summary = defaultdict(lambda: defaultdict(int))
    with (root / "qc.jsonl").open("w", encoding="utf-8") as out:
        for r in rows:
            if "error" in r:
                continue
            res = analyse(root / r["wav"], r["text"])
            key = re.sub(r"\W+", " ", r["text"].lower()).strip()
            if key and key in seen_text[r["speaker"]]:
                res["flags"].append("duplicate_text")
            if r["original_sha256"] in seen_audio[r["speaker"]]:
                res["flags"].append("duplicate_audio")
            seen_text[r["speaker"]][key] = r["id"]
            seen_audio[r["speaker"]][r["original_sha256"]] = r["id"]
            out.write(json.dumps({"id": r["id"], "speaker": r["speaker"], **res}, ensure_ascii=False) + "\n")
            summary[r["speaker"]]["clips"] += 1
            summary[r["speaker"]]["clean"] += not res["flags"]
            for f in res["flags"]:
                summary[r["speaker"]][f] += 1
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

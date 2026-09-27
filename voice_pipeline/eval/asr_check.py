"""Automatic intelligibility check: transcribe synthesized clips with Whisper and compare with what should be said.

    python -m voice_pipeline.eval.asr_check --run eval-runs/coral-tts-a [--run ...] --out asr.json
    python -m voice_pipeline.eval.asr_check --human /data/coral-tts:20 --out asr-human.json   # baseline

Both the expected text and the transcript go through the same Danish normaliser as calls (numbers, dates, amounts
spelled out), then lower-case without punctuation, so "1.495 kr." and "et tusind fire hundrede og femoghalvfems
kroner" compare equal. Reports word and character error rate per clip, per category and overall, and whether every
`must_say` phrase was heard. The baseline on original recordings shows how much of the error is Whisper's own.

This is a proxy. It never replaces the blind listening test with Danish raters, and it says nothing about
naturalness. Model: openai/whisper-large-v3-turbo (MIT) at a pinned revision.
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import time
from pathlib import Path

from app.modules.voices import danish

MODEL = "openai/whisper-large-v3-turbo"
REVISION = "41f01f3fe87f28c78e2fbf8b568835947dd65ed9"
TESTSET = Path(__file__).with_name("testset_da.jsonl")


def canon(text: str) -> list[str]:
    t = danish.normalize(text).lower()
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


def compare(expected: str, heard: str, must_say: list[str]) -> dict:
    e, h = canon(expected), canon(heard)
    ec, hc = " ".join(e), " ".join(h)
    return {"wer": round(edit_distance(e, h) / max(1, len(e)), 3),
            "cer": round(edit_distance(list(ec), list(hc)) / max(1, len(ec)), 3),
            "must_say_missing": [m for m in must_say if " ".join(canon(m)) not in hc]}


def load16k(path: Path):
    import librosa

    x, _ = librosa.load(str(path), sr=16000, mono=True)
    return {"raw": x, "sampling_rate": 16000}


def summary(rows: list[dict]) -> dict:
    def agg(rs):
        return {"clips": len(rs), "wer_mean": round(statistics.mean(r["wer"] for r in rs), 3),
                "cer_mean": round(statistics.mean(r["cer"] for r in rs), 3),
                "wer_median": round(statistics.median(r["wer"] for r in rs), 3),
                "clips_wer_over_20pct": sum(r["wer"] > 0.2 for r in rs),
                "must_say_missing": sum(len(r["must_say_missing"]) for r in rs)}
    cats = sorted({r.get("category", "-") for r in rows})
    return {"overall": agg(rows), "by_category": {c: agg([r for r in rows if r.get("category", "-") == c]) for c in cats}}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", action="append", default=[], type=Path)
    ap.add_argument("--human", help="<import-dir>:<clips per speaker> – original recordings as baseline")
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--device", default="cpu")
    args = ap.parse_args(argv)
    import torch
    from transformers import pipeline

    asr = pipeline("automatic-speech-recognition", model=MODEL, revision=REVISION, device=args.device,
                   torch_dtype=torch.float32)
    gen = {"language": "danish", "task": "transcribe"}
    testset = {r["id"]: r for r in map(json.loads, TESTSET.read_text(encoding="utf-8").splitlines()) if r}
    report: dict = {"model": MODEL, "revision": REVISION, "runs": {}}
    jobs: list[tuple[str, list[tuple[Path, dict]]]] = []
    for run in args.run:
        rows = [json.loads(x) for x in (run / "results.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
        jobs.append((run.name, [(run / f"{r['id']}.wav", testset.get(r["id"], r)) for r in rows
                                if (run / f"{r['id']}.wav").exists()]))
    if args.human:
        import random

        from voice_pipeline.eval.listening_test import _human_clips

        import_dir, n = args.human.rsplit(":", 1)
        clips = _human_clips(Path(import_dir), int(n), random.Random(7))
        jobs.append(("human-reference", [(c["path"], {"id": c["sentence"], "text": c["text"], "must_say": []})
                                         for c in clips]))
    for name, items in jobs:
        rows = []
        t0 = time.monotonic()
        for path, ref in items:
            heard = asr(load16k(path), generate_kwargs=gen)["text"].strip()
            rows.append({"id": ref["id"], "category": ref.get("category", "-"), "expected": ref["text"], "heard": heard}
                        | compare(ref["text"], heard, ref.get("must_say", [])))
        report["runs"][name] = {"summary": summary(rows), "seconds": round(time.monotonic() - t0), "clips": rows}
        print(name, json.dumps(report["runs"][name]["summary"]["overall"], ensure_ascii=False))
    args.out.write_text(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

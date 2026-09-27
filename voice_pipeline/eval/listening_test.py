"""Blind listening test for Danish raters, and scoring of the returned answers.

    # 1) build: pick N sentences per candidate, shuffle, anonymise
    python -m voice_pipeline.eval.listening_test build --run coral-a=eval-runs/a --run coral-b=eval-runs/b \
        --per-candidate 20 --out listening/2026-10
    #   add --human <import-dir>:4 to mix original recordings in as a blind anchor
    # → listening/2026-10/index.html (page: audio, 1–5 ACR scales, answers copied as CSV text)
    #   listening/2026-10/key.json   (which clip is which candidate – keep away from raters)
    # 2) score: after ≥3 raters have sent their CSV files
    python -m voice_pipeline.eval.listening_test score --dir listening/2026-10 answers/*.csv

Scales 1–5 (ACR, ITU-T P.800): forståelighed, naturlighed, stemmestabilitet. Every clip is resampled to 24 kHz and
loudness-matched, and each rater gets their own random order. Raters state whether Danish is their first language;
only those count towards the ≥3 Danish raters goal. Critical error = a wrong date, number, amount, negation or booking status. The score
command prints per-candidate means and the evidence JSON for the operator check `listening_test`. It never
invents ratings; missing raters stay missing.
"""
from __future__ import annotations

import argparse
import csv
import html
import json
import random
import statistics
from pathlib import Path

SCALES = ("forstaaelighed", "naturlighed", "stabilitet", "dialekt")
LABELS = {"forstaaelighed": "Forståelighed", "naturlighed": "Naturlighed", "stabilitet": "Stemmestabilitet",
          "dialekt": "Dialekt (kun hvis du selv taler den)"}


PAGE = Path(__file__).with_name("listening_page.html")
TARGET_SR = 24000
TARGET_DBFS = -23.0


def _prepare(src: Path, dst: Path) -> None:
    """Same sample rate and loudness for every clip, so neither gives a candidate away."""
    import numpy as np
    import soundfile as sf

    x, sr = sf.read(str(src), dtype="float32", always_2d=True)
    x = x.mean(axis=1)
    if sr != TARGET_SR:
        n = int(round(len(x) * TARGET_SR / sr))
        try:
            import librosa

            x = librosa.resample(x, orig_sr=sr, target_sr=TARGET_SR)
        except ImportError:  # linear fallback (tests)
            x = np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x).astype("float32")
    rms = float(np.sqrt(np.mean(x.astype("float64") ** 2)) + 1e-12)
    x = x * (10 ** (TARGET_DBFS / 20) / rms)
    peak = float(np.max(np.abs(x)) + 1e-12)
    if peak > 0.97:
        x = x * (0.97 / peak)
    sf.write(str(dst), x.astype("float32"), TARGET_SR, subtype="PCM_16")


def _human_clips(import_dir: Path, per_speaker: int, rng: random.Random) -> list[dict]:
    """Original recordings as a blind anchor: QC-clean, 3–12 s, never a clip used as a voice reference."""
    manifest = [json.loads(x) for x in (import_dir / "manifest.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
    flags = {}
    if (import_dir / "qc.jsonl").exists():
        flags = {q["id"]: q["flags"] for q in map(json.loads, (import_dir / "qc.jsonl").read_text().splitlines()) if q}
    refs = Path(__file__).resolve().parents[1] / "references" / "coral-tts.json"
    used = {c["id"] for s in json.loads(refs.read_text())["speakers"].values() for c in s} if refs.exists() else set()
    out = []
    for spk in sorted({r["speaker"] for r in manifest if "wav" in r}):
        pool = [r for r in manifest if r.get("speaker") == spk and "wav" in r and not flags.get(r["id"])
                and 3 <= r["duration"] <= 12 and r["id"] not in used and len(r["text"].split()) >= 4]
        out += [{"path": import_dir / r["wav"], "text": r["text"], "sentence": r["id"], "speaker": spk}
                for r in rng.sample(pool, min(per_speaker, len(pool)))]
    return out


def build(runs: list[str], per: int, out: Path, seed: int, human: str | None = None, test_id: str | None = None) -> None:
    rng = random.Random(seed)
    out.mkdir(parents=True, exist_ok=True)
    (out / "audio").mkdir(exist_ok=True)
    items, key = [], {}

    def add(src: Path, text: str, meta: dict) -> None:
        clip = f"k{rng.randrange(16**8):08x}"
        _prepare(src, out / "audio" / f"{clip}.wav")
        key[clip] = meta
        items.append({"clip": clip, "text": text, "src": f"audio/{clip}.wav"})

    for spec in runs:
        name, path = spec.split("=", 1)
        rows = [json.loads(x) for x in (Path(path) / "results.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
        rows = [r for r in rows if (Path(path) / f"{r['id']}.wav").exists()]
        for r in rng.sample(rows, min(per, len(rows))):
            add(Path(path) / f"{r['id']}.wav", r["text"], {"candidate": name, "sentence": r["id"],
                                                          "simulated": r.get("simulated")})
    if human:
        import_dir, n = human.rsplit(":", 1)
        for h in _human_clips(Path(import_dir), int(n), rng):
            add(h["path"], h["text"], {"candidate": "human-reference", "sentence": h["sentence"],
                                       "speaker": h["speaker"], "simulated": False})
    rng.shuffle(items)  # each rater's page shuffles again; this only hides build order
    test_id = test_id or out.name
    (out / "key.json").write_text(json.dumps({"test_id": test_id, "clips": key}, indent=2, ensure_ascii=False))
    page = PAGE.read_text(encoding="utf-8")
    page = page.replace("/*ITEMS*/[]", json.dumps(items, ensure_ascii=False)).replace("/*TEST_ID*/", html.escape(test_id))
    (out / "index.html").write_text(page, encoding="utf-8")
    print(f"{len(items)} clips → {out / 'index.html'} (key: {out / 'key.json'} – keep it away from raters)")


def score(directory: Path, files: list[Path]) -> dict:
    key = json.loads((directory / "key.json").read_text())
    key = key.get("clips", key)
    per: dict = {}
    native: dict[str, str] = {}
    rows = []
    for f in files:
        with f.open(encoding="utf-8") as fh:
            rows += list(csv.DictReader(fh))
    for row in rows:
        if row["clip"] == "_rater" and row["field"] == "native":
            native[row["rater"]] = row["value"]
    for row in rows:
        meta = key.get(row["clip"])
        if meta is None:
            continue
        c = per.setdefault(meta["candidate"], {s: [] for s in SCALES} | {"kritisk": 0, "raters": set(),
                                                                          "simulated": bool(meta.get("simulated"))})
        c["raters"].add(row["rater"])
        if row["field"] in SCALES and row["value"]:
            c[row["field"]].append(int(row["value"]))
        elif row["field"] == "kritisk":
            c["kritisk"] += 1
    out = {}
    for name, c in per.items():
        danish = sum(1 for r in c["raters"] if native.get(r) == "ja")
        means = {s: round(statistics.mean(c[s]), 2) if c[s] else None for s in SCALES}
        out[name] = {"raters": len(c["raters"]), "intelligibility": means["forstaaelighed"],
                     "naturalness": means["naturlighed"], "stability": means["stabilitet"], "dialect": means["dialekt"],
                     "danish_native_raters": danish,
                     "critical_errors": c["kritisk"], "simulated_audio": c["simulated"],
                     "meets_goal": (danish >= 3 and (means["forstaaelighed"] or 0) >= 4
                                    and (means["naturlighed"] or 0) >= 4 and c["kritisk"] == 0 and not c["simulated"])}
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--run", action="append", required=True)
    b.add_argument("--per-candidate", type=int, default=20)
    b.add_argument("--out", required=True, type=Path)
    b.add_argument("--seed", type=int, default=2026)
    b.add_argument("--human", help="<import-dir>:<clips per speaker> – original recordings as a blind anchor")
    b.add_argument("--test-id")
    s = sub.add_parser("score")
    s.add_argument("--dir", required=True, type=Path)
    s.add_argument("files", nargs="+", type=Path)
    args = ap.parse_args(argv)
    if args.cmd == "build":
        build(args.run, args.per_candidate, args.out, args.seed, args.human, args.test_id)
    else:
        print(json.dumps(score(args.dir, args.files), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

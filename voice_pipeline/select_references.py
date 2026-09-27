"""Choose clean Danish reference clips per speaker for Chatterbox conditioning and record the choice.

    python -m voice_pipeline.select_references --import-dir /data/coral-tts --per-speaker 5

Rules (Chatterbox Multilingual uses up to ~10 s of the reference for the decoder and ~6 s for the speech
prompt): 6–12 s long, no QC flags, lowest noise floor first, different sentences. Clips reserved for the
test split (voice_pipeline/eval) are never used as references. The result is written to
voice_pipeline/references/coral-tts.json (committed): ids, checksums and source rows only – no audio.
The first clip per speaker is the primary reference used by the service; the rest are alternates for
evaluation. Choosing references is conditioning, not fine-tuning.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent / "references" / "coral-tts.json"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--import-dir", required=True, type=Path)
    ap.add_argument("--per-speaker", type=int, default=5)
    ap.add_argument("--exclude", type=Path, help="ids reserved for test/validation (one per line)")
    args = ap.parse_args(argv)
    root = args.import_dir
    manifest = {r["id"]: r for r in map(json.loads, (root / "manifest.jsonl").read_text(encoding="utf-8").splitlines()) if "id" in r}
    qc = [json.loads(x) for x in (root / "qc.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
    excluded = set(args.exclude.read_text().split()) if args.exclude else set()
    summary = json.loads((root / "import_summary.json").read_text())
    by_speaker: dict[str, list] = {}
    for q in qc:
        if q["flags"] or q["id"] in excluded or not (6.0 <= q["duration"] <= 12.0):
            continue
        by_speaker.setdefault(q["speaker"], []).append(q)
    chosen = {}
    for spk, items in sorted(by_speaker.items()):
        items.sort(key=lambda q: q["noise_floor_db"])
        picked, texts = [], set()
        for q in items:
            m = manifest[q["id"]]
            if m["text"] in texts:
                continue
            texts.add(m["text"])
            picked.append({"id": q["id"], "wav": m["wav"], "wav_sha256": m["wav_sha256"], "duration": q["duration"],
                           "noise_floor_db": q["noise_floor_db"], "source_file": m["source_file"], "row": m["row"],
                           "sample_rate": m["sample_rate"]})
            if len(picked) >= args.per_speaker:
                break
        chosen[spk] = picked
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"dataset": "CoRal-project/coral-tts", "revision": summary["revision"],
                               "rule": "6–12 s, no QC flags, lowest noise floor, distinct sentences, not in test split",
                               "speakers": chosen}, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({k: len(v) for k, v in chosen.items()}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

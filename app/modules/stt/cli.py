"""Run the Stemmetest from the terminal, without the database or the web page.

    python -m app.modules.stt.cli                         # every profile with access × every case with audio
    python -m app.modules.stt.cli --profile E --profile F --case S03 --mode natural --out run.json

Keys come from the environment (SPEECHMATICS_API_KEY, SONIOX_API_KEY, ELEVENLABS_API_KEY) and are never printed. A profile
without a key is listed as 'mangler adgang'; nothing is invented. Audio is replayed in real time, so this takes about as
long as the recordings last.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://unused@localhost/unused")  # settings need it; the CLI never connects

from app.modules.stt import manifest, metrics, profiles, replay


async def main_async(args) -> dict:
    chosen = [profiles.BY_ID[p] for p in (args.profile or [p.id for p in profiles.PROFILES]) if p in profiles.BY_ID]
    cases = [c for c in manifest.cases() if (not args.case or c["id"] in args.case) and manifest.audio_path(c)
             and (not args.split or c["split"] == args.split)]
    out: dict = {"mode": args.mode, "profiles": {}, "missing_access": {}, "not_replayable": [p.id for p in chosen if p.adapter is None],
                 "cases_without_audio": sum(1 for c in manifest.cases() if not manifest.audio_path(c))}
    vocab = manifest.vocabulary()
    for p in chosen:
        acc = profiles.access(p)
        if p.adapter is None:
            continue
        if acc["status"] != "klar":
            out["missing_access"][p.id] = acc["reason"]
            continue
        results = []
        for c in cases:
            pcm, rate = manifest.read_wav(manifest.audio_path(c))
            r = await replay.run_audio(p, pcm, rate, reference=c["text"], expected=c["entities"], vocabulary=vocab, mode=args.mode,
                                       reference_alts=c.get("reference_alts"))
            r["case"] = c["id"]
            r["synthetic"] = manifest.is_synthetic(c)
            results.append(r)
            print(f'{p.id} {c["id"]}: {r["status"]} wer={r.get("wer", {}).get("wer")} "{r.get("transcript_raw", r.get("error"))}"',
                  file=sys.stderr)
        out["profiles"][p.id] = {"aggregate": metrics.aggregate([r for r in results if r["status"] == "ok"]), "runs": results}
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--profile", action="append")
    ap.add_argument("--case", action="append")
    ap.add_argument("--split", choices=["tuning", "final"])
    ap.add_argument("--mode", choices=["controlled", "natural"], default="controlled")
    ap.add_argument("--out")
    args = ap.parse_args()
    res = asyncio.run(main_async(args))
    text = json.dumps(res, ensure_ascii=False, indent=1)
    if args.out:
        open(args.out, "w", encoding="utf-8").write(text)
    for pid, v in res["profiles"].items():
        a = v["aggregate"]
        print(f'{pid}: {a["cases"]} cases, ordfejl {a["wer"]}, vigtige oplysninger {a["entities"]}')
    for pid, why in res["missing_access"].items():
        print(f"{pid}: mangler adgang – {why}")
    print(f'{res["cases_without_audio"]} cases mangler stadig en menneskeindtalt optagelse', file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

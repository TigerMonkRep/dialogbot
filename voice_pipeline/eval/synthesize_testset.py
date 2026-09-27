"""Synthesize the Danish test set with one candidate voice through the real TTS service.

    python -m voice_pipeline.eval.synthesize_testset --voice voice.json --tts-url https://tts... \
        --token $TTS_SERVICE_TOKEN --out eval-runs/coral-tts-a-v1

voice.json is the `voice` object the API sends (version_id, engine, model_repo, model_revision, references,
settings) – print it with `GET /api/v1/operator/voices`. Every sentence is normalised exactly like in calls
(app.modules.voices.danish) and synthesised unit by unit. Writes <out>/<id>.wav and <out>/results.jsonl with
text, spoken form, expected meaning, audio seconds, synthesis ms per unit and real-time factor.
Test sentences are never used as references or for tuning.
"""
from __future__ import annotations

import argparse
import json
import time
import uuid
import wave
from pathlib import Path

import httpx

from app.modules.voices import danish

TESTSET = Path(__file__).with_name("testset_da.jsonl")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--voice", required=True, type=Path)
    ap.add_argument("--tts-url", required=True)
    ap.add_argument("--token", required=True)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--sample-rate", type=int, default=24000)
    ap.add_argument("--limit", type=int)
    ap.add_argument("--resume", action="store_true", help="keep clips already in --out and synthesize the rest")
    args = ap.parse_args(argv)
    voice = json.loads(args.voice.read_text())
    rows = [json.loads(x) for x in TESTSET.read_text(encoding="utf-8").splitlines() if x.strip()][: args.limit]
    args.out.mkdir(parents=True, exist_ok=True)
    h = {"authorization": f"Bearer {args.token}"}
    done = set()
    if args.resume and (args.out / "results.jsonl").exists():
        done = {json.loads(x)["id"] for x in (args.out / "results.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()}
    mode = "a" if args.resume else "w"
    with httpx.Client(timeout=900) as c, (args.out / "results.jsonl").open(mode, encoding="utf-8") as res:
        info = c.get(f"{args.tts_url}/ready", headers=h).json()
        for r in rows:
            if r["id"] in done:
                continue
            spoken = danish.normalize(r["text"])
            pcm, unit_ms = b"", []
            t0 = time.monotonic()
            first_ms = None
            for unit in danish.chunks(spoken):
                t = time.monotonic()
                resp = c.post(f"{args.tts_url}/v1/synthesize", headers=h, json={
                    "voice": voice, "text": unit, "language": "da", "format": "pcm_s16le",
                    "sample_rate": args.sample_rate, "request_id": uuid.uuid4().hex})
                resp.raise_for_status()
                unit_ms.append(int((time.monotonic() - t) * 1000))
                first_ms = first_ms if first_ms is not None else unit_ms[0]
                pcm += resp.content
            total_ms = int((time.monotonic() - t0) * 1000)
            seconds = len(pcm) / 2 / args.sample_rate
            with wave.open(str(args.out / f"{r['id']}.wav"), "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(args.sample_rate)
                w.writeframes(pcm)
            res.write(json.dumps(r | {"spoken": spoken, "audio_seconds": round(seconds, 2), "first_unit_ms": first_ms,
                                      "total_ms": total_ms, "unit_ms": unit_ms,
                                      "rtf": round(total_ms / 1000 / seconds, 3) if seconds else None,
                                      "model_revision": info.get("model_revision"), "engine": info.get("engine"),
                                      "simulated": info.get("simulated")}, ensure_ascii=False) + "\n")
            res.flush()
    print(f"wrote {len(rows)} clips to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

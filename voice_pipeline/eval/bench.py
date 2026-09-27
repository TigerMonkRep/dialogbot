"""Latency benchmark on named hardware.

    # TTS only (service directly): p50/p95 synthesis time per speech unit, RTF, at 1..N concurrent sessions
    python -m voice_pipeline.eval.bench tts --tts-url ... --token ... --voice voice.json --concurrency 1,2,4 --n 40
    # Vapi path (API → TTS service): time to first audio byte of /api/v1/voice/vapi/{session} – what Vapi waits for
    python -m voice_pipeline.eval.bench vapi --url https://api.../api/v1/voice/vapi/<session_id> --secret ... --n 40

Reports p50/p95 of time-to-first-audio (TTFA), total time and real-time factor. `--hardware` is written into
the result so numbers are never quoted without the machine they were measured on. The full chain (caller
stops talking → first audible answer) additionally includes Vapi end-pointing, STT and the dialogue model;
measure that from Vapi call logs / recordings and report it separately.
"""
from __future__ import annotations

import argparse
import json
import statistics
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

import httpx

SENTENCES = ["Hej, du taler med en digital assistent. Hvordan kan jeg hjælpe dig i dag?",
             "Jeg har en ledig tid onsdag den otteogtyvende oktober klokken halv elleve.",
             "Tiden er endnu ikke bekræftet. Jeg undersøger, om den blev oprettet.",
             "Det koster et tusind fire hundrede og femoghalvfems kroner om måneden eksklusive moms."]


def pct(xs, p):
    xs = sorted(xs)
    return round(xs[min(len(xs) - 1, int(len(xs) * p))], 1) if xs else None


def tts_once(c, url, token, voice, text, rate):
    t0 = time.monotonic()
    r = c.post(f"{url}/v1/synthesize", headers={"authorization": f"Bearer {token}"},
               json={"voice": voice, "text": text, "language": "da", "format": "pcm_s16le", "sample_rate": rate,
                     "request_id": uuid.uuid4().hex})
    r.raise_for_status()
    ms = (time.monotonic() - t0) * 1000
    return ms, len(r.content) / 2 / rate


def vapi_once(c, url, secret, text, rate):
    t0 = time.monotonic()
    first = None
    total = 0
    with c.stream("POST", url, headers={"x-vapi-secret": secret},
                  json={"message": {"type": "voice-request", "text": text, "sampleRate": rate}}) as r:
        r.raise_for_status()
        for chunk in r.iter_bytes():
            if first is None and chunk:
                first = (time.monotonic() - t0) * 1000
            total += len(chunk)
    return first, (time.monotonic() - t0) * 1000, total / 2 / rate


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["tts", "vapi"])
    ap.add_argument("--tts-url")
    ap.add_argument("--token")
    ap.add_argument("--voice")
    ap.add_argument("--url")
    ap.add_argument("--secret")
    ap.add_argument("--n", type=int, default=40)
    ap.add_argument("--concurrency", default="1")
    ap.add_argument("--rate", type=int, default=24000)
    ap.add_argument("--hardware", default="unspecified")
    args = ap.parse_args(argv)
    results = {"mode": args.mode, "hardware": args.hardware, "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "runs": []}
    voice = json.load(open(args.voice)) if args.mode == "tts" else None
    with httpx.Client(timeout=120) as c:
        for conc in [int(x) for x in args.concurrency.split(",")]:
            jobs = [SENTENCES[i % len(SENTENCES)] for i in range(args.n)]
            with ThreadPoolExecutor(conc) as pool:
                if args.mode == "tts":
                    out = list(pool.map(lambda t: tts_once(c, args.tts_url, args.token, voice, t, args.rate), jobs))
                    ms = [o[0] for o in out]
                    rtf = [o[0] / 1000 / o[1] for o in out if o[1]]
                    results["runs"].append({"concurrency": conc, "unit_ms_p50": pct(ms, .5), "unit_ms_p95": pct(ms, .95),
                                            "rtf_p50": pct(rtf, .5), "rtf_p95": pct(rtf, .95)})
                else:
                    out = list(pool.map(lambda t: vapi_once(c, args.url, args.secret, t, args.rate), jobs))
                    ttfa = [o[0] for o in out if o[0] is not None]
                    total = [o[1] for o in out]
                    results["runs"].append({"concurrency": conc, "ttfa_ms_p50": pct(ttfa, .5), "ttfa_ms_p95": pct(ttfa, .95),
                                            "total_ms_p50": pct(total, .5), "total_ms_p95": pct(total, .95),
                                            "mean_audio_s": round(statistics.mean(o[2] for o in out), 2)})
    print(json.dumps(results, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

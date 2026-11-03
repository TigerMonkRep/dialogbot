"""Blind listening samples for the voice comparison (T0 current voice vs T1/T2), same Danish text per model.

    ELEVENLABS_API_KEY=... python -m scripts.stemmetest_tts_samples --voice-id <Peter's voice id> \
        --model T0=eleven_v4_turbo --model T2=eleven_flash_v2_5 --out var/tts-blind

Writes var/tts-blind/index.html (anonymous A/B/C labels in a random order per sentence, rate 1–5 for naturlighed,
udtale, forståelighed and tal) and key.json (which label is which model – keep it away from the rater until done).
The voice id is YOURS to give: it is never guessed. Models are sent exactly as named, so the report can say which model
actually ran. Same voice id with a different model is a model change; a different voice id is a voice AND model change."""
from __future__ import annotations

import argparse
import html
import json
import os
import random
import time
from pathlib import Path

import httpx

URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream"
SENTENCES = [
    "Goddag, du har ringet til Gastro Hall. Hvad kan jeg hjælpe dig med?",
    "Vi har Racehall i Aarhus og Gastro Hall i Højbjerg.",
    "Jeg har booket jer til klokken halv syv på fredag.",
    "Mit testnummer er tyve, tredive, fyrre, halvtreds.",
    "Din booking er bekræftet: seks personer, lørdag den ottende november klokken seksten.",
]


def synth(key: str, voice_id: str, model: str, text: str) -> tuple[bytes, float]:
    t0 = time.monotonic()
    first = None
    buf = b""
    with httpx.stream("POST", URL.format(voice_id=voice_id), params={"output_format": "mp3_44100_128"},
                      headers={"xi-api-key": key}, json={"text": text, "model_id": model, "language_code": "da"}, timeout=60) as r:
        r.raise_for_status()
        for chunk in r.iter_bytes():
            if first is None:
                first = time.monotonic() - t0
            buf += chunk
    return buf, first or 0.0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--voice-id", required=True)
    ap.add_argument("--model", action="append", required=True, help="LABEL=model_id, e.g. T0=eleven_v4_turbo")
    ap.add_argument("--out", default="var/tts-blind")
    a = ap.parse_args()
    key = os.environ.get("ELEVENLABS_API_KEY")
    if not key:
        raise SystemExit("ELEVENLABS_API_KEY mangler – ingen prøver er lavet")
    models = dict(m.split("=", 1) for m in a.model)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    rng = random.Random()
    key_map: dict = {}
    rows = []
    for i, text in enumerate(SENTENCES):
        labels = list("ABCDEFG"[: len(models)])
        rng.shuffle(labels)
        items = []
        for (name, model), label in zip(models.items(), labels, strict=True):
            audio, first = synth(key, a.voice_id, model, text)
            f = f"s{i}_{label}.mp3"
            (out / f).write_bytes(audio)
            key_map[f] = {"sentence": i, "label": label, "profile": name, "model": model, "first_audio_s": round(first, 3)}
            items.append((label, f))
        rows.append((text, sorted(items)))
    page = ["<meta charset=utf-8><title>Blind stemmetest</title><body style='font-family:sans-serif;max-width:48rem;margin:2rem auto'>"]
    for i, (text, items) in enumerate(rows):
        page.append(f"<h3>{i + 1}. {html.escape(text)}</h3>")
        for label, f in items:
            page.append(f"<p><b>{label}</b> <audio controls src='{f}'></audio><br>naturlighed 1–5 <input size=2> udtale 1–5 <input size=2> "
                        f"forståelighed 1–5 <input size=2> tal korrekte? <input size=3></p>")
    (out / "index.html").write_text("\n".join(page), encoding="utf-8")
    (out / "key.json").write_text(json.dumps(key_map, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(key_map)} prøver i {out}/ – åbn index.html; key.json afslører, hvem der er hvem")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

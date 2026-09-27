"""Import → QC → reference selection on a synthetic Parquet file shaped like CoRal-TTS (audio struct with bytes and
path, text, speaker_id). Proves extraction without the `datasets` decoder, safe paths, flags and selection rules."""
from __future__ import annotations

import io
import json

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import soundfile as sf

from voice_pipeline import import_coral_tts, qc, select_references


def _clip(seconds, sr=44100, amp=0.3, clip=False, silence_mid=0.0):
    t = np.arange(int(sr * seconds)) / sr
    x = amp * np.sin(2 * np.pi * 220 * t) + 0.001 * np.random.default_rng(1).standard_normal(len(t))
    if silence_mid:
        m = len(x) // 2
        x[m:m + int(sr * silence_mid)] = 0
    if clip:
        x[: len(x) // 10] = 1.0
    pad = np.zeros(int(sr * 0.3)) + 0.0005 * np.random.default_rng(2).standard_normal(int(sr * 0.3))
    x = np.concatenate([pad, x[: len(x) // 2], pad, x[len(x) // 2:], pad])  # speech has pauses
    buf = io.BytesIO()
    sf.write(buf, x.astype("float32"), sr, format="FLAC")
    return buf.getvalue()


def test_pipeline(tmp_path, monkeypatch):
    rows = [
        ({"bytes": _clip(8), "path": "../../etc/passwd"}, "Hej, jeg hedder Mette og jeg bor i Aarhus.", "spk_F"),
        ({"bytes": _clip(9), "path": "x.flac"}, "Vi sliber gulve i hele Østjylland med støvfrit anlæg.", "spk_F"),
        ({"bytes": _clip(7, clip=True), "path": "y.flac"}, "Det her er en klippet optagelse på dansk.", "spk_F"),
        ({"bytes": _clip(10, silence_mid=2.0), "path": "z.flac"}, "Der er en lang pause midt i den her sætning.", "spk_M"),
        ({"bytes": _clip(8), "path": "a.flac"}, "The weather is nice and you have to go with this.", "spk_M"),
        ({"bytes": _clip(11), "path": "b.flac"}, "Tak for opkaldet, og hav en god dag i Sønderborg.", "spk_M"),
        ({"bytes": None, "path": "c.flac"}, "Tom række", "spk_M"),
    ]
    audio = pa.array([r[0] for r in rows], type=pa.struct([("bytes", pa.binary()), ("path", pa.string())]))
    table = pa.table({"audio": audio, "text": [r[1] for r in rows], "speaker_id": [r[2] for r in rows]})
    parquet = tmp_path / "train-00000.parquet"
    pq.write_table(table, parquet, row_group_size=3)
    out = tmp_path / "import"
    out.mkdir()
    with (out / "manifest.jsonl").open("w", encoding="utf-8") as m:
        n = import_coral_tts.extract(parquet, out, per_speaker=None, seen={}, manifest=m)
    assert n == 6
    manifest = [json.loads(x) for x in (out / "manifest.jsonl").read_text().splitlines()]
    assert any("error" in r for r in manifest)
    for r in manifest:
        if "wav" in r:
            p = (out / r["wav"]).resolve()
            assert out.resolve() in p.parents and "passwd" not in r["wav"]
            assert r["sample_rate"] == 44100  # original rate kept
    (out / "import_summary.json").write_text(json.dumps({"revision": "c" * 40}))
    qc.main(["--import-dir", str(out)])
    flags = {json.loads(x)["id"]: json.loads(x)["flags"] for x in (out / "qc.jsonl").read_text().splitlines()}
    assert any("clipping" in f for f in flags.values())
    assert any("long_internal_silence" in f for f in flags.values())
    assert any("possibly_not_danish" in f for f in flags.values())
    monkeypatch.setattr(select_references, "OUT", tmp_path / "refs.json")
    select_references.main(["--import-dir", str(out), "--per-speaker", "3"])
    chosen = json.loads((tmp_path / "refs.json").read_text())
    assert chosen["revision"] == "c" * 40
    assert len(chosen["speakers"]["spk_f"]) == 2 and len(chosen["speakers"]["spk_m"]) == 1
    assert all(6 <= c["duration"] <= 12 for s in chosen["speakers"].values() for c in s)

"""Blind listening test: the page never reveals which candidate a clip is, clips are loudness- and rate-matched,
original recordings join as a blind anchor, and scoring only counts native Danish raters towards the goal."""
from __future__ import annotations

import json

import numpy as np
import soundfile as sf

from voice_pipeline.eval import listening_test


def _wav(path, seconds, sr, amp):
    t = np.arange(int(sr * seconds)) / sr
    sf.write(path, (amp * np.sin(2 * np.pi * 200 * t)).astype("float32"), sr, subtype="PCM_16")


def test_build_and_score(tmp_path):
    runs = []
    for name, amp in (("coral-a", 0.05), ("coral-b", 0.5)):
        d = tmp_path / name
        d.mkdir()
        with (d / "results.jsonl").open("w") as f:
            for i in range(4):
                _wav(d / f"da-00{i}.wav", 2, 24000, amp)
                f.write(json.dumps({"id": f"da-00{i}", "text": f"Sætning {i}", "meaning": "x", "simulated": False}) + "\n")
        runs.append(f"{name}={d}")
    imp = tmp_path / "import"
    (imp / "wav" / "spk").mkdir(parents=True)
    with (imp / "manifest.jsonl").open("w") as f:
        for i in range(3):
            _wav(imp / "wav" / "spk" / f"h{i}.wav", 4, 44100, 0.2)
            f.write(json.dumps({"id": f"h{i}", "speaker": "spk", "wav": f"wav/spk/h{i}.wav", "duration": 4.0,
                                "text": "Dette er en original optagelse"}) + "\n")
    out = tmp_path / "test"
    listening_test.build(runs, 3, out, seed=1, human=f"{imp}:2", test_id="t1")
    key = json.loads((out / "key.json").read_text())["clips"]
    assert sorted(m["candidate"] for m in key.values()).count("human-reference") == 2
    assert len(key) == 8
    page = (out / "index.html").read_text()
    for secret in ("coral-a", "coral-b", "human-reference", "da-00", "spk", "h0"):
        assert secret not in page
    levels = []
    for clip in key:
        x, sr = sf.read(out / "audio" / f"{clip}.wav")
        assert sr == 24000
        levels.append(20 * np.log10(np.sqrt(np.mean(x ** 2))))
    assert max(levels) - min(levels) < 0.5  # loudness matched across candidates
    clips = {m["candidate"]: c for c, m in key.items()}
    rows = ["rater,clip,field,value"]
    for rater, native in (("A", "ja"), ("B", "ja"), ("C", "nej")):
        rows.append(f"{rater},_rater,native,{native}")
        for field in ("forstaaelighed", "naturlighed", "stabilitet"):
            rows.append(f"{rater},{clips['coral-a']},{field},5")
    csv_file = tmp_path / "answers.csv"
    csv_file.write_text("\n".join(rows) + "\n")
    result = listening_test.score(out, [csv_file])
    assert result["coral-a"]["raters"] == 3 and result["coral-a"]["danish_native_raters"] == 2
    assert result["coral-a"]["meets_goal"] is False  # only two native Danish raters


def test_asr_compare_normalises_numbers():
    from voice_pipeline.eval.asr_check import compare

    r = compare("Det koster 1.495 kroner.", "Det koster et tusind fire hundrede og femoghalvfems kroner",
                ["et tusind fire hundrede og femoghalvfems kroner"])
    assert r["wer"] == 0 and r["must_say_missing"] == []
    r = compare("Tiden er ikke bekræftet.", "Tiden er bekræftet", ["ikke"])
    assert r["wer"] > 0 and r["must_say_missing"] == ["ikke"]

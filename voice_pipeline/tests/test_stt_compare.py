"""STT comparison mechanics: the phone-line degradation, entity scoring and the summary – without calling any engine."""
from __future__ import annotations

import numpy as np

from voice_pipeline.eval import stt_compare as sc


def test_phone_line_is_band_limited_8k_and_keeps_length():
    t = np.arange(sc.SR) / sc.SR
    x = (0.3 * np.sin(2 * np.pi * 1000 * t) + 0.3 * np.sin(2 * np.pi * 6000 * t)).astype(np.float32)
    y = sc.phone_line(x)
    assert abs(len(y) - len(x)) <= 2 and np.isfinite(y).all()
    spec = np.abs(np.fft.rfft(y))
    freqs = np.fft.rfftfreq(len(y), 1 / sc.SR)
    in_band = spec[(freqs > 900) & (freqs < 1100)].max()
    above = spec[(freqs > 5900) & (freqs < 6100)].max()
    assert above < in_band * 0.01  # 6 kHz does not survive an 8 kHz phone line


def test_entities_and_score_catch_names_and_numbers():
    ref = "Ring til Mette Hansen på 20 30 40 50, vi kommer til Havnevej 12 i Aarhus."
    ents = sc.entities(ref)
    assert "Mette Hansen" in ents and "Havnevej" in ents and "Aarhus" in ents and any("20 30 40 50" in e for e in ents)
    perfect = sc.score(ref, ref)
    assert perfect["wer"] == 0 and perfect["entities_caught"] == perfect["entities"]
    bad = sc.score(ref, "ring til mette hansen på tyve tredive, vi kommer til havnevej tolv i århus")
    assert bad["wer"] > 0 and "Aarhus" in bad["entities_missed"] and bad["entities_caught"] < bad["entities"]


def test_summary_is_word_weighted():
    rows = [{"wer": 0.0, "cer": 0.0, "ref_words": 30, "entities": 2, "entities_caught": 2, "latency_ms": 100, "error": None},
            {"wer": 1.0, "cer": 1.0, "ref_words": 10, "entities": 2, "entities_caught": 0, "latency_ms": 300, "error": "x"}]
    s = sc.summarize(rows)
    assert s["wer"] == 0.25 and s["entities_caught"] == "2/4" and s["errors"] == 1 and s["latency_ms_p50"] == 200

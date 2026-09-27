"""Danish speech normalisation keeps every value: numbers round-trip through a parser, dates, amounts,
times, phone numbers and e-mails are spelled out exactly, negations stay, chunks never split a value."""
from __future__ import annotations

import json
import random
import re
from pathlib import Path

import pytest

from app.modules.voices import danish

UNITS = {w: i for i, w in enumerate(danish.ONES)} | {"et": 1}
TENS = {w: n for n, w in danish.TENS.items()}


def _parse_below_100(w: str) -> int:
    if w in UNITS:
        return UNITS[w]
    if w in TENS:
        return TENS[w]
    for t_word, t in TENS.items():
        if w.endswith("og" + t_word):
            return UNITS[w[: -len("og" + t_word)]] + t
    raise ValueError(w)


def parse_number(words: str) -> int:
    """Inverse of danish.number (test oracle)."""
    total, current = 0, 0
    tokens = words.split()
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok == "og":
            i += 1
            continue
        if tok in ("million", "millioner"):
            total += (current or 1) * 1_000_000
            current = 0
        elif tok == "tusind":
            total += (current or 1) * 1000
            current = 0
        elif tok == "hundrede":
            current = (current or 1) * 100
        else:
            current += _parse_below_100(tok)
        i += 1
    return total + current


def test_numbers_round_trip():
    for n in list(range(0, 2101)) + random.Random(7).sample(range(2101, 10_000_000), 2000):
        assert parse_number(danish.number(n)) == n, n


def test_known_words():
    assert danish.number(1495) == "et tusind fire hundrede og femoghalvfems"
    assert danish.number(1005) == "et tusind og fem"
    assert danish.number(21) == "enogtyve"
    assert danish.number(2_500_000) == "to millioner fem hundrede tusind"
    assert danish.ordinal(28) == "otteogtyvende" and danish.ordinal(31) == "enogtredivte" and danish.ordinal(2) == "anden"
    assert danish.digit_pairs("20304050") == "tyve tredive fyrre halvtreds"
    assert danish.digit_pairs("0712") == "nul syv tolv"


@pytest.mark.parametrize("text,expected", [
    ("Jeg har en ledig tid onsdag den 28. oktober klokken halv elleve.",
     "Jeg har en ledig tid onsdag den otteogtyvende oktober klokken halv elleve."),
    ("Det koster 1.495 kroner om måneden eksklusive moms.",
     "Det koster et tusind fire hundrede og femoghalvfems kroner om måneden eksklusive moms."),
    ("Tilbuddet gælder ved mindst 40 kvadratmeter.", "Tilbuddet gælder ved mindst fyrre kvadratmeter."),
    ("Tiden er endnu ikke bekræftet. Jeg undersøger, om den blev oprettet.",
     "Tiden er endnu ikke bekræftet. Jeg undersøger, om den blev oprettet."),
    ("Er adressen i Aarhus, Rødovre eller Sønderborg?", "Er adressen i Aarhus, Rødovre eller Sønderborg?"),
    ("Ring på 20 30 40 50.", "Ring på tyve tredive fyrre halvtreds."),
    ("Ring på +45 70 12 34 56.", "Ring på plus femogfyrre, halvfjerds tolv fireogtredive seksoghalvtreds."),
    ("Vi har åbent kl. 8.00-16.30.", "Vi har åbent klokken otte til seksten tredive."),
    ("Mødet er kl. 9.05.", "Mødet er klokken ni nul fem."),
    ("Prisen er 149,50 kr. inkl. moms.", "Prisen er et hundrede og niogfyrre kroner og halvtreds øre inklusive moms."),
    ("Skriv til info@fyrster.dk.", "Skriv til info snabel-a fyrster punktum d k."),
    ("Fakturaen forfalder 01.12.2026.", "Fakturaen forfalder den første december to tusind og seksogtyve."),
    ("Moms er 25 %.", "Moms er femogtyve procent."),
    ("Det koster 1.495 kr. Tak!", "Det koster et tusind fire hundrede og femoghalvfems kroner. Tak!"),
])
def test_examples(text, expected):
    assert danish.normalize(text) == expected


def test_pronunciation_dictionary_whole_words_only():
    entries = [{"term": "Fjord", "say": "Fjor"}, {"term": "ApS", "say": "a p s"}]
    out = danish.normalize("Fjord Gulvservice ApS og fjordens vand", entries)
    assert out == "Fjor Gulvservice a p s og fjordens vand"


def test_chunks_never_split_values_and_keep_negations():
    text = danish.normalize("Tiden er ikke bekræftet endnu. Det koster 1.495 kr. om måneden, og tilbuddet gælder ved 40 m2. "
                            "Ring på 20 30 40 50!")
    parts = danish.chunks(text)
    assert parts == ["Tiden er ikke bekræftet endnu.",
                     "Det koster et tusind fire hundrede og femoghalvfems kroner om måneden, og tilbuddet gælder ved fyrre kvadratmeter.",
                     "Ring på tyve tredive fyrre halvtreds!"]
    long = "Jeg har kigget i kalenderen, " * 12 + "og der er ingen ledige tider."
    for p in danish.chunks(long, max_chars=120):
        assert len(p) <= 120
    assert " ".join(danish.chunks(long, max_chars=120)) == long.strip()


TESTSET = Path(__file__).resolve().parents[1] / "voice_pipeline" / "eval" / "testset_da.jsonl"


def test_testset_is_large_and_every_critical_value_survives():
    rows = [json.loads(line) for line in TESTSET.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(rows) >= 100 and len({r["id"] for r in rows}) == len(rows)
    cats = {r["category"] for r in rows}
    assert {"kort_spørgsmål", "langt_svar", "navne_steder", "tal_beløb", "tid_dato", "email_telefon",
            "afbrydelse", "bookingfejl", "negation"} <= cats
    for r in rows:
        spoken = danish.normalize(r["text"])
        assert not re.search(r"\d", spoken), (r["id"], spoken)  # every digit is spoken
        for phrase in r.get("must_say", []):
            assert phrase in spoken, (r["id"], phrase, spoken)
        for word in ("ikke", "ingen", "aldrig"):
            assert spoken.lower().count(word) >= r["text"].lower().count(word), (r["id"], word)

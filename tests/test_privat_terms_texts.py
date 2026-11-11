"""The app's words about the Opkaldssaldo and website bookings match the Privat terms (legal.json privatTerms), in all 8
languages – Fürster's decisions 2026-11-11 on F-VF-06-PC-TERMS and F-PQ-03-X09:

1. «Slet min konto» (privat.json myData.deleteText): a remaining saldo is lost and not refunded, EXCEPT the unused part of a
   top-up within 14 days (the right of withdrawal, terms point 7) – never stricter than the terms.
2. Website booking: the terms say «fair use» without a number; the code keeps its hidden cap (30). No user text names it.
3. The top-up sheet (buy.note): the saldo does not expire as long as the account exists – not «in the pilot».
4. The simulated sponsor spot is gone: no sponsor texts, no sponsor sheet, no sponsor call in the web.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from app.modules.billing import prices

ROOT = Path(__file__).resolve().parents[1]
MSG = ROOT / "web/src/i18n/messages"
LANGS = ("da", "de", "en", "es", "fr", "it", "no", "sv")


def _load(lang: str, name: str) -> dict:
    return json.loads((MSG / lang / name).read_text(encoding="utf-8"))


def _strings(o, path=""):
    if isinstance(o, dict):
        for k, v in o.items():
            yield from _strings(v, f"{path}.{k}")
    elif isinstance(o, list):
        for i, v in enumerate(o):
            yield from _strings(v, f"{path}[{i}]")
    elif isinstance(o, str):
        yield path, o


def _saldo_paragraphs(lang: str) -> tuple[str, str]:
    """(expiry, refund) – the two paragraphs of the terms' Opkaldssaldo section about expiry and refunds."""
    texts = [t for _p, t in _strings(_load(lang, "legal.json")["privatTerms"]) if len(t) > 5]
    i = next(i for i, t in enumerate(texts) if "{pWelcome}" in t and "{pReferral}" in t)
    return texts[i], texts[i + 1]


def test_all_8_languages_are_here():
    assert sorted(p.name for p in MSG.iterdir() if p.is_dir()) == sorted(LANGS)


def test_delete_account_warning_keeps_the_14_day_withdrawal_like_the_terms():
    for lang in LANGS:
        text = _load(lang, "privat.json")["myData"]["deleteText"]
        _expiry, refund = _saldo_paragraphs(lang)
        point = re.search(r"\((?:\w+ )?(\d+)\)\.?$", refund).group(1)  # «… (punkt 7).»
        assert "14" in refund and "14" in text, (lang, text)
        assert re.search(rf"\b{point}\b", text), (lang, "refers to the withdrawal point of the terms", text)
    da = _load("da", "privat.json")["myData"]["deleteText"]
    assert "refunderes ikke – undtagen inden for 14 dage efter en optankning" in da
    assert "den ubrugte del af optankningen" in da


def test_top_up_sheet_says_what_the_terms_say_about_expiry():
    pilot = re.compile(r"(?i)pilot")
    for lang in LANGS:
        note = _load(lang, "privat.json")["buy"]["note"]
        expiry, _refund = _saldo_paragraphs(lang)
        first = expiry.split(". ")[0].rstrip(".")  # «Saldoen udløber ikke, så længe kontoen findes»
        assert not pilot.search(note), (lang, note)
        assert first in note, (lang, note, first)


def test_website_booking_cap_is_fair_use_in_words_and_never_a_number():
    assert prices.PRIVAT_BROWSER_BOOKINGS_PER_MONTH == 30  # the code keeps its cap (decision 2026-11-11)
    cap = re.compile(rf"\b{prices.PRIVAT_BROWSER_BOOKINGS_PER_MONTH}\b")
    da_terms = [t for _p, t in _strings(_load("da", "legal.json")["privatTerms"])]
    idx = next(i for i, t in enumerate(da_terms) if "Hjemmesidebooking" in t and "fair use" in t)
    for lang in LANGS:
        terms = [t for _p, t in _strings(_load(lang, "legal.json")["privatTerms"])]
        assert len(terms) == len(da_terms), lang
        assert not re.search(r"\d", terms[idx]), (lang, terms[idx])
        for path, text in _strings(_load(lang, "privat.json")["browser"]):
            assert not cap.search(text), (lang, f"browser{path}", text)


def test_no_sponsor_spot_left_in_texts_or_web_code():
    for lang in LANGS:
        p = _load(lang, "privat.json")
        assert "sponsor" not in p and "sponsor" not in p["paywall"], lang
        hits = [(path, t) for path, t in _strings(p) if re.search(r"(?i)sponsor", t) and path != ".travel.sponsored"]
        assert hits == [], (lang, hits)
    for rel in ("web/src/lib/privat/api.ts", "web/src/lib/privat/fake.ts", "web/src/components/privat/sheets.tsx",
                "web/src/components/privat/store.tsx"):
        src = (ROOT / rel).read_text(encoding="utf-8")
        assert not re.search(r"sponsorClaim|sponsor_left_today|sponsor/claim|SponsorSheet|\"sponsor\"", src), rel

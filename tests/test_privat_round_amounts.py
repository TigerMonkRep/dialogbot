"""Opkaldssaldo amounts in other currencies are round, explicit numbers (decision Fürster 2026-11-11, via qa-lead):
top-ups SEK/NOK 75/150/300 and EUR 7/15/30; welcome and referral bonus SEK/NOK 15 and EUR 1,50; extra task SEK/NOK 3 and
EUR 0,30. No factor derivation for these. The extra-call prices are NOT round: they stay Erhverv × moms (F-PDEC-01)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.modules.billing import markets, prices

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = {
    "DKK": {"topups": (5000, 10000, 20000), "welcome": 1000, "referral": 1000, "extra_task": 300},
    "SEK": {"topups": (7500, 15000, 30000), "welcome": 1500, "referral": 1500, "extra_task": 300},
    "NOK": {"topups": (7500, 15000, 30000), "welcome": 1500, "referral": 1500, "extra_task": 300},
    "EUR": {"topups": (700, 1500, 3000), "welcome": 150, "referral": 150, "extra_task": 30},
}


@pytest.mark.parametrize("cur", list(EXPECTED))
def test_the_values_per_currency(cur):
    e = EXPECTED[cur]
    assert markets.PRIVAT_TOPUPS[cur] == markets.privat_topups(cur) == e["topups"]
    assert markets.privat_balance_amount(cur, "welcome") == e["welcome"]
    assert markets.privat_balance_amount(cur, "referral") == e["referral"]
    assert markets.privat_balance_amount(cur, "extra_task") == e["extra_task"]


def test_dkk_is_still_prices_py():
    assert markets.PRIVAT_BALANCE["DKK"] == {"topups": prices.PRIVAT_TOPUPS_GROSS_MINOR,
                                             "welcome": prices.PRIVAT_WELCOME_BONUS_MINOR,
                                             "referral": prices.PRIVAT_REFERRAL_BONUS_MINOR,
                                             "extra_task": prices.PRIVAT_EXTRA_TASK_MINOR}


def test_they_are_written_out_not_derived(monkeypatch):
    """Changing the factor (Erhverv's minute price) moves the extra-call prices but none of these amounts."""
    before = {c: markets.privat_extra_call(c)["minute"] for c in ("SEK", "NOK", "EUR")}
    for c in ("SEK", "NOK", "EUR"):
        monkeypatch.setitem(markets.ERHVERV[c], "outbound_extra_minute", markets.ERHVERV[c]["outbound_extra_minute"] * 2)
    for c in ("SEK", "NOK", "EUR"):
        assert markets.privat_extra_call(c)["minute"] != before[c]
        assert markets.privat_topups(c) == EXPECTED[c]["topups"]
        assert markets.privat_balance_amount(c, "welcome") == EXPECTED[c]["welcome"]
        assert markets.privat_balance_amount(c, "extra_task") == EXPECTED[c]["extra_task"]


def test_the_extra_call_prices_are_unchanged():
    assert markets.privat_extra_call("SEK") == {"answered": 738, "voicemail": 188, "no_answer": 44, "minute": 369, "max": 2581}
    assert markets.privat_extra_call("EUR") == {"answered": 69, "voicemail": 18, "no_answer": 4, "minute": 34, "max": 239}


def test_the_website_table_and_the_doc_say_the_same():
    table = json.loads((ROOT / "web/src/lib/prices.json").read_text())
    for c, e in EXPECTED.items():
        assert table["privatTopups"][c] == list(e["topups"])
        assert table["privatBalance"][c] == {"welcome": e["welcome"], "referral": e["referral"], "extra_task": e["extra_task"]}
    doc = (ROOT / "docs/markets.md").read_text().replace("\u00a0", " ")
    assert "75 kr / 150 kr / 300 kr" in doc and "€7 / €15 / €30" in doc and "€1.50" in doc and "€0.30" in doc
    assert "14,75" not in doc and "€1.35" not in doc


def test_a_fresh_welcome_bonus_moves_to_the_round_bonus_at_the_first_checkout(api, pv, db):
    from app.modules.privat import ledger

    tok = pv.account("hans@testmail.dk", trial=False)
    ws = pv.ws(tok)
    assert ledger.balance(db, ws) == 1000
    ledger.adopt_currency(db, ws, "SEK")
    db.commit()
    assert ledger._sum(db, ws, "SEK") == 1500


def test_a_spent_part_of_the_welcome_bonus_moves_at_the_factor(api, pv, db):
    from app.modules.privat import ledger

    tok = pv.account("hans@testmail.dk", trial=False)
    ws = pv.ws(tok)
    ledger.add(db, ws, kind="spend", amount=-300, source_ref="test:task", cur="DKK", text="ekstra opgave")
    ledger.adopt_currency(db, ws, "EUR")
    db.commit()
    assert ledger._sum(db, ws, "EUR") == markets.privat_from_dkk(700, "EUR") == 95

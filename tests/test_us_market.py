"""The US market (decision 13 November 2026): dollars as the fifth currency, the website's «us» edition (English texts,
dollar prices) and what follows from it in billing, languages and the outreach e-mails."""
from __future__ import annotations

import json
from pathlib import Path

from app.core import languages
from app.modules.billing import markets
from app.modules.outreach import localization
from app.modules.privat import market as privat_market

ROOT = Path(__file__).resolve().parent.parent


def test_usd_list_prices_are_349_a_month_and_the_euro_price_scaled():
    usd, eur = markets.ERHVERV["USD"], markets.ERHVERV["EUR"]
    assert usd["monthly"] == 34_900 and usd["setup"] == 70_900
    for item in ("extra_minute", "outbound_extra_minute", "call_answered", "call_voicemail", "call_no_answer"):
        assert usd[item] == round(eur[item] * 349 / 329), item          # whole cents
    assert set(usd) == set(markets.ERHVERV["DKK"])                      # every price exists in dollars
    assert markets.fmt(usd["monthly"], "USD") == "$349" and markets.fmt(usd["call_answered"], "USD") == "$0.58"
    assert markets.fmt(1_234_500, "USD") == "$12,345"


def test_a_us_company_pays_in_dollars_without_danish_vat():
    assert markets.currency_for_country("US") == "USD" and markets.currency_for_country("us") == "USD"
    assert markets.currency_for_country("GB") == "EUR" and markets.currency_for_country("DK") == "DKK"   # unchanged
    vat = markets.erhverv_vat("US", None)
    assert vat.rate_bp == 0 and vat.kind == "outside_eu"


def test_the_us_edition_is_english_with_dollars_everywhere_a_locale_is_read():
    assert markets.currency_for_locale("us") == "USD" and markets.currency_for_locale("en") == "EUR"
    assert languages.normalize("us") == "en" and languages.normalize("en-US") == "en"   # a market, not a language
    assert "us" not in languages.LANGUAGES
    assert privat_market.norm_locale("us") == "us" and privat_market.stripe_locale("us") == "en"
    assert privat_market.currency(None, "us") == "USD"
    assert privat_market.currency("DKK", "us") == "DKK"                 # a customer keeps the currency it started in
    assert markets.privat_vat(markets.LOCALE_COUNTRY["us"]).rate_bp == 0


def test_privat_in_dollars_keeps_the_yearly_promise():
    for plan, p in markets.PRIVAT["USD"].items():
        assert p["yearly_total"] == 12 * p["yearly_monthly"], plan
        assert p["yearly_monthly"] * 100 <= p["monthly"] * 80, plan     # «save 20 %» is true
    assert markets.privat_topups("USD") == (800, 1_500, 3_000)


def test_the_website_table_carries_the_us_edition():
    table = json.loads((ROOT / "web/src/lib/prices.json").read_text())
    assert table["localeCurrency"]["us"] == "USD" and "USD" in table["currencies"]
    assert table["erhverv"]["USD"]["monthly"] == 34_900


def test_outreach_to_the_us_quotes_the_billable_dollar_price_and_links_to_the_us_edition():
    assert localization.locale_for("US").price == "$349/mo"
    assert localization.demo_url("US") == "https://dialogbot.app/us"
    assert localization.demo_url("UK") == "https://dialogbot.app"

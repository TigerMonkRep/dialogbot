"""One offer, written once: the subscription from 2.495 kr./md. (300 inbound minutes included, then 1,50 kr./min),
4 kr. per outbound campaign call plus 2 kr. per started minute, and 5.000 kr. for specialist setup, all excl. VAT.
These tests keep the old prices (1.495 kr., 149 kr. per approved enquiry, 9 kr. per contact) from creeping back into
any text a customer, a visitor, a salesperson or an AI can read."""
from __future__ import annotations

import json
import re
from pathlib import Path

from app.modules.billing import agreements, markets, prices

ROOT = Path(__file__).resolve().parent.parent

# Where old prices legitimately still appear: code that keeps old agreements and old months readable, and history.
ALLOWED = {
    "app/modules/billing/agreements.py", "app/modules/billing/statement.py", "app/modules/billing/money.py",
    "app/modules/leads/service.py", "app/models/domain.py", "app/modules/leads/router.py",
    "app/modules/voices/danish.py",  # a number-reading example in a comment, not a price statement

    "web/src/app/app/(admin)/leads/client.tsx", "web/src/app/app/(admin)/billing/page.tsx",
    "web/src/app/app/(admin)/settings/agreement/client.tsx",  # shows an old model-B agreement honestly
}
SCANNED = ["app", "web/src", "web/public/materiale", "web/public/llms.txt", "design-reference/byggevejledning",
           "docs/social-media.md", "docs/sales", "docs/ambassadors", "docs/telephony"]
OLD = re.compile(r"1\.495|\b149 kr|\b149,00|pr\. godkendt henvendelse|[Mm]odel [AB]\b|kontaktpakke|9 kr\. pr\. kontakt|9,00 kr|[Gg]ratis (personlig )?opsætning|opsætning(en)? (koster )?0 kr|intet opstartsgebyr")
SUFFIXES = {".py", ".ts", ".tsx", ".html", ".txt", ".md"}


def _files():
    for entry in SCANNED:
        p = ROOT / entry
        for f in ([p] if p.is_file() else sorted(p.rglob("*"))):
            if f.is_file() and f.suffix in SUFFIXES and "node_modules" not in f.parts and ".next" not in f.parts \
                    and "__pycache__" not in f.parts:
                yield f


def test_list_prices():
    assert prices.SUBSCRIPTION_MONTHLY_NET_MINOR == 249_500 and prices.CAMPAIGN_CALL_NET_MINOR == 400
    assert prices.CAMPAIGN_MINUTE_NET_MINOR == 200 and prices.INBOUND_INCLUDED_MINUTES == 300 and prices.INBOUND_EXTRA_MINUTE_NET_MINOR == 150
    assert prices.kr(150) == "1,50" and prices.kr(200) == "2"
    assert prices.SPECIALIST_SETUP_NET_MINOR == 500_000
    assert (prices.kr(249_500), prices.kr(400), prices.kr(450), prices.kr(500_000)) == ("2.495", "4", "4,50", "5.000")
    assert agreements.TAX_BASIS_POINTS == 2500


def test_the_old_prices_are_gone_everywhere_a_person_or_an_ai_can_read():
    hits = []
    for f in _files():
        rel = f.relative_to(ROOT).as_posix()
        if rel in ALLOWED:
            continue
        for n, line in enumerate(f.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
            if OLD.search(line):
                hits.append(f"{rel}:{n}: {line.strip()[:110]}")
    assert not hits, "old price or price model found:\n" + "\n".join(hits)


def _da_render(text: str) -> str:
    """The Danish site renders {p…} tokens with the DKK row of prices.json (web/src/lib/markets.ts); markets.fmt writes
    DKK as the site does ("2.495 kr.", "1,50 kr.", with a plain space on the site), so this mirrors what a Danish visitor reads."""
    e = markets.ERHVERV["DKK"]
    values = {"pMonthly": e["monthly"], "pCall": e["call"], "pMinute": e["minute"], "pExtraMinute": e["extra_minute"],
              "pSetup": e["setup"], "pCall3Min": e["call"] + 3 * e["minute"]}
    out = text
    for k, minor in values.items():
        out = out.replace("{" + k + "}", markets.fmt(minor, "DKK").replace("\u00a0", " "))  # the site: plain spaces
    for k, minor in {"pMonthlyNum": e["monthly"], "pCallNum": e["call"], "pSetupNum": e["setup"]}.items():
        out = out.replace("{" + k + "}", prices.kr(minor))
    return out.replace("{pCur}", "kr.").replace("{pIncluded}", str(markets.INBOUND_INCLUDED_MINUTES))


def test_the_public_pages_state_both_prices():
    # The page texts live in the Danish source dictionaries (web/src/i18n/messages/da) and state every price as a
    # {p…} token, filled in per market by the translator – so a price is written once (prices.json), never in copy.
    pricing = (ROOT / "web/src/i18n/messages/da/landing.json").read_text(encoding="utf-8")
    site = (ROOT / "web/src/i18n/messages/da/site.json").read_text(encoding="utf-8")  # front page + build guide
    for text in (pricing, site):
        assert "{pMonthly}" in text and "{pCall} pr." in text and "{pMinute} pr." in text and "{pSetup}" in text and "ekskl. moms" in text
        assert not re.search(r"\d\s?kr\.", re.sub(r"(400|600) kr\.", "", text)), "a hard-coded amount in kroner"
    assert "300 minutter" in pricing and "{pExtraMinute}" in pricing  # the included inbound minutes and the price above them
    # Rendered for a Danish visitor, the copy states the same amounts as always.
    rendered = _da_render(pricing)
    assert "2.495 kr." in rendered and "4 kr. pr." in rendered and "2 kr. pr." in rendered and "5.000 kr." in rendered
    assert "1,50 kr." in rendered
    # The big price figures on the front page: amount and unit side by side.
    site_json = json.loads(site)
    assert _da_render(site_json["prices"]["monthly"]) + " " + _da_render(site_json["home"]["price"]["subscription"]["unit"]) == "2.495 kr./md."
    # One flat subscription: the price is stated without "Fra" (it implied a tier ladder that does not exist).
    assert "{pMonthly}/md." in site and "Fra {pMonthly}" not in site
    # llms.txt is static text, read by AI crawlers: it states the Danish prices literally.
    llms = (ROOT / "web/public/llms.txt").read_text(encoding="utf-8")
    assert "2.495 kr." in llms and "4 kr. pr." in llms and "2 kr. pr." in llms and "5.000 kr." in llms and "ekskl. moms" in llms
    assert "300 minutter" in llms and "1,50 kr." in llms


def test_the_website_price_table_is_the_markets_table():
    # web/src/lib/prices.json is generated from markets.py (scripts/export_prices.py) and its DKK row is prices.py.
    table = json.loads((ROOT / "web/src/lib/prices.json").read_text(encoding="utf-8"))
    assert {k: v for k, v in table.items() if k != "_comment"} == {k: v for k, v in markets.export().items() if k != "_comment"}
    assert table["erhverv"]["DKK"] == {
        "monthly": prices.SUBSCRIPTION_MONTHLY_NET_MINOR, "call": prices.CAMPAIGN_CALL_NET_MINOR,
        "minute": prices.CAMPAIGN_MINUTE_NET_MINOR, "extra_minute": prices.INBOUND_EXTRA_MINUTE_NET_MINOR,
        "setup": prices.SPECIALIST_SETUP_NET_MINOR}
    assert table["privat"]["DKK"] == {p["key"]: {"monthly": p["monthly_minor"], "yearly_monthly": p["yearly_monthly_minor"],
                                                 "yearly_total": p["yearly_total_minor"]} for p in prices.PRIVAT_PLANS}
    assert table["privatCreditPack"]["DKK"] == prices.PRIVAT_CREDIT_PACK_GROSS_MINOR
    assert table["inboundIncludedMinutes"] == prices.INBOUND_INCLUDED_MINUTES and table["privatTrialDays"] == prices.PRIVAT_TRIAL_DAYS
    assert table["localeCurrency"] == {"da": "DKK", "sv": "SEK", "no": "NOK", "en": "EUR", "de": "EUR", "es": "EUR", "fr": "EUR", "it": "EUR"}


def test_eur_languages_state_no_amount_in_kroner():
    # The bug this guards: every language showed the Danish amounts with "kr." (en "2,495 kr./month"). EUR markets'
    # texts carry tokens; a competitor's Danish price is written currency-first ("DKK 899").
    kroner = re.compile(r"\d[\d.,\u00a0 ]*\s?(?:kr\b\.?|DKK\b)")
    hits = []
    for loc in ("en", "de", "es", "fr", "it"):
        for f in sorted((ROOT / f"web/src/i18n/messages/{loc}").glob("*.json")):
            for n, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
                if kroner.search(line):
                    hits.append(f"{loc}/{f.name}:{n}: {line.strip()[:110]}")
    assert not hits, "amount in kroner in a EUR text:\n" + "\n".join(hits)

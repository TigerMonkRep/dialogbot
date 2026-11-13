"""One offer, written once (Fürster's decision 2026-11-10): the subscription from 2.495 kr./md. with a package of 300
minutes a month shared by inbound and outbound calls, then 1,50 kr. per started inbound minute and 2 kr. per started
outbound minute – no price per call – and 5.000 kr. for specialist setup, all excl. VAT.
These tests keep the old prices (1.495 kr., 149 kr. per approved enquiry, 9 kr. per contact, 4 kr. per outbound call,
"300 minutes of inbound calls") from creeping back into any text a customer, a visitor, a salesperson or an AI can read."""
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
# The per-call fee and the inbound-only package, gone since 2026-11-10 (design-reference mock-ups are history).
OLD_CALL_FEE = re.compile(r"4 kr\. pr\. (udgående )?(kampagne)?opkald|\{pCall\}|\{pCall3Min\}|minutters indgående opkald|"
                          r"300 indgående minutter")
CALL_FEE_ALLOWED = ALLOWED | {"app/modules/sales/outbound.py"}


def _files():
    for entry in SCANNED:
        p = ROOT / entry
        for f in ([p] if p.is_file() else sorted(p.rglob("*"))):
            if f.is_file() and f.suffix in SUFFIXES and "node_modules" not in f.parts and ".next" not in f.parts \
                    and "__pycache__" not in f.parts:
                yield f


def test_list_prices():
    assert prices.SUBSCRIPTION_MONTHLY_NET_MINOR == 249_500 and not hasattr(prices, "CAMPAIGN_CALL_NET_MINOR")  # no per-call fee
    assert prices.INCLUDED_MINUTES == prices.INBOUND_INCLUDED_MINUTES == 300  # one package for inbound and outbound
    assert prices.OUTBOUND_EXTRA_MINUTE_NET_MINOR == 200 and prices.INBOUND_EXTRA_MINUTE_NET_MINOR == 150
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


def test_the_per_call_fee_and_the_inbound_only_package_are_gone():
    hits = []
    for f in _files():
        rel = f.relative_to(ROOT).as_posix()
        if rel in CALL_FEE_ALLOWED or rel.startswith("design-reference/"):
            continue
        for n, line in enumerate(f.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
            if OLD_CALL_FEE.search(line):
                hits.append(f"{rel}:{n}: {line.strip()[:110]}")
    assert not hits, "per-call fee or inbound-only package found:\n" + "\n".join(hits)


def test_the_terms_state_the_shared_package_in_every_language():
    """Terms version 2 (from 10 November 2026): one package for inbound and outbound minutes, no price per call, the
    minute prices above it per direction, credits only after a complaint about a call."""
    for loc in ("da", "en", "de", "es", "fr", "it", "no", "sv"):
        terms = json.loads((ROOT / f"web/src/i18n/messages/{loc}/legal.json").read_text(encoding="utf-8"))["terms"]
        assert terms["updated"].split()[1] == "2" and "2026" in terms["updated"], loc
        text = json.dumps(terms, ensure_ascii=False)
        assert "{pExtraMinute}" in text and "{pMinute}" in text and "300" in text, loc
        assert "{pCall}" not in text and "pTermsV1Call" not in text and "{pCallAnswered}" in text, loc
    da = json.dumps(json.loads((ROOT / "web/src/i18n/messages/da/legal.json").read_text(encoding="utf-8"))["terms"],
                    ensure_ascii=False)
    assert "Version 2 · gældende fra 10. november 2026." in da and "ingen pris pr. opkald" in da
    assert "fælles pulje til både indgående opkald og udgående kampagneopkald" in da and "klager over et bestemt opkald" in da


def _da_render(text: str) -> str:
    """The Danish site renders {p…} tokens with the DKK row of prices.json (web/src/lib/markets.ts); markets.fmt writes
    DKK as the site does ("2.495 kr.", "1,50 kr.", with a plain space on the site), so this mirrors what a Danish visitor reads."""
    e = markets.ERHVERV["DKK"]
    values = {"pMonthly": e["monthly"], "pMinute": e["outbound_extra_minute"], "pExtraMinute": e["extra_minute"],
              "pSetup": e["setup"]}
    out = text.replace("{pIncluded}", str(markets.INCLUDED_MINUTES))
    for k, minor in values.items():
        out = out.replace("{" + k + "}", markets.fmt(minor, "DKK").replace("\u00a0", " "))  # the site: plain spaces
    for k, minor in {"pMonthlyNum": e["monthly"], "pMinuteNum": e["outbound_extra_minute"], "pSetupNum": e["setup"]}.items():
        out = out.replace("{" + k + "}", prices.kr(minor))
    return out.replace("{pCur}", "kr.").replace("{pIncluded}", str(markets.INBOUND_INCLUDED_MINUTES))


def test_the_public_pages_state_both_prices():
    # The page texts live in the Danish source dictionaries (web/src/i18n/messages/da) and state every price as a
    # {p…} token, filled in per market by the translator – so a price is written once (prices.json), never in copy.
    pricing = (ROOT / "web/src/i18n/messages/da/landing.json").read_text(encoding="utf-8")
    site = (ROOT / "web/src/i18n/messages/da/site.json").read_text(encoding="utf-8")  # front page + build guide
    for text in (pricing, site):
        assert "{pMonthly}" in text and ("{pMinute} pr." in text or "{pMinuteNum}" in text) and "{pSetup}" in text and "ekskl. moms" in text
        assert "{pCall}" not in text and "ingen pris pr. opkald" in text.lower()
        assert not re.search(r"\d\s?kr\.", re.sub(r"(400|600) kr\.", "", text)), "a hard-coded amount in kroner"
    assert "{pIncluded} minutter" in pricing and "{pExtraMinute}" in pricing  # the package and the price above it
    # Rendered for a Danish visitor, the copy states the same amounts as always.
    rendered = _da_render(pricing)
    assert "2.495 kr." in rendered and "4 kr. pr." not in rendered and "2 kr. pr." in rendered and "5.000 kr." in rendered
    assert "1,50 kr." in rendered and "300 minutter om måneden" in rendered and "ind- og udgående" in rendered
    # The big price figures on the front page: amount and unit side by side.
    site_json = json.loads(site)
    assert _da_render(site_json["prices"]["monthly"]) + " " + _da_render(site_json["home"]["price"]["subscription"]["unit"]) == "2.495 kr./md."
    # One flat subscription: the price is stated without "Fra" (it implied a tier ladder that does not exist).
    assert "{pMonthly}/md." in site and "Fra {pMonthly}" not in site
    # llms.txt is static text, read by AI crawlers: it states the Danish prices literally.
    llms = (ROOT / "web/public/llms.txt").read_text(encoding="utf-8")
    assert "2.495 kr." in llms and "4 kr. pr." not in llms and "2 kr. pr." in llms and "5.000 kr." in llms and "ekskl. moms" in llms
    assert "300 minutter om måneden til både indgående opkald og udgående kampagneopkald" in llms and "1,50 kr." in llms
    assert "ingen pris pr. opkald" in llms


def test_the_website_price_table_is_the_markets_table():
    # web/src/lib/prices.json is generated from markets.py (scripts/export_prices.py) and its DKK row is prices.py.
    table = json.loads((ROOT / "web/src/lib/prices.json").read_text(encoding="utf-8"))
    assert {k: v for k, v in table.items() if k != "_comment"} == {k: v for k, v in markets.export().items() if k != "_comment"}
    assert table["erhverv"]["DKK"] == {
        "monthly": prices.SUBSCRIPTION_MONTHLY_NET_MINOR, "extra_minute": prices.INBOUND_EXTRA_MINUTE_NET_MINOR,
        "outbound_extra_minute": prices.OUTBOUND_EXTRA_MINUTE_NET_MINOR, "call_answered": prices.OUTBOUND_CALL_ANSWERED_NET_MINOR,
        "call_voicemail": prices.OUTBOUND_CALL_VOICEMAIL_NET_MINOR, "call_no_answer": prices.OUTBOUND_CALL_NO_ANSWER_NET_MINOR,
        "setup": prices.SPECIALIST_SETUP_NET_MINOR}
    assert table["privat"]["DKK"] == {p["key"]: {"monthly": p["monthly_minor"], "yearly_monthly": p["yearly_monthly_minor"],
                                                 "yearly_total": p["yearly_total_minor"]} for p in prices.PRIVAT_PLANS}
    assert table["privatExtraCall"]["DKK"] == {"answered": 500, "voicemail": 125, "no_answer": 31, "minute": 250, "max": 1750}
    assert table["privatTopups"]["DKK"] == list(prices.PRIVAT_TOPUPS_GROSS_MINOR) and "privatCreditPack" not in table
    assert table["privatBalance"]["DKK"] == {"welcome": 1000, "referral": 1000, "extra_task": 300}
    assert table["includedMinutes"] == prices.INCLUDED_MINUTES and table["privatTrialDays"] == prices.PRIVAT_TRIAL_DAYS
    assert table["localeCurrency"] == {"da": "DKK", "sv": "SEK", "no": "NOK", "en": "EUR", "de": "EUR", "es": "EUR", "fr": "EUR", "it": "EUR", "us": "USD"}


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


LOCALES = ("da", "en", "de", "es", "fr", "it", "no", "sv")
# "per started minute" in each language: the amounts are billed per started minute (statement rounds each call up)
STARTED = {"da": "påbegyndt", "en": "started", "de": "angefangene", "es": "iniciado", "fr": "entamée", "it": "iniziato",
           "no": "påbegynt", "sv": "påbörjad"}


def _msg(loc: str, file: str, key: str) -> str:
    v = json.loads((ROOT / f"web/src/i18n/messages/{loc}/{file}").read_text(encoding="utf-8"))
    for k in key.split("."):
        v = v[k]
    return v


def _passed_vars(tsx: str, key: str) -> set[str]:
    """The variable names a page passes to t("<key>", { … }) (one call, on one line)."""
    src = (ROOT / tsx).read_text(encoding="utf-8")
    m = re.search(r't\("' + re.escape(key) + r'", \{(.*?)\}\)\}', src, re.S)
    assert m, f"{tsx}: t({key!r}, …) not found"
    return set(re.findall(r"(\w+):", m.group(1)))


def test_the_texts_a_customer_accepts_state_every_call_price_and_the_started_minute():
    """F-VR-06: the offer (/tilbud) and the campaign start dialog are what a customer accepts. Both state all three call
    prices after the package (answered / voicemail / no answer) and that a minute is billed per started minute, in every
    language – with the amounts passed in from the API (agreements.offer_call_prices / the campaign's call_prices)."""
    texts = {("auth.json", "offer.outboundValue"): ({"call", "voicemail", "noAnswer", "minute"}, "web/src/app/tilbud/[token]/page.tsx"),
             ("app.json", "campaigns.start.body"): ({"answered", "voicemail", "noAnswer", "minute"},
                                                    "web/src/app/app/(admin)/kampagner/client.tsx")}
    for (file, key), (needed, tsx) in texts.items():
        passed = _passed_vars(tsx, key)
        for loc in LOCALES:
            s = _msg(loc, file, key)
            used = set(re.findall(r"\{(\w+)\}", s))
            assert needed <= used, (loc, key, needed - used)
            assert used <= passed, (loc, key, "not passed by the page", used - passed)
            assert STARTED[loc] in s, (loc, key, "per started minute")
            assert not re.search(r"\d", s), (loc, key, "a hard-coded amount")


def test_a_big_price_figure_carries_its_currency_once():
    """F-VR-05: a big price figure is an amount plus a unit beside it. Either the amount has the currency ({pX}) and the
    unit has none, or the amount is bare ({pXNum}) and the unit carries {pCur} – en showed a bare "0.55"."""
    pairs = [("prices.monthly", "home.price.subscription.unit"), ("prices.perCall", "home.price.campaign.unit"),
             ("prices.perCall", "guide.pricing.campaign.unit")]
    for loc in LOCALES:
        for amount_key, unit_key in pairs:
            amount, unit = _msg(loc, "site.json", amount_key), _msg(loc, "site.json", unit_key)
            assert re.fullmatch(r"\{p\w+\}", amount), (loc, amount_key, amount)
            bare = amount.endswith("Num}")
            assert bare == ("{pCur}" in unit), (loc, amount_key, amount, unit_key, unit)


# F-PDEC-03 (Fürster 2026-11-11): Dialogbot Privat's own consumer terms (/privat/vilkaar, legal.json → privatTerms).
# Every price in them is a {p…} token; each token below names where its amount lives in web/src/lib/prices.json (the
# export of app/modules/billing/markets.py) – per currency, so every market's terms state its own prices.
PRIVAT_TERMS_TOKENS = {
    **{f"p{name}": ("privat", plan, "monthly") for name, plan in (("Basis", "basis"), ("Plus", "plus"), ("Familie", "familie"))},
    **{f"p{name}Year": ("privat", plan, "yearly_monthly") for name, plan in (("Basis", "basis"), ("Plus", "plus"), ("Familie", "familie"))},
    **{f"p{name}YearTotal": ("privat", plan, "yearly_total") for name, plan in (("Basis", "basis"), ("Plus", "plus"), ("Familie", "familie"))},
    "pXAnswered": ("privatExtraCall", "answered"), "pXVoicemail": ("privatExtraCall", "voicemail"),
    "pXNoAnswer": ("privatExtraCall", "no_answer"), "pXMinute": ("privatExtraCall", "minute"), "pXMax": ("privatExtraCall", "max"),
    "pTopup1": ("privatTopups", 0), "pTopup2": ("privatTopups", 1), "pTopup3": ("privatTopups", 2),
    "pWelcome": ("privatBalance", "welcome"), "pReferral": ("privatBalance", "referral"),
    "pExtraTask": ("privatBalance", "extra_task"), "pTrialDays": ("privatTrialDays",),
}
# Amounts written out instead of a token ("49 kr.", "€6.49", "17,50 DKK") – the terms must carry none.
WRITTEN_AMOUNT = re.compile(r"\d[\d.,  ]*\s?(?:kr\b\.?|DKK|SEK|NOK|EUR|€)|€\s?\d")


def test_the_privat_terms_exist_in_every_language_with_every_price_from_prices_json():
    from app.modules.privat import market

    table = json.loads((ROOT / "web/src/lib/prices.json").read_text(encoding="utf-8"))
    ts_tokens = set(re.findall(r'"(p\w+)"', re.search(r"PRICE_TOKENS = \[([^\]]*)\]",
                                                      (ROOT / "web/src/lib/markets.ts").read_text(encoding="utf-8")).group(1)))
    for token, path in PRIVAT_TERMS_TOKENS.items():
        assert token in ts_tokens, (token, "not filled in by lib/markets.ts")
        for cur in table["currencies"]:
            v = table
            for i, k in enumerate(path):
                v = v[k]
                if i == 0 and k != "privatTrialDays":
                    v = v[cur]  # every price table is per currency
            assert isinstance(v, int) and v > 0, (token, cur, path)
    da = json.loads((ROOT / "web/src/i18n/messages/da/legal.json").read_text(encoding="utf-8"))["privatTerms"]
    for loc in LOCALES:
        terms = json.loads((ROOT / f"web/src/i18n/messages/{loc}/legal.json").read_text(encoding="utf-8"))["privatTerms"]
        text = json.dumps(terms, ensure_ascii=False)
        used = set(re.findall(r"\{(p[A-Z]\w*)\}", text))
        assert used <= set(PRIVAT_TERMS_TOKENS), (loc, "token without a prices.json source", used - set(PRIVAT_TERMS_TOKENS))
        assert used == set(PRIVAT_TERMS_TOKENS), (loc, "price missing from the terms", set(PRIVAT_TERMS_TOKENS) - used)
        assert not WRITTEN_AMOUNT.search(text), (loc, "a written-out amount", WRITTEN_AMOUNT.search(text).group(0))
        # versioned like the business terms v2; the version is the one Stripe Checkout records (terms_version)
        assert terms["version"] == market.TERMS_VERSION, loc
        assert re.search(rf"\b{market.TERMS_VERSION}\b", terms["updated"]) and "2026" in terms["updated"], loc
        assert [len(s["body"]) for s in terms["sections"]] == [len(s["body"]) for s in da["sections"]], loc
        assert "/privatliv" in text and "forbrug.dk" in text and "Forbrugerklagenævnet" in text, loc
        refund = terms["sections"][7]["body"][5]  # 8. Opkaldssaldo: no refund on cancel/delete, no «write to us first»
        assert refund["type"] == "p" and "parts" not in refund and "14" in refund["text"], loc
    assert "Version 1 · gældende fra 11. november 2026." == da["updated"]
    da_text = json.dumps(da, ensure_ascii=False)
    for promise in ("14 dages fortrydelsesret", "én prøveperiode pr. konto og pr. betalingskort",
                    "udløber ikke, så længe kontoen findes", "slettes efter 90 dage", "gælder i 7 dage",
                    "tilbagekalder vi adgangen hos Google", "«Annonce»", "30 dages varsel", "fair use",
                    # Fürster 2026-11-11: no refund of unused balance on cancel/delete – only the 14-day withdrawal
                    "ubrugt saldo refunderes ikke", "den ubrugte del af den optankning"):
        assert promise.lower() in da_text.lower(), promise
    # the page, and every Privat place that leads to a Checkout, links the Privat terms – never the business terms
    page = (ROOT / "web/src/app/privat/vilkaar/page.tsx").read_text(encoding="utf-8")
    assert '"legal.privatTerms.sections"' in page and 'audience="privat"' in page
    landing = (ROOT / "web/src/app/privat/page.tsx").read_text(encoding="utf-8")
    assert 'href="/privat/vilkaar"' in landing and 'href="/vilkaar"' not in landing
    for f in ("account.tsx", "sheets.tsx"):
        assert 'href="/privat/vilkaar"' in (ROOT / f"web/src/components/privat/{f}").read_text(encoding="utf-8"), f

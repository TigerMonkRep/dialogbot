"""Markets: the list prices per currency and the VAT rule per country. The one place a foreign price is written.

Dialogbot sells in four currencies. The Danish prices in `prices.py` stay the source; the other currencies are rounded
list prices set from them (not live conversions – a price does not move with the exchange rate):

    1 EUR ≈ 7,46 DKK (pegged) · 1 DKK ≈ 1,47 SEK · 1 DKK ≈ 1,58 NOK  (rates of early November 2026)

Which currency a customer pays in:
- Erhverv: the company's country (BusinessProfile.country) – DK → DKK, SE → SEK, NO → NOK, everything else → EUR.
  The agreement snapshots it, so a customer keeps the currency (and price) it signed at.
- Privat: the visitor's language when they start the checkout (da → DKK, sv → SEK, no → NOK, others → EUR).
- The website shows the prices of the language's market (`LOCALE_CURRENCY`).

VAT (confirm with the accountant before the first foreign sale – these are the rules the code follows):
- Erhverv (B2B), invoiced monthly in arrears:
  · Danish company → 25 % Danish VAT.
  · Company elsewhere in the EU → no VAT, reverse charge (art. 196 of the VAT Directive). Needs the customer's VAT
    number, so an EU company outside Denmark must give one before its card is saved.
  · Company outside the EU (Norway …) → no Danish VAT; the customer accounts for VAT in its own country.
- Privat (B2C), prices INCLUDE VAT and are the same gross price in every country of a currency:
  · `PRIVAT_EU_VAT_MODE=danish` (default): 25 % Danish VAT for every EU consumer. Allowed while Dialogbot's
    cross-border B2C sales in the EU stay under 10.000 EUR a year.
  · `PRIVAT_EU_VAT_MODE=destination`: the consumer's own country's rate (needs OSS registration at Skattestyrelsen).
  · Norway: no VAT until Dialogbot is VOEC-registered (`NO_VOEC_REGISTERED=true`, required above 50.000 NOK a year
    of sales to Norwegian consumers), then 25 % Norwegian VAT.
  · Other countries outside the EU: no VAT.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.modules.billing import prices

Currency = Literal["DKK", "SEK", "NOK", "EUR"]
CURRENCIES: tuple[Currency, ...] = ("DKK", "SEK", "NOK", "EUR")

# Standard VAT rates in the EU (basis points), 2026. Only the rate matters here, not reduced rates.
EU_VAT_BP: dict[str, int] = {
    "AT": 2000, "BE": 2100, "BG": 2000, "CY": 1900, "CZ": 2100, "DE": 1900, "DK": 2500, "EE": 2400, "ES": 2100,
    "FI": 2550, "FR": 2000, "GR": 2400, "HR": 2500, "HU": 2700, "IE": 2300, "IT": 2200, "LT": 2100, "LU": 1700,
    "LV": 2100, "MT": 1800, "NL": 2100, "PL": 2300, "PT": 2300, "RO": 2100, "SE": 2500, "SI": 2200, "SK": 2300,
}
NO_VAT_BP = 2500
DK_VAT_BP = prices.TAX_BASIS_POINTS

COUNTRY_CURRENCY: dict[str, Currency] = {"DK": "DKK", "SE": "SEK", "NO": "NOK"}
LOCALE_CURRENCY: dict[str, Currency] = {"da": "DKK", "sv": "SEK", "no": "NOK", "en": "EUR", "de": "EUR", "es": "EUR",
                                        "fr": "EUR", "it": "EUR"}
# The country a language most likely means (used for Privat's VAT before Stripe knows the billing address).
LOCALE_COUNTRY: dict[str, str | None] = {"da": "DK", "sv": "SE", "no": "NO", "de": "DE", "es": "ES", "fr": "FR",
                                         "it": "IT", "en": None}

# --------------------------------------------------------------------------- Erhverv (excl. VAT, minor units)
# monthly · campaign call · campaign minute · inbound minute above the included 300 · specialist setup ·
# call_* = the outbound call price by outcome decided 2026-11-10 (prices.OUTBOUND_CALL_*; the same keys and values as
# on qa/decisions-2026-11-10: the DKK price × the market's factor SEK 1,475, NOK 1,575, EUR 0,135, rounded to 5 öre /
# 5 øre / 1 cent). Dialogbot Privat's extra calls are priced from call_* and minute (privat_extra_call).
ERHVERV: dict[Currency, dict[str, int]] = {
    "DKK": {"monthly": prices.SUBSCRIPTION_MONTHLY_NET_MINOR, "call": prices.CAMPAIGN_CALL_NET_MINOR,
            "minute": prices.CAMPAIGN_MINUTE_NET_MINOR, "extra_minute": prices.INBOUND_EXTRA_MINUTE_NET_MINOR,
            "call_answered": prices.OUTBOUND_CALL_ANSWERED_NET_MINOR,
            "call_voicemail": prices.OUTBOUND_CALL_VOICEMAIL_NET_MINOR,
            "call_no_answer": prices.OUTBOUND_CALL_NO_ANSWER_NET_MINOR, "setup": prices.SPECIALIST_SETUP_NET_MINOR},
    "SEK": {"monthly": 369_500, "call": 590, "minute": 295, "extra_minute": 220, "call_answered": 590,
            "call_voicemail": 150, "call_no_answer": 35, "setup": 729_500},
    "NOK": {"monthly": 399_500, "call": 630, "minute": 315, "extra_minute": 235, "call_answered": 630,
            "call_voicemail": 160, "call_no_answer": 40, "setup": 789_500},
    "EUR": {"monthly": 32_900, "call": 55, "minute": 27, "extra_minute": 20, "call_answered": 55,
            "call_voicemail": 14, "call_no_answer": 3, "setup": 66_900},
}
INBOUND_INCLUDED_MINUTES = prices.INBOUND_INCLUDED_MINUTES

# --------------------------------------------------------------------------- Privat (INCL. VAT, minor units)
# The yearly plan is paid once a year (yearly_total = 12 × yearly_monthly), about 20 % below monthly.
_DKK_PLANS = {p["key"]: p for p in prices.PRIVAT_PLANS}
PRIVAT: dict[Currency, dict[str, dict[str, int]]] = {
    "DKK": {k: {"monthly": p["monthly_minor"], "yearly_monthly": p["yearly_monthly_minor"],
                "yearly_total": p["yearly_total_minor"]} for k, p in _DKK_PLANS.items()},
    "SEK": {"basis": {"monthly": 6900, "yearly_monthly": 5500, "yearly_total": 66000},
            "plus": {"monthly": 14900, "yearly_monthly": 11900, "yearly_total": 142800},
            "familie": {"monthly": 24900, "yearly_monthly": 19900, "yearly_total": 238800}},
    "NOK": {"basis": {"monthly": 7900, "yearly_monthly": 6300, "yearly_total": 75600},
            "plus": {"monthly": 15900, "yearly_monthly": 12700, "yearly_total": 152400},
            "familie": {"monthly": 26900, "yearly_monthly": 21500, "yearly_total": 258000}},
    "EUR": {"basis": {"monthly": 649, "yearly_monthly": 519, "yearly_total": 6228},
            "plus": {"monthly": 1349, "yearly_monthly": 1079, "yearly_total": 12948},
            "familie": {"monthly": 2249, "yearly_monthly": 1799, "yearly_total": 21588}},
}
# Dialogbot Privat's extra calls (beyond the plan's calls a month), Fürster's decision 2026-11-11: Erhverv's net price
# by outcome (decided 2026-11-10) + 25 % moms – the Privat rule in every currency (the same gross price in every
# country of a currency, Danish VAT, see the module docstring) – rounded half up to a whole øre/öre/cent ONCE, in
# prices.gross_minor.
# answered / voicemail / no_answer: the call by outcome; minute: per started minute of conversation (answered calls);
# max: the most one extra call costs (Erhverv's max per contact: 2 attempts answered + 3 minutes) = what is reserved.
EXTRA_CALL_OUTCOMES = ("answered", "voicemail", "no_answer")


def privat_extra_call(currency: str) -> dict[str, int]:
    e = ERHVERV[_cur(currency)]
    cap = prices.MAX_PER_CONTACT_ATTEMPTS * e["call_answered"] + prices.MAX_PER_CONTACT_MINUTES * e["minute"]
    return {"answered": prices.gross_minor(e["call_answered"]), "voicemail": prices.gross_minor(e["call_voicemail"]),
            "no_answer": prices.gross_minor(e["call_no_answer"]), "minute": prices.gross_minor(e["minute"]),
            "max": prices.gross_minor(cap)}


def privat_extra_call_price(currency: str, outcome: str, minutes: int) -> int:
    """What one extra call costs: its outcome price + started minutes (only an answered call has minutes), never more
    than `max`."""
    p = privat_extra_call(currency)
    if outcome not in EXTRA_CALL_OUTCOMES:
        raise ValueError(f"unknown outcome {outcome!r}")
    return min(p[outcome] + (max(0, minutes) * p["minute"] if outcome == "answered" else 0), p["max"])


def privat_extra_call_text(currency: str = "DKK") -> str:
    """«5 kr. besvaret, 1,25 kr. telefonsvarer, 0,31 kr. ubesvaret + 2,50 kr. pr. påbegyndt minut, højst 17,50 kr.»"""
    p = privat_extra_call(currency)
    f = lambda k: fmt(p[k], currency)  # noqa: E731
    return (f"{f('answered')} besvaret, {f('voicemail')} telefonsvarer, {f('no_answer')} ubesvaret + {f('minute')} pr. "
            f"påbegyndt minut, højst {f('max')}")


def privat_from_dkk(dkk_minor: int, currency: str, *, whole: bool = False) -> int:
    """A Privat amount set in DKK (top-ups, bonuses, the extra task) in another currency: × the market's factor (the
    ratio of Erhverv's minute price to the Danish one: SEK 1,475, NOK 1,575, EUR 0,135), rounded half up to a whole
    öre/øre/cent – or with `whole` to a whole krona/krone/euro (top-ups are round amounts)."""
    c = _cur(currency)
    num, den = ERHVERV[c]["minute"], ERHVERV["DKK"]["minute"]
    unit = 100 if whole else 1
    return (dkk_minor * num + den * unit // 2) // (den * unit) * unit


def privat_topups(currency: str) -> tuple[int, ...]:
    return tuple(privat_from_dkk(a, currency, whole=True) for a in prices.PRIVAT_TOPUPS_GROSS_MINOR)


PRIVAT_EXTRA_CALL: dict[Currency, dict[str, int]] = {}
PRIVAT_TOPUPS: dict[Currency, tuple[int, ...]] = {}


def currency_for_country(country: str | None) -> Currency:
    return COUNTRY_CURRENCY.get((country or "DK").upper(), "EUR")


def currency_for_locale(locale: str | None) -> Currency:
    return LOCALE_CURRENCY.get((locale or "da").lower(), "DKK")


def erhverv_price(currency: str, item: str) -> int:
    return ERHVERV[_cur(currency)][item]


def privat_plan(currency: str, plan: str) -> dict[str, int]:
    return PRIVAT[_cur(currency)][plan]


def _cur(currency: str) -> Currency:
    c = (currency or "DKK").upper()
    if c not in CURRENCIES:
        raise ValueError(f"unknown currency {currency!r}")
    return c  # type: ignore[return-value]


PRIVAT_EXTRA_CALL.update({c: privat_extra_call(c) for c in CURRENCIES})
PRIVAT_TOPUPS.update({c: privat_topups(c) for c in CURRENCIES})


# --------------------------------------------------------------------------- VAT

@dataclass(frozen=True)
class Vat:
    """What VAT an invoice or checkout line carries. `rate_bp` 0 with a `note` = the note must be printed."""
    rate_bp: int
    kind: Literal["domestic", "reverse_charge", "outside_eu", "destination", "none"]
    country: str | None = None  # whose VAT it is (DK for Danish VAT)
    note: str | None = None


REVERSE_CHARGE_NOTE = ("Reverse charge: VAT to be accounted for by the recipient (Article 196, Council Directive "
                       "2006/112/EC). Omvendt betalingspligt.")
OUTSIDE_EU_NOTE = "Not subject to Danish VAT: the service is supplied to a business outside the EU (place of supply)."


class VatNumberRequired(ValueError):
    """An EU company outside Denmark must give its VAT number before it can be invoiced without VAT."""


def is_eu(country: str | None) -> bool:
    return (country or "").upper() in EU_VAT_BP


def erhverv_vat(country: str | None, vat_number: str | None) -> Vat:
    """VAT on an Erhverv (B2B) invoice for a company in `country` with `vat_number` (may be empty)."""
    c = (country or "DK").upper()
    if c == "DK":
        return Vat(DK_VAT_BP, "domestic", "DK")
    if c in EU_VAT_BP:
        if not (vat_number or "").strip():
            raise VatNumberRequired(c)
        return Vat(0, "reverse_charge", c, REVERSE_CHARGE_NOTE)
    return Vat(0, "outside_eu", c, OUTSIDE_EU_NOTE)


def privat_vat(country: str | None, *, eu_mode: str = "danish", voec_registered: bool = False) -> Vat:
    """VAT included in a Privat (B2C) price for a consumer in `country`."""
    c = (country or "DK").upper()
    if c in EU_VAT_BP:
        if eu_mode == "destination":
            return Vat(EU_VAT_BP[c], "destination", c)
        return Vat(DK_VAT_BP, "domestic", "DK")
    if c == "NO":
        return Vat(NO_VAT_BP, "destination", "NO") if voec_registered else Vat(0, "none", None)
    return Vat(0, "none", None)


def privat_checkout_rates(*, eu_mode: str = "danish", voec_registered: bool = False) -> list[Vat]:
    """The distinct inclusive VAT rates a Privat checkout may apply (Stripe picks one by the billing country)."""
    if eu_mode == "destination":
        out = [Vat(bp, "destination", c) for c, bp in sorted(EU_VAT_BP.items())]
    else:
        out = [Vat(DK_VAT_BP, "domestic", "DK")]
    if voec_registered:
        out.append(Vat(NO_VAT_BP, "destination", "NO"))
    return out


# --------------------------------------------------------------------------- display

_SYMBOL = {"DKK": "kr.", "SEK": "kr", "NOK": "kr", "EUR": "€"}


def fmt(minor: int, currency: str) -> str:
    """Plain display for invoice lines and texts: "2.495 kr." · "3 695 kr" · "€329" · "€0.55" (decimals only when
    needed; Danish separators for DKK, Scandinavian for SEK/NOK, English-style € for EUR)."""
    c = _cur(currency)
    whole, cents = divmod(abs(minor), 100)
    sign = "-" if minor < 0 else ""
    if c == "EUR":
        w = f"{whole:,}"
        return f"{sign}€{w}" + (f".{cents:02d}" if cents else "")
    sep = "." if c == "DKK" else " "
    w = f"{whole:,}".replace(",", sep)
    dec = f",{cents:02d}" if cents else ""
    return f"{sign}{w}{dec} {_SYMBOL[c]}"


def export() -> dict:
    """Everything the website needs, written to web/src/lib/prices.json by scripts/export_prices.py (CI checks it)."""
    return {
        "_comment": "Generated by scripts/export_prices.py from app/modules/billing/markets.py – do not edit by hand.",
        "currencies": list(CURRENCIES),
        "localeCurrency": LOCALE_CURRENCY,
        "inboundIncludedMinutes": INBOUND_INCLUDED_MINUTES,
        "privatTrialDays": prices.PRIVAT_TRIAL_DAYS,
        "erhverv": ERHVERV,
        "privat": PRIVAT,
        "privatExtraCall": PRIVAT_EXTRA_CALL,
        "privatTopups": {c: list(v) for c, v in PRIVAT_TOPUPS.items()},
        # the Opkaldssaldo's bonuses and the extra task in each currency (privat_from_dkk), for the website's texts
        "privatBalance": {c: {"welcome": privat_from_dkk(prices.PRIVAT_WELCOME_BONUS_MINOR, c),
                              "referral": privat_from_dkk(prices.PRIVAT_REFERRAL_BONUS_MINOR, c),
                              "extra_task": privat_from_dkk(prices.PRIVAT_EXTRA_TASK_MINOR, c)} for c in CURRENCIES},
    }

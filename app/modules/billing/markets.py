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
# monthly · inbound minute above the package · outbound (campaign) minute above the package · specialist setup
ERHVERV: dict[Currency, dict[str, int]] = {
    # extra_minute = inbound minute above the package, outbound_extra_minute = campaign minute above it (the market's
    # equivalent of 2 kr.); the package itself (INCLUDED_MINUTES) is the same everywhere. No fee per call.
    "DKK": {"monthly": prices.SUBSCRIPTION_MONTHLY_NET_MINOR, "extra_minute": prices.INBOUND_EXTRA_MINUTE_NET_MINOR,
            "outbound_extra_minute": prices.OUTBOUND_EXTRA_MINUTE_NET_MINOR, "setup": prices.SPECIALIST_SETUP_NET_MINOR},
    "SEK": {"monthly": 369_500, "extra_minute": 220, "outbound_extra_minute": 295, "setup": 729_500},
    "NOK": {"monthly": 399_500, "extra_minute": 235, "outbound_extra_minute": 315, "setup": 789_500},
    "EUR": {"monthly": 32_900, "extra_minute": 20, "outbound_extra_minute": 27, "setup": 66_900},
}
INBOUND_INCLUDED_MINUTES = prices.INBOUND_INCLUDED_MINUTES
INCLUDED_MINUTES = prices.INCLUDED_MINUTES

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
# Ten Privat credits ("ekstra opkald"), incl. VAT.
PRIVAT_CREDIT_PACK: dict[Currency, int] = {"DKK": prices.PRIVAT_CREDIT_PACK_GROSS_MINOR, "SEK": 4500, "NOK": 4500,
                                           "EUR": 399}


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
        "includedMinutes": INCLUDED_MINUTES,  # the package: inbound and outbound minutes together
        "privatTrialDays": prices.PRIVAT_TRIAL_DAYS,
        "erhverv": ERHVERV,
        "privat": PRIVAT,
        "privatCreditPack": PRIVAT_CREDIT_PACK,
    }

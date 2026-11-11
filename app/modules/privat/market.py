"""Dialogbot Privat's markets at Stripe Checkout (docs/markets.md): language → currency, Stripe locale and VAT.

- Currency: a customer keeps the currency of its first Checkout (private_subscriptions.currency); before that the
  visitor's language decides (markets.currency_for_locale: da → DKK, sv → SEK, no → NOK, others → EUR).
- Stripe's Checkout locale is the language (Norwegian is "nb" at Stripe).
- VAT: prices include VAT. The line carries ONE inclusive Stripe tax rate, chosen by the country the language most
  likely means (markets.LOCALE_COUNTRY; "en" → Denmark's rules) through markets.privat_vat with PRIVAT_EU_VAT_MODE and
  NO_VOEC_REGISTERED. Stripe's `dynamic_tax_rates` (rate picked by the billing address) is deprecated, is no longer in
  the current Checkout API and never supported Norway; and in the default "danish" mode every EU consumer pays the
  Danish rate, which an address-matched DK rate would not give a German address. So a fixed `tax_rates` entry is used.
  A rate of 0 (Norway before VOEC, countries outside the EU) means no tax rate on the line.
- STRIPE_TAX_ENABLED=true: Stripe Tax decides instead (from the billing address Checkout collects): the session has
  automatic_tax, the inline product the SaaS personal-use tax code, the price stays tax_behavior inclusive, and no
  tax rates of ours are sent. The rules above then only shape the texts.
"""
from __future__ import annotations

from app.config import get_settings
from app.modules.billing import markets

LOCALES = ("da", "en", "de", "es", "fr", "it", "no", "sv")
LOCALE_PATTERN = "^(da|en|de|es|fr|it|no|sv)$"
STRIPE_LOCALE = {"no": "nb"}


def norm_locale(locale: str | None) -> str:
    loc = (locale or "da").lower()
    return loc if loc in LOCALES else "da"


def stripe_locale(locale: str | None) -> str:
    loc = norm_locale(locale)
    return STRIPE_LOCALE.get(loc, loc)


def currency(row_currency: str | None, locale: str | None) -> str:
    """The row's currency if the customer has one (it keeps it), else the language's."""
    if row_currency in markets.CURRENCIES:
        return row_currency
    return markets.currency_for_locale(norm_locale(locale))


# The consumer terms (web /privat/vilkaar, legal.json → privatTerms; F-PDEC-03). The version a customer bought under is
# written into the Checkout metadata (`terms_version`) of the plan and of a top-up, and the page is linked above the pay
# button. Must equal privatTerms.version in all 8 languages (tests/test_prices.py).
TERMS_VERSION = "1"
TERMS_PATH = "/privat/vilkaar"


def terms_note(base_url: str, locale: str | None) -> str:
    """The line above Checkout's pay button that links the terms (Danish for da, English otherwise, like the rest)."""
    url = base_url.rstrip("/") + TERMS_PATH
    if norm_locale(locale) == "da":
        return f"Handelsbetingelser for Dialogbot Privat (version {TERMS_VERSION}): {url}"
    return f"Terms of sale for Dialogbot Privat (version {TERMS_VERSION}): {url}"


TAX_CODE = "txcd_10103000"  # Stripe Tax: Software as a service (SaaS) - personal use


def stripe_tax() -> bool:
    return bool(get_settings().stripe_tax_enabled)


def apply_tax(payload: dict, line: dict, locale: str | None) -> None:
    """Put the VAT on a Checkout payload and its one line: Stripe Tax (automatic_tax + tax code) when enabled,
    otherwise our one inclusive tax rate (if any)."""
    if stripe_tax():
        payload["automatic_tax"] = {"enabled": True}
        payload.setdefault("billing_address_collection", "required")  # Stripe Tax needs the address
        if "price_data" in line:
            line["price_data"]["product_data"]["tax_code"] = TAX_CODE
        if payload.get("customer"):
            payload["customer_update"] = {"address": "auto", "name": "auto"}  # Checkout may save the address
    elif rates := tax_rates(locale):
        line["tax_rates"] = rates


def text_rate(locale: str | None) -> int | None:
    """The VAT rate the product text names; None with Stripe Tax (the rate is Stripe's: «inkl. moms» only)."""
    return None if stripe_tax() else vat(locale).rate_bp


def vat_text(rate_bp: int | None, locale: str | None) -> str:
    da = norm_locale(locale) == "da"
    if rate_bp is None:
        return " inkl. moms" if da else " incl. VAT"
    if not rate_bp:
        return ""
    return f" inkl. {pct(rate_bp, 'da')} % moms" if da else f" incl. {pct(rate_bp, 'en')} % VAT"


def vat(locale: str | None) -> markets.Vat:
    s = get_settings()
    return markets.privat_vat(markets.LOCALE_COUNTRY.get(norm_locale(locale)), eu_mode=s.privat_eu_vat_mode,
                              voec_registered=s.no_voec_registered)


def tax_rates(locale: str | None) -> list[str]:
    """The inclusive Stripe tax rate for the line (empty when no VAT applies)."""
    from app.modules.billing import stripe as stripe_api

    v = vat(locale)
    if not v.rate_bp or not v.country:
        return []
    return [stripe_api.tax_rate_id(v.country, v.rate_bp, True)]


def pct(bp: int, locale: str) -> str:
    """2500 → "25", 2550 → "25,5" (Danish) / "25.5"."""
    whole, frac = divmod(bp, 100)
    if not frac:
        return str(whole)
    dec = f"{frac:02d}".rstrip("0")
    return f"{whole},{dec}" if norm_locale(locale) == "da" else f"{whole}.{dec}"

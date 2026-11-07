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

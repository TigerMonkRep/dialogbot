"""An Erhverv workspace's market: its country, currency, VAT number and the VAT its invoices carry.

- Country: BusinessProfile.country (DK when there is no profile).
- Currency: the agreement's currency once the workspace has an agreement (locked – a later country change does not
  move it), otherwise the country's currency (markets.currency_for_country).
- VAT: markets.erhverv_vat(country, vat_number), decided when the statement / invoice is made. An EU company outside
  Denmark without a VAT number gets kind "vat_number_required" (rate 0): the statement still renders as a preview,
  but no card can be saved and no invoice made until the number is given.
"""
from __future__ import annotations

import re
import uuid

from sqlalchemy.orm import Session as OrmSession

from app.core.errors import ValidationFailed
from app.models import BillingAccount, BusinessProfile
from app.modules.billing import agreements, markets

VAT_NUMBER_REQUIRED_NOTE = "A VAT number is required before the company can be invoiced without VAT (reverse charge)."
VAT_NUMBER_REQUIRED_MESSAGE = ("Angiv virksomhedens momsnummer (VAT-nummer) først. En virksomhed i et andet EU-land end "
                               "Danmark faktureres uden dansk moms (omvendt betalingspligt), og det kræver momsnummeret.")
# Stripe's languages (Checkout `locale`, customer `preferred_locales`) by company country; others get English.
STRIPE_LOCALE = {"DK": "da", "SE": "sv", "NO": "nb", "DE": "de", "AT": "de", "FR": "fr", "ES": "es", "IT": "it"}
# Stripe Tax product tax codes (https://docs.stripe.com/tax/tax-codes): SaaS for business / personal use.
TAX_CODE_ERHVERV = "txcd_10103001"
TAX_CODE_PRIVAT = "txcd_10103000"
# The VAT number's prefix differs from the ISO country code for Greece.
VAT_PREFIX = {"GR": "EL"}


def country_of(db: OrmSession, ws_id: uuid.UUID) -> str:
    p = db.get(BusinessProfile, ws_id)
    return ((p.country if p else None) or "DK").upper()


def vat_number_of(db: OrmSession, ws_id: uuid.UUID) -> str | None:
    a = db.get(BillingAccount, ws_id)
    return (a.vat_number if a else None) or None


def currency_of(db: OrmSession, ws_id: uuid.UUID) -> str:
    """The workspace's currency: the agreement's (locked) or, before the first agreement, the country's."""
    a = agreements.current(db, ws_id)
    if a is not None:
        return a.currency
    return markets.currency_for_country(country_of(db, ws_id))


def stripe_tax_enabled() -> bool:
    from app.config import get_settings

    return bool(get_settings().stripe_tax_enabled)


def stripe_address(db: OrmSession, ws_id: uuid.UUID) -> dict:
    """The company's address for the Stripe customer (Stripe Tax needs at least the country)."""
    p = db.get(BusinessProfile, ws_id)
    out = {"country": country_of(db, ws_id)}
    if p is not None:
        for key, value in (("line1", p.address_line), ("postal_code", p.postal_code), ("city", p.city)):
            if value:
                out[key] = value
    return out


def stripe_locale(country: str | None) -> str:
    return STRIPE_LOCALE.get((country or "DK").upper(), "en")


def vat_out(country: str | None, vat_number: str | None) -> dict:
    """{kind, rate_bp, country, note}: the VAT an Erhverv invoice to this company carries."""
    try:
        v = markets.erhverv_vat(country, vat_number)
    except markets.VatNumberRequired:
        return {"kind": "vat_number_required", "rate_bp": 0, "country": (country or "DK").upper(),
                "note": VAT_NUMBER_REQUIRED_NOTE}
    return {"kind": v.kind, "rate_bp": v.rate_bp, "country": v.country, "note": v.note}


def vat_of(db: OrmSession, ws_id: uuid.UUID) -> dict:
    return vat_out(country_of(db, ws_id), vat_number_of(db, ws_id))


def normalize_vat_number(value: str | None, country: str | None) -> str | None:
    """Strip spaces, dots and dashes, uppercase, and check it fits the company's country. Empty → None (cleared).

    EU: the country prefix (EL for Greece) followed by 2–12 letters/digits; a number typed without the prefix gets it.
    Norway: 9 digits (optionally NO… and …MVA), stored as "123456789MVA" (Stripe's no_vat format).
    Elsewhere: 4–20 letters/digits."""
    v = re.sub(r"[\s.\-]", "", value or "").upper()
    if not v:
        return None
    c = (country or "DK").upper()
    bad = ValidationFailed("Momsnummeret ser ikke rigtigt ud", code="invalid_vat_number",
                           field_errors=[{"field": "vat_number", "message": "Ugyldigt momsnummer"}])
    if c in markets.EU_VAT_BP:
        prefix = VAT_PREFIX.get(c, c)
        if v[0].isdigit():
            v = prefix + v
        if not v.startswith(prefix):
            raise ValidationFailed(f"Momsnummeret skal begynde med {prefix} for en virksomhed i {c}",
                                   code="vat_number_country_mismatch",
                                   field_errors=[{"field": "vat_number", "message": f"Skal begynde med {prefix}"}])
        if not re.fullmatch(rf"{prefix}[0-9A-Z]{{2,12}}", v) or not any(ch.isdigit() for ch in v[len(prefix):]):
            raise bad
        return v
    if c == "NO":
        m = re.fullmatch(r"(?:NO)?(\d{9})(?:MVA)?", v)
        if not m:
            raise bad
        return f"{m.group(1)}MVA"
    if not re.fullmatch(r"[0-9A-Z]{4,20}", v):
        raise bad
    return v


def stripe_tax_id(country: str | None, vat_number: str | None) -> dict | None:
    """The Stripe customer tax id for the number: eu_vat in the EU, no_vat in Norway; None elsewhere / without one."""
    if not vat_number:
        return None
    c = (country or "DK").upper()
    if c in markets.EU_VAT_BP:
        return {"type": "eu_vat", "value": vat_number}
    if c == "NO":
        return {"type": "no_vat", "value": vat_number}
    return None


def account_market(db: OrmSession, ws_id: uuid.UUID) -> dict:
    """The market fields of GET /billing/account."""
    country = country_of(db, ws_id)
    number = vat_number_of(db, ws_id)
    return {"country": country, "currency": currency_of(db, ws_id), "vat_number": number,
            "vat": vat_out(country, number)}

"""Reception price agreements (versioned). There is one offer, so every new agreement is the subscription at the list
price in `prices.py`; choosing it creates a new immutable version that snapshots the price.

Older agreements stay as they were (an old "model B" agreement, per approved enquiry, keeps its fee snapshot and its
statement lines), but no new model-B agreement can be made.

Currency (docs/markets.md): the first agreement takes the currency of the company's country (BusinessProfile.country →
markets.currency_for_country) and the list price in that currency (markets.ERHVERV). From then on the workspace's
currency is LOCKED: every later version keeps the currency of the one before, even if the country changes. An
agreement from an accepted SalesOffer (Dialogbot's own Danish sales) is always DKK.

`tax_basis_points` is kept on the row (25 % for Danish companies, the rate that applied when it was made otherwise),
but the VAT an invoice actually carries is decided when the statement / invoice is made (markets.erhverv_vat)."""
from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session as OrmSession

from app.core.errors import ValidationFailed
from app.models import BillingAccount, BusinessProfile, ReceptionAgreement
from app.modules.billing import markets, prices
from app.modules.billing.money import Money

TAX_BASIS_POINTS = prices.TAX_BASIS_POINTS


def current(db: OrmSession, workspace_id: uuid.UUID) -> ReceptionAgreement | None:
    return db.scalar(select(ReceptionAgreement).where(ReceptionAgreement.workspace_id == workspace_id)
                     .order_by(ReceptionAgreement.version.desc()).limit(1))


def create(db: OrmSession, workspace_id: uuid.UUID, model: str, created_by: uuid.UUID, *,
           offer=None) -> ReceptionAgreement:
    """`offer` (an accepted SalesOffer) snapshots the offer's monthly price, VAT, setup fee and package (included
    inbound minutes, overage price) instead of the list price; its amounts were themselves copied from prices.py when
    the offer was created. Without an offer the package is the list price in the agreement's currency."""
    if model != "A":
        raise ValidationFailed("Betaling pr. henvendelse findes ikke længere. Der er ét abonnement.",
                               field_errors=[{"field": "model", "message": "Kun abonnement"}], code="plan_discontinued")
    last = db.scalar(select(func.max(ReceptionAgreement.version)).where(ReceptionAgreement.workspace_id == workspace_id))
    previous = current(db, workspace_id)
    if offer is not None:
        currency = "DKK"  # Dialogbot's own sales are Danish and priced in DKK
    elif previous is not None:
        currency = previous.currency  # locked: a later country change does not move the currency
    else:
        p = db.get(BusinessProfile, workspace_id)
        currency = markets.currency_for_country(p.country if p else None)
    tax_bp = offer.tax_basis_points if offer is not None else _vat_bp_now(db, workspace_id)
    a = ReceptionAgreement(workspace_id=workspace_id, version=(last or 0) + 1, model="A", currency=currency,
                           monthly_net_minor=offer.monthly_net_minor if offer else markets.erhverv_price(currency, "monthly"),
                           lead_fee_net_minor=0, tax_basis_points=tax_bp,
                           setup_net_minor=offer.setup_net_minor if offer else 0,
                           inbound_included_minutes=(offer.inbound_included_minutes if offer
                                                     else prices.INBOUND_INCLUDED_MINUTES),
                           inbound_extra_minute_net_minor=(offer.inbound_extra_minute_net_minor if offer
                                                           else markets.erhverv_price(currency, "extra_minute")),
                           # an offer's campaign minute price is the outbound minute (above the package since 2026-11)
                           outbound_extra_minute_net_minor=(offer.campaign_minute_net_minor if offer
                                                            else markets.erhverv_price(currency, "outbound_extra_minute")),
                           # an offer's campaign call price is the answered call after the package
                           outbound_call_answered_net_minor=(offer.campaign_call_net_minor if offer and offer.campaign_call_net_minor
                                                             else markets.erhverv_price(currency, "call_answered")),
                           outbound_call_voicemail_net_minor=markets.erhverv_price(currency, "call_voicemail"),
                           outbound_call_no_answer_net_minor=markets.erhverv_price(currency, "call_no_answer"),
                           sales_offer_id=offer.id if offer else None, created_by=created_by)
    db.add(a)
    db.flush()
    return a


def _vat_bp_now(db: OrmSession, workspace_id: uuid.UUID) -> int:
    """The VAT rate an invoice to the company would carry today (informational on the row; 0 if unknown yet)."""
    p = db.get(BusinessProfile, workspace_id)
    acc = db.get(BillingAccount, workspace_id)
    try:
        return markets.erhverv_vat(p.country if p else None, acc.vat_number if acc else None).rate_bp
    except markets.VatNumberRequired:
        return 0


def lead_fee(a: ReceptionAgreement) -> Money:
    """What one approved lead costs under this agreement: nothing, except under an old model-B agreement."""
    return Money(a.currency, a.lead_fee_net_minor if a.model == "B" else 0, a.tax_basis_points)


def out(a: ReceptionAgreement | None) -> dict | None:
    if a is None:
        return None
    return {"id": str(a.id), "version": a.version, "model": a.model, "currency": a.currency,
            "monthly": Money(a.currency, a.monthly_net_minor, a.tax_basis_points).snapshot(),
            "lead_fee": lead_fee(a).snapshot(),
            # one package for inbound and outbound minutes; above it, priced per direction; no fee per call
            "included_minutes": a.inbound_included_minutes,
            "inbound_included_minutes": a.inbound_included_minutes,
            "outbound_extra_minute": Money(a.currency, a.outbound_extra_minute_net_minor, a.tax_basis_points).snapshot(),
            # the price of an outbound call that starts after the package is used up, by outcome
            "outbound_call": {k: Money(a.currency, getattr(a, f"outbound_call_{k}_net_minor"), a.tax_basis_points).snapshot()
                              for k in ("answered", "voicemail", "no_answer")},
            "inbound_extra_minute": Money(a.currency, a.inbound_extra_minute_net_minor, a.tax_basis_points).snapshot(),
            "setup": Money(a.currency, a.setup_net_minor or 0, a.tax_basis_points).snapshot(),
            "created_at": a.created_at.isoformat(),
            "invoicing": "not_implemented"}

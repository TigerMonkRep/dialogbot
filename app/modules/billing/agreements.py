"""Reception price agreements (versioned). There is one offer, so every new agreement is the subscription at the list
price in `prices.py`; choosing it creates a new immutable version that snapshots the price.

Older agreements stay as they were (an old "model B" agreement, per approved enquiry, keeps its fee snapshot and its
statement lines), but no new model-B agreement can be made."""
from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session as OrmSession

from app.core.errors import ValidationFailed
from app.models import ReceptionAgreement
from app.modules.billing import prices
from app.modules.billing.money import Money

TAX_BASIS_POINTS = prices.TAX_BASIS_POINTS


def current(db: OrmSession, workspace_id: uuid.UUID) -> ReceptionAgreement | None:
    return db.scalar(select(ReceptionAgreement).where(ReceptionAgreement.workspace_id == workspace_id)
                     .order_by(ReceptionAgreement.version.desc()).limit(1))


def create(db: OrmSession, workspace_id: uuid.UUID, model: str, created_by: uuid.UUID) -> ReceptionAgreement:
    if model != "A":
        raise ValidationFailed("Betaling pr. henvendelse findes ikke længere. Der er ét abonnement.",
                               field_errors=[{"field": "model", "message": "Kun abonnement"}], code="plan_discontinued")
    last = db.scalar(select(func.max(ReceptionAgreement.version)).where(ReceptionAgreement.workspace_id == workspace_id))
    a = ReceptionAgreement(workspace_id=workspace_id, version=(last or 0) + 1, model="A", currency="DKK",
                           monthly_net_minor=prices.SUBSCRIPTION_MONTHLY_NET_MINOR, lead_fee_net_minor=0,
                           tax_basis_points=TAX_BASIS_POINTS, created_by=created_by)
    db.add(a)
    db.flush()
    return a


def lead_fee(a: ReceptionAgreement) -> Money:
    """What one approved lead costs under this agreement: nothing, except under an old model-B agreement."""
    return Money(a.currency, a.lead_fee_net_minor if a.model == "B" else 0, a.tax_basis_points)


def out(a: ReceptionAgreement | None) -> dict | None:
    if a is None:
        return None
    return {"id": str(a.id), "version": a.version, "model": a.model, "currency": a.currency,
            "monthly": Money(a.currency, a.monthly_net_minor, a.tax_basis_points).snapshot(),
            "lead_fee": lead_fee(a).snapshot(),
            "campaign_call": Money(a.currency, prices.CAMPAIGN_CALL_NET_MINOR, a.tax_basis_points).snapshot(),
            "created_at": a.created_at.isoformat(),
            "invoicing": "not_implemented"}

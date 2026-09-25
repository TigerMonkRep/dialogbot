"""Reception price agreements (versioned). List prices come from the product rules and are
not negotiable in the app; choosing a model creates a new immutable version.

No invoice is produced in this stage: an agreement only fixes what an approved lead costs."""
from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session as OrmSession

from app.models import ReceptionAgreement
from app.modules.billing.money import Money

MODEL_A_MONTHLY_NET_MINOR = 149_500  # 1.495 kr./md., no lead fee
MODEL_B_LEAD_FEE_NET_MINOR = 14_900  # 149 kr. per approved lead
TAX_BASIS_POINTS = 2500


def current(db: OrmSession, workspace_id: uuid.UUID) -> ReceptionAgreement | None:
    return db.scalar(select(ReceptionAgreement).where(ReceptionAgreement.workspace_id == workspace_id)
                     .order_by(ReceptionAgreement.version.desc()).limit(1))


def create(db: OrmSession, workspace_id: uuid.UUID, model: str, created_by: uuid.UUID) -> ReceptionAgreement:
    last = db.scalar(select(func.max(ReceptionAgreement.version)).where(ReceptionAgreement.workspace_id == workspace_id))
    a = ReceptionAgreement(workspace_id=workspace_id, version=(last or 0) + 1, model=model, currency="DKK",
                           monthly_net_minor=MODEL_A_MONTHLY_NET_MINOR if model == "A" else 0,
                           lead_fee_net_minor=MODEL_B_LEAD_FEE_NET_MINOR if model == "B" else 0,
                           tax_basis_points=TAX_BASIS_POINTS, created_by=created_by)
    db.add(a)
    db.flush()
    return a


def lead_fee(a: ReceptionAgreement) -> Money:
    """What one approved lead costs under this agreement (0 under model A)."""
    return Money(a.currency, a.lead_fee_net_minor if a.model == "B" else 0, a.tax_basis_points)


def out(a: ReceptionAgreement | None) -> dict | None:
    if a is None:
        return None
    return {"id": str(a.id), "version": a.version, "model": a.model, "currency": a.currency,
            "monthly": Money(a.currency, a.monthly_net_minor, a.tax_basis_points).snapshot(),
            "lead_fee": lead_fee(a).snapshot(), "created_at": a.created_at.isoformat(),
            "invoicing": "not_implemented"}

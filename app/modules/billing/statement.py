"""Monthly billing statement (preview only — no invoice, no payment).

Rules (product rules; money in whole øre, 25 % VAT, half-up on the total):
- Model A: the monthly subscription of the agreement version in force at the end of the month.
  Approved leads never change a model-A total.
- Model B: the sum of the fee snapshots of leads approved in the month (each keeps the price that
  applied when it was approved, even if the agreement changed later).
- Campaign packages: one per contact whose first attempt was dialled in the month, at the price
  snapshotted then.
- Months are calendar months in the workspace's time zone. No proration in this stage.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session as OrmSession

from app.models import Campaign, CampaignContact, Lead, ReceptionAgreement
from app.modules.billing.agreements import TAX_BASIS_POINTS
from app.modules.billing.money import Money


def month_bounds(month: date, tz: str) -> tuple[datetime, datetime]:
    z = ZoneInfo(tz)
    first = month.replace(day=1)
    nxt = date(first.year + (first.month == 12), first.month % 12 + 1, 1)
    return datetime.combine(first, time.min, tzinfo=z), datetime.combine(nxt, time.min, tzinfo=z)


def statement(db: OrmSession, workspace_id: uuid.UUID, month: date, tz: str) -> dict:
    start, end = month_bounds(month, tz)
    agreement = db.scalar(select(ReceptionAgreement).where(ReceptionAgreement.workspace_id == workspace_id,
                                                           ReceptionAgreement.created_at < end)
                          .order_by(ReceptionAgreement.version.desc()).limit(1))
    lines: list[dict] = []
    if agreement is not None and agreement.model == "A":
        lines.append({"kind": "subscription", "description": f"Reception, model A – abonnement (aftale v{agreement.version})",
                      "net_minor": agreement.monthly_net_minor})
    leads = db.scalars(select(Lead).where(Lead.workspace_id == workspace_id, Lead.billing_status == "approved",
                                          Lead.billing_decided_at >= start, Lead.billing_decided_at < end)
                       .order_by(Lead.billing_decided_at)).all()
    for x in leads:
        snap = x.fee_snapshot or {}
        net = int(snap.get("net_minor", 0))
        lines.append({"kind": "lead", "lead_id": str(x.id), "description": f"Godkendt henvendelse: {x.contact_name or '(uden navn)'}",
                      "approved_at": x.billing_decided_at.isoformat(), "model": snap.get("model"),
                      "agreement_version": snap.get("agreement_version"), "net_minor": net})
    packages = db.execute(
        select(Campaign.id, Campaign.name, func.count(CampaignContact.id), func.sum(CampaignContact.charged_net_minor))
        .join(CampaignContact, CampaignContact.campaign_id == Campaign.id)
        .where(Campaign.workspace_id == workspace_id, CampaignContact.charged_at >= start, CampaignContact.charged_at < end)
        .group_by(Campaign.id, Campaign.name).order_by(Campaign.name)).all()
    for cid, name, n, net in packages:
        lines.append({"kind": "campaign", "campaign_id": str(cid), "packages": int(n),
                      "description": f"Kampagne \"{name}\": {n} kontaktpakke{'r' if n != 1 else ''}", "net_minor": int(net or 0)})
    total = Money("DKK", sum(line["net_minor"] for line in lines), TAX_BASIS_POINTS)
    return {
        "month": month.strftime("%Y-%m"), "timezone": tz, "status": "preview", "invoicing": "not_implemented",
        "agreement": {"version": agreement.version, "model": agreement.model} if agreement else None,
        "approved_leads": len(leads), "billable_leads": sum(1 for line in lines if line["kind"] == "lead" and line["net_minor"] > 0),
        "lines": lines, "totals": total.snapshot(),
    }

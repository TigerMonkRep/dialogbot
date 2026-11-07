"""Monthly billing statement (the basis of the invoice).

Rules (product rules; money in whole øre, 25 % VAT, half-up on the total):
- Subscription: the monthly price of the agreement version in force at the end of the month ("Fra 2.495 kr./md.").
  Approved enquiries never change it; there is no fee per enquiry.
- Campaign calls: every outbound call dialled in the month, at the prices snapshotted on the call: 4 kr. for dialling
  plus 2 kr. per started minute of conversation (the minutes are priced when the end-of-call report arrives).
- Inbound calls: 300 started minutes a month are included in the subscription; every started minute above that costs
  1,50 kr. (list prices, billing/prices.py). Campaign and demo calls are not inbound.
- Legacy, kept so old months and old agreements do not change: fee snapshots of leads approved under an old
  model-B agreement, and the old per-contact campaign packages (9 kr.) that were charged before per-call pricing.
- Months are calendar months in the workspace's time zone. No proration in this stage.

Markets (docs/markets.md): the statement is in the currency of the agreement in force (else the workspace's currency,
customer_market.currency_of – DKK for a Danish company), the inbound extra-minute price is that currency's list price,
and the VAT is markets.erhverv_vat(country, vat_number): 25 % for a Danish company, 0 with the reverse-charge note for
an EU company with a VAT number, 0 with the outside-EU note elsewhere. Without the VAT number an EU company outside
Denmark still gets the preview, with `vat.kind = "vat_number_required"` and rate 0 (it cannot be invoiced yet).
Descriptions are Danish for DKK statements (unchanged texts) and English otherwise, amounts through markets.fmt.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session as OrmSession

from app.models import Call, Campaign, CampaignCall, CampaignContact, DemoCall, Lead, ReceptionAgreement
from app.modules.billing import customer_market, markets, prices
from app.modules.billing.money import Money


def month_bounds(month: date, tz: str) -> tuple[datetime, datetime]:
    z = ZoneInfo(tz)
    first = month.replace(day=1)
    nxt = date(first.year + (first.month == 12), first.month % 12 + 1, 1)
    return datetime.combine(first, time.min, tzinfo=z), datetime.combine(nxt, time.min, tzinfo=z)


def _minutes_of(seconds: list) -> int:
    """Started minutes, rounded up per call (61 s = 2 minutes); calls without a report yet count 0."""
    return sum(-(-int(x) // 60) for x in seconds if x)


def inbound_minutes(db: OrmSession, workspace_id: uuid.UUID, start: datetime, end: datetime,
                    extra_minute_net_minor: int = prices.INBOUND_EXTRA_MINUTE_NET_MINOR) -> dict:
    """Inbound call minutes in the window: every phone call that is neither a campaign call nor a demo call."""
    outbound = select(CampaignCall.provider_call_id).where(CampaignCall.provider_call_id.is_not(None))
    demo = select(DemoCall.provider_call_id).where(DemoCall.provider_call_id.is_not(None))
    rows = db.scalars(select(Call.duration_seconds).where(
        Call.workspace_id == workspace_id, Call.started_at >= start, Call.started_at < end,
        Call.provider_call_id.not_in(outbound), Call.provider_call_id.not_in(demo))).all()
    minutes = _minutes_of(rows)
    extra = max(0, minutes - prices.INBOUND_INCLUDED_MINUTES)
    return {"calls": len(rows), "minutes": minutes, "included": prices.INBOUND_INCLUDED_MINUTES, "extra": extra,
            "net_minor": extra * extra_minute_net_minor}


def _plural(n: int, one: str, many: str) -> str:
    return one if n == 1 else many


def statement(db: OrmSession, workspace_id: uuid.UUID, month: date, tz: str) -> dict:
    start, end = month_bounds(month, tz)
    agreement = db.scalar(select(ReceptionAgreement).where(ReceptionAgreement.workspace_id == workspace_id,
                                                           ReceptionAgreement.created_at < end)
                          .order_by(ReceptionAgreement.version.desc()).limit(1))
    currency = agreement.currency if agreement is not None else customer_market.currency_of(db, workspace_id)
    da = currency == "DKK"
    # Our estimate; with Stripe Tax on, the invoice's VAT is Stripe's (invoices.tax_source = "stripe_tax").
    vat = customer_market.vat_of(db, workspace_id) | {"source": "estimate"}
    lines: list[dict] = []
    if agreement is not None and agreement.model == "A":
        lines.append({"kind": "subscription",
                      "description": (f"Dialogbot – abonnement (aftale v{agreement.version})" if da
                                      else f"Dialogbot – subscription (agreement v{agreement.version})"),
                      "net_minor": agreement.monthly_net_minor})
    leads = db.scalars(select(Lead).where(Lead.workspace_id == workspace_id, Lead.billing_status == "approved",
                                          Lead.billing_decided_at >= start, Lead.billing_decided_at < end)
                       .order_by(Lead.billing_decided_at)).all()
    for x in leads:
        snap = x.fee_snapshot or {}
        net = int(snap.get("net_minor", 0))
        lines.append({"kind": "lead", "lead_id": str(x.id),
                      "description": (f"Godkendt henvendelse: {x.contact_name or '(uden navn)'}" if da
                                      else f"Approved enquiry: {x.contact_name or '(no name)'}"),
                      "approved_at": x.billing_decided_at.isoformat(), "model": snap.get("model"),
                      "agreement_version": snap.get("agreement_version"), "net_minor": net})
    packages = db.execute(
        select(Campaign.id, Campaign.name, func.count(CampaignContact.id), func.sum(CampaignContact.charged_net_minor))
        .join(CampaignContact, CampaignContact.campaign_id == Campaign.id)
        .where(Campaign.workspace_id == workspace_id, CampaignContact.charged_at >= start, CampaignContact.charged_at < end)
        .group_by(Campaign.id, Campaign.name).order_by(Campaign.name)).all()
    for cid, name, n, net in packages:  # legacy: charged before per-call pricing
        lines.append({"kind": "campaign", "campaign_id": str(cid), "packages": int(n),
                      "description": (f"Kampagne \"{name}\": {n} kontaktpakke{'r' if n != 1 else ''}" if da
                                      else f"Campaign \"{name}\": {n} contact {_plural(n, 'package', 'packages')}"),
                      "net_minor": int(net or 0)})
    calls = db.execute(
        select(Campaign.id, Campaign.name, func.count(CampaignCall.id), func.sum(CampaignCall.net_minor),
               func.sum(CampaignCall.minutes_net_minor))
        .join(CampaignCall, CampaignCall.campaign_id == Campaign.id)
        .where(Campaign.workspace_id == workspace_id, CampaignCall.dialled_at >= start, CampaignCall.dialled_at < end)
        .group_by(Campaign.id, Campaign.name).order_by(Campaign.name)).all()
    for cid, name, n, net, minutes_net in calls:
        minutes = _minutes_of(db.scalars(select(CampaignCall.connected_seconds).where(
            CampaignCall.campaign_id == cid, CampaignCall.dialled_at >= start, CampaignCall.dialled_at < end)).all())
        lines.append({"kind": "campaign_calls", "campaign_id": str(cid), "calls": int(n), "minutes": minutes,
                      "description": (f"Kampagne \"{name}\": {n} udgående opkald, {minutes} samtaleminut{'ter' if minutes != 1 else ''}"
                                      if da else f"Campaign \"{name}\": {n} outbound {_plural(int(n), 'call', 'calls')}, "
                                      f"{minutes} {_plural(minutes, 'minute', 'minutes')} of conversation"),
                      "net_minor": int(net or 0) + int(minutes_net or 0)})
    extra_price = markets.erhverv_price(currency, "extra_minute")
    inbound = inbound_minutes(db, workspace_id, start, end, extra_price)
    if inbound["calls"]:
        if da:
            text = (f"Indgående opkald: {inbound['minutes']} min ({inbound['included']} min er med i abonnementet"
                    + (f", {inbound['extra']} min ekstra à {markets.fmt(extra_price, currency)})" if inbound["extra"] else ")"))
        else:
            text = (f"Inbound calls: {inbound['minutes']} min ({inbound['included']} min included in the subscription"
                    + (f", {inbound['extra']} min extra at {markets.fmt(extra_price, currency)})" if inbound["extra"] else ")"))
        lines.append({"kind": "inbound_minutes", "calls": inbound["calls"], "minutes": inbound["minutes"],
                      "included_minutes": inbound["included"], "extra_minutes": inbound["extra"],
                      "description": text, "net_minor": inbound["net_minor"]})
    from app.modules.ambassadors.service import discount_line

    discount = discount_line(db, workspace_id, month, lines)
    if discount is not None:
        if not da:
            discount["description"] = "Welcome discount: 50 % off the first month (referral)"
        lines.append(discount)
    from app.modules.billing.discounts import erhverv_line

    # an operator's discount code typed on Konto (an amount-off code is in DKK and applies to DKK statements only)
    code_discount = erhverv_line(db, workspace_id, month, tz, lines, currency=currency)
    if code_discount is not None:
        lines.append(code_discount)
    # Specialist setup from an accepted sales offer: once, in the month the agreement was made (its first invoice).
    # Added after the ambassador discount, which covers the running subscription, not the one-off setup.
    setup = db.scalars(select(ReceptionAgreement).where(
        ReceptionAgreement.workspace_id == workspace_id, ReceptionAgreement.setup_net_minor > 0,
        ReceptionAgreement.created_at >= start, ReceptionAgreement.created_at < end)
        .order_by(ReceptionAgreement.version)).all()
    for a in setup:
        lines.append({"kind": "setup_fee", "agreement_version": a.version,
                      "description": "Specialist-opsætning (engangsbeløb)" if da else "Specialist setup (one-off)",
                      "net_minor": a.setup_net_minor})
    total = Money(currency, sum(line["net_minor"] for line in lines), vat["rate_bp"])
    return {
        "month": month.strftime("%Y-%m"), "timezone": tz, "status": "preview", "invoicing": "not_implemented",
        "currency": currency, "vat": vat,
        "agreement": {"version": agreement.version, "model": agreement.model} if agreement else None,
        "approved_leads": len(leads), "billable_leads": sum(1 for line in lines if line["kind"] == "lead" and line["net_minor"] > 0),
        "lines": lines, "totals": total.snapshot(),
    }

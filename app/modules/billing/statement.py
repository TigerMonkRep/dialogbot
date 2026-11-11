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

from app.models import Call, Campaign, CampaignCall, CampaignContact, DemoCall, Lead, ReceptionAgreement, TelephonyTest
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
                    extra_minute_net_minor: int | None = None, included_minutes: int | None = None) -> dict:
    """Inbound call minutes in the window: every phone call that is neither a campaign call nor a demo call.
    The package (included minutes, overage price) is the agreement's snapshot; the list price only without one."""
    if extra_minute_net_minor is None:
        extra_minute_net_minor = prices.INBOUND_EXTRA_MINUTE_NET_MINOR
    if included_minutes is None:
        included_minutes = prices.INBOUND_INCLUDED_MINUTES
    outbound = select(CampaignCall.provider_call_id).where(CampaignCall.provider_call_id.is_not(None))
    demo = select(DemoCall.provider_call_id).where(DemoCall.provider_call_id.is_not(None))
    tests = select(TelephonyTest.provider_call_id).where(TelephonyTest.provider_call_id.is_not(None))  # owner's test calls
    rows = db.scalars(select(Call.duration_seconds).where(
        Call.workspace_id == workspace_id, Call.started_at >= start, Call.started_at < end,
        Call.provider_call_id.not_in(outbound), Call.provider_call_id.not_in(demo),
        Call.provider_call_id.not_in(tests))).all()
    minutes = _minutes_of(rows)
    extra = max(0, minutes - included_minutes)
    return {"calls": len(rows), "minutes": minutes, "included": included_minutes, "extra": extra,
            "net_minor": extra * extra_minute_net_minor}


def _plural(n: int, one: str, many: str) -> str:
    return one if n == 1 else many


def statement(db: OrmSession, workspace_id: uuid.UUID, month: date, tz: str) -> dict:
    start, end = month_bounds(month, tz)
    agreement = _agreement_at(db, workspace_id, end)
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
    lines += usage_lines(db, workspace_id, start, end, agreement, currency)
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
    # Usage of earlier, already invoiced months reported after their invoice (after the discounts: those cover this
    # month, not an earlier period).
    lines += late_usage_lines(db, workspace_id, month, tz)
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


USAGE_KINDS = ("campaign_calls", "inbound_minutes")  # usage lines: their minutes may be reported after the month closed
LATE_KIND = "late_usage_adjustment"


def _agreement_at(db: OrmSession, workspace_id: uuid.UUID, end: datetime) -> ReceptionAgreement | None:
    return db.scalar(select(ReceptionAgreement).where(ReceptionAgreement.workspace_id == workspace_id,
                                                      ReceptionAgreement.created_at < end)
                     .order_by(ReceptionAgreement.version.desc()).limit(1))


def usage_lines(db: OrmSession, workspace_id: uuid.UUID, start: datetime, end: datetime,
                agreement: ReceptionAgreement | None, currency: str) -> list[dict]:
    """Campaign calls and inbound minutes of the window, priced by the agreement in force (its package snapshot)."""
    da = currency == "DKK"
    lines: list[dict] = []
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
    if agreement is not None:
        extra_price, included = agreement.inbound_extra_minute_net_minor, agreement.inbound_included_minutes
    else:
        extra_price, included = markets.erhverv_price(currency, "extra_minute"), prices.INBOUND_INCLUDED_MINUTES
    inbound = inbound_minutes(db, workspace_id, start, end, extra_price, included)
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
    return lines


MONTH_DA = ("januar", "februar", "marts", "april", "maj", "juni", "juli", "august", "september", "oktober",
            "november", "december")


def late_usage_lines(db: OrmSession, workspace_id: uuid.UUID, month: date, tz: str) -> list[dict]:
    """Usage of an already invoiced month that was reported after its invoice (QA F-BQ-012): an end-of-call report
    arriving after the 1st, a call that started 23:58 on the last day. The month's usage is counted again with the
    agreement in force then; what that adds beyond the invoice's frozen usage lines and the late-usage lines already on
    later invoices becomes a line «Efterregistreret forbrug <måned>» here. Idempotent: once this month is invoiced, its
    lines are frozen and count as billed for the next month's statement – nothing is billed twice."""
    from app.models import Invoice

    first = month.replace(day=1)
    invoices = db.scalars(select(Invoice).where(Invoice.workspace_id == workspace_id, Invoice.month < first)
                          .order_by(Invoice.month)).all()
    later_lines = [x for inv in invoices for x in (inv.lines or []) if x.get("kind") == LATE_KIND]
    out: list[dict] = []
    for inv in invoices:
        period = inv.month.strftime("%Y-%m")
        s0, e0 = month_bounds(inv.month, tz)
        recount = usage_lines(db, workspace_id, s0, e0, _agreement_at(db, workspace_id, e0), inv.currency)
        for kind in USAGE_KINDS:
            now = [x for x in recount if x["kind"] == kind]
            billed = sum(int(x.get("net_minor") or 0) for x in (inv.lines or []) if x.get("kind") == kind) + sum(
                int(x.get("net_minor") or 0) for x in later_lines if x.get("period") == period and x.get("usage_kind") == kind)
            delta = sum(x["net_minor"] for x in now) - billed
            if delta <= 0:  # nothing new (late usage only ever adds; a smaller recount is not credited here)
                continue
            billed_minutes = sum(int(x.get("minutes") or 0) for x in (inv.lines or []) if x.get("kind") == kind) + sum(
                int(x.get("minutes") or 0) for x in later_lines if x.get("period") == period and x.get("usage_kind") == kind)
            minutes = max(0, sum(int(x.get("minutes") or 0) for x in now) - billed_minutes)
            da = inv.currency == "DKK"
            what = {"inbound_minutes": ("indgående opkald", "inbound calls"),
                    "campaign_calls": ("kampagneopkald", "campaign calls")}[kind]
            label = f"{MONTH_DA[inv.month.month - 1]} {inv.month.year}" if da else inv.month.strftime("%B %Y")
            out.append({"kind": LATE_KIND, "usage_kind": kind, "period": period, "minutes": minutes,
                        "description": (f"Efterregistreret forbrug {label} – {what[0]}: {minutes} min, registreret efter "
                                        "fakturaen" if da else
                                        f"Usage reported after the invoice, {label} – {what[1]}: {minutes} min"),
                        "net_minor": delta})
    return out

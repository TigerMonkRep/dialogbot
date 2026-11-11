"""Monthly billing statement (the basis of the invoice).

Rules (product rules; money in whole øre, 25 % VAT, half-up on the total):
- Subscription: the monthly price of the agreement version in force at the end of the month ("Fra 2.495 kr./md.").
  Approved enquiries never change it; there is no fee per enquiry.
- From SHARED_POOL_FROM (2026-11, Fürster's decisions 2026-11-10): ONE package of minutes a month (300) that inbound
  calls and outbound campaign calls draw on together, in the order the calls happened (inbound by start, campaign calls
  by dialling); every started minute above the package costs the agreement's price for its direction (1,50 kr. inbound,
  2 kr. outbound). Inside the package there is no price per call. A campaign call that STARTS when the package is
  already used up also costs a call price by outcome (4 kr. answered, 1 kr. voicemail, 0,25 kr. unanswered/busy or not
  reported yet) – its own line per campaign; a call that crosses the limit only splits its minutes. Demo and test
  calls never count.
- Months before that keep the model they were invoiced under: campaign calls at the prices snapshotted on the call
  (4 kr. for dialling + 2 kr. per started minute), and the package for inbound minutes only.
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
    package = None
    if shared_pool(month):
        usage, package = _pool_lines(db, workspace_id, start, end, agreement, currency)
    else:
        usage = _legacy_usage_lines(db, workspace_id, start, end, agreement, currency)
    lines += usage
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
    # Usage of earlier, already invoiced months reported after their invoice, and credits for complaints about calls
    # in invoiced months (after the discounts: those cover this month, not an earlier period).
    lines += late_usage_lines(db, workspace_id, month, tz)
    lines += dispute_credit_lines(db, workspace_id, month, tz, currency)
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
        # the minute package of the month (inbound + outbound together); None for months before the shared package
        "package": package,
        "approved_leads": len(leads), "billable_leads": sum(1 for line in lines if line["kind"] == "lead" and line["net_minor"] > 0),
        "lines": lines, "totals": total.snapshot(),
    }


USAGE_KINDS = ("campaign_calls", "campaign_call_fees", "inbound_minutes")  # usage lines: their minutes may be reported after the month closed
LATE_KIND = "late_usage_adjustment"


def _agreement_at(db: OrmSession, workspace_id: uuid.UUID, end: datetime) -> ReceptionAgreement | None:
    return db.scalar(select(ReceptionAgreement).where(ReceptionAgreement.workspace_id == workspace_id,
                                                      ReceptionAgreement.created_at < end)
                     .order_by(ReceptionAgreement.version.desc()).limit(1))


def shared_pool(month: date) -> bool:
    return month.replace(day=1) >= prices.SHARED_POOL_FROM


def package_terms(agreement: ReceptionAgreement | None, currency: str) -> dict:
    """The package in force: the agreement's snapshot, the list price in the currency without an agreement."""
    if agreement is not None:
        return {"included": agreement.inbound_included_minutes, "inbound": agreement.inbound_extra_minute_net_minor,
                "outbound": agreement.outbound_extra_minute_net_minor,
                "call": {"answered": agreement.outbound_call_answered_net_minor,
                         "voicemail": agreement.outbound_call_voicemail_net_minor,
                         "no_answer": agreement.outbound_call_no_answer_net_minor}}
    return {"included": prices.INCLUDED_MINUTES, "inbound": markets.erhverv_price(currency, "extra_minute"),
            "outbound": markets.erhverv_price(currency, "outbound_extra_minute"),
            "call": {k: markets.erhverv_price(currency, f"call_{k}") for k in OUTCOMES}}


OUTCOMES = ("answered", "voicemail", "no_answer")


def usage_events(db: OrmSession, workspace_id: uuid.UUID, start: datetime, end: datetime, *,
                 include_pool_credited: bool = False, exclude: frozenset = frozenset()) -> list[dict]:
    """Every billable call of the window, oldest first: inbound calls (by start) and campaign calls (by dialling), with
    their started minutes (a call without its end-of-call report yet counts 0 until the report arrives).
    A call whose complaint was approved before its month was invoiced (CallDispute credit_mode 'pool') is not usage:
    its minutes are back in the package (listed only with include_pool_credited, marked `credited`). `exclude` leaves
    out further calls by (direction, id) – used to value a complaint on an invoiced month."""
    from app.models import CallDispute

    pooled = (CallDispute.workspace_id == workspace_id) & (CallDispute.status == "approved") & (CallDispute.credit_mode == "pool")
    pooled_in = set(db.scalars(select(CallDispute.call_id).where(pooled, CallDispute.call_id.is_not(None))))
    pooled_out = set(db.scalars(select(CallDispute.campaign_call_id).where(pooled, CallDispute.campaign_call_id.is_not(None))))
    outbound = select(CampaignCall.provider_call_id).where(CampaignCall.provider_call_id.is_not(None))
    demo = select(DemoCall.provider_call_id).where(DemoCall.provider_call_id.is_not(None))
    tests = select(TelephonyTest.provider_call_id).where(TelephonyTest.provider_call_id.is_not(None))
    events = [{"direction": "inbound", "id": str(cid), "at": at, "minutes": _minutes_of([sec]), "campaign_id": None,
               "credited": cid in pooled_in}
              for cid, at, sec in db.execute(select(Call.id, Call.started_at, Call.duration_seconds).where(
                  Call.workspace_id == workspace_id, Call.started_at >= start, Call.started_at < end,
                  Call.provider_call_id.not_in(outbound), Call.provider_call_id.not_in(demo),
                  Call.provider_call_id.not_in(tests))).all()]
    events += [{"direction": "outbound", "id": str(cid), "at": at, "minutes": _minutes_of([sec]), "campaign_id": camp,
                "credited": cid in pooled_out, "outcome": outcome or "no_answer"}  # unknown = the cheapest
               for cid, at, sec, camp, outcome in db.execute(
                   select(CampaignCall.id, CampaignCall.dialled_at, CampaignCall.connected_seconds, CampaignCall.campaign_id,
                          CampaignCall.outcome_class)
                   .join(Campaign, Campaign.id == CampaignCall.campaign_id)
                   .where(Campaign.workspace_id == workspace_id, CampaignCall.dialled_at >= start,
                          CampaignCall.dialled_at < end)).all()]
    events = [e for e in events if (include_pool_credited or not e["credited"]) and (e["direction"], e["id"]) not in exclude]
    return sorted(events, key=lambda e: (e["at"], e["id"]))


def allocate(events: list[dict], terms: dict) -> dict:
    """Use the package in call order; minutes above it are priced by direction, and an outbound call that starts when
    the package is already used up also costs the call price for its outcome. Mutates each event with package_minutes /
    extra_minutes / minutes_net_minor / call_net_minor / net_minor and returns the package summary."""
    left = terms["included"]
    events = [e for e in events if not e.get("credited")]
    for e in events:
        after_package = left == 0  # the package was used up before this call started
        e["package_minutes"] = min(e["minutes"], left)
        left -= e["package_minutes"]
        e["extra_minutes"] = e["minutes"] - e["package_minutes"]
        e["minutes_net_minor"] = e["extra_minutes"] * terms[e["direction"]]
        e["call_net_minor"] = terms["call"][e["outcome"]] if e["direction"] == "outbound" and after_package else 0
        e["net_minor"] = e["minutes_net_minor"] + e["call_net_minor"]
    used = sum(e["minutes"] for e in events)
    return {"included": terms["included"], "used": used, "remaining": max(0, terms["included"] - used),
            "over": sum(e["extra_minutes"] for e in events)}


def _pool_lines(db: OrmSession, workspace_id: uuid.UUID, start: datetime, end: datetime,
                agreement: ReceptionAgreement | None, currency: str) -> tuple[list[dict], dict]:
    da = currency == "DKK"
    terms = package_terms(agreement, currency)
    events = usage_events(db, workspace_id, start, end)
    package = allocate(events, terms)
    lines: list[dict] = []
    names = dict(db.execute(select(Campaign.id, Campaign.name).where(Campaign.workspace_id == workspace_id)).all())
    by_campaign: dict = {}
    for e in events:
        if e["direction"] == "outbound":
            by_campaign.setdefault(e["campaign_id"], []).append(e)
    for cid, evs in sorted(by_campaign.items(), key=lambda kv: names.get(kv[0], "")):
        n, minutes = len(evs), sum(e["minutes"] for e in evs)
        extra = sum(e["extra_minutes"] for e in evs)
        name = names.get(cid, "")
        over = (f", {extra} min ud over pakken à {markets.fmt(terms['outbound'], currency)}" if da
                else f", {extra} min above the package at {markets.fmt(terms['outbound'], currency)}") if extra else ""
        lines.append({"kind": "campaign_calls", "campaign_id": str(cid), "calls": n, "minutes": minutes,
                      "package_minutes": minutes - extra, "extra_minutes": extra,
                      "description": (f"Kampagne \"{name}\": {n} udgående opkald, {minutes} samtaleminut"
                                      f"{'ter' if minutes != 1 else ''} ({minutes - extra} min fra pakken{over})" if da else
                                      f"Campaign \"{name}\": {n} outbound {_plural(n, 'call', 'calls')}, {minutes} "
                                      f"{_plural(minutes, 'minute', 'minutes')} of conversation ({minutes - extra} min from "
                                      f"the package{over})"),
                      "net_minor": sum(e["minutes_net_minor"] for e in evs)})
        paid = [e for e in evs if e["call_net_minor"]]
        if paid:  # calls that started after the package was used up: the call price by outcome, its own line
            counts = {k: sum(1 for e in paid if e["outcome"] == k) for k in OUTCOMES}
            parts = [(k, n) for k, n in counts.items() if n]
            words = {"answered": ("besvaret", "answered"), "voicemail": ("telefonsvarer", "voicemail"),
                     "no_answer": ("ubesvaret/optaget", "unanswered/busy")}
            text = ", ".join(f"{n} {words[k][0 if da else 1]} à {markets.fmt(terms['call'][k], currency)}" for k, n in parts)
            lines.append({"kind": "campaign_call_fees", "campaign_id": str(cid), "calls": len(paid), **counts,
                          "description": (f"Kampagne \"{name}\": opkald efter brugt pakke – {text}" if da
                                          else f"Campaign \"{name}\": calls after the package was used up – {text}"),
                          "net_minor": sum(e["call_net_minor"] for e in paid)})
    inbound = [e for e in events if e["direction"] == "inbound"]
    if inbound:
        minutes, extra = sum(e["minutes"] for e in inbound), sum(e["extra_minutes"] for e in inbound)
        if da:
            text = (f"Indgående opkald: {minutes} min ({minutes - extra} min fra pakken på {terms['included']} min"
                    + (f", {extra} min ekstra à {markets.fmt(terms['inbound'], currency)})" if extra else ")"))
        else:
            text = (f"Inbound calls: {minutes} min ({minutes - extra} min from the {terms['included']}-minute package"
                    + (f", {extra} min extra at {markets.fmt(terms['inbound'], currency)})" if extra else ")"))
        lines.append({"kind": "inbound_minutes", "calls": len(inbound), "minutes": minutes,
                      "included_minutes": terms["included"], "package_minutes": minutes - extra, "extra_minutes": extra,
                      "description": text, "net_minor": sum(e["net_minor"] for e in inbound)})
    return lines, package


def agreement_at(db: OrmSession, workspace_id: uuid.UUID, end: datetime) -> ReceptionAgreement | None:
    """The agreement in force at the end of a month (the newest version made before `end`)."""
    return _agreement_at(db, workspace_id, end)


def usage_lines(db: OrmSession, workspace_id: uuid.UUID, start: datetime, end: datetime,
                agreement: ReceptionAgreement | None, currency: str, month: date | None = None) -> list[dict]:
    """Campaign calls and inbound minutes of the month, priced by the agreement in force (its package snapshot) under
    the model of that month (shared package from SHARED_POOL_FROM)."""
    if month is None:
        month = start.date()
    if shared_pool(month):
        return _pool_lines(db, workspace_id, start, end, agreement, currency)[0]
    return _legacy_usage_lines(db, workspace_id, start, end, agreement, currency)


def _legacy_usage_lines(db: OrmSession, workspace_id: uuid.UUID, start: datetime, end: datetime,
                        agreement: ReceptionAgreement | None, currency: str) -> list[dict]:
    """Before 2026-11: campaign calls at the per-call snapshot (4 kr. + 2 kr./min), the package for inbound only."""
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
        recount = usage_lines(db, workspace_id, s0, e0, _agreement_at(db, workspace_id, e0), inv.currency, inv.month)
        # one shared package: a late call can move package minutes between inbound and outbound, so the month is
        # compared as a whole; before it, the two kinds were priced independently
        for kind in (("package",) if shared_pool(inv.month) else USAGE_KINDS):
            kinds = USAGE_KINDS if kind == "package" else (kind,)
            now = [x for x in recount if x["kind"] in kinds]
            billed = sum(int(x.get("net_minor") or 0) for x in (inv.lines or []) if x.get("kind") in kinds) + sum(
                int(x.get("net_minor") or 0) for x in later_lines if x.get("period") == period and x.get("usage_kind") == kind)
            delta = sum(x["net_minor"] for x in now) - billed
            if delta <= 0:  # nothing new (late usage only ever adds; a smaller recount is not credited here)
                continue
            billed_minutes = sum(int(x.get("minutes") or 0) for x in (inv.lines or []) if x.get("kind") in kinds) + sum(
                int(x.get("minutes") or 0) for x in later_lines if x.get("period") == period and x.get("usage_kind") == kind)
            minutes = max(0, sum(int(x.get("minutes") or 0) for x in now) - billed_minutes)
            da = inv.currency == "DKK"
            what = {"inbound_minutes": ("indgående opkald", "inbound calls"),
                    "campaign_calls": ("kampagneopkald", "campaign calls"),
                    "package": ("ind- og udgående opkald", "inbound and outbound calls")}[kind]
            label = f"{MONTH_DA[inv.month.month - 1]} {inv.month.year}" if da else inv.month.strftime("%B %Y")
            out.append({"kind": LATE_KIND, "usage_kind": kind, "period": period, "minutes": minutes,
                        "description": (f"Efterregistreret forbrug {label} – {what[0]}: {minutes} min, registreret efter "
                                        "fakturaen" if da else
                                        f"Usage reported after the invoice, {label} – {what[1]}: {minutes} min"),
                        "net_minor": delta})
    return out


CREDIT_KIND = "dispute_credit"


def dispute_credit_lines(db: OrmSession, workspace_id: uuid.UUID, month: date, tz: str, currency: str) -> list[dict]:
    """Complaints approved after their month was invoiced (CallDispute credit_mode 'invoice'): the amount the call
    added to that invoice comes off the next invoice, once – a credit already on an earlier invoice is not repeated
    (the frozen lines carry `dispute_id`). A credit of 0 (the call was within the package) gets no line."""
    from app.models import CallDispute, Invoice

    first = month.replace(day=1)
    _start, end = month_bounds(first, tz)
    done = {x.get("dispute_id") for lines in db.scalars(select(Invoice.lines).where(
        Invoice.workspace_id == workspace_id, Invoice.month < first)) for x in (lines or []) if x.get("kind") == CREDIT_KIND}
    out = []
    for d in db.scalars(select(CallDispute).where(
            CallDispute.workspace_id == workspace_id, CallDispute.status == "approved", CallDispute.credit_mode == "invoice",
            CallDispute.period < first, CallDispute.decided_at < end, CallDispute.credit_net_minor > 0)
            .order_by(CallDispute.decided_at)):
        if str(d.id) in done:
            continue
        da = currency == "DKK"
        label = f"{MONTH_DA[d.period.month - 1]} {d.period.year}" if da else d.period.strftime("%B %Y")
        when = d.call_at.astimezone(ZoneInfo(tz))
        out.append({"kind": CREDIT_KIND, "dispute_id": str(d.id), "period": d.period.strftime("%Y-%m"), "minutes": d.minutes,
                    "description": (f"Kreditering efter klage: opkald {when.day}. {MONTH_DA[when.month - 1]} kl. "
                                    f"{when:%H.%M} ({d.minutes} min) på fakturaen for {label}" if da else
                                    f"Credit after a complaint: call on {when:%d %B %H:%M} ({d.minutes} min), invoice {label}"),
                    "net_minor": -d.credit_net_minor})
    return out

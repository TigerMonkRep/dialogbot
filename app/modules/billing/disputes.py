"""Complaints about a billed call – the only way minutes are credited (Fürster 2026-11-10; B03/B04, DB-002).

The customer sees every billed call of a month with its minutes (Konto) and can complain about one call with a reason.
One complaint per call, idempotent. The operator decides:
- approve while the call's month is NOT invoiced → the call leaves the month's usage and its minutes go back into the
  package (credit_mode 'pool'). No credit note: nothing was billed (DB-002 «unbilled uphold»).
- approve after the month WAS invoiced → what the call added to that invoice (its minutes above the package at the
  price for its direction, valued against the month as invoiced) is credited as a line on the next invoice
  (credit_mode 'invoice', statement.dispute_credit_lines). 0 kr. when the call was within the package.
- reject → nothing changes and nothing says «krediteret».
Only months with the shared package (from prices.SHARED_POOL_FROM) take complaints here; earlier months go to support.
Every step is audit-logged.
"""
from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from app.core.audit import record_audit
from app.core.errors import Conflict, NotFound, ValidationFailed
from app.models import Call, CallDispute, Campaign, CampaignCall, Invoice
from app.modules.billing import customer_market, statement

KINDS = ("inbound", "outbound")


def _period(at: datetime, tz: str) -> date:
    return at.astimezone(ZoneInfo(tz)).date().replace(day=1)


def billable_call(db: OrmSession, workspace_id: uuid.UUID, kind: str, call_id: uuid.UUID, tz: str) -> dict:
    """The call as billed usage of its month (direction, id, at, minutes), or 404/422."""
    if kind not in KINDS:
        raise ValidationFailed("Ukendt opkaldstype", field_errors=[{"field": "kind"}])
    if kind == "inbound":
        row = db.get(Call, call_id)
        if row is None or row.workspace_id != workspace_id:
            raise NotFound("Opkaldet findes ikke")
        at = row.started_at
    else:
        row = db.get(CampaignCall, call_id)
        if row is None or row.workspace_id != workspace_id:
            raise NotFound("Opkaldet findes ikke")
        at = row.dialled_at
    period = _period(at, tz)
    if not statement.shared_pool(period):
        raise ValidationFailed("Opkald fra før november 2026 behandles af supporten – skriv til info@dialogbot.dk.",
                               code="period_not_supported", field_errors=[{"field": "call_id"}])
    start, end = statement.month_bounds(period, tz)
    events = statement.usage_events(db, workspace_id, start, end, include_pool_credited=True)
    ev = next((e for e in events if e["direction"] == kind and e["id"] == str(call_id)), None)
    if ev is None:  # a demo or test call is never billed, so there is nothing to complain about
        raise ValidationFailed("Opkaldet er ikke en del af forbruget", code="not_billed", field_errors=[{"field": "call_id"}])
    return ev | {"period": period}


def get_for_call(db: OrmSession, kind: str, call_id: uuid.UUID) -> CallDispute | None:
    col = CallDispute.call_id if kind == "inbound" else CallDispute.campaign_call_id
    return db.scalar(select(CallDispute).where(col == call_id))


def create(db: OrmSession, workspace_id: uuid.UUID, *, kind: str, call_id: uuid.UUID, reason: str,
           user_id: uuid.UUID | None, tz: str, request_id: str | None = None) -> tuple[CallDispute, bool]:
    """(complaint, created). A second complaint about the same call returns the first one unchanged."""
    reason = (reason or "").strip()
    if len(reason) < 5:
        raise ValidationFailed("Skriv kort, hvad der var galt med opkaldet", field_errors=[{"field": "reason"}])
    ev = billable_call(db, workspace_id, kind, call_id, tz)
    existing = get_for_call(db, kind, call_id)
    if existing is not None:
        return existing, False
    d = CallDispute(workspace_id=workspace_id, call_id=call_id if kind == "inbound" else None,
                    campaign_call_id=call_id if kind == "outbound" else None, period=ev["period"], call_at=ev["at"],
                    minutes=ev["minutes"], reason=reason[:2000], status="open", created_by=user_id, decision_note="")
    db.add(d)
    db.flush()
    record_audit(db, workspace_id=workspace_id, actor_user_id=user_id, action="billing.dispute_created",
                 object_type="call_dispute", object_id=d.id,
                 after={"kind": kind, "call_id": str(call_id), "minutes": d.minutes, "period": d.period.isoformat()},
                 request_id=request_id)
    return d, True


def kind_of(d: CallDispute) -> str:
    return "inbound" if d.call_id else "outbound"


def invoiced(db: OrmSession, workspace_id: uuid.UUID, period: date) -> bool:
    return db.scalar(select(Invoice.id).where(Invoice.workspace_id == workspace_id, Invoice.month == period,
                                              Invoice.status != "void")) is not None


def credit_for_invoiced_period(db: OrmSession, d: CallDispute, tz: str) -> int:
    """What the call added to its (invoiced) month: the month's usage as invoiced, minus the same month without the
    call. Calls credited earlier the same way are left out of both, so two complaints never credit the same minutes."""
    start, end = statement.month_bounds(d.period, tz)
    a = statement.agreement_at(db, d.workspace_id, end)
    terms = statement.package_terms(a, a.currency if a else customer_market.currency_of(db, d.workspace_id))
    earlier = frozenset((kind_of(x), str(x.call_id or x.campaign_call_id)) for x in db.scalars(select(CallDispute).where(
        CallDispute.workspace_id == d.workspace_id, CallDispute.period == d.period, CallDispute.status == "approved",
        CallDispute.credit_mode == "invoice", CallDispute.id != d.id)))
    this = (kind_of(d), str(d.call_id or d.campaign_call_id))

    def value(exclude: frozenset) -> int:
        events = statement.usage_events(db, d.workspace_id, start, end, exclude=exclude)
        statement.allocate(events, terms)
        return sum(e["net_minor"] for e in events)

    return max(0, value(earlier) - value(earlier | {this}))


def decide(db: OrmSession, d: CallDispute, *, decision: str, note: str, operator_id: uuid.UUID, tz: str,
           request_id: str | None = None) -> CallDispute:
    """Approve or reject an open complaint. Repeating the same decision is a no-op; changing it is a conflict."""
    if decision not in ("approve", "reject"):
        raise ValidationFailed("Vælg godkend eller afvis", field_errors=[{"field": "decision"}])
    target = "approved" if decision == "approve" else "rejected"
    if d.status != "open":
        if d.status == target:
            return d
        raise Conflict("Klagen er allerede afgjort", code="dispute_decided")
    d.status, d.decided_by, d.decided_at, d.decision_note = target, operator_id, datetime.now(UTC), (note or "").strip()[:2000]
    if target == "approved":
        if invoiced(db, d.workspace_id, d.period):
            d.credit_mode = "invoice"
            d.credit_net_minor = credit_for_invoiced_period(db, d, tz)
        else:
            d.credit_mode, d.credit_net_minor = "pool", 0
    db.flush()
    record_audit(db, workspace_id=d.workspace_id, actor_user_id=operator_id, action=f"billing.dispute_{target}",
                 object_type="call_dispute", object_id=d.id,
                 after={"credit_mode": d.credit_mode, "credit_net_minor": d.credit_net_minor, "minutes": d.minutes},
                 request_id=request_id)
    return d


def out(d: CallDispute) -> dict:
    return {"id": str(d.id), "kind": kind_of(d), "call_id": str(d.call_id or d.campaign_call_id),
            "period": d.period.strftime("%Y-%m"), "call_at": d.call_at.isoformat(), "minutes": d.minutes,
            "reason": d.reason, "status": d.status, "created_at": d.created_at.isoformat() if d.created_at else None,
            "decided_at": d.decided_at.isoformat() if d.decided_at else None, "decision_note": d.decision_note,
            "credit_mode": d.credit_mode, "credit_net_minor": d.credit_net_minor}


def month_usage(db: OrmSession, workspace_id: uuid.UUID, month: date, tz: str) -> dict:
    """Konto «Forbrug pr. opkald»: every billed call of the month with its minutes and how the package covered it,
    the complaint on it, and – for an invoiced month – the invoice's frozen lines."""
    month = month.replace(day=1)
    start, end = statement.month_bounds(month, tz)
    inv = db.scalar(select(Invoice).where(Invoice.workspace_id == workspace_id, Invoice.month == month,
                                          Invoice.status != "void"))
    pooled = statement.shared_pool(month)
    events = statement.usage_events(db, workspace_id, start, end, include_pool_credited=True)
    package = None
    if pooled:
        a = statement.agreement_at(db, workspace_id, end)
        terms = statement.package_terms(a, a.currency if a else customer_market.currency_of(db, workspace_id))
        package = statement.allocate(events, terms)
    disputes = {(kind_of(x), str(x.call_id or x.campaign_call_id)): x for x in db.scalars(
        select(CallDispute).where(CallDispute.workspace_id == workspace_id, CallDispute.period == month))}
    calls = {str(c.id): c for c in db.scalars(select(Call).where(Call.id.in_(
        [uuid.UUID(e["id"]) for e in events if e["direction"] == "inbound"])))} if events else {}
    names = dict(db.execute(select(Campaign.id, Campaign.name).where(Campaign.workspace_id == workspace_id)).all())
    items = []
    for e in events:
        d = disputes.get((e["direction"], e["id"]))
        c = calls.get(e["id"])
        items.append({"kind": e["direction"], "id": e["id"], "at": e["at"].isoformat(), "minutes": e["minutes"],
                      "package_minutes": e.get("package_minutes"), "extra_minutes": e.get("extra_minutes"),
                      "net_minor": e.get("net_minor"), "call_net_minor": e.get("call_net_minor"),
                      "outcome": e.get("outcome"), "credited": e["credited"],
                      "label": (c.from_number if c is not None and c.from_number else None) if e["direction"] == "inbound"
                      else names.get(e["campaign_id"]),
                      "dispute": out(d) if d else None, "can_dispute": pooled and d is None})
    return {"month": month.strftime("%Y-%m"), "shared_package": pooled, "package": package,
            "invoiced": inv is not None, "invoice": ({"status": inv.status, "number": inv.number, "lines": inv.lines,
                                                     "net_minor": inv.net_minor, "gross_minor": inv.gross_minor,
                                                     "currency": inv.currency} if inv else None),
            "calls": items}

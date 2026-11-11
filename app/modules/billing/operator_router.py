"""Operator billing (M04): per customer the agreement (its package snapshot), the month's usage (inbound/outbound
minutes, package used/left, overage), invoices and open complaints; the list prices (read-only); and the complaint
queue where the operator approves or rejects a complaint about a call (billing/disputes.py). Operators only."""
from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session as OrmSession

from app.core.auth import Principal
from app.core.errors import NotFound
from app.db import get_db
from app.models import CallDispute, Invoice, Workspace
from app.modules.billing import agreements, customer_market, disputes, markets, statement
from app.modules.reports.service import local_today, tz_of
from app.modules.voices.operator_router import operator

router = APIRouter(prefix="/operator/admin", tags=["admin-operator"])


def customer_billing(db: OrmSession, ws: Workspace, month: date | None = None) -> dict:
    """The agreement snapshot and the month's usage for one customer (also used by the customer detail view)."""
    tz = tz_of(db, ws.id)
    month = (month or local_today(tz)).replace(day=1)
    a = agreements.current(db, ws.id)
    currency = a.currency if a else customer_market.currency_of(db, ws.id)
    start, end = statement.month_bounds(month, tz)
    usage = None
    if statement.shared_pool(month):
        terms = statement.package_terms(statement.agreement_at(db, ws.id, end), currency)
        events = statement.usage_events(db, ws.id, start, end)
        pkg = statement.allocate(events, terms)
        by = {d: [e for e in events if e["direction"] == d] for d in ("inbound", "outbound")}
        usage = {"month": month.strftime("%Y-%m"), "currency": currency, "package": pkg,
                 **{d: {"calls": len(v), "minutes": sum(e["minutes"] for e in v),
                        "extra_minutes": sum(e["extra_minutes"] for e in v), "net_minor": sum(e["net_minor"] for e in v)}
                    for d, v in by.items()},
                 "overage_net_minor": sum(e["net_minor"] for e in events)}
    return {"agreement": (agreements.out(a) | {"outbound_extra_minute_net_minor": a.outbound_extra_minute_net_minor,
                                                "inbound_extra_minute_net_minor": a.inbound_extra_minute_net_minor})
            if a else None,
            "usage": usage}


@router.get("/billing")
def billing_overview(limit: int = Query(default=100, ge=1, le=500), db: OrmSession = Depends(get_db),
                     principal: Principal = Depends(operator)):
    """Every business customer: agreement (package snapshot), this month's usage, last invoices and open complaints."""
    out = []
    for ws in db.scalars(select(Workspace).where(Workspace.kind == "business").order_by(desc(Workspace.created_at)).limit(limit)):
        invoices = db.scalars(select(Invoice).where(Invoice.workspace_id == ws.id).order_by(desc(Invoice.month)).limit(3)).all()
        open_disputes = db.scalar(select(func.count()).select_from(CallDispute).where(
            CallDispute.workspace_id == ws.id, CallDispute.status == "open")) or 0
        out.append({"id": str(ws.id), "name": ws.name, **customer_billing(db, ws),
                    "invoices": [{"month": i.month.strftime("%Y-%m"), "status": i.status, "net_minor": i.net_minor,
                                  "gross_minor": i.gross_minor, "currency": i.currency, "number": i.number} for i in invoices],
                    "open_disputes": open_disputes})
    return {"items": out}


@router.get("/prices")
def list_prices(principal: Principal = Depends(operator)):
    """The list prices per market (read-only; a price changes in app/modules/billing/prices.py / markets.py)."""
    e = markets.export()
    return {"erhverv": e["erhverv"], "included_minutes": e["includedMinutes"], "currencies": e["currencies"]}


@router.get("/disputes")
def list_disputes(status: str | None = Query(default="open", pattern="^(open|approved|rejected|all)$"),
                  db: OrmSession = Depends(get_db), principal: Principal = Depends(operator)):
    q = select(CallDispute, Workspace.name).join(Workspace, Workspace.id == CallDispute.workspace_id) \
        .order_by(CallDispute.created_at)
    if status and status != "all":
        q = q.where(CallDispute.status == status)
    items = []
    for d, name in db.execute(q.limit(500)).all():
        items.append(disputes.out(d) | {"workspace_id": str(d.workspace_id), "workspace_name": name,
                                        "invoiced": disputes.invoiced(db, d.workspace_id, d.period)})
    return {"items": items}


class DecisionIn(BaseModel):
    decision: str = Field(pattern="^(approve|reject)$")
    note: str = Field(default="", max_length=2000)


@router.post("/disputes/{dispute_id}/decision")
def decide_dispute(dispute_id: uuid.UUID, body: DecisionIn, request: Request, db: OrmSession = Depends(get_db),
                   principal: Principal = Depends(operator)):
    """Approve (minutes back in the package, or a credit on the next invoice when the month is invoiced) or reject."""
    d = db.scalar(select(CallDispute).where(CallDispute.id == dispute_id).with_for_update())
    if d is None:
        raise NotFound("Klagen findes ikke")
    disputes.decide(db, d, decision=body.decision, note=body.note, operator_id=principal.user.id,
                    tz=tz_of(db, d.workspace_id), request_id=request.state.request_id)
    db.commit()
    return disputes.out(d) | {"invoiced": disputes.invoiced(db, d.workspace_id, d.period)}

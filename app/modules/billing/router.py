from __future__ import annotations

import re
from datetime import date

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from app.core.audit import record_audit
from app.core.auth import WorkspaceContext, require_capability
from app.core.errors import Conflict, ValidationFailed
from app.db import get_db
from app.modules.billing import stripe
from app.modules.billing.statement import statement
from app.modules.reports.service import local_today, tz_of

router = APIRouter(prefix="/workspaces/{workspace_id}/billing", tags=["billing"])


@router.get("/statement")
def get_statement(month: str | None = Query(default=None, description="YYYY-MM; default: current month"),
                  ctx: WorkspaceContext = Depends(require_capability("billing.read")), db: OrmSession = Depends(get_db)):
    """Preview of what the month would cost under the agreement. Not an invoice; nothing is charged."""
    tz = tz_of(db, ctx.workspace.id)
    if month is None:
        m = local_today(tz).replace(day=1)
    elif re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", month):
        m = date(int(month[:4]), int(month[5:]), 1)
    else:
        raise ValidationFailed("month skal være på formen ÅÅÅÅ-MM", field_errors=[{"field": "month"}])
    return statement(db, ctx.workspace.id, m, tz)


# --------------------------------------------------------------------------- Stripe: card and invoices

def _month(value: str) -> date:
    if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", value or ""):
        raise ValidationFailed("month skal være på formen ÅÅÅÅ-MM", field_errors=[{"field": "month"}])
    return date(int(value[:4]), int(value[5:]), 1)


@router.get("/account")
def get_account(ctx: WorkspaceContext = Depends(require_capability("billing.read")), db: OrmSession = Depends(get_db)):
    from app.models import BillingAccount

    a = db.get(BillingAccount, ctx.workspace.id)
    card = {"brand": a.card_brand, "last4": a.card_last4, "exp": a.card_exp} if a and a.payment_method_id else None
    return {"configured": stripe.configured(), "card": card, "billing_email": a.billing_email if a else None,
            "can_manage": ctx.can("billing.manage")}


@router.post("/card/checkout")
def card_checkout(request: Request, ctx: WorkspaceContext = Depends(require_capability("billing.manage")),
                  db: OrmSession = Depends(get_db)):
    """Stripe Checkout (setup mode): the owner saves a card at Stripe. Nothing is charged now."""
    from app.models import User

    user = db.get(User, ctx.user_id)
    url = stripe.card_checkout(db, ctx.workspace, user.email if user else None)
    record_audit(db, workspace_id=ctx.workspace.id, actor_user_id=ctx.user_id, action="billing.card_checkout_started",
                 object_type="billing_account", object_id=ctx.workspace.id, request_id=request.state.request_id)
    db.commit()
    return {"url": url}


@router.get("/invoices")
def list_invoices(ctx: WorkspaceContext = Depends(require_capability("billing.read")), db: OrmSession = Depends(get_db)):
    from app.models import Invoice

    rows = db.scalars(select(Invoice).where(Invoice.workspace_id == ctx.workspace.id).order_by(Invoice.month.desc()))
    return {"items": [stripe.invoice_out(i) for i in rows]}


class InvoiceIn(BaseModel):
    month: str


@router.post("/invoices", status_code=201)
def create_invoice(body: InvoiceIn, request: Request, response: Response,
                   ctx: WorkspaceContext = Depends(require_capability("billing.manage")), db: OrmSession = Depends(get_db)):
    """Invoice a month now (normally the worker does it after the month closes). Idempotent per month."""
    tz = tz_of(db, ctx.workspace.id)
    m = _month(body.month)
    if m >= local_today(tz).replace(day=1):
        raise ValidationFailed("Kun afsluttede måneder kan faktureres", field_errors=[{"field": "month"}])
    inv = stripe.create_invoice(db, ctx.workspace, m, tz)
    if inv is None:
        raise Conflict("Der er intet at fakturere for måneden", code="nothing_to_invoice")
    record_audit(db, workspace_id=ctx.workspace.id, actor_user_id=ctx.user_id, action="billing.invoice_created",
                 object_type="invoice", object_id=inv.id, after={"month": body.month, "gross_minor": inv.gross_minor},
                 request_id=request.state.request_id)
    db.commit()
    return stripe.invoice_out(inv)

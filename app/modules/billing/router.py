from __future__ import annotations

import logging
import re
import uuid
from datetime import UTC, date, datetime
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from app.core.audit import record_audit
from app.core.auth import WorkspaceContext, require_capability
from app.core.errors import ApiError, Conflict, ValidationFailed
from app.db import get_db
from app.modules.billing import customer_market, stripe
from app.modules.billing.statement import statement
from app.modules.reports.service import local_today, tz_of

log = logging.getLogger(__name__)
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


# --------------------------------------------------------------------------- usage per call and complaints (B03/B04)

@router.get("/usage")
def get_usage(month: str | None = Query(default=None, description="YYYY-MM; default: current month"),
              ctx: WorkspaceContext = Depends(require_capability("billing.read")), db: OrmSession = Depends(get_db)):
    """Every billed call of the month with its minutes, how the package covered it and any complaint about it; for an
    invoiced month also the invoice's frozen lines."""
    from app.modules.billing import disputes

    tz = tz_of(db, ctx.workspace.id)
    m = local_today(tz).replace(day=1) if month is None else _month(month)
    return disputes.month_usage(db, ctx.workspace.id, m, tz)


class DisputeIn(BaseModel):
    kind: str = Field(pattern="^(inbound|outbound)$")
    call_id: uuid.UUID
    reason: str = Field(min_length=1, max_length=2000)


@router.get("/disputes")
def list_disputes(ctx: WorkspaceContext = Depends(require_capability("billing.read")), db: OrmSession = Depends(get_db)):
    from app.models import CallDispute
    from app.modules.billing import disputes

    rows = db.scalars(select(CallDispute).where(CallDispute.workspace_id == ctx.workspace.id)
                      .order_by(CallDispute.created_at.desc()))
    return {"items": [disputes.out(d) for d in rows]}


@router.post("/disputes", status_code=201)
def create_dispute(body: DisputeIn, request: Request, response: Response,
                   ctx: WorkspaceContext = Depends(require_capability("billing.manage")), db: OrmSession = Depends(get_db)):
    """Complain about one billed call. One complaint per call: asking again returns the first one (200)."""
    from app.modules.billing import disputes

    d, created = disputes.create(db, ctx.workspace.id, kind=body.kind, call_id=body.call_id, reason=body.reason,
                                 user_id=ctx.user_id, tz=tz_of(db, ctx.workspace.id), request_id=request.state.request_id)
    db.commit()
    if not created:
        response.status_code = 200
    return disputes.out(d)


# --------------------------------------------------------------------------- Stripe: card and invoices

def _month(value: str) -> date:
    if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", value or ""):
        raise ValidationFailed("month skal være på formen ÅÅÅÅ-MM", field_errors=[{"field": "month"}])
    return date(int(value[:4]), int(value[5:]), 1)


def _account_out(db: OrmSession, ctx: WorkspaceContext) -> dict:
    from app.models import BillingAccount

    a = db.get(BillingAccount, ctx.workspace.id)
    card = {"brand": a.card_brand, "last4": a.card_last4, "exp": a.card_exp} if a and a.payment_method_id else None
    # test_mode: Stripe's sandbox (sk_test_) – shown on Konto so nobody believes a real card was charged
    from app.modules.billing import grace
    from app.modules.integrations.registry import stripe_test_mode

    now = datetime.now(UTC)
    paid = grace.strictly_paid(db, ctx.workspace.id, now)
    ends = None if paid else grace.grace_ends(a, now)
    # subscription: paid by the plain rule; else in_grace until grace_ends (chat and phone still run), then stopped
    subscription = {"paid": paid, "in_grace": bool(ends and now < ends), "grace_ends": ends.isoformat() if ends else None,
                    "card_expired": bool(a and a.payment_method_id and grace.card_expired(a.card_exp, now)),
                    "payment_failed": bool(a and a.payment_failed_at)}
    return {"configured": stripe.configured(), "test_mode": stripe.configured() and stripe_test_mode(), "card": card, "billing_email": a.billing_email if a else None,
            "can_manage": ctx.can("billing.manage"), "subscription": subscription} | customer_market.account_market(db, ctx.workspace.id)


@router.get("/account")
def get_account(ctx: WorkspaceContext = Depends(require_capability("billing.read")), db: OrmSession = Depends(get_db)):
    """Card, billing e-mail and the market: country, currency (locked once there is an agreement), VAT number and the
    VAT the invoices carry ({kind: domestic|reverse_charge|outside_eu|vat_number_required, rate_bp, country, note})."""
    return _account_out(db, ctx)


class VatNumberIn(BaseModel):
    vat_number: str = Field(max_length=40, description="Momsnummer, fx SE556677889901 eller DE123456789. Tom = fjern.")


@router.put("/vat-number")
def put_vat_number(body: VatNumberIn, request: Request,
                   ctx: WorkspaceContext = Depends(require_capability("billing.manage")), db: OrmSession = Depends(get_db)):
    """The company's VAT number (normalised; it must fit the company's country – EL for Greece). Empty clears it. An EU
    company outside Denmark is invoiced without VAT (reverse charge) only with one. The Stripe customer's tax id
    follows it."""
    country = customer_market.country_of(db, ctx.workspace.id)
    number = customer_market.normalize_vat_number(body.vat_number, country)
    a = stripe.account(db, ctx.workspace.id, lock=True)
    before = a.vat_number
    if number != before:
        a.vat_number = number
        a.updated_at = datetime.now(UTC)
        record_audit(db, workspace_id=ctx.workspace.id, actor_user_id=ctx.user_id, action="billing.vat_number_changed",
                     object_type="billing_account", object_id=ctx.workspace.id, before={"vat_number": before},
                     after={"vat_number": number}, request_id=request.state.request_id)
        db.flush()
        if a.stripe_customer_id and stripe.configured():
            try:
                stripe.sync_customer(db, a)
            except ApiError:  # the number is saved; the customer is synced again before the next invoice / card
                log.warning("billing: could not sync the Stripe tax id for %s", ctx.workspace.id, exc_info=True)
    db.commit()
    return _account_out(db, ctx)


class CardCheckoutIn(BaseModel):
    return_to: Literal["konto", "opsaetning"] = Field(
        default="konto", description="Where Stripe sends the owner back: Konto (default) or the guide's payment step.")


@router.post("/card/checkout")
def card_checkout(request: Request, body: CardCheckoutIn | None = None,
                  ctx: WorkspaceContext = Depends(require_capability("billing.manage")), db: OrmSession = Depends(get_db)):
    """Stripe Checkout (setup mode): the owner saves a card at Stripe. Nothing is charged now."""
    from app.models import User

    user = db.get(User, ctx.user_id)
    url = stripe.card_checkout(db, ctx.workspace, user.email if user else None,
                               return_to=body.return_to if body else "konto")
    record_audit(db, workspace_id=ctx.workspace.id, actor_user_id=ctx.user_id, action="billing.card_checkout_started",
                 object_type="billing_account", object_id=ctx.workspace.id, request_id=request.state.request_id)
    db.commit()
    return {"url": url}


# --------------------------------------------------------------------------- discount code (operators make them in the admin)

class DiscountIn(BaseModel):
    code: str


@router.get("/discount")
def get_discount(ctx: WorkspaceContext = Depends(require_capability("billing.read")), db: OrmSession = Depends(get_db)):
    """The discount code this workspace uses (if any): the code, its terms and the months it covers."""
    from app.modules.billing import discounts

    return discounts.erhverv_status(db, ctx.workspace.id, tz_of(db, ctx.workspace.id)) | {"can_manage": ctx.can("billing.manage")}


@router.put("/discount")
def put_discount(body: DiscountIn, request: Request, ctx: WorkspaceContext = Depends(require_capability("billing.manage")),
                 db: OrmSession = Depends(get_db)):
    """The owner types a discount code. One per workspace; it counts from the current month's statement."""
    from app.modules.billing import discounts

    r = discounts.redeem_erhverv(db, ctx.workspace.id, body.code)
    record_audit(db, workspace_id=ctx.workspace.id, actor_user_id=ctx.user_id, action="billing.discount_code_used",
                 object_type="discount_redemption", object_id=r.id, after={"code": discounts.normalize(body.code)},
                 request_id=request.state.request_id)
    db.commit()
    return discounts.erhverv_status(db, ctx.workspace.id, tz_of(db, ctx.workspace.id)) | {"can_manage": True}


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

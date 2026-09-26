"""Stripe: card on file and monthly invoices in arrears (test mode first).

- The owner saves a card through Stripe Checkout in *setup* mode – card data never touches us.
- After a month closes, the worker turns that month's statement (model A subscription, model B
  approved leads, campaign packages) into ONE Stripe invoice with 25 % Danish VAT, charged
  automatically. One invoice per workspace and month (unique row + Stripe idempotency key).
- Stripe webhooks (signed) move our invoice row to paid / payment_failed / void.
- Payment never starts calls: nothing in campaigns or telephony reads payment state.

Stripe is called with plain HTTPS (form-encoded) through `request()`, which tests replace.
"""
from __future__ import annotations

import hashlib
import hmac
import time
import uuid
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as OrmSession

from app.config import get_settings
from app.core.errors import ApiError, NotImplementedYet, Unauthenticated
from app.models import BillingAccount, BusinessProfile, Invoice, Workspace
from app.modules.billing.statement import statement

API = "https://api.stripe.com/v1"
SIGNATURE_TOLERANCE_SECONDS = 300
_tax_rate_id: str | None = None


class PaymentNotConfigured(NotImplementedYet):
    code = "payment_not_configured"


class StripeFailed(ApiError):
    status_code = 502
    code = "stripe_failed"


def configured() -> bool:
    return bool(get_settings().stripe_secret_key)


def _flatten(data: dict, prefix: str = "") -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for k, v in data.items():
        key = f"{prefix}[{k}]" if prefix else k
        if isinstance(v, dict):
            out += _flatten(v, key)
        elif isinstance(v, list):
            for i, x in enumerate(v):
                out += _flatten(x, f"{key}[{i}]") if isinstance(x, dict) else [(f"{key}[{i}]", str(x))]
        elif v is not None:
            out.append((key, "true" if v is True else "false" if v is False else str(v)))
    return out


def request(method: str, path: str, data: dict | None = None, *, idempotency_key: str | None = None) -> dict:
    import httpx

    key = get_settings().stripe_secret_key
    if not key:
        raise PaymentNotConfigured("Kortbetaling er ikke sat op på serveren (STRIPE_SECRET_KEY mangler)")
    headers = {"authorization": f"Bearer {key}"}
    if idempotency_key:
        headers["idempotency-key"] = idempotency_key
    try:
        r = httpx.request(method, f"{API}{path}", data=_flatten(data or {}) if method != "GET" else None,
                          params=_flatten(data or {}) if method == "GET" else None, headers=headers, timeout=30.0)
    except httpx.HTTPError as e:
        raise StripeFailed("Stripe svarede ikke") from e
    body = r.json() if r.content else {}
    if r.status_code >= 400:
        msg = (body.get("error") or {}).get("message") or f"HTTP {r.status_code}"
        raise StripeFailed(f"Stripe afviste kaldet: {msg}"[:300])
    return body


# --------------------------------------------------------------------------- account and card

def account(db: OrmSession, ws_id: uuid.UUID, *, lock: bool = False) -> BillingAccount:
    q = select(BillingAccount).where(BillingAccount.workspace_id == ws_id)
    a = db.scalar(q.with_for_update() if lock else q)
    if a is None:
        a = BillingAccount(workspace_id=ws_id)
        db.add(a)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            a = db.scalar(q)
    return a


def ensure_customer(db: OrmSession, ws: Workspace, email: str | None) -> BillingAccount:
    a = account(db, ws.id, lock=True)
    if not a.stripe_customer_id:
        p = db.get(BusinessProfile, ws.id)
        c = request("POST", "/customers", {"name": (p.legal_name if p and p.legal_name else ws.name)[:200],
                                            "email": a.billing_email or email, "preferred_locales": ["da"],
                                            "metadata": {"workspace_id": str(ws.id)}},
                    idempotency_key=f"dialogbot-customer-{ws.id}")
        a.stripe_customer_id = c["id"]
        if not a.billing_email and email:
            a.billing_email = email
    return a


def card_checkout(db: OrmSession, ws: Workspace, email: str | None) -> str:
    """A Stripe Checkout page (setup mode) where the owner saves a card. Returns its URL."""
    a = ensure_customer(db, ws, email)
    base = get_settings().frontend_base_url
    s = request("POST", "/checkout/sessions", {
        "mode": "setup", "customer": a.stripe_customer_id, "currency": "dkk", "payment_method_types": ["card"],
        "locale": "da", "success_url": f"{base}/app/billing?card=saved", "cancel_url": f"{base}/app/billing?card=cancelled",
        "metadata": {"workspace_id": str(ws.id)}, "setup_intent_data": {"metadata": {"workspace_id": str(ws.id)}}})
    return s["url"]


def save_card_from_setup_intent(db: OrmSession, setup_intent_id: str) -> BillingAccount | None:
    si = request("GET", f"/setup_intents/{setup_intent_id}")
    ws_id = (si.get("metadata") or {}).get("workspace_id")
    pm_id = si.get("payment_method")
    if not ws_id or not pm_id or si.get("status") != "succeeded":
        return None
    a = account(db, uuid.UUID(ws_id), lock=True)
    if not a.stripe_customer_id or si.get("customer") != a.stripe_customer_id:
        return None
    request("POST", f"/customers/{a.stripe_customer_id}", {"invoice_settings": {"default_payment_method": pm_id}})
    pm = request("GET", f"/payment_methods/{pm_id}")
    card = pm.get("card") or {}
    a.payment_method_id, a.card_brand, a.card_last4 = pm_id, str(card.get("brand") or "")[:20], str(card.get("last4") or "")[:4]
    a.card_exp = f"{card.get('exp_month', 0):02d}/{str(card.get('exp_year', ''))[-2:]}" if card.get("exp_month") else None
    a.updated_at = datetime.now(UTC)
    return a


# --------------------------------------------------------------------------- invoices

def tax_rate_id() -> str:
    """The 25 % Danish VAT rate in the Stripe account (created once if missing)."""
    global _tax_rate_id
    if _tax_rate_id:
        return _tax_rate_id
    rows = request("GET", "/tax_rates", {"active": True, "limit": 100}).get("data") or []
    found = next((r for r in rows if (r.get("metadata") or {}).get("dialogbot") == "dk_vat_25"), None)
    if found is None:
        found = request("POST", "/tax_rates", {"display_name": "Moms", "percentage": 25, "inclusive": False,
                                               "country": "DK", "jurisdiction": "DK", "metadata": {"dialogbot": "dk_vat_25"}},
                        idempotency_key="dialogbot-tax-rate-dk-vat-25")
    _tax_rate_id = found["id"]
    return _tax_rate_id


def create_invoice(db: OrmSession, ws: Workspace, month: date, tz: str) -> Invoice | None:
    """Invoice one closed month. None when there is nothing to charge. Idempotent per workspace+month."""
    existing = db.scalar(select(Invoice).where(Invoice.workspace_id == ws.id, Invoice.month == month))
    if existing is not None:
        return existing
    a = account(db, ws.id, lock=True)
    if not a.stripe_customer_id or not a.payment_method_id:
        raise ApiError("Tilføj et betalingskort først", code="no_payment_method", status_code=409)
    st = statement(db, ws.id, month, tz)
    if st["totals"]["net_minor"] <= 0:
        return None
    inv = Invoice(workspace_id=ws.id, month=month, status="creating", currency="DKK", net_minor=st["totals"]["net_minor"],
                  tax_minor=st["totals"]["tax_minor"], gross_minor=st["totals"]["gross_minor"], lines=st["lines"])
    db.add(inv)
    db.flush()  # the unique (workspace, month) row reserves the month before Stripe is called
    key = f"dialogbot-invoice-{ws.id}-{month:%Y-%m}"
    label = st["month"]
    si = request("POST", "/invoices", {
        "customer": a.stripe_customer_id, "collection_method": "charge_automatically", "auto_advance": True,
        "currency": "dkk", "pending_invoice_items_behavior": "exclude", "default_tax_rates": [tax_rate_id()],
        "description": f"Dialogbot {label}", "metadata": {"workspace_id": str(ws.id), "month": label}},
        idempotency_key=key)
    for i, line in enumerate(st["lines"]):
        request("POST", "/invoiceitems", {"customer": a.stripe_customer_id, "invoice": si["id"], "currency": "dkk",
                                          "amount": line["net_minor"], "description": line["description"][:500],
                                          "metadata": {"kind": line["kind"]}},
                idempotency_key=f"{key}-line-{i}")
    fin = request("POST", f"/invoices/{si['id']}/finalize", {"auto_advance": True}, idempotency_key=f"{key}-finalize")
    apply_stripe_invoice(inv, fin)
    return inv


STATUS = {"draft": "creating", "open": "open", "paid": "paid", "void": "void", "uncollectible": "failed"}


def apply_stripe_invoice(inv: Invoice, obj: dict) -> None:
    inv.stripe_invoice_id = obj.get("id") or inv.stripe_invoice_id
    inv.status = STATUS.get(str(obj.get("status")), inv.status)
    inv.number = obj.get("number") or inv.number
    inv.hosted_invoice_url = obj.get("hosted_invoice_url") or inv.hosted_invoice_url
    inv.invoice_pdf = obj.get("invoice_pdf") or inv.invoice_pdf
    if obj.get("total") is not None and obj.get("total") != inv.gross_minor:
        inv.note = f"Stripe-total {obj.get('total')} øre afviger fra oversigtens {inv.gross_minor} øre"[:300]
    inv.updated_at = datetime.now(UTC)


def invoice_due(db: OrmSession, today_utc: datetime | None = None) -> int:
    """Worker job: invoice last month for every workspace with a card and no invoice yet."""
    from app.modules.reports.service import local_today, tz_of

    if not configured():
        return 0
    n = 0
    for a in db.scalars(select(BillingAccount).where(BillingAccount.payment_method_id.is_not(None))).all():
        ws = db.get(Workspace, a.workspace_id)
        tz = tz_of(db, ws.id)
        first = local_today(tz).replace(day=1)
        last_month = date(first.year - (first.month == 1), (first.month - 2) % 12 + 1, 1)
        if db.scalar(select(Invoice.id).where(Invoice.workspace_id == ws.id, Invoice.month == last_month)):
            continue
        try:
            if create_invoice(db, ws, last_month, tz) is not None:
                n += 1
            db.commit()
        except ApiError:
            db.rollback()
    return n


# --------------------------------------------------------------------------- webhook

def verify_signature(secret: str, header: str | None, payload: bytes, now: float | None = None) -> None:
    parts = dict(p.split("=", 1) for p in (header or "").split(",") if "=" in p)
    sigs = [p.split("=", 1)[1] for p in (header or "").split(",") if p.startswith("v1=")]
    try:
        ts = int(parts.get("t", ""))
    except ValueError as e:
        raise Unauthenticated("Ugyldig Stripe-signatur", code="invalid_signature") from e
    if abs((now or time.time()) - ts) > SIGNATURE_TOLERANCE_SECONDS:
        raise Unauthenticated("Stripe-signaturen er for gammel", code="invalid_signature")
    expected = hmac.new(secret.encode(), f"{ts}.".encode() + payload, hashlib.sha256).hexdigest()
    if not any(hmac.compare_digest(expected, s) for s in sigs):
        raise Unauthenticated("Ugyldig Stripe-signatur", code="invalid_signature")


def process_event(db: OrmSession, event: dict) -> str:
    kind = str(event.get("type") or "")
    obj = (event.get("data") or {}).get("object") or {}
    if kind == "checkout.session.completed" and obj.get("mode") == "setup" and obj.get("setup_intent"):
        return "applied" if save_card_from_setup_intent(db, str(obj["setup_intent"])) else "ignored"
    if kind.startswith("invoice.") and obj.get("id"):
        inv = db.scalar(select(Invoice).where(Invoice.stripe_invoice_id == obj["id"]))
        if inv is None:
            return "unmatched"
        apply_stripe_invoice(inv, obj)
        if kind == "invoice.payment_failed":
            inv.status = "payment_failed"
        return "applied"
    return "ignored"


def invoice_out(i: Invoice) -> dict:
    return {"id": str(i.id), "month": i.month.strftime("%Y-%m"), "status": i.status, "number": i.number,
            "net_minor": i.net_minor, "tax_minor": i.tax_minor, "gross_minor": i.gross_minor,
            "hosted_invoice_url": i.hosted_invoice_url, "invoice_pdf": i.invoice_pdf, "note": i.note,
            "created_at": i.created_at.isoformat()}

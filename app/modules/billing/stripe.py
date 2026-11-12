"""Stripe: card on file and monthly invoices in arrears (test mode first).

- The owner saves a card through Stripe Checkout in *setup* mode – card data never touches us.
- After a month closes, the worker turns that month's statement (the subscription, minutes above the shared
  package; old model-B leads, 4 kr. campaign calls and old campaign packages on old months) into ONE Stripe invoice, charged
  automatically. One invoice per workspace and month (unique row + Stripe idempotency key).
- Markets (docs/markets.md): the invoice is in the statement's currency. A Danish company gets 25 % Danish VAT (the
  exclusive tax rate "dk_vat_25"); an EU company with a VAT number gets no tax rate and the reverse-charge note, a
  company outside the EU no tax rate and the outside-EU note (footer + custom field). The Stripe customer carries the
  company's language and its VAT number as a customer tax id (eu_vat / no_vat), so Stripe prints it on the invoice.
  An EU company outside Denmark without a VAT number cannot save a card or be invoiced (409 vat_number_required).
- STRIPE_TAX_ENABLED=true: Stripe Tax decides the VAT instead – the invoice has automatic_tax, every item the SaaS
  business tax code and tax_behavior exclusive, no tax rates and no note of ours (Stripe prints reverse charge itself
  from the customer's address and tax id); the Invoice row takes net/tax/gross from Stripe's finalized invoice.
- Stripe webhooks (signed) move our invoice row to paid / payment_failed / void.
- Payment never starts calls: nothing in campaigns or telephony reads payment state.

Stripe is called with plain HTTPS (form-encoded) through `request()`, which tests replace.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import time
import uuid
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as OrmSession

from app.config import get_settings
from app.core.errors import ApiError, NotImplementedYet, Unauthenticated
from app.models import BillingAccount, BusinessProfile, Invoice, Workspace
from app.modules.billing import customer_market
from app.modules.billing.statement import statement

log = logging.getLogger(__name__)
API = "https://api.stripe.com/v1"
SIGNATURE_TOLERANCE_SECONDS = 300
_tax_rate_ids: dict[tuple[str, int, bool], str] = {}  # (country, basis points, inclusive) → Stripe tax rate id
# Seller identity printed on every invoice (bogføringsloven/momsloven: name, CVR, address).
INVOICE_FOOTER = "Dialogbot · CVR-nr. 25632710 · Abildgade 18, 8200 Aarhus, Danmark · info@dialogbot.dk"


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


def request(method: str, path: str, data: dict | None = None, *, idempotency_key: str | None = None,
            version: str | None = None) -> dict:
    """One Stripe call. `version` pins the Stripe-Version header for that call alone (a parameter that only exists
    from a given API version, such as Checkout branding_settings); everything else runs on the account's version."""
    import httpx

    key = get_settings().stripe_secret_key
    if not key:
        raise PaymentNotConfigured("Kortbetaling er ikke sat op på serveren (STRIPE_SECRET_KEY mangler)")
    headers = {"authorization": f"Bearer {key}"}
    if idempotency_key:
        headers["idempotency-key"] = idempotency_key
    if version:
        headers["stripe-version"] = version
    try:
        # httpx takes a mapping (a list of pairs is read as raw byte content); the flattened keys are unique.
        form = dict(_flatten(data or {}))
        r = httpx.request(method, f"{API}{path}", data=form if method != "GET" else None,
                          params=form if method == "GET" else None, headers=headers, timeout=30.0)
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
    """The workspace's Stripe customer: created with the company's language and VAT number (customer tax id); an
    existing one is brought in line with them (sync_customer)."""
    a = account(db, ws.id, lock=True)
    country = customer_market.country_of(db, ws.id)
    if not a.stripe_customer_id:
        p = db.get(BusinessProfile, ws.id)
        data: dict = {"name": (p.legal_name if p and p.legal_name else ws.name)[:200],
                      "email": a.billing_email or email, "preferred_locales": [customer_market.stripe_locale(country)],
                      "address": customer_market.stripe_address(db, ws.id), "metadata": {"workspace_id": str(ws.id)}}
        if tax_id := customer_market.stripe_tax_id(country, a.vat_number):
            data["tax_id_data"] = [tax_id]
        c = request("POST", "/customers", data, idempotency_key=f"dialogbot-customer-{ws.id}")
        a.stripe_customer_id = c["id"]
        if not a.billing_email and email:
            a.billing_email = email
    else:
        sync_customer(db, a)
    return a


def sync_customer(db: OrmSession, a: BillingAccount) -> None:
    """Idempotent: the customer's preferred language follows the company's country, and its VAT customer tax id is
    exactly the account's VAT number (an old eu_vat/no_vat id is removed when the number changes or is cleared), and
    its address is the company's (Stripe Tax needs it)."""
    if not a.stripe_customer_id:
        return
    country = customer_market.country_of(db, a.workspace_id)
    cid = a.stripe_customer_id
    request("POST", f"/customers/{cid}", {"preferred_locales": [customer_market.stripe_locale(country)],
                                          "address": customer_market.stripe_address(db, a.workspace_id)})
    want = customer_market.stripe_tax_id(country, a.vat_number)
    have = False
    for t in request("GET", f"/customers/{cid}/tax_ids", {"limit": 100}).get("data") or []:
        if want and t.get("type") == want["type"] and t.get("value") == want["value"]:
            have = True
        elif t.get("type") in ("eu_vat", "no_vat") and t.get("id"):
            request("DELETE", f"/customers/{cid}/tax_ids/{t['id']}")
    if want and not have:
        request("POST", f"/customers/{cid}/tax_ids", want)


def require_vat_number(db: OrmSession, ws_id: uuid.UUID) -> dict:
    """The workspace's VAT; 409 vat_number_required for an EU company outside Denmark without a VAT number."""
    vat = customer_market.vat_of(db, ws_id)
    if vat["kind"] == "vat_number_required":
        raise ApiError(customer_market.VAT_NUMBER_REQUIRED_MESSAGE, code="vat_number_required", status_code=409,
                       field_errors=[{"field": "vat_number", "message": "Momsnummer mangler"}])
    return vat


def card_checkout(db: OrmSession, ws: Workspace, email: str | None, *, return_to: str = "konto") -> str:
    """A Stripe Checkout page (setup mode) where the owner saves a card. Returns its URL. In the workspace's currency
    and the company's language; an EU company outside Denmark must give its VAT number first (409)."""
    require_vat_number(db, ws.id)
    a = ensure_customer(db, ws, email)
    base = get_settings().frontend_base_url
    back = "/opsaetning/betaling" if return_to == "opsaetning" else "/app/konto"
    s = request("POST", "/checkout/sessions", {
        "mode": "setup", "customer": a.stripe_customer_id, "currency": customer_market.currency_of(db, ws.id).lower(),
        "payment_method_types": ["card"], "locale": customer_market.stripe_locale(customer_market.country_of(db, ws.id)),
        "success_url": f"{base}{back}?card=saved", "cancel_url": f"{base}{back}?card=cancelled",
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
    # A new card ends a failed payment's lapse and the grace at once (Fürster 12/11).
    a.payment_failed_at = None
    from app.modules.billing import grace

    db.flush()
    grace.sync(db, a.workspace_id)
    return a


# --------------------------------------------------------------------------- invoices

def tax_rate_metadata(country: str, bp: int, inclusive: bool) -> str:
    """The `dialogbot` metadata that identifies one of our tax rates. The original Danish 25 % exclusive rate keeps its
    old tag, so existing Stripe accounts reuse it."""
    if (country.upper(), bp, inclusive) == ("DK", 2500, False):
        return "dk_vat_25"
    return f"{country.lower()}_vat_{bp}_{'incl' if inclusive else 'excl'}"


def tax_rate_id(country: str = "DK", bp: int = 2500, inclusive: bool = False) -> str:
    """A VAT rate in the Stripe account (found by metadata, created once if missing), cached per (country, bp,
    inclusive). Default: the 25 % Danish VAT added on top of an Erhverv invoice."""
    key = (country.upper(), bp, inclusive)
    if key in _tax_rate_ids:
        return _tax_rate_ids[key]
    tag = tax_rate_metadata(country, bp, inclusive)
    found = None
    params: dict = {"active": True, "limit": 100}
    for _ in range(10):
        page = request("GET", "/tax_rates", params)
        rows = page.get("data") or []
        found = next((r for r in rows if (r.get("metadata") or {}).get("dialogbot") == tag), None)
        if found is not None or not page.get("has_more") or not rows:
            break
        params = {"active": True, "limit": 100, "starting_after": rows[-1]["id"]}
    if found is None:
        name = "Moms" if key[0] == "DK" else "MVA" if key[0] == "NO" else "VAT"
        idem = "dialogbot-tax-rate-dk-vat-25" if tag == "dk_vat_25" else f"dialogbot-tax-rate-{tag}"
        found = request("POST", "/tax_rates", {"display_name": name, "percentage": bp // 100 if bp % 100 == 0 else bp / 100,
                                               "inclusive": inclusive, "country": key[0], "jurisdiction": key[0],
                                               "metadata": {"dialogbot": tag}},
                        idempotency_key=idem)
    _tax_rate_ids[key] = found["id"]
    return found["id"]


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
    vat = st["vat"]
    if vat["kind"] == "vat_number_required":
        raise ApiError(customer_market.VAT_NUMBER_REQUIRED_MESSAGE, code="vat_number_required", status_code=409)
    currency = st["currency"]
    inv = Invoice(workspace_id=ws.id, month=month, status="creating", currency=currency, net_minor=st["totals"]["net_minor"],
                  tax_minor=st["totals"]["tax_minor"], gross_minor=st["totals"]["gross_minor"], lines=st["lines"])
    db.add(inv)
    db.flush()  # the unique (workspace, month) row reserves the month before Stripe is called
    auto_tax = customer_market.stripe_tax_enabled()
    if auto_tax or vat["kind"] != "domestic":
        sync_customer(db, a)  # address and VAT number (customer tax id) on the customer before the invoice is final
    key = f"dialogbot-invoice-{ws.id}-{month:%Y-%m}"
    label = st["month"]
    data: dict = {
        "customer": a.stripe_customer_id, "collection_method": "charge_automatically", "auto_advance": True,
        "currency": currency.lower(), "pending_invoice_items_behavior": "exclude",
        "description": f"Dialogbot {label}", "footer": INVOICE_FOOTER, "metadata": {"workspace_id": str(ws.id), "month": label}}
    if auto_tax:
        data["automatic_tax"] = {"enabled": True}  # Stripe Tax: rate, reverse charge and its note are Stripe's
    elif vat["rate_bp"] > 0:
        data["default_tax_rates"] = [tax_rate_id(vat["country"], vat["rate_bp"], False)]
    if vat.get("note") and not auto_tax:  # reverse charge / outside the EU: no VAT, and the invoice must say why
        data["footer"] = f"{INVOICE_FOOTER}\n{vat['note']}"
        data["custom_fields"] = [{"name": "VAT", "value": vat["note"][:140]}]
    si = request("POST", "/invoices", data, idempotency_key=key)
    for i, line in enumerate(st["lines"]):
        item = {"customer": a.stripe_customer_id, "invoice": si["id"], "currency": currency.lower(),
                "amount": line["net_minor"], "description": line["description"][:500], "metadata": {"kind": line["kind"]}}
        if auto_tax:
            item |= {"tax_code": customer_market.TAX_CODE_ERHVERV, "tax_behavior": "exclusive"}
        request("POST", "/invoiceitems", item, idempotency_key=f"{key}-line-{i}")
    fin = request("POST", f"/invoices/{si['id']}/finalize", {"auto_advance": True}, idempotency_key=f"{key}-finalize")
    inv.tax_source = "stripe_tax" if auto_tax else "manual"
    if auto_tax:
        _amounts_from_stripe(inv, fin)
    apply_stripe_invoice(inv, fin)
    return inv


def _amounts_from_stripe(inv: Invoice, obj: dict) -> None:
    """With Stripe Tax the charged amounts are Stripe's: net = total_excluding_tax, tax = Σ total_taxes (older API
    versions: `tax`), gross = total."""
    total = obj.get("total")
    if total is None:
        return
    taxes = obj.get("total_taxes")
    if isinstance(taxes, list):
        tax = sum(int(t.get("amount") or 0) for t in taxes)
    elif obj.get("tax") is not None:
        tax = int(obj["tax"])
    else:
        tax = int(total) - int(obj.get("total_excluding_tax") or total)
    net = obj.get("total_excluding_tax")
    inv.gross_minor = int(total)
    inv.tax_minor = tax
    inv.net_minor = int(net) if net is not None else int(total) - tax


STATUS = {"draft": "creating", "open": "open", "paid": "paid", "void": "void", "uncollectible": "failed"}
# Stripe does not deliver events in order: once an invoice is paid or void, a late event about an earlier state
# (open, payment_failed, uncollectible) must not move it back. Refunds are handled separately (credit notes).
TERMINAL = ("paid", "void")


def apply_stripe_invoice(inv: Invoice, obj: dict) -> None:
    inv.stripe_invoice_id = obj.get("id") or inv.stripe_invoice_id
    new = STATUS.get(str(obj.get("status")), inv.status)
    if inv.status not in TERMINAL or new in TERMINAL:
        inv.status = new
    inv.number = obj.get("number") or inv.number
    inv.hosted_invoice_url = obj.get("hosted_invoice_url") or inv.hosted_invoice_url
    inv.invoice_pdf = obj.get("invoice_pdf") or inv.invoice_pdf
    if obj.get("total") is not None and obj.get("total") != inv.gross_minor:
        inv.note = f"Stripe-total {obj.get('total')} afviger fra oversigtens {inv.gross_minor} (mindste enhed, {inv.currency})"[:300]
    inv.updated_at = datetime.now(UTC)


def invoice_due(db: OrmSession, today_utc: datetime | None = None) -> int:
    """Worker job: invoice last month for every workspace with a card and no invoice yet."""
    from app.modules.reports.service import local_today, tz_of

    if not configured():
        return 0
    n = 0
    for a in db.scalars(select(BillingAccount).join(Workspace, Workspace.id == BillingAccount.workspace_id)
                        .where(BillingAccount.payment_method_id.is_not(None), Workspace.kind == "business")).all():
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
    if kind.startswith("checkout.session."):
        from app.modules.privat.payments import on_checkout_event

        privat = on_checkout_event(db, kind, obj)  # Dialogbot Privat Opkaldssaldo top-ups (mode=payment)
        if privat is not None:
            return privat
        if kind == "checkout.session.completed":
            from app.modules.privat.subscriptions import on_checkout_completed

            privat = on_checkout_completed(db, obj)  # Dialogbot Privat subscriptions (mode=subscription)
            if privat is not None:
                return privat
    if kind.startswith("customer.subscription."):
        from app.modules.privat.subscriptions import on_subscription_event

        privat = on_subscription_event(db, kind, obj)
        if privat is not None:
            return privat
    if kind in ("invoice.paid", "invoice.payment_failed", "charge.refunded"):
        from app.modules.privat.subscriptions import on_billing_event

        privat = on_billing_event(db, kind, obj)  # Dialogbot Privat customers: receipt / dunning / refund mails
        if privat is not None:
            return privat
    if kind == "checkout.session.completed" and obj.get("mode") == "setup" and obj.get("setup_intent"):
        return "applied" if save_card_from_setup_intent(db, str(obj["setup_intent"])) else "ignored"
    if kind.startswith("invoice.") and obj.get("id"):
        inv = db.scalar(select(Invoice).where(Invoice.stripe_invoice_id == obj["id"]))
        if inv is None:
            return "unmatched"
        was = inv.status
        apply_stripe_invoice(inv, obj)
        if kind == "invoice.payment_failed" and inv.status not in TERMINAL:
            inv.status = "payment_failed"
            _payment_state(db, inv.workspace_id, failed=True)  # the 7 days' grace starts (billing.grace)
            _owner_mail(db, inv.workspace_id, kind="payment_failed", dedupe=f"{obj['id']}:{obj.get('attempt_count') or 1}",
                        amount_minor=int(obj.get("amount_due") or inv.gross_minor or 0),
                        currency=str(obj.get("currency") or "DKK").upper())  # E06 dunning (F-PBQ-08)
        _commission(db, inv, was, kind, obj)
        if inv.status == "paid" and was != "paid":
            _payment_state(db, inv.workspace_id, failed=False)
            from app.modules.sales.offers import on_invoice_paid

            on_invoice_paid(db, inv.workspace_id)  # a company from Dialogbot's own sales becomes a paying customer
        return "applied"
    invoice_id = _refunded_invoice_id(kind, obj) if kind in ("charge.refunded", "credit_note.created") else None
    if invoice_id:
        # Refunds and credit notes reduce what an ambassador earned from the invoice (see ambassadors.service).
        inv = db.scalar(select(Invoice).where(Invoice.stripe_invoice_id == invoice_id))
        if inv is None or not inv.gross_minor:
            return "unmatched"
        from app.modules.ambassadors.service import reverse_for_invoice

        delta, already = _refund_delta(inv, kind, obj)
        if delta <= 0:
            return "applied"  # the same refund seen again (other event type, or a repeat): no second effect
        reverse_for_invoice(db, inv, source_ref=f"{obj.get('id') or kind}:{inv.refunds['applied_minor']}"[:64],
                            fraction=delta / inv.gross_minor, already=already / inv.gross_minor)
        _owner_mail(db, inv.workspace_id, kind="refund", dedupe=f"{inv.stripe_invoice_id}:{inv.refunds['applied_minor']}",
                    amount_minor=delta, currency=str(obj.get("currency") or "DKK").upper())  # refund confirmed
        return "applied"
    return "ignored"


def _payment_state(db, workspace_id, *, failed: bool) -> None:
    """A failed payment makes the subscription unpaid (grace); a paid invoice makes it paid again."""
    from app.modules.billing import grace

    a = account(db, workspace_id, lock=True)
    a.payment_failed_at = datetime.now(UTC) if failed else None
    grace.sync(db, workspace_id)


def _owner_mail(db, workspace_id, *, kind: str, dedupe: str, amount_minor: int, currency: str) -> None:
    """Erhverv's billing mails to the workspace's owners (F-PBQ-08; E06 dunning and refund-confirmed were missing)."""
    from app.models import Membership, User
    from app.modules.billing import customer_mails

    for u in db.scalars(select(User).join(Membership, Membership.user_id == User.id).where(
            Membership.workspace_id == workspace_id, Membership.role == "owner")):
        customer_mails.send(db, kind=kind, to_email=u.email, lang=u.interface_language, audience="erhverv",
                            dedupe=f"{dedupe}:{u.id}", amount_minor=amount_minor, currency=currency,
                            workspace_id=workspace_id)


def _refund_delta(inv: Invoice, kind: str, obj: dict) -> tuple[int, int]:
    """(newly refunded amount, amount refunded before) for an invoice, in minor units.

    charge.refunded carries the CUMULATIVE `amount_refunded` per charge; a refund made through a credit note is also
    reported as credit_note.created for the same money. The invoice's refunded amount is therefore the larger of
    Σ charges and Σ credit notes – never their sum – and only the growth since last time reduces the commission."""
    r = dict(inv.refunds or {})
    charges, notes = dict(r.get("charges") or {}), dict(r.get("credit_notes") or {})
    ref = str(obj.get("id") or kind)
    if kind == "charge.refunded":
        charges[ref] = max(int(charges.get(ref) or 0), int(obj.get("amount_refunded") or 0))
    else:
        notes[ref] = int(obj.get("total") or 0)
    already = int(r.get("applied_minor") or 0)
    total = min(inv.gross_minor, max(sum(charges.values()), sum(notes.values())))
    delta = max(0, total - already)
    inv.refunds = {"charges": charges, "credit_notes": notes, "applied_minor": already + delta}
    return delta, already


def _refunded_invoice_id(kind: str, obj: dict) -> str | None:
    """The Stripe invoice behind a refund or credit note. Since API version 2025-03-31 a charge no longer carries
    `invoice`; it is found through the invoice payment for the charge's payment intent instead."""
    if obj.get("invoice"):
        return str(obj["invoice"])
    if kind != "charge.refunded" or not obj.get("payment_intent"):
        return None
    try:
        rows = request("GET", "/invoice_payments", {
            "payment": {"type": "payment_intent", "payment_intent": str(obj["payment_intent"])}, "limit": 1}).get("data") or []
    except Exception:
        log.warning("stripe: could not look up the invoice for refunded charge %s", obj.get("id"), exc_info=True)
        return None
    return str(rows[0]["invoice"]) if rows and rows[0].get("invoice") else None


def _commission(db: OrmSession, inv: Invoice, was: str, kind: str, obj: dict) -> None:
    from app.modules.ambassadors.service import accrue_for_invoice, reverse_for_invoice

    if inv.status == "paid" and was != "paid":
        accrue_for_invoice(db, inv)
    elif inv.status == "void" and was == "paid":
        already = min(1.0, int((inv.refunds or {}).get("applied_minor") or 0) / inv.gross_minor) if inv.gross_minor else 0.0
        reverse_for_invoice(db, inv, source_ref=f"void:{obj.get('id')}", fraction=1.0 - already, already=already)


def invoice_out(i: Invoice) -> dict:
    return {"id": str(i.id), "month": i.month.strftime("%Y-%m"), "status": i.status, "number": i.number,
            "currency": i.currency, "tax_source": i.tax_source, "net_minor": i.net_minor, "tax_minor": i.tax_minor, "gross_minor": i.gross_minor,
            "hosted_invoice_url": i.hosted_invoice_url, "invoice_pdf": i.invoice_pdf, "note": i.note,
            "lines": i.lines or [],  # the frozen statement lines of the invoiced month (package usage included)
            "refunds": refunds_out(i),  # B05: refunds / credit notes Stripe reported for this invoice
            "created_at": i.created_at.isoformat()}


def refunds_out(i: Invoice) -> dict:
    from app.modules.billing import disputes

    return disputes.refunds_out(i)

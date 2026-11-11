"""Top up the «Opkaldssaldo»: Stripe Checkout (mode=payment) for 50, 100 or 200 kr. incl. 25 % moms (F-PDEC-01).

The amount is added ONLY by the signed Stripe webhook (checkout.session.completed / async_payment_succeeded, paid),
with source_ref stripe:<checkout_session_id>: the webhook router records WebhookEvent(provider='stripe', event_id) in the
same transaction, so a resent event changes nothing, and a different event for the same session cannot add twice.
The webhook adds what the session was created for (metadata amount_minor, one of the top-ups of the currency) and only
when Stripe says at least that much was paid (F-PBQ-03): an underpaid session adds nothing and is logged.

Markets (privat/market.py, docs/markets.md): the top-ups are in the balance's currency (ledger.currency: the
subscription's, else DKK; before any Checkout the visitor's language decides and the account keeps it), at
markets.PRIVAT_TOPUPS, with the inclusive VAT rate of the language's country.
"""
from __future__ import annotations

import uuid

from sqlalchemy.orm import Session as OrmSession

from app.config import get_settings
from app.core.errors import ValidationFailed
from app.models import PrivateProfile, PrivateSubscription, Workspace
from app.modules.billing import markets, prices
from app.modules.privat import branding, ledger, market

KIND = "privat_topup"
# Credit packs (10 credits) opened at Stripe before 2026-11-11 and paid after: added as what they cost, in øre.
LEGACY_KIND = "privat_credits"
LEGACY_PACK = {"DKK": 2900, "SEK": 4500, "NOK": 4500, "EUR": 399}


def _description(amount: int, currency: str, locale: str | None, rate_bp: int | None) -> str:
    if currency == "DKK" and rate_bp == prices.TAX_BASIS_POINTS and market.norm_locale(locale) == "da":
        vat = amount - amount * 10000 // (10000 + rate_bp)
        return (f"Opkaldssaldo · {markets.fmt(amount, currency)} inkl. 25 % moms ({markets.fmt(amount - vat, currency)} + "
                f"{markets.fmt(vat, currency)} moms)")
    return "Opkaldssaldo · " + markets.fmt(amount, currency) + market.vat_text(rate_bp, locale)


def checkout(db: OrmSession, ctx, amount_minor: int | None = None, locale: str | None = None) -> str:
    s = get_settings()
    base = s.frontend_base_url.rstrip("/")
    row = db.get(PrivateSubscription, ctx.ws_id)
    currency = market.currency(row.currency if row else None, locale)
    if row is not None and row.currency != currency:
        row.currency = currency  # a customer keeps the currency of its first Checkout (market.py)
        ledger.adopt_currency(db, ctx.ws_id, currency)
    allowed = markets.PRIVAT_TOPUPS[currency]
    amount = allowed[0] if amount_minor is None else int(amount_minor)
    if amount not in allowed:
        raise ValidationFailed("Vælg et af beløbene", code="invalid_topup",
                               field_errors=[{"field": "amount_minor", "allowed": list(allowed)}])
    meta = {"workspace_id": str(ctx.ws_id), "kind": KIND, "amount_minor": str(amount), "currency": currency}
    line = {"quantity": 1, "price_data": {
        "currency": currency.lower(), "unit_amount": amount, "tax_behavior": "inclusive",
        "product_data": {"name": "Opkaldssaldo – Dialogbot Privat" if market.norm_locale(locale) == "da"
                         else "Call balance – Dialogbot Privat",
                         "description": _description(amount, currency, locale, market.text_rate(locale))}}}
    payload = {
        "mode": "payment", "line_items": [line], "locale": market.stripe_locale(locale), "customer_email": ctx.user.email,
        # No discount codes on top-ups (F-PBQ-03): the Privat codes are made for the plans (no applies_to), and a
        # top-up paid below its amount would be ignored by the webhook – paid, but nothing added.
        "client_reference_id": str(ctx.ws_id), "metadata": meta, "payment_intent_data": {"metadata": meta},
        "success_url": f"{base}/privat/konto?betaling=ok", "cancel_url": f"{base}/privat/konto?betaling=annulleret"}
    market.apply_tax(payload, line, locale)
    sess = branding.create_checkout_session(payload)
    return sess["url"]


def on_checkout_event(db: OrmSession, kind: str, obj: dict) -> str | None:
    """Add a paid top-up to the Opkaldssaldo. None = not a Dialogbot Privat top-up."""
    meta = obj.get("metadata") or {}
    if obj.get("mode") != "payment" or meta.get("kind") not in (KIND, LEGACY_KIND):
        return None
    if kind not in ("checkout.session.completed", "checkout.session.async_payment_succeeded"):
        return "ignored"
    if obj.get("payment_status") != "paid":
        return "ignored"  # e.g. a bank transfer still pending: async_payment_succeeded adds later
    try:
        ws_id = uuid.UUID(str(meta.get("workspace_id")))
    except ValueError:
        return "unmatched"
    ws = db.get(Workspace, ws_id)
    if ws is None or ws.kind != "personal" or db.get(PrivateProfile, ws_id) is None:
        return "unmatched"
    currency = str(obj.get("currency") or meta.get("currency") or "DKK").upper()
    if currency not in markets.CURRENCIES:
        return "ignored"
    if meta.get("kind") == LEGACY_KIND:  # a credit pack opened before the switch: what was paid for it, in øre
        expected, allowed = LEGACY_PACK.get(currency, 0), (LEGACY_PACK.get(currency),)
    else:
        try:
            expected = int(str(meta.get("amount_minor")))
        except ValueError:
            return "ignored"
        allowed = markets.PRIVAT_TOPUPS[currency]
    paid = obj.get("amount_total")
    if expected not in allowed or currency != ledger.currency(db, ws_id) or paid is None or int(paid) < expected:
        # Paid, but not the top-up it was opened for (less than its amount, should be impossible without codes, or
        # another currency than the balance's): nothing added, and a person must refund or add by hand – never
        # silently (F-PBQ-03).
        import structlog

        structlog.get_logger("dialogbot.privat.payments").error(
            "privat.topup_underpaid", session=str(obj.get("id") or ""), workspace_id=str(ws_id),
            amount_total=paid, expected=expected, currency=currency, balance_currency=ledger.currency(db, ws_id))
        return "ignored"
    sid = str(obj.get("id") or "")
    if not sid:
        return "ignored"
    added = ledger.add(db, ws_id, kind="purchase", amount=expected, source_ref=f"stripe:{sid}", cur=currency,
                       text=f"Opkaldssaldo fyldt op · {markets.fmt(expected, currency)} inkl. moms")
    return "applied" if added else "ignored"

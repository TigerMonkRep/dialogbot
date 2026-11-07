"""Credit packs: Stripe Checkout (mode=payment), 10 credits for 29 kr. incl. 25 % moms (2320 + 580 øre).

The credits are granted ONLY by the signed Stripe webhook (checkout.session.completed / async_payment_succeeded, paid),
with source_ref stripe:<checkout_session_id>: the webhook router records WebhookEvent(provider='stripe', event_id) in the
same transaction, so a resent event changes nothing, and a different event for the same session cannot grant twice.

Markets (privat/market.py, docs/markets.md): the pack is sold in the customer's currency (its subscription's, else the
visitor's language's) at markets.PRIVAT_CREDIT_PACK, with the inclusive VAT rate of the language's country.
"""
from __future__ import annotations

import uuid

from sqlalchemy.orm import Session as OrmSession

from app.config import get_settings
from app.models import PrivateProfile, PrivateSubscription, Workspace
from app.modules.billing import markets, prices
from app.modules.privat import branding, ledger, market

KIND = "privat_credits"


def _description(amount: int, currency: str, locale: str | None, rate_bp: int | None) -> str:
    if currency == "DKK" and rate_bp == prices.TAX_BASIS_POINTS and market.norm_locale(locale) == "da" \
            and amount == prices.PRIVAT_CREDIT_PACK_GROSS_MINOR:
        net = prices.PRIVAT_CREDIT_PACK_NET_MINOR
        return (f"{markets.fmt(amount, currency)} inkl. 25 % moms ({markets.fmt(net, currency)} + "
                f"{markets.fmt(amount - net, currency)} moms)")
    return markets.fmt(amount, currency) + market.vat_text(rate_bp, locale)


def checkout(db: OrmSession, ctx, locale: str | None = None) -> str:
    s = get_settings()
    base = s.frontend_base_url.rstrip("/")
    row = db.get(PrivateSubscription, ctx.ws_id)
    currency = market.currency(row.currency if row else None, locale)
    amount = markets.PRIVAT_CREDIT_PACK[currency]
    meta = {"workspace_id": str(ctx.ws_id), "kind": KIND, "credits": str(prices.PRIVAT_CREDIT_PACK_CREDITS),
            "currency": currency}
    if currency == "DKK" and s.privat_stripe_price_id:  # the fixed Stripe price is a DKK price
        line = {"price": s.privat_stripe_price_id, "quantity": 1}
    else:
        line = {"quantity": 1, "price_data": {
            "currency": currency.lower(), "unit_amount": amount, "tax_behavior": "inclusive",
            "product_data": {"name": f"{prices.PRIVAT_CREDIT_PACK_CREDITS} credits – Dialogbot Privat",
                             "description": _description(amount, currency, locale, market.text_rate(locale))}}}
    payload = {
        "mode": "payment", "line_items": [line], "locale": market.stripe_locale(locale), "customer_email": ctx.user.email,
        "allow_promotion_codes": True,
        "client_reference_id": str(ctx.ws_id), "metadata": meta, "payment_intent_data": {"metadata": meta},
        "success_url": f"{base}/privat/konto?betaling=ok", "cancel_url": f"{base}/privat/konto?betaling=annulleret"}
    market.apply_tax(payload, line, locale)
    sess = branding.create_checkout_session(payload)
    return sess["url"]


def on_checkout_event(db: OrmSession, kind: str, obj: dict) -> str | None:
    """Grant +10 for a paid credit-pack session. None = not a Dialogbot Privat event."""
    meta = obj.get("metadata") or {}
    if obj.get("mode") != "payment" or meta.get("kind") != KIND:
        return None
    if kind not in ("checkout.session.completed", "checkout.session.async_payment_succeeded"):
        return "ignored"
    if obj.get("payment_status") != "paid":
        return "ignored"  # e.g. a bank transfer still pending: async_payment_succeeded grants later
    try:
        ws_id = uuid.UUID(str(meta.get("workspace_id")))
    except ValueError:
        return "unmatched"
    ws = db.get(Workspace, ws_id)
    if ws is None or ws.kind != "personal" or db.get(PrivateProfile, ws_id) is None:
        return "unmatched"
    currency = str(obj.get("currency") or meta.get("currency") or "DKK").upper()
    expected = markets.PRIVAT_CREDIT_PACK.get(currency)
    if expected is None:
        return "ignored"
    if obj.get("amount_total") is not None and int(obj["amount_total"]) < expected:
        return "ignored"
    sid = str(obj.get("id") or "")
    if not sid:
        return "ignored"
    added = ledger.add(db, ws_id, kind="purchase", amount=prices.PRIVAT_CREDIT_PACK_CREDITS,
                       source_ref=f"stripe:{sid}",
                       text=f"Købt {prices.PRIVAT_CREDIT_PACK_CREDITS} credits · {markets.fmt(expected, currency)} inkl. moms")
    return "applied" if added else "ignored"

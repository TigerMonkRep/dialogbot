"""Credit packs: Stripe Checkout (mode=payment), 10 credits for 29 kr. incl. 25 % moms (2320 + 580 øre).

The credits are granted ONLY by the signed Stripe webhook (checkout.session.completed / async_payment_succeeded, paid),
with source_ref stripe:<checkout_session_id>: the webhook router records WebhookEvent(provider='stripe', event_id) in the
same transaction, so a resent event changes nothing, and a different event for the same session cannot grant twice.
"""
from __future__ import annotations

import uuid

from sqlalchemy.orm import Session as OrmSession

from app.config import get_settings
from app.models import PrivateProfile, Workspace
from app.modules.billing import prices
from app.modules.privat import branding, ledger

KIND = "privat_credits"


def checkout(db: OrmSession, ctx) -> str:
    s = get_settings()
    base = s.frontend_base_url.rstrip("/")
    meta = {"workspace_id": str(ctx.ws_id), "kind": KIND, "credits": str(prices.PRIVAT_CREDIT_PACK_CREDITS)}
    if s.privat_stripe_price_id:
        line = {"price": s.privat_stripe_price_id, "quantity": 1}
    else:
        line = {"quantity": 1, "price_data": {
            "currency": "dkk", "unit_amount": prices.PRIVAT_CREDIT_PACK_GROSS_MINOR, "tax_behavior": "inclusive",
            "product_data": {"name": f"{prices.PRIVAT_CREDIT_PACK_CREDITS} credits – Dialogbot Privat",
                             "description": "29 kr. inkl. 25 % moms (23,20 kr. + 5,80 kr. moms)"}}}
    sess = branding.create_checkout_session({
        "mode": "payment", "line_items": [line], "locale": "da", "customer_email": ctx.user.email, "allow_promotion_codes": True,
        "client_reference_id": str(ctx.ws_id), "metadata": meta, "payment_intent_data": {"metadata": meta},
        "success_url": f"{base}/privat/konto?betaling=ok", "cancel_url": f"{base}/privat/konto?betaling=annulleret"})
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
    if obj.get("amount_total") is not None and int(obj["amount_total"]) < prices.PRIVAT_CREDIT_PACK_GROSS_MINOR:
        return "ignored"
    sid = str(obj.get("id") or "")
    if not sid:
        return "ignored"
    added = ledger.add(db, ws_id, kind="purchase", amount=prices.PRIVAT_CREDIT_PACK_CREDITS,
                       source_ref=f"stripe:{sid}",
                       text=f"Købt {prices.PRIVAT_CREDIT_PACK_CREDITS} credits · 29 kr. inkl. moms")
    return "applied" if added else "ignored"

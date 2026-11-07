"""Dialogbot Privat subscriptions: the 14-day trial, Basis / Plus / Familie, Stripe Checkout and the Billing Portal.

Rules (docs/pricing.md, docs/privat-api.md):
- Every private account starts a 14-day trial with Plus rights, no card. Accounts from before subscriptions existed
  get their trial row lazily on first read, counted from that moment.
- Entitled (trial, active or past_due; canceled until the paid period ends): lists and reminders are unlimited
  (paid_by 'plan'), calls draw on the plan's monthly quota (calendar month, Europe/Copenhagen; a call nobody answers
  or that fails does not count), Shop apps with `included_in` can be switched on. Not entitled: the old free quota
  (10 tasks a month) and credits apply, unchanged.
- The ONLY writer of active/past_due/canceled is the signed Stripe webhook (upsert_from_stripe_subscription) or the
  return from Checkout (sync_from_session reads the session from Stripe, never trusts the browser).
"""
from __future__ import annotations

import math
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as OrmSession

from app.config import get_settings
from app.core.errors import NotFound, NotImplementedYet, ValidationFailed
from app.models import PrivateCall, PrivateProfile, PrivateSubscription, Workspace
from app.modules.billing import markets, prices
from app.modules.billing import stripe as stripe_api
from app.modules.privat import branding, market, rules

KIND = "privat_subscription"
PLANS: dict[str, dict] = {p["key"]: dict(p) for p in prices.PRIVAT_PLANS}
INTERVALS = ("month", "year")
TRIAL_PLAN = "plus"
ENTITLED_STATUSES = ("trial", "active", "past_due")
# Stripe subscription status → ours. Stripe's trialing is our "trial": the 14 days run on the subscription the card
# was given for (Checkout, trial_period_days), and Stripe flips it to active by itself when they are over.
STRIPE_STATUS = {"trialing": "trial", "active": "active", "past_due": "past_due", "canceled": "canceled",
                 "unpaid": "canceled", "incomplete_expired": "canceled", "incomplete": "past_due", "paused": "past_due"}
FEATURES = {
    "basis": ("Ubegrænsede lister og påmindelser", "3 opkald om måneden", "Delte lister og ønskelister"),
    "plus": ("Ubegrænsede lister og påmindelser", "10 opkald om måneden", "Alle apps i Butikken",
             "Delte lister og ønskelister"),
    "familie": ("Alt i Plus", "25 opkald om måneden", "Op til 5 personer", "Alle apps i Butikken"),
}


def plan_out(key: str, currency: str = "DKK") -> dict:
    """One plan with its amounts (incl. VAT, minor units) in `currency` (markets.PRIVAT)."""
    p = PLANS[key]
    a = markets.privat_plan(currency, key)
    return {"key": p["key"], "name": p["name"], "currency": currency, "monthly_minor": a["monthly"],
            "yearly_monthly_minor": a["yearly_monthly"], "yearly_total_minor": a["yearly_total"],
            "calls": p["calls"], "people": p["people"], "apps_included": p["apps_included"],
            "recommended": p["recommended"], "features": list(FEATURES[key])}


def plans_out(currency: str = "DKK") -> list[dict]:
    return [plan_out(k, currency) for k in PLANS]


# --------------------------------------------------------------------------- the row

def get(db: OrmSession, ws_id: uuid.UUID, *, lock: bool = False) -> PrivateSubscription | None:
    q = select(PrivateSubscription).where(PrivateSubscription.workspace_id == ws_id)
    return db.scalar(q.with_for_update() if lock else q)


def start_free(db: OrmSession, ws_id: uuid.UUID) -> PrivateSubscription:
    """The account's row without any rights (status none): the free tier sees lists shared with it and nothing
    else. The 14-day trial starts at Stripe Checkout, with a card (checkout()). Idempotent."""
    row = get(db, ws_id)
    if row is not None:
        return row
    now = rules.now()
    row = PrivateSubscription(workspace_id=ws_id, plan=TRIAL_PLAN, status="none", created_at=now, updated_at=now)
    try:
        with db.begin_nested():
            db.add(row)
    except IntegrityError:  # a concurrent request created it
        return get(db, ws_id)
    return row


def start_trial(db: OrmSession, ws_id: uuid.UUID) -> PrivateSubscription:
    """Old name: accounts no longer get a card-less trial; this is the free row now."""
    return start_free(db, ws_id)


def ensure(db: OrmSession, ws_id: uuid.UUID) -> PrivateSubscription:
    return get(db, ws_id) or start_free(db, ws_id)


def trial_available(row: PrivateSubscription) -> bool:
    """One trial per account: never had one (local or at Stripe) and never a subscription."""
    return row.trial_ends_at is None and row.stripe_subscription_id is None


# --------------------------------------------------------------------------- entitlements

def _month_bounds(at: datetime | None = None) -> tuple[datetime, datetime]:
    first = rules.local(at).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    nxt = first.replace(year=first.year + (first.month == 12), month=first.month % 12 + 1)
    return first.astimezone(UTC), nxt.astimezone(UTC)


def calls_used(db: OrmSession, ws_id: uuid.UUID, at: datetime | None = None) -> int:
    """Approved plan calls this Copenhagen month that were not lost to no answer / failure."""
    start, end = _month_bounds(at)
    return int(db.scalar(select(func.count()).select_from(PrivateCall).where(
        PrivateCall.workspace_id == ws_id, PrivateCall.paid_via == "plan",
        PrivateCall.approved_at >= start, PrivateCall.approved_at < end,
        PrivateCall.result.is_(None) | PrivateCall.result.not_in(("no_answer", "failed")))) or 0)


def plan_call_index(db: OrmSession, c: PrivateCall) -> int:
    """"Opkald N af M": this call's number among the month's counting plan calls (by approval order)."""
    start, end = _month_bounds(c.approved_at)
    return int(db.scalar(select(func.count()).select_from(PrivateCall).where(
        PrivateCall.workspace_id == c.workspace_id, PrivateCall.paid_via == "plan",
        PrivateCall.approved_at >= start, PrivateCall.approved_at < end, PrivateCall.approved_at <= c.approved_at,
        PrivateCall.id != c.id,
        PrivateCall.result.is_(None) | PrivateCall.result.not_in(("no_answer", "failed")))) or 0) + 1


def _state(row: PrivateSubscription | None, now: datetime) -> tuple[str, str, bool]:
    """(status, plan, entitled) as the contract defines them, from the stored row."""
    if row is None or row.status == "none":
        return "none", "none", False
    if row.status == "trial":
        if row.trial_ends_at is not None and row.trial_ends_at > now:
            return "trial", row.plan if row.plan in PLANS else TRIAL_PLAN, True
        return "expired", "none", False
    if row.status in ("active", "past_due"):
        return row.status, row.plan, True
    # canceled: the paid period still runs out
    if row.current_period_end is not None and row.current_period_end > now:
        return "canceled", row.plan, True
    return "canceled", "none", False


def entitlements(db: OrmSession, ws_id: uuid.UUID) -> dict:
    """The Subscription object of docs/privat-api.md (without `plans`). Creates the trial row for old accounts."""
    row = ensure(db, ws_id)
    now = rules.now()
    status, plan, entitled = _state(row, now)
    p = PLANS.get(plan)
    quota = p["calls"] if (entitled and p) else 0
    used = calls_used(db, ws_id) if entitled else 0
    days_left = 0
    if status == "trial":
        days_left = max(0, math.ceil((row.trial_ends_at - now).total_seconds() / 86400))
    return {
        "plan": plan, "status": status, "interval": row.interval if entitled else None,
        "trial_ends_at": row.trial_ends_at.isoformat() if row.trial_ends_at else None, "trial_days_left": days_left,
        "current_period_end": row.current_period_end.isoformat() if row.current_period_end else None,
        "cancel_at_period_end": bool(row.cancel_at_period_end) if entitled else False,
        "entitled": entitled, "calls_quota": quota, "calls_used": used, "calls_left": max(0, quota - used),
        "people_limit": p["people"] if (entitled and p) else 1,
        "apps_included": bool(p["apps_included"]) if (entitled and p) else False,
    }


def display_currency(row: PrivateSubscription | None, asked: str | None = None) -> str:
    """The row's currency if set (a customer keeps theirs), else the one asked for (?currency=), else DKK."""
    if row is not None and row.currency in markets.CURRENCIES:
        return row.currency
    return asked if asked in markets.CURRENCIES else "DKK"


def subscription_out(db: OrmSession, ws_id: uuid.UUID, currency: str | None = None) -> dict:
    ent = entitlements(db, ws_id)
    cur = display_currency(get(db, ws_id), currency)
    return ent | {"currency": cur, "plans": plans_out(cur)}


def plan_label(ent: dict) -> str:
    """"Plus" – also during the trial, which carries Plus rights."""
    return PLANS[ent["plan"]]["name"] if ent.get("plan") in PLANS else PLANS[TRIAL_PLAN]["name"]


def covers(ent: dict, plans: tuple[str, ...]) -> bool:
    """Whether the current rights include one of `plans` (the trial counts as Plus)."""
    return bool(ent.get("entitled")) and ent.get("plan") in plans


# --------------------------------------------------------------------------- Stripe Checkout and portal

def price_id(plan: str, interval: str) -> str | None:
    return getattr(get_settings(), f"privat_stripe_price_{plan}_{interval}", None) or None


def _line_text(p: dict, interval: str, currency: str, locale: str, rate_bp: int | None) -> str:
    """The product description on the Checkout page, in the visitor's language (Danish for da, English otherwise)."""
    a = markets.privat_plan(currency, p["key"])
    amount = a["monthly"] if interval == "month" else a["yearly_total"]
    if market.norm_locale(locale) == "da":
        per = "pr. måned" if interval == "month" else f"pr. år ({markets.fmt(a['yearly_monthly'], currency)}/md.)"
        return f"{markets.fmt(amount, currency)} {per}{market.vat_text(rate_bp, locale)} · {p['calls']} opkald om måneden"
    per = "per month" if interval == "month" else f"per year ({markets.fmt(a['yearly_monthly'], currency)}/month)"
    return f"{markets.fmt(amount, currency)} {per}{market.vat_text(rate_bp, locale)} · {p['calls']} calls a month"


def checkout(db: OrmSession, ctx, *, plan: str, interval: str, code: str | None = None, locale: str | None = None) -> str:
    """A Stripe Checkout page (mode=subscription). The subscription itself arrives with the webhook / sync.
    `code`: a discount code the customer typed (or ?kode=) – applied on the Stripe page; without one the page shows
    Stripe's own field for a code. `locale` (da, en, de, es, fr, it, no, sv): the page's language and, for a customer
    without a currency yet, the currency (privat/market.py); the row keeps that currency from now on."""
    from app.modules.billing import discounts

    if plan not in PLANS:
        raise ValidationFailed("Vælg Basis, Plus eller Familie", field_errors=[{"field": "plan"}])
    if interval not in INTERVALS:
        raise ValidationFailed("Vælg månedlig eller årlig betaling", field_errors=[{"field": "interval"}])
    s = get_settings()
    base = s.frontend_base_url.rstrip("/")
    p = PLANS[plan]
    row = ensure(db, ctx.ws_id)
    currency = market.currency(row.currency, locale)
    if row.currency != currency:
        row.currency = currency  # a customer keeps the currency of its first Checkout
    meta = {"kind": KIND, "workspace_id": str(ctx.ws_id), "plan": plan, "interval": interval, "currency": currency}
    if currency == "DKK" and (pid := price_id(plan, interval)):  # the fixed Stripe prices are DKK prices
        line = {"price": pid, "quantity": 1}
    else:
        a = markets.privat_plan(currency, plan)
        amount = a["monthly"] if interval == "month" else a["yearly_total"]
        line = {"quantity": 1, "price_data": {
            "currency": currency.lower(), "unit_amount": amount, "tax_behavior": "inclusive",
            "recurring": {"interval": interval},
            "product_data": {"name": f"Dialogbot Privat – {p['name']}",
                             "description": _line_text(p, interval, currency, locale, market.text_rate(locale))}}}
    sub_data: dict = {"metadata": meta}
    if trial_available(row):
        # «Prøv gratis i 14 dage»: the card is given now, nothing is charged until the trial is over, and Stripe
        # turns the subscription active by itself. One trial per account.
        sub_data["trial_period_days"] = prices.PRIVAT_TRIAL_DAYS
    elif row.status == "trial" and row.trial_ends_at is not None and row.stripe_subscription_id is None \
            and row.trial_ends_at - rules.now() > timedelta(hours=48):
        sub_data["trial_end"] = int(row.trial_ends_at.timestamp())  # an old card-less trial keeps its remaining days
    payload: dict = {
        "mode": "subscription", "line_items": [line], "locale": market.stripe_locale(locale),
        "client_reference_id": str(ctx.ws_id),
        "metadata": meta, "subscription_data": sub_data, "payment_method_collection": "always",
        # Name, address and phone are collected by Stripe on the same page (they are never stored by us).
        "billing_address_collection": "required", "phone_number_collection": {"enabled": True},
        "success_url": f"{base}/privat/konto?abonnement=ok&session_id={{CHECKOUT_SESSION_ID}}",
        "cancel_url": f"{base}/privat/konto?abonnement=annulleret"}
    if row.stripe_customer_id:
        payload["customer"] = row.stripe_customer_id
    else:
        payload["customer_email"] = ctx.user.email
    market.apply_tax(payload, line, locale)
    applied = discounts.privat_checkout_discounts(db, code)
    if applied:
        payload["discounts"] = applied  # Stripe allows either a fixed discount or its code field, not both
    else:
        payload["allow_promotion_codes"] = True
    sess = branding.create_checkout_session(payload)
    return sess["url"]


def portal(db: OrmSession, ctx) -> str:
    """Stripe Billing Portal (change plan, cancel, update card). 501 not_configured without Stripe or a customer."""
    row = ensure(db, ctx.ws_id)
    if not stripe_api.configured():
        raise NotImplementedYet("Abonnementer kan ikke administreres endnu (Stripe er ikke sat op)",
                                code="not_configured")
    if not row.stripe_customer_id:
        raise NotImplementedYet("Du har ikke et abonnement at administrere endnu – vælg en plan først",
                                code="not_configured")
    base = get_settings().frontend_base_url.rstrip("/")
    sess = stripe_api.request("POST", "/billing_portal/sessions",
                              {"customer": row.stripe_customer_id, "return_url": f"{base}/privat/konto"})
    return sess["url"]


# --------------------------------------------------------------------------- from Stripe

def _ts(v) -> datetime | None:
    try:
        return datetime.fromtimestamp(int(v), UTC) if v is not None else None
    except (TypeError, ValueError, OverflowError):
        return None


def _period_end(obj: dict) -> datetime | None:
    # Stripe API ≥ 2025-03-31 moved current_period_end from the subscription to each item.
    if obj.get("current_period_end") is not None:
        return _ts(obj["current_period_end"])
    items = ((obj.get("items") or {}).get("data") or [])
    return _ts(items[0].get("current_period_end")) if items else None


def _interval_of(obj: dict) -> str | None:
    items = ((obj.get("items") or {}).get("data") or [])
    rec = ((items[0].get("price") or {}).get("recurring") or {}) if items else {}
    return rec.get("interval") if rec.get("interval") in INTERVALS else None


def upsert_from_stripe_subscription(db: OrmSession, obj: dict, *, session_meta: dict | None = None) -> str:
    """Mirror one Stripe subscription object into private_subscriptions. Idempotent (same object → same row).
    Returns applied | ignored | unmatched."""
    meta = obj.get("metadata") or {}
    if meta.get("kind") != KIND:
        meta = session_meta or {}
    if meta.get("kind") != KIND:
        return "ignored"
    try:
        ws_id = uuid.UUID(str(meta.get("workspace_id")))
    except ValueError:
        return "unmatched"
    ws = db.get(Workspace, ws_id)
    if ws is None or ws.kind != "personal" or db.get(PrivateProfile, ws_id) is None:
        return "unmatched"
    sid = str(obj.get("id") or "")
    if not sid:
        return "ignored"
    status = STRIPE_STATUS.get(str(obj.get("status") or ""))
    if status is None:
        return "ignored"
    plan = meta.get("plan") if meta.get("plan") in PLANS else None
    interval = meta.get("interval") if meta.get("interval") in INTERVALS else _interval_of(obj)
    row = get(db, ws_id, lock=True) or start_free(db, ws_id)
    if row.stripe_subscription_id and row.stripe_subscription_id != sid and status == "canceled":
        return "ignored"  # an older subscription ending must not touch the one that replaced it
    if plan is None and row.stripe_subscription_id != sid:
        return "unmatched"  # a subscription we cannot place on a plan
    row.stripe_subscription_id = sid
    row.status = status
    if status == "trial":
        row.trial_ends_at = _ts(obj.get("trial_end")) or row.trial_ends_at or (rules.now() + timedelta(days=prices.PRIVAT_TRIAL_DAYS))
    row.plan = plan or row.plan
    row.interval = interval or row.interval
    cur = str(obj.get("currency") or meta.get("currency") or "").upper()
    if cur in markets.CURRENCIES:
        row.currency = cur  # what Stripe actually charges in
    cust = obj.get("customer")
    if isinstance(cust, dict):
        cust = cust.get("id")
    if cust:
        row.stripe_customer_id = str(cust)[:100]
    row.current_period_end = _period_end(obj) or row.current_period_end
    row.cancel_at_period_end = bool(obj.get("cancel_at_period_end"))
    row.updated_at = rules.now()
    db.flush()
    if status in ENTITLED_STATUSES:
        from app.modules.privat import addons, service

        addons.enable_defaults(db, ws_id)  # the plan's default add-ons («Ring for mig» …) come on with the rights
        service.activate_drafts_with_plan(db, ws_id)  # what waited for the plan (the funnel's lists …) goes live
    return "applied"


def on_checkout_completed(db: OrmSession, obj: dict) -> str | None:
    """checkout.session.completed with mode=subscription for one of ours: fetch the subscription and mirror it.
    None = not a Dialogbot Privat subscription session."""
    meta = obj.get("metadata") or {}
    if obj.get("mode") != "subscription" or meta.get("kind") != KIND:
        return None
    sub_id = obj.get("subscription")
    if isinstance(sub_id, dict):
        sub_id = sub_id.get("id")
    if not sub_id:
        return "ignored"
    sub = stripe_api.request("GET", f"/subscriptions/{sub_id}")
    result = upsert_from_stripe_subscription(db, sub, session_meta=meta)
    if result == "applied":
        from app.modules.billing import discounts

        try:
            discounts.record_privat_redemption(db, uuid.UUID(str(meta.get("workspace_id"))), obj)
        except ValueError:
            pass
    return result


def on_subscription_event(db: OrmSession, kind: str, obj: dict) -> str | None:
    """customer.subscription.created|updated|deleted. None = not ours."""
    if not kind.startswith("customer.subscription."):
        return None
    if (obj.get("metadata") or {}).get("kind") != KIND:
        return None
    return upsert_from_stripe_subscription(db, obj)


def sync_from_session(db: OrmSession, ctx, session_id: str) -> str:
    """Back from Checkout (?session_id=): read the session FROM STRIPE and mirror its subscription, so the account
    page is right even before the webhook arrives. The session must belong to the caller's own workspace."""
    session_id = (session_id or "").strip()[:200]
    if not session_id.startswith("cs_"):
        raise ValidationFailed("Ugyldig Stripe-session", field_errors=[{"field": "session_id"}])
    sess = stripe_api.request("GET", f"/checkout/sessions/{session_id}")
    meta = sess.get("metadata") or {}
    if meta.get("kind") != KIND or meta.get("workspace_id") != str(ctx.ws_id):
        raise NotFound("Betalingen hører ikke til din konto", code="session_not_yours")
    return on_checkout_completed(db, sess) or "ignored"

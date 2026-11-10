"""QA billing-qa · X08 – Dialogbot Privat: Basis/Plus/Familie, month↔year, trial, cancellation in the trial, trial
expiry, failed renewal, Stripe Tax / moms. Stripe is a local fake (no network); webhooks are signed locally.

Independent price table (incl. 25 % moms, øre) – the DKK catalogue the UI shows (web/src/lib/prices.json):
  Basis   49 kr./md · 39 kr./md årligt = 468 kr./år
  Plus    99 kr./md · 79 kr./md årligt = 948 kr./år
  Familie 169 kr./md · 135 kr./md årligt = 1.620 kr./år
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
from datetime import timedelta
from pathlib import Path

import pytest

from app.config import get_settings
from app.models import PrivateSubscription
from app.modules.billing import stripe as stripe_api
from tests.privat_fixtures import WED_10

EXPECTED_DKK = {"basis": (4900, 3900, 46800, 3), "plus": (9900, 7900, 94800, 10), "familie": (16900, 13500, 162000, 25)}
ROOT = Path(__file__).resolve().parents[2]


def _event(client, event: dict, secret="whsec_qa_bill") -> dict:
    body = json.dumps(event).encode()
    ts = int(time.time())
    sig = hmac.new(secret.encode(), f"{ts}.".encode() + body, hashlib.sha256).hexdigest()
    r = client.post("/api/v1/webhooks/stripe", content=body, headers={"stripe-signature": f"t={ts},v1={sig}"})
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture
def stripe_env(monkeypatch):
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_qa_bill")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_qa_bill")
    get_settings.cache_clear()
    sent: list = []

    def fake(m, p, d=None, **k):
        sent.append((m, p, d))
        if p == "/tax_rates":
            return {"data": []} if m == "GET" else {"id": f"txr_{d['metadata']['dialogbot']}"}
        if p.startswith("/billing_portal"):
            return {"url": "https://billing.stripe.com/p/session/qa"}
        return {"id": "cs_qa_1", "url": "https://checkout.stripe.com/c/pay/cs_qa_1"}

    monkeypatch.setattr(stripe_api, "request", fake)
    yield sent
    get_settings.cache_clear()


def _sub(ws, *, sid="sub_qa", status="active", plan="plus", interval="month", period_end=None, cancel=False,
         trial_end=None, price_id=None, item_interval=None, created=None, extra=None) -> dict:
    end = int((period_end or (WED_10 + timedelta(days=30))).timestamp())
    price = {"recurring": {"interval": item_interval or interval}}
    if price_id:
        price["id"] = price_id
    obj = {"id": sid, "object": "subscription", "status": status, "customer": "cus_qa", "currency": "dkk",
           "cancel_at_period_end": cancel, "items": {"data": [{"current_period_end": end, "price": price}]},
           "metadata": {"kind": "privat_subscription", "workspace_id": str(ws), "plan": plan, "interval": interval,
                        "currency": "DKK"}}
    if trial_end is not None:
        obj["trial_end"] = int(trial_end.timestamp())
    if created is not None:
        obj["created"] = created
    return obj | (extra or {})


def _ev(eid, kind, obj, created=None):
    e = {"id": eid, "type": f"customer.subscription.{kind}", "data": {"object": obj}}
    if created is not None:
        e["created"] = created
    return e


# --------------------------------------------------------------------------- catalogue: API = UI = independent table

def test_x08_plan_amounts_api_ui_and_independent_table_agree(api, pv):
    tok = pv.account("x08-cat@qa-bill.dk", trial=False)
    s = pv.subscription(tok)
    ui = json.loads((ROOT / "web/src/lib/prices.json").read_text())["privat"]["DKK"]
    assert s["currency"] == "DKK"
    for p in s["plans"]:
        m, ym, yt, calls = EXPECTED_DKK[p["key"]]
        assert (p["monthly_minor"], p["yearly_monthly_minor"], p["yearly_total_minor"], p["calls"]) == (m, ym, yt, calls)
        assert yt == 12 * ym                                           # yearly is charged once a year
        assert ui[p["key"]] == {"monthly": m, "yearly_monthly": ym, "yearly_total": yt}
        assert 0.19 <= 1 - ym / m <= 0.21                              # "about 20 % below monthly"


@pytest.mark.parametrize("plan", ["basis", "plus", "familie"])
@pytest.mark.parametrize("interval", ["month", "year"])
def test_x08_checkout_charges_the_listed_amount_incl_25pct_moms(api, pv, stripe_env, plan, interval):
    tok = pv.account(f"x08-co-{plan}-{interval}@qa-bill.dk", trial=False)
    r = api.post(tok, "/privat/subscription/checkout", {"plan": plan, "interval": interval})
    assert r.status_code == 200, r.text
    d = [x for m, p, x in stripe_env if (m, p) == ("POST", "/checkout/sessions")][-1]
    line = d["line_items"][0]
    m, _, yt, calls = EXPECTED_DKK[plan]
    pd = line["price_data"]
    assert (pd["currency"], pd["unit_amount"], pd["tax_behavior"], pd["recurring"]) == \
        ("dkk", m if interval == "month" else yt, "inclusive", {"interval": interval})
    assert line["tax_rates"] == ["txr_dk_vat_2500_incl"]
    assert d["subscription_data"]["trial_period_days"] == 14 and d["payment_method_collection"] == "always"
    assert f"{calls} opkald om måneden" in pd["product_data"]["description"]
    assert "inkl. 25 % moms" in pd["product_data"]["description"]


def test_x08_stripe_tax_enabled_lets_stripe_decide_the_moms(api, pv, stripe_env, monkeypatch):
    monkeypatch.setenv("STRIPE_TAX_ENABLED", "true")
    get_settings.cache_clear()
    tok = pv.account("x08-tax@qa-bill.dk", trial=False)
    assert api.post(tok, "/privat/subscription/checkout", {"plan": "familie", "interval": "year"}).status_code == 200
    d = [x for m, p, x in stripe_env if (m, p) == ("POST", "/checkout/sessions")][-1]
    line = d["line_items"][0]
    assert d["automatic_tax"] == {"enabled": True} and d["billing_address_collection"] == "required"
    assert "tax_rates" not in line                                            # no rate of ours on top of Stripe Tax
    assert line["price_data"]["tax_behavior"] == "inclusive" and line["price_data"]["unit_amount"] == 162000
    assert line["price_data"]["product_data"]["tax_code"] == "txcd_10103000"
    assert not [p for m, p, _ in stripe_env if p == "/tax_rates"]


# --------------------------------------------------------------------------- trial, cancellation, expiry

def test_x08_trial_then_active_and_cancel_inside_the_trial(api, client, pv, db, stripe_env):
    tok = pv.account("x08-trial@qa-bill.dk", trial=False)
    ws = pv.ws(tok)
    t_end = WED_10 + timedelta(days=14)
    assert _event(client, _ev("evt_x08_t1", "created", _sub(ws, status="trialing", plan="basis", trial_end=t_end,
                                                              period_end=t_end)))["outcome"] == "applied"
    s = pv.subscription(tok)
    assert (s["status"], s["plan"], s["entitled"], s["calls_quota"], s["trial_days_left"]) == ("trial", "basis", True, 3, 14)
    # the customer cancels in the trial (portal: cancel at period end) → keeps the trial until it ends, never charged
    assert _event(client, _ev("evt_x08_t2", "updated", _sub(ws, status="trialing", plan="basis", trial_end=t_end,
                                                              period_end=t_end, cancel=True)))["outcome"] == "applied"
    s = pv.subscription(tok)
    assert (s["status"], s["entitled"], s["cancel_at_period_end"]) == ("trial", True, True)
    # at the trial end Stripe deletes it: no rights, nothing charged
    pv.clock.at = t_end + timedelta(minutes=1)
    assert _event(client, _ev("evt_x08_t3", "deleted", _sub(ws, status="canceled", plan="basis", trial_end=t_end,
                                                              period_end=t_end, cancel=True)))["outcome"] == "applied"
    s = pv.subscription(tok)
    assert (s["status"], s["plan"], s["entitled"], s["calls_quota"]) == ("canceled", "none", False, 0)
    # one trial per account: a new checkout has no second trial
    assert api.post(tok, "/privat/subscription/checkout", {"plan": "plus", "interval": "month"}).status_code == 200
    d = [x for m, p, x in stripe_env if (m, p) == ("POST", "/checkout/sessions")][-1]
    assert "trial_period_days" not in d["subscription_data"]


def test_x08_trial_expiry_converts_to_paid_plan(api, client, pv, db, stripe_env):
    tok = pv.account("x08-expiry@qa-bill.dk", trial=False)
    ws = pv.ws(tok)
    t_end = WED_10 + timedelta(days=14)
    _event(client, _ev("evt_x08_e1", "created", _sub(ws, status="trialing", plan="familie", trial_end=t_end, period_end=t_end)))
    pv.clock.at = t_end + timedelta(hours=1)
    _event(client, _ev("evt_x08_e2", "updated", _sub(ws, status="active", plan="familie", period_end=t_end + timedelta(days=30))))
    s = pv.subscription(tok)
    assert (s["status"], s["plan"], s["entitled"], s["calls_quota"], s["people_limit"]) == ("active", "familie", True, 25, 5)


@pytest.mark.xfail(strict=True, reason="F-BQ-005-X08 needs-decision: an immediately canceled trial keeps Plus/plan "
                                       "rights until the original trial end")
def test_x08_immediate_cancel_in_trial_ends_rights(api, client, pv, db, stripe_env):
    tok = pv.account("x08-cancelnow@qa-bill.dk", trial=False)
    ws = pv.ws(tok)
    t_end = WED_10 + timedelta(days=14)
    _event(client, _ev("evt_x08_c1", "created", _sub(ws, status="trialing", plan="plus", trial_end=t_end, period_end=t_end)))
    _event(client, _ev("evt_x08_c2", "deleted", _sub(ws, status="canceled", plan="plus", trial_end=t_end, period_end=t_end,
                                                     extra={"canceled_at": int(WED_10.timestamp()),
                                                            "ended_at": int(WED_10.timestamp())})))
    assert pv.subscription(tok)["entitled"] is False


# --------------------------------------------------------------------------- failed renewal

def test_x08_failed_renewal_past_due_keeps_rights_during_dunning(api, client, pv, db, stripe_env):
    tok = pv.account("x08-pastdue@qa-bill.dk", trial=False)
    ws = pv.ws(tok)
    _event(client, _ev("evt_x08_p1", "updated", _sub(ws, status="past_due", plan="plus")))
    s = pv.subscription(tok)
    assert (s["status"], s["entitled"], s["calls_quota"]) == ("past_due", True, 10)


def test_x08_subscription_ended_for_non_payment_has_no_rights_for_the_unpaid_period(api, client, pv, db, stripe_env):
    """Renewal on 4/11 failed; Stripe's retries end 18/11 and it cancels the subscription. The period 4/11–4/12 was
    never paid, so no rights must remain ("canceled: the paid period still runs out" – it was not paid)."""
    tok = pv.account("x08-unpaid@qa-bill.dk", trial=False)
    ws = pv.ws(tok)
    unpaid_end = WED_10 + timedelta(days=30)
    _event(client, _ev("evt_x08_u1", "updated", _sub(ws, status="past_due", plan="plus", period_end=unpaid_end)))
    pv.clock.at = WED_10 + timedelta(days=14)
    _event(client, _ev("evt_x08_u2", "deleted", _sub(ws, status="canceled", plan="plus", period_end=unpaid_end,
                                                     extra={"ended_at": int(pv.clock.at.timestamp()),
                                                            "cancellation_details": {"reason": "payment_failed"}})))
    s = pv.subscription(tok)
    assert s["status"] == "canceled"
    assert s["entitled"] is False, f"unpaid period still grants {s['plan']} with {s['calls_quota']} calls"


# --------------------------------------------------------------------------- plan / interval changes in the Billing Portal

def test_x08_plan_change_in_portal_follows_the_price_paid(api, client, pv, db, stripe_env, monkeypatch):
    """Basis → Familie in the Stripe Billing Portal: Stripe swaps the item's price; the subscription METADATA (set once at
    Checkout) still says basis. The customer pays 169 kr. and must get Familie (25 calls, 5 people) – and the reverse
    (Familie → Basis) must not keep Familie rights at the Basis price."""
    monkeypatch.setenv("PRIVAT_STRIPE_PRICE_BASIS_MONTH", "price_basis_m")
    monkeypatch.setenv("PRIVAT_STRIPE_PRICE_FAMILIE_MONTH", "price_familie_m")
    get_settings.cache_clear()
    tok = pv.account("x08-portal@qa-bill.dk", trial=False)
    ws = pv.ws(tok)
    _event(client, _ev("evt_x08_pc1", "created", _sub(ws, plan="basis", price_id="price_basis_m")))
    assert pv.subscription(tok)["plan"] == "basis"
    _event(client, _ev("evt_x08_pc2", "updated", _sub(ws, plan="basis", price_id="price_familie_m")))
    s = pv.subscription(tok)
    assert (s["plan"], s["calls_quota"], s["people_limit"]) == ("familie", 25, 5)


def test_x08_month_to_year_in_portal_updates_the_interval(api, client, pv, db, stripe_env):
    tok = pv.account("x08-interval@qa-bill.dk", trial=False)
    ws = pv.ws(tok)
    _event(client, _ev("evt_x08_i1", "created", _sub(ws, plan="plus", interval="month")))
    assert pv.subscription(tok)["interval"] == "month"
    _event(client, _ev("evt_x08_i2", "updated", _sub(ws, plan="plus", interval="month", item_interval="year",
                                                     period_end=WED_10 + timedelta(days=365))))
    assert pv.subscription(tok)["interval"] == "year"


# --------------------------------------------------------------------------- webhook ordering

def test_x08_duplicate_event_has_no_second_effect(api, client, pv, db, stripe_env):
    tok = pv.account("x08-dup@qa-bill.dk", trial=False)
    ws = pv.ws(tok)
    ev = _ev("evt_x08_d1", "created", _sub(ws, plan="plus"))
    assert _event(client, ev)["outcome"] == "applied"
    assert _event(client, ev)["outcome"] == "duplicate"


def test_x08_out_of_order_stale_trialing_event_does_not_lock_out_a_paying_customer(api, client, pv, db, stripe_env):
    """Stripe does not guarantee event order. The trial→active update (created later) arrives first, then the older
    trialing update. The customer has paid and must stay active."""
    tok = pv.account("x08-order@qa-bill.dk", trial=False)
    ws = pv.ws(tok)
    t_end = WED_10 + timedelta(days=14)
    t_old, t_new = int(WED_10.timestamp()), int((t_end + timedelta(minutes=5)).timestamp())
    pv.clock.at = t_end + timedelta(hours=1)
    _event(client, _ev("evt_x08_o_new", "updated", _sub(ws, status="active", plan="plus",
                                                         period_end=t_end + timedelta(days=30)), created=t_new))
    _event(client, _ev("evt_x08_o_old", "updated", _sub(ws, status="trialing", plan="plus", trial_end=t_end,
                                                         period_end=t_end), created=t_old))
    s = pv.subscription(tok)
    assert (s["status"], s["entitled"]) == ("active", True), s


# --------------------------------------------------------------------------- UI text = what is charged after the trial

def test_x08_paywall_trial_note_names_the_price_charged_after_the_trial():
    """The paywall's «Prøv 14 dage» button checks out Plus MONTHLY (store.tsx startTrial). The note under it must name
    that price (99 kr./md.), not the yearly per-month price (79 kr./md.) that the customer is not signing up for."""
    store = (ROOT / "web/src/components/privat/store.tsx").read_text()
    assert 'subscriptionCheckout({ plan: "plus", interval: "month"' in store       # what startTrial buys
    prices_json = json.loads((ROOT / "web/src/lib/prices.json").read_text())["privat"]["DKK"]["plus"]
    charged = prices_json["monthly"]                                                # 9900 after the trial
    for loc in ("da", "en", "de", "sv", "no"):
        note = json.loads((ROOT / f"web/src/i18n/messages/{loc}/privat.json").read_text())["paywall"]["trialNote"]
        names = "{pPlus}" if "{pPlus}" in note else "{pPlusYear}" if "{pPlusYear}" in note else None
        shown = {"{pPlus}": prices_json["monthly"], "{pPlusYear}": prices_json["yearly_monthly"]}.get(names)
        assert shown == charged, f"{loc}: paywall says {shown} øre/md after the trial, checkout charges {charged}"

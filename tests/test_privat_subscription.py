"""Dialogbot Privat subscriptions: the 14-day trial, entitlements, plan calls before extra calls from the Opkaldssaldo,
unlimited tasks with a
plan, the Shop's needs_plan gate, Stripe Checkout payload, the webhook upsert and the Billing Portal."""
from __future__ import annotations

import hashlib
import hmac
import json
import time
from datetime import UTC, datetime, timedelta

from app.config import get_settings
from app.models import CreditLedger, PrivateCall, PrivateSubscription, PrivateTask
from app.modules.billing import markets, prices
from app.modules.billing import stripe as stripe_api
from app.modules.campaigns import service as campaigns
from app.modules.privat import subscriptions
from tests.privat_fixtures import WED_10
from tests.test_privat import _propose, _report

PLAN_KEYS = {"key", "name", "currency", "monthly_minor", "yearly_monthly_minor", "yearly_total_minor", "calls", "people",
             "apps_included", "recommended", "features"}
SUB_KEYS = {"plan", "status", "interval", "trial_ends_at", "trial_days_left", "current_period_end",
            "cancel_at_period_end", "entitled", "calls_quota", "calls_used", "calls_left", "people_limit",
            "apps_included", "currency", "plans"}


def _stripe_event(client, event: dict, secret="whsec_privat") -> dict:
    body = json.dumps(event).encode()
    ts = int(time.time())
    sig = hmac.new(secret.encode(), f"{ts}.".encode() + body, hashlib.sha256).hexdigest()
    return client.post("/api/v1/webhooks/stripe", content=body, headers={"stripe-signature": f"t={ts},v1={sig}"}).json()


def _stripe_env(monkeypatch):
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_x")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_privat")
    get_settings.cache_clear()


def _sub_obj(ws, *, sid="sub_1", status="active", plan="plus", interval="month", period_end=None, cancel=False,
             customer="cus_1", meta=True) -> dict:
    end = period_end or int((WED_10 + timedelta(days=30)).timestamp())
    return {"id": sid, "object": "subscription", "status": status, "customer": customer,
            "cancel_at_period_end": cancel,
            "items": {"data": [{"current_period_end": end, "price": {"recurring": {"interval": interval}}}]},
            "metadata": {"kind": "privat_subscription", "workspace_id": str(ws), "plan": plan, "interval": interval}
            if meta else {}}


# --------------------------------------------------------------------------- trial and shape

def test_the_account_starts_free_and_the_trial_comes_with_the_card(api, pv, db):
    tok = pv.account("mette@testmail.dk", trial=False)
    ws = pv.ws(tok)
    row = db.get(PrivateSubscription, ws)
    assert (row.status, row.trial_ends_at, row.stripe_subscription_id) == ("none", None, None)  # the free tier
    sub = pv.subscription(tok)
    assert set(sub) == SUB_KEYS and all(set(p) == PLAN_KEYS for p in sub["plans"])
    assert (sub["plan"], sub["status"], sub["entitled"], sub["calls_quota"], sub["trial_days_left"]) == ("none", "none", False, 0, 0)
    api.post(tok, "/privat/account")  # idempotent
    db.expire_all()
    assert db.get(PrivateSubscription, ws).status == "none"
    pv.start_trial(tok)  # Stripe Checkout with a card → the webhook mirrors «trialing» as our trial
    sub = pv.subscription(tok)
    assert sub["plan"] == "plus" and sub["status"] == "trial" and sub["entitled"] is True
    assert sub["trial_days_left"] == 14 and sub["trial_ends_at"] == (WED_10 + timedelta(days=14)).isoformat()
    assert (sub["calls_quota"], sub["calls_used"], sub["calls_left"]) == (10, 0, 10)
    assert sub["people_limit"] == 1 and sub["apps_included"] is True and sub["interval"] == "month"
    assert [p["key"] for p in sub["plans"]] == ["basis", "plus", "familie"]
    plus = sub["plans"][1]
    assert (plus["monthly_minor"], plus["yearly_monthly_minor"], plus["yearly_total_minor"]) == (9900, 7900, 94800)
    assert plus["recommended"] is True and sub["plans"][0]["recommended"] is False
    assert (sub["plans"][2]["calls"], sub["plans"][2]["people"]) == (25, 5)
    # the last trial day still counts; the day after it is expired
    pv.clock.at = WED_10 + timedelta(days=13, hours=23)
    s = pv.subscription(tok)
    assert s["trial_days_left"] == 1 and s["entitled"] is True
    pv.clock.at = WED_10 + timedelta(days=14, minutes=1)
    s = pv.subscription(tok)
    assert (s["plan"], s["status"], s["entitled"], s["trial_days_left"], s["calls_quota"]) == ("none", "expired", False, 0, 0)
    me = pv.me(tok)
    assert (me["plan"], me["plan_status"], me["entitled"], me["calls_left"]) == ("none", "expired", False, 0)


def test_old_account_without_a_row_is_free(api, pv, db):
    tok = pv.account("mette@testmail.dk")
    ws = pv.ws(tok)
    db.query(PrivateSubscription).filter_by(workspace_id=ws).delete()
    db.commit()
    pv.clock.at = WED_10 + timedelta(days=40)
    me = pv.me(tok)
    assert me["plan_status"] == "none" and me["trial_days_left"] == 0 and me["entitled"] is False
    db.expire_all()
    assert db.get(PrivateSubscription, ws).status == "none"


def test_an_old_cardless_trial_keeps_running(api, pv, db):
    """Accounts from before this change had a local trial without a card: it is honoured until it expires."""
    tok = pv.account("mette@testmail.dk", trial=False)
    ws = pv.ws(tok)
    row = db.get(PrivateSubscription, ws)
    row.status, row.plan, row.trial_ends_at = "trial", "plus", WED_10 + timedelta(days=3)
    db.commit()
    me = pv.me(tok)
    assert (me["plan_status"], me["plan"], me["entitled"], me["trial_days_left"]) == ("trial", "plus", True, 3)
    pv.clock.at = WED_10 + timedelta(days=4)
    assert pv.me(tok)["plan_status"] == "expired"


def test_entitlements_per_status(api, pv):
    tok = pv.account("mette@testmail.dk")
    pv.set_plan(tok, "basis")
    s = pv.subscription(tok)
    assert (s["plan"], s["status"], s["entitled"], s["calls_quota"], s["apps_included"], s["interval"]) == \
        ("basis", "active", True, 3, False, "month")
    pv.set_plan(tok, "familie", status="past_due", interval="year")
    s = pv.subscription(tok)
    assert (s["plan"], s["status"], s["entitled"], s["calls_quota"], s["people_limit"]) == ("familie", "past_due", True, 25, 5)
    # canceled: rights last until the paid period ends
    pv.set_plan(tok, "plus", status="canceled", period_days=5)
    s = pv.subscription(tok)
    assert (s["plan"], s["status"], s["entitled"]) == ("plus", "canceled", True)
    pv.clock.at = WED_10 + timedelta(days=6)
    s = pv.subscription(tok)
    assert (s["plan"], s["status"], s["entitled"], s["calls_quota"]) == ("none", "canceled", False, 0)


# --------------------------------------------------------------------------- tasks

def test_task_11_is_not_a_draft_during_the_trial(api, pv, db):
    tok = pv.account("mette@testmail.dk")
    for i in range(12):
        pv.say(tok, f"Lav en liste med ting {i}")
    tasks = api.get(tok, "/privat/tasks").json()
    assert len(tasks) == 12 and all(t["status"] == "in_progress" for t in tasks)
    assert all(t["usage_text"] == "Med i prøveperioden" for t in tasks)
    assert pv.me(tok)["free_used"] == 0 and pv.me(tok)["balance_minor"] == 1000
    assert db.query(PrivateTask).filter_by(paid_by="plan").count() == 12
    pv.set_plan(tok, "basis")
    out = pv.say(tok, "Mind mig om at hente pakken i morgen kl 16")
    assert out["messages"][-1]["kind"] == "task"
    assert pv.task(tok, out["messages"][-1]["task_id"]).json()["usage_text"] == "Med i Basis"
    # trial over, no plan: nothing is free – the next task is a draft
    pv.expire_trial(tok)
    assert pv.me(tok)["free_used"] == 0 and pv.me(tok)["free_limit"] == 0
    assert pv.say(tok, "Lav en liste med y")["messages"][-1]["kind"] == "draft"


# --------------------------------------------------------------------------- calls

def _approve_plan(api, pv, tok, monkeypatch, vapi_id="call_v1"):
    called = []
    monkeypatch.setattr(campaigns, "create_call", lambda p: called.append(p) or {"id": vapi_id})
    tid = _propose(pv, tok)
    t = api.post(tok, f"/privat/calls/{tid}/approve", {"share_phone": False}).json()
    return tid, t, called


def test_calls_use_the_plan_quota_first_then_the_balance(api, client, pv, db, monkeypatch):
    tok = pv.account("mette@testmail.dk")
    pv.verify_phone(tok)
    pv.set_plan(tok, "basis")  # 3 calls a month
    tid1, t, called = _approve_plan(api, pv, tok, monkeypatch, "call_1")
    assert t["status"] == "in_progress" and t["usage_text"] == "Opkald 1 af 3 i Basis"
    assert t["events"][-1]["text"] == "Du godkendte opkaldet. Opkald 1 af 3 i Basis."
    assert len(called) == 1
    me = pv.me(tok)
    assert (me["balance_minor"], me["held_minor"], me["calls_used"], me["calls_left"]) == (1000, 0, 1, 2)
    c1 = db.query(PrivateCall).filter_by(task_id=tid1).one()
    assert c1.paid_via == "plan"
    # nobody answered: the call does not count, nothing moves on the Opkaldssaldo (a plan call is never charged)
    assert _report(client, called[0], "customer-did-not-answer", [], seconds=0, call_id="call_1")["outcome"] == "applied"
    t = pv.task(tok, tid1).json()
    assert t["status"] == "awaiting_user" and t["events"][-1]["text"] == "Ingen tog telefonen – opkaldet tæller ikke"
    assert t["usage_text"] == "Intet forbrug – ingen svarede"
    assert pv.me(tok)["calls_used"] == 0 and pv.me(tok)["balance_minor"] == 1000
    assert api.get(tok, "/privat/ledger").json()[0]["kind"] == "grant"  # only the welcome grant
    # answered calls count: 1, 2, 3
    for n in (1, 2, 3):
        tid, t, called = _approve_plan(api, pv, tok, monkeypatch, f"call_a{n}")
        assert t["usage_text"] == f"Opkald {n} af 3 i Basis"
        msgs = [{"role": "bot", "message": "Hej"}, {"role": "user", "message": "Ja, torsdag kl. 15.30 passer."}]
        assert _report(client, called[0], "customer-ended-call", msgs, seconds=70, call_id=f"call_a{n}")["outcome"] == "applied"
        t = pv.task(tok, tid).json()
        assert t["status"] == "done" and t["usage_text"] == f"Opkald {n} af 3 i Basis · besvaret, 1 min. 10 sek."
        assert t["events"][-1]["text"] == f"Opkald {n} af 3 i Basis"
    me = pv.me(tok)
    assert (me["calls_used"], me["calls_left"], me["balance_minor"], me["held_minor"]) == (3, 0, 1000, 0)
    assert not any(r["kind"] in ("reserve", "capture", "release") for r in api.get(tok, "/privat/ledger").json())
    # quota used: approval makes it an EXTRA call – its maximum (17,50\u00a0kr.) is reserved on the Opkaldssaldo (F-PDEC-01)
    pv.top_up(tok, 1000)
    tid4, t, called = _approve_plan(api, pv, tok, monkeypatch, "call_4")
    assert t["usage_text"] == "Ekstra opkald · højst 17,50\u00a0kr. reserveret"
    assert db.query(PrivateCall).filter_by(task_id=tid4).one().paid_via == "balance"
    assert pv.me(tok)["balance_minor"] == 250 and pv.me(tok)["held_minor"] == 1750
    assert _report(client, called[0], "customer-did-not-answer", [], seconds=0, call_id="call_4")["outcome"] == "applied"
    # an unanswered call still does not count against the quota, but an unanswered EXTRA call costs 0,31\u00a0kr.
    assert pv.task(tok, tid4).json()["events"][-1]["text"] == \
        "Ingen tog telefonen – 0,31\u00a0kr. er trukket fra din opkaldssaldo, resten er frigivet"
    assert pv.me(tok)["balance_minor"] == 2000 - 31 and pv.me(tok)["calls_used"] == 3
    # out of quota AND not enough on the balance: 409 «Fyld op», with the plan in the extra
    db.add(CreditLedger(workspace_id=pv.ws(tok), kind="spend", amount=-1000, source_ref="test:spend", text="t"))
    db.commit()
    tid5 = _propose(pv, tok)
    r = api.post(tok, f"/privat/calls/{tid5}/approve", {"share_phone": False})
    assert r.status_code == 409 and r.json()["code"] == "insufficient_balance"
    assert r.json()["calls_left"] == 0 and r.json()["needs_plan"] is False and r.json()["cta"]["label"] == "Fyld op"
    # a new month: the quota is back
    pv.clock.at = datetime(2026, 12, 1, 9, 0, tzinfo=UTC)
    assert pv.me(tok)["calls_used"] == 0 and pv.me(tok)["calls_left"] == 3
    assert pv.task(tok, tid5).json()["usage_text"] == "Ekstra opkald: højst 17,50\u00a0kr., når du godkender"  # when proposed


def test_trial_calls_say_plus(api, pv, monkeypatch):
    tok = pv.account("mette@testmail.dk")
    pv.verify_phone(tok)
    tid = _propose(pv, tok)
    assert pv.task(tok, tid).json()["usage_text"] == "Opkald 1 af 10 i Plus, når du godkender"
    _tid, t, called = _approve_plan(api, pv, tok, monkeypatch)
    assert t["usage_text"] == "Opkald 1 af 10 i Plus" and len(called) == 1
    assert pv.me(tok)["calls_left"] == 9 and pv.me(tok)["held_minor"] == 0


# --------------------------------------------------------------------------- the Shop

def test_addon_enable_needs_plan(api, pv):
    tok = pv.account("mette@testmail.dk")
    cat = {a["key"]: a for a in api.get(tok, "/privat/addons").json()}
    assert cat["ring-for-mig"]["included_in"] == ["basis", "plus", "familie"] and cat["ring-for-mig"]["requires_plan"]
    assert cat["delte-lister"]["included"] is True and cat["delte-lister"]["requires_plan"] is False
    assert cat["kalender"]["included"] is True and cat["kalender"]["included_in"] == ["plus", "familie"]
    for key in ("foedselsdage", "madplan", "bil-og-syn", "regninger", "laege-og-tandlaege", "pakkeliste"):
        a = cat[key]
        assert a["status"] in ("coming_soon", "available") and a["what"] and a["example"] and len(a["steps"]) >= 2
        assert a["included_in"] == ["plus", "familie"]
        if a["status"] == "coming_soon":
            assert api.post(tok, f"/privat/addons/{key}/enable").json()["code"] == "coming_soon"
    assert all(a["what"] and a["example"] and a["steps"] for a in cat.values())
    # trial over: plan apps are locked, free ones are not
    pv.expire_trial(tok)
    cat = {a["key"]: a for a in api.get(tok, "/privat/addons").json()}
    assert cat["ring-for-mig"]["included"] is False and cat["ring-for-mig"]["enabled"] is True  # stays on (stopped)
    assert cat["delte-lister"]["included"] is True
    api.post(tok, "/privat/addons/ring-for-mig/disable")
    r = api.post(tok, "/privat/addons/ring-for-mig/enable")
    assert r.status_code == 409 and r.json()["code"] == "needs_plan" and r.json()["addon"] == "ring-for-mig"
    assert r.json()["plans"] == ["basis", "plus", "familie"]
    api.post(tok, "/privat/addons/delte-lister/disable")
    assert api.post(tok, "/privat/addons/delte-lister/enable").json()["enabled"] is True
    # Basis does not include Plus apps
    pv.set_plan(tok, "basis")
    assert api.post(tok, "/privat/addons/ring-for-mig/enable").json()["enabled"] is True
    cat = {a["key"]: a for a in api.get(tok, "/privat/addons").json()}
    assert cat["kalender"]["included"] is False and cat["pakker"]["included"] is False
    pv.set_plan(tok, "familie")
    cat = {a["key"]: a for a in api.get(tok, "/privat/addons").json()}
    assert cat["kalender"]["included"] is True


# --------------------------------------------------------------------------- Stripe

def _fake_checkout(monkeypatch):
    """A fake Stripe: tax rates (listed empty, then created as txr_<metadata>) and Checkout sessions."""
    sent = []

    def fake(m, p, d=None, **k):
        sent.append((m, p, d))
        if p == "/tax_rates":
            return {"data": []} if m == "GET" else {"id": f"txr_{d['metadata']['dialogbot']}"}
        return {"id": "cs_sub_1", "url": "https://checkout.stripe.com/c/pay/cs_sub_1"}

    monkeypatch.setattr(stripe_api, "request", fake)
    return sent


def _sessions(sent) -> list[dict]:
    return [d for m, p, d in sent if (m, p) == ("POST", "/checkout/sessions")]


def test_checkout_payload(api, pv, db, monkeypatch):
    tok = pv.account("mette@testmail.dk", trial=False)  # a fresh sign-up: the trial starts here, with the card
    ws = pv.ws(tok)
    _stripe_env(monkeypatch)
    sent = _fake_checkout(monkeypatch)
    r = api.post(tok, "/privat/subscription/checkout", {"plan": "plus", "interval": "month"})
    assert r.json() == {"url": "https://checkout.stripe.com/c/pay/cs_sub_1"}
    d = _sessions(sent)[0]
    assert d["mode"] == "subscription" and d["locale"] == "da"
    line = d["line_items"][0]
    assert line["price_data"] == {"currency": "dkk", "unit_amount": 9900, "tax_behavior": "inclusive",
                                  "recurring": {"interval": "month"},
                                  "product_data": {"name": "Dialogbot Privat – Plus",
                                                   "description": "99\u00a0kr. pr. måned inkl. 25 % moms · 10 opkald om måneden"}}
    assert line["tax_rates"] == ["txr_dk_vat_2500_incl"]  # 25 % Danish VAT, included in the price
    created = next(x for x in sent if x[:2] == ("POST", "/tax_rates"))[2]
    assert (created["percentage"], created["inclusive"], created["country"]) == (25, True, "DK")
    meta = {"kind": "privat_subscription", "workspace_id": str(ws), "plan": "plus", "interval": "month", "currency": "DKK"}
    assert d["metadata"] == meta and d["subscription_data"]["metadata"] == meta
    assert d["subscription_data"]["trial_period_days"] == 14  # 14 days free, the card is given now
    assert d["payment_method_collection"] == "always" and d["billing_address_collection"] == "required"
    assert d["phone_number_collection"] == {"enabled": True}  # name, address and phone at Stripe, never stored by us
    assert d["customer_email"] == "mette@testmail.dk" and d["client_reference_id"] == str(ws)
    assert d["success_url"] == "http://frontend.test/privat/konto?abonnement=ok&session_id={CHECKOUT_SESSION_ID}"
    assert d["cancel_url"] == "http://frontend.test/privat/konto?abonnement=annulleret"
    assert db.get(PrivateSubscription, ws).currency == "DKK"
    # yearly: the yearly total, interval year. After a trial (expired or running at Stripe): never a second one.
    pv.start_trial(tok)
    pv.expire_trial(tok)
    api.post(tok, "/privat/subscription/checkout", {"plan": "familie", "interval": "year"})
    d = _sessions(sent)[1]
    assert d["line_items"][0]["price_data"]["unit_amount"] == 162000
    assert d["line_items"][0]["price_data"]["recurring"] == {"interval": "year"}
    assert "trial_period_days" not in d["subscription_data"] and "trial_end" not in d["subscription_data"]
    # a fixed Stripe price id replaces price_data (it is a DKK price)
    monkeypatch.setenv("PRIVAT_STRIPE_PRICE_BASIS_MONTH", "price_basis_m")
    get_settings.cache_clear()
    api.post(tok, "/privat/subscription/checkout", {"plan": "basis", "interval": "month"})
    assert _sessions(sent)[2]["line_items"][0] == {"price": "price_basis_m", "quantity": 1,
                                                  "tax_rates": ["txr_dk_vat_2500_incl"]}
    assert api.post(tok, "/privat/subscription/checkout", {"plan": "gold", "interval": "month"}).status_code == 422
    assert api.post(tok, "/privat/subscription/checkout", {"plan": "plus", "locale": "xx"}).status_code == 422
    assert prices.PRIVAT_PLANS[0]["monthly_minor"] == 4900


def test_checkout_in_the_visitors_currency_and_language(api, pv, db, monkeypatch):
    _stripe_env(monkeypatch)
    sent = _fake_checkout(monkeypatch)
    # German: EUR, Stripe locale de, English text, 25 % Danish VAT in the default «danish» mode
    tok = pv.account("hans@testmail.dk", trial=False)
    ws = pv.ws(tok)
    assert api.post(tok, "/privat/subscription/checkout", {"plan": "plus", "interval": "year", "locale": "de"}).status_code == 200
    d = _sessions(sent)[-1]
    pd = d["line_items"][0]["price_data"]
    assert (d["locale"], pd["currency"], pd["unit_amount"]) == ("de", "eur", markets.PRIVAT["EUR"]["plus"]["yearly_total"])
    assert pd["product_data"]["description"] == "€129.48 per year (€10.79/month) incl. 25 % VAT · 10 calls a month"
    assert d["line_items"][0]["tax_rates"] == ["txr_dk_vat_2500_incl"] and d["metadata"]["currency"] == "EUR"
    assert db.get(PrivateSubscription, ws).currency == "EUR"
    # the customer keeps EUR, whatever language it comes back in, and is shown EUR even if DKK is asked for
    api.post(tok, "/privat/subscription/checkout", {"plan": "basis", "interval": "month", "locale": "da"})
    d = _sessions(sent)[-1]
    assert (d["locale"], d["line_items"][0]["price_data"]["currency"]) == ("da", "eur")
    sub = api.get(tok, "/privat/subscription?currency=DKK").json()
    assert sub["currency"] == "EUR" and {p["currency"] for p in sub["plans"]} == {"EUR"}
    # «destination» mode: the consumer's own country's rate (Germany 19 %)
    monkeypatch.setenv("PRIVAT_EU_VAT_MODE", "destination")
    get_settings.cache_clear()
    api.post(tok, "/privat/subscription/checkout", {"plan": "plus", "interval": "month", "locale": "de"})
    d = _sessions(sent)[-1]
    assert d["line_items"][0]["tax_rates"] == ["txr_de_vat_1900_incl"]
    assert "incl. 19 % VAT" in d["line_items"][0]["price_data"]["product_data"]["description"]
    monkeypatch.delenv("PRIVAT_EU_VAT_MODE")
    get_settings.cache_clear()
    # Swedish: SEK, locale sv
    tok2 = pv.account("sven@testmail.dk", trial=False)
    api.post(tok2, "/privat/subscription/checkout", {"plan": "familie", "interval": "month", "locale": "sv"})
    d = _sessions(sent)[-1]
    pd = d["line_items"][0]["price_data"]
    assert (d["locale"], pd["currency"], pd["unit_amount"]) == ("sv", "sek", 24900)
    assert d["line_items"][0]["tax_rates"] == ["txr_dk_vat_2500_incl"]
    # Norwegian: NOK, Stripe's nb; no VAT before VOEC registration, 25 % Norwegian VAT after
    tok3 = pv.account("ola@testmail.dk", trial=False)
    api.post(tok3, "/privat/subscription/checkout", {"plan": "plus", "interval": "month", "locale": "no"})
    d = _sessions(sent)[-1]
    assert (d["locale"], d["line_items"][0]["price_data"]["currency"]) == ("nb", "nok")
    assert "tax_rates" not in d["line_items"][0] and "VAT" not in d["line_items"][0]["price_data"]["product_data"]["description"]
    monkeypatch.setenv("NO_VOEC_REGISTERED", "true")
    get_settings.cache_clear()
    api.post(tok3, "/privat/subscription/checkout", {"plan": "plus", "interval": "month", "locale": "no"})
    assert _sessions(sent)[-1]["line_items"][0]["tax_rates"] == ["txr_no_vat_2500_incl"]
    # a fixed (DKK) Stripe price id is never used for another currency
    monkeypatch.setenv("PRIVAT_STRIPE_PRICE_PLUS_MONTH", "price_plus_m")
    get_settings.cache_clear()
    api.post(tok3, "/privat/subscription/checkout", {"plan": "plus", "interval": "month", "locale": "no"})
    assert "price" not in _sessions(sent)[-1]["line_items"][0]


def test_checkout_with_stripe_tax(api, pv, db, monkeypatch):
    """STRIPE_TAX_ENABLED: automatic_tax and the SaaS personal-use tax code, no tax rates of ours, the address is
    collected (and may be saved on an existing customer)."""
    _stripe_env(monkeypatch)
    monkeypatch.setenv("STRIPE_TAX_ENABLED", "true")
    get_settings.cache_clear()
    sent = _fake_checkout(monkeypatch)
    tok = pv.account("hans@testmail.dk", trial=False)
    ws = pv.ws(tok)
    api.post(tok, "/privat/subscription/checkout", {"plan": "plus", "interval": "month", "locale": "de"})
    d = _sessions(sent)[-1]
    line = d["line_items"][0]
    assert d["automatic_tax"] == {"enabled": True} and d["billing_address_collection"] == "required"
    assert line["price_data"]["tax_behavior"] == "inclusive" and "tax_rates" not in line
    assert line["price_data"]["product_data"]["tax_code"] == "txcd_10103000"
    assert line["price_data"]["product_data"]["description"] == "€13.49 per month incl. VAT · 10 calls a month"
    assert "customer_update" not in d and not [x for x in sent if x[1] == "/tax_rates"]
    row = db.get(PrivateSubscription, ws)
    row.stripe_customer_id = "cus_hans"
    db.commit()
    api.post(tok, "/privat/subscription/checkout", {"plan": "plus", "interval": "month", "locale": "de"})
    d = _sessions(sent)[-1]
    assert d["customer"] == "cus_hans" and d["customer_update"] == {"address": "auto", "name": "auto"}
    api.post(tok, "/privat/balance/checkout", {"locale": "da"})
    d = _sessions(sent)[-1]
    assert d["mode"] == "payment" and d["automatic_tax"] == {"enabled": True}
    assert d["line_items"][0]["price_data"]["product_data"]["tax_code"] == "txcd_10103000"
    assert "tax_rates" not in d["line_items"][0] and d["billing_address_collection"] == "required"
    assert d["line_items"][0]["price_data"]["product_data"]["description"] == "Opkaldssaldo · €7 inkl. moms"  # EUR now


def test_a_dkk_customer_stays_dkk(api, pv, db, monkeypatch):
    _stripe_env(monkeypatch)
    sent = _fake_checkout(monkeypatch)
    tok = pv.account("mette@testmail.dk", trial=False)
    ws = pv.ws(tok)
    db.get(PrivateSubscription, ws).currency = "DKK"
    db.commit()
    api.post(tok, "/privat/subscription/checkout", {"plan": "plus", "interval": "month", "locale": "de"})
    d = _sessions(sent)[-1]
    assert d["line_items"][0]["price_data"]["currency"] == "dkk" and d["line_items"][0]["price_data"]["unit_amount"] == 9900
    assert d["locale"] == "de"  # the page is still in the visitor's language
    assert api.get(tok, "/privat/subscription?currency=EUR").json()["currency"] == "DKK"
    api.post(tok, "/privat/balance/checkout", {"locale": "sv"})
    pd = _sessions(sent)[-1]["line_items"][0]["price_data"]
    assert (pd["currency"], pd["unit_amount"]) == ("dkk", 5000)


def test_plans_and_subscription_per_currency(api, pv):
    for cur in markets.CURRENCIES:
        plans = subscriptions.plans_out(cur)
        assert [p["key"] for p in plans] == ["basis", "plus", "familie"]
        for p in plans:
            a = markets.PRIVAT[cur][p["key"]]
            assert p["currency"] == cur and (p["monthly_minor"], p["yearly_monthly_minor"], p["yearly_total_minor"]) == (
                a["monthly"], a["yearly_monthly"], a["yearly_total"])
    assert subscriptions.plans_out()[1]["monthly_minor"] == 9900  # DKK by default
    tok = pv.account("mette@testmail.dk", trial=False)
    assert api.get(tok, "/privat/subscription").json()["currency"] == "DKK"
    sub = api.get(tok, "/privat/subscription?currency=eur").json()
    assert sub["currency"] == "EUR" and sub["plans"][0]["monthly_minor"] == 649
    assert api.get(tok, "/privat/subscription?currency=USD").status_code == 422


def test_topup_checkout_and_webhook_per_currency(api, client, pv, db, monkeypatch):
    """F-PDEC-01: the Opkaldssaldo is filled up with 50/100/200 kr. – in another currency the same amounts × the
    market's factor, rounded to whole units – and the account's DKK welcome bonus moves to its currency once."""
    _stripe_env(monkeypatch)
    sent = _fake_checkout(monkeypatch)
    tok = pv.account("hans@testmail.dk", trial=False)
    ws = pv.ws(tok)
    assert pv.me(tok)["currency"] == "DKK" and pv.me(tok)["balance_minor"] == 1000
    assert api.post(tok, "/privat/balance/checkout", {"locale": "de"}).status_code == 200
    d = _sessions(sent)[-1]
    pd = d["line_items"][0]["price_data"]
    assert (d["locale"], pd["currency"], pd["unit_amount"]) == ("de", "eur", 700)
    assert pd["product_data"]["description"] == "Opkaldssaldo · €7 incl. 25 % VAT" and d["metadata"]["currency"] == "EUR"
    assert d["line_items"][0]["tax_rates"] == ["txr_dk_vat_2500_incl"]
    me = pv.me(tok)  # the first Checkout gave the account EUR: 10 kr. welcome bonus = €1.35 (factor 0,135)
    assert (me["currency"], me["balance_minor"], me["topups_minor"]) == ("EUR", 135, [700, 1400, 2700])
    assert me["extra_call"] == {"answered": 69, "voicemail": 18, "no_answer": 4, "minute": 34, "max": 239}
    assert api.post(tok, "/privat/balance/checkout", {"amount_minor": 5000}).status_code == 422  # a DKK amount
    # the webhook adds a EUR top-up paid in full
    obj = {"id": "cs_eur_1", "mode": "payment", "payment_status": "paid", "currency": "eur", "amount_total": 700,
           "metadata": {"kind": "privat_topup", "workspace_id": str(ws), "amount_minor": "700", "currency": "EUR"}}
    out = _stripe_event(client, {"id": "evt_eur_1", "type": "checkout.session.completed", "data": {"object": obj}})
    assert out["outcome"] == "applied"
    rows = db.query(CreditLedger).filter_by(workspace_id=ws).order_by(CreditLedger.created_at).all()
    assert (rows[-1].amount, rows[-1].currency) == (700, "EUR") and "€7" in rows[-1].text
    assert pv.me(tok)["balance_minor"] == 835
    short = obj | {"id": "cs_eur_2", "amount_total": 300}
    assert _stripe_event(client, {"id": "evt_eur_2", "type": "checkout.session.completed",
                                  "data": {"object": short}})["outcome"] == "ignored"
    # Danish, DKK: the VAT spelled out
    mette = pv.account("mette@testmail.dk", trial=False)
    api.post(mette, "/privat/balance/checkout", {"amount_minor": 20000})
    d = _sessions(sent)[-1]
    assert d["locale"] == "da" and d["line_items"][0]["price_data"]["product_data"]["description"] == \
        "Opkaldssaldo · 200\u00a0kr. inkl. 25 % moms (160\u00a0kr. + 40\u00a0kr. moms)"


def test_webhook_upserts_subscription(api, client, pv, db, monkeypatch):
    tok = pv.account("mette@testmail.dk", trial=False)
    ws = pv.ws(tok)
    _stripe_env(monkeypatch)
    # Stripe's trialing (the 14 days on the subscription the card was given for) is our trial, with its trial_end
    sub = _sub_obj(ws, status="trialing", customer="cus_1") | {"trial_end": int((WED_10 + timedelta(days=14)).timestamp())}
    ev = {"id": "evt_sub_1", "type": "customer.subscription.created", "data": {"object": sub}}
    assert _stripe_event(client, ev)["outcome"] == "applied"
    assert _stripe_event(client, ev)["duplicate"] is True
    row = db.get(PrivateSubscription, ws)
    assert (row.status, row.plan, row.interval, row.stripe_subscription_id, row.stripe_customer_id) == \
        ("trial", "plus", "month", "sub_1", "cus_1")
    assert row.trial_ends_at == WED_10 + timedelta(days=14)
    s = pv.subscription(tok)
    assert (s["status"], s["plan"], s["entitled"], s["calls_quota"], s["trial_days_left"]) == ("trial", "plus", True, 10, 14)
    # the plan's default add-ons came on with the rights
    assert {a["key"] for a in api.get(tok, "/privat/addons").json() if a["enabled"]} >= {"ring-for-mig"}
    # after the 14 days Stripe makes it active
    sub = _sub_obj(ws, status="active", customer="cus_1")
    assert _stripe_event(client, {"id": "evt_sub_1b", "type": "customer.subscription.updated", "data": {"object": sub}})["outcome"] == "applied"
    db.expire_all()
    row = db.get(PrivateSubscription, ws)
    assert row.status == "active" and row.current_period_end == WED_10 + timedelta(days=30) and row.cancel_at_period_end is False
    s = pv.subscription(tok)
    assert (s["status"], s["plan"], s["entitled"], s["calls_quota"]) == ("active", "plus", True, 10)
    assert s["current_period_end"] == (WED_10 + timedelta(days=30)).isoformat()
    # the same object again (idempotent), then updates: past_due, cancel at period end, deleted
    assert subscriptions.upsert_from_stripe_subscription(db, sub) == "applied"
    db.commit()
    for status, cancel, ours in (("past_due", False, "past_due"), ("active", True, "active"), ("canceled", True, "canceled")):
        ev = {"id": f"evt_{status}_{cancel}", "type": "customer.subscription.updated",
              "data": {"object": _sub_obj(ws, status=status, cancel=cancel)}}
        assert _stripe_event(client, ev)["outcome"] == "applied"
        db.expire_all()
        assert db.get(PrivateSubscription, ws).status == ours and db.get(PrivateSubscription, ws).cancel_at_period_end is cancel
    s = pv.subscription(tok)
    assert s["status"] == "canceled" and s["entitled"] is True and s["cancel_at_period_end"] is True  # paid period runs
    pv.clock.at = WED_10 + timedelta(days=31)
    assert pv.subscription(tok)["entitled"] is False
    # an old subscription ending never touches the one that replaced it
    ev = {"id": "evt_new", "type": "customer.subscription.created", "data": {"object": _sub_obj(ws, sid="sub_2", plan="familie")}}
    assert _stripe_event(client, ev)["outcome"] == "applied"
    ev = {"id": "evt_old_gone", "type": "customer.subscription.deleted",
          "data": {"object": _sub_obj(ws, sid="sub_1", status="canceled")}}
    assert _stripe_event(client, ev)["outcome"] == "ignored"
    db.expire_all()
    assert (db.get(PrivateSubscription, ws).plan, db.get(PrivateSubscription, ws).status) == ("familie", "active")
    # not ours / unknown workspace
    other = _sub_obj(ws, sid="sub_x", meta=False)
    assert _stripe_event(client, {"id": "evt_x", "type": "customer.subscription.created", "data": {"object": other}})["outcome"] == "ignored"
    bad = _sub_obj(ws, sid="sub_y")
    bad["metadata"]["workspace_id"] = "00000000-0000-0000-0000-000000000000"
    assert _stripe_event(client, {"id": "evt_y", "type": "customer.subscription.created", "data": {"object": bad}})["outcome"] == "unmatched"


def test_webhook_for_an_account_without_a_row(api, client, pv, db, monkeypatch):
    tok = pv.account("mette@testmail.dk")
    ws = pv.ws(tok)
    db.query(PrivateSubscription).filter_by(workspace_id=ws).delete()
    db.commit()
    _stripe_env(monkeypatch)
    ev = {"id": "evt_norow", "type": "customer.subscription.created", "data": {"object": _sub_obj(ws, plan="familie")}}
    assert _stripe_event(client, ev)["outcome"] == "applied"
    s = pv.subscription(tok)
    assert (s["status"], s["plan"], s["calls_quota"]) == ("active", "familie", 25)


def test_checkout_completed_and_session_sync(api, client, pv, db, monkeypatch):
    tok = pv.account("mette@testmail.dk", trial=False)  # no running subscription yet (PC-SUB-07)
    ws = pv.ws(tok)
    _stripe_env(monkeypatch)
    meta = {"kind": "privat_subscription", "workspace_id": str(ws), "plan": "basis", "interval": "year"}
    session = {"id": "cs_sub_9", "object": "checkout.session", "mode": "subscription", "subscription": "sub_9",
               "customer": "cus_9", "metadata": meta, "status": "complete"}
    # the subscription object itself carries no metadata here: the session's is the fallback
    fetched = []

    def fake_request(m, p, d=None, **k):
        fetched.append((m, p))
        if p == "/subscriptions/sub_9":
            return _sub_obj(ws, sid="sub_9", meta=False, customer="cus_9", interval="year")
        if p == "/checkout/sessions/cs_sub_9":
            return session
        raise AssertionError(p)

    monkeypatch.setattr(stripe_api, "request", fake_request)
    ev = {"id": "evt_cs_9", "type": "checkout.session.completed", "data": {"object": session}}
    assert _stripe_event(client, ev)["outcome"] == "applied"
    assert fetched == [("GET", "/subscriptions/sub_9")]
    row = db.get(PrivateSubscription, ws)
    assert (row.status, row.plan, row.interval, row.stripe_customer_id) == ("active", "basis", "year", "cus_9")
    # back from Checkout: GET /privat/subscription?session_id= reads the session from Stripe first
    s = api.get(tok, "/privat/subscription?session_id=cs_sub_9").json()
    assert s["status"] == "active" and s["plan"] == "basis" and fetched[-2:] == [("GET", "/checkout/sessions/cs_sub_9"),
                                                                                ("GET", "/subscriptions/sub_9")]
    # an open session (declined card / abandoned checkout) is never mirrored – only a complete one (QA batch 5)
    from app.modules.privat import subscriptions as subs

    n = len(fetched)
    session["status"] = "open"
    assert subs.sync_from_session(db, type("C", (), {"ws_id": ws})(), "cs_sub_9") == "ignored"
    assert fetched[n:] == [("GET", "/checkout/sessions/cs_sub_9")]  # the subscription is not even fetched
    session["status"] = "complete"
    # someone else's session is refused
    ole = pv.account("ole@testmail.dk", "Ole Berg")
    assert api.get(ole, "/privat/subscription?session_id=cs_sub_9").status_code == 404
    assert api.get(tok, "/privat/subscription?session_id=nonsense").status_code == 422
    # a credit pack opened before the switch (2026-11-11) and paid now is still handled by payments.py, not here:
    # it adds what was paid for it (29 kr. = 10 credits at 2,90 kr.)
    pack = {"id": "cs_pack", "object": "checkout.session", "mode": "payment", "payment_status": "paid", "amount_total": 2900,
            "metadata": {"workspace_id": str(ws), "kind": "privat_credits", "credits": "10"}}
    assert _stripe_event(client, {"id": "evt_pack", "type": "checkout.session.completed", "data": {"object": pack}})["outcome"] == "applied"
    assert pv.me(tok)["balance_minor"] == 1000 + 2900


def test_portal(api, pv, monkeypatch):
    tok = pv.account("mette@testmail.dk", trial=False)  # no Stripe customer yet
    r = api.post(tok, "/privat/subscription/portal")
    assert r.status_code == 501 and r.json()["code"] == "not_configured"  # no Stripe
    _stripe_env(monkeypatch)
    r = api.post(tok, "/privat/subscription/portal")
    assert r.status_code == 501 and r.json()["code"] == "not_configured"  # Stripe, but no customer yet
    pv.set_plan(tok, "plus")
    sent = []
    monkeypatch.setattr(stripe_api, "request", lambda m, p, d=None, **k: sent.append((m, p, d)) or
                        {"url": "https://billing.stripe.com/p/session/x"})
    assert api.post(tok, "/privat/subscription/portal").json() == {"url": "https://billing.stripe.com/p/session/x"}
    assert sent == [("POST", "/billing_portal/sessions", {"customer": "cus_test", "return_url": "http://frontend.test/privat/konto"})]


# --------------------------------------------------------------------------- one subscription per account

def _two_checkouts_completed(client, pv, ws, monkeypatch, *, status: str, invoice: dict | None = None):
    """Two Checkouts opened before either completed (two tabs …): both sessions complete at Stripe."""
    subs = {"sub_a": _sub_obj(ws, sid="sub_a", status=status, plan="basis"),
            "sub_b": _sub_obj(ws, sid="sub_b", status=status, plan="plus")}
    for sub in subs.values():
        sub["latest_invoice"] = f"in_{sub['id']}"
    sent = []

    def fake(m, p, d=None, **k):
        sent.append((m, p, d, k.get("idempotency_key")))
        if p.startswith("/subscriptions/"):
            sub = subs[p.rsplit("/", 1)[1]]
            if m == "DELETE":
                sub["status"] = "canceled"
            return sub
        if m == "GET" and p.startswith("/invoices/"):
            return invoice or {}
        if (m, p) == ("POST", "/refunds"):
            return {"id": "re_1", "status": "succeeded"}
        raise AssertionError((m, p))

    monkeypatch.setattr(stripe_api, "request", fake)
    outs = []
    for sid in ("sub_a", "sub_b"):
        meta = {"kind": "privat_subscription", "workspace_id": str(ws), "plan": subs[sid]["metadata"]["plan"],
                "interval": "month"}
        session = {"id": f"cs_{sid}", "object": "checkout.session", "mode": "subscription", "subscription": sid,
                   "customer": "cus_1", "metadata": meta, "status": "complete"}
        outs.append(_stripe_event(client, {"id": f"evt_{sid}", "type": "checkout.session.completed",
                                           "data": {"object": session}})["outcome"])
    return outs, subs, sent


def test_two_open_checkouts_leave_one_live_subscription(api, client, pv, db, monkeypatch):
    """F-PBQ-01 (S0): the second completed Checkout is cancelled at Stripe at once (in its trial: nothing charged, no
    refund) and the account keeps the first – never two subscriptions billing the same card."""
    tok = pv.account("mette@testmail.dk", trial=False)
    ws = pv.ws(tok)
    _stripe_env(monkeypatch)
    outs, subs, sent = _two_checkouts_completed(client, pv, ws, monkeypatch, status="trialing")
    assert outs == ["applied", "dup_canceled"]
    assert [s["id"] for s in subs.values() if s["status"] in ("trialing", "active", "past_due")] == ["sub_a"]
    assert ("DELETE", "/subscriptions/sub_b") in [(m, p) for m, p, _d, _k in sent]
    assert not [x for x in sent if x[1] in ("/refunds", "/credit_notes") or x[1].startswith("/invoices/")]
    db.expire_all()
    row = db.get(PrivateSubscription, ws)
    assert (row.stripe_subscription_id, row.plan, row.status) == ("sub_a", "basis", "trial")
    # the cancelled duplicate's own deletion event never touches the account
    gone = subs["sub_b"] | {"ended_at": int(WED_10.timestamp())}
    assert _stripe_event(client, {"id": "evt_gone", "type": "customer.subscription.deleted",
                                  "data": {"object": gone}})["outcome"] == "ignored"
    assert pv.subscription(tok)["entitled"] is True


def test_paid_duplicate_without_trial_is_refunded(api, client, pv, db, monkeypatch):
    """F-PBQ-09 (S0): without a trial the duplicate's first invoice is already paid – it is refunded in full, once."""
    tok = pv.account("mette@testmail.dk", trial=False)
    ws = pv.ws(tok)
    _stripe_env(monkeypatch)
    inv = {"id": "in_sub_b", "status": "paid", "amount_paid": 9900, "payment_intent": "pi_dup"}
    outs, subs, sent = _two_checkouts_completed(client, pv, ws, monkeypatch, status="active", invoice=inv)
    assert outs == ["applied", "dup_canceled"] and subs["sub_b"]["status"] == "canceled"
    refunds = [(d, k) for m, p, d, k in sent if (m, p) == ("POST", "/refunds")]
    assert len(refunds) == 1
    body, key = refunds[0]
    assert body["payment_intent"] == "pi_dup" and body["metadata"]["subscription"] == "sub_b"
    assert key == "privat-dup-refund-sub_b"
    assert ("GET", "/invoices/in_sub_b") in [(m, p) for m, p, _d, _k in sent]


def test_unpaid_duplicate_is_cancelled_but_not_refunded(api, client, pv, db, monkeypatch):
    tok = pv.account("mette@testmail.dk", trial=False)
    ws = pv.ws(tok)
    _stripe_env(monkeypatch)
    inv = {"id": "in_sub_b", "status": "open", "amount_paid": 0, "payment_intent": "pi_dup"}
    outs, subs, sent = _two_checkouts_completed(client, pv, ws, monkeypatch, status="active", invoice=inv)
    assert outs == ["applied", "dup_canceled"] and subs["sub_b"]["status"] == "canceled"
    assert not [x for x in sent if x[1] == "/refunds"]


def test_topup_checkout_takes_no_discount_codes(api, client, pv, db, monkeypatch):
    """F-PBQ-03 (S0): a Privat code paid a credit pack below its price and the webhook (rightly) added nothing – the
    Opkaldssaldo top-up's Checkout shows no code field, so the amount paid and the amount added always match."""
    _stripe_env(monkeypatch)
    sent = _fake_checkout(monkeypatch)
    tok = pv.account("hans@testmail.dk", trial=False)
    for body in ({}, {"locale": "de"}, {"locale": "sv"}):
        assert api.post(tok, "/privat/balance/checkout", body).status_code == 200
        d = _sessions(sent)[-1]
        assert d["mode"] == "payment" and "allow_promotion_codes" not in d and "discounts" not in d


def test_no_second_checkout_while_a_subscription_runs(api, pv, db, monkeypatch):
    """PC-SUB-07 / F-PBQ-01: with a running Stripe subscription (here the card trial) a new Checkout would start a
    second subscription. 409 subscription_exists → the web sends the customer to the Billing Portal instead."""
    tok = pv.account("mette@testmail.dk")  # trial via Checkout: a Stripe subscription exists
    _stripe_env(monkeypatch)
    sent = _fake_checkout(monkeypatch)
    r = api.post(tok, "/privat/subscription/checkout", {"plan": "familie", "interval": "year"})
    assert r.status_code == 409 and r.json()["code"] == "subscription_exists" and r.json()["portal"] is True
    assert _sessions(sent) == []
    pv.set_plan(tok, "plus")  # active
    assert api.post(tok, "/privat/subscription/checkout", {"plan": "basis", "interval": "month"}).status_code == 409
    row = db.get(PrivateSubscription, pv.ws(tok))
    row.status, row.current_period_end = "canceled", None  # ended: a new subscription is allowed again
    db.commit()
    assert api.post(tok, "/privat/subscription/checkout", {"plan": "basis", "interval": "month"}).status_code == 200


def test_one_trial_per_card(api, client, pv, db, monkeypatch):
    """F-PBQ-02 (Fürster 2026-11-10): ÉT KORT = ÉN PRØVEPERIODE. A second account whose card (Stripe fingerprint) has
    already started a Privat trial gets no trial: the trial is ended at once (Stripe charges now), the account is told,
    and only the fingerprint – never card data – is kept. The Checkout page says so before the card is given."""
    from app.models import PrivateTrialCard

    _stripe_env(monkeypatch)
    trial_end = int((WED_10 + timedelta(days=14)).timestamp())
    calls = []

    def fake(m, p, d=None, **k):
        calls.append((m, p, d))
        if p.startswith("/payment_methods/"):
            return {"id": p.rsplit("/", 1)[1], "card": {"fingerprint": "fp_SAMECARD", "last4": "4242"}}
        if m == "POST" and p.startswith("/subscriptions/"):
            sid = p.rsplit("/", 1)[1]
            return _sub_obj(ws_of[sid], sid=sid, status="active") | {"default_payment_method": "pm_x"}
        raise AssertionError((m, p))

    monkeypatch.setattr(stripe_api, "request", fake)
    ws_of = {}
    for i, email in enumerate(("kort-a@testmail.dk", "kort-b@testmail.dk")):
        tok = pv.account(email, trial=False)
        ws = pv.ws(tok)
        sid = f"sub_card_{i}"
        ws_of[sid] = ws
        sub = _sub_obj(ws, sid=sid, status="trialing") | {"trial_end": trial_end, "default_payment_method": f"pm_{i}"}
        assert _stripe_event(client, {"id": f"evt_card_{i}", "type": "customer.subscription.created",
                                      "data": {"object": sub}})["outcome"] == "applied"
    db.expire_all()
    first, second = (db.get(PrivateSubscription, ws_of[f"sub_card_{i}"]) for i in range(2))
    assert first.status == "trial"  # the card's first trial
    assert second.status == "active"  # same card: no second trial
    assert [(m, p, d) for m, p, d in calls if m == "POST"] == [
        ("POST", "/subscriptions/sub_card_1", {"trial_end": "now", "proration_behavior": "none"})]
    rows = db.query(PrivateTrialCard).all()
    assert [(r.fingerprint, r.workspace_id) for r in rows] == [("fp_SAMECARD", ws_of["sub_card_0"])]
    tok_b = pv.account("kort-c@testmail.dk", trial=False)
    sent = _fake_checkout(monkeypatch)
    api.post(tok_b, "/privat/subscription/checkout", {"plan": "plus", "interval": "month"})
    assert "Én prøveperiode pr. kort" in _sessions(sent)[0]["custom_text"]["submit"]["message"]


def test_privat_sends_its_own_billing_mails(api, client, pv, db, monkeypatch):
    """F-PBQ-08 (Fürster 2026-11-10): Privat sends Dialogbot's own branded mails (Privat orange): trial ends in 3 days,
    receipt, failed payment (dunning) and refund confirmed – once per Stripe object, in the user's language."""
    from app.models import OutboxEvent

    _stripe_env(monkeypatch)
    tok = pv.account("mails@testmail.dk")  # in the trial (card at Stripe, customer cus_test)
    ws = pv.ws(tok)
    row = db.get(PrivateSubscription, ws)
    sub = _sub_obj(ws, sid=row.stripe_subscription_id, status="trialing", customer="cus_test") | {
        "trial_end": int((WED_10 + timedelta(days=3)).timestamp())}
    events = [("customer.subscription.trial_will_end", sub),
              ("invoice.paid", {"id": "in_p1", "customer": "cus_test", "amount_paid": 9900, "currency": "dkk"}),
              ("invoice.paid", {"id": "in_p0", "customer": "cus_test", "amount_paid": 0, "currency": "dkk"}),
              ("invoice.payment_failed", {"id": "in_p2", "customer": "cus_test", "amount_due": 9900, "currency": "dkk",
                                          "attempt_count": 1}),
              ("charge.refunded", {"id": "ch_1", "customer": "cus_test", "amount_refunded": 9900, "currency": "dkk"})]
    for i, (kind, obj) in enumerate(events):
        _stripe_event(client, {"id": f"evt_mail_{i}", "type": kind, "data": {"object": obj}})
    _stripe_event(client, {"id": "evt_mail_again", "type": "invoice.paid", "data": {"object": events[1][1]}})  # replay
    db.expire_all()
    mails = [e.payload for e in db.query(OutboxEvent).filter_by(event_type="email.branded")
             if e.dedupe_key.startswith("billing-mail:")]
    subjects = [m["email"]["subject"] for m in mails]
    assert subjects == ["Din prøveperiode slutter om 3 dage", "Kvittering: 99 kr. er betalt",
                        "Betalingen på 99 kr. gik ikke igennem", "Refusion: 99 kr. er sendt tilbage"], subjects
    assert {m["to_email"] for m in mails} == {"mails@testmail.dk"} and {m["email"]["audience"] for m in mails} == {"privat"}
    from app.modules.integrations import email_templates as tpl

    html = tpl.from_payload(mails[1]).html()
    assert "#C4461A" in html and "Dialogbot Privat" in html and "/privat/konto" in html


# --------------------------------------------------------------------------- «Ring for mig» stops without a plan (2026-11-11)

def test_ring_for_mig_stops_without_a_plan_even_with_a_balance(api, pv, db, monkeypatch):
    """Decision Fürster 2026-11-11: the Opkaldssaldo never pays for «Ring for mig» without a plan. Approve, retry and new
    proposals answer 409 needs_plan with a CTA to Konto; nothing is reserved and nothing is dialled, balance or not."""
    called = []
    monkeypatch.setattr(campaigns, "create_call", lambda p: called.append(p) or {"id": "x"})
    tok = pv.account("mette@testmail.dk")
    pv.verify_phone(tok)
    tid = _propose(pv, tok)  # proposed during the trial
    assert pv.task(tok, tid).json()["usage_text"].startswith("Opkald 1 af")
    pv.expire_trial(tok)
    db.add(CreditLedger(workspace_id=pv.ws(tok), kind="purchase", amount=5000, source_ref="test:buy", text="t"))
    db.commit()
    assert pv.me(tok)["balance_minor"] >= 1750
    r = api.post(tok, f"/privat/calls/{tid}/approve", {"share_phone": False})
    assert r.status_code == 409 and r.json()["code"] == "needs_plan", r.text
    assert r.json()["cta"] == {"label": "Kræver en plan", "href": "/privat/konto"}
    assert called == [] and pv.me(tok)["held_minor"] == 0
    c = db.query(PrivateCall).filter_by(task_id=tid).one()
    assert c.status == "proposed" and c.paid_via is None
    assert not db.query(CreditLedger).filter(CreditLedger.kind == "reserve").count()
    r = api.post(tok, f"/privat/calls/{tid}/retry")
    assert r.status_code == 409 and r.json()["code"] == "needs_plan"
    # the app stops like every plan app (data kept) – the shop card says «Kræver plan»
    card = next(a for a in api.get(tok, "/privat/addons").json() if a["key"] == "ring-for-mig")
    assert card["needs_plan"] is True
    # with a plan again it works
    pv.set_plan(tok, "basis")
    t = api.post(tok, f"/privat/calls/{tid}/approve", {"share_phone": False}).json()
    assert t["status"] == "in_progress" and t["usage_text"] == "Opkald 1 af 3 i Basis" and len(called) == 1


def test_extra_calls_from_the_balance_only_on_top_of_a_plan(api, pv, db, monkeypatch):
    """A plan whose month's calls are used: an extra call reserves its maximum, 17,50\u00a0kr., on the Opkaldssaldo."""
    called = []
    monkeypatch.setattr(campaigns, "create_call", lambda p: called.append(p) or {"id": "x2"})
    tok = pv.account("mette@testmail.dk")
    pv.verify_phone(tok)
    pv.set_plan(tok, "basis")
    pv.use_up_calls(tok)
    pv.top_up(tok, 1000)
    tid = _propose(pv, tok)
    assert pv.task(tok, tid).json()["usage_text"] == "Ekstra opkald: højst 17,50\u00a0kr., når du godkender"
    t = api.post(tok, f"/privat/calls/{tid}/approve", {"share_phone": False}).json()
    assert t["usage_text"] == "Ekstra opkald · højst 17,50\u00a0kr. reserveret" and len(called) == 1
    assert db.query(PrivateCall).filter_by(task_id=tid).one().paid_via == "balance"


def test_a_planned_extra_call_is_not_made_when_the_plan_lapses(api, pv, db, monkeypatch):
    """A call approved «ved næste åbningstid» as an extra call: the plan ends before it is due – it is not dialled and
    the whole reservation comes back (before: only plan-paid calls were stopped)."""
    from app.modules.privat import calls

    called = []
    monkeypatch.setattr(campaigns, "create_call", lambda p: called.append(p) or {"id": "x3"})
    tok = pv.account("mette@testmail.dk")
    pv.verify_phone(tok)
    pv.set_plan(tok, "basis")
    pv.use_up_calls(tok)
    pv.top_up(tok, 1000)
    pv.clock.at = datetime(2026, 11, 4, 17, 30, tzinfo=UTC)  # 18:30: outside calling hours
    tid = _propose(pv, tok)
    t = api.post(tok, f"/privat/calls/{tid}/approve", {"share_phone": False, "at_next_open": True}).json()
    assert t["status"] == "planned" and pv.me(tok)["held_minor"] == 1750
    c = db.query(PrivateCall).filter_by(task_id=tid).one()
    sub = db.get(PrivateSubscription, pv.ws(tok))
    sub.status = "canceled"
    sub.current_period_end = pv.clock() - timedelta(minutes=1)
    db.commit()
    pv.clock.at = c.scheduled_for + timedelta(minutes=1)

    class Ev:
        payload = {"private_call_id": str(c.id), "at": c.scheduled_for.isoformat()}

    calls.handle_call_due(db, Ev())
    db.expire_all()
    assert called == [] and db.get(PrivateCall, c.id).status == "failed"
    assert pv.me(tok)["held_minor"] == 0 and pv.me(tok)["balance_minor"] == 2000
    assert "abonnement" in pv.task(tok, tid).json()["events"][-1]["text"]

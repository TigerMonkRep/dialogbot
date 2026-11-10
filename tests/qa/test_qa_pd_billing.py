"""QA Privat-dybderunde fase 2 – billing-qa (prefix PBQ). 29 scenarier fra qa/privat/scenarios.csv (owner=billing-qa).

Every expected amount below is written down INDEPENDENTLY (the EXPECTED_* tables) from the price rules / the brief –
never read from app.modules.billing.markets – and then compared with what the API returns, what the web catalogue
(web/src/lib/prices.json) says and what is sent to (fake) Stripe.

Stripe: only the in-process fake (monkeypatched app.modules.billing.stripe.request). No network, no live objects.
Tests that assert the CORRECT behaviour of a confirmed defect fail until it is fixed (finding id in the docstring);
status-quo documentation of a needs-decision is marked xfail(strict=True) with the finding id.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import re
import time
import uuid
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from app.config import get_settings
from app.models import CreditLedger, PrivateCall, PrivateSubscription, PrivateTask
from app.models.domain import EmailDelivery, OutboxEvent
from app.modules.billing import stripe as stripe_api
from app.modules.campaigns import service as campaigns
from app.modules.privat import addons, bills, expenses, subscriptions
from tests.privat_fixtures import WED_10

ROOT = Path(__file__).resolve().parents[2]
SECRET = "whsec_qa_pbq"

# ----------------------------------------------------------------------------------------------- independent tables
# Privat plan prices INCL. 25 % moms, minor units (brief + docs/pricing.md; the Stripe test catalogue is not reachable
# from the QA sandbox, so the checkout line sent to Stripe is the "catalogue" side compared here).
EXPECTED_PLANS = {  # currency: plan: (monthly, yearly per month, yearly total)
    "DKK": {"basis": (4900, 3900, 46800), "plus": (9900, 7900, 94800), "familie": (16900, 13500, 162000)},
    "SEK": {"basis": (6900, 5500, 66000), "plus": (14900, 11900, 142800), "familie": (24900, 19900, 238800)},
    "NOK": {"basis": (7900, 6300, 75600), "plus": (15900, 12700, 152400), "familie": (26900, 21500, 258000)},
    "EUR": {"basis": (649, 519, 6228), "plus": (1349, 1079, 12948), "familie": (2249, 1799, 21588)},
}
EXPECTED_QUOTA = {"basis": (3, 1, False), "plus": (10, 1, True), "familie": (25, 5, True)}  # calls, people, all apps
EXPECTED_PACK = {"DKK": 2900, "SEK": 4500, "NOK": 4500, "EUR": 399}  # 10 credits incl. moms
# The 8 Privat languages → (currency, Stripe locale, inclusive tax rate id on the line in the default «danish» mode)
EXPECTED_LOCALE = {"da": ("DKK", "da", ["txr_dk_vat_2500_incl"]), "en": ("EUR", "en", ["txr_dk_vat_2500_incl"]),
                   "de": ("EUR", "de", ["txr_dk_vat_2500_incl"]), "es": ("EUR", "es", ["txr_dk_vat_2500_incl"]),
                   "fr": ("EUR", "fr", ["txr_dk_vat_2500_incl"]), "it": ("EUR", "it", ["txr_dk_vat_2500_incl"]),
                   "no": ("NOK", "nb", None), "sv": ("SEK", "sv", ["txr_dk_vat_2500_incl"])}


def vat_inclusive_split(gross: int, rate_bp: int = 2500) -> tuple[int, int]:
    """(net, tax) of an inclusive price the way Stripe rounds it: tax = round-half-up(gross × r / (1 + r))."""
    tax = (gross * rate_bp * 2 + (10000 + rate_bp)) // (2 * (10000 + rate_bp))
    return gross - tax, tax


# ----------------------------------------------------------------------------------------------- fake Stripe
class FakeStripe:
    """Stateful Checkout + subscriptions, like tests/qa/qa_privat_stack.py but in-process."""

    def __init__(self):
        self.sessions: dict[str, dict] = {}
        self.subs: dict[str, dict] = {}
        self.calls: list[tuple[str, str, dict | None]] = []

    def __call__(self, m, p, d=None, **_k):
        self.calls.append((m, p, d))
        if p == "/tax_rates":
            if m == "GET":
                return {"data": []}
            return {"id": f"txr_{d['metadata']['dialogbot']}"}
        if (m, p) == ("POST", "/checkout/sessions"):
            sid = f"cs_test_pbq_{len(self.sessions) + 1}"
            self.sessions[sid] = {"id": sid, "object": "checkout.session", "mode": d["mode"], "status": "open",
                                  "payment_status": "unpaid", "subscription": None, "metadata": d.get("metadata") or {},
                                  "customer": d.get("customer"), "_payload": d}
            return {"id": sid, "url": f"https://checkout.stripe.test/{sid}"}
        if m == "GET" and p.startswith("/checkout/sessions/"):
            s = self.sessions.get(p.rsplit("/", 1)[1])
            if s is None:
                raise stripe_api.StripeFailed("No such checkout.session")
            return {k: v for k, v in s.items() if k != "_payload"}
        if m == "GET" and p.startswith("/subscriptions/"):
            return self.subs[p.rsplit("/", 1)[1]]
        if m in ("DELETE", "POST") and p.startswith("/subscriptions/"):
            sub = self.subs[p.split("/")[2]]
            if m == "DELETE":
                sub["status"] = "canceled"
            return sub
        if (m, p) in (("POST", "/refunds"), ("POST", "/credit_notes")):
            return {"id": f"re_pbq_{len(self.calls)}", "status": "succeeded", **(d or {})}
        if m == "GET" and p.startswith("/invoices"):
            return {"id": "in_pbq", "status": "paid", "amount_paid": 9900, "payment_intent": "pi_pbq_dup"}
        if (m, p) == ("POST", "/billing_portal/sessions"):
            return {"url": "https://billing.stripe.test/p/session"}
        raise AssertionError(f"unexpected Stripe call {m} {p}")

    def payload(self, n: int = -1) -> dict:
        return list(self.sessions.values())[n]["_payload"]

    def complete(self, sid: str, now: datetime) -> dict:
        s = self.sessions[sid]
        d = s["_payload"]
        sd = d.get("subscription_data") or {}
        trial = sd.get("trial_period_days")
        line = d["line_items"][0]
        pd = line.get("price_data") or {}
        interval = (pd.get("recurring") or {}).get("interval") or sd["metadata"]["interval"]
        cur = pd.get("currency") or "dkk"
        end = now + timedelta(days=trial) if trial else now + timedelta(days=30 if interval == "month" else 365)
        cust = d.get("customer") or f"cus_{sid}"  # Stripe makes a NEW customer for customer_email
        sub_id = f"sub_{sid}"
        self.subs[sub_id] = {"id": sub_id, "object": "subscription", "status": "trialing" if trial else "active",
                             "customer": cust, "cancel_at_period_end": False, "currency": cur,
                             "trial_end": int(end.timestamp()) if trial else None, "metadata": sd["metadata"],
                             "items": {"data": [{"current_period_end": int(end.timestamp()),
                                                 "price": {"id": line.get("price"), "recurring": {"interval": interval}}}]}}
        s.update(status="complete", subscription=sub_id, customer=cust,
                 payment_status="no_payment_required" if trial else "paid")
        return {k: v for k, v in s.items() if k != "_payload"}

    def live_subs(self, ws) -> list[dict]:
        return [x for x in self.subs.values() if x["metadata"].get("workspace_id") == str(ws)
                and x["status"] in ("trialing", "active", "past_due")]


@pytest.fixture
def stripe(monkeypatch):
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_pbq")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", SECRET)
    get_settings.cache_clear()
    fake = FakeStripe()
    monkeypatch.setattr(stripe_api, "request", fake)
    yield fake
    get_settings.cache_clear()


def _event(client, event: dict) -> dict:
    body = json.dumps(event).encode()
    ts = int(time.time())
    sig = hmac.new(SECRET.encode(), f"{ts}.".encode() + body, hashlib.sha256).hexdigest()
    r = client.post("/api/v1/webhooks/stripe", content=body, headers={"stripe-signature": f"t={ts},v1={sig}"})
    assert r.status_code == 200, r.text
    return r.json()


def _evt(kind: str, obj: dict) -> dict:
    return {"id": f"evt_{uuid.uuid4().hex[:14]}", "type": kind, "data": {"object": obj}}


def _checkout(api, tok, **body) -> dict:
    r = api.post(tok, "/privat/subscription/checkout", {"plan": "plus", "interval": "month", **body})
    return {"status": r.status_code, "json": r.json()}


def _complete_via_webhook(client, stripe, pv) -> str:
    sid = list(stripe.sessions)[-1]
    obj = stripe.complete(sid, pv.clock())
    assert _event(client, _evt("checkout.session.completed", obj))["outcome"] == "applied"
    return obj["subscription"]


def _emails_to(db, addr: str) -> list[str]:
    db.expire_all()
    subj = [e.subject for e in db.query(EmailDelivery).filter(EmailDelivery.to_email == addr)]
    for ev in db.query(OutboxEvent).all():
        p = ev.payload or {}
        if (p.get("to_email") or (p.get("email") or {}).get("to_email")) == addr:
            subj.append(str((p.get("email") or {}).get("subject") or ev.event_type))
    return [x for x in subj if "Bekræft din e-mail" not in x and x != "email.verify_address"]


PLAN_APPS = sorted(k for k, a in addons.CATALOG.items() if a.included_in and a.live_status != "coming_soon")


# =============================================================================================== SUB: checkout + trial

def test_pc_sub_01_checkout_collects_card_address_phone_and_gives_no_rights_before_complete(api, pv, stripe, db):
    tok = pv.account("pbq01@testmail.dk", trial=False)
    assert pv.subscription(tok)["status"] == "none"
    r = _checkout(api, tok)
    assert r["status"] == 200 and r["json"]["url"].startswith("https://checkout.stripe.test/cs_test_pbq_")
    d = stripe.payload()
    assert d["mode"] == "subscription" and d["payment_method_collection"] == "always"
    assert d["billing_address_collection"] == "required" and d["phone_number_collection"] == {"enabled": True}
    assert d["subscription_data"]["trial_period_days"] == 14 and "trial_end" not in d["subscription_data"]
    assert d["customer_email"] == "pbq01@testmail.dk"
    assert d["metadata"] == {"kind": "privat_subscription", "workspace_id": str(pv.ws(tok)), "plan": "plus",
                             "interval": "month", "currency": "DKK"}
    assert len(stripe.sessions) == 1
    # before the session is complete: nothing
    s = api.get(tok, f"/privat/subscription?session_id={list(stripe.sessions)[0]}").json()
    assert (s["status"], s["entitled"], s["calls_quota"]) == ("none", False, 0)
    assert api.post(tok, "/privat/addons/kalender/enable").json()["code"] == "needs_plan"


@pytest.mark.parametrize("why", ["declined_0002", "insufficient_9995", "3ds_failed_3155"])
def test_pc_sub_03_04_failed_card_leaves_session_open_no_rights_no_mail(api, pv, stripe, db, why):
    tok = pv.account(f"pbq04{why[:4]}@testmail.dk", trial=False)
    _checkout(api, tok)
    sid = list(stripe.sessions)[-1]  # the fake hosted page refuses the card → session stays open (Stripe ≥ 2025-03-31)
    s = api.get(tok, f"/privat/subscription?session_id={sid}").json()
    assert (s["status"], s["plan"], s["entitled"]) == ("none", "none", False)
    assert db.get(PrivateSubscription, pv.ws(tok)).status == "none"
    for key in ("kalender", "foedselsdage", "regninger"):
        r = api.post(tok, f"/privat/addons/{key}/enable")
        assert r.status_code == 409 and r.json()["code"] == "needs_plan"
    assert not [x for x in _emails_to(db, f"pbq04{why[:4]}@testmail.dk") if "Plus" in x or "elkommen" in x]


def test_pc_sub_05_second_checkout_on_same_account_never_gets_another_trial(api, client, pv, stripe, db):
    tok = pv.account("pbq05@testmail.dk", trial=False)
    ws = pv.ws(tok)
    _checkout(api, tok)
    sub_id = _complete_via_webhook(client, stripe, pv)
    assert pv.subscription(tok)["status"] == "trial"
    # cancels in the trial, trial runs out
    sub = stripe.subs[sub_id] | {"status": "canceled", "cancel_at_period_end": True,
                                 "ended_at": stripe.subs[sub_id]["trial_end"]}
    assert _event(client, _evt("customer.subscription.deleted", sub))["outcome"] == "applied"
    pv.clock.at = WED_10 + timedelta(days=15)
    assert pv.subscription(tok)["entitled"] is False
    _checkout(api, tok)
    sd = stripe.payload()["subscription_data"]
    assert "trial_period_days" not in sd and "trial_end" not in sd  # the card is charged at checkout
    assert stripe.payload()["customer"] == f"cus_{list(stripe.sessions)[0]}"  # same Stripe customer, no new one
    # an expired card-less local trial row (old accounts) also gets no new trial
    tok2 = pv.account("pbq05b@testmail.dk", trial=False)
    with db.begin_nested():
        row = db.get(PrivateSubscription, pv.ws(tok2))
        row.status, row.trial_ends_at = "trial", pv.clock() - timedelta(days=1)
    db.commit()
    _checkout(api, tok2)
    assert "trial_period_days" not in stripe.payload()["subscription_data"]
    assert ws  # silence


@pytest.mark.xfail(strict=True, reason="F-PBQ-02-PC-SUB-06: needs-decision – a new e-mail with the same card gets a new "
                                       "14-day trial (one trial per ACCOUNT, no card-fingerprint check)")
def test_pc_sub_06_new_email_same_card_is_refused_a_second_trial(api, client, pv, stripe):
    first = pv.account("teen@testmail.dk", trial=False)
    _checkout(api, first)
    _complete_via_webhook(client, stripe, pv)
    second = pv.account("teen+2@testmail.dk", trial=False)  # same person, same test card 4242
    _checkout(api, second)
    assert "trial_period_days" not in stripe.payload()["subscription_data"]


def test_pc_sub_07_active_customer_cannot_start_a_second_subscription(api, client, pv, stripe):
    """F-PBQ-01-PC-SUB-07 (S0): POST /subscription/checkout for an account that already has a live Stripe subscription
    must not open a second Checkout (409 / portal) – otherwise Stripe bills two subscriptions."""
    tok = pv.account("pbq07@testmail.dk", trial=False)
    _checkout(api, tok, plan="basis")
    _complete_via_webhook(client, stripe, pv)
    assert pv.subscription(tok)["status"] == "trial"
    n = len(stripe.sessions)
    r = _checkout(api, tok, plan="plus")  # «Skift plan» in Konto, PlanSheet in Butikken, or the API
    assert r["status"] == 409, f"second Checkout opened for a live subscriber: {r}"
    assert len(stripe.sessions) == n


def test_pc_sub_07b_two_open_checkouts_completed_leave_two_billing_subscriptions(api, client, pv, stripe, db):
    """F-PBQ-01-PC-SUB-07 (S0): the subscription_exists guard (21:12) only sees a subscription that has ALREADY arrived.
    Two Checkouts opened before either completes (two tabs, the PlanSheet in Butikken + Konto, a back-button retry,
    the e-mail link) both carry trial_period_days=14 and both complete: Stripe now runs two subscriptions on the same
    card (Basis 49 + Plus 99 = 148 kr./md. after the trial) while the row only knows the last one. When the customer
    cancels the one the account shows, the other keeps charging and the account has no rights."""
    tok = pv.account("pbq07b@testmail.dk", trial=False)
    ws = pv.ws(tok)
    assert _checkout(api, tok, plan="basis")["status"] == 200
    s_basis = list(stripe.sessions)[-1]
    assert _checkout(api, tok, plan="plus")["status"] == 200  # second tab – nothing has completed yet
    s_plus = list(stripe.sessions)[-1]
    assert all(stripe.sessions[x]["_payload"]["subscription_data"].get("trial_period_days") == 14 for x in (s_basis, s_plus))
    for sid in (s_basis, s_plus):
        obj = stripe.complete(sid, pv.clock())
        _event(client, _evt("checkout.session.completed", obj))
    live = stripe.live_subs(ws)
    billed = sum(EXPECTED_PLANS["DKK"][x["metadata"]["plan"]][0] for x in live)
    db.expire_all()
    shown = db.get(PrivateSubscription, ws).stripe_subscription_id
    # the customer cancels the subscription the account shows
    stripe.subs[shown]["status"] = "canceled"
    _event(client, _evt("customer.subscription.deleted", stripe.subs[shown] | {"ended_at": int(pv.clock().timestamp())}))
    still = [(x["id"], x["metadata"]["plan"]) for x in stripe.live_subs(ws)]
    ent = pv.subscription(tok)["entitled"]
    assert len(live) <= 1, (f"{len(live)} live Stripe subscriptions after two completed checkouts, {billed} øre/md. after "
                            f"the trial; account shows {shown}; after cancelling it {still} keeps billing, entitled={ent}")


def test_pc_sub_07c_paid_duplicate_without_trial_is_refunded(api, client, pv, stripe, db):
    """F-PBQ-09-PC-SUB-07 (residual of F-PBQ-01): a returning customer (trial used, old subscription over) opens two
    Checkouts; both are paid AT ONCE (no trial). The duplicate is cancelled (DELETE /subscriptions) – but its first
    invoice (here 99 kr.) is already paid and nothing refunds it."""
    tok = pv.account("pbq07c@testmail.dk", trial=False)
    ws = pv.ws(tok)
    _checkout(api, tok, plan="basis")
    old = _complete_via_webhook(client, stripe, pv)
    _event(client, _evt("customer.subscription.deleted", stripe.subs[old] | {"status": "canceled",
                                                                           "ended_at": int(pv.clock().timestamp())}))
    stripe.subs[old]["status"] = "canceled"
    pv.clock.at = WED_10 + timedelta(days=20)
    assert pv.subscription(tok)["entitled"] is False
    assert _checkout(api, tok, plan="basis")["status"] == 200
    a = list(stripe.sessions)[-1]
    assert _checkout(api, tok, plan="plus")["status"] == 200
    b = list(stripe.sessions)[-1]
    assert "trial_period_days" not in stripe.sessions[b]["_payload"]["subscription_data"]
    outs = []
    for sid in (a, b):
        obj = stripe.complete(sid, pv.clock())
        stripe.subs[obj["subscription"]]["latest_invoice"] = f"in_{sid}"
        outs.append(_event(client, _evt("checkout.session.completed", obj))["outcome"])
    paid = sum(EXPECTED_PLANS["DKK"][stripe.sessions[x]["metadata"]["plan"]][0] for x in (a, b))
    live = stripe.live_subs(ws)
    refunds = [c for c in stripe.calls if c[1] in ("/refunds", "/credit_notes")]
    assert len(live) == 1, outs
    assert refunds, (f"customer paid {paid} øre for two first periods; duplicate cancelled ({outs}) but no refund/credit "
                     f"note was requested – {paid - EXPECTED_PLANS['DKK'][live[0]['metadata']['plan']][0]} øre kept")


def test_pc_sub_11_trial_to_active_keeps_rights_replay_and_out_of_order(api, client, pv, stripe, db):
    tok = pv.account("pbq11@testmail.dk", trial=False)
    _checkout(api, tok, plan="familie")
    sub_id = _complete_via_webhook(client, stripe, pv)
    trialing = dict(stripe.subs[sub_id])
    s = pv.subscription(tok)
    assert (s["status"], s["plan"], s["calls_quota"], s["people_limit"], s["trial_days_left"]) == ("trial", "familie", 25, 5, 14)
    pv.clock.at = WED_10 + timedelta(days=14)
    active = trialing | {"status": "active", "trial_end": trialing["trial_end"],
                         "items": {"data": [{"current_period_end": int((WED_10 + timedelta(days=44)).timestamp()),
                                             "price": {"recurring": {"interval": "month"}}}]}}
    ev = _evt("customer.subscription.updated", active)
    assert _event(client, ev)["outcome"] == "applied"
    assert _event(client, ev)["duplicate"] is True  # replay
    s = pv.subscription(tok)
    assert (s["status"], s["plan"], s["entitled"], s["calls_quota"]) == ("active", "familie", True, 25)
    # a late «trialing» after «active» is ignored (regression F-BQ-004)
    assert _event(client, _evt("customer.subscription.updated", trialing))["outcome"] == "ignored"
    assert pv.subscription(tok)["status"] == "active"
    # no own e-mail on the first payment (Privat relies on Stripe's receipts) – documented, see PC-ACC-04
    assert not _emails_to(db, "pbq11@testmail.dk")


def test_pc_sub_12_ent_04_chat_05_expired_local_trial(api, client, pv, db, monkeypatch):
    tok = pv.account("pbq12@testmail.dk")
    pv.verify_phone(tok)
    with db.begin_nested():
        row = db.get(PrivateSubscription, pv.ws(tok))
        row.status, row.trial_ends_at, row.stripe_subscription_id = "trial", WED_10 - timedelta(seconds=1), None
    db.commit()
    s = pv.subscription(tok)
    assert (s["status"], s["plan"], s["entitled"], s["calls_quota"], s["people_limit"]) == ("expired", "none", False, 0, 1)
    # CHAT-05: a new task is a draft waiting for the plan
    out = pv.say(tok, "Lav en indkøbsliste med smør")
    tid = next(m["task_id"] for m in out["messages"] if m["kind"] in ("task", "draft"))
    assert [m["kind"] for m in out["messages"]][-1] == "draft"
    t = db.get(PrivateTask, uuid.UUID(tid))
    assert (t.status, t.paid_by, t.usage_text) == ("draft", "none", "Ikke betalt endnu")
    # ENT-04: a call needs 3 credits (the 3 welcome credits)
    from tests.test_privat_subscription import _approve_plan

    _tid, t2, called = _approve_plan(api, pv, tok, monkeypatch, "call_pbq12")
    assert t2["usage_text"] == "3 credits reserveret" and len(called) == 1
    c = db.query(PrivateCall).filter_by(workspace_id=pv.ws(tok)).one()
    assert c.paid_via == "credits"
    assert [(r.kind, r.amount) for r in db.query(CreditLedger).filter_by(workspace_id=pv.ws(tok))
            .order_by(CreditLedger.created_at)] == [("grant", 3), ("reserve", -3)]
    from tests.test_privat import _propose

    tid3 = _propose(pv, tok)
    r = api.post(tok, f"/privat/calls/{tid3}/approve", {"share_phone": False})
    assert r.status_code == 409 and r.json()["code"] == "insufficient_credits" and r.json()["needs_plan"] is True


def test_pc_sub_13_cancel_in_trial_keeps_rights_to_trial_end_then_nothing(api, client, pv, stripe, db):
    tok = pv.account("pbq13@testmail.dk", trial=False)
    _checkout(api, tok)
    sub_id = _complete_via_webhook(client, stripe, pv)
    stripe.subs[sub_id]["cancel_at_period_end"] = True
    _event(client, _evt("customer.subscription.updated", stripe.subs[sub_id]))
    s = pv.subscription(tok)
    assert (s["status"], s["entitled"], s["cancel_at_period_end"]) == ("trial", True, True)
    trial_end = stripe.subs[sub_id]["trial_end"]
    # Stripe ends it at trial_end without an invoice
    pv.clock.at = datetime.fromtimestamp(trial_end, UTC) + timedelta(seconds=1)
    gone = stripe.subs[sub_id] | {"status": "canceled", "ended_at": trial_end}
    assert _event(client, _evt("customer.subscription.deleted", gone))["outcome"] == "applied"
    s = pv.subscription(tok)
    assert (s["status"], s["entitled"], s["calls_quota"]) == ("canceled", False, 0)
    assert not [c for c in stripe.calls if c[1].startswith("/invoices")]


def test_pc_sub_13_ui_trial_canceled_does_not_promise_the_charge():
    """F-PBQ-04-PC-SUB-13 (S2): Konto in a canceled trial still says «Derefter Plus til 99 kr./md.» – the trial line
    must respect cancelAtPeriodEnd («Opsagt – slutter <dato>»)."""
    src = (ROOT / "web/src/components/privat/account.tsx").read_text()
    line = next(x for x in src.splitlines() if 'p.status === "trial" && <p' in x)
    assert "cancelAtPeriodEnd" in line, line.strip()[:200]


def test_pc_sub_14_past_due_keeps_rights_then_unpaid_cancel_ends_them(api, client, pv, stripe, db):
    tok = pv.account("pbq14@testmail.dk", trial=False)
    _checkout(api, tok)
    sub_id = _complete_via_webhook(client, stripe, pv)
    sub = stripe.subs[sub_id] | {"status": "active"}
    _event(client, _evt("customer.subscription.updated", sub))
    pv.clock.at = WED_10 + timedelta(days=15)  # renewal fails
    period_end = int((WED_10 + timedelta(days=45)).timestamp())
    sub = sub | {"status": "past_due",
                 "items": {"data": [{"current_period_end": period_end, "price": {"recurring": {"interval": "month"}}}]}}
    _event(client, _evt("customer.subscription.updated", sub))
    s = pv.subscription(tok)
    assert (s["status"], s["entitled"], s["calls_quota"]) == ("past_due", True, 10)
    # invoice.payment_failed for a Privat invoice: no Invoice row, so Dialogbot sends nothing itself (Stripe's mails)
    inv = {"id": "in_pbq14", "object": "invoice", "subscription": sub_id, "customer": sub["customer"],
           "amount_due": 9900, "currency": "dkk"}
    assert _event(client, _evt("invoice.payment_failed", inv))["outcome"] == "unmatched"
    assert not _emails_to(db, "pbq14@testmail.dk")
    # dunning gives up 7 days later: canceled for non-payment → no rights for the unpaid period (regression F-BQ-003)
    pv.clock.at = WED_10 + timedelta(days=22)
    ended = sub | {"status": "canceled", "ended_at": int(pv.clock().timestamp()),
                   "cancellation_details": {"reason": "payment_failed"}}
    _event(client, _evt("customer.subscription.deleted", ended))
    s = pv.subscription(tok)
    assert (s["status"], s["entitled"]) == ("canceled", False)


def test_pc_sub_15_plan_and_interval_changes_follow_the_price(api, client, pv, stripe, db, monkeypatch):
    for plan in ("basis", "plus", "familie"):
        for iv in ("month", "year"):
            monkeypatch.setenv(f"PRIVAT_STRIPE_PRICE_{plan.upper()}_{iv.upper()}", f"price_{plan}_{iv}")
    get_settings.cache_clear()
    tok = pv.account("pbq15@testmail.dk", trial=False)
    ws = pv.ws(tok)
    _checkout(api, tok, plan="basis")
    assert stripe.payload()["line_items"][0] == {"price": "price_basis_month", "quantity": 1,
                                                 "tax_rates": ["txr_dk_vat_2500_incl"]}
    sub_id = _complete_via_webhook(client, stripe, pv)
    base = stripe.subs[sub_id] | {"status": "active"}

    def change(plan, iv):
        obj = base | {"items": {"data": [{"current_period_end": int((pv.clock() + timedelta(days=30)).timestamp()),
                                           "price": {"id": f"price_{plan}_{iv}", "recurring": {"interval": iv}}}]}}
        assert _event(client, _evt("customer.subscription.updated", obj))["outcome"] == "applied"
        return pv.subscription(tok)

    addons_before = None
    for plan, iv in (("basis", "month"), ("plus", "month"), ("plus", "year"), ("familie", "year"), ("basis", "month")):
        s = change(plan, iv)
        calls, people, apps = EXPECTED_QUOTA[plan]
        assert (s["plan"], s["interval"], s["calls_quota"], s["people_limit"], s["apps_included"]) == \
            (plan, iv, calls, people, apps)
        if plan == "familie":
            for key in PLAN_APPS:
                api.post(tok, f"/privat/addons/{key}/enable")
            addons_before = {a["key"] for a in api.get(tok, "/privat/addons").json() if a["enabled"]}
    # Familie → Basis: the Plus apps stay switched on (documented status quo → PC-ENT-02 needs-decision)
    after = {a["key"] for a in api.get(tok, "/privat/addons").json() if a["enabled"]}
    assert set(PLAN_APPS) <= addons_before and set(PLAN_APPS) <= after
    assert ws


# =============================================================================================== amounts per market

def test_pc_sub_17_plans_in_all_currencies_match_independent_table_and_web_catalogue(api, pv):
    tok = pv.account("pbq17@testmail.dk", trial=False)
    web = json.loads((ROOT / "web/src/lib/prices.json").read_text())["privat"]
    for cur, plans in EXPECTED_PLANS.items():
        out = api.get(tok, f"/privat/subscription?currency={cur}").json()
        assert out["currency"] == cur
        assert [p["key"] for p in out["plans"]] == ["basis", "plus", "familie"]
        assert [p["key"] for p in out["plans"] if p["recommended"]] == ["plus"]  # exactly one «Anbefalet»
        for p in out["plans"]:
            m, ym, yt = plans[p["key"]]
            assert (p["monthly_minor"], p["yearly_monthly_minor"], p["yearly_total_minor"]) == (m, ym, yt), (cur, p["key"])
            assert yt == 12 * ym and ym * 100 <= m * 80  # «spar 20 %» is true (at least 20 % below monthly)
            assert (p["calls"], p["people"], p["apps_included"]) == EXPECTED_QUOTA[p["key"]]
            assert web[cur][p["key"]] == {"monthly": m, "yearly_monthly": ym, "yearly_total": yt}, (cur, p["key"])
    assert json.loads((ROOT / "web/src/lib/prices.json").read_text())["privatCreditPack"] == EXPECTED_PACK


@pytest.mark.parametrize("locale", list(EXPECTED_LOCALE))
@pytest.mark.parametrize("plan,interval", [(p, i) for p in ("basis", "plus", "familie") for i in ("month", "year")])
def test_pc_sub_18_checkout_line_amount_currency_vat_for_all_8_languages(api, pv, stripe, locale, plan, interval):
    tok = pv.account(f"pbq18{locale}{plan}{interval}@testmail.dk", trial=False)
    cur, slocale, rates = EXPECTED_LOCALE[locale]
    assert _checkout(api, tok, plan=plan, interval=interval, locale=locale)["status"] == 200
    d = stripe.payload()
    line = d["line_items"][0]
    pd = line["price_data"]
    m, _ym, yt = EXPECTED_PLANS[cur][plan]
    assert (d["locale"], pd["currency"], pd["unit_amount"], pd["tax_behavior"]) == \
        (slocale, cur.lower(), m if interval == "month" else yt, "inclusive")
    assert pd["recurring"] == {"interval": interval}
    assert line.get("tax_rates") == rates
    assert d["metadata"]["currency"] == cur and d["metadata"]["interval"] == interval
    desc = pd["product_data"]["description"]
    assert ("moms" in desc or "VAT" in desc) is (rates is not None), desc


def test_pc_sub_18_currency_is_kept_and_stripe_tax_mode(api, pv, stripe, monkeypatch):
    tok = pv.account("pbq18keep@testmail.dk", trial=False)
    _checkout(api, tok, locale="sv")
    assert stripe.payload()["line_items"][0]["price_data"]["currency"] == "sek"
    _checkout(api, tok, locale="de")
    assert stripe.payload()["line_items"][0]["price_data"]["currency"] == "sek"  # keeps its first currency
    assert pv.subscription(tok)["currency"] == "SEK"
    monkeypatch.setenv("STRIPE_TAX_ENABLED", "true")
    get_settings.cache_clear()
    tok2 = pv.account("pbq18tax@testmail.dk", trial=False)
    _checkout(api, tok2, locale="da", plan="familie", interval="year")
    d = stripe.payload()
    line = d["line_items"][0]
    assert d["automatic_tax"] == {"enabled": True} and "tax_rates" not in line
    assert line["price_data"]["product_data"]["tax_code"] == "txcd_10103000"
    assert line["price_data"]["tax_behavior"] == "inclusive" and line["price_data"]["unit_amount"] == 162000
    assert line["price_data"]["product_data"]["description"].startswith("1.620 kr. pr. år (135 kr./md.) inkl. moms")


def test_vat_split_of_every_privat_amount_is_exact_or_documented():
    """Inclusive 25 %: DKK/SEK/NOK amounts split exactly; EUR amounts need Stripe's rounding (documented in the table)."""
    exact = {(c, p, i) for c, plans in EXPECTED_PLANS.items() for p, v in plans.items() for i, g in zip("mt", (v[0], v[2]))
             if g * 2500 % 12500 == 0}
    inexact = {(c, p, i) for c, plans in EXPECTED_PLANS.items() for p, v in plans.items() for i, g in zip("mt", (v[0], v[2]))
               if g * 2500 % 12500}
    assert all(c == "EUR" for c, _p, _i in inexact) and len(exact) == 18
    assert vat_inclusive_split(649) == (519, 130) and vat_inclusive_split(1349) == (1079, 270)
    assert vat_inclusive_split(2249) == (1799, 450) and vat_inclusive_split(399) == (319, 80)
    assert vat_inclusive_split(2900) == (2320, 580)


def test_pc_sub_19_discount_codes(api, pv, stripe, db):
    from app.models.domain import DiscountCode

    tok = pv.account("pbq19@testmail.dk", trial=False)
    assert _checkout(api, tok)["status"] == 200
    assert stripe.payload().get("allow_promotion_codes") is True and "discounts" not in stripe.payload()
    r = _checkout(api, tok, code="FINDESIKKE")
    assert r["status"] in (404, 422) and r["status"] != 500
    cols = {c.name for c in DiscountCode.__table__.columns}
    assert "stripe_promotion_code_id" in cols


# =============================================================================================== credits

def test_pc_sub_21_credit_pack_once_per_session_all_currencies(api, client, pv, stripe, db):
    for cur, loc in (("DKK", "da"), ("SEK", "sv"), ("NOK", "no"), ("EUR", "de")):
        tok = pv.account(f"pbq21{cur.lower()}@testmail.dk", trial=False)
        ws = pv.ws(tok)
        assert api.post(tok, "/privat/credits/checkout", {"locale": loc}).status_code == 200
        d = stripe.payload()
        assert d["line_items"][0]["price_data"]["unit_amount"] == EXPECTED_PACK[cur]
        sid = list(stripe.sessions)[-1]
        base = {"id": sid, "mode": "payment", "currency": cur.lower(), "amount_total": EXPECTED_PACK[cur],
                "metadata": d["metadata"]}
        # abandoned / unpaid → 0
        assert _event(client, _evt("checkout.session.completed", base | {"payment_status": "unpaid"}))["outcome"] == "ignored"
        paid = _evt("checkout.session.completed", base | {"payment_status": "paid"})
        assert _event(client, paid)["outcome"] == "applied"
        assert _event(client, paid)["duplicate"] is True
        assert _event(client, _evt("checkout.session.async_payment_succeeded", base | {"payment_status": "paid"}))[
            "outcome"] == "ignored"
        db.expire_all()
        rows = [(r.kind, r.amount) for r in db.query(CreditLedger).filter_by(workspace_id=ws).order_by(CreditLedger.created_at)]
        assert rows == [("grant", 3), ("purchase", 10)], (cur, rows)


def test_pc_sub_21_no_promotion_codes_on_the_credit_pack(api, client, pv, stripe, db):
    """F-PBQ-03-PC-SUB-21 (S0, fixed by «no codes on the credit pack»): the credit Checkout must not show Stripe's code
    field, so nobody can pay less than the list price. An underpaid session (should never happen now) is still
    ignored – fix-engineer logs it as privat.credit_pack_underpaid for a manual refund."""
    tok = pv.account("pbq21promo@testmail.dk", trial=False)
    assert api.post(tok, "/privat/credits/checkout", {}).status_code == 200
    d = stripe.payload()
    assert "allow_promotion_codes" not in d and "discounts" not in d
    obj = {"id": list(stripe.sessions)[-1], "mode": "payment", "currency": "dkk", "amount_total": 1450,
           "amount_subtotal": 2900, "total_details": {"amount_discount": 1450}, "payment_status": "paid",
           "metadata": d["metadata"]}
    assert _event(client, _evt("checkout.session.completed", obj))["outcome"] == "ignored"
    db.expire_all()
    assert not db.query(CreditLedger).filter_by(workspace_id=pv.ws(tok), kind="purchase").count()


def test_credit_pack_refund_takes_the_credits_back(api, client, pv, stripe, db):
    """F-PBQ-05-PC-SUB-21 (S2): a refunded credit pack (charge.refunded) changes nothing in the ledger."""
    tok = pv.account("pbq21refund@testmail.dk", trial=False)
    api.post(tok, "/privat/credits/checkout", {})
    d = stripe.payload()
    sid = list(stripe.sessions)[-1]
    _event(client, _evt("checkout.session.completed", {"id": sid, "mode": "payment", "currency": "dkk",
                                                        "amount_total": 2900, "payment_status": "paid",
                                                        "payment_intent": "pi_pbq", "metadata": d["metadata"]}))
    refund = {"id": "ch_pbq", "object": "charge", "payment_intent": "pi_pbq", "amount": 2900, "amount_refunded": 2900,
              "refunded": True, "metadata": d["metadata"]}
    try:
        _event(client, _evt("charge.refunded", refund))
    except AssertionError:
        pass  # the fake has no /invoice_payments – the handler looks for an Erhverv invoice
    db.expire_all()
    bal = sum(r.amount for r in db.query(CreditLedger).filter_by(workspace_id=pv.ws(tok)))
    assert bal == 3, f"after a full refund the balance is {bal} (3 welcome + 10 refunded pack)"


# =============================================================================================== entitlements

def _all_apps_on(api, tok) -> set[str]:
    for key in PLAN_APPS:
        api.post(tok, f"/privat/addons/{key}/enable")
    return {a["key"] for a in api.get(tok, "/privat/addons").json() if a["enabled"]}


def test_pc_ent_02_plan_apps_stop_when_the_plan_ends(api, client, pv, stripe, db):
    tok = pv.account("pbq-ent02@testmail.dk", trial=False)
    _checkout(api, tok)
    sub_id = _complete_via_webhook(client, stripe, pv)
    on = _all_apps_on(api, tok)
    assert set(PLAN_APPS) <= on
    _event(client, _evt("customer.subscription.deleted", stripe.subs[sub_id] | {"status": "canceled",
                                                                                "ended_at": int(pv.clock().timestamp())}))
    pv.clock.at = WED_10 + timedelta(days=15)
    assert pv.subscription(tok)["entitled"] is False
    for path in ("/privat/bills", "/privat/birthdays", "/privat/car", "/privat/health-contacts",
                 "/privat/apps/garanti/overview", "/privat/apps/flytning/overview"):
        assert api.get(tok, path).status_code in (402, 403, 409), path


def test_pc_ent_02_plan_apps_pause_but_keep_data_after_the_trial(api, client, pv, stripe, db):
    """F-PBQ-06 decided (option A, commit 451d53b): after the plan ends the plan apps stay «on» with their data kept,
    but the gate refuses them until a plan is active again."""
    from app.core.errors import ApiError

    tok = pv.account("pbq-ent02b@testmail.dk", trial=False)
    ws = pv.ws(tok)
    _checkout(api, tok)
    sub_id = _complete_via_webhook(client, stripe, pv)
    _all_apps_on(api, tok)
    api.post(tok, "/privat/bills", {"name": "Vand", "amount": "450", "frequency": "quarterly", "due_day": 15})
    _event(client, _evt("customer.subscription.deleted", stripe.subs[sub_id] | {"status": "canceled",
                                                                                "ended_at": int(pv.clock().timestamp())}))
    pv.clock.at = WED_10 + timedelta(days=20)
    assert pv.subscription(tok)["entitled"] is False
    for key in PLAN_APPS:
        with pytest.raises(ApiError):
            addons.require(db, ws, key)
    for path in ("/privat/bills", "/privat/birthdays", "/privat/car", "/privat/health-contacts"):
        assert api.get(tok, path).status_code in (402, 403, 409), path
    db.expire_all()
    from app.models import PrivateBill

    assert db.query(PrivateBill).filter_by(workspace_id=ws).count() == 1  # data kept


def test_pc_ent_03_no_reminders_from_plan_apps_after_expiry(api, client, pv, stripe, db):
    """F-PBQ-06 decided (option A): birthday and bill reminders stop when the plan has ended."""
    from app.modules.privat import birthdays

    tok = pv.account("pbq-ent03@testmail.dk")
    ws = pv.ws(tok)
    for key in ("foedselsdage", "regninger"):
        assert api.post(tok, f"/privat/addons/{key}/enable").status_code == 200
    pv.expire_trial(tok)
    assert pv.subscription(tok)["entitled"] is False
    birthdays.save(db, ws, name="Mormor", when="2026-11-08", remind_days_before=7)
    bills.save(db, ws, name="El", amount="640", frequency="monthly", due_day=6, remind_days_before=3)
    db.commit()
    assert birthdays.send_due(db, WED_10) == 0 and bills.send_due(db, WED_10) == 0
    # with a plan again they come back
    pv.set_plan(tok, "plus")
    assert birthdays.send_due(db, WED_10) == 1 and bills.send_due(db, WED_10) == 1


def test_pc_ent_05_call_09_basis_quota_unanswered_failed_and_replay(api, client, pv, db, monkeypatch):
    from tests.test_privat import _report
    from tests.test_privat_subscription import _approve_plan

    tok = pv.account("pbq-ent05@testmail.dk")
    pv.verify_phone(tok)
    pv.set_plan(tok, "basis")
    msgs = [{"role": "bot", "message": "Hej"}, {"role": "user", "message": "Ja, torsdag passer."}]
    # unanswered and failed do not count
    for i, reason in enumerate(("customer-did-not-answer", "pipeline-error-openai-llm-failed")):
        _t, _x, called = _approve_plan(api, pv, tok, monkeypatch, f"c_lost{i}")
        _report(client, called[0], reason, [], seconds=0, call_id=f"c_lost{i}")
    assert pv.me(tok)["calls_used"] == 0
    for n in (1, 2, 3):
        _t, t, called = _approve_plan(api, pv, tok, monkeypatch, f"c_ok{n}")
        assert t["usage_text"] == f"Opkald {n} af 3 i Basis"
        rep = _report(client, called[0], "customer-ended-call", msgs, seconds=61, call_id=f"c_ok{n}")
        assert rep["outcome"] == "applied"
        replay = _report(client, called[0], "customer-ended-call", msgs, seconds=61, call_id=f"c_ok{n}")
        assert replay.get("duplicate") is True or replay.get("outcome") in ("duplicate", "ignored"), replay
    me = pv.me(tok)
    assert (me["calls_used"], me["calls_left"], me["credits"], me["reserved"]) == (3, 0, 3, 0)
    _t, t, called = _approve_plan(api, pv, tok, monkeypatch, "c_4")
    assert t["usage_text"] == "3 credits reserveret"
    _report(client, called[0], "customer-ended-call", msgs, seconds=61, call_id="c_4")
    _report(client, called[0], "customer-ended-call", msgs, seconds=61, call_id="c_4")  # replay
    db.expire_all()
    rows = [(r.kind, r.amount) for r in db.query(CreditLedger).filter_by(workspace_id=pv.ws(tok)).order_by(CreditLedger.created_at)]
    assert rows == [("grant", 3), ("reserve", -3), ("capture", 0)] or sum(a for _k, a in rows) == 0, rows
    assert pv.me(tok)["credits"] == 0 and pv.me(tok)["reserved"] == 0


def _call_row(db, ws, task_id, approved_at, result="answered"):
    db.add(PrivateCall(workspace_id=ws, task_id=task_id, business_name="Test", status="answered", result=result,
                       paid_via="plan", approved_at=approved_at))


@pytest.mark.parametrize("approved_utc,clock_utc,expected", [
    # 31/10 23:30 local (CET, DST ended 25/10) = 22:30 UTC → October
    (datetime(2026, 10, 31, 22, 30, tzinfo=UTC), datetime(2026, 10, 31, 22, 45, tzinfo=UTC), 1),
    (datetime(2026, 10, 31, 22, 30, tzinfo=UTC), datetime(2026, 10, 31, 23, 0, tzinfo=UTC), 0),  # 1/11 00:00 local: reset
    # 1/11 00:30 local = 31/10 23:30 UTC → November (UTC would still say October)
    (datetime(2026, 10, 31, 23, 30, tzinfo=UTC), datetime(2026, 11, 1, 9, 0, tzinfo=UTC), 1),
    (datetime(2026, 10, 31, 23, 30, tzinfo=UTC), datetime(2026, 10, 31, 22, 59, tzinfo=UTC), 0),
    # DST night itself, 25/10 02:30 CEST (00:30 UTC) and 02:30 CET (01:30 UTC): both October
    (datetime(2026, 10, 25, 0, 30, tzinfo=UTC), datetime(2026, 10, 30, 9, 0, tzinfo=UTC), 1),
    (datetime(2026, 10, 25, 1, 30, tzinfo=UTC), datetime(2026, 10, 30, 9, 0, tzinfo=UTC), 1),
    # spring: 31/3/2027 23:30 CEST = 21:30 UTC → March; 1/4 00:30 CEST = 22:30 UTC 31/3 → April
    (datetime(2027, 3, 31, 21, 30, tzinfo=UTC), datetime(2027, 3, 31, 21, 45, tzinfo=UTC), 1),
    (datetime(2027, 3, 31, 22, 30, tzinfo=UTC), datetime(2027, 4, 1, 8, 0, tzinfo=UTC), 1),
    (datetime(2027, 3, 31, 21, 30, tzinfo=UTC), datetime(2027, 3, 31, 22, 0, tzinfo=UTC), 0),
])
def test_pc_ent_06_quota_month_is_copenhagen_incl_dst(api, pv, db, approved_utc, clock_utc, expected):
    tok = pv.account(f"pbq-ent06-{approved_utc:%m%d%H%M}-{clock_utc:%m%d%H%M}@testmail.dk")
    pv.set_plan(tok, "plus", period_days=400)
    ws = pv.ws(tok)
    tid = pv.make_list(tok)
    _call_row(db, ws, uuid.UUID(tid), approved_utc)
    db.commit()
    pv.clock.at = clock_utc
    me = pv.me(tok)
    assert (me["calls_used"], me["calls_left"]) == (expected, 10 - expected)


@pytest.mark.xfail(strict=True, reason="F-PQ-03-X09 (open, needs-decision): a free account activates drafts via welcome "
                                       "credit / simulated sponsor – regression only, no duplicate")
def test_pc_ent_07_free_account_cannot_activate_drafts(api, pv, db):
    tok = pv.account("pbq-ent07@testmail.dk", trial=False)
    t1, t2 = (next(m["task_id"] for m in pv.say(tok, x)["messages"] if m["kind"] == "draft")
              for x in ("Lav en liste med æbler", "Lav en liste med pærer"))
    r1 = api.post(tok, f"/privat/tasks/{t1}/activate", {"method": "credit"})
    r2 = api.post(tok, "/privat/sponsor/claim", {"task_id": t2})
    assert r1.status_code in (403, 409) and r2.status_code in (403, 409)


def _privat_paths(app) -> list[str]:
    return [p for p in app.openapi()["paths"] if "/privat" in p]


def test_pc_ent_08_familie_people_limit_has_no_way_to_add_people(api, pv, app):
    """F-PBQ-07-PC-ENT-08 (S1): Familie (169 kr./md.) is sold as «Op til 5 personer», but no endpoint, model or UI
    attaches other people to the plan: people_limit is only a number."""
    tok = pv.account("pbq-ent08@testmail.dk")
    pv.set_plan(tok, "familie")
    s = pv.subscription(tok)
    assert s["people_limit"] == 5 and "Op til 5 personer" in next(p for p in s["plans"] if p["key"] == "familie")["features"]
    routes = _privat_paths(app)
    assert len(routes) > 50
    household = [p for p in routes if re.search(r"household|husstand|family|familie|plan/members|subscription/members", p)]
    src = "\n".join(p.read_text() for p in (ROOT / "app/modules/privat").glob("*.py"))
    uses = [m for m in re.findall(r"people_limit[^\n]*", src) if "people_limit" in m]
    assert household, f"no household/family endpoint among {len(routes)} /privat routes; people_limit used only as: {uses}"


# =============================================================================================== money in the apps

def test_pc_app_07_bills_due_dates_and_danish_amounts():
    for text, minor in (("1.234,50 kr.", 123450), ("640", 64000), ("640 kr.", 64000), ("1.250", 125000),
                        ("1250,5", 125050), ("1250.5", 125050), (640, 64000), (12.5, 1250), ("0,01", 1),
                        ("1.234.567,89", 123456789)):
        assert bills.parse_amount(text) == minor, text
    for bad in ("-5", -5, "abc", "1,234,50", "12,345"):
        assert bills.parse_amount(bad) is None, bad
    assert bills.money(123450) == "1.234,50 kr." and bills.money(64000) == "640 kr."
    # due_day 31 → last day of short months, back to 31 after
    assert bills.first_due(date(2027, 2, 10), due_day=31) == (date(2027, 2, 28), 31)
    assert bills.first_due(date(2028, 2, 10), due_day=31) == (date(2028, 2, 29), 31)
    assert bills.first_due(date(2027, 1, 31), due_day=31) == (date(2027, 1, 31), 31)
    assert bills.first_due(date(2027, 2, 1), due_day=1) == (date(2027, 2, 1), 1)

    class B:
        def __init__(self, f, d, a):
            self.frequency, self.next_due, self.anchor_day = f, d, a

    cases = [("monthly", date(2027, 1, 31), date(2027, 2, 1), date(2027, 2, 28)),
             ("monthly", date(2027, 2, 28), date(2027, 3, 1), date(2027, 3, 31)),
             ("quarterly", date(2026, 11, 30), date(2026, 12, 1), date(2027, 2, 28)),
             ("half_yearly", date(2026, 8, 31), date(2026, 9, 1), date(2027, 2, 28)),
             ("yearly", date(2028, 2, 29), date(2028, 3, 1), date(2029, 2, 28)),
             ("monthly", date(2026, 1, 15), date(2026, 11, 10), date(2026, 11, 15))]  # several periods missed
    for f, due, today, nxt in cases:
        b = B(f, due, due.day if f != "monthly" or due.day != 28 else 31)
        assert bills.roll(b, today) is True and b.next_due == nxt, (f, due, b.next_due)
    once = B("once", date(2026, 11, 1), 1)
    assert bills.roll(once, date(2026, 11, 10)) is False and once.next_due == date(2026, 11, 1)


def test_pc_app_11_expense_split_sums_to_zero_in_whole_ore():
    g = {"name": "Sommerhus", "people": ["Mette", "Ole", "Anna"],
         "expenses": [{"payer": "Mette", "amount_minor": 10000, "text": "", "among": None}]}
    bal = expenses.balances(g)
    assert sum(bal.values()) == 0 and bal == {"Mette": 6666, "Ole": -3333, "Anna": -3333}
    assert sorted(expenses.settle(g)) == [("Anna", "Mette", 3333), ("Ole", "Mette", 3333)]
    g["expenses"] += [{"payer": "Ole", "amount_minor": 1, "text": "", "among": ["Mette", "Anna"]},
                      {"payer": "Anna", "amount_minor": 99999, "text": "", "among": ["Anna", "Ole"]}]
    bal = expenses.balances(g)
    assert sum(bal.values()) == 0
    moves = expenses.settle(g)
    assert len(moves) <= len(g["people"]) - 1 and all(n > 0 for _a, _b, n in moves)
    after = dict(bal)
    for a, b, n in moves:
        after[a] += n
        after[b] -= n
    assert set(after.values()) == {0}
    text = expenses.summary_text(g)
    assert "MobilePay" not in text and "overfør" not in text.lower()  # no transfer offered by Dialogbot


def test_pc_app_11_negative_and_zero_expense_refused(api, pv, db):
    from app.core.errors import ValidationFailed

    tok = pv.account("pbq-app11@testmail.dk")
    api.post(tok, "/privat/addons/faelles-udgifter/enable")
    ctx = type("C", (), {"ws_id": pv.ws(tok), "user_id": pv.uid(tok)})()
    for bad in ("-100", -100, 0, "0 kr."):
        with pytest.raises(ValidationFailed):
            expenses.add_expense(db, ctx, me="Mette", group="Tur", paid_by="Mette", amount=bad)
    db.rollback()


def test_pc_gift_01_pledge_bounds(api, pv):
    from tests.test_privat_wishes import _gift, _gift_wish, _pledge, _wishlist

    mette, ole, anna, tid = _wishlist(api, pv)
    iid = _gift_wish(api, mette, tid, target=100000)
    for bad in (0, -1, -100000):
        assert _pledge(api, ole, tid, iid, bad).status_code == 422
    assert _pledge(api, ole, tid, iid, 60000).status_code == 200
    r = _pledge(api, anna, tid, iid, 40001)
    assert r.status_code == 409 and r.json()["code"] == "pledge_exceeds_remaining" and r.json()["remaining_minor"] == 40000
    assert _pledge(api, ole, tid, iid, 100000).status_code == 200  # raise own pledge up to the whole target
    assert _gift(api, ole, tid, iid)["status"] == "full"
    assert _pledge(api, ole, tid, iid, 30000).status_code == 200  # lower again
    g = _gift(api, anna, tid, iid)
    assert (g["pledged_minor"], g["remaining_minor"], g["status"]) == (30000, 70000, "open")
    api.delete(ole, f"/privat/tasks/{tid}/items/{iid}/gift/pledge")
    assert _gift(api, anna, tid, iid)["pledged_minor"] == 0


# =============================================================================================== referrals

@pytest.mark.xfail(strict=True, reason="F-PQ-03-X09 consequence (no duplicate): via welcome-credit activation a FREE "
                                       "alt-account becomes an 'active invitee' and pays the inviter +3 credits")
def test_pc_inv_08_self_referral_farm_without_any_plan(api, pv, db):
    from tests.test_privat_sharing import _accept

    teen = pv.account("teen-farm@testmail.dk")
    link = api.post(teen, "/privat/referrals/link").json()
    for i in range(3):
        alt = pv.user(f"teen-farm+{i}@testmail.dk", f"Alt{i} Teen")  # alias e-mails, all verified
        _accept(api, alt, link["token"])
        out = pv.say(alt, f"Lav en liste med ting{i}")  # draft (no plan)
        tid = next(m["task_id"] for m in out["messages"] if m["kind"] == "draft")
        assert api.post(alt, f"/privat/tasks/{tid}/activate", {"method": "credit"}).status_code == 200  # F-PQ-03
        pv.say(alt, f"Lav en liste med mere{i}")  # any next message → referrals.try_activate sees an own active task
    db.expire_all()
    earned = sum(r.amount for r in db.query(CreditLedger).filter_by(workspace_id=pv.ws(teen), kind="referral"))
    assert earned == 0, f"inviter farmed {earned} credits from 3 free alt-accounts"


def test_pc_inv_08_referral_caps_hold(api, pv, db):
    from tests.test_privat_sharing import _accept

    teen = pv.account("teen-cap@testmail.dk")
    link = api.post(teen, "/privat/referrals/link").json()
    _accept(api, teen, link["token"])  # self
    for i in range(11):
        alt = pv.user(f"teen-cap+{i}@testmail.dk", f"Alt{i} Teen")
        _accept(api, alt, link["token"])
        _accept(api, alt, link["token"])  # twice
        pv.start_trial(alt)
        pv.make_list(alt, f"Lav en liste med ting{i}")
    db.expire_all()
    rows = db.query(CreditLedger).filter_by(workspace_id=pv.ws(teen), kind="referral").all()
    assert len(rows) == 10 and sum(r.amount for r in rows) == 30
    # next Copenhagen month: the cap is fresh (1/12 00:00 local = 30/11 23:00 UTC)
    from app.modules.privat import referrals

    pv.clock.at = datetime(2026, 11, 30, 23, 0, tzinfo=UTC)
    assert referrals.inviter_rewards_this_month(db, pv.ws(teen)) == 0


# =============================================================================================== invoices / receipts

def test_pc_acc_04_invoices_only_through_the_stripe_portal(api, client, pv, stripe, db, app):
    tok = pv.account("pbq-acc04@testmail.dk", trial=False)
    r = api.post(tok, "/privat/subscription/portal")
    assert r.status_code == 501 and r.json()["code"] == "not_configured"
    _checkout(api, tok)
    _complete_via_webhook(client, stripe, pv)
    r = api.post(tok, "/privat/subscription/portal")
    assert r.status_code == 200 and r.json()["url"].startswith("https://billing.stripe.test/")
    assert stripe.calls[-1][2] == {"customer": f"cus_{list(stripe.sessions)[0]}",
                                   "return_url": f"{get_settings().frontend_base_url.rstrip('/')}/privat/konto"}
    routes = _privat_paths(app)
    assert len(routes) > 50 and not [p for p in routes if re.search(r"invoice|faktura|receipt|kvittering", p) and "/privat/" in p
                and "warranty" not in p and "garanti" not in p and "expense" not in p]
    da = json.loads((ROOT / "web/src/i18n/messages/da/privat.json").read_text())
    assert not re.search(r"[Ff]aktura|[Kk]vittering for", json.dumps(da.get("plan", {}), ensure_ascii=False))


def test_pc_ent_08_household_limit_shared_quota_and_end_of_plan(api, client, pv, db):
    """F-PBQ-07 retest (household built, 451d53b): 5 people incl. owner, members get Familie rights live from the owner,
    the 25 calls are the household's, and the rights stop with the owner's plan."""
    owner = pv.account("pbq-hh-owner@testmail.dk")
    pv.set_plan(owner, "familie")
    toks = []
    for i in range(4):
        inv = api.post(owner, "/privat/household/invites")
        assert inv.status_code == 200, inv.text
        m = pv.user(f"pbq-hh-{i}@testmail.dk", f"Medlem{i} Hansen")
        api.post(m, "/privat/account")
        r = api.post(m, f"/privat/invites/{inv.json()['token']}/accept")
        assert r.status_code == 200, r.text
        toks.append(m)
    r = api.post(owner, "/privat/household/invites")
    assert r.status_code == 409 and r.json()["code"] == "household_full"
    s = pv.subscription(toks[0])
    assert (s["entitled"], s["plan"], s["calls_quota"]) == (True, "familie", 25)
    # shared quota: an answered plan call by a member counts for everybody
    tid = pv.make_list(toks[1])
    db.add(PrivateCall(workspace_id=pv.ws(toks[1]), task_id=uuid.UUID(tid), business_name="T", status="answered",
                       result="answered", paid_via="plan", approved_at=pv.clock()))
    db.commit()
    assert pv.subscription(owner)["calls_used"] == 1 and pv.subscription(toks[2])["calls_left"] == 24
    # owner downgrades to Plus → members lose rights at once
    pv.set_plan(owner, "plus")
    assert pv.subscription(toks[0])["entitled"] is False
    pv.set_plan(owner, "familie")
    assert pv.subscription(toks[0])["entitled"] is True
    pv.clock.at = WED_10 + timedelta(days=31)  # owner's period over, nothing renewed
    with db.begin_nested():
        db.get(PrivateSubscription, pv.ws(owner)).status = "canceled"
    db.commit()
    assert pv.subscription(toks[3])["entitled"] is False

"""QA X07 (e2e-privat, P0): «Prøv gratis i 14 dage» → Stripe Checkout (navn, adresse, telefon, e-mail, kort) → adgang
KUN efter gennemført Stripe-setup. Afvist kort / afbrudt checkout / udløbet session / forfalsket retur giver ingen adgang.

Stripe is replaced exactly as the suite does it (monkeypatching app.modules.billing.stripe.request): a small stateful
fake that knows sessions (open/complete/expired) and subscriptions. No network.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
from datetime import timedelta

import pytest

from app.config import get_settings
from app.models import PrivateSubscription, PrivateTask
from app.modules.billing import stripe as stripe_api
from tests.privat_fixtures import WED_10

SECRET = "whsec_qa_x07"


class FakeStripe:
    def __init__(self):
        self.sessions: dict[str, dict] = {}
        self.subs: dict[str, dict] = {}
        self.sent: list[tuple[str, str, dict | None]] = []

    def __call__(self, m, p, d=None, **_k):
        self.sent.append((m, p, d))
        if p == "/tax_rates":
            return {"data": []} if m == "GET" else {"id": f"txr_{d['metadata']['dialogbot']}"}
        if (m, p) == ("POST", "/checkout/sessions"):
            sid = f"cs_test_x07_{len(self.sessions) + 1}"
            self.sessions[sid] = {"id": sid, "object": "checkout.session", "mode": d["mode"], "status": "open",
                                  "payment_status": "unpaid", "subscription": None, "metadata": d["metadata"],
                                  "_payload": d}
            return {"id": sid, "url": f"https://checkout.stripe.test/{sid}"}
        if m == "GET" and p.startswith("/checkout/sessions/"):
            s = self.sessions.get(p.rsplit("/", 1)[1])
            if s is None:
                raise stripe_api.StripeFailed("Stripe afviste kaldet: No such checkout.session")
            return {k: v for k, v in s.items() if k != "_payload"}
        if m == "GET" and p.startswith("/subscriptions/"):
            return self.subs[p.rsplit("/", 1)[1]]
        raise AssertionError(f"unexpected Stripe call {m} {p}")

    def complete(self, sid: str, *, sub_status: str = "trialing") -> dict:
        s = self.sessions[sid]
        sd = s["_payload"]["subscription_data"]
        trial = sd.get("trial_period_days")
        sub_id = f"sub_{sid}"
        end = int((WED_10 + timedelta(days=trial or 30)).timestamp())
        self.subs[sub_id] = {"id": sub_id, "object": "subscription", "status": sub_status, "customer": f"cus_{sid}",
                             "cancel_at_period_end": False, "trial_end": end if trial else None,
                             "metadata": sd["metadata"],
                             "items": {"data": [{"current_period_end": end, "price": {"recurring": {"interval": "month"}}}]}}
        s.update(status="complete", subscription=sub_id, payment_status="no_payment_required" if trial else "paid",
                 customer=f"cus_{sid}")
        return {k: v for k, v in s.items() if k != "_payload"}


@pytest.fixture
def stripe(monkeypatch):
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_x07")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", SECRET)
    get_settings.cache_clear()
    fake = FakeStripe()
    monkeypatch.setattr(stripe_api, "request", fake)
    return fake


def _event(client, event: dict, secret: str = SECRET):
    body = json.dumps(event).encode()
    ts = int(time.time())
    sig = hmac.new(secret.encode(), f"{ts}.".encode() + body, hashlib.sha256).hexdigest()
    return client.post("/api/v1/webhooks/stripe", content=body, headers={"stripe-signature": f"t={ts},v1={sig}"})


def _no_access(api, pv, tok):
    s = pv.subscription(tok)
    assert (s["status"], s["plan"], s["entitled"], s["calls_quota"], s["trial_days_left"]) == ("none", "none", False, 0, 0)
    me = pv.me(tok)
    assert me["entitled"] is False and me["plan_status"] == "none"
    # what the plan would give: Shop apps, own lists live
    r = api.post(tok, "/privat/addons/kalender/enable")
    assert r.status_code >= 400, r.text
    out = pv.say(tok, "Lav en liste med kaffe")
    assert next(m["kind"] for m in out["messages"] if m["role"] == "assistant") == "draft"


def _checkout(api, tok) -> str:
    r = api.post(tok, "/privat/subscription/checkout", {"plan": "plus", "interval": "month"})
    assert r.status_code == 200, r.text
    return r.json()["url"].rsplit("/", 1)[1]


def test_checkout_collects_name_address_phone_email_card_and_14_days(api, pv, stripe):
    tok = pv.account("x07-a@testmail.dk", trial=False)
    sid = _checkout(api, tok)
    d = stripe.sessions[sid]["_payload"]
    assert d["mode"] == "subscription"
    assert d["billing_address_collection"] == "required"        # name + address
    assert d["phone_number_collection"] == {"enabled": True}     # phone
    assert d["customer_email"] == "x07-a@testmail.dk"            # e-mail
    assert d["payment_method_collection"] == "always"            # card, even though nothing is charged for 14 days
    assert d["subscription_data"]["trial_period_days"] == 14
    assert d["success_url"].endswith("/privat/konto?abonnement=ok&session_id={CHECKOUT_SESSION_ID}")
    assert d["cancel_url"].endswith("/privat/konto?abonnement=annulleret")
    _no_access(api, pv, tok)  # merely starting the checkout gives nothing


def test_abandoned_declined_and_expired_checkout_give_no_access(api, client, pv, stripe, db):
    tok = pv.account("x07-b@testmail.dk", trial=False)
    ws = pv.ws(tok)
    sid = _checkout(api, tok)
    # back from Stripe without paying (declined card / closed tab / «Tilbage»): the session is still open
    for _ in range(2):  # reload of the return URL
        r = api.get(tok, f"/privat/subscription?session_id={sid}")
        assert r.status_code == 200 and (r.json()["status"], r.json()["entitled"]) == ("none", False)
    # Stripe's own events for a failed / given-up session change nothing
    for i, kind in enumerate(("checkout.session.expired", "checkout.session.async_payment_failed")):
        stripe.sessions[sid]["status"] = "expired" if kind.endswith("expired") else "open"
        obj = {k: v for k, v in stripe.sessions[sid].items() if k != "_payload"}
        r = _event(client, {"id": f"evt_x07_fail_{i}", "type": kind, "data": {"object": obj}})
        assert r.status_code == 200, r.text
    assert pv.subscription(tok)["status"] == "none"
    db.expire_all()
    row = db.get(PrivateSubscription, ws)
    assert (row.status, row.trial_ends_at, row.stripe_subscription_id) == ("none", None, None)
    _no_access(api, pv, tok)
    # the trial is still available afterwards (nothing was used up)
    sid2 = _checkout(api, tok)
    assert stripe.sessions[sid2]["_payload"]["subscription_data"]["trial_period_days"] == 14


def test_forged_and_foreign_returns_give_no_access(api, client, pv, stripe):
    mette = pv.account("x07-c@testmail.dk", trial=False)
    ole = pv.account("x07-d@testmail.dk", "Ole Berg", trial=False)
    sid = _checkout(api, ole)
    stripe.complete(sid)  # Ole really completed his
    # Mette replays Ole's success URL: refused, and she gets nothing
    assert api.get(mette, f"/privat/subscription?session_id={sid}").status_code == 404
    assert api.get(mette, "/privat/subscription?session_id=cs_test_does_not_exist").status_code in (404, 502)
    assert api.get(mette, "/privat/subscription?session_id=sub_123").status_code == 422
    _no_access(api, pv, mette)
    # a webhook with a wrong signature is rejected and changes nothing
    obj = stripe.sessions[sid] | {"metadata": stripe.sessions[sid]["metadata"] | {"workspace_id": str(pv.ws(mette))}}
    obj = {k: v for k, v in obj.items() if k != "_payload"}
    r = _event(client, {"id": "evt_x07_forged", "type": "checkout.session.completed", "data": {"object": obj}},
               secret="whsec_wrong")
    assert r.status_code == 401
    assert pv.subscription(mette)["status"] == "none"
    # an unsigned customer.subscription.created claiming «trialing» for Mette: same
    sub = dict(stripe.subs[f"sub_{sid}"]) | {"metadata": obj["metadata"]}
    r = client.post("/api/v1/webhooks/stripe", content=json.dumps(
        {"id": "evt_x07_unsigned", "type": "customer.subscription.created", "data": {"object": sub}}).encode())
    assert r.status_code == 401
    assert pv.subscription(mette)["status"] == "none"


@pytest.mark.parametrize("path", ["return", "webhook"])
def test_completed_setup_grants_14_days_plus_once(api, client, pv, stripe, db, path):
    tok = pv.account(f"x07-e-{path}@testmail.dk", trial=False)
    pv.say(tok, "Lav en liste med kaffe")  # waits as a draft for the plan
    sid = _checkout(api, tok)
    obj = stripe.complete(sid)
    if path == "return":
        s = api.get(tok, f"/privat/subscription?session_id={sid}").json()
        again = api.get(tok, f"/privat/subscription?session_id={sid}").json()  # reload of the success URL
        assert again == s
    else:
        assert _event(client, {"id": f"evt_x07_ok_{path}", "type": "checkout.session.completed",
                               "data": {"object": obj}}).json()["outcome"] == "applied"
        assert _event(client, {"id": f"evt_x07_ok_{path}", "type": "checkout.session.completed",
                               "data": {"object": obj}}).json()["duplicate"] is True
        s = pv.subscription(tok)
    assert (s["status"], s["plan"], s["entitled"], s["trial_days_left"], s["calls_quota"]) == ("trial", "plus", True, 14, 10)
    assert s["trial_ends_at"] == (WED_10 + timedelta(days=14)).isoformat()
    # the draft that waited for the plan is live now, paid by the plan
    db.expire_all()
    assert {t.status for t in db.query(PrivateTask).filter_by(workspace_id=pv.ws(tok))} == {"in_progress"}
    # a second checkout never carries a second trial
    sid2 = _checkout(api, tok)
    assert "trial_period_days" not in stripe.sessions[sid2]["_payload"]["subscription_data"]

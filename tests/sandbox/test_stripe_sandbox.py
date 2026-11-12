"""Stripe TEST mode through our own billing code (app/modules/billing/stripe.py, app/modules/privat/subscriptions.py).

Erhverv: the owner's card Checkout (setup mode) creates the real Stripe customer; the card is saved with Stripe's test
card (a confirmed SetupIntent with pm_card_visa – the hosted Checkout page itself needs a browser) and reaches us as a
locally signed `checkout.session.completed` webhook; one closed month is invoiced by our code; Stripe's finalized
invoice must carry exactly our price model (subscription net + 25 % Danish VAT); the invoice is paid with the test card
and the signed `invoice.paid` webhook moves our row to paid. The Stripe customer is deleted afterwards.

Privat: our subscription Checkout session (mode=subscription) is created at Stripe; its amounts must be the plan price
incl. 25 % moms. The session is expired afterwards (nothing to pay, nothing left open).

Test clocks are not used: Erhverv invoices are created explicitly by our worker (not by Stripe's billing cycle), and a
Privat subscription only exists after the hosted Checkout page is completed in a browser.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import re
import time
import uuid
from datetime import UTC, date, datetime, timedelta

import pytest

from app.config import get_settings
from app.db import get_session_factory
from app.models import BillingAccount, PrivateSubscription, ReceptionAgreement
from app.modules.billing import markets
from app.modules.billing import stripe as stripe_api

pytestmark = [pytest.mark.sandbox, pytest.mark.sandbox_stripe, pytest.mark.usefixtures("stripe_test_key")]

DUMMY_WEBHOOK_SECRET = "whsec_sandbox_dummy_not_a_real_secret"
DK_VAT_BP = markets.DK_VAT_BP


def _sign(payload: bytes) -> str:
    ts = int(time.time())
    sig = hmac.new(DUMMY_WEBHOOK_SECRET.encode(), f"{ts}.".encode() + payload, hashlib.sha256).hexdigest()
    return f"t={ts},v1={sig}"


def _webhook(client, event: dict) -> dict:
    body = json.dumps(event).encode()
    r = client.post("/api/v1/webhooks/stripe", content=body, headers={"stripe-signature": _sign(body)})
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture
def stripe_env(monkeypatch):
    """The real key stays as the environment gave it; the webhook secret is a dummy (we sign our own events) and
    Stripe Tax is off, so the invoice carries our own tax rate (the price model under test)."""
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", DUMMY_WEBHOOK_SECRET)
    monkeypatch.setenv("STRIPE_TAX_ENABLED", "false")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _not_live(obj: dict) -> dict:
    assert obj.get("livemode") is False, "sandbox: Stripe svarede med et live-mode-objekt – afbryder"
    return obj


def test_erhverv_card_invoice_tax_and_payment(api, client, db, stripe_env):
    tok = api.user("sandbox-erhverv@example.com", intent="reception")
    ws = api.workspace(tok, "Sandbox Gulvservice ApS")
    ws_id = uuid.UUID(ws)
    customer_id = None
    try:
        # The subscription (model A) was in force during last month.
        assert api.post(tok, f"/workspaces/{ws}/agreement", {"model": "A"}).status_code == 201
        this_month = date.today().replace(day=1)
        last = (this_month - timedelta(days=1)).replace(day=15)
        agreement = db.query(ReceptionAgreement).filter_by(workspace_id=ws_id).one()
        agreement.created_at = datetime.combine(last, datetime.min.time(), tzinfo=UTC) - timedelta(days=40)
        db.commit()

        # 1) Card Checkout (setup mode) through our endpoint: creates the Stripe customer and the session.
        r = api.post(tok, f"/workspaces/{ws}/billing/card/checkout")
        assert r.status_code == 200, r.text
        assert r.json()["url"].startswith("https://checkout.stripe.com/")
        db.expire_all()
        customer_id = db.query(BillingAccount).filter_by(workspace_id=ws_id).one().stripe_customer_id
        assert customer_id and customer_id.startswith("cus_")
        cust = _not_live(stripe_api.request("GET", f"/customers/{customer_id}"))
        assert cust["metadata"]["workspace_id"] == ws and cust["preferred_locales"] == ["da"]
        cs_id = re.search(r"(cs_test_[A-Za-z0-9]+)", r.json()["url"]).group(1)
        cs = _not_live(stripe_api.request("GET", f"/checkout/sessions/{cs_id}"))
        assert (cs["mode"], cs["customer"], cs["metadata"]["workspace_id"]) == ("setup", customer_id, ws)

        # 2) The card: Stripe's test card on a confirmed SetupIntent (what the hosted page does), then our webhook.
        si = _not_live(stripe_api.request("POST", "/setup_intents", {
            "customer": customer_id, "payment_method": "pm_card_visa", "payment_method_types": ["card"],
            "confirm": True, "usage": "off_session", "metadata": {"workspace_id": ws}}))
        assert si["status"] == "succeeded"
        out = _webhook(client, {"id": f"evt_sandbox_{uuid.uuid4().hex}", "type": "checkout.session.completed",
                                "data": {"object": {"id": cs_id, "mode": "setup", "setup_intent": si["id"]}}})
        assert out["outcome"] == "applied"
        acc = api.get(tok, f"/workspaces/{ws}/billing/account").json()
        assert acc["card"]["brand"] == "visa" and acc["card"]["last4"] == "4242"
        cust = stripe_api.request("GET", f"/customers/{customer_id}")
        assert cust["invoice_settings"]["default_payment_method"] == si["payment_method"]

        # 3) Last month's invoice through our endpoint; Stripe's amounts must be our price model.
        month = last.strftime("%Y-%m")
        r = api.post(tok, f"/workspaces/{ws}/billing/invoices", {"month": month})
        assert r.status_code == 201, r.text
        inv = r.json()
        monthly = markets.erhverv_price("DKK", "monthly")
        sub_lines = [x for x in inv["lines"] if x["kind"] == "subscription"]
        assert [x["net_minor"] for x in sub_lines] == [monthly]  # the subscription at the list price
        net = sum(x["net_minor"] for x in inv["lines"])
        tax = round(net * DK_VAT_BP / 10_000)
        assert (inv["currency"], inv["net_minor"], inv["tax_minor"], inv["gross_minor"]) == ("DKK", net, tax, net + tax)
        assert inv["status"] == "open" and inv["note"] is None  # no Stripe-total mismatch note
        assert inv["hosted_invoice_url"] and inv["number"]
        sinv = _not_live(stripe_api.request("GET", f"/invoices/{_stripe_invoice_id(db, inv['id'])}"))
        assert (sinv["currency"], sinv["subtotal"], sinv["total"]) == ("dkk", net, net + tax)
        assert sinv["total"] - sinv.get("total_excluding_tax", sinv["subtotal"]) == tax
        assert sinv["collection_method"] == "charge_automatically" and sinv["customer"] == customer_id
        assert "CVR-nr. 25632710" in (sinv.get("footer") or "")
        rate = stripe_api.request("GET", f"/tax_rates/{stripe_api.tax_rate_id('DK', DK_VAT_BP, False)}")
        assert (rate["percentage"], rate["inclusive"], rate["country"]) == (DK_VAT_BP / 100, False, "DK")

        # 4) Pay with the saved test card; the signed invoice.paid webhook (Stripe's real object) marks it paid.
        paid = _not_live(stripe_api.request("POST", f"/invoices/{sinv['id']}/pay", {"off_session": True}))
        assert paid["status"] == "paid" and paid["amount_paid"] == net + tax
        out = _webhook(client, {"id": f"evt_sandbox_{uuid.uuid4().hex}", "type": "invoice.paid",
                                "data": {"object": paid}})
        assert out["outcome"] == "applied"
        items = api.get(tok, f"/workspaces/{ws}/billing/invoices").json()["items"]
        assert [(i["month"], i["status"], i["gross_minor"]) for i in items] == [(month, "paid", net + tax)]
    finally:
        if customer_id:
            stripe_api.request("DELETE", f"/customers/{customer_id}")


def _stripe_invoice_id(db, invoice_id: str) -> str:
    from app.models import Invoice

    db.expire_all()
    sid = db.get(Invoice, uuid.UUID(invoice_id)).stripe_invoice_id
    assert sid and sid.startswith("in_")
    return sid


def test_privat_subscription_checkout_amounts(api, pv, stripe_env):
    """A Privat subscription Checkout (no trial left): the first payment is the plan's monthly price incl. 25 % moms."""
    tok = pv.account("sandbox-privat@example.com", trial=False)
    ws = pv.ws(tok)
    with get_session_factory()() as s:  # the one trial is used up (and never had a Stripe customer)
        row = s.get(PrivateSubscription, ws)
        row.status, row.trial_ends_at = "trial", pv.clock() - timedelta(days=1)
        s.commit()
    r = api.post(tok, "/privat/subscription/checkout", {"plan": "plus", "interval": "month"})
    assert r.status_code == 200, r.text
    cs_id = re.search(r"(cs_test_[A-Za-z0-9]+)", r.json()["url"]).group(1)
    try:
        cs = _not_live(stripe_api.request("GET", f"/checkout/sessions/{cs_id}"))
        monthly = markets.privat_plan("DKK", "plus")["monthly"]
        included_tax = round(monthly * DK_VAT_BP / (10_000 + DK_VAT_BP))  # 25 % VAT inside the price
        assert (cs["mode"], cs["currency"], cs["amount_total"]) == ("subscription", "dkk", monthly)
        assert cs["total_details"]["amount_tax"] == included_tax
        assert cs["metadata"]["kind"] == "privat_subscription" and cs["metadata"]["workspace_id"] == str(ws)
        lines = stripe_api.request("GET", f"/checkout/sessions/{cs_id}/line_items", {"limit": 10})["data"]
        assert len(lines) == 1
        price = lines[0]["price"]
        assert (price["unit_amount"], price["tax_behavior"], price["recurring"]["interval"]) == (monthly, "inclusive", "month")
    finally:
        stripe_api.request("POST", f"/checkout/sessions/{cs_id}/expire")

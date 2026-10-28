"""Stripe billing: card via Checkout (setup mode), one invoice per closed month from the statement,
signed webhooks, honest 501 without keys, and payment never touching calls."""
from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid
from datetime import UTC, date, datetime, timedelta

import pytest

from app.config import get_settings
from app.core.errors import Unauthenticated
from app.models import BillingAccount, Invoice
from app.modules.billing import stripe

WH_SECRET = "whsec_test_0123456789abcdef"


class FakeStripe:
    def __init__(self):
        self.calls: list[tuple[str, str, dict, str | None]] = []
        self.n = 0

    def __call__(self, method, path, data=None, *, idempotency_key=None):
        self.calls.append((method, path, data or {}, idempotency_key))
        self.n += 1
        if path == "/customers":
            return {"id": "cus_1"}
        if path == "/checkout/sessions":
            return {"id": "cs_1", "url": "https://checkout.stripe.com/c/pay/cs_1"}
        if path.startswith("/setup_intents/"):
            return {"id": "seti_1", "status": "succeeded", "payment_method": "pm_1", "customer": "cus_1",
                    "metadata": {"workspace_id": self.ws}}
        if path.startswith("/payment_methods/"):
            return {"id": "pm_1", "card": {"brand": "visa", "last4": "4242", "exp_month": 4, "exp_year": 2030}}
        if path == "/tax_rates" and method == "GET":
            return {"data": []}
        if path == "/tax_rates":
            return {"id": "txr_1"}
        if path == "/invoices":
            return {"id": "in_1", "status": "draft"}
        if path.endswith("/finalize"):
            return {"id": "in_1", "status": "open", "number": "DB-0001", "hosted_invoice_url": "https://invoice.stripe.com/i/1",
                    "invoice_pdf": "https://pay.stripe.com/invoice/1/pdf", "total": self.total}
        return {"id": f"obj_{self.n}"}


def _sign(payload: bytes, secret=WH_SECRET, ts=None) -> str:
    ts = ts or int(time.time())
    return f"t={ts},v1={hmac.new(secret.encode(), f'{ts}.'.encode() + payload, hashlib.sha256).hexdigest()}"


def test_signature():
    body = b'{"a":1}'
    stripe.verify_signature(WH_SECRET, _sign(body), body)
    with pytest.raises(Unauthenticated):
        stripe.verify_signature(WH_SECRET, _sign(body, "whsec_other"), body)
    with pytest.raises(Unauthenticated):
        stripe.verify_signature(WH_SECRET, _sign(body, ts=int(time.time()) - 3600), body)
    assert ("card[number]", "x") not in stripe._flatten({"a": {"b": [1, {"c": True}]}})
    assert stripe._flatten({"a": {"b": [1, {"c": True}]}}) == [("a[b][0]", "1"), ("a[b][1][c]", "true")]


def test_not_configured(api, two_workspaces, monkeypatch):
    monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
    get_settings.cache_clear()
    t = two_workspaces
    r = api.post(t["tok_a"], f"/workspaces/{t['ws_a']}/billing/card/checkout")
    assert r.status_code == 501 and r.json()["code"] == "payment_not_configured"
    acc = api.get(t["tok_a"], f"/workspaces/{t['ws_a']}/billing/account").json()
    assert acc["configured"] is False and acc["card"] is None
    get_settings.cache_clear()


def test_card_invoice_and_webhooks(api, client, two_workspaces, db, monkeypatch):
    t = two_workspaces
    tok, ws = t["tok_a"], t["ws_a"]
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_dummy")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", WH_SECRET)
    get_settings.cache_clear()
    fake = FakeStripe()
    fake.ws = ws
    monkeypatch.setattr(stripe, "request", fake)
    monkeypatch.setattr(stripe, "_tax_rate_id", None)
    # only the owner handles cards; admins can read
    admin = api.add_member(tok, ws, "admin-bill@testmail.dk", "admin")
    assert api.post(admin, f"/workspaces/{ws}/billing/card/checkout").status_code == 403
    r = api.post(tok, f"/workspaces/{ws}/billing/card/checkout")
    assert r.status_code == 200 and r.json()["url"].startswith("https://checkout.stripe.com/")
    sess = next(c for c in fake.calls if c[1] == "/checkout/sessions")[2]
    assert sess["mode"] == "setup" and sess["customer"] == "cus_1"
    # the signed webhook saves the card
    event = json.dumps({"id": "evt_1", "type": "checkout.session.completed",
                        "data": {"object": {"mode": "setup", "setup_intent": "seti_1"}}}).encode()
    bad = client.post("/api/v1/webhooks/stripe", content=event, headers={"stripe-signature": _sign(event, "whsec_x")})
    assert bad.status_code == 401
    ok = client.post("/api/v1/webhooks/stripe", content=event, headers={"stripe-signature": _sign(event)})
    assert ok.status_code == 200 and ok.json()["outcome"] == "applied"
    acc = api.get(tok, f"/workspaces/{ws}/billing/account").json()
    assert acc["card"] == {"brand": "visa", "last4": "4242", "exp": "04/30"}
    # a month on the subscription (2.495 kr.) plus three campaign calls (3 × 4 kr.) → one invoice, + 25 % moms
    from app.models import Campaign, CampaignCall, CampaignContact, ReceptionAgreement

    assert api.post(tok, f"/workspaces/{ws}/agreement", {"model": "A"}).status_code == 201
    this_month = date.today().replace(day=1)
    last = (this_month - timedelta(days=1)).replace(day=15)
    at = datetime.combine(last, datetime.min.time(), tzinfo=UTC)
    agreement = db.query(ReceptionAgreement).filter_by(workspace_id=uuid.UUID(ws)).one()
    agreement.created_at = at - timedelta(days=40)  # the agreement was in force during last month
    camp = Campaign(workspace_id=uuid.UUID(ws), name="Forårstilbud", call_net_minor=400, max_attempts=2,
                    max_connected_seconds=180)
    db.add(camp)
    db.flush()
    contact = CampaignContact(campaign_id=camp.id, workspace_id=uuid.UUID(ws), phone="+4520304050", kind="business")
    db.add(contact)
    db.flush()
    for i in range(3):
        db.add(CampaignCall(workspace_id=uuid.UUID(ws), campaign_id=camp.id, contact_id=contact.id,
                            dialled_at=at + timedelta(hours=i), net_minor=400))
    db.commit()
    fake.total = 313_375  # (249.500 + 1.200) + 25 %
    assert api.post(tok, f"/workspaces/{ws}/billing/invoices", {"month": this_month.strftime("%Y-%m")}).status_code == 422
    month = last.strftime("%Y-%m")
    r = api.post(tok, f"/workspaces/{ws}/billing/invoices", {"month": month})
    assert r.status_code == 201, r.text
    inv = r.json()
    assert (inv["status"], inv["gross_minor"], inv["number"], inv["note"]) == ("open", 313_375, "DB-0001", None)
    items = [c for c in fake.calls if c[1] == "/invoiceitems"]
    assert [i[2]["amount"] for i in items] == [249_500, 1_200]  # the subscription, then the 3 calls
    created = next(c for c in fake.calls if c[1] == "/invoices")
    assert "CVR-nr. 25632710" in created[2]["footer"]
    assert created[2]["default_tax_rates"] == ["txr_1"] and created[3] == f"dialogbot-invoice-{ws}-{month}"
    # idempotent: the same month again returns the same invoice and calls Stripe no more
    before = len(fake.calls)
    assert api.post(tok, f"/workspaces/{ws}/billing/invoices", {"month": month}).json()["id"] == inv["id"]
    assert len(fake.calls) == before
    paid = json.dumps({"id": "evt_2", "type": "invoice.paid", "data": {"object": {"id": "in_1", "status": "paid"}}}).encode()
    assert client.post("/api/v1/webhooks/stripe", content=paid, headers={"stripe-signature": _sign(paid)}).json()["outcome"] == "applied"
    items = api.get(tok, f"/workspaces/{ws}/billing/invoices").json()["items"]
    assert items[0]["status"] == "paid" and items[0]["hosted_invoice_url"]
    assert db.query(Invoice).count() >= 1 and db.query(BillingAccount).filter_by(workspace_id=uuid.UUID(ws)).one().card_last4 == "4242"
    get_settings.cache_clear()

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
from app.models import BillingAccount, Invoice, Lead
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
    # a model-B month with one approved lead → one invoice of 149 kr. + 25 % moms
    assert api.post(tok, f"/workspaces/{ws}/agreement", {"model": "B"}).status_code == 201
    lead = api.post(tok, f"/workspaces/{ws}/leads", {"contact_name": "Mette", "contact_phone": "+4520304050",
                                                     "need_summary": "Tilbud"}).json()
    q = api.c.patch(f"{api.base}/workspaces/{ws}/leads/{lead['id']}", headers=api.h(tok),
                    json={"expected_version": lead["version"], "qualification_status": "qualified"})
    assert q.status_code == 200, q.text
    assert api.post(tok, f"/workspaces/{ws}/leads/{lead['id']}/approve", {}).status_code == 200
    fake.total = 18625
    this_month = date.today().replace(day=1)
    assert api.post(tok, f"/workspaces/{ws}/billing/invoices", {"month": this_month.strftime("%Y-%m")}).status_code == 422
    last = (this_month - timedelta(days=1)).replace(day=15)
    row = db.get(Lead, uuid.UUID(lead["id"]))
    db.refresh(row)
    row.billing_decided_at = datetime.combine(last, datetime.min.time(), tzinfo=UTC)  # approved last month
    db.commit()
    month = last.strftime("%Y-%m")
    r = api.post(tok, f"/workspaces/{ws}/billing/invoices", {"month": month})
    assert r.status_code == 201, r.text
    inv = r.json()
    assert (inv["status"], inv["gross_minor"], inv["number"], inv["note"]) == ("open", 18625, "DB-0001", None)
    items = [c for c in fake.calls if c[1] == "/invoiceitems"]
    assert len(items) == 1 and items[0][2]["amount"] == 14900
    created = next(c for c in fake.calls if c[1] == "/invoices")
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
    assert db.query(Lead).filter(Lead.workspace_id == uuid.UUID(ws)).count() == 1
    get_settings.cache_clear()

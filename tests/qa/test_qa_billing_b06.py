"""QA billing-qa · B06 – invoices: list/detail, download, pending/paid/failed/adjusted states; Stripe Tax amounts;
webhook replay / out-of-order; refunds and credit notes (DB-012: duplicate event has no second effect).
Stripe is never called: the invoice rows are created locally and webhooks are signed with a local secret."""
from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid
from datetime import UTC, date, datetime, timedelta

import pytest

from app.config import get_settings
from app.models import Ambassador, CommissionEntry, Invoice, Referral
from app.modules.billing import stripe as stripe_api

SECRET = "whsec_qa_bill_b06"
NET, TAX, GROSS = 249_500, 62_375, 311_875          # one month of the subscription, 25 % moms


@pytest.fixture
def wh(client, monkeypatch):
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_qa_bill")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", SECRET)
    get_settings.cache_clear()

    def no_network(*a, **k):
        raise AssertionError("no Stripe network calls in QA")

    monkeypatch.setattr(stripe_api, "request", no_network)

    def send(eid, kind, obj, created=None):
        ev = {"id": eid, "type": kind, "data": {"object": obj}}
        if created:
            ev["created"] = created
        body = json.dumps(ev).encode()
        ts = int(time.time())
        sig = hmac.new(SECRET.encode(), f"{ts}.".encode() + body, hashlib.sha256).hexdigest()
        r = client.post("/api/v1/webhooks/stripe", content=body, headers={"stripe-signature": f"t={ts},v1={sig}"})
        assert r.status_code == 200, r.text
        return r.json()

    yield send
    get_settings.cache_clear()


def _invoice(db, ws, sid="in_qa_b06", status="open", month=date(2026, 10, 1)):
    inv = Invoice(workspace_id=uuid.UUID(ws), month=month, status=status, currency="DKK", net_minor=NET, tax_minor=TAX,
                  gross_minor=GROSS, lines=[{"kind": "subscription", "net_minor": NET}], stripe_invoice_id=sid,
                  tax_source="manual")
    db.add(inv)
    db.commit()
    return inv


def _status(api, tok, ws):
    return {i["id"]: i for i in api.get(tok, f"/workspaces/{ws}/billing/invoices").json()["items"]}


def test_b06_states_open_paid_failed_void_and_download_links(api, two_workspaces, db, wh):
    tok, ws = two_workspaces["tok_a"], two_workspaces["ws_a"]
    a = _invoice(db, ws, "in_qa_a")
    b = _invoice(db, ws, "in_qa_b", month=date(2026, 9, 1))
    c = _invoice(db, ws, "in_qa_c", month=date(2026, 8, 1))
    assert wh("evt_b06_1", "invoice.paid", {"id": "in_qa_a", "status": "paid", "total": GROSS, "number": "DB-QA-1",
                                            "hosted_invoice_url": "https://invoice.stripe.com/i/qa",
                                            "invoice_pdf": "https://pay.stripe.com/invoice/qa/pdf"})["outcome"] == "applied"
    assert wh("evt_b06_2", "invoice.payment_failed", {"id": "in_qa_b", "status": "open", "total": GROSS})["outcome"] == "applied"
    assert wh("evt_b06_3", "invoice.marked_uncollectible", {"id": "in_qa_c", "status": "uncollectible"})["outcome"] == "applied"
    rows = _status(api, tok, ws)
    assert (rows[str(a.id)]["status"], rows[str(b.id)]["status"], rows[str(c.id)]["status"]) == ("paid", "payment_failed", "failed")
    assert rows[str(a.id)]["invoice_pdf"].endswith("/pdf") and rows[str(a.id)]["number"] == "DB-QA-1"
    assert (rows[str(a.id)]["net_minor"], rows[str(a.id)]["tax_minor"], rows[str(a.id)]["gross_minor"]) == (NET, TAX, GROSS)
    assert rows[str(a.id)]["note"] is None                                   # Stripe total == our gross
    # a mismatching Stripe total is flagged, not silently overwritten
    wh("evt_b06_4", "invoice.finalized", {"id": "in_qa_c", "status": "uncollectible", "total": GROSS + 1})
    assert "afviger" in _status(api, tok, ws)[str(c.id)]["note"]
    # replay of the same event id: no second effect
    assert wh("evt_b06_1", "invoice.paid", {"id": "in_qa_a", "status": "paid"})["outcome"] == "duplicate"


def test_b06_a_late_payment_failed_event_must_not_reopen_a_paid_invoice(api, two_workspaces, db, wh):
    """Stripe does not guarantee order: the failed first attempt's invoice.payment_failed (created earlier) can arrive
    after invoice.paid (the retry succeeded). The invoice is paid."""
    tok, ws = two_workspaces["tok_a"], two_workspaces["ws_a"]
    inv = _invoice(db, ws, "in_qa_order")
    t0 = int(time.time()) - 600
    wh("evt_b06_o2", "invoice.paid", {"id": "in_qa_order", "status": "paid", "total": GROSS}, created=t0 + 300)
    wh("evt_b06_o1", "invoice.payment_failed", {"id": "in_qa_order", "status": "open", "total": GROSS}, created=t0)
    assert _status(api, tok, ws)[str(inv.id)]["status"] == "paid"


def test_b06_stripe_tax_amounts_come_from_stripe():
    inv = Invoice(workspace_id=uuid.uuid4(), month=date(2026, 10, 1), status="creating", currency="DKK",
                  net_minor=NET, tax_minor=TAX, gross_minor=GROSS, lines=[])
    stripe_api._amounts_from_stripe(inv, {"total": 311_876, "total_excluding_tax": 249_500,
                                          "total_taxes": [{"amount": 62_376}]})
    assert (inv.net_minor, inv.tax_minor, inv.gross_minor) == (249_500, 62_376, 311_876)
    inv2 = Invoice(workspace_id=uuid.uuid4(), month=date(2026, 10, 1), status="creating", currency="DKK",
                   net_minor=0, tax_minor=0, gross_minor=0, lines=[])
    stripe_api._amounts_from_stripe(inv2, {"total": 249_500, "total_excluding_tax": 249_500, "total_taxes": []})
    assert (inv2.net_minor, inv2.tax_minor, inv2.gross_minor) == (249_500, 0, 249_500)  # reverse charge


# --------------------------------------------------------------------------- refunds / credit notes → commission

def _commission_setup(api, two_workspaces, db):
    tok_b = two_workspaces["tok_b"]
    me = api.c.get("/api/v1/auth/me", headers=api.h(tok_b)).json()
    uid = uuid.UUID(me.get("id") or me["user"]["id"])
    amb = Ambassador(user_id=uid, status="active", kind="company", slug=f"qa-bill-{uid.hex[:6]}",
                     code=f"QAB{uid.hex[:6].upper()}", full_name="QA Ambassadør", rate_bp=1000, months=12, bonus_minor=0,
                     rules_version="qa", rules_accepted_at=datetime.now(UTC))
    db.add(amb)
    db.flush()
    ws = uuid.UUID(two_workspaces["ws_a"])
    db.add(Referral(workspace_id=ws, ambassador_id=amb.id, via="link"))
    inv = _invoice(db, str(ws), "in_qa_refund", status="paid")
    share = CommissionEntry(ambassador_id=amb.id, workspace_id=ws, invoice_id=inv.id, kind="share", month=inv.month,
                            base_minor=NET, amount_minor=24_950, status="held",
                            hold_until=datetime.now(UTC) + timedelta(days=30))
    db.add(share)
    db.commit()
    return share.id


def test_b06_two_partial_refunds_reduce_commission_by_the_refunded_share_once(api, two_workspaces, db, wh):
    """Commission 10 % of 2.495 kr. = 249,50 kr. Refund 20 % (623,75 kr.), later another 20 %: Stripe's charge.refunded
    carries the CUMULATIVE amount_refunded (1.247,50 kr. = 40 %). Expected remaining: 60 % × 24.950 = 14.970 øre."""
    sid = _commission_setup(api, two_workspaces, db)
    wh("evt_b06_r1", "charge.refunded", {"id": "ch_qa_1", "invoice": "in_qa_refund", "amount_refunded": 62_375})
    db.expire_all()
    assert db.get(CommissionEntry, sid).amount_minor == 19_960
    wh("evt_b06_r2", "charge.refunded", {"id": "ch_qa_1", "invoice": "in_qa_refund", "amount_refunded": 124_750})
    db.expire_all()
    assert db.get(CommissionEntry, sid).amount_minor == 14_970


def test_b06_one_refund_reported_as_refund_and_credit_note_counts_once(api, two_workspaces, db, wh):
    """A refund made through a credit note emits credit_note.created AND charge.refunded for the same 20 %."""
    sid = _commission_setup(api, two_workspaces, db)
    wh("evt_b06_cn", "credit_note.created", {"id": "cn_qa_1", "invoice": "in_qa_refund", "total": 62_375})
    wh("evt_b06_ch", "charge.refunded", {"id": "ch_qa_2", "invoice": "in_qa_refund", "amount_refunded": 62_375})
    db.expire_all()
    assert db.get(CommissionEntry, sid).amount_minor == 19_960


def test_b06_invoice_detail_route_and_adjusted_state_are_not_built(app):
    from app.models import Invoice as Inv

    paths = [getattr(r, "path", "") for r in app.routes]
    assert not [p for p in paths if p.rstrip("/").endswith("/invoices/{invoice_id}")]
    ck = [c for c in Inv.__table__.constraints if getattr(c, "name", "") == "ck_invoices_status"][0]
    assert "adjusted" not in str(ck.sqltext)

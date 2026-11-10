"""QA billing-qa · minutpakke-model (Fürster 2026-11-10): "a package = the subscription's included minutes; usage
beyond is billed". Gap analysis for C09, C15, M04, B03, B04, B05 – see qa/billing/minutpakker-gap.md.

Price rules (source of truth, billing-qa agent definition): subscription 2.495 kr./md. with 300 inbound minutes
included, 1,50 kr. per started inbound minute above; campaign calls 4 kr. + 2 kr. per started minute (not part of the
included minutes). 25 % VAT, half-up on the total, minor units, calendar months in Europe/Copenhagen.

Expected numbers are computed by hand here, never by calling the code under test. Stripe is never called: the
`request` function is replaced by a local fake (no network).

- pass  = the minute-package rule is built and proven;
- fail  = a defect (finding F-BQ-011 / F-BQ-012);
- xfail(strict) = not built (turns red when it is built, so the gap table must be updated).
"""
from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

import pytest

from app.models import BillingAccount, Call, ReceptionAgreement, Workspace

SUB = 249_500          # 2.495 kr./md.
INCLUDED = 300         # inbound minutes in the package
EXTRA = 150            # 1,50 kr. per started inbound minute above the package


def _agreement(db, ws, at=datetime(2026, 8, 1, tzinfo=UTC)):
    db.add(ReceptionAgreement(workspace_id=ws, version=1, model="A", monthly_net_minor=SUB, lead_fee_net_minor=0,
                              created_at=at))


def _inbound(db, ws, at, seconds, tag=""):
    db.add(Call(workspace_id=ws, provider="vapi", provider_call_id=f"mp_{tag}{uuid.uuid4().hex[:12]}", started_at=at,
                duration_seconds=seconds))


def _statement(api, tok, ws, month):
    r = api.get(tok, f"/workspaces/{ws}/billing/statement?month={month}")
    assert r.status_code == 200, r.text
    return r.json()


def _line(st, kind):
    xs = [x for x in st["lines"] if x["kind"] == kind]
    return xs[0] if xs else None


# --------------------------------------------------------------------------- (a) what the package is today

def test_mp_one_package_level_300_inbound_minutes_shown_as_used_of_included(api, two_workspaces, db):
    """Today there is exactly one package: the subscription with 300 inbound minutes. The customer's month-to-date
    preview carries used / included / over and the overage amount (Konto reads exactly these fields)."""
    from app.modules.billing import markets, prices

    ws = uuid.UUID(two_workspaces["ws_a"])
    tok = two_workspaces["tok_a"]
    assert prices.INBOUND_INCLUDED_MINUTES == INCLUDED
    assert all("included" not in k for k in markets.ERHVERV["DKK"])  # no per-tier / per-market minute allowance
    plan = api.get(tok, f"/workspaces/{ws}/agreement").json()["plan"]
    assert (plan["inbound_included_minutes"], plan["inbound_extra_minute_net_minor"]) == (INCLUDED, EXTRA)
    _agreement(db, ws)
    _inbound(db, ws, datetime(2026, 9, 3, 8, tzinfo=UTC), 250 * 60)
    db.commit()
    line = _line(_statement(api, tok, ws, "2026-09"), "inbound_minutes")
    # used 250 of 300 → 50 left, nothing over
    assert (line["minutes"], line["included_minutes"], line["extra_minutes"], line["net_minor"]) == (250, 300, 0, 0)
    _inbound(db, ws, datetime(2026, 9, 20, 8, tzinfo=UTC), 61 * 60 + 1)   # 62 started minutes → 312
    db.commit()
    st = _statement(api, tok, ws, "2026-09")
    line = _line(st, "inbound_minutes")
    assert (line["minutes"], line["extra_minutes"], line["net_minor"]) == (312, 12, 12 * EXTRA)       # 1.800
    assert "12 min ekstra" in line["description"] and "1,50\u00a0kr." in line["description"]
    # 249.500 + 1.800 = 251.300 net; 25 % = 62.825; gross 314.125
    assert (st["totals"]["net_minor"], st["totals"]["tax_minor"], st["totals"]["gross_minor"]) == (251_300, 62_825, 314_125)


# --------------------------------------------------------------------------- price snapshot of the package (defect)

def test_mp_package_terms_are_snapshotted_per_agreement_not_read_from_the_list_price(api, two_workspaces, db, monkeypatch):
    """F-BQ-011. The agreement snapshots the monthly price but NOT the package (included minutes) or the overage
    price: statement.py reads prices.INBOUND_INCLUDED_MINUTES and markets.erhverv_price(...,'extra_minute') at the
    time the statement is made. A list change therefore rewrites every month that is not yet invoiced for every
    customer on an older agreement. Expected (rule "price change does not alter old orders"): September under the
    August agreement stays 300 included / 1,50 kr. → 310 min = 10 × 150 = 1.500."""
    from app.modules.billing import markets, prices

    ws = uuid.UUID(two_workspaces["ws_a"])
    tok = two_workspaces["tok_a"]
    _agreement(db, ws)
    _inbound(db, ws, datetime(2026, 9, 10, 9, tzinfo=UTC), 310 * 60)
    db.commit()
    before = _line(_statement(api, tok, ws, "2026-09"), "inbound_minutes")
    assert (before["extra_minutes"], before["net_minor"]) == (10, 1_500)
    # the list changes later (smaller package, dearer overage) – only NEW agreements may get it
    monkeypatch.setattr(prices, "INBOUND_INCLUDED_MINUTES", 200)
    monkeypatch.setattr(prices, "INBOUND_EXTRA_MINUTE_NET_MINOR", 300)
    monkeypatch.setitem(markets.ERHVERV["DKK"], "extra_minute", 300)
    after = _line(_statement(api, tok, ws, "2026-09"), "inbound_minutes")
    assert (after["included_minutes"], after["extra_minutes"], after["net_minor"]) == (300, 10, 1_500), after


def test_mp_agreement_row_has_no_column_for_the_package_terms():
    """Root cause of F-BQ-011, stated as a schema fact: the sales offer snapshots inbound_included_minutes and
    inbound_extra_minute_net_minor, the agreement made from it drops them."""
    from app.models.sales import SalesOffer

    offer_cols = set(SalesOffer.__table__.columns.keys())
    agr_cols = set(ReceptionAgreement.__table__.columns.keys())
    assert {"inbound_included_minutes", "inbound_extra_minute_net_minor"} <= offer_cols
    assert not ({"inbound_included_minutes", "inbound_extra_minute_net_minor"} & agr_cols)


# --------------------------------------------------------------------------- month close / reconciliation (defect)

@pytest.fixture
def fake_stripe(monkeypatch):
    from app.config import get_settings
    from app.modules.billing import stripe as stripe_api

    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_qa_bill_mp")
    monkeypatch.delenv("STRIPE_TAX_ENABLED", raising=False)
    get_settings.cache_clear()
    sent: list[tuple[str, str, dict]] = []

    def fake(method, path, data=None, **_k):
        sent.append((method, path, dict(data or {})))
        if path == "/invoices":
            return {"id": "in_qa_mp", "status": "draft"}
        if path.endswith("/finalize"):
            return {"id": "in_qa_mp", "status": "open", "number": "QA-MP-1"}
        if path.startswith("/tax_rates"):
            return {"id": "txr_qa", "data": [{"id": "txr_qa", "percentage": 25, "inclusive": False, "active": True,
                                              "country": "DK", "metadata": {}}]}
        return {"id": f"ii_{len(sent)}"}

    monkeypatch.setattr(stripe_api, "request", fake)
    monkeypatch.setattr(stripe_api, "tax_rate_id", lambda *a, **k: "txr_qa")
    yield sent
    get_settings.cache_clear()


def test_mp_overage_reaches_the_stripe_invoice_and_the_invoice_keeps_the_period_snapshot(two_workspaces, db, fake_stripe):
    """The overage is an invoice line at Stripe (description + amount) and invoices.lines freezes the period."""
    from app.modules.billing import stripe as stripe_api

    ws_id = uuid.UUID(two_workspaces["ws_a"])
    _agreement(db, ws_id)
    _inbound(db, ws_id, datetime(2026, 10, 5, 9, tzinfo=UTC), 310 * 60)
    db.add(BillingAccount(workspace_id=ws_id, stripe_customer_id="cus_qa_mp", payment_method_id="pm_qa_mp"))
    db.commit()
    inv = stripe_api.create_invoice(db, db.get(Workspace, ws_id), date(2026, 10, 1), "Europe/Copenhagen")
    db.commit()
    items = [d for m, p, d in fake_stripe if p == "/invoiceitems"]
    assert sorted(i["amount"] for i in items) == [1_500, SUB]
    over = next(i for i in items if i["metadata"]["kind"] == "inbound_minutes")
    assert "310 min" in over["description"] and "10 min ekstra" in over["description"]
    # 251.000 net, 62.750 moms, 313.750 brutto
    assert (inv.net_minor, inv.tax_minor, inv.gross_minor) == (251_000, 62_750, 313_750)
    frozen = next(x for x in inv.lines if x["kind"] == "inbound_minutes")
    assert (frozen["minutes"], frozen["extra_minutes"], frozen["net_minor"]) == (310, 10, 1_500)


def test_mp_usage_reported_after_the_month_was_invoiced_is_billed_somewhere(api, two_workspaces, db, fake_stripe):
    """F-BQ-012. invoice_due invoices last month on the first worker tick after local midnight, without a grace
    period. A call that starts 31/10 23:58 local (22:58Z, CET) is stored when its end-of-call report arrives – after
    the invoice. Its minutes belong to October (statement counts by started_at) but October is frozen and November
    does not pick them up, so they are never billed. Expected: October 310 + 5 = 315 min → 15 extra = 2.250 in total
    across the October invoice and any adjustment/carry-over."""
    from app.modules.billing import stripe as stripe_api

    ws_id = uuid.UUID(two_workspaces["ws_a"])
    tok = two_workspaces["tok_a"]
    _agreement(db, ws_id)
    _inbound(db, ws_id, datetime(2026, 10, 5, 9, tzinfo=UTC), 310 * 60)
    db.add(BillingAccount(workspace_id=ws_id, stripe_customer_id="cus_qa_mp", payment_method_id="pm_qa_mp"))
    db.commit()
    inv = stripe_api.create_invoice(db, db.get(Workspace, ws_id), date(2026, 10, 1), "Europe/Copenhagen")
    db.commit()
    invoiced = next(x for x in inv.lines if x["kind"] == "inbound_minutes")["net_minor"]
    assert invoiced == 1_500
    # the late end-of-call report: started in October (local), stored after the invoice
    _inbound(db, ws_id, datetime(2026, 10, 31, 22, 58, tzinfo=UTC), 5 * 60, tag="late")
    db.commit()
    octo_now = _line(_statement(api, tok, ws_id, "2026-10"), "inbound_minutes")["net_minor"]
    assert octo_now == 2_250  # the preview of the (already invoiced) month has silently moved
    nov = _line(_statement(api, tok, ws_id, "2026-11"), "inbound_minutes")
    carried = nov["net_minor"] if nov else 0
    adjustments = [x for x in _statement(api, tok, ws_id, "2026-11")["lines"] if "adjust" in x["kind"]]
    assert invoiced + carried + sum(x["net_minor"] for x in adjustments) == 2_250, \
        f"750 øre (5 min × 1,50 kr.) never billed: invoice {invoiced}, November carries {carried}"


# --------------------------------------------------------------------------- visibility (not built)

@pytest.mark.xfail(strict=True, reason="B05/minutpakke: invoice API does not expose the frozen period lines")
def test_mp_customer_can_read_the_frozen_package_usage_of_an_invoiced_month(api, two_workspaces, db):
    from app.models import Invoice

    ws = uuid.UUID(two_workspaces["ws_a"])
    db.add(Invoice(workspace_id=ws, month=date(2026, 10, 1), status="open", currency="DKK", net_minor=251_000,
                   tax_minor=62_750, gross_minor=313_750, stripe_invoice_id="in_qa_mp_vis", tax_source="manual",
                   lines=[{"kind": "subscription", "net_minor": SUB},
                          {"kind": "inbound_minutes", "minutes": 310, "included_minutes": 300, "extra_minutes": 10,
                           "net_minor": 1_500}]))
    db.commit()
    item = api.get(two_workspaces["tok_a"], f"/workspaces/{ws}/billing/invoices").json()["items"][0]
    assert any(x.get("kind") == "inbound_minutes" and x.get("extra_minutes") == 10 for x in item.get("lines", []))


@pytest.mark.xfail(strict=True, reason="M04/minutpakke: operator customer view has no package, usage or overage")
def test_mp_operator_sees_package_usage_per_customer(api, two_workspaces, db):
    ws = uuid.UUID(two_workspaces["ws_a"])
    _agreement(db, ws)
    _inbound(db, ws, datetime.now(UTC), 310 * 60)
    db.commit()
    body = api.get(api.operator(), f"/operator/admin/customers/{ws}").json()
    assert "agreement" in body and "usage" in body, sorted(body)


@pytest.mark.xfail(strict=True, reason="B03/B04/minutpakke: no way to dispute/credit a failed inbound call's minutes")
def test_mp_failed_call_minutes_can_be_disputed_or_credited(app):
    from qa_sec_helpers import all_routes

    paths = [p for _m, p, _r in all_routes(app) if "/privat/" not in p]  # Privat credit packs are another product
    assert any(("dispute" in p or "credit" in p) or ("/calls/" in p and "billing" in p) for p in paths), "no route"

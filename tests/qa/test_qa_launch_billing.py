"""Launch requirements C09, C15, B03, B04, B05, M04 in the CURRENT price model (A', Fürster 2026-11-10, final 20:28).

The expected numbers are worked out by hand from the price rules (docs/pricing.md, app/modules/billing/prices.py), not
read from the code:
- one plan: 2.495 kr./md. excl. VAT with ONE package of 300 started minutes a calendar month (Europe/Copenhagen) that
  inbound calls and outbound campaign calls use together, in the order the calls happen;
- inside the package no price per call; above it 1,50 kr. per started inbound minute and 2 kr. per started outbound
  minute; an outbound call that STARTS after the package is used up also costs 4 kr. (answered) / 1 kr. (voicemail) /
  0,25 kr. (unanswered/busy, or no report yet); a call that crosses the limit only splits its minutes;
- at most 2 attempts and 3 minutes per contact = at most 14 kr. per contact;
- demo calls and the owner's test calls never count; minutes are credited only after an approved complaint;
- 25 % VAT, half up on the total.

The month used is November 2026 (the first month of the shared package). Scenario ids are in the test names; the
scenario texts in qa/scenarios.csv were rewritten to this model on 2026-11-12 (fix-engineer #26).
"""
from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest

from app.config import get_settings
from app.models import (
    BillingAccount,
    Call,
    Campaign,
    CampaignCall,
    CampaignContact,
    DemoCall,
    Invoice,
    ReceptionAgreement,
    TelephonyTest,
)

SECRET = "vapi-test-secret-0123456789abcdef"
NOV = "2026-11"


def _at(day: int, hour: int = 9, month: int = 11, minute: int = 0) -> datetime:
    return datetime(2026, month, day, hour, minute, tzinfo=UTC)


def _month(db, ws: uuid.UUID) -> dict:
    """November 2026 for one customer, in call order (CET = UTC+1):

    | # | when (UTC)  | call                         | started min | package left after | extra | price            |
    |---|-------------|------------------------------|-------------|--------------------|-------|------------------|
    | 1 | 2/11 09:00  | inbound 17.400 s             | 290         | 10                 | 0     | 0                |
    | 2 | 3/11 09:00  | campaign A answered 330 s    | 6           | 4                  | 0     | 0 (in package)   |
    | 3 | 4/11 09:00  | inbound 61 s                 | 2           | 2                  | 0     | 0                |
    | 4 | 5/11 09:00  | campaign B answered 181 s    | 4           | 0                  | 2     | 2 × 2 = 4,00     |
    |   |             | (crosses the limit: minutes only, no call price)                                 |
    | 5 | 6/11 09:00  | campaign C voicemail         | 0           | 0                  | 0     | 1,00             |
    | 6 | 7/11 09:00  | campaign D unanswered        | 0           | 0                  | 0     | 0,25             |
    | 7 | 8/11 09:00  | campaign E, no report yet    | 0 (pending) | 0                  | 0     | 0,25 (cheapest)  |
    | 8 | 9/11 09:00  | inbound 125 s                | 3           | 0                  | 3     | 3 × 1,50 = 4,50  |
    | – | 10/11       | demo call 600 s, owner's test call 300 s – never usage                           |
    | – | 30/11 23:30 | inbound 60 s = 1/12 00:30 in Copenhagen – December, not November                 |

    Package: 305 of 300 used, 5 over. Usage 4,00 + 1,00 + 0,25 + 0,25 + 4,50 = 10,00 kr.
    Month: 2.495,00 + 10,00 = 2.505,00 kr. excl. VAT, 626,25 VAT, 3.131,25 incl. VAT.
    """
    db.add(ReceptionAgreement(workspace_id=ws, version=1, model="A", monthly_net_minor=249_500,
                              created_at=datetime(2026, 8, 1, tzinfo=UTC)))
    camp = Campaign(workspace_id=ws, name="Vinter", call_net_minor=0, minute_net_minor=200, max_attempts=2,
                    max_connected_seconds=180, status="running")
    db.add(camp)
    db.flush()
    contacts = []
    for i in range(5):
        c = CampaignContact(campaign_id=camp.id, workspace_id=ws, phone=f"+452030405{i}", kind="business", attempts=1,
                            status="done")
        db.add(c)
        contacts.append(c)
    db.flush()

    def inbound(name, at, seconds):
        return Call(workspace_id=ws, provider="vapi", provider_call_id=f"lb_{name}_{uuid.uuid4().hex[:6]}", started_at=at,
                    duration_seconds=seconds, from_number="+4540000000")

    def outbound(i, at, seconds, outcome):
        return CampaignCall(workspace_id=ws, campaign_id=camp.id, contact_id=contacts[i].id, net_minor=0, dialled_at=at,
                            provider_call_id=f"lb_out{i}_{uuid.uuid4().hex[:6]}", connected_seconds=seconds,
                            outcome_class=outcome)

    r = {"campaign": camp,
         "in1": inbound("in1", _at(2), 290 * 60), "A": outbound(0, _at(3), 330, "answered"),
         "in2": inbound("in2", _at(4), 61), "B": outbound(1, _at(5), 181, "answered"),
         "C": outbound(2, _at(6), 0, "voicemail"), "D": outbound(3, _at(7), 0, "no_answer"),
         "E": outbound(4, _at(8), None, None), "in3": inbound("in3", _at(9), 125),
         "dec": inbound("dec", _at(30, 23, minute=30), 60)}
    demo = inbound("demo", _at(10), 600)
    test = inbound("test", _at(10, 10), 300)
    db.add_all([v for k, v in r.items() if k != "campaign"] + [demo, test])
    db.add(DemoCall(workspace_id=ws, source="web", phone="+4520304050", consent_version="demo-call-web-v2", consent_text="ja",
                    consented_at=_at(10), provider_call_id=demo.provider_call_id, status="done"))
    db.add(TelephonyTest(workspace_id=ws, expires_at=_at(11), provider_call_id=test.provider_call_id))
    db.commit()
    r["demo"], r["test"] = demo, test
    return r


def _st(api, tok, ws, month=NOV):
    return api.get(tok, f"/workspaces/{ws}/billing/statement?month={month}").json()


def _freeze(db, ws, month, st, number):
    y, m = map(int, month.split("-"))
    inv = Invoice(workspace_id=ws, month=date(y, m, 1), status="open", currency="DKK", number=number,
                  net_minor=st["totals"]["net_minor"], tax_minor=st["totals"]["tax_minor"],
                  gross_minor=st["totals"]["gross_minor"], lines=st["lines"])
    db.add(inv)
    db.commit()
    return inv


def _usage(api, tok, ws, month=NOV):
    return api.get(tok, f"/workspaces/{ws}/billing/usage?month={month}").json()


# ---------------------------------------------------------------------------------------------------------- B03


def test_b03_usage_register_per_call_in_the_shared_package(api, two_workspaces, db):
    """B03: every billable call with its time, duration, started minutes and whether it was in the package or over it
    (with its price); demo and test calls are not usage; a call is in the month of its Copenhagen date; approved
    enquiries cost nothing (no lead lines); each call can be complained about."""
    ws, tok = uuid.UUID(two_workspaces["ws_a"]), two_workspaces["tok_a"]
    r = _month(db, ws)
    u = _usage(api, tok, ws)
    assert u["package"] == {"included": 300, "used": 305, "remaining": 0, "over": 5}
    rows = {c["id"]: c for c in u["calls"]}
    ids = {k: str(v.id) for k, v in r.items() if k != "campaign"}
    assert set(rows) == {ids[k] for k in ("in1", "A", "in2", "B", "C", "D", "E", "in3")}  # no demo/test/December call
    want = {  # seconds, started minutes, from package, over, call price, total, pending
        "in1": (17_400, 290, 290, 0, 0, 0, False), "A": (330, 6, 6, 0, 0, 0, False), "in2": (61, 2, 2, 0, 0, 0, False),
        "B": (181, 4, 2, 2, 0, 400, False), "C": (0, 0, 0, 0, 100, 100, False), "D": (0, 0, 0, 0, 25, 25, False),
        "E": (None, 0, 0, 0, 25, 25, True), "in3": (125, 3, 0, 3, 0, 450, False)}
    for k, (sec, mins, pkg, extra, fee, net, pending) in want.items():
        x = rows[ids[k]]
        assert (x["seconds"], x["minutes"], x["package_minutes"], x["extra_minutes"], x["call_net_minor"], x["net_minor"],
                x["pending"]) == (sec, mins, pkg, extra, fee, net, pending), k
        assert x["can_dispute"] is True and x["dispute"] is None
    assert [rows[ids[k]]["outcome"] for k in "ABCDE"] == ["answered", "answered", "voicemail", "no_answer", "no_answer"]
    # in call order, times in UTC ISO (the page shows them in Europe/Copenhagen)
    assert [c["at"] for c in u["calls"]] == sorted(c["at"] for c in u["calls"])
    assert rows[ids["in1"]]["at"].startswith("2026-11-02T09:00:00")
    # the call at 23:30 UTC on 30/11 is 00:30 on 1/12 in Copenhagen: December's usage
    assert [c["id"] for c in _usage(api, tok, ws, "2026-12")["calls"]] == [ids["dec"]]
    st = _st(api, tok, ws)
    assert st["approved_leads"] == 0 and not [x for x in st["lines"] if x["kind"] == "lead"]


# ---------------------------------------------------------------------------------------------------------- B05


def test_b05_period_statement_package_snapshot_frozen_invoice_refunds_and_vat(api, two_workspaces, db):
    """B05: the month's statement = the agreement's snapshot (2.495, 300 min, 1,50/2,00, 4/1/0,25), package
    used/included/left/over with amounts, net/VAT/gross apart and half up; once invoiced the lines are frozen and shown
    with the invoice, and Stripe's refunds/credit notes are shown on it."""
    from app.modules.billing import stripe as billing_stripe

    ws, tok = uuid.UUID(two_workspaces["ws_a"]), two_workspaces["tok_a"]
    _month(db, ws)
    a = api.get(tok, f"/workspaces/{ws}/agreement").json()["current"]
    assert (a["monthly"]["net_minor"], a["included_minutes"], a["inbound_extra_minute"]["net_minor"],
            a["outbound_extra_minute"]["net_minor"]) == (249_500, 300, 150, 200)
    assert {k: v["net_minor"] for k, v in a["outbound_call"].items()} == {"answered": 400, "voicemail": 100, "no_answer": 25}
    st = _st(api, tok, ws)
    by = {x["kind"]: x for x in st["lines"]}
    assert by["subscription"]["net_minor"] == 249_500
    assert (by["campaign_calls"]["calls"], by["campaign_calls"]["minutes"], by["campaign_calls"]["package_minutes"],
            by["campaign_calls"]["extra_minutes"], by["campaign_calls"]["net_minor"]) == (5, 10, 8, 2, 400)
    assert (by["campaign_call_fees"]["calls"], by["campaign_call_fees"]["voicemail"], by["campaign_call_fees"]["no_answer"],
            by["campaign_call_fees"]["answered"], by["campaign_call_fees"]["net_minor"]) == (3, 1, 2, 0, 150)
    assert (by["inbound_minutes"]["minutes"], by["inbound_minutes"]["extra_minutes"], by["inbound_minutes"]["net_minor"]) == (295, 3, 450)
    assert st["package"] == {"included": 300, "used": 305, "remaining": 0, "over": 5}
    assert (st["totals"]["net_minor"], st["totals"]["tax_minor"], st["totals"]["gross_minor"]) == (250_500, 62_625, 313_125)
    # invoiced: the lines are frozen with the invoice; a later list-price change cannot touch them
    inv = _freeze(db, ws, NOV, st, "DB-2026-11")
    u = _usage(api, tok, ws)
    assert u["invoiced"] is True and u["invoice"]["lines"] == st["lines"]
    assert (u["invoice"]["net_minor"], u["invoice"]["tax_minor"], u["invoice"]["gross_minor"]) == (250_500, 62_625, 313_125)
    assert u["invoice"]["refunds"] == {"charges_minor": 0, "credit_notes_minor": 0, "total_minor": 0}
    # a refund at Stripe (charge.refunded, then the same money as credit_note.created): shown once, not twice
    billing_stripe._refund_delta(inv, "charge.refunded", {"id": "ch_1", "amount_refunded": 10_000})
    billing_stripe._refund_delta(inv, "credit_note.created", {"id": "cn_1", "total": 10_000})
    db.commit()
    assert _usage(api, tok, ws)["invoice"]["refunds"] == {"charges_minor": 10_000, "credit_notes_minor": 10_000, "total_minor": 10_000}
    listed = api.get(tok, f"/workspaces/{ws}/billing/invoices").json()["items"][0]
    assert listed["refunds"]["total_minor"] == 10_000 and listed["lines"] == st["lines"]


# ---------------------------------------------------------------------------------------------------------- B04


def test_b04_complaint_in_an_open_month_puts_minutes_back_and_recounts_the_package(api, two_workspaces, db):
    """B04 (month not invoiced): approving a complaint takes the call out of the month – its minutes go back in the
    package before invoicing, no credit note. Without call B (4 min) the package ends at 301 minutes: C, D and E now
    start inside the package (no call prices), in3 has 2 minutes left in the package and 1 over = 1,50 kr. Rejecting
    another complaint changes nothing. The customer sees the decision and the operator's note."""
    ws, tok = uuid.UUID(two_workspaces["ws_a"]), two_workspaces["tok_a"]
    r = _month(db, ws)
    op = api.operator()
    d = api.post(tok, f"/workspaces/{ws}/billing/disputes",
                 {"kind": "outbound", "call_id": str(r["B"].id), "reason": "Ringede til en, der havde frabedt sig opkald"})
    assert d.status_code == 201 and d.json()["status"] == "open" and d.json()["minutes"] == 4
    assert _st(api, tok, ws)["totals"]["net_minor"] == 250_500  # nothing changes before the decision
    dec = api.post(op, f"/operator/admin/disputes/{d.json()['id']}/decision", {"decision": "approve", "note": "Fejl i spærrelisten"})
    assert (dec.json()["credit_mode"], dec.json()["credit_net_minor"]) == ("pool", 0)
    st = _st(api, tok, ws)
    assert st["package"] == {"included": 300, "used": 301, "remaining": 0, "over": 1}
    assert st["totals"]["net_minor"] == 249_500 + 150
    assert not [x for x in st["lines"] if x["kind"] in ("campaign_call_fees", "dispute_credit")]
    row = next(c for c in _usage(api, tok, ws)["calls"] if c["id"] == str(r["B"].id))
    assert row["credited"] is True and row["dispute"]["status"] == "approved"
    assert row["dispute"]["decision_note"] == "Fejl i spærrelisten"
    # a rejected complaint changes nothing
    before = _st(api, tok, ws)["totals"]
    d2 = api.post(tok, f"/workspaces/{ws}/billing/disputes", {"kind": "outbound", "call_id": str(r["D"].id), "reason": "For dyrt synes jeg"})
    assert api.post(op, f"/operator/admin/disputes/{d2.json()['id']}/decision", {"decision": "reject", "note": "Opkaldet var i orden"}).json()["status"] == "rejected"
    assert _st(api, tok, ws)["totals"] == before


def test_b04_complaint_about_an_invoiced_month_is_credited_once_on_the_next_invoice(api, two_workspaces, db):
    """B04 (month invoiced): the credit is what the call added to the invoice – without in3 November would have been
    10,00 − 4,50 = 5,50 kr. of usage, so 4,50 kr. comes off the next invoice as its own line, once (approving again is
    a no-op; a later invoice does not repeat it). December: 2.495,00 − 4,50 = 2.490,50 kr.; VAT 622,625 → 622,63 (half
    up); 3.113,13 incl. VAT. The November period shows where the credit went."""
    ws, tok = uuid.UUID(two_workspaces["ws_a"]), two_workspaces["tok_a"]
    r = _month(db, ws)
    _freeze(db, ws, NOV, _st(api, tok, ws), "DB-2026-11")
    op = api.operator()
    d = api.post(tok, f"/workspaces/{ws}/billing/disputes", {"kind": "inbound", "call_id": str(r["in3"].id), "reason": "Fejlopkald – ingen sagde noget"}).json()
    a = api.post(op, f"/operator/admin/disputes/{d['id']}/decision", {"decision": "approve"}).json()
    assert (a["credit_mode"], a["credit_net_minor"], a["invoiced"]) == ("invoice", 450, True)
    assert api.post(op, f"/operator/admin/disputes/{d['id']}/decision", {"decision": "approve"}).json()["credit_net_minor"] == 450
    credits = _usage(api, tok, ws)["credits"]
    assert [(x["dispute_id"], x["credit_net_minor"], x["on_invoice"]) for x in credits] == [(d["id"], 450, False)]
    dec = _st(api, tok, ws, "2026-12")
    lines = [x for x in dec["lines"] if x["kind"] == "dispute_credit"]
    assert [(x["period"], x["net_minor"]) for x in lines] == [("2026-11", -450)]
    assert (dec["totals"]["net_minor"], dec["totals"]["tax_minor"], dec["totals"]["gross_minor"]) == (249_050, 62_263, 311_313)
    assert not [x for x in dec["lines"] if x["kind"] == "late_usage_adjustment"]
    _freeze(db, ws, "2026-12", dec, "DB-2026-12")
    assert not [x for x in _st(api, tok, ws, "2027-01")["lines"] if x["kind"] == "dispute_credit"]
    assert [(x["on_invoice"], x["invoice_number"]) for x in _usage(api, tok, ws)["credits"]] == [(True, "DB-2026-12")]


# ---------------------------------------------------------------------------------------------------------- C15


def test_c15_campaign_reconciliation_pending_report_and_late_usage(api, two_workspaces, db, monkeypatch):
    """C15: the campaign's calls and minutes are the statement's (one source); a call without its end-of-call report is
    «awaiting report», not 0 minutes; when that report comes after November was invoiced, the difference is billed on
    the next invoice as «Efterregistreret forbrug» (nothing lost): E answered 90 s after the package = 4,00 + 2 × 2,00 =
    8,00 kr. instead of the 0,25 kr. invoiced → 7,75 kr. There is nothing prepaid to refund: no checkout, package or
    order per campaign."""
    from app.modules.billing import operator_router

    ws, tok = uuid.UUID(two_workspaces["ws_a"]), two_workspaces["tok_a"]
    r = _month(db, ws)
    camp = api.get(tok, f"/workspaces/{ws}/campaigns/{r['campaign'].id}").json()
    st = _st(api, tok, ws)
    line = next(x for x in st["lines"] if x["kind"] == "campaign_calls")
    assert camp["counts"]["calls"] == line["calls"] == 5 and camp["counts"]["awaiting_report"] == 1
    _freeze(db, ws, NOV, st, "DB-2026-11")
    e = db.get(CampaignCall, r["E"].id)
    e.connected_seconds, e.outcome_class = 90, "answered"  # what the webhook writes when the report arrives
    db.commit()
    assert api.get(tok, f"/workspaces/{ws}/campaigns/{r['campaign'].id}").json()["counts"]["awaiting_report"] == 0
    late = [x for x in _st(api, tok, ws, "2026-12")["lines"] if x["kind"] == "late_usage_adjustment"]
    assert [(x["period"], x["minutes"], x["net_minor"]) for x in late] == [("2026-11", 2, 775)]
    # the operator's monthly reconciliation shows the same amount before the December invoice is made
    monkeypatch.setattr(operator_router, "local_today", lambda tz: date(2026, 12, 3))
    rec = next(x for x in api.get(api.operator(), "/operator/admin/billing").json()["items"] if x["id"] == str(ws))["reconciliation"]
    assert rec["next_invoice_month"] == "2026-12" and [(x["period"], x["net_minor"]) for x in rec["late_usage"]] == [("2026-11", 775)]
    for p in ("checkout", "packages", "order", "refund"):
        assert api.get(tok, f"/workspaces/{ws}/campaigns/{r['campaign'].id}/{p}").status_code in (404, 405), p


# ---------------------------------------------------------------------------------------------------------- C09


def _ready(api, t, monkeypatch):
    tok, ws = t["tok_a"], t["ws_a"]
    monkeypatch.setenv("VAPI_SERVER_SECRET", SECRET)
    monkeypatch.setenv("AI_PROVIDER", "fake")
    monkeypatch.setenv("VAPI_API_KEY", "vapi-private-key-test")
    get_settings.cache_clear()
    it = api.knowledge(tok, ws, "service", "Gulvafslibning", {"description": "Vi sliber trægulve."})
    api.submit(tok, ws, it["open_draft"]["id"])
    api.approve(tok, ws, it["open_draft"]["id"])
    api.map_number(ws, "+4570123456", "pn_qa_lb", outbound=True)
    c = api.post(tok, f"/workspaces/{ws}/campaigns", {"name": "QA C09", "purpose": "Tilbud på gulvafslibning"}).json()
    api.post(tok, f"/workspaces/{ws}/campaigns/{c['id']}/contacts/import",
             {"csv": "Mette;20304050\nOle;21222324\nBo;22334455", "kind": "business", "consent_source": "Tilmelding på hjemmesiden"})
    return api.get(tok, f"/workspaces/{ws}/campaigns/{c['id']}").json()


def test_c09_start_shows_the_honest_maximum_and_needs_a_paid_subscription_with_a_card(api, two_workspaces, db, monkeypatch):
    """C09: before the start the price snapshot and the maximum: 3 contacts × (2 attempts × 4 kr. + 3 min × 2 kr.) =
    42,00 kr. excl. VAT, 10,50 VAT, 52,50 incl. VAT (14 kr. per contact); with the 300 package minutes left it is 0 kr.
    The start needs the explicit confirmation of that amount (a higher maximum since → 409 price_changed) and a paid
    subscription: with Stripe set up a confirmed agreement AND a usable card (409 subscription_required otherwise). Paying
    never starts a campaign; a lapsed subscription stops the dialler."""
    from app.modules.billing import stripe as billing_stripe
    from app.modules.campaigns import service

    t = two_workspaces
    tok, ws = t["tok_a"], t["ws_a"]
    c = _ready(api, t, monkeypatch)
    p = c["pricing"]
    assert (p["call_prices"], p["minute_net_minor"], p["per_contact_max_net_minor"], p["max_attempts"],
            p["max_connected_seconds"]) == ({"answered": 400, "voicemail": 100, "no_answer": 25}, 200, 1_400, 2, 180)
    assert (c["max_cost"]["net_minor"], c["max_cost"]["tax_minor"], c["max_cost"]["gross_minor"]) == (4_200, 1_050, 5_250)
    assert c["max_cost_with_package"]["net_minor"] == 0 and c["max_minutes"] == 9 and c["package"]["included"] == 300
    start = f"/workspaces/{ws}/campaigns/{c['id']}/start"
    body = {"expected_version": c["version"], "legal_confirmed": True, "accept_max_net_minor": 4_200}
    assert api.post(tok, start, body | {"accept_max_net_minor": 4_199}).json()["code"] == "price_changed"
    monkeypatch.setattr(billing_stripe, "configured", lambda: True)  # card payment (Stripe test mode) is set up
    assert c["billing_ready"] is False
    assert api.post(tok, start, body).json()["code"] == "subscription_required"  # no agreement
    assert api.post(tok, f"/workspaces/{ws}/agreement", {"model": "A"}).status_code == 201
    r = api.post(tok, start, body)
    assert r.status_code == 409 and r.json()["code"] == "subscription_required"  # agreement, but no card
    wid = uuid.UUID(ws)
    acc = db.get(BillingAccount, wid) or BillingAccount(workspace_id=wid)
    acc.payment_method_id, acc.card_brand, acc.card_last4, acc.card_exp = "pm_test_visa", "visa", "4242", "12/30"
    db.add(acc)
    db.commit()
    assert api.get(tok, f"/workspaces/{ws}/campaigns/{c['id']}").json()["billing_ready"] is True
    r = api.post(tok, start, body)
    assert r.status_code == 200 and r.json()["status"] == "running", r.text
    assert r.json()["legal_confirmation"]["accepted_max_net_minor"] == 4_200
    # the dialler only calls while the subscription is paid: the card is removed (never paid → no grace) → no call
    calls = []
    monkeypatch.setattr(service, "create_call", lambda p: calls.append(p) or {"id": f"lb_{len(calls)}"})
    now = datetime.now(UTC).replace(hour=10)
    monkeypatch.setattr(service, "in_window", lambda *a: True)
    acc = db.get(BillingAccount, wid)
    acc.payment_method_id = None
    db.commit()
    assert service.dispatch(db, now) == 0 and calls == []
    acc.payment_method_id = "pm_test_visa"
    db.commit()
    assert service.dispatch(db, now + timedelta(seconds=1)) == 1 and len(calls) == 1
    get_settings.cache_clear()


# ---------------------------------------------------------------------------------------------------------- M04


def test_m04_operator_billing_catalogue_customer_snapshot_usage_invoices_and_reconciliation(api, two_workspaces, db, monkeypatch):
    """M04: the price list per currency with its version; per customer the agreement's snapshot (incl. the call prices
    by outcome), the month's usage split inbound/outbound (DB-004) with the call prices and calls awaiting a report,
    invoices with frozen lines and refunds, the complaint queue and the reconciliation for the next invoice. Operators
    only."""
    from app.modules.billing import operator_router

    t = two_workspaces
    ws, tok = uuid.UUID(t["ws_a"]), t["tok_a"]
    r = _month(db, ws)
    op = api.operator()
    prices = api.get(op, "/operator/admin/prices").json()
    assert prices["version"] == "2026-11-10" and prices["valid_from"] == "2026-11-01" and prices["included_minutes"] == 300
    assert {k: prices["erhverv"]["DKK"][k] for k in ("monthly", "extra_minute", "outbound_extra_minute", "call_answered",
                                                     "call_voicemail", "call_no_answer")} == {
        "monthly": 249_500, "extra_minute": 150, "outbound_extra_minute": 200, "call_answered": 400, "call_voicemail": 100,
        "call_no_answer": 25}
    assert set(prices["currencies"]) >= {"DKK", "SEK", "NOK", "EUR"}
    monkeypatch.setattr(operator_router, "local_today", lambda tz: date(2026, 11, 20))
    row = next(x for x in api.get(op, "/operator/admin/billing").json()["items"] if x["id"] == str(ws))
    assert {k: v["net_minor"] for k, v in row["agreement"]["outbound_call"].items()} == {"answered": 400, "voicemail": 100, "no_answer": 25}
    u = row["usage"]
    assert u["package"] == {"included": 300, "used": 305, "remaining": 0, "over": 5}
    assert (u["inbound"]["calls"], u["inbound"]["minutes"], u["inbound"]["net_minor"]) == (3, 295, 450)
    assert (u["outbound"]["calls"], u["outbound"]["minutes"], u["outbound"]["extra_minutes"], u["outbound"]["call_fees_net_minor"],
            u["outbound"]["net_minor"], u["outbound"]["pending_reports"]) == (5, 10, 2, 150, 550, 1)
    assert u["overage_net_minor"] == 1_000
    # an invoiced month with a complaint approved afterwards: the invoice's frozen lines, and the credit in the
    # reconciliation for the next invoice
    st = _st(api, tok, ws)
    _freeze(db, ws, NOV, st, "DB-2026-11")
    d = api.post(tok, f"/workspaces/{ws}/billing/disputes", {"kind": "inbound", "call_id": str(r["in3"].id), "reason": "Fejlopkald hos jer"}).json()
    assert row["open_disputes"] == 0
    queue = api.get(op, "/operator/admin/disputes").json()["items"]
    assert [(x["id"], x["invoiced"]) for x in queue] == [(d["id"], True)]
    api.post(op, f"/operator/admin/disputes/{d['id']}/decision", {"decision": "approve", "note": "Teknisk fejl"})
    monkeypatch.setattr(operator_router, "local_today", lambda tz: date(2026, 12, 2))
    row = next(x for x in api.get(op, "/operator/admin/billing").json()["items"] if x["id"] == str(ws))
    inv = row["invoices"][0]
    assert (inv["month"], inv["number"], inv["net_minor"], inv["tax_minor"], inv["gross_minor"]) == (NOV, "DB-2026-11", 250_500, 62_625, 313_125)
    assert inv["lines"] == st["lines"] and inv["refunds"]["total_minor"] == 0
    rec = row["reconciliation"]
    assert [(x["period"], x["net_minor"]) for x in rec["credits"]] == [(NOV, -450)] and rec["late_usage"] == [] and rec["net_minor"] == -450
    for path in ("/operator/admin/billing", "/operator/admin/prices", "/operator/admin/disputes"):
        assert api.get(tok, path).status_code == 403, path


@pytest.mark.parametrize("path", ["/operator/admin/orders", "/operator/admin/refunds"])
def test_m04_no_orders_or_refund_desk_in_the_one_plan_model(api, path):
    """NOT APPLICABLE in the one-plan model: there are no campaign orders to list or refund; money goes back only as
    an approved complaint (credit) – or a refund made at Stripe, which the invoice then shows (B05)."""
    assert api.get(api.operator(), path).status_code in (404, 405)

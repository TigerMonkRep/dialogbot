"""Complaints about calls → credit (B03/B04, DB-002) and the operator billing overview (M04).

Fürster 2026-11-10: minutes are credited ONLY when the customer complains about a call. One shared package of 300
minutes a month (inbound + outbound), then 1,50 kr. inbound / 2 kr. outbound per started minute. Expected numbers are
worked out by hand here.
"""
from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

from app.models import (
    AuditLog,
    Call,
    CallDispute,
    Campaign,
    CampaignCall,
    CampaignContact,
    DemoCall,
    Invoice,
    ReceptionAgreement,
)


def _setup(db, ws):
    db.add(ReceptionAgreement(workspace_id=ws, version=1, model="A", monthly_net_minor=249_500,
                              created_at=datetime(2026, 8, 1, tzinfo=UTC)))
    # November 2026: 290 inbound minutes on 2/11, then a 20-minute inbound call on 5/11 (10 in the package, 10 over)
    big = Call(workspace_id=ws, provider="vapi", provider_call_id=f"d_big_{uuid.uuid4().hex[:6]}",
               started_at=datetime(2026, 11, 2, 9, tzinfo=UTC), duration_seconds=290 * 60, from_number="+4520000001")
    late = Call(workspace_id=ws, provider="vapi", provider_call_id=f"d_late_{uuid.uuid4().hex[:6]}",
                started_at=datetime(2026, 11, 5, 9, tzinfo=UTC), duration_seconds=20 * 60, from_number="+4520000002")
    db.add_all([big, late])
    db.commit()
    return big, late


def _statement(api, tok, ws, month):
    return api.get(tok, f"/workspaces/{ws}/billing/statement?month={month}").json()


def _freeze(db, ws, month, st):
    y, m = map(int, month.split("-"))
    db.add(Invoice(workspace_id=ws, month=date(y, m, 1), status="open", currency="DKK", net_minor=st["totals"]["net_minor"],
                   tax_minor=st["totals"]["tax_minor"], gross_minor=st["totals"]["gross_minor"], lines=st["lines"]))
    db.commit()


def test_usage_per_call_and_a_complaint_in_an_open_month_puts_the_minutes_back_in_the_package(api, two_workspaces, db):
    ws, tok = uuid.UUID(two_workspaces["ws_a"]), two_workspaces["tok_a"]
    big, late = _setup(db, ws)
    u = api.get(tok, f"/workspaces/{ws}/billing/usage?month=2026-11").json()
    assert u["shared_package"] is True and u["invoiced"] is False and u["package"] == {"included": 300, "used": 310, "remaining": 0, "over": 10}
    row = next(c for c in u["calls"] if c["id"] == str(late.id))
    assert (row["kind"], row["minutes"], row["package_minutes"], row["extra_minutes"], row["net_minor"]) == ("inbound", 20, 10, 10, 1_500)
    assert row["label"] == "+4520000002" and row["can_dispute"] is True and row["dispute"] is None
    assert _statement(api, tok, ws, "2026-11")["totals"]["net_minor"] == 249_500 + 1_500
    # the owner complains; asking again returns the same complaint (one per call, idempotent)
    body = {"kind": "inbound", "call_id": str(late.id), "reason": "Assistenten lagde på midt i samtalen"}
    first = api.post(tok, f"/workspaces/{ws}/billing/disputes", body)
    again = api.post(tok, f"/workspaces/{ws}/billing/disputes", body | {"reason": "Igen igen igen"})
    assert (first.status_code, again.status_code) == (201, 200) and first.json()["id"] == again.json()["id"]
    assert again.json()["reason"] == "Assistenten lagde på midt i samtalen" and first.json()["status"] == "open"
    assert api.post(tok, f"/workspaces/{ws}/billing/disputes", body | {"call_id": str(big.id), "reason": "x"}).status_code == 422
    # nothing changes until the operator decides
    assert _statement(api, tok, ws, "2026-11")["totals"]["net_minor"] == 251_000
    op = api.operator()
    queue = api.get(op, "/operator/admin/disputes").json()["items"]
    assert [(d["id"], d["invoiced"], d["workspace_name"]) for d in queue] == [(first.json()["id"], False, "Fjord Gulvservice ApS")]
    r = api.post(op, f"/operator/admin/disputes/{first.json()['id']}/decision", {"decision": "approve", "note": "Fejl hos os"})
    assert r.status_code == 200 and (r.json()["status"], r.json()["credit_mode"], r.json()["credit_net_minor"]) == ("approved", "pool", 0)
    # the 20 minutes are back in the package: 290 used, nothing over, no credit note line (DB-002 unbilled uphold)
    st = _statement(api, tok, ws, "2026-11")
    assert st["package"] == {"included": 300, "used": 290, "remaining": 10, "over": 0} and st["totals"]["net_minor"] == 249_500
    assert not [x for x in st["lines"] if x["kind"] == "dispute_credit"]
    row = next(c for c in api.get(tok, f"/workspaces/{ws}/billing/usage?month=2026-11").json()["calls"] if c["id"] == str(late.id))
    assert row["credited"] is True and row["dispute"]["status"] == "approved" and row["can_dispute"] is False
    # the same decision again is a no-op; a different one is a conflict
    assert api.post(op, f"/operator/admin/disputes/{first.json()['id']}/decision", {"decision": "approve"}).status_code == 200
    assert api.post(op, f"/operator/admin/disputes/{first.json()['id']}/decision", {"decision": "reject"}).status_code == 409
    actions = [a.action for a in db.query(AuditLog).filter(AuditLog.object_type == "call_dispute")]
    assert sorted(actions) == ["billing.dispute_approved", "billing.dispute_created"]


def test_a_complaint_about_an_invoiced_month_is_credited_once_on_the_next_invoice(api, two_workspaces, db):
    ws, tok = uuid.UUID(two_workspaces["ws_a"]), two_workspaces["tok_a"]
    big, late = _setup(db, ws)
    _freeze(db, ws, "2026-11", _statement(api, tok, ws, "2026-11"))  # 10 min × 1,50 kr. = 15 kr. invoiced
    u = api.get(tok, f"/workspaces/{ws}/billing/usage?month=2026-11").json()
    assert u["invoiced"] is True and any(x["kind"] == "inbound_minutes" for x in u["invoice"]["lines"])
    inv = api.get(tok, f"/workspaces/{ws}/billing/invoices").json()["items"][0]
    assert any(x.get("kind") == "inbound_minutes" and x.get("extra_minutes") == 10 for x in inv["lines"])
    op = api.operator()
    d_late = api.post(tok, f"/workspaces/{ws}/billing/disputes", {"kind": "inbound", "call_id": str(late.id), "reason": "Forkert opkald"}).json()
    d_big = api.post(tok, f"/workspaces/{ws}/billing/disputes", {"kind": "inbound", "call_id": str(big.id), "reason": "Testopkald fra os selv"}).json()
    a = api.post(op, f"/operator/admin/disputes/{d_late['id']}/decision", {"decision": "approve"}).json()
    # without the 20-minute call November would have been 290 minutes = within the package: 15 kr. back
    assert (a["credit_mode"], a["credit_net_minor"], a["invoiced"]) == ("invoice", 1_500, True)
    # the second complaint is valued after the first: without both, still nothing over → 0 kr., no line
    b = api.post(op, f"/operator/admin/disputes/{d_big['id']}/decision", {"decision": "approve"}).json()
    assert (b["credit_mode"], b["credit_net_minor"]) == ("invoice", 0)
    dec = _statement(api, tok, ws, "2026-12")
    credits = [x for x in dec["lines"] if x["kind"] == "dispute_credit"]
    assert [(x["dispute_id"], x["period"], x["net_minor"]) for x in credits] == [(d_late["id"], "2026-11", -1_500)]
    assert "Kreditering efter klage" in credits[0]["description"]
    assert dec["totals"]["net_minor"] == 249_500 - 1_500
    # the invoiced month itself is not recounted into a late-usage charge or a second credit
    assert not [x for x in dec["lines"] if x["kind"] == "late_usage_adjustment"]
    _freeze(db, ws, "2026-12", dec)
    assert not [x for x in _statement(api, tok, ws, "2027-01")["lines"] if x["kind"] == "dispute_credit"]


def test_rejected_complaint_changes_nothing(api, two_workspaces, db):
    ws, tok = uuid.UUID(two_workspaces["ws_a"]), two_workspaces["tok_a"]
    _big, late = _setup(db, ws)
    before = _statement(api, tok, ws, "2026-11")["totals"]
    d = api.post(tok, f"/workspaces/{ws}/billing/disputes", {"kind": "inbound", "call_id": str(late.id), "reason": "Synes det var dyrt"}).json()
    r = api.post(api.operator(), f"/operator/admin/disputes/{d['id']}/decision", {"decision": "reject", "note": "Opkaldet var i orden"}).json()
    assert (r["status"], r["credit_mode"], r["credit_net_minor"]) == ("rejected", None, 0)
    assert _statement(api, tok, ws, "2026-11")["totals"] == before
    assert "krediteret" not in str(r).lower()


def test_campaign_calls_can_be_disputed_and_old_months_and_demo_calls_cannot(api, two_workspaces, db):
    ws, tok = uuid.UUID(two_workspaces["ws_a"]), two_workspaces["tok_a"]
    camp = Campaign(workspace_id=ws, name="Vinter", call_net_minor=0, minute_net_minor=200, max_attempts=2, max_connected_seconds=180)
    db.add(camp)
    db.flush()
    contact = CampaignContact(campaign_id=camp.id, workspace_id=ws, phone="+4520304050", kind="business")
    db.add(contact)
    db.flush()
    cc = CampaignCall(workspace_id=ws, campaign_id=camp.id, contact_id=contact.id, net_minor=0, connected_seconds=125,
                      dialled_at=datetime(2026, 11, 20, 9, tzinfo=UTC))
    old = Call(workspace_id=ws, provider="vapi", provider_call_id="d_old", started_at=datetime(2026, 10, 20, 9, tzinfo=UTC),
               duration_seconds=60)
    demo = Call(workspace_id=ws, provider="vapi", provider_call_id="d_demo", started_at=datetime(2026, 11, 20, 9, tzinfo=UTC),
                duration_seconds=60)
    db.add_all([cc, old, demo, DemoCall(workspace_id=ws, source="web", phone="+4520304050", consent_version="demo-call-web-v2",
                                         consent_text="ja", consented_at=datetime(2026, 11, 20, tzinfo=UTC),
                                         provider_call_id="d_demo", status="done")])
    db.commit()
    r = api.post(tok, f"/workspaces/{ws}/billing/disputes", {"kind": "outbound", "call_id": str(cc.id), "reason": "Ringede til forkert kunde"})
    assert r.status_code == 201 and (r.json()["kind"], r.json()["minutes"]) == ("outbound", 3)
    bad_old = api.post(tok, f"/workspaces/{ws}/billing/disputes", {"kind": "inbound", "call_id": str(old.id), "reason": "Gammelt opkald"})
    assert bad_old.status_code == 422 and bad_old.json()["code"] == "period_not_supported"
    bad_demo = api.post(tok, f"/workspaces/{ws}/billing/disputes", {"kind": "inbound", "call_id": str(demo.id), "reason": "Demoopkald"})
    assert bad_demo.status_code == 422 and bad_demo.json()["code"] == "not_billed"
    assert db.query(CallDispute).count() == 1


def test_roles_and_isolation(api, two_workspaces, db):
    t = two_workspaces
    ws, tok = uuid.UUID(t["ws_a"]), t["tok_a"]
    _big, late = _setup(db, ws)
    body = {"kind": "inbound", "call_id": str(late.id), "reason": "Fejl i opkaldet"}
    admin = api.add_member(tok, t["ws_a"], "admin-disp@testmail.dk", "admin")
    staff = api.add_member(tok, t["ws_a"], "staff-disp@testmail.dk", "staff")
    assert api.get(admin, f"/workspaces/{ws}/billing/usage?month=2026-11").status_code == 200
    assert api.post(admin, f"/workspaces/{ws}/billing/disputes", body).status_code == 403  # the owner complains
    assert api.get(staff, f"/workspaces/{ws}/billing/usage").status_code == 403
    assert api.post(t["tok_b"], f"/workspaces/{t['ws_b']}/billing/disputes", body).status_code == 404  # not B's call
    d = api.post(tok, f"/workspaces/{ws}/billing/disputes", body).json()
    for path in ("/operator/admin/billing", "/operator/admin/disputes", "/operator/admin/prices"):
        assert api.get(tok, path).status_code == 403, path
    assert api.post(tok, f"/operator/admin/disputes/{d['id']}/decision", {"decision": "approve"}).status_code == 403


def test_operator_billing_overview_and_customer_detail(api, two_workspaces, db, monkeypatch):
    from app.modules.billing import operator_router

    t = two_workspaces
    ws = uuid.UUID(t["ws_a"])
    _setup(db, ws)
    monkeypatch.setattr(operator_router, "local_today", lambda tz: date(2026, 11, 20))
    op = api.operator()
    rows = {r["id"]: r for r in api.get(op, "/operator/admin/billing").json()["items"]}
    a = rows[str(ws)]
    assert a["agreement"]["version"] == 1 and a["agreement"]["included_minutes"] == 300
    assert a["agreement"]["outbound_extra_minute"]["net_minor"] == 200 and a["agreement"]["inbound_extra_minute"]["net_minor"] == 150
    u = a["usage"]
    assert u["package"] == {"included": 300, "used": 310, "remaining": 0, "over": 10}
    assert (u["inbound"]["minutes"], u["outbound"]["minutes"], u["overage_net_minor"]) == (310, 0, 1_500)
    assert rows[t["ws_b"]]["agreement"] is None
    detail = api.get(op, f"/operator/admin/customers/{ws}").json()
    assert detail["agreement"]["version"] == 1 and detail["usage"]["package"]["used"] == 310
    prices = api.get(op, "/operator/admin/prices").json()
    assert prices["included_minutes"] == 300 and prices["erhverv"]["DKK"]["outbound_extra_minute"] == 200


def test_week_overview_campaign_amount_comes_from_the_package(api, two_workspaces, db):
    from app.modules.reports import service

    ws = uuid.UUID(two_workspaces["ws_a"])
    _setup(db, ws)  # the package is full after 5/11 (310 inbound minutes)
    camp = Campaign(workspace_id=ws, name="Vinter", call_net_minor=0, minute_net_minor=200, max_attempts=2, max_connected_seconds=600)
    db.add(camp)
    db.flush()
    contact = CampaignContact(campaign_id=camp.id, workspace_id=ws, phone="+4520304050", kind="business")
    db.add(contact)
    db.flush()
    db.add(CampaignCall(workspace_id=ws, campaign_id=camp.id, contact_id=contact.id, net_minor=0, connected_seconds=5 * 60,
                        dialled_at=datetime(2026, 11, 10, 9, tzinfo=UTC)))
    db.commit()
    w = service.week(db, ws, date(2026, 11, 9), "Europe/Copenhagen")
    assert (w["campaign_calls"], w["campaign_net_minor"]) == (1, 5 * 200)  # all 5 minutes above the package

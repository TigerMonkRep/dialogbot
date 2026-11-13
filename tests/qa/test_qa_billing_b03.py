"""QA billing-qa · B03 – billable-lead register (/app/billing/leads) and DB-002 (dispute rules).

What exists: leads with billing_status pending/approved/rejected, a fee snapshot at approval, list filter ?billing=,
the pure rule money.decide_unbilled_dispute. What does not exist: a dispute model/endpoint, duplicate status, the
/app/billing/leads route (scenario status not-implemented – asserted here so the status is evidence-backed).
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path

from app.models import Lead, ReceptionAgreement

ROOT = Path(__file__).resolve().parents[2]


def _qualified_lead(api, tok, ws, name="QA Lead"):
    r = api.post(tok, f"/workspaces/{ws}/leads", {"contact_name": name, "need_summary": "Vil have tilbud"})
    assert r.status_code == 201, r.text
    lead = r.json()
    lid = lead["id"]
    r = api.c.patch(f"{api.base}/workspaces/{ws}/leads/{lid}", json={"qualification_status": "qualified",
                                                                    "expected_version": lead["version"]},
                    headers=api.h(tok))
    assert r.status_code == 200, r.text
    return lid


def test_b03_approval_under_the_subscription_snapshots_zero_fee_and_is_decided_once(api, two_workspaces, db):
    tok, ws = two_workspaces["tok_a"], two_workspaces["ws_a"]
    lid = _qualified_lead(api, tok, ws)
    assert api.post(tok, f"/workspaces/{ws}/leads/{lid}/approve", {}).json()["code"] == "no_agreement"
    assert api.post(tok, f"/workspaces/{ws}/agreement", {"model": "A"}).status_code == 201
    r = api.post(tok, f"/workspaces/{ws}/leads/{lid}/approve", {}, **{"Idempotency-Key": "qa-bill-b03-1"})
    assert r.status_code == 200, r.text
    snap = r.json()["fee_snapshot"]
    assert (snap["net_minor"], snap["tax_minor"], snap["gross_minor"], snap["model"]) == (0, 0, 0, "A")
    # replay with the same key returns the same answer; a second decision is refused
    again = api.post(tok, f"/workspaces/{ws}/leads/{lid}/approve", {}, **{"Idempotency-Key": "qa-bill-b03-1"})
    assert again.status_code == 200 and again.json()["fee_snapshot"] == snap
    assert api.post(tok, f"/workspaces/{ws}/leads/{lid}/reject", {"reason": "dublet"}).json()["code"] == "lead_billing_decided"
    # register filter
    items = api.get(tok, f"/workspaces/{ws}/leads?billing=approved").json()
    items = items["items"] if isinstance(items, dict) else items
    assert [x["id"] for x in items] == [lid]
    # the month's statement: subscription only, the approved lead costs nothing
    month = datetime.now(UTC).strftime("%Y-%m")
    st = api.get(tok, f"/workspaces/{ws}/billing/statement?month={month}").json()
    assert st["approved_leads"] == 1 and st["billable_leads"] == 0
    assert [x["net_minor"] for x in st["lines"] if x["kind"] == "lead"] == [0]


def test_b03_reject_needs_a_reason_and_model_b_cannot_be_chosen(api, two_workspaces):
    tok, ws = two_workspaces["tok_a"], two_workspaces["ws_a"]
    lid = _qualified_lead(api, tok, ws)
    assert api.post(tok, f"/workspaces/{ws}/leads/{lid}/reject", {"reason": "  "}).status_code == 422
    r = api.post(tok, f"/workspaces/{ws}/agreement", {"model": "B"})
    assert r.status_code == 422 and r.json()["code"] == "plan_discontinued"


def test_b03_legacy_model_b_fee_snapshot_survives_a_new_agreement(api, two_workspaces, db):
    """14 leads × 149 kr. under an old model-B agreement = 2.086 kr. (DB-002 fixture 208.600 øre)."""
    ws = uuid.UUID(two_workspaces["ws_a"])
    db.add(ReceptionAgreement(workspace_id=ws, version=1, model="B", monthly_net_minor=0, lead_fee_net_minor=14_900,
                              created_at=datetime(2026, 8, 1, tzinfo=UTC)))
    for i in range(14):
        db.add(Lead(workspace_id=ws, source="manual", contact_name=f"K{i}", qualification_status="qualified",
                    billing_status="approved", billing_decided_at=datetime(2026, 9, 10, tzinfo=UTC),
                    fee_snapshot={"net_minor": 14_900, "model": "B", "agreement_version": 1}))
    db.commit()
    st = api.get(two_workspaces["tok_a"], f"/workspaces/{ws}/billing/statement?month=2026-09").json()
    assert st["totals"]["net_minor"] == 14 * 14_900 == 208_600
    assert st["totals"]["tax_minor"] == 52_150 and st["totals"]["gross_minor"] == 260_750


def test_b03_db002_unbilled_dispute_rule_numbers():
    """DB-002 acceptance: unbilled uphold = 208.600 approved / 14.900 suspended / no credit note; reject = 223.500 /
    14.900 / no credit note. Alternative outcomes from the SAME start state."""
    from app.modules.billing.money import LeadBillingState, decide_unbilled_dispute

    start = LeadBillingState(approved_count=14, approved_subtotal_net_minor=208_600, suspended_total_net_minor=29_800)
    up = decide_unbilled_dispute(start, disputed_net_minor=14_900, ruling="uphold")
    rj = decide_unbilled_dispute(start, disputed_net_minor=14_900, ruling="reject")
    assert (up.approved_subtotal_net_minor, up.suspended_total_net_minor, up.excluded_net_minor, up.credit_note_created) \
        == (208_600, 14_900, 14_900, False)
    assert (rj.approved_count, rj.approved_subtotal_net_minor, rj.suspended_total_net_minor,
            rj.next_invoice_addition_net_minor, rj.credit_note_created) == (15, 223_500, 14_900, 14_900, False)


def test_b03_register_route_and_dispute_api_exist(app):
    """B03 in the one-plan model (rewritten 2026-11-12, fix-engineer #26): there is no fee per lead any more, so the
    old «billable-lead register» (/app/billing/leads) is NOT APPLICABLE. The register is the usage per call
    (GET /billing/usage, Konto «Forbrug pr. opkald») with a complaint per call (POST /billing/disputes). Numbers:
    tests/qa/test_qa_launch_billing.py::test_b03_usage_register_per_call_in_the_shared_package."""
    from qa_sec_helpers import all_routes

    paths = {(m, p) for m, p, _r in all_routes(app)}
    assert ("GET", "/api/v1/workspaces/{workspace_id}/billing/usage") in paths
    assert ("POST", "/api/v1/workspaces/{workspace_id}/billing/disputes") in paths
    assert not [p for _m, p in paths if "/billing/leads" in p]  # no per-lead fee → no lead register
    konto = (ROOT / "web/src/app/app/(admin)/konto/page.tsx").read_text()
    assert "UsagePerCall" in konto and 'id="forbrug"' in konto

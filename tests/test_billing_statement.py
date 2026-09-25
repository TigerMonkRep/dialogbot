"""Monthly statement preview: model A subscription vs model B approved-lead fees in whole øre,
fee snapshots survive agreement changes, month bounds in local time, admin-only."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import update

from app.models import Lead, ReceptionAgreement


def _agreement(db, ws, version, model, at):
    db.add(ReceptionAgreement(workspace_id=ws, version=version, model=model,
                              monthly_net_minor=149_500 if model == "A" else 0,
                              lead_fee_net_minor=14_900 if model == "B" else 0, created_at=at))


def _approved(db, ws, n, at, net=14_900, model="B", version=1):
    for i in range(n):
        db.add(Lead(workspace_id=ws, source="manual", contact_name=f"Kunde {i}", qualification_status="qualified",
                    billing_status="approved", billing_decided_at=at,
                    fee_snapshot={"net_minor": net, "model": model, "agreement_version": version}))


def test_model_b_fourteen_leads(api, two_workspaces, db):
    ws = uuid.UUID(two_workspaces["ws_a"])
    _agreement(db, ws, 1, "B", datetime(2026, 8, 1, tzinfo=UTC))
    _approved(db, ws, 14, datetime(2026, 9, 10, 12, tzinfo=UTC))
    _approved(db, ws, 3, datetime(2026, 8, 31, 21, 59, tzinfo=UTC))  # 23:59 local 31/8 → August
    db.commit()
    s = api.get(two_workspaces["tok_a"], f"/workspaces/{ws}/billing/statement?month=2026-09").json()
    assert s["status"] == "preview" and s["invoicing"] == "not_implemented"
    assert s["approved_leads"] == 14 and s["billable_leads"] == 14
    assert s["totals"] == {"currency": "DKK", "net_minor": 208_600, "tax_minor": 52_150, "gross_minor": 260_750,
                           "tax_basis_points": 2500, "rounding": "half_up"}
    aug = api.get(two_workspaces["tok_a"], f"/workspaces/{ws}/billing/statement?month=2026-08").json()
    assert aug["approved_leads"] == 3 and aug["totals"]["net_minor"] == 44_700


def test_model_a_subscription_ignores_leads_and_snapshots_survive_changes(api, two_workspaces, db):
    ws = uuid.UUID(two_workspaces["ws_a"])
    _agreement(db, ws, 1, "B", datetime(2026, 8, 1, tzinfo=UTC))
    _approved(db, ws, 2, datetime(2026, 9, 5, tzinfo=UTC))                          # under B: 149 kr. each
    _agreement(db, ws, 2, "A", datetime(2026, 9, 20, tzinfo=UTC))
    _approved(db, ws, 5, datetime(2026, 9, 25, tzinfo=UTC), net=0, model="A", version=2)  # under A: 0
    db.commit()
    s = api.get(two_workspaces["tok_a"], f"/workspaces/{ws}/billing/statement?month=2026-09").json()
    kinds = [line["kind"] for line in s["lines"]]
    assert kinds.count("subscription") == 1 and kinds.count("lead") == 7
    assert s["billable_leads"] == 2
    assert s["totals"]["net_minor"] == 149_500 + 2 * 14_900


def test_no_agreement_roles_and_validation(api, two_workspaces, db):
    t = two_workspaces
    base = f"/workspaces/{t['ws_a']}/billing/statement"
    s = api.get(t["tok_a"], base).json()
    assert s["agreement"] is None and s["lines"] == [] and s["totals"]["gross_minor"] == 0
    assert api.get(t["tok_a"], f"{base}?month=2026-13").status_code == 422
    staff = api.add_member(t["tok_a"], t["ws_a"], "staff@testmail.dk", "staff")
    assert api.get(staff, base).status_code == 403
    assert api.get(t["tok_b"], base).status_code == 404
    db.execute(update(Lead).values(billing_status="approved"))  # no-op safety: nothing leaks across workspaces
    assert api.get(t["tok_b"], f"/workspaces/{t['ws_b']}/billing/statement").json()["lines"] == []

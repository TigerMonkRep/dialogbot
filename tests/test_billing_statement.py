"""Monthly statement: the subscription and the 4 kr. campaign calls in whole øre, month bounds in local time,
admin-only. Old model-B fee snapshots and old per-contact campaign packages still count, so past months and old
agreements do not change."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import update

from app.models import Campaign, CampaignCall, CampaignContact, Lead, ReceptionAgreement
from app.modules.billing import prices


def _agreement(db, ws, version, model, at):
    db.add(ReceptionAgreement(workspace_id=ws, version=version, model=model,
                              monthly_net_minor=prices.SUBSCRIPTION_MONTHLY_NET_MINOR if model == "A" else 0,
                              lead_fee_net_minor=14_900 if model == "B" else 0, created_at=at))


def _approved(db, ws, n, at, net=14_900, model="B", version=1):
    for i in range(n):
        db.add(Lead(workspace_id=ws, source="manual", contact_name=f"Kunde {i}", qualification_status="qualified",
                    billing_status="approved", billing_decided_at=at,
                    fee_snapshot={"net_minor": net, "model": model, "agreement_version": version}))


def test_legacy_model_b_fourteen_leads(api, two_workspaces, db):
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


def test_subscription_ignores_leads_and_old_snapshots_survive_changes(api, two_workspaces, db):
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
    assert s["totals"]["net_minor"] == 249_500 + 2 * 14_900


def test_campaign_calls_are_four_kroner_each_in_the_month_they_were_dialled(api, two_workspaces, db):
    ws = uuid.UUID(two_workspaces["ws_a"])
    _agreement(db, ws, 1, "A", datetime(2026, 8, 1, tzinfo=UTC))
    camp = Campaign(workspace_id=ws, name="Forårstilbud", call_net_minor=prices.CAMPAIGN_CALL_NET_MINOR, max_attempts=2,
                    max_connected_seconds=180)
    db.add(camp)
    db.flush()
    contact = CampaignContact(campaign_id=camp.id, workspace_id=ws, phone="+4520304050", kind="business")
    db.add(contact)
    db.flush()
    for at in (datetime(2026, 9, 3, 9, tzinfo=UTC), datetime(2026, 9, 3, 12, tzinfo=UTC), datetime(2026, 9, 30, 21, 59, tzinfo=UTC),
               datetime(2026, 8, 31, 21, 59, tzinfo=UTC)):  # the last is 23:59 local on 31/8 → August
        db.add(CampaignCall(workspace_id=ws, campaign_id=camp.id, contact_id=contact.id, dialled_at=at,
                            net_minor=prices.CAMPAIGN_CALL_NET_MINOR))
    db.commit()
    sep = api.get(two_workspaces["tok_a"], f"/workspaces/{ws}/billing/statement?month=2026-09").json()
    calls = [x for x in sep["lines"] if x["kind"] == "campaign_calls"]
    assert len(calls) == 1 and calls[0]["calls"] == 3 and calls[0]["net_minor"] == 1_200
    assert "3 udgående opkald" in calls[0]["description"]
    assert sep["totals"]["net_minor"] == 249_500 + 1_200 and sep["totals"]["gross_minor"] == 313_375
    aug = api.get(two_workspaces["tok_a"], f"/workspaces/{ws}/billing/statement?month=2026-08").json()
    assert [x["calls"] for x in aug["lines"] if x["kind"] == "campaign_calls"] == [1]
    # an old per-contact package (9 kr., charged before per-call pricing) is still on its month's statement
    contact.charged_at, contact.charged_net_minor = datetime(2026, 7, 10, 9, tzinfo=UTC), 900
    db.commit()
    jul = api.get(two_workspaces["tok_a"], f"/workspaces/{ws}/billing/statement?month=2026-07").json()
    assert [(x["kind"], x["net_minor"]) for x in jul["lines"]] == [("campaign", 900)]


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

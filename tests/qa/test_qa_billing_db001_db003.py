"""QA billing-qa · regression for DB-001 (Model A must not compute Model B lead charges) and DB-003 (unique contacts
and attempts persisted separately, all counters derived from the same run). Exact backlog numbers."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from app.models import Campaign, CampaignCall, CampaignContact, ReceptionAgreement


def test_db001_model_a_ignores_leads_model_b_charges_them():
    from app.modules.billing.money import CampaignPackageTerms, ReceptionAgreement as RA, calculator_total_net

    a = RA(model="A", monthly_net_minor=149_500)
    b = RA(model="B", lead_fee_net_minor=14_900)
    pkg = CampaignPackageTerms(net_minor=900, max_attempts=2, max_connected_ai_seconds_total=180)
    # 14 leads + 500 packages: A = 1.495 + 4.500 = 5.995 kr.; B = 14 × 149 + 4.500 = 6.586 kr.
    assert calculator_total_net(a, 14, pkg, 500) == 599_500
    assert calculator_total_net(a, 0, pkg, 500) == 599_500
    assert calculator_total_net(a, 1000, pkg, 500) == 599_500
    assert calculator_total_net(b, 14, pkg, 500) == 658_600


def test_db003_contacts_and_attempts_are_separate_and_consistent_with_the_statement(api, two_workspaces, db):
    """301 unique contacts; 119 of them dialled twice → 420 attempts. counts.total = 301, counts.calls = 420, and the
    statement bills exactly those 420 calls (420 × 4 kr. = 1.680 kr.)."""
    ws = uuid.UUID(two_workspaces["ws_a"])
    tok = two_workspaces["tok_a"]
    db.add(ReceptionAgreement(workspace_id=ws, version=1, model="A", monthly_net_minor=249_500, lead_fee_net_minor=0,
                              created_at=datetime(2026, 8, 1, tzinfo=UTC)))
    camp = Campaign(workspace_id=ws, name="DB-003", call_net_minor=400, minute_net_minor=200, max_attempts=2,
                    max_connected_seconds=180, status="completed")
    db.add(camp)
    db.flush()
    at = datetime(2026, 9, 10, 8, tzinfo=UTC)
    for i in range(301):
        twice = i < 119
        c = CampaignContact(campaign_id=camp.id, workspace_id=ws, phone=f"+4530{i:06d}", kind="business",
                            consent_source="QA", status="done" if i % 3 else "no_answer", attempts=2 if twice else 1)
        db.add(c)
        db.flush()
        for k in range(2 if twice else 1):
            db.add(CampaignCall(workspace_id=ws, campaign_id=camp.id, contact_id=c.id, dialled_at=at + timedelta(minutes=i, seconds=k),
                                net_minor=400, connected_seconds=0))
    db.commit()
    lst = api.get(tok, f"/workspaces/{ws}/campaigns").json()["items"]
    counts = next(x for x in lst if x["name"] == "DB-003")["counts"]
    assert counts["total"] == 301 and counts["calls"] == 420
    assert sum(counts["by_status"].values()) == counts["total"]
    st = api.get(tok, f"/workspaces/{ws}/billing/statement?month=2026-09").json()
    line = next(x for x in st["lines"] if x["kind"] == "campaign_calls")
    assert (line["calls"], line["net_minor"]) == (counts["calls"], 420 * 400)

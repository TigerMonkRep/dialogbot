"""Monthly statement: the subscription, the campaign calls (4 kr. + 2 kr. per started minute) and inbound minutes
above the included 300 in whole øre, month bounds in local time,
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
    assert len(calls) == 1 and calls[0]["calls"] == 3 and calls[0]["net_minor"] == 1_200  # no reports yet: no minutes
    assert "3 udgående opkald, 0 samtaleminutter" in calls[0]["description"]
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


def test_inbound_minutes_above_the_included_300_are_charged(api, two_workspaces, db):
    from app.models import Call, DemoCall
    from app.modules.billing import prices

    ws = uuid.UUID(two_workspaces["ws_a"])
    _agreement(db, ws, 1, "A", datetime(2026, 9, 1, tzinfo=UTC))
    at = datetime(2026, 9, 10, 9, tzinfo=UTC)
    # 290 full minutes, one 61-second call (2 started minutes) and one 30-second call (1 minute) = 293 minutes
    db.add(Call(workspace_id=ws, provider="vapi", provider_call_id="in_long", started_at=at, duration_seconds=290 * 60))
    db.add(Call(workspace_id=ws, provider="vapi", provider_call_id="in_61", started_at=at, duration_seconds=61))
    db.add(Call(workspace_id=ws, provider="vapi", provider_call_id="in_30", started_at=at, duration_seconds=30))
    # a demo call and a campaign call are outbound and never count as inbound minutes
    db.add(Call(workspace_id=ws, provider="vapi", provider_call_id="demo_1", started_at=at, duration_seconds=600))
    db.add(DemoCall(workspace_id=ws, source="web", phone="+4520304050", consent_version="demo-call-web-v2",
                    consent_text="ja", consented_at=at, provider_call_id="demo_1", status="done"))
    db.commit()
    tok = two_workspaces["tok_a"]
    sep = api.get(tok, f"/workspaces/{ws}/billing/statement?month=2026-09").json()
    inbound = [x for x in sep["lines"] if x["kind"] == "inbound_minutes"]
    assert len(inbound) == 1 and inbound[0]["calls"] == 3 and inbound[0]["minutes"] == 293
    assert inbound[0]["extra_minutes"] == 0 and inbound[0]["net_minor"] == 0  # within the included 300
    assert "300 min er med i abonnementet" in inbound[0]["description"]
    db.add(Call(workspace_id=ws, provider="vapi", provider_call_id="in_more", started_at=at, duration_seconds=10 * 60))
    db.commit()
    sep = api.get(tok, f"/workspaces/{ws}/billing/statement?month=2026-09").json()
    inbound = [x for x in sep["lines"] if x["kind"] == "inbound_minutes"][0]
    assert (inbound["minutes"], inbound["extra_minutes"]) == (303, 3)
    assert inbound["net_minor"] == 3 * prices.INBOUND_EXTRA_MINUTE_NET_MINOR == 450  # 1,50 kr. per extra minute
    assert "3 min ekstra à 1,50\u00a0kr." in inbound["description"]  # markets.fmt: a no-break space before kr.
    assert sep["totals"]["net_minor"] == 249_500 + 450
    # a month without inbound calls has no inbound line at all
    oct_lines = api.get(tok, f"/workspaces/{ws}/billing/statement?month=2026-10").json()["lines"]
    assert not [x for x in oct_lines if x["kind"] == "inbound_minutes"]


def _freeze(db, ws, month, st):
    """What stripe.create_invoice stores: the statement's lines frozen on the month's invoice."""
    from datetime import date

    from app.models import Invoice

    y, m = map(int, month.split("-"))
    db.add(Invoice(workspace_id=ws, month=date(y, m, 1), status="open", currency="DKK", net_minor=st["totals"]["net_minor"],
                   tax_minor=st["totals"]["tax_minor"], gross_minor=st["totals"]["gross_minor"], lines=st["lines"]))
    db.commit()


def test_usage_reported_after_the_invoice_is_billed_once_on_the_next_invoice(api, two_workspaces, db):
    """QA F-BQ-012: minutes that belong to an invoiced month but were reported after its invoice land on the next
    statement as «Efterregistreret forbrug <måned>» – exactly once, also when more arrive even later."""
    from app.models import Call

    ws, tok = uuid.UUID(two_workspaces["ws_a"]), two_workspaces["tok_a"]
    _agreement(db, ws, 1, "A", datetime(2026, 8, 1, tzinfo=UTC))
    db.add(Call(workspace_id=ws, provider="vapi", provider_call_id="oct_1", started_at=datetime(2026, 10, 5, 9, tzinfo=UTC),
                duration_seconds=310 * 60))
    camp = Campaign(workspace_id=ws, name="Efterår", call_net_minor=prices.CAMPAIGN_CALL_NET_MINOR, max_attempts=1,
                    max_connected_seconds=600)
    db.add(camp)
    db.flush()
    contact = CampaignContact(campaign_id=camp.id, workspace_id=ws, phone="+4520304050", kind="business")
    db.add(contact)
    db.flush()
    cc = CampaignCall(workspace_id=ws, campaign_id=camp.id, contact_id=contact.id, net_minor=prices.CAMPAIGN_CALL_NET_MINOR,
                      dialled_at=datetime(2026, 10, 31, 22, 55, tzinfo=UTC))  # 23:55 local, report not in yet
    db.add(cc)
    db.commit()
    get = lambda m: api.get(tok, f"/workspaces/{ws}/billing/statement?month={m}").json()  # noqa: E731
    _freeze(db, ws, "2026-10", get("2026-10"))  # October invoiced: 10 min extra (1.500) + one call (400)
    # the reports arrive after the invoice: an inbound call started 23:58 and the campaign call's 3 minutes
    db.add(Call(workspace_id=ws, provider="vapi", provider_call_id="oct_late", started_at=datetime(2026, 10, 31, 22, 58, tzinfo=UTC),
                duration_seconds=5 * 60))
    cc.connected_seconds, cc.minutes_net_minor = 170, 3 * prices.CAMPAIGN_MINUTE_NET_MINOR
    db.commit()
    nov = get("2026-11")
    late = sorted((x["usage_kind"], x["period"], x["minutes"], x["net_minor"]) for x in nov["lines"]
                  if x["kind"] == "late_usage_adjustment")
    assert late == [("campaign_calls", "2026-10", 3, 600), ("inbound_minutes", "2026-10", 5, 750)]
    assert any("Efterregistreret forbrug oktober 2026" in x["description"] for x in nov["lines"])
    assert nov["totals"]["net_minor"] == 249_500 + 600 + 750
    _freeze(db, ws, "2026-11", nov)
    # December: nothing billed twice …
    assert [x for x in get("2026-12")["lines"] if x["kind"] == "late_usage_adjustment"] == []
    # … but a still later report for October is picked up with only the new minutes
    db.add(Call(workspace_id=ws, provider="vapi", provider_call_id="oct_later", started_at=datetime(2026, 10, 31, 12, tzinfo=UTC),
                duration_seconds=2 * 60))
    db.commit()
    dec = [(x["period"], x["minutes"], x["net_minor"]) for x in get("2026-12")["lines"] if x["kind"] == "late_usage_adjustment"]
    assert dec == [("2026-10", 2, 300)]


def test_package_terms_come_from_the_agreement_not_the_list(api, two_workspaces, db, monkeypatch):
    """QA F-BQ-011: an agreement keeps its package (included minutes, overage price) when the list changes; a new
    agreement gets the new list."""
    from app.models import Call
    from app.modules.billing import agreements, markets

    ws, tok = uuid.UUID(two_workspaces["ws_a"]), two_workspaces["tok_a"]
    _agreement(db, ws, 1, "A", datetime(2026, 8, 1, tzinfo=UTC))
    db.add(Call(workspace_id=ws, provider="vapi", provider_call_id="sep", started_at=datetime(2026, 9, 10, 9, tzinfo=UTC),
                duration_seconds=310 * 60))
    db.commit()
    monkeypatch.setattr(prices, "INBOUND_INCLUDED_MINUTES", 200)
    monkeypatch.setitem(markets.ERHVERV["DKK"], "extra_minute", 300)
    line = [x for x in api.get(tok, f"/workspaces/{ws}/billing/statement?month=2026-09").json()["lines"]
            if x["kind"] == "inbound_minutes"][0]
    assert (line["included_minutes"], line["extra_minutes"], line["net_minor"]) == (300, 10, 1_500)
    a1 = db.query(ReceptionAgreement).filter_by(workspace_id=ws).one()
    a2 = agreements.create(db, ws, "A", None)
    assert (a2.inbound_included_minutes, a2.inbound_extra_minute_net_minor) == (200, 300)
    out = agreements.out(a1)
    assert out["inbound_included_minutes"] == 300 and out["inbound_extra_minute"]["net_minor"] == 150

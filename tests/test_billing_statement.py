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

# Months before 2026-11 keep the model they were invoiced under: 4 kr. per call dialled + 2 kr. per started minute,
# snapshotted on each call (the per-call fee was removed on 2026-11-10).
LEGACY_CALL, LEGACY_MINUTE = 400, 200


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
    camp = Campaign(workspace_id=ws, name="Forårstilbud", call_net_minor=LEGACY_CALL, max_attempts=2,
                    max_connected_seconds=180)
    db.add(camp)
    db.flush()
    contact = CampaignContact(campaign_id=camp.id, workspace_id=ws, phone="+4520304050", kind="business")
    db.add(contact)
    db.flush()
    for at in (datetime(2026, 9, 3, 9, tzinfo=UTC), datetime(2026, 9, 3, 12, tzinfo=UTC), datetime(2026, 9, 30, 21, 59, tzinfo=UTC),
               datetime(2026, 8, 31, 21, 59, tzinfo=UTC)):  # the last is 23:59 local on 31/8 → August
        db.add(CampaignCall(workspace_id=ws, campaign_id=camp.id, contact_id=contact.id, dialled_at=at,
                            net_minor=LEGACY_CALL))
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
    camp = Campaign(workspace_id=ws, name="Efterår", call_net_minor=LEGACY_CALL, max_attempts=1,
                    max_connected_seconds=600)
    db.add(camp)
    db.flush()
    contact = CampaignContact(campaign_id=camp.id, workspace_id=ws, phone="+4520304050", kind="business")
    db.add(contact)
    db.flush()
    cc = CampaignCall(workspace_id=ws, campaign_id=camp.id, contact_id=contact.id, net_minor=LEGACY_CALL,
                      dialled_at=datetime(2026, 10, 31, 22, 55, tzinfo=UTC))  # 23:55 local, report not in yet
    db.add(cc)
    db.commit()
    get = lambda m: api.get(tok, f"/workspaces/{ws}/billing/statement?month={m}").json()  # noqa: E731
    _freeze(db, ws, "2026-10", get("2026-10"))  # October invoiced: 10 min extra (1.500) + one call (400)
    # the reports arrive after the invoice: an inbound call started 23:58 and the campaign call's 3 minutes
    db.add(Call(workspace_id=ws, provider="vapi", provider_call_id="oct_late", started_at=datetime(2026, 10, 31, 22, 58, tzinfo=UTC),
                duration_seconds=5 * 60))
    cc.connected_seconds, cc.minutes_net_minor = 170, 3 * LEGACY_MINUTE
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


# --------------------------------------------------------------------------- shared package (from 2026-11)
# Fürster 2026-11-10: one package of 300 minutes a month for inbound AND outbound minutes, used in call order; above
# it 1,50 kr. per started inbound minute and 2 kr. per started outbound minute; no fee per outbound call.

def _campaign(db, ws, name="Vinter"):
    camp = Campaign(workspace_id=ws, name=name, call_net_minor=0, minute_net_minor=prices.OUTBOUND_EXTRA_MINUTE_NET_MINOR,
                    max_attempts=2, max_connected_seconds=180)
    db.add(camp)
    db.flush()
    contact = CampaignContact(campaign_id=camp.id, workspace_id=ws, phone="+4520304050", kind="business")
    db.add(contact)
    db.flush()
    return camp, contact


def test_shared_package_inbound_and_outbound_in_call_order(api, two_workspaces, db):
    from app.models import Call

    ws, tok = uuid.UUID(two_workspaces["ws_a"]), two_workspaces["tok_a"]
    _agreement(db, ws, 1, "A", datetime(2026, 8, 1, tzinfo=UTC))
    camp, contact = _campaign(db, ws)
    # 1/12: 250 inbound minutes; 2/12: campaign calls 40 + 20 minutes (and one unanswered); 3/12: 15 inbound minutes
    db.add(Call(workspace_id=ws, provider="vapi", provider_call_id="dec_in1", started_at=datetime(2026, 12, 1, 9, tzinfo=UTC),
                duration_seconds=250 * 60))
    for i, sec in enumerate((40 * 60, 19 * 60 + 1, 0)):
        db.add(CampaignCall(workspace_id=ws, campaign_id=camp.id, contact_id=contact.id, net_minor=0, connected_seconds=sec,
                            dialled_at=datetime(2026, 12, 2, 9, i, tzinfo=UTC)))
    db.add(Call(workspace_id=ws, provider="vapi", provider_call_id="dec_in2", started_at=datetime(2026, 12, 3, 9, tzinfo=UTC),
                duration_seconds=15 * 60))
    db.commit()
    st = api.get(tok, f"/workspaces/{ws}/billing/statement?month=2026-12").json()
    # package: 250 in + 40 out = 290; the 20-minute call takes the last 10 → 10 out over; the 15 inbound minutes are all over
    assert st["package"] == {"included": 300, "used": 325, "remaining": 0, "over": 25}
    out = next(x for x in st["lines"] if x["kind"] == "campaign_calls")
    inb = next(x for x in st["lines"] if x["kind"] == "inbound_minutes")
    assert (out["calls"], out["minutes"], out["package_minutes"], out["extra_minutes"], out["net_minor"]) == (3, 60, 50, 10, 2_000)
    assert (inb["minutes"], inb["package_minutes"], inb["extra_minutes"], inb["net_minor"]) == (265, 250, 15, 2_250)
    assert "Kampagne \"Vinter\": 3 udgående opkald, 60 samtaleminutter (50 min fra pakken, 10 min ud over pakken à 2" in out["description"]
    # the unanswered call (09:02) starts after the 20-minute call used up the package: 0,25 kr. (no report = cheapest)
    fees = next(x for x in st["lines"] if x["kind"] == "campaign_call_fees")
    assert (fees["calls"], fees["no_answer"], fees["net_minor"]) == (1, 1, 25)
    # 2.495 + 20 + 0,25 + 22,50 = 2.537,75 net; 25 % VAT (634,4375 → 634,44)
    assert st["totals"]["net_minor"] == 249_500 + 2_000 + 25 + 2_250 and st["totals"]["gross_minor"] == 317_219


def test_unanswered_campaign_calls_inside_the_package_cost_nothing_and_a_quiet_month_is_just_the_subscription(api, two_workspaces, db):
    ws, tok = uuid.UUID(two_workspaces["ws_a"]), two_workspaces["tok_a"]
    _agreement(db, ws, 1, "A", datetime(2026, 8, 1, tzinfo=UTC))
    camp, contact = _campaign(db, ws)
    for i in range(5):  # five unanswered attempts inside the package (an old 4 kr. snapshot on the call is not charged)
        db.add(CampaignCall(workspace_id=ws, campaign_id=camp.id, contact_id=contact.id, net_minor=400, connected_seconds=0,
                            dialled_at=datetime(2026, 11, 20, 9, i, tzinfo=UTC)))
    db.commit()
    st = api.get(tok, f"/workspaces/{ws}/billing/statement?month=2026-11").json()
    assert [x["net_minor"] for x in st["lines"] if x["kind"] == "campaign_calls"] == [0]
    assert st["totals"]["net_minor"] == 249_500 and st["package"]["used"] == 0
    # October (invoiced under the old model) keeps it: the same calls a month earlier cost 4 kr. each
    for i in range(2):
        db.add(CampaignCall(workspace_id=ws, campaign_id=camp.id, contact_id=contact.id, net_minor=400, connected_seconds=0,
                            dialled_at=datetime(2026, 10, 20, 9, i, tzinfo=UTC)))
    db.commit()
    octo = api.get(tok, f"/workspaces/{ws}/billing/statement?month=2026-10").json()
    assert octo["package"] is None and [x["net_minor"] for x in octo["lines"] if x["kind"] == "campaign_calls"] == [800]


def test_outbound_price_is_the_agreements_snapshot(api, two_workspaces, db, monkeypatch):
    from app.modules.billing import agreements, markets

    ws, tok = uuid.UUID(two_workspaces["ws_a"]), two_workspaces["tok_a"]
    _agreement(db, ws, 1, "A", datetime(2026, 8, 1, tzinfo=UTC))
    camp, contact = _campaign(db, ws)
    db.add(CampaignCall(workspace_id=ws, campaign_id=camp.id, contact_id=contact.id, net_minor=0, connected_seconds=310 * 60,
                        dialled_at=datetime(2026, 11, 3, 9, tzinfo=UTC)))
    db.commit()
    monkeypatch.setitem(markets.ERHVERV["DKK"], "outbound_extra_minute", 500)
    line = next(x for x in api.get(tok, f"/workspaces/{ws}/billing/statement?month=2026-11").json()["lines"]
                if x["kind"] == "campaign_calls")
    assert (line["extra_minutes"], line["net_minor"]) == (10, 2_000)  # 2 kr. from the agreement, not the new list
    a = db.query(ReceptionAgreement).filter_by(workspace_id=ws).one()
    assert a.outbound_extra_minute_net_minor == 200 and agreements.out(a)["outbound_extra_minute"]["net_minor"] == 200


def test_late_usage_in_a_shared_package_month_is_compared_as_a_whole(api, two_workspaces, db):
    """A late inbound call that started before campaign calls moves package minutes between the kinds; the
    adjustment is the difference for the month as a whole (F-BQ-012 with the shared package)."""
    from app.models import Call
    from tests.test_billing_statement import _freeze

    ws, tok = uuid.UUID(two_workspaces["ws_a"]), two_workspaces["tok_a"]
    _agreement(db, ws, 1, "A", datetime(2026, 8, 1, tzinfo=UTC))
    camp, contact = _campaign(db, ws)
    db.add(CampaignCall(workspace_id=ws, campaign_id=camp.id, contact_id=contact.id, net_minor=0, connected_seconds=300 * 60,
                        dialled_at=datetime(2026, 11, 10, 9, tzinfo=UTC)))
    db.commit()
    get = lambda m: api.get(tok, f"/workspaces/{ws}/billing/statement?month={m}").json()  # noqa: E731
    _freeze(db, ws, "2026-11", get("2026-11"))  # November: the campaign used exactly the package → 0 extra
    # an inbound call of 10 minutes on 9/11 reported after the invoice: it takes 10 package minutes first, so the
    # campaign's last 10 minutes are now over (10 × 2 kr. = 20 kr.)
    db.add(Call(workspace_id=ws, provider="vapi", provider_call_id="nov_late", started_at=datetime(2026, 11, 9, 9, tzinfo=UTC),
                duration_seconds=10 * 60))
    db.commit()
    late = [x for x in get("2026-12")["lines"] if x["kind"] == "late_usage_adjustment"]
    assert [(x["usage_kind"], x["period"], x["minutes"], x["net_minor"]) for x in late] == [("package", "2026-11", 10, 2_000)]


# --------------------------------------------------------------------------- call price after the package (A')
# Fürster 2026-11-10 20:28: inside the package no call price; a campaign call that STARTS after the package is used
# up costs 4 kr. answered / 1 kr. voicemail / 0,25 kr. unanswered-busy (unknown = 0,25 kr.) + 2 kr. per started
# minute; a call that crosses the limit only splits its minutes.

def test_call_price_by_outcome_only_for_calls_that_start_after_the_package(api, two_workspaces, db):
    from app.models import Call

    ws, tok = uuid.UUID(two_workspaces["ws_a"]), two_workspaces["tok_a"]
    _agreement(db, ws, 1, "A", datetime(2026, 8, 1, tzinfo=UTC))
    camp, contact = _campaign(db, ws)
    db.add(Call(workspace_id=ws, provider="vapi", provider_call_id="ap_in", started_at=datetime(2026, 11, 2, 9, tzinfo=UTC),
                duration_seconds=295 * 60))  # 295 of 300 minutes
    calls = [  # (minute of 3/11 09:xx, seconds, outcome)
        (0, 10 * 60, "answered"),   # crosses the limit: 5 in the package, 5 over – NO call price
        (1, 2 * 60, "answered"),    # starts after the package: 4 kr. + 2 min × 2 kr.
        (2, 0, "voicemail"),        # 1 kr.
        (3, 0, "no_answer"),        # 0,25 kr.
        (4, None, None),            # no report yet: billed as the cheapest, 0,25 kr.
    ]
    for m, sec, outcome in calls:
        db.add(CampaignCall(workspace_id=ws, campaign_id=camp.id, contact_id=contact.id, net_minor=0, connected_seconds=sec,
                            outcome_class=outcome, dialled_at=datetime(2026, 11, 3, 9, m, tzinfo=UTC)))
    db.commit()
    st = api.get(tok, f"/workspaces/{ws}/billing/statement?month=2026-11").json()
    minutes = next(x for x in st["lines"] if x["kind"] == "campaign_calls")
    fees = next(x for x in st["lines"] if x["kind"] == "campaign_call_fees")
    assert (minutes["minutes"], minutes["package_minutes"], minutes["extra_minutes"], minutes["net_minor"]) == (12, 5, 7, 1_400)
    assert (fees["calls"], fees["answered"], fees["voicemail"], fees["no_answer"], fees["net_minor"]) == (4, 1, 1, 2, 400 + 100 + 25 + 25)
    assert "1 besvaret à 4" in fees["description"] and "1 telefonsvarer à 1" in fees["description"]
    assert st["totals"]["net_minor"] == 249_500 + 1_400 + 550


def test_no_call_price_inside_the_package(api, two_workspaces, db):
    ws, tok = uuid.UUID(two_workspaces["ws_a"]), two_workspaces["tok_a"]
    _agreement(db, ws, 1, "A", datetime(2026, 8, 1, tzinfo=UTC))
    camp, contact = _campaign(db, ws)
    for i, outcome in enumerate(("answered", "voicemail", "no_answer")):
        db.add(CampaignCall(workspace_id=ws, campaign_id=camp.id, contact_id=contact.id, net_minor=0,
                            connected_seconds=60 if outcome == "answered" else 0, outcome_class=outcome,
                            dialled_at=datetime(2026, 11, 3, 9, i, tzinfo=UTC)))
    db.commit()
    st = api.get(tok, f"/workspaces/{ws}/billing/statement?month=2026-11").json()
    assert not [x for x in st["lines"] if x["kind"] == "campaign_call_fees"] and st["totals"]["net_minor"] == 249_500


def test_outcome_class_mapping():
    from app.modules.campaigns.service import outcome_class

    assert outcome_class("voicemail", False) == "voicemail"
    assert outcome_class("customer-ended-call", True) == "answered"
    for reason in ("customer-did-not-answer", "customer-busy", "twilio-failed-to-connect-call", "customer-ended-call"):
        assert outcome_class(reason, False) == "no_answer", reason


def test_call_prices_are_the_agreements_snapshot(api, two_workspaces, db, monkeypatch):
    from app.modules.billing import agreements, markets

    ws = uuid.UUID(two_workspaces["ws_a"])
    a = agreements.create(db, ws, "A", None)
    db.commit()
    assert (a.outbound_call_answered_net_minor, a.outbound_call_voicemail_net_minor, a.outbound_call_no_answer_net_minor) == (400, 100, 25)
    monkeypatch.setitem(markets.ERHVERV["DKK"], "call_answered", 999)
    assert agreements.out(a)["outbound_call"]["answered"]["net_minor"] == 400
    assert agreements.create(db, ws, "A", None).outbound_call_answered_net_minor == 999  # a new version takes the new list

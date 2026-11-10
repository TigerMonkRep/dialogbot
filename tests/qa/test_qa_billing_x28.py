"""QA billing-qa · X28 – Erhverv usage pricing (independent expected values).

Price rules (billing-qa agent definition, the source of truth):
  outbound campaign call: 4 kr. per call + 2 kr. per STARTED conversation minute (excl. VAT)
  inbound: 300 minutes/month included, then 1,50 kr. per started minute (excl. VAT)
  25 % VAT, minor units, calendar months in Europe/Copenhagen.

Every expected number below is computed by hand in this file, never by calling the code under test.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from app.models import Call, Campaign, CampaignCall, CampaignContact, Conversation, ReceptionAgreement

SUB = 249_500          # 2.495 kr./md.
CALL = 400             # 4 kr.
MIN = 200              # 2 kr. per started minute
EXTRA = 150            # 1,50 kr. per started inbound minute above 300


def _agreement(db, ws, at=datetime(2025, 12, 1, tzinfo=UTC)):
    db.add(ReceptionAgreement(workspace_id=ws, version=1, model="A", monthly_net_minor=SUB, lead_fee_net_minor=0,
                              created_at=at))


def _statement(api, tok, ws, month):
    r = api.get(tok, f"/workspaces/{ws}/billing/statement?month={month}")
    assert r.status_code == 200, r.text
    return r.json()


def _line(st, kind):
    xs = [x for x in st["lines"] if x["kind"] == kind]
    return xs[0] if xs else None


def _inbound(db, ws, n, at, seconds):
    db.add(Call(workspace_id=ws, provider="vapi", provider_call_id=f"in_{uuid.uuid4().hex[:12]}_{n}", started_at=at,
                duration_seconds=seconds))


# --------------------------------------------------------------------------- campaign calls through the real report path

def _campaign(db, ws):
    camp = Campaign(workspace_id=ws, name="X28 kampagne", call_net_minor=CALL, minute_net_minor=MIN, max_attempts=2,
                    max_connected_seconds=180, status="running")
    db.add(camp)
    db.flush()
    return camp


def _dial(db, ws, camp, call_id, at):
    contact = CampaignContact(campaign_id=camp.id, workspace_id=ws, phone=f"+4520{uuid.uuid4().int % 10**6:06d}",
                              kind="business", consent_source="QA", status="calling", attempts=1,
                              provider_call_id=call_id, last_attempt_at=at)
    db.add(contact)
    db.flush()
    db.add(CampaignCall(workspace_id=ws, campaign_id=camp.id, contact_id=contact.id, provider_call_id=call_id,
                        dialled_at=at, net_minor=camp.call_net_minor))
    db.flush()
    return contact


def _report(db, ws, call_id, duration, *, answered=True):
    from app.modules.campaigns import service

    conv = Conversation(workspace_id=ws, channel="phone", visitor_token_digest="-" * 64)
    db.add(conv)
    db.flush()
    msg = {"endedReason": "customer-ended-call" if answered else "customer-did-not-answer"}
    assert service.on_report(db, msg, call_id=call_id, conv=conv, duration=duration,
                             visitor_lines=1 if answered else 0, transcript="Kontakt: nej tak", summary="nej tak")


@pytest.fixture
def no_llm(monkeypatch):
    from app.modules.campaigns import service

    monkeypatch.setattr(service, "classify", lambda db, ws, transcript, fallback: ("not_interested", "Nej tak"))


def test_x28_campaign_call_minute_boundaries_0_1_59_60_61(api, two_workspaces, db, no_llm):
    ws = uuid.UUID(two_workspaces["ws_a"])
    _agreement(db, ws)
    camp = _campaign(db, ws)
    at = datetime(2026, 9, 15, 10, tzinfo=UTC)
    # (seconds, expected started minutes) – by the rule, independent of the code
    cases = [(0, 0), (1, 1), (59, 1), (60, 1), (61, 2)]
    for i, (_sec, _) in enumerate(cases):
        _dial(db, ws, camp, f"x28_c{i}", at)
    _dial(db, ws, camp, "x28_noanswer", at)
    db.commit()
    for i, (sec, _) in enumerate(cases):
        _report(db, ws, f"x28_c{i}", sec)
    _report(db, ws, "x28_noanswer", 30, answered=False)  # not answered: 4 kr., no minutes
    db.commit()
    rows = {c.provider_call_id: c for c in db.query(CampaignCall).filter_by(campaign_id=camp.id)}
    for i, (sec, minutes) in enumerate(cases):
        c = rows[f"x28_c{i}"]
        assert (c.net_minor, c.minutes_net_minor) == (CALL, minutes * MIN), (sec, c.connected_seconds)
    assert (rows["x28_noanswer"].net_minor, rows["x28_noanswer"].minutes_net_minor) == (CALL, 0)
    st = _statement(api, two_workspaces["tok_a"], ws, "2026-09")
    line = _line(st, "campaign_calls")
    exp_minutes = sum(m for _, m in cases)                       # 0+1+1+1+2 = 5
    exp_net = 6 * CALL + exp_minutes * MIN                        # 2.400 + 1.000 = 3.400
    assert (line["calls"], line["minutes"], line["net_minor"]) == (6, 5, 3_400) == (6, exp_minutes, exp_net)
    assert "6 udgående opkald, 5 samtaleminutter" in line["description"]
    net = SUB + 3_400                                             # 252.900
    assert st["totals"]["net_minor"] == net and st["totals"]["tax_minor"] == 63_225 and st["totals"]["gross_minor"] == 316_125


def test_x28_duplicate_end_of_call_report_is_priced_once(api, two_workspaces, db, no_llm):
    ws = uuid.UUID(two_workspaces["ws_a"])
    _agreement(db, ws)
    camp = _campaign(db, ws)
    _dial(db, ws, camp, "x28_dup", datetime(2026, 9, 15, 10, tzinfo=UTC))
    db.commit()
    _report(db, ws, "x28_dup", 125)   # 3 started minutes
    _report(db, ws, "x28_dup", 400)   # a resent / late report must not re-price
    db.commit()
    c = db.query(CampaignCall).filter_by(provider_call_id="x28_dup").one()
    assert (c.connected_seconds, c.minutes_net_minor) == (125, 3 * MIN)
    assert _line(_statement(api, two_workspaces["tok_a"], ws, "2026-09"), "campaign_calls")["net_minor"] == CALL + 3 * MIN


@pytest.mark.xfail(strict=True, reason="F-BQ-001-X28: needs-decision – fractional seconds are truncated before rounding "
                                       "up (60.4 s billed as 1 started minute)")
def test_x28_fractional_second_past_a_minute_is_a_started_minute(api, two_workspaces, db, no_llm):
    """Vapi reports durationSeconds as a float. 60.4 s has started the 2nd minute; the rule says 'per started minute'."""
    ws = uuid.UUID(two_workspaces["ws_a"])
    _agreement(db, ws)
    camp = _campaign(db, ws)
    _dial(db, ws, camp, "x28_frac", datetime(2026, 9, 15, 10, tzinfo=UTC))
    db.commit()
    _report(db, ws, "x28_frac", 60.4)
    db.commit()
    c = db.query(CampaignCall).filter_by(provider_call_id="x28_frac").one()
    assert c.minutes_net_minor == 2 * MIN


def test_x28_price_snapshot_survives_a_list_price_change(api, two_workspaces, db, no_llm, monkeypatch):
    from app.modules.billing import markets, prices

    ws = uuid.UUID(two_workspaces["ws_a"])
    _agreement(db, ws)
    camp = _campaign(db, ws)
    _dial(db, ws, camp, "x28_snap", datetime(2026, 9, 15, 10, tzinfo=UTC))
    db.commit()
    _report(db, ws, "x28_snap", 90)
    db.commit()
    monkeypatch.setattr(prices, "CAMPAIGN_CALL_NET_MINOR", 999)
    monkeypatch.setitem(markets.ERHVERV["DKK"], "call", 999)
    monkeypatch.setitem(markets.ERHVERV["DKK"], "minute", 999)
    assert _line(_statement(api, two_workspaces["tok_a"], ws, "2026-09"), "campaign_calls")["net_minor"] == CALL + 2 * MIN


# --------------------------------------------------------------------------- inbound minutes

def test_x28_inbound_boundaries_and_exactly_300_included(api, two_workspaces, db):
    ws = uuid.UUID(two_workspaces["ws_a"])
    tok = two_workspaces["tok_a"]
    _agreement(db, ws)
    at = datetime(2026, 9, 10, 9, tzinfo=UTC)
    for i, sec in enumerate((0, 1, 59, 60, 61)):   # 0+1+1+1+2 = 5 started minutes, 5 calls
        _inbound(db, ws, i, at, sec)
    _inbound(db, ws, 9, at, 295 * 60)              # 295 → exactly 300
    db.commit()
    line = _line(_statement(api, tok, ws, "2026-09"), "inbound_minutes")
    assert (line["calls"], line["minutes"], line["extra_minutes"], line["net_minor"]) == (6, 300, 0, 0)
    _inbound(db, ws, 10, at, 1)                    # 301st minute
    db.commit()
    st = _statement(api, tok, ws, "2026-09")
    line = _line(st, "inbound_minutes")
    assert (line["minutes"], line["extra_minutes"], line["net_minor"]) == (301, 1, EXTRA)
    # VAT half-up on the total: (249.500 + 150) × 25 % = 62.412,5 → 62.413
    assert st["totals"] == {"currency": "DKK", "net_minor": 249_650, "tax_minor": 62_413, "gross_minor": 312_063,
                            "tax_basis_points": 2500, "rounding": "half_up"}


def test_x28_included_minutes_reset_at_copenhagen_midnight_month_change(api, two_workspaces, db):
    """CET after 25/10: 31/10 23:59:59 local = 22:59:59Z; 1/11 00:00 local = 23:00:00Z."""
    ws = uuid.UUID(two_workspaces["ws_a"])
    tok = two_workspaces["tok_a"]
    _agreement(db, ws)
    _inbound(db, ws, 1, datetime(2026, 10, 5, 9, tzinfo=UTC), 309 * 60)
    _inbound(db, ws, 2, datetime(2026, 10, 31, 22, 59, 59, tzinfo=UTC), 60)       # October: 310 → 10 extra
    _inbound(db, ws, 3, datetime(2026, 10, 31, 23, 0, 0, tzinfo=UTC), 5 * 60)     # November: fresh 300
    db.commit()
    octo = _line(_statement(api, tok, ws, "2026-10"), "inbound_minutes")
    nov = _line(_statement(api, tok, ws, "2026-11"), "inbound_minutes")
    assert (octo["calls"], octo["minutes"], octo["extra_minutes"], octo["net_minor"]) == (2, 310, 10, 1_500)
    assert (nov["calls"], nov["minutes"], nov["extra_minutes"], nov["net_minor"]) == (1, 5, 0, 0)


def test_x28_dst_start_month_boundary_and_new_year(api, two_workspaces, db):
    """CEST in spring: 31/3 23:59:59 local = 21:59:59Z; 1/4 00:00 local = 22:00Z. New year: CET, 31/12 23:00Z = 1/1."""
    ws = uuid.UUID(two_workspaces["ws_a"])
    tok = two_workspaces["tok_a"]
    _agreement(db, ws)
    _inbound(db, ws, 1, datetime(2026, 3, 29, 1, 30, tzinfo=UTC), 60)              # 03:30 CEST on the DST day → March
    _inbound(db, ws, 2, datetime(2026, 3, 31, 21, 59, 59, tzinfo=UTC), 60)         # March
    _inbound(db, ws, 3, datetime(2026, 3, 31, 22, 0, 0, tzinfo=UTC), 60)           # April
    _inbound(db, ws, 4, datetime(2026, 10, 25, 0, 30, tzinfo=UTC), 60)             # 02:30 CEST, the repeated hour → October
    _inbound(db, ws, 5, datetime(2026, 10, 25, 1, 30, tzinfo=UTC), 60)             # 02:30 CET, the repeated hour → October
    _inbound(db, ws, 6, datetime(2025, 12, 31, 22, 59, 59, tzinfo=UTC), 60)        # December 2025
    _inbound(db, ws, 7, datetime(2025, 12, 31, 23, 0, 0, tzinfo=UTC), 60)          # January 2026
    db.commit()
    got = {m: (_line(_statement(api, tok, ws, m), "inbound_minutes") or {}).get("calls", 0)
           for m in ("2025-12", "2026-01", "2026-03", "2026-04", "2026-10")}
    assert got == {"2025-12": 1, "2026-01": 1, "2026-03": 2, "2026-04": 1, "2026-10": 2}


def test_x28_campaign_calls_counted_in_copenhagen_month_of_dialling(api, two_workspaces, db):
    ws = uuid.UUID(two_workspaces["ws_a"])
    _agreement(db, ws)
    camp = _campaign(db, ws)
    _dial(db, ws, camp, "x28_m1", datetime(2026, 3, 31, 21, 59, 59, tzinfo=UTC))   # 23:59:59 CEST → March
    _dial(db, ws, camp, "x28_m2", datetime(2026, 3, 31, 22, 0, 0, tzinfo=UTC))     # 00:00 CEST 1/4 → April
    db.commit()
    tok = two_workspaces["tok_a"]
    assert _line(_statement(api, tok, ws, "2026-03"), "campaign_calls")["calls"] == 1
    assert _line(_statement(api, tok, ws, "2026-04"), "campaign_calls")["calls"] == 1


def test_x28_campaign_calls_never_count_as_inbound_minutes(api, two_workspaces, db, no_llm):
    ws = uuid.UUID(two_workspaces["ws_a"])
    _agreement(db, ws)
    camp = _campaign(db, ws)
    at = datetime(2026, 9, 15, 10, tzinfo=UTC)
    _dial(db, ws, camp, "x28_out", at)
    db.add(Call(workspace_id=ws, provider="vapi", provider_call_id="x28_out", started_at=at, duration_seconds=400 * 60))
    db.commit()
    st = _statement(api, two_workspaces["tok_a"], ws, "2026-09")
    assert _line(st, "inbound_minutes") is None


# --------------------------------------------------------------------------- the prices the customer is shown

def test_x28_agreement_plan_prices_are_in_the_workspace_currency(api, two_workspaces, db):
    """/app/konto shows the subscription, call, minute and extra-minute prices from GET /agreement → plan, formatted in
    the account's currency. A Swedish company is charged the SEK list prices (markets.ERHVERV['SEK']: 3.695 kr/md,
    5,90 kr per call, 2,95 kr per minute, 2,20 kr per extra minute) and must be shown them – not the DKK numbers."""
    from app.models import BusinessProfile

    tok, ws = two_workspaces["tok_a"], two_workspaces["ws_a"]
    p = db.get(BusinessProfile, uuid.UUID(ws))
    p.country = "SE"
    db.commit()
    acc = api.get(tok, f"/workspaces/{ws}/billing/account").json()
    assert acc["currency"] == "SEK"
    plan = api.get(tok, f"/workspaces/{ws}/agreement").json()["plan"]
    shown = (plan["monthly_net_minor"], plan["campaign_call_net_minor"], plan["campaign_minute_net_minor"],
             plan["inbound_extra_minute_net_minor"])
    assert shown == (369_500, 590, 295, 220), f"konto would show {shown} as SEK"


def test_x28_konto_text_says_started_minute_for_campaign_calls_like_for_inbound():
    """The price rule is 2 kr. per STARTED minute; the inbound line already says «pr. påbegyndt minut»."""
    import json
    from pathlib import Path

    acc = json.loads((Path(__file__).resolve().parents[2] / "web/src/i18n/messages/da/app.json").read_text())["account"]["sub"]
    assert "påbegyndt minut" in acc["inboundExtra"] and "påbegyndt minut" in acc["inboundPrice"]
    assert "påbegyndt minut" in acc["campaignPrice"], acc["campaignPrice"]

"""Verifier (2026-11-11): independent check of Fürster's pricing decisions 2026-11-10 (model A').

Rules, taken ONLY from the commit messages c36eca3 / 23b79c8 / 631cecc and docs/pricing.md (not from the code):
- one package of 300 started minutes a month, inbound + outbound together, used in the order the calls happen
  (inbound by start, campaign calls by dialling); demo/test calls never count;
- inside the package: no price per call;
- above it: inbound 1,50 kr. / outbound 2 kr. per started minute (agreement snapshot; SEK/NOK/EUR = markets table);
- an outbound call that STARTS after the package is used up: + 4 kr. answered / 1 kr. voicemail / 0,25 kr.
  unanswered/busy, unknown outcome (no report yet) = 0,25 kr.; a call that crosses the limit only splits its minutes;
- usage reported after the invoice → «Efterregistreret forbrug» on the next invoice, once;
- complaint approved in an open month → minutes back in the package; in an invoiced month → credit line on the next
  invoice, once.

`expected()` below is a hand-written model of those rules; every scenario also states its numbers literally.
"""
from __future__ import annotations

import math
import uuid
from datetime import UTC, date, datetime

from app.models import BusinessProfile, Call, Campaign, CampaignCall, CampaignContact, DemoCall, Invoice
from app.modules.billing import statement as st_mod
from app.modules.campaigns import service

TZ = "Europe/Copenhagen"
DKK = {"inbound": 150, "outbound": 200, "call": {"answered": 400, "voicemail": 100, "no_answer": 25}}
SEK = {"inbound": 220, "outbound": 295, "call": {"answered": 590, "voicemail": 150, "no_answer": 35}}
NOK = {"inbound": 235, "outbound": 315, "call": {"answered": 630, "voicemail": 160, "no_answer": 40}}
EUR = {"inbound": 20, "outbound": 27, "call": {"answered": 55, "voicemail": 14, "no_answer": 3}}


def expected(events, p, included=300):
    """events: (at, 'inbound'|'outbound', seconds, outcome|None). Returns total usage net (minor) and parts."""
    left, minutes_net, fees, over = included, 0, 0, 0
    for _at, d, sec, outcome in sorted(events, key=lambda e: e[0]):
        m = math.ceil((sec or 0) / 60)
        if d == "outbound" and left == 0:
            fees += p["call"][outcome or "no_answer"]
        used = min(m, left)
        left -= used
        over += m - used
        minutes_net += (m - used) * p[d]
    return {"minutes_net": minutes_net, "fees": fees, "total": minutes_net + fees, "over": over, "left": left}


def _t(day, h, mi=0, month=11, year=2026):
    return datetime(year, month, day, h, mi, tzinfo=UTC)


class W:
    def __init__(self, db, ws):
        self.db, self.ws = db, ws
        self.camp = Campaign(workspace_id=ws, name="Vinter", call_net_minor=0, minute_net_minor=200, max_attempts=2,
                             max_connected_seconds=180)
        db.add(self.camp)
        db.flush()
        self.contact = CampaignContact(campaign_id=self.camp.id, workspace_id=ws, phone="+4520304050", kind="business")
        db.add(self.contact)
        db.flush()
        self.events = []

    def inbound(self, at, sec):
        c = Call(workspace_id=self.ws, provider="vapi", provider_call_id=f"in_{uuid.uuid4().hex[:8]}", started_at=at,
                 duration_seconds=sec, from_number="+4520000001")
        self.db.add(c)
        self.db.flush()
        self.events.append((at, "inbound", sec, None))
        return c

    def outbound(self, at, sec, outcome):
        c = CampaignCall(workspace_id=self.ws, campaign_id=self.camp.id, contact_id=self.contact.id, net_minor=0,
                         dialled_at=at, connected_seconds=sec, outcome_class=outcome,
                         provider_call_id=f"out_{uuid.uuid4().hex[:8]}")
        self.db.add(c)
        self.db.flush()
        self.events.append((at, "outbound", sec, outcome))
        return c


def _agreement(api, tok, ws):
    r = api.post(tok, f"/workspaces/{ws}/agreement", {"model": "A"})
    assert r.status_code in (200, 201), r.text
    return r.json()


def _st(api, tok, ws, month):
    r = api.get(tok, f"/workspaces/{ws}/billing/statement?month={month}")
    assert r.status_code == 200, r.text
    return r.json()


def _usage(st):
    return sum(x["net_minor"] for x in st["lines"] if x["kind"] in ("campaign_calls", "campaign_call_fees", "inbound_minutes"))


def _freeze(db, ws, month, st):
    y, m = map(int, month.split("-"))
    db.add(Invoice(workspace_id=ws, month=date(y, m, 1), status="open", currency=st["currency"],
                   net_minor=st["totals"]["net_minor"], tax_minor=st["totals"]["tax_minor"],
                   gross_minor=st["totals"]["gross_minor"], lines=st["lines"]))
    db.commit()


# --------------------------------------------------------------------------- V1 under the package


def test_v1_under_300_minutes_costs_only_the_subscription(api, two_workspaces, db):
    tok, ws = two_workspaces["tok_a"], uuid.UUID(two_workspaces["ws_a"])
    _agreement(api, tok, ws)
    w = W(db, ws)
    w.inbound(_t(2, 8), 100 * 60)
    w.outbound(_t(2, 9), 125, "answered")       # 3 min
    w.outbound(_t(2, 10), 0, "no_answer")       # inside the package: no call price
    w.outbound(_t(2, 11), 0, "voicemail")       # idem
    w.inbound(_t(3, 8), 61)                      # 2 min
    db.commit()
    s = _st(api, tok, ws, "2026-11")
    assert expected(w.events, DKK)["total"] == 0
    assert s["package"] == {"included": 300, "used": 105, "remaining": 195, "over": 0}
    assert _usage(s) == 0 and s["totals"]["net_minor"] == 249_500 and s["totals"]["gross_minor"] == 311_875
    assert not [x for x in s["lines"] if x["kind"] == "campaign_call_fees"]


# --------------------------------------------------------------------------- V2 over, mixed, every outcome


def _mixed(w):
    w.inbound(_t(2, 8), 250 * 60)               # 250 → 50 left
    w.outbound(_t(2, 9), 125, "answered")        # 3 → 47 left, no fee
    w.inbound(_t(2, 10), 46 * 60 + 1)            # 47 → exactly 0 left (fills, does not cross)
    w.outbound(_t(2, 11), 0, "no_answer")        # after package: 0,25
    w.outbound(_t(2, 12), 0, "voicemail")        # after package: 1
    w.outbound(_t(2, 13), 61, "answered")        # after package: 4 + 2 min × 2 = 8
    w.inbound(_t(2, 14), 10 * 60)                # 10 × 1,50 = 15
    w.outbound(_t(2, 15), 0, None)               # no report yet: 0,25


def test_v2_over_the_package_mixed_chronology_every_outcome(api, two_workspaces, db):
    tok, ws = two_workspaces["tok_a"], uuid.UUID(two_workspaces["ws_a"])
    _agreement(api, tok, ws)
    w = W(db, ws)
    _mixed(w)
    db.commit()
    e = expected(w.events, DKK)
    assert (e["fees"], e["minutes_net"], e["total"]) == (25 + 100 + 400 + 25, 2 * 200 + 10 * 150, 2_450)
    s = _st(api, tok, ws, "2026-11")
    assert s["package"] == {"included": 300, "used": 312, "remaining": 0, "over": 12}
    fees = [x for x in s["lines"] if x["kind"] == "campaign_call_fees"]
    assert len(fees) == 1 and fees[0]["net_minor"] == 550
    assert (fees[0]["answered"], fees[0]["voicemail"], fees[0]["no_answer"]) == (1, 1, 2)
    camp = next(x for x in s["lines"] if x["kind"] == "campaign_calls")
    assert (camp["calls"], camp["minutes"], camp["package_minutes"], camp["extra_minutes"], camp["net_minor"]) == (5, 5, 3, 2, 400)
    inb = next(x for x in s["lines"] if x["kind"] == "inbound_minutes")
    assert (inb["minutes"], inb["package_minutes"], inb["extra_minutes"], inb["net_minor"]) == (307, 297, 10, 1_500)
    assert _usage(s) == e["total"] == 2_450
    assert s["totals"]["net_minor"] == 251_950 and s["totals"]["tax_minor"] == 62_988 and s["totals"]["gross_minor"] == 314_938
    # Konto «Forbrug pr. opkald» shows the same per call and adds up to the statement
    u = api.get(tok, f"/workspaces/{ws}/billing/usage?month=2026-11").json()
    assert sum(c["net_minor"] for c in u["calls"]) == 2_450 and u["package"] == s["package"]
    per = [(c["kind"], c["minutes"], c["call_net_minor"], c["net_minor"]) for c in u["calls"]]
    assert per == [("inbound", 250, 0, 0), ("outbound", 3, 0, 0), ("inbound", 47, 0, 0), ("outbound", 0, 25, 25),
                   ("outbound", 0, 100, 100), ("outbound", 2, 400, 800), ("inbound", 10, 0, 1_500), ("outbound", 0, 25, 25)]


def test_v3_a_call_that_crosses_the_limit_only_splits_its_minutes(api, two_workspaces, db):
    tok, ws = two_workspaces["tok_a"], uuid.UUID(two_workspaces["ws_a"])
    _agreement(api, tok, ws)
    w = W(db, ws)
    w.inbound(_t(4, 8), 295 * 60)                # 5 left
    w.outbound(_t(4, 9), 7 * 60 + 30, "answered")  # 8 min: 5 package + 3 × 2 = 6 kr., NO call price
    w.outbound(_t(4, 10), 0, "no_answer")        # starts after: 0,25
    w.inbound(_t(4, 11), 2 * 60)                 # 2 × 1,50 = 3
    # a demo call never counts
    w.db.add(Call(workspace_id=ws, provider="vapi", provider_call_id="demo_v3", started_at=_t(4, 7), duration_seconds=600))
    w.db.add(DemoCall(workspace_id=ws, source="web", phone="+4520304050", consent_version="demo-call-web-v2",
                      consent_text="ja", consented_at=_t(4, 7), provider_call_id="demo_v3", status="done"))
    db.commit()
    e = expected(w.events, DKK)
    assert e["total"] == 600 + 25 + 300 == 925
    s = _st(api, tok, ws, "2026-11")
    assert _usage(s) == 925 and s["package"]["over"] == 5
    assert next(x for x in s["lines"] if x["kind"] == "campaign_call_fees")["net_minor"] == 25


# --------------------------------------------------------------------------- V4 late report after the invoice


def test_v4_report_after_the_invoice_is_billed_once_on_the_next_invoice(api, two_workspaces, db):
    tok, ws = two_workspaces["tok_a"], uuid.UUID(two_workspaces["ws_a"])
    _agreement(api, tok, ws)
    w = W(db, ws)
    w.inbound(_t(2, 8), 300 * 60)                         # package full
    late = w.outbound(_t(30, 22, 58), None, None)          # 30/11 23:58 local, no report at invoice time → 0,25
    late_in = w.inbound(_t(30, 22, 59), None)              # inbound still running at invoice time → 0
    db.commit()
    nov = _st(api, tok, ws, "2026-11")
    assert _usage(nov) == 25
    _freeze(db, ws, "2026-11", nov)
    # the reports arrive on 1/12: answered, 150 s (3 min) / inbound 4 min
    late.connected_seconds, late.outcome_class = 150, "answered"
    late_in.duration_seconds = 4 * 60
    db.commit()
    w.events = [ev for ev in w.events if ev[0] < _t(30, 22, 58)] + [(_t(30, 22, 58), "outbound", 150, "answered"),
                                                                     (_t(30, 22, 59), "inbound", 240, None)]
    e = expected(w.events, DKK)
    assert e["total"] == 400 + 600 + 600 == 1_600       # 4 + 3×2 + 4×1,50
    dec = _st(api, tok, ws, "2026-12")
    late_lines = [x for x in dec["lines"] if x["kind"] == "late_usage_adjustment"]
    assert [(x["period"], x["net_minor"], x["minutes"]) for x in late_lines] == [("2026-11", 1_600 - 25, 7)]
    assert dec["totals"]["net_minor"] == 249_500 + 1_575
    _freeze(db, ws, "2026-12", dec)
    assert not [x for x in _st(api, tok, ws, "2027-01")["lines"] if x["kind"] == "late_usage_adjustment"]


# --------------------------------------------------------------------------- V5/V6 complaints


def _complaint_setup(w):
    w.inbound(_t(5, 8), 298 * 60)                 # 2 left
    x = w.outbound(_t(5, 9), 3 * 60, "answered")  # 2 package + 1 × 2 kr., starts inside → no fee
    y = w.outbound(_t(5, 10), 60, "answered")     # after package: 4 + 2 = 6 kr.
    return x, y


def test_v5_complaint_approved_in_an_open_month_puts_the_minutes_back(api, two_workspaces, db):
    tok, ws = two_workspaces["tok_a"], uuid.UUID(two_workspaces["ws_a"])
    _agreement(api, tok, ws)
    w = W(db, ws)
    x, _y = _complaint_setup(w)
    db.commit()
    assert expected(w.events, DKK)["total"] == 800 and _usage(_st(api, tok, ws, "2026-11")) == 800
    d = api.post(tok, f"/workspaces/{ws}/billing/disputes", {"kind": "outbound", "call_id": str(x.id), "reason": "Forkert nummer"})
    assert d.status_code == 201
    r = api.post(api.operator(), f"/operator/admin/disputes/{d.json()['id']}/decision", {"decision": "approve"}).json()
    assert (r["credit_mode"], r["credit_net_minor"]) == ("pool", 0)
    without_x = [ev for ev in w.events if ev[0] != _t(5, 9)]
    assert expected(without_x, DKK)["total"] == 0           # Y now fits in the 2 minutes left: no fee, no minutes
    s = _st(api, tok, ws, "2026-11")
    assert _usage(s) == 0 and s["package"] == {"included": 300, "used": 299, "remaining": 1, "over": 0}


def test_v6_complaint_approved_in_an_invoiced_month_is_credited_once(api, two_workspaces, db):
    tok, ws = two_workspaces["tok_a"], uuid.UUID(two_workspaces["ws_a"])
    _agreement(api, tok, ws)
    w = W(db, ws)
    x, y = _complaint_setup(w)
    db.commit()
    _freeze(db, ws, "2026-11", _st(api, tok, ws, "2026-11"))
    d = api.post(tok, f"/workspaces/{ws}/billing/disputes", {"kind": "outbound", "call_id": str(x.id), "reason": "Forkert nummer"}).json()
    r = api.post(api.operator(), f"/operator/admin/disputes/{d['id']}/decision", {"decision": "approve"}).json()
    assert (r["credit_mode"], r["credit_net_minor"]) == ("invoice", 800)
    dec = _st(api, tok, ws, "2026-12")
    assert [x["net_minor"] for x in dec["lines"] if x["kind"] == "dispute_credit"] == [-800]
    assert not [x for x in dec["lines"] if x["kind"] == "late_usage_adjustment"]
    _freeze(db, ws, "2026-12", dec)
    jan = _st(api, tok, ws, "2027-01")
    assert not [x for x in jan["lines"] if x["kind"] in ("dispute_credit", "late_usage_adjustment")]


# --------------------------------------------------------------------------- V7 other currencies


def _country(db, ws, country):
    p = db.get(BusinessProfile, ws)
    p.country = country
    db.commit()


def test_v7_sek_nok_eur_use_the_markets_prices(api, two_workspaces, db):
    for country, cur, p, monthly in (("SE", "SEK", SEK, 369_500), ("NO", "NOK", NOK, 399_500), ("DE", "EUR", EUR, 32_900)):
        tok = api.user(f"owner-{cur.lower()}@testmail.dk", intent="reception")
        ws = uuid.UUID(api.workspace(tok, f"Firma {cur}"))
        _country(db, ws, country)
        a = _agreement(api, tok, ws)
        assert a["currency"] == cur
        assert {k: v["net_minor"] for k, v in a["outbound_call"].items()} == p["call"], cur
        assert (a["outbound_extra_minute"]["net_minor"], a["inbound_extra_minute"]["net_minor"]) == (p["outbound"], p["inbound"])
        w = W(db, ws)
        _mixed(w)
        db.commit()
        e = expected(w.events, p)
        s = _st(api, tok, ws, "2026-11")
        assert s["currency"] == cur and _usage(s) == e["total"], (cur, _usage(s), e)
        assert s["totals"]["net_minor"] == monthly + e["total"], cur


# --------------------------------------------------------------------------- V8 max cost


def test_v8_max_cost_is_honest(api, two_workspaces, db):
    tok, ws = two_workspaces["tok_a"], uuid.UUID(two_workspaces["ws_a"])
    _agreement(api, tok, ws)
    w = W(db, ws)
    for i in range(9):
        db.add(CampaignContact(campaign_id=w.camp.id, workspace_id=ws, phone=f"+45203040{i:02d}", kind="business"))
    db.add(CampaignContact(campaign_id=w.camp.id, workspace_id=ws, phone="+4529999999", kind="business", attempts=1,
                           connected_seconds=0))
    # contact used in W is pending with 0 attempts: 11 pending contacts, one has 1 attempt left
    w.inbound(_t(2, 8), 290 * 60)  # 10 minutes left in the package
    db.commit()
    c = service.max_cost(db, w.camp, now=_t(20, 9))
    attempts, minutes = 10 * 2 + 1, 11 * 3
    assert (c["attempts"], c["minutes"]) == (attempts, minutes)
    assert c["per_contact_net_minor"] == 1_400
    assert c["net_minor"] == attempts * 400 + minutes * 200 == 15_000
    assert c["package_remaining"] == 10
    assert c["with_package_net_minor"] == (minutes - 10) * 200 + attempts * 400 == 13_000


def test_v9_outcome_classes_follow_the_rules():
    oc = service.outcome_class
    assert oc("voicemail", False) == "voicemail"
    assert oc("customer-did-not-answer", False) == "no_answer"
    assert oc("customer-busy", False) == "no_answer"
    assert oc("twilio-failed-to-connect-call", False) == "no_answer"
    assert oc("customer-ended-call", True) == "answered"
    assert oc("silence-timed-out", False) == "no_answer"   # picked up but silent


def test_v10_statement_function_and_api_agree(api, two_workspaces, db):
    tok, ws = two_workspaces["tok_a"], uuid.UUID(two_workspaces["ws_a"])
    _agreement(api, tok, ws)
    w = W(db, ws)
    _mixed(w)
    db.commit()
    assert st_mod.statement(db, ws, date(2026, 11, 1), TZ)["totals"] == _st(api, tok, ws, "2026-11")["totals"]


# --------------------------------------------------------------------------- V11 the 14 kr. cap per contact holds


def test_v11_a_contacts_real_worst_case_after_the_package_stays_under_14_kr(api, two_workspaces, db):
    """Customer campaigns get 2 attempts and 180 s; an unanswered attempt has no minutes and an answered one ends the
    contact. Worst real sequence after the package: voicemail (1 kr.) then answered 180 s (4 kr. + 3 × 2 kr.) = 11 kr."""
    tok, ws = two_workspaces["tok_a"], uuid.UUID(two_workspaces["ws_a"])
    _agreement(api, tok, ws)
    assert (service.MAX_ATTEMPTS, service.MAX_CONNECTED_SECONDS) == (2, 180)
    w = W(db, ws)
    w.inbound(_t(6, 8), 300 * 60)                 # package used up
    w.outbound(_t(6, 9), 0, "voicemail")
    w.outbound(_t(6, 10), 180, "answered")
    db.commit()
    e = expected(w.events, DKK)
    assert e["total"] == 100 + 400 + 3 * 200 == 1_100
    s = _st(api, tok, ws, "2026-11")
    assert _usage(s) == 1_100 <= service.max_cost(db, w.camp, now=_t(20, 9))["per_contact_net_minor"] == 1_400

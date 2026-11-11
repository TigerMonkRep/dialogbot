"""F-PDEC-01 (Fürster's decision 2026-11-11): extra calls in Dialogbot Privat follow Erhverv's price by outcome + moms,
and the credits became the «Opkaldssaldo» – a prepaid balance in kroner, in øre. One test per rule."""
from __future__ import annotations

import json
import uuid

import pytest
from sqlalchemy import text

from app.models import CreditLedger, PrivateCall, PrivateTask
from app.modules.billing import markets, prices
from app.modules.campaigns import service as campaigns
from tests.test_privat import _approve, _ledger, _propose, _report, _stripe

HELLO = [{"role": "bot", "message": "Hej"}, {"role": "user", "message": "Ja, torsdag kl. 15.30 passer fint."}]


# --------------------------------------------------------------------------- 1. prices, derived and rounded once

def test_gross_rounds_half_up_to_whole_ore_in_one_place():
    assert prices.gross_minor(25) == 31          # 0,25 kr. × 1,25 = 0,3125 → 0,31 kr.
    assert prices.gross_minor(100) == 125 and prices.gross_minor(400) == 500 and prices.gross_minor(200) == 250
    assert prices.gross_minor(1400) == 1750      # the maximum: 14 kr. × 1,25
    assert prices.gross_minor(590) == 738        # 7,375 → 7,38 (half up, not to even)
    assert prices.gross_minor(3) == 4 and prices.gross_minor(2) == 3 and prices.gross_minor(-25) == -31


def test_extra_call_prices_are_erhvervs_net_prices_plus_moms():
    assert markets.privat_extra_call("DKK") == {"answered": 500, "voicemail": 125, "no_answer": 31, "minute": 250,
                                                "max": 1750}
    for cur in markets.CURRENCIES:  # every currency: the same factor (× 1,25) and rule on that market's net prices
        e, p = markets.ERHVERV[cur], markets.privat_extra_call(cur)
        assert p["answered"] == prices.gross_minor(e["call_answered"]) and p["minute"] == prices.gross_minor(e["outbound_extra_minute"])
        assert p["voicemail"] == prices.gross_minor(e["call_voicemail"])
        assert p["no_answer"] == prices.gross_minor(e["call_no_answer"])
        assert p["max"] == prices.gross_minor(2 * e["call_answered"] + 3 * e["outbound_extra_minute"])
    assert markets.privat_extra_call("SEK")["answered"] == 738 and markets.privat_extra_call("EUR")["no_answer"] == 4


def test_extra_call_prices_follow_erhverv_not_a_copy(monkeypatch):
    """Not hard-coded: a new Erhverv net price changes the Privat price."""
    monkeypatch.setitem(markets.ERHVERV["DKK"], "call_answered", 480)
    assert markets.privat_extra_call("DKK")["answered"] == 600 and markets.privat_extra_call("DKK")["max"] == 1950


def test_price_by_outcome_minutes_and_maximum():
    price = markets.privat_extra_call_price
    assert price("DKK", "answered", 0) == 500 and price("DKK", "answered", 1) == 750
    assert price("DKK", "answered", 3) == 1250
    assert price("DKK", "answered", 9) == 1750               # never more than 17,50 kr.
    assert price("DKK", "voicemail", 3) == 125 and price("DKK", "no_answer", 3) == 31  # no minutes without an answer
    with pytest.raises(ValueError):
        price("DKK", "failed", 0)
    assert markets.privat_extra_call_text() == ("5 kr. besvaret, 1,25 kr. telefonsvarer, 0,31 kr. "
                                                "ubesvaret + 2,50 kr. pr. påbegyndt minut, højst 17,50 kr.")


# --------------------------------------------------------------------------- 2. when the price applies

def test_a_call_inside_the_quota_costs_nothing_extra(api, client, pv, db, monkeypatch):
    called = []
    monkeypatch.setattr(campaigns, "create_call", lambda p: called.append(p) or {"id": "call_q"})
    tok = pv.account("mette@testmail.dk")
    pv.verify_phone(tok)
    pv.set_plan(tok, "basis")
    tid = _propose(pv, tok)
    t = api.post(tok, f"/privat/calls/{tid}/approve", {"share_phone": False}).json()
    assert t["usage_text"] == "Opkald 1 af 3 i Basis"
    assert _report(client, called[0], "customer-ended-call", HELLO, seconds=200, call_id="call_q")["outcome"] == "applied"
    me = pv.me(tok)
    assert (me["balance_minor"], me["held_minor"], me["calls_used"]) == (1000, 0, 1)
    assert [r[0] for r in _ledger(db, pv.ws(tok))] == ["grant"]  # nothing moved on the Opkaldssaldo


def test_an_unanswered_extra_call_costs_the_unanswered_price_and_does_not_count(api, client, pv, db, monkeypatch):
    tok = pv.account("mette@testmail.dk")
    _tid, p = _approve(api, pv, tok, monkeypatch)
    assert _report(client, p, "customer-busy", [], seconds=0)["outcome"] == "applied"
    assert pv.me(tok)["balance_minor"] == 2000 - 31


def test_a_voicemail_extra_call_costs_the_voicemail_price(api, client, pv, db, monkeypatch):
    tok = pv.account("mette@testmail.dk")
    tid, p = _approve(api, pv, tok, monkeypatch)
    assert _report(client, p, "voicemail", [{"role": "bot", "message": "Hej"}], seconds=25)["outcome"] == "applied"
    t = pv.task(tok, tid).json()
    assert t["call"]["result"] == "no_answer" and t["usage_text"] == "Ekstra opkald · telefonsvarer · 1,25 kr."
    assert t["events"][-1]["text"].startswith("Telefonsvareren tog den – 1,25 kr. er trukket")
    assert pv.me(tok)["balance_minor"] == 2000 - 125 and pv.me(tok)["held_minor"] == 0


def test_an_answered_extra_call_is_capped_at_the_maximum(api, client, pv, db, monkeypatch):
    tok = pv.account("mette@testmail.dk")
    _tid, p = _approve(api, pv, tok, monkeypatch)
    assert _report(client, p, "customer-ended-call", HELLO, seconds=600)["outcome"] == "applied"  # 10 minutes
    assert pv.me(tok)["balance_minor"] == 2000 - 1750


def test_without_a_plan_ring_for_mig_stays_blocked(api, pv, db, monkeypatch):
    monkeypatch.setattr(campaigns, "create_call", lambda p: {"id": "x"})
    tok = pv.account("mette@testmail.dk")
    pv.verify_phone(tok)
    tid = _propose(pv, tok)
    pv.expire_trial(tok)
    pv.top_up(tok, 20000)
    r = api.post(tok, f"/privat/calls/{tid}/approve", {"share_phone": False})
    assert r.status_code == 409 and r.json()["code"] == "needs_plan"
    assert pv.me(tok)["held_minor"] == 0


# --------------------------------------------------------------------------- 3. reservation and settlement

def test_vapi_error_releases_everything(api, client, pv, db, monkeypatch):
    tok = pv.account("mette@testmail.dk")
    tid, p = _approve(api, pv, tok, monkeypatch)
    out = _report(client, p, "pipeline-error-openai-llm-failed", [{"role": "bot", "message": "Hej"}], seconds=3)
    assert out["outcome"] == "applied"
    t = pv.task(tok, tid).json()
    assert t["call"]["result"] == "failed" and t["usage_text"] == "Intet forbrug"
    c = db.query(PrivateCall).one()
    assert sorted(r for r in _ledger(db, pv.ws(tok)) if r[2].startswith(f"call:{c.id}")) == [
        ("release", 1750, f"call:{c.id}:release"), ("reserve", -1750, f"call:{c.id}:reserve")]
    assert pv.me(tok)["balance_minor"] == 2000


def test_settlement_is_idempotent_per_call(api, client, pv, db, monkeypatch):
    from app.modules.privat import calls, ledger

    tok = pv.account("mette@testmail.dk")
    _tid, p = _approve(api, pv, tok, monkeypatch)
    assert _report(client, p, "customer-ended-call", HELLO, seconds=61)["outcome"] == "applied"
    assert _report(client, p, "customer-did-not-answer", [], seconds=0)["duplicate"] is True
    c = db.query(PrivateCall).one()
    assert ledger.settle(db, c.workspace_id, f"call:{c.id}", None, text="again") is None  # settled: no release after
    task = db.get(PrivateTask, c.task_id)
    assert calls.settle_extra(db, c, task, "answered", minutes=1, text="again") is None
    db.commit()
    assert pv.me(tok)["balance_minor"] == 2000 - 1000  # 5 kr. + 2 started minutes × 2,50 kr. – once


def test_a_cancelled_scheduled_extra_call_releases_everything(api, pv, db, monkeypatch):
    from datetime import UTC, datetime

    monkeypatch.setattr(campaigns, "create_call", lambda p: {"id": "x"})
    tok = pv.account("mette@testmail.dk")
    pv.verify_phone(tok)
    pv.use_up_calls(tok)
    pv.top_up(tok, 1000)
    pv.clock.at = datetime(2026, 11, 4, 17, 30, tzinfo=UTC)
    tid = _propose(pv, tok)
    api.post(tok, f"/privat/calls/{tid}/approve", {"share_phone": False, "at_next_open": True})
    assert pv.me(tok)["held_minor"] == 1750
    assert api.post(tok, f"/privat/calls/{tid}/decline").json()["status"] == "declined"
    assert (pv.me(tok)["balance_minor"], pv.me(tok)["held_minor"]) == (2000, 0)


def test_the_card_shows_the_extra_call_prices_before_approval(api, pv, monkeypatch):
    tok = pv.account("mette@testmail.dk")
    pv.verify_phone(tok)
    pv.use_up_calls(tok)
    tid = _propose(pv, tok)
    t = pv.task(tok, tid).json()
    assert t["usage_text"] == "Ekstra opkald: højst 17,50 kr., når du godkender"
    me = pv.me(tok)
    assert me["extra_call"] == markets.privat_extra_call("DKK") and me["currency"] == "DKK"


# --------------------------------------------------------------------------- 4. the balance in kroner

def test_no_number_of_credits_anywhere_in_the_api(api, pv):
    tok = pv.account("mette@testmail.dk")
    out = json.dumps([api.get(tok, "/privat/bootstrap").json(), api.get(tok, "/privat/addons").json(),
                      api.get(tok, "/privat/referrals").json(), api.get(tok, "/privat/ledger").json()],
                     ensure_ascii=False).lower()
    assert "credit" not in out and "kredit" not in out


def test_openapi_has_no_credits():
    from app.main import create_app

    spec = json.dumps(create_app().openapi(), ensure_ascii=False).lower()
    assert "/privat/credits" not in spec and "/privat/balance/checkout" in spec
    assert "creditscheckoutin" not in spec


def test_extra_task_costs_3_kr_and_sponsor_stays(api, pv, db):
    tok = pv.account("mette@testmail.dk")
    pv.expire_trial(tok)
    d1, d2 = (next(m for m in pv.say(tok, f"Lav en liste med x{i}")["messages"] if m["kind"] == "draft")["task_id"]
              for i in range(2))
    assert api.post(tok, f"/privat/tasks/{d1}/activate", {"method": "balance"}).json()["status"] != "draft"
    assert api.post(tok, f"/privat/tasks/{d2}/activate", {"method": "sponsor"}).json()["status"] != "draft"
    assert pv.me(tok)["balance_minor"] == 700
    db.add(CreditLedger(workspace_id=pv.ws(tok), kind="spend", amount=-600, source_ref="test:drain", text="t"))
    db.commit()
    d3 = next(m for m in pv.say(tok, "Lav en liste med y")["messages"] if m["kind"] == "draft")["task_id"]
    r = api.post(tok, f"/privat/tasks/{d3}/activate", {"method": "balance"})
    assert r.status_code == 409 and r.json()["code"] == "insufficient_balance" and r.json()["cta"]["label"] == "Fyld op"


def test_welcome_bonus_is_10_kr(api, pv, db):
    tok = pv.account("mette@testmail.dk")
    ws = pv.ws(tok)
    assert _ledger(db, ws) == [("grant", 1000, f"welcome:{ws}")]


def test_topup_amounts_and_webhook_checks_what_was_paid(api, client, pv, db, monkeypatch):
    from app.config import get_settings
    from app.modules.billing import stripe

    tok = pv.account("mette@testmail.dk")
    ws = pv.ws(tok)
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_x")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_privat")
    get_settings.cache_clear()
    sent = []
    monkeypatch.setattr(stripe, "request", lambda m, p, d=None, **k: sent.append((p, d)) or
                        {"id": "cs_x", "url": "https://checkout.stripe.com/c/pay/cs_x"})
    for amount in (5000, 10000, 20000):
        assert api.post(tok, "/privat/balance/checkout", {"amount_minor": amount}).status_code == 200
        d = [d for p, d in sent if p == "/checkout/sessions"][-1]
        assert d["mode"] == "payment" and d["line_items"][0]["price_data"]["unit_amount"] == amount
    meta = {"workspace_id": str(ws), "kind": "privat_topup", "amount_minor": "20000", "currency": "DKK"}
    paid = {"id": "cs_200", "object": "checkout.session", "mode": "payment", "payment_status": "paid",
            "amount_total": 19999, "metadata": meta}
    ev = {"id": "evt_200a", "type": "checkout.session.completed", "data": {"object": paid}}
    assert _stripe(client, ev)["outcome"] == "ignored"  # 1 øre short
    paid["amount_total"] = 20000
    assert _stripe(client, ev | {"id": "evt_200b"})["outcome"] == "applied"
    assert pv.me(tok)["balance_minor"] == 21000


def test_referral_bonus_is_10_kr_each_only_after_a_paid_period(api, pv, db):
    from tests.test_privat_sharing import _accept, _referral_ledger, _share

    mette = pv.account("mette@testmail.dk")
    inv = _share(api, mette, pv.make_list(mette))
    nina = pv.user("nina@testmail.dk", "Nina Ny")
    _accept(api, nina, inv["token"])
    pv.start_trial(nina)
    pv.make_list(nina, "Lav en liste med æg")
    assert _referral_ledger(db, pv.ws(nina)) == []  # the trial is not a paid period
    pv.set_plan(nina, "plus")
    pv.make_list(nina, "Lav en liste med mel")
    nid = pv.uid(nina)
    assert _referral_ledger(db, pv.ws(nina)) == [(1000, f"referral:{nid}:invitee")]
    assert _referral_ledger(db, pv.ws(mette)) == [(1000, f"referral:{nid}:inviter")]


def test_a_foreign_currency_moves_the_welcome_bonus_once(api, pv, db):
    from app.modules.privat import ledger

    tok = pv.account("mette@testmail.dk", trial=False)
    ws = pv.ws(tok)
    ledger.adopt_currency(db, ws, "SEK")
    ledger.adopt_currency(db, ws, "SEK")  # once
    db.commit()
    rows = [(r.kind, r.amount, r.currency) for r in db.query(CreditLedger).filter_by(workspace_id=ws, kind="convert")]
    assert sorted(rows) == [("convert", -1000, "DKK"), ("convert", 1500, "SEK")]  # the round bonus (2026-11-11)


# --------------------------------------------------------------------------- 5. the migration (1 credit = 2,90 kr.)

def test_migration_converts_credits_to_ore_and_back(pv, db):
    import os

    from alembic.config import Config

    from alembic import command

    tok = pv.account("mette@testmail.dk")
    ws = pv.ws(tok)
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cfg = Config(os.path.join(root, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(root, "alembic"))
    db.close()
    command.downgrade(cfg, "d7f2b9c4e1a8")
    try:
        with db.bind.begin() as conn:
            assert conn.execute(text("select amount from credit_ledger where workspace_id = :w"), {"w": ws}).scalar() == 3
            conn.execute(text("insert into credit_ledger (id, workspace_id, kind, amount, source_ref, text, created_at) "
                              "values (:id, :w, 'reserve', -3, 'call:x:reserve', 'old', now())"),
                         {"id": uuid.uuid4(), "w": ws})
            conn.execute(text("insert into private_tasks (id, workspace_id, kind, title, status, next_step, who, "
                              "usage_text, paid_by) values (:id, :w, 'list', 't', 'planned', '', '', '', 'credit')"),
                         {"id": uuid.uuid4(), "w": ws})
    finally:
        command.upgrade(cfg, "head")
    with db.bind.connect() as conn:
        rows = sorted(conn.execute(text("select kind, amount, currency from credit_ledger where workspace_id = :w"),
                                   {"w": ws}).all())
        assert rows == [("grant", 870, "DKK"), ("reserve", -870, "DKK")]  # 3 credits = 8,70 kr.
        assert conn.execute(text("select paid_by from private_tasks where workspace_id = :w"), {"w": ws}).scalar() \
            == "balance"

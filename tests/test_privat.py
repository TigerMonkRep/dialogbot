"""Dialogbot Privat: accounts and isolation, the monthly quota, reminders, payments, calls, call-backs, phone."""
from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid
from datetime import UTC, datetime, timedelta

from app.config import get_settings
from app.models import CreditLedger, OutboxEvent, PrivateCall, PrivateTask, Workspace
from app.modules.campaigns import service as campaigns
from app.modules.integrations.connectors.fakes import WORLD
from app.worker import runner
from tests.privat_fixtures import POOL, SECRET

VAPI_H = {"authorization": f"Bearer {SECRET}"}


def _ledger(db, ws) -> list[tuple[str, int, str]]:
    db.expire_all()
    return [(r.kind, r.amount, r.source_ref) for r in db.query(CreditLedger).filter_by(workspace_id=ws)
            .order_by(CreditLedger.created_at, CreditLedger.source_ref)]


# --------------------------------------------------------------------------- accounts and isolation

def test_account_is_personal_idempotent_and_flagged(api, pv, db, monkeypatch):
    tok = pv.user("mette@testmail.dk")
    r1, r2 = api.post(tok, "/privat/account").json(), api.post(tok, "/privat/account").json()
    assert r1["created"] is True and r2 == {"workspace_id": r1["workspace_id"], "created": False}
    ws = db.get(Workspace, uuid.UUID(r1["workspace_id"]))
    assert ws.kind == "personal"
    from app.models import BusinessProfile, GoalSelection, LanguageSettings

    for model in (BusinessProfile, GoalSelection, LanguageSettings):  # no business seed rows
        assert db.query(model).filter_by(workspace_id=ws.id).count() == 0
    assert api.get(tok, "/workspaces").json() == []  # never listed as a business workspace
    assert api.get(tok, f"/workspaces/{ws.id}/business-profile").status_code == 404
    # a fresh account is the free tier: no rights until the 14-day trial starts at Stripe Checkout, with a card
    assert pv.me(tok) == {"free_used": 0, "free_limit": 0, "credits": 3, "reserved": 0, "sponsor_left_today": 2,
                          "phone_display": None, "phone_verified": False, "push_enabled": False,
                          "location_city": None, "assistant_name": "Peter", "assistant_pronoun": "han",
                          "plan": "none", "plan_status": "none", "trial_days_left": 0, "calls_quota": 0,
                          "calls_used": 0, "calls_left": 0, "entitled": False}
    pv.start_trial(tok)  # … as the webhook mirrors it after the checkout
    me = pv.me(tok)
    assert (me["plan"], me["plan_status"], me["trial_days_left"], me["calls_quota"], me["entitled"]) == ("plus", "trial", 14, 10, True)
    assert _ledger(db, ws.id) == [("grant", 3, f"welcome:{ws.id}")]
    # pilot allow-list and the feature flag
    monkeypatch.setenv("PRIVAT_ALLOWED_EMAILS", "someone@else.dk")
    get_settings.cache_clear()
    assert api.get(tok, "/privat/me").json()["code"] == "privat_not_enabled"
    monkeypatch.setenv("PRIVAT_ALLOWED_EMAILS", "")
    monkeypatch.setenv("PRIVAT_ENABLED", "false")
    get_settings.cache_clear()
    assert api.get(tok, "/privat/me").status_code == 403


def test_personal_workspaces_left_out_of_reports_admin_and_invoicing(api, pv, db, two_workspaces,
                                                                      monkeypatch):
    tok = pv.account("mette@testmail.dk")
    ws = pv.ws(tok)
    from app.modules.reports import service as reports

    seen = []
    monkeypatch.setattr(reports, "generate", lambda db, ws_id, day, now: seen.append(ws_id))
    reports.run_due(db, datetime.combine((datetime.now(UTC) + timedelta(days=2)).date(), datetime.min.time(), UTC)
                    + timedelta(hours=12))
    assert ws not in seen and uuid.UUID(two_workspaces["ws_a"]) in seen  # business workspaces still get theirs
    op = api.operator()
    ids = {c["id"] for c in api.get(op, "/operator/admin/customers").json()["items"]}
    assert str(ws) not in ids and two_workspaces["ws_a"] in ids
    assert api.get(op, f"/operator/admin/customers/{ws}").status_code == 404


def test_isolation(api, pv, two_workspaces):
    mette = pv.account("mette@testmail.dk")
    tid = pv.make_list(mette)
    biz = two_workspaces["tok_a"]  # a business owner without a private account
    assert api.get(biz, f"/privat/tasks/{tid}").status_code == 404
    other = pv.account("ole@testmail.dk", "Ole Berg")  # another private user
    for path in (f"/privat/tasks/{tid}", f"/privat/messages?task_id={tid}"):
        assert api.get(other, path).status_code == 404
    assert api.post(other, f"/privat/tasks/{tid}/items", {"text": "x"}).status_code == 404
    assert api.post(other, f"/privat/tasks/{tid}/activate", {"method": "credit"}).status_code == 404
    assert api.post(other, f"/privat/calls/{tid}/approve", {"share_phone": False}).status_code == 404
    assert api.get(other, "/privat/tasks").json() == []
    # and the other way round: the private user cannot use business endpoints on their personal workspace,
    # nor reach the business workspace
    ws = pv.ws(mette)
    assert api.get(mette, f"/workspaces/{ws}").status_code == 404
    assert api.get(mette, f"/workspaces/{two_workspaces['ws_a']}").status_code == 404
    # operator "se som kunde" never shows private data
    from app.core.security import new_token, token_digest
    from app.db import get_session_factory
    from app.models import Session as Sess

    raw = new_token()
    with get_session_factory()() as s:
        s.add(Sess(user_id=pv.uid(mette), token_hash=token_digest(raw), expires_at=datetime.now(UTC) + timedelta(hours=1),
                   impersonator_user_id=pv.uid(api.operator())))
        s.commit()
    assert api.get(raw, "/privat/me").json()["code"] == "view_as_not_allowed"


# --------------------------------------------------------------------------- quota

def test_free_task_11(api, pv, db):
    """Without a plan (trial over): no free tasks – a new task becomes a draft; editing what exists stays free."""
    tok = pv.account("mette@testmail.dk")
    lid = pv.make_list(tok)  # made during the trial
    pv.expire_trial(tok)
    assert pv.me(tok)["free_used"] == 0 and pv.me(tok)["free_limit"] == 0
    # editing, ticking and reading an existing task is free
    pv.say(tok, "Tilføj æbler", about=lid)
    t = pv.task(tok, lid).json()
    api.post(tok, f"/privat/tasks/{lid}/items/{t['items'][0]['id']}/toggle")
    assert pv.me(tok)["free_used"] == 0
    out = pv.say(tok, "Mind mig om at hente pakken i morgen kl 16")
    draft = next(m for m in out["messages"] if m["kind"] == "draft")
    t11 = pv.task(tok, draft["task_id"]).json()
    assert t11["status"] == "draft" and t11["usage_text"] == "Ikke betalt endnu"
    assert db.query(OutboxEvent).filter(OutboxEvent.event_type == "privat.reminder",
                                        OutboxEvent.dedupe_key.like(f"privat-reminder:{t11['id']}:%")).count() == 0
    t = api.post(tok, f"/privat/tasks/{t11['id']}/activate", {"method": "credit"}).json()
    assert t["status"] == "planned" and t["usage_text"] == "1 credit"
    assert api.post(tok, f"/privat/tasks/{t11['id']}/activate", {"method": "credit"}).json()["status"] == "planned"
    ws = pv.ws(tok)
    assert [r for r in _ledger(db, ws) if r[0] == "spend"] == [("spend", -1, f"spend:{t11['id']}")]
    assert pv.me(tok)["credits"] == 2
    # sponsor: at most 2 a day
    drafts = [next(m for m in pv.say(tok, f"Lav en liste med x{i}")["messages"] if m["kind"] == "draft")["task_id"]
              for i in range(3)]
    assert api.post(tok, "/privat/sponsor/claim", {"task_id": drafts[0]}).json()["usage_text"] == "Sponsorindslag (+1 opgave)"
    assert api.post(tok, f"/privat/tasks/{drafts[1]}/activate", {"method": "sponsor"}).status_code == 200
    r = api.post(tok, f"/privat/tasks/{drafts[2]}/activate", {"method": "sponsor"})
    assert r.status_code == 409 and r.json()["code"] == "sponsor_limit"
    assert pv.me(tok)["sponsor_left_today"] == 0
    # the trial (card at Stripe) activates every draft that waited for it
    pv.clock.at = datetime(2026, 12, 1, 9, 0, tzinfo=UTC)
    pv.start_trial(tok)
    assert pv.task(tok, drafts[2]).json()["status"] == "in_progress"  # a list's own status
    assert pv.task(tok, drafts[2]).json()["usage_text"] == "Med i prøveperioden"


# --------------------------------------------------------------------------- reminders

def test_reminder_move(api, pv, db):
    tok = pv.account("mette@testmail.dk")
    out = pv.say(tok, "Mind mig om at hente pakken i morgen kl 16")
    assert out["messages"][1]["text"] == "Jeg minder dig om det i morgen kl. 16.00."
    tid = out["messages"][2]["task_id"]

    def active():
        db.expire_all()
        return db.query(OutboxEvent).filter(OutboxEvent.event_type == "privat.reminder", OutboxEvent.status == "queued",
                                            OutboxEvent.dedupe_key.like(f"privat-reminder:{tid}:%")).all()

    first = active()
    assert len(first) == 1 and first[0].next_attempt_at == datetime(2026, 11, 5, 15, 0, tzinfo=UTC)
    out = pv.say(tok, "Flyt den til kl 17", about=tid)
    move = out["messages"][-1]
    assert move["kind"] == "move" and (move["before"], move["after"]) == ("I morgen kl. 16.00", "I morgen kl. 17.00")
    pv.say(tok, "Flyt den til kl 18", about=tid)
    evs = active()
    assert len(evs) == 1 and evs[0].next_attempt_at == datetime(2026, 11, 5, 17, 0, tzinfo=UTC)
    assert len(api.get(tok, "/privat/tasks").json()) == 1  # moving is free: still one task
    # deliver: e-mail, task done; a cancelled event never sends
    db.query(OutboxEvent).filter(OutboxEvent.id == evs[0].id).update({"next_attempt_at": datetime.now(UTC)})
    db.commit()
    runner.drain()
    t = pv.task(tok, tid).json()
    assert t["status"] == "done" and t["events"][-1]["text"] == "Påmindelse sendt"
    from app.models import EmailDelivery

    assert db.query(EmailDelivery).filter(EmailDelivery.subject.like("Påmindelse:%")).count() == 1


# --------------------------------------------------------------------------- payments

def _stripe(client, event: dict, secret="whsec_privat") -> dict:
    body = json.dumps(event).encode()
    ts = int(time.time())
    sig = hmac.new(secret.encode(), f"{ts}.".encode() + body, hashlib.sha256).hexdigest()
    return client.post("/api/v1/webhooks/stripe", content=body, headers={"stripe-signature": f"t={ts},v1={sig}"}).json()


def test_payment_signal_twice(api, client, pv, db, monkeypatch):
    tok = pv.account("mette@testmail.dk")
    ws = pv.ws(tok)
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_x")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_privat")
    get_settings.cache_clear()
    sent = []
    from app.modules.billing import stripe

    monkeypatch.setattr(stripe, "request", lambda m, p, d=None, **k: sent.append((p, d)) or
                        {"id": "cs_test_1", "url": "https://checkout.stripe.com/c/pay/cs_test_1"})
    assert api.post(tok, "/privat/credits/checkout").json() == {"url": "https://checkout.stripe.com/c/pay/cs_test_1"}
    data = next(d for p, d in sent if p == "/checkout/sessions")  # (the VAT tax rate is looked up first)
    assert data["mode"] == "payment" and data["metadata"]["workspace_id"] == str(ws)
    assert data["line_items"][0]["price_data"]["unit_amount"] == 2900
    session = {"id": "cs_test_1", "object": "checkout.session", "mode": "payment", "payment_status": "paid",
               "amount_total": 2900, "metadata": {"workspace_id": str(ws), "kind": "privat_credits", "credits": "10"}}
    ev = {"id": "evt_privat_1", "type": "checkout.session.completed", "data": {"object": session}}
    assert _stripe(client, ev)["outcome"] == "applied"
    assert _stripe(client, ev)["duplicate"] is True  # the same event again
    ev2 = {"id": "evt_privat_2", "type": "checkout.session.async_payment_succeeded", "data": {"object": session}}
    assert _stripe(client, ev2)["outcome"] == "ignored"  # another event, same session
    assert [r for r in _ledger(db, ws) if r[0] == "purchase"] == [("purchase", 10, "stripe:cs_test_1")]
    assert pv.me(tok)["credits"] == 13
    from app.models import WebhookEvent

    assert db.query(WebhookEvent).filter_by(provider="stripe").count() == 2


# --------------------------------------------------------------------------- calls

def _propose(pv, tok) -> str:
    out = pv.say(tok, "Ring til cykelværkstedet og find en tid torsdag efter klokken tre")
    clar = out["messages"][-1]
    assert clar["kind"] == "clarify" and [o["label"] for o in clar["options"]] == ["Cykelmageren", "Østbyens Cykler",
                                                                                     "En anden"]
    assert clar["options"][0]["id"] == "place:cykelmageren"
    r = pv.api.post(tok, f"/privat/messages/{clar['id']}/options/{clar['options'][0]['id']}")
    prop = r.json()["messages"][-1]
    assert prop["kind"] == "call_proposal"
    return prop["task_id"]


def test_no_call_without_approval(api, pv, db, monkeypatch):
    called = []
    monkeypatch.setattr(campaigns, "create_call", lambda p: called.append(p) or {"id": "x"})
    tok = pv.account("mette@testmail.dk")
    pv.verify_phone(tok)
    tid = _propose(pv, tok)
    t = pv.task(tok, tid).json()
    assert t["status"] == "awaiting_user" and t["call"]["business_name"] == "Cykelmageren"
    assert t["call"]["window"] == "torsdag efter kl. 15" and t["call"]["phone_display"] == "86 12 34 56"
    assert called == [] and pv.me(tok)["reserved"] == 0
    # a number the user never wrote is never used
    from app.models import User
    from app.modules.privat import chat, deps

    principal = type("P", (), {"user": db.get(User, pv.uid(tok))})()
    ctx = deps._ctx(db, principal, deps.find_profile(db, pv.uid(tok)))
    turn = chat.Turn(db=db, ctx=ctx, text="Ring til Frisør Hansen og bestil en tid", about=None)
    chat.tool_propose_call(turn, {"business_name": "Frisør Hansen", "phone": "33445566", "purpose": "Bestil tid"})
    db.commit()
    assert turn.out[-1].kind == "text" and "nummer" in turn.out[-1].text
    assert db.query(PrivateCall).count() == 1
    # declining never calls
    assert api.post(tok, f"/privat/calls/{tid}/decline").json()["status"] == "declined"
    assert called == []


def test_needs_phone_insufficient_credits_outside_hours(api, pv, db, monkeypatch):
    called = []
    monkeypatch.setattr(campaigns, "create_call", lambda p: called.append(p) or {"id": "x"})
    tok = pv.account("mette@testmail.dk")
    pv.expire_trial(tok)  # credits path (plan calls: tests/test_privat_subscription.py)
    tid = _propose(pv, tok)
    path = f"/privat/calls/{tid}/approve"
    assert api.post(tok, path, {"share_phone": False}).json()["code"] == "needs_phone"
    pv.verify_phone(tok)
    pv.clock.at = datetime(2026, 11, 4, 17, 30, tzinfo=UTC)  # 18:30 in Copenhagen
    r = api.post(tok, path, {"share_phone": False})
    assert r.status_code == 409 and r.json()["code"] == "outside_hours"
    pv.clock.at = datetime(2026, 11, 7, 9, 0, tzinfo=UTC)  # Saturday
    assert api.post(tok, path, {"share_phone": False}).json()["code"] == "outside_hours"
    pv.clock.at = datetime(2026, 11, 4, 9, 0, tzinfo=UTC)
    ws = pv.ws(tok)
    db.add(CreditLedger(workspace_id=ws, kind="spend", amount=-1, source_ref="test:spend", text="test"))
    db.commit()
    r = api.post(tok, path, {"share_phone": False})
    assert r.status_code == 409 and r.json()["code"] == "insufficient_credits"
    assert r.json()["calls_left"] == 0 and r.json()["needs_plan"] is True
    assert called == [] and pv.me(tok)["reserved"] == 0


def _approve(api, pv, tok, monkeypatch, vapi_id="call_v1", name="Mette Hansen"):
    """Approve on the credits path (trial over, no plan): 3 credits reserved."""
    called = []
    monkeypatch.setattr(campaigns, "create_call", lambda p: called.append(p) or {"id": vapi_id})
    pv.expire_trial(tok)
    pv.verify_phone(tok)
    tid = _propose(pv, tok)
    t = api.post(tok, f"/privat/calls/{tid}/approve", {"window": "torsdag efter kl. 15", "share_phone": False},
                 **{"Idempotency-Key": "k1"}).json()
    assert t["status"] == "in_progress" and t["usage_text"] == "3 credits reserveret"
    again = api.post(tok, f"/privat/calls/{tid}/approve", {"window": "torsdag efter kl. 15", "share_phone": False},
                     **{"Idempotency-Key": "k1"}).json()
    assert again["id"] == tid and len(called) == 1
    p = called[0]
    assert p["phoneNumberId"] == "pn_pool" and p["customer"]["number"] == "+4586123456"
    a = p["assistant"]
    assert a["firstMessage"].startswith(f"Hej, jeg ringer fra Dialogbot på vegne af {name}")
    assert a["maxDurationSeconds"] == 180 and a["voicemailDetection"] == {"provider": "vapi"}
    assert a["metadata"]["private_call_id"] and a["metadata"]["private_task_id"] == tid
    assert "Du må IKKE" in a["model"]["messages"][0]["content"]
    assert pv.me(tok)["credits"] == 0 and pv.me(tok)["reserved"] == 3
    return tid, p


def _report(client, payload, reason, messages, seconds=60, call_id="call_v1"):
    return client.post("/api/v1/webhooks/vapi", headers=VAPI_H, json={"message": {
        "type": "end-of-call-report", "endedReason": reason, "durationSeconds": seconds,
        "call": {"id": call_id, "phoneNumberId": "pn_pool", "type": "outboundPhoneCall",
                 "customer": {"number": "+4586123456"}, "metadata": payload["metadata"]},
        "analysis": {"summary": "Værkstedet kan tage cyklen torsdag kl. 15.30."},
        "artifact": {"messages": messages}}}).json()


def test_unanswered_call(api, client, pv, db, monkeypatch):
    tok = pv.account("mette@testmail.dk")
    tid, p = _approve(api, pv, tok, monkeypatch)
    out = _report(client, p, "customer-did-not-answer", [{"role": "bot", "message": "Hej"}], seconds=0)
    assert out["outcome"] == "applied"
    t = pv.task(tok, tid).json()
    assert t["status"] == "awaiting_user" and t["call"]["result"] == "no_answer"
    assert t["events"][-1]["text"] == "Ingen tog telefonen – dine 3 credits er frigivet"
    assert pv.me(tok)["credits"] == 3 and pv.me(tok)["reserved"] == 0
    ws = pv.ws(tok)
    before = _ledger(db, ws)
    assert _report(client, p, "customer-did-not-answer", [], seconds=0)["duplicate"] is True
    assert _ledger(db, ws) == before
    c = db.query(PrivateCall).one()
    assert sorted(r for r in before if r[0] in ("reserve", "release")) == [
        ("release", 3, f"call:{c.id}:release"), ("reserve", -3, f"call:{c.id}:reserve")]
    from app.models import Call

    assert db.query(Call).count() == 0  # never stored as a business call
    # retry: a new proposal, back to awaiting_user
    t = api.post(tok, f"/privat/calls/{tid}/retry").json()
    assert t["status"] == "awaiting_user" and t["call"]["result"] is None and t["call"]["status"] == "proposed"


def test_answered_call(api, client, pv, db, monkeypatch):
    tok = pv.account("mette@testmail.dk")
    tid, p = _approve(api, pv, tok, monkeypatch)
    msgs = [{"role": "bot", "message": "Hej, jeg ringer fra Dialogbot"},
            {"role": "user", "message": "Ja, vi kan tage cyklen torsdag kl. 15.30. Et eftersyn koster 450 kr."}]
    assert _report(client, p, "customer-ended-call", msgs, seconds=130)["outcome"] == "applied"
    assert _report(client, p, "customer-ended-call", msgs, seconds=130)["duplicate"] is True
    t = pv.task(tok, tid).json()
    assert t["status"] == "done" and t["call"]["result"] == "answered"
    assert t["call"]["confirmed_text"] == "Torsdag kl. 15.30" and t["call"]["duration_seconds"] == 130
    assert t["usage_text"] == "3 credits · besvaret opkald, 2 min. 10 sek."
    ws = pv.ws(tok)
    c = db.query(PrivateCall).one()
    assert [r for r in _ledger(db, ws) if r[0] == "capture"] == [("capture", 0, f"call:{c.id}:capture")]
    assert pv.me(tok) | {} == pv.me(tok) and pv.me(tok)["credits"] == 0 and pv.me(tok)["reserved"] == 0
    msgs = api.get(tok, f"/privat/messages?task_id={tid}").json()
    assert msgs[-1]["text"] == "Opkaldet er slut. Cykelmageren har bekræftet torsdag kl. 15.30."


def _assistant_request(client, caller):
    return client.post("/api/v1/webhooks/vapi", headers=VAPI_H, json={"message": {
        "type": "assistant-request", "phoneNumber": {"id": "pn_pool", "number": POOL},
        "call": {"id": f"in_{uuid.uuid4().hex[:6]}", "phoneNumberId": "pn_pool", "customer": {"number": caller}}}}).json()


def test_callback_routing(api, client, pv, db, monkeypatch):
    mette = pv.account("mette@testmail.dk", "Mette Hansen")
    tid, p = _approve(api, pv, mette, monkeypatch)
    _report(client, p, "customer-did-not-answer", [], seconds=0)
    a = _assistant_request(client, "+4586123456")["assistant"]
    assert "på vegne af Mette Hansen" in a["firstMessage"]
    assert a["metadata"]["private_call_ids"] == [p["metadata"]["private_call_id"]]
    assert not any(t.get("type") == "transferCall" for t in a["model"]["tools"])  # share_phone was false
    # the callback report updates the right task and tells the user
    r = client.post("/api/v1/webhooks/vapi", headers=VAPI_H, json={"message": {
        "type": "end-of-call-report", "endedReason": "customer-ended-call",
        "call": {"id": "cb_1", "phoneNumberId": "pn_pool", "customer": {"number": "+4586123456"},
                 "assistant": {"metadata": a["metadata"]}},
        "artifact": {"messages": [{"role": "user", "message": "Det er fint, hun kan komme torsdag kl. 16."}]}}}).json()
    assert r["outcome"] == "applied"
    t = pv.task(tok := mette, tid).json()
    assert t["status"] == "done" and t["call"]["confirmed_text"] == "Torsdag kl. 16"
    assert t["events"][-1]["text"].startswith("Cykelmageren ringede tilbage")
    # two users called the same business: the assistant asks which person
    ole = pv.account("ole@testmail.dk", "Ole Berg")
    _approve(api, pv, ole, monkeypatch, vapi_id="call_v2", name="Ole Berg")
    a = _assistant_request(client, "+4586123456")["assistant"]
    assert "hvem drejer det sig om" in a["firstMessage"]
    content = a["model"]["messages"][0]["content"]
    assert "Mette" in content and "Ole" in content and "+45" not in content
    # unknown caller: generic, no personal data
    a = _assistant_request(client, "+4511223344")["assistant"]
    assert "kan desværre ikke se en henvendelse" in a["firstMessage"]
    blob = json.dumps(a, ensure_ascii=False)
    assert "Mette" not in blob and "Ole" not in blob and "Cykelmageren" not in blob
    assert tok


def test_phone_verify(api, pv, db):
    tok = pv.account("mette@testmail.dk")
    WORLD.reset()
    assert api.post(tok, "/privat/phone/start", {"phone": "20 30 40 50"}).json() == {"sent": True}
    sms = WORLD.sms[-1]
    assert sms["from"] == "Dialogbot" and sms["to"] == "+4520304050"
    code = sms["body"].split("er ")[1][:6]
    from app.models import PrivateProfile

    assert code not in (db.query(PrivateProfile).one().phone_code_hash or "")
    bad = api.post(tok, "/privat/phone/verify", {"code": "000000" if code != "000000" else "111111"})
    assert bad.status_code == 422 and bad.json()["attempts_left"] == 4
    ok = api.post(tok, "/privat/phone/verify", {"code": code}).json()
    assert ok["phone_verified"] is True and ok["phone_display"] == "20 30 40 50"
    # five wrong attempts lock the code; an expired code is refused
    pv.clock.at += timedelta(minutes=1)
    api.post(tok, "/privat/phone/start", {"phone": "21222324"})
    for _ in range(5):
        api.post(tok, "/privat/phone/verify", {"code": "999999"})
    assert api.post(tok, "/privat/phone/verify", {"code": "999999"}).json()["code"] == "too_many_attempts"
    pv.clock.at += timedelta(minutes=1)
    api.post(tok, "/privat/phone/start", {"phone": "21222324"})
    code = WORLD.sms[-1]["body"].split("er ")[1][:6]
    pv.clock.at += timedelta(minutes=11)
    assert api.post(tok, "/privat/phone/verify", {"code": code}).json()["code"] == "code_expired"


def test_chat_basics_waiting_and_clarify(api, pv):
    tok = pv.account("mette@testmail.dk")
    lid = pv.make_list(tok)
    t = pv.task(tok, lid).json()
    assert [i["text"] for i in t["items"]] == ["Mælk", "Rugbrød"] and t["list_type"] == "shopping"
    out = pv.say(tok, "Tilføj æbler og kaffe")
    assert out["messages"][1]["text"].startswith("Tilføjet æbler og kaffe.")
    out = pv.say(tok, "Hvad venter på mig?")
    assert out["messages"][-1]["kind"] == "waiting" and out["messages"][-1]["text"] == "Intet venter på dit svar lige nu."
    out = pv.say(tok, "Hmm")
    clar = out["messages"][-1]
    assert clar["kind"] == "clarify" and len(clar["options"]) == 3 and "action" not in clar["options"][0]
    day = api.get(tok, "/privat/day").json()
    assert [x["id"] for x in day["today"]] == [lid]
    # idempotent chat: the same key replays, nothing is created twice
    a = pv.say(tok, "Lav en liste med kage", key="same")
    b = pv.say(tok, "Lav en liste med kage", key="same")
    assert a == b and len(api.get(tok, "/privat/tasks").json()) == 2
    led = api.get(tok, "/privat/ledger").json()
    assert led[0]["kind"] == "grant" and led[0]["amount"] == 3


def test_stale_call_released(api, pv, db, monkeypatch):
    tok = pv.account("mette@testmail.dk")
    tid, _p = _approve(api, pv, tok, monkeypatch)
    from app.modules.privat import calls

    pv.clock.at += timedelta(minutes=31)
    assert calls.sweep_stale(db) == 1
    assert pv.me(tok)["credits"] == 3 and pv.task(tok, tid).json()["status"] == "awaiting_user"
    assert db.query(PrivateTask).count() == 1


def test_failed_tool_is_explained(api, pv):
    tok = pv.account("mette@testmail.dk")
    out = pv.say(tok, "Tilføj æbler")  # there is no list yet
    assert out["messages"][-1]["text"] == "Jeg fandt ingen åben liste"

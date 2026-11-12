"""Sending and the way back: unsubscribes, provider events, the dry run, and what live mode refuses."""
from __future__ import annotations

import json
import time

import pytest
from sqlalchemy import select

from app.config import Settings
from app.models import OutreachLead, OutreachLog, OutreachMessage, OutreachSuppression
from app.modules.outreach.agents import dispatcher
from app.modules.outreach.agents.dispatcher import DispatcherAndWebhookHandler, DryRunProvider, unsubscribe_token
from app.modules.outreach.compliance import Action, ComplianceEngine, LeadFacts
from app.modules.webhooks import resend
from tests.outreach_fixtures import env, raw, run

EMAIL = "office@brightwater.example"
LIVE = dict(OUTREACH_MODE="live", OUTREACH_SENDER_INBOXES="sam@send.example", AI_PROVIDER="anthropic",
            OUTREACH_POSTAL_ADDRESS="Testvej 1, 8000 Aarhus C, Denmark", ANTHROPIC_API_KEY="sk-ant-test",
            OUTREACH_RESEND_API_KEY="re_test")


def queued(db) -> OutreachMessage:
    return db.scalars(select(OutreachMessage)).one()


def test_unsubscribe_link_suppresses_at_once_and_cancels_what_is_pending(db, outreach, client):
    run(db, [raw("US")])
    r = client.get("/api/v1/unsubscribe", params={"token": unsubscribe_token(EMAIL)})
    assert r.status_code == 200 and "unsubscribed" in r.text.lower()
    db.expire_all()
    assert db.scalars(select(OutreachSuppression)).one().value == EMAIL
    assert queued(db).status == "cancelled" and db.scalars(select(OutreachLead)).one().status == "unsubscribed"
    assert client.post("/api/v1/unsubscribe", params={"token": unsubscribe_token(EMAIL)}).status_code == 200   # idempotent
    assert client.get("/api/v1/unsubscribe", params={"token": unsubscribe_token(EMAIL) + "x"}).status_code == 422
    assert client.get("/api/v1/unsubscribe", params={"token": "garbage"}).status_code == 422


def test_an_unsubscribed_address_can_never_be_emailed_again(db, outreach, client):
    run(db, [raw("US")])
    msg = queued(db)
    assert client.post("/api/v1/unsubscribe", params={"token": unsubscribe_token(EMAIL)}).status_code == 200
    # 1) the engine refuses it, in any casing, so no agent will touch it
    d = ComplianceEngine(db).evaluate(LeadFacts(company_name="Brightwater LLC", email=EMAIL.upper(), country="US"))
    assert d.action is Action.BLOCK and "suppressed" in d.reasons[0]
    # 2) a new batch with the same address (another company name) writes nothing
    calls = len(outreach.calls)
    db.query(OutreachLead).delete()
    db.commit()
    rep = run(db, [raw("US", company="Brightwater Plumbing Inc")], batch="again")
    assert rep["leads"][0]["status"] == "blocked" and len(outreach.calls) == calls
    # 3) even an e-mail that somehow sits in the queue is cancelled at send time, not sent
    run(db, [raw("US", email="other@firm.example", company="Other LLC")], batch="b3")
    other = db.scalars(select(OutreachMessage).where(OutreachMessage.to_email == "other@firm.example")).one()
    other.to_email = EMAIL
    db.commit()
    out = DispatcherAndWebhookHandler(db).dispatch()
    assert out["sent"] == 0 and out["cancelled"] == 1 and msg.id != other.id


def test_a_suppressed_domain_blocks_every_address_on_it(db, outreach, api):
    op = api.operator()
    assert api.post(op, "/operator/outreach/suppressions", {"value": "Brightwater.example", "kind": "domain"}).status_code == 201
    rep = run(db, [raw("US"), raw("US", email="owner@brightwater.example", company="Brightwater 2 LLC")])
    assert [x["status"] for x in rep["leads"]] == ["blocked", "blocked"] and outreach.calls == []


def test_provider_events_reply_halts_bounce_and_complaint_suppress(db, outreach, client, monkeypatch):
    env(monkeypatch, OUTREACH_WEBHOOK_SECRET="s3cret-value")
    run(db, [raw("US"), raw("US", email="office@two.example", company="Two LLC")])
    post = lambda body, secret="s3cret-value": client.post(  # noqa: E731
        "/api/v1/webhooks/events", json=body, headers={"X-Outreach-Secret": secret})
    assert post({"event": "reply", "email": EMAIL}, secret="wrong").status_code == 401
    assert post({"event": "reply", "email": EMAIL}).json() == {"received": True, "result": "halted"}
    assert post({"event": "bounce", "email": "office@two.example"}).json()["result"] == "suppressed"
    db.expire_all()
    by = {m.to_email: m.status for m in db.scalars(select(OutreachMessage))}
    assert by == {EMAIL: "cancelled", "office@two.example": "cancelled"}
    leads = {x.email_normalized: x.status for x in db.scalars(select(OutreachLead))}
    assert leads == {EMAIL: "replied", "office@two.example": "bounced"}
    assert [s.value for s in db.scalars(select(OutreachSuppression))] == ["office@two.example"]   # a reply is not an opt-out
    assert DispatcherAndWebhookHandler(db).dispatch()["sent"] == 0


def test_resend_events_are_accepted_only_with_a_valid_svix_signature(db, outreach, client, monkeypatch):
    secret = "whsec_" + "dGVzdHNlY3JldHRlc3RzZWNyZXQ="
    env(monkeypatch, RESEND_WEBHOOK_SECRET=secret)
    run(db, [raw("US")])
    body = json.dumps({"type": "email.complained", "data": {"to": [EMAIL]}}).encode()
    ts = str(int(time.time()))
    h = {"svix-id": "msg_1", "svix-timestamp": ts, "content-type": "application/json"}
    bad = client.post("/api/v1/webhooks/events", content=body, headers={**h, "svix-signature": "v1,AAAA"})
    assert bad.status_code == 401 and db.scalars(select(OutreachSuppression)).all() == []
    ok = client.post("/api/v1/webhooks/events", content=body,
                     headers={**h, "svix-signature": resend.sign(secret, "msg_1", ts, body)})
    assert ok.json()["result"] == "suppressed"
    db.expire_all()
    assert db.scalars(select(OutreachSuppression)).one().reason == "complaint"


def test_webhook_without_a_configured_secret_is_refused(db, outreach, client):
    assert client.post("/api/v1/webhooks/events", json={"event": "bounce", "email": EMAIL}).status_code == 503


def test_dry_run_renders_the_final_email_and_sends_nothing(db, outreach, monkeypatch):
    env(monkeypatch, PUBLIC_BASE_URL="https://api.dialogbot.app")
    sentinel = DryRunProvider()
    dispatcher.set_provider_override(sentinel)        # must be ignored in dry_run
    run(db, [raw("US")])
    out = DispatcherAndWebhookHandler(db).dispatch()
    db.commit()
    assert out == {"mode": "dry_run", "provider": "dry_run", "sent": 1, "cancelled": 0, "waiting": 0, "failed": 0}
    assert sentinel.sent == [] and queued(db).status == "dry_run"
    rendered = db.scalars(select(OutreachLog).where(OutreachLog.kind == "dispatch")).one().detail
    url = f"https://api.dialogbot.app/api/v1/unsubscribe?token={unsubscribe_token(EMAIL)}"
    from app.modules.outreach.pipelines.batch import report

    assert report(db, "t1")["leads"][0]["email_draft"]["rendered"] == rendered["rendered"]
    assert url in rendered["rendered"] and "{{unsubscribe_link}}" not in rendered["rendered"]
    assert rendered["headers"] == {"List-Unsubscribe": f"<{url}>", "List-Unsubscribe-Post": "List-Unsubscribe=One-Click"}


def test_live_sends_only_where_the_callback_demo_can_ring(db, outreach, monkeypatch):
    run(db, [raw("US")])
    env(monkeypatch, **LIVE)
    box = DryRunProvider()
    box.name = "resend"
    dispatcher.set_provider_override(box)
    msg = queued(db)
    msg.sender_inbox = "sam@send.example"
    msg.footer = msg.footer.replace("Aarhus, Denmark", "Testvej 1, 8000 Aarhus C, Denmark")
    db.commit()
    assert DispatcherAndWebhookHandler(db).dispatch()["waiting"] == 1 and box.sent == []     # demo rings DK only
    env(monkeypatch, **LIVE, OUTREACH_DEMO_CALLBACK_COUNTRIES="DK,US")
    out = DispatcherAndWebhookHandler(db).dispatch()
    assert out["sent"] == 1 and box.sent[0].to_email == EMAIL and box.sent[0].from_email == "sam@send.example"
    assert "Testvej 1, 8000 Aarhus C" in box.sent[0].text and queued(db).status == "sent"
    assert DispatcherAndWebhookHandler(db).dispatch()["sent"] == 0                           # never twice


def test_live_mode_refuses_to_start_half_configured():
    base = dict(DATABASE_URL="postgresql+psycopg://x/y", _env_file=None)
    with pytest.raises(ValueError, match="OUTREACH_SENDER_INBOXES, OUTREACH_POSTAL_ADDRESS"):
        Settings(**base, OUTREACH_MODE="live", OUTREACH_RESEND_API_KEY="re_x", AI_PROVIDER="anthropic", ANTHROPIC_API_KEY="k")
    for provider in ("instantly", "smartlead"):
        with pytest.raises(ValueError, match="not implemented"):
            Settings(**base, **{k: v for k, v in LIVE.items()}, OUTREACH_PROVIDER=provider)
    assert Settings(**base).outreach_mode == "off"


def test_everything_is_off_by_default(db, api, monkeypatch):
    monkeypatch.delenv("OUTREACH_MODE", raising=False)
    op = api.operator()
    assert api.post(op, "/operator/outreach/batches", {"leads": [{"company_name": "X LLC", "email": "a@b.example", "country": "US"}]}).status_code == 501
    assert api.post(op, "/operator/outreach/dispatch", {}).status_code == 501
    assert db.scalars(select(OutreachLead)).all() == []


def test_operator_endpoints_run_a_batch_and_are_closed_to_customers(db, outreach, api, two_workspaces, monkeypatch):
    monkeypatch.setattr("app.modules.outreach.agents.sourcing.default_mx_check", lambda _d: True)
    body = {"name": "api-1", "csv": "company_name,email,country,niche,context\nBrightwater LLC,office@brightwater.example,US,plumbing,"
                                    "\"Review: I called three times and it went to voicemail every time.\"\n"
                                    "Müller GmbH,info@mueller.example,DE,plumber,\n"}
    assert api.post(two_workspaces["tok_a"], "/operator/outreach/batches", body).status_code == 403
    r = api.post(api.operator(), "/operator/outreach/batches", body)
    assert r.status_code == 201, r.text
    assert r.json()["totals"] == {"queued": 1, "blocked": 1}
    assert api.get(api.operator(), "/operator/outreach/batches/api-1").json()["leads"][0]["email_draft"]["audit"]["passed"]
    assert api.post(api.operator(), "/operator/outreach/dispatch", {}).json()["sent"] == 1

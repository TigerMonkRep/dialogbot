"""M03: the operator's operations screen – call and calendar-sync status, dependency incidents, controlled retry
(idempotent, audited, no duplicate calendar events or deliveries) and tenant suspension (operator only, isolated).

Everything runs with fake providers: the calendar and SMS are app.modules.integrations.connectors.fakes.WORLD,
mail is the simulated adapter, the dialler's create_call is replaced. Nothing leaves the process."""
from __future__ import annotations

from datetime import UTC, date, datetime, time

import pytest
from sqlalchemy import func, select

from app.config import get_settings
from app.core.outbox import enqueue
from app.models import AuditLog, Booking, EmailDelivery, OutboxEvent
from app.modules.integrations.connectors import fakes
from app.modules.integrations.connectors.base import ActionError
from app.modules.integrations.connectors.fakes import WORLD
from app.worker import runner
from tests.qa.test_qa_integ_E07 import _call, _ready

OPS = "/operator/admin/operations"


@pytest.fixture
def fake(monkeypatch):
    monkeypatch.setenv("CONNECTORS_PROVIDER", "fake")
    monkeypatch.delenv("TELEPHONY_PROVIDER", raising=False)
    get_settings.cache_clear()
    WORLD.reset()
    yield WORLD
    WORLD.reset()
    get_settings.cache_clear()


def _audits(db, action: str) -> int:
    return db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == action)) or 0


def _failed_job(db, ws: str, key: str, event_type: str = "qa.m03.fails") -> OutboxEvent:
    runner.FAIL_EVENT_TYPES.add(event_type)
    ev = enqueue(db, event_type=event_type, dedupe_key=key, workspace_id=ws, payload={"x": 1})
    db.commit()
    runner.drain()
    db.expire_all()
    ev = db.get(OutboxEvent, ev.id)
    ev.status = "failed"  # as after max attempts
    db.commit()
    return ev


# --------------------------------------------------------------------------- access

def test_only_operators_read_or_act(api, two_workspaces, db):
    t = two_workspaces
    ev = _failed_job(db, t["ws_a"], "m03-acl")
    for tok in (t["tok_a"], t["tok_b"]):
        assert api.get(tok, OPS).status_code == 403
        assert api.post(tok, f"{OPS}/jobs/{ev.id}/retry", {}).status_code == 403
        assert api.post(tok, f"{OPS}/workspaces/{t['ws_a']}/suspend", {"reason": "test af adgang"}).status_code == 403
        assert api.post(tok, f"{OPS}/workspaces/{t['ws_b']}/resume", {}).status_code == 403
        assert api.post(tok, f"{OPS}/bookings/{ev.id}/calendar-retry", {}).status_code == 403
    db.expire_all()
    assert db.get(OutboxEvent, ev.id).status == "failed" and _audits(db, "operator.ops.job_retry") == 0


# --------------------------------------------------------------------------- controlled job retry

def test_job_retry_gives_exactly_one_more_attempt_and_is_idempotent(api, two_workspaces, db):
    t = two_workspaces
    op = api.operator()
    ev = _failed_job(db, t["ws_a"], "m03-retry")
    attempts = ev.attempts
    job = next(j for j in api.get(op, OPS).json()["failed_jobs"] if j["id"] == str(ev.id))
    assert job["retryable"] is True and job["workspace_name"] == "Fjord Gulvservice ApS"

    r1 = api.post(op, f"{OPS}/jobs/{ev.id}/retry", {"note": "leverandør oppe igen"}, **{"Idempotency-Key": "k1"})
    assert r1.status_code == 200 and r1.json()["result"] == "queued", r1.text
    replay = api.post(op, f"{OPS}/jobs/{ev.id}/retry", {"note": "leverandør oppe igen"}, **{"Idempotency-Key": "k1"})
    assert replay.json() == r1.json()
    again = api.post(op, f"{OPS}/jobs/{ev.id}/retry", {})  # a second click without the key: already queued
    assert again.status_code == 200 and again.json()["result"] == "already_queued"
    assert _audits(db, "operator.ops.job_retry") == 1
    db.expire_all()
    ev = db.get(OutboxEvent, ev.id)
    assert ev.status == "queued" and ev.max_attempts == attempts + 1
    # still failing: one attempt, then «failed» again – no runaway retries
    runner.drain()
    db.expire_all()
    ev = db.get(OutboxEvent, ev.id)
    assert ev.status == "failed" and ev.attempts == attempts + 1
    # fixed: one more controlled retry succeeds; a done job is never re-run
    runner.FAIL_EVENT_TYPES.clear()
    runner.HANDLERS["qa.m03.fails"] = lambda db_, ev_: None
    try:
        assert api.post(op, f"{OPS}/jobs/{ev.id}/retry", {}).json()["result"] == "queued"
        runner.drain()
        db.expire_all()
        assert db.get(OutboxEvent, ev.id).status == "done"
        done = api.post(op, f"{OPS}/jobs/{ev.id}/retry", {})
        assert done.status_code == 409 and done.json()["code"] == "job_done"
    finally:
        runner.HANDLERS.pop("qa.m03.fails", None)
    audit = db.scalars(select(AuditLog).where(AuditLog.action == "operator.ops.job_retry")).all()
    assert len(audit) == 2 and all(a.actor_user_id is not None and a.object_type == "outbox_event" for a in audit)
    assert audit[0].before["status"] == "failed" and audit[0].after["note"] in ("leverandør oppe igen", "")


def test_retried_mail_is_delivered_once(api, two_workspaces, db):
    t = two_workspaces
    op = api.operator()
    ev = _failed_job(db, t["ws_a"], "m03-mail", event_type="email.branded")
    ev.payload = {"to_email": "kunde@testmail.dk", "subject": "Hej", "body": "Tekst"}
    db.commit()
    runner.FAIL_EVENT_TYPES.clear()
    for _ in range(3):  # three clicks: one queue, one delivery
        api.post(op, f"{OPS}/jobs/{ev.id}/retry", {})
    runner.drain()
    api.post(op, f"{OPS}/jobs/{ev.id}/retry", {})
    runner.drain()
    assert db.scalar(select(func.count()).select_from(EmailDelivery).where(EmailDelivery.outbox_event_id == ev.id)) == 1


# --------------------------------------------------------------------------- calendar sync retry (DB-007)

def _broken_calendar(monkeypatch, message: str, code: str, method: str = "create_event"):
    def broken(self, *a, **kw):
        raise ActionError(message, code=code, retryable=True)

    monkeypatch.setattr(fakes.FakeCalendarClient, method, broken)


def test_calendar_retry_after_timeout_needs_confirmation_and_never_duplicates(api, client, fake, db, monkeypatch):
    tok, ws = _ready(api, client, "m03-cal-timeout")
    op = api.operator()
    slots = _call(db, ws, "ledige_tider", {})["run"]["output"]["tider"]
    with monkeypatch.context() as m:
        _broken_calendar(m, "Kalenderen svarede ikke i tide", "provider_timeout")
        r = _call(db, ws, "book_tid", {"start": slots[0]["start"], "navn": "Mette Nielsen", "bekraeftet": True})
    assert r["run"]["status"] == "failed" and fake.events == {}
    b = db.scalar(select(Booking).where(Booking.workspace_id == ws))
    row = next(x for x in api.get(op, OPS).json()["calendar_sync"]["failed"] if x["id"] == str(b.id))
    assert row["outcome"] == "unknown" and row["workspace_name"] == "Fjord Gulvservice ApS"
    # unknown outcome: no blind second write
    blind = api.post(op, f"{OPS}/bookings/{b.id}/calendar-retry", {})
    assert blind.status_code == 409 and blind.json()["code"] == "calendar_outcome_unknown" and fake.events == {}
    assert _audits(db, "operator.ops.calendar_retry") == 0
    ok = api.post(op, f"{OPS}/bookings/{b.id}/calendar-retry", {"confirm_not_created": True, "note": "tjekket kalenderen"})
    assert ok.status_code == 200 and ok.json()["result"] == "synced", ok.text
    assert len(fake.events) == 1
    for _ in range(2):
        again = api.post(op, f"{OPS}/bookings/{b.id}/calendar-retry", {"confirm_not_created": True})
        assert again.json()["result"] == "already_synced"
    assert len(fake.events) == 1 and _audits(db, "operator.ops.calendar_retry") == 1
    assert not [x for x in api.get(op, OPS).json()["calendar_sync"]["failed"] if x["id"] == str(b.id)]


def test_calendar_retry_creates_when_not_created_and_updates_when_it_exists(api, client, fake, db, monkeypatch):
    tok, ws = _ready(api, client, "m03-cal-states")
    op = api.operator()
    slots = _call(db, ws, "ledige_tider", {})["run"]["output"]["tider"]
    with monkeypatch.context() as m:  # not created: the provider refused before writing
        _broken_calendar(m, "Kalenderen kunne ikke nås", "provider_unavailable")
        _call(db, ws, "book_tid", {"start": slots[0]["start"], "navn": "Jens Poulsen", "bekraeftet": True})
    b = db.scalar(select(Booking).where(Booking.workspace_id == ws))
    assert api.get(op, OPS).json()["calendar_sync"]["failed"][0]["outcome"] == "not_created"
    assert api.post(op, f"{OPS}/bookings/{b.id}/calendar-retry", {}).json()["result"] == "synced"
    assert len(fake.events) == 1
    event_id = next(iter(fake.events))
    db.expire_all()  # the retry ran in the API's session
    with monkeypatch.context() as m:  # exists: the move failed; the retry updates the same event
        _broken_calendar(m, "Kalenderen kunne ikke nås", "provider_unavailable", method="update_event")
        _call(db, ws, "flyt_tid", {"ny_start": slots[1]["start"], "bekraeftet": True})
    db.expire_all()
    b = db.get(Booking, b.id)
    assert b.calendar_sync == "failed"
    assert api.get(op, OPS).json()["calendar_sync"]["failed"][0]["outcome"] == "exists"
    still_failing = None
    with monkeypatch.context() as m:  # the provider is still down: honest «failed», nothing written
        _broken_calendar(m, "Kalenderen kunne ikke nås", "provider_unavailable", method="update_event")
        still_failing = api.post(op, f"{OPS}/bookings/{b.id}/calendar-retry", {}).json()
    assert still_failing["result"] == "failed"
    assert api.post(op, f"{OPS}/bookings/{b.id}/calendar-retry", {}).json()["result"] == "synced"
    assert list(fake.events) == [event_id]
    assert fake.events[event_id]["start"] == datetime.fromisoformat(slots[1]["start"]).astimezone(UTC)


# --------------------------------------------------------------------------- suspension and tenant isolation

def test_suspension_pauses_only_that_tenant_and_resume_continues(api, two_workspaces, db):
    t = two_workspaces
    op = api.operator()
    s = api.post(op, f"{OPS}/workspaces/{t['ws_a']}/suspend", {"reason": "Google-kalender giver 401 for kunden"})
    assert s.status_code == 200 and s.json()["suspended"] is True
    assert api.post(op, f"{OPS}/workspaces/{t['ws_a']}/suspend", {"reason": "igen"}).json()["reason"] == \
        "Google-kalender giver 401 for kunden"  # idempotent: the first reason stands
    assert _audits(db, "operator.ops.workspace_suspended") == 1
    ops = api.get(op, OPS).json()
    assert [x["workspace_id"] for x in ops["suspended"]] == [t["ws_a"]] and ops["suspended"][0]["by"] == "operator@testmail.dk"
    runner.HANDLERS["qa.m03.noop"] = lambda db_, ev_: None
    try:
        a = enqueue(db, event_type="qa.m03.noop", dedupe_key="m03-a", workspace_id=t["ws_a"], payload={})
        b = enqueue(db, event_type="qa.m03.noop", dedupe_key="m03-b", workspace_id=t["ws_b"], payload={})
        g = enqueue(db, event_type="qa.m03.noop", dedupe_key="m03-g", workspace_id=None, payload={})
        db.commit()
        runner.drain()
        db.expire_all()
        assert (db.get(OutboxEvent, a.id).status, db.get(OutboxEvent, b.id).status, db.get(OutboxEvent, g.id).status) == \
            ("queued", "done", "done")
        # a retry for the suspended tenant is refused
        f = _failed_job(db, t["ws_a"], "m03-susp-retry")
        r = api.post(op, f"{OPS}/jobs/{f.id}/retry", {})
        assert r.status_code == 409 and r.json()["code"] == "workspace_suspended"
        assert next(j for j in api.get(op, OPS).json()["failed_jobs"] if j["id"] == str(f.id))["retryable"] is False
        # the tenants cannot lift it, nor touch each other
        assert api.post(t["tok_a"], f"{OPS}/workspaces/{t['ws_a']}/resume", {}).status_code == 403
        assert api.post(t["tok_b"], f"{OPS}/workspaces/{t['ws_a']}/resume", {}).status_code == 403
        # resume: the waiting job runs, nothing was dropped or duplicated
        assert api.post(op, f"{OPS}/workspaces/{t['ws_a']}/resume", {"note": "løst"}).json()["suspended"] is False
        runner.drain()
        db.expire_all()
        assert db.get(OutboxEvent, a.id).status == "done"
        assert db.scalar(select(func.count()).select_from(OutboxEvent).where(OutboxEvent.dedupe_key == "m03-a")) == 1
    finally:
        runner.HANDLERS.pop("qa.m03.noop", None)
    assert _audits(db, "operator.ops.workspace_resumed") == 1
    assert api.get(op, OPS).json()["suspended"] == []


def test_suspended_tenant_actions_are_refused_others_unaffected(api, client, fake, db):
    tok_a, ws_a = _ready(api, client, "m03-act-a")
    tok_b, ws_b = _ready(api, client, "m03-act-b")
    op = api.operator()
    assert api.post(op, f"{OPS}/workspaces/{ws_a}/suspend", {"reason": "SMS-udbyder svarer med fejl"}).status_code == 200
    ra = _call(db, ws_a, "ledige_tider", {})
    assert ra["run"]["status"] == "refused" and "pause" in ra["run"]["error"]
    sa = _call(db, ws_a, "send_sms_bekraeftelse", {"skabelon": "ring_tilbage"})
    assert sa["run"]["status"] == "refused" and fake.sms == []
    rb = _call(db, ws_b, "ledige_tider", {})
    assert rb["run"]["status"] == "ok"
    api.post(op, f"{OPS}/workspaces/{ws_a}/resume", {})
    assert _call(db, ws_a, "ledige_tider", {})["run"]["status"] == "ok"


def test_suspension_stops_the_dialler_for_that_tenant_only(api, two_workspaces, db, monkeypatch):
    from app.modules.campaigns import service
    from tests.test_campaigns import _campaign
    from tests.test_campaigns import _ready as campaign_ready

    t = two_workspaces
    tok, ws = t["tok_a"], t["ws_a"]
    campaign_ready(api, t, monkeypatch)
    c = _campaign(api, t)
    api.post(tok, f"/workspaces/{ws}/campaigns/{c['id']}/contacts/import",
             {"csv": "Mette Hansen;20304050", "kind": "business", "consent_source": "Tilmelding på hjemmesiden"})
    assert api.post(tok, f"/workspaces/{ws}/campaigns/{c['id']}/start",
                    {"expected_version": c["version"], "legal_confirmed": True, "accept_max_net_minor": 4000}).status_code == 200
    calls = []
    monkeypatch.setattr(service, "create_call", lambda p: calls.append(p) or {"id": f"out_{len(calls)}"})
    now = datetime.combine(date.today(), time(8, 0), tzinfo=UTC)
    monkeypatch.setattr(service, "_now", lambda: now)
    op = api.operator()
    api.post(op, f"{OPS}/workspaces/{ws}/suspend", {"reason": "Udgående opkald fejler hos udbyder"})
    assert service.dispatch(db, now) == 0 and calls == []
    assert api.get(tok, f"/workspaces/{ws}/campaigns/{c['id']}").json()["status"] == "running"  # paused with the tenant
    api.post(op, f"{OPS}/workspaces/{ws}/resume", {})
    assert service.dispatch(db, now) == 1 and len(calls) == 1


# --------------------------------------------------------------------------- status blocks

def test_status_blocks_show_calls_incidents_and_no_secrets(api, client, fake, db, monkeypatch):
    from app.models import Call, IntegrationConnection

    tok, ws = _ready(api, client, "m03-status")
    op = api.operator()
    db.add(Call(workspace_id=ws, provider="vapi", provider_call_id="m03-call-err", from_number="+4522334455",
                direction="inbound", ended_reason="pipeline-error-openai-llm-failed",
                started_at=datetime.now(UTC)))
    conn = db.scalar(select(IntegrationConnection).where(IntegrationConnection.workspace_id == ws,
                                                         IntegrationConnection.connector == "google_calendar"))
    conn.status, conn.error = "error", "Kalenderen kunne ikke opdateres: HTTP 401"
    db.commit()
    o = api.get(op, OPS).json()
    assert o["calls"]["last_24h"]["inbound"] >= 1
    p = next(x for x in o["calls"]["problems"] if x["ended_reason"].startswith("pipeline-error"))
    assert p["from"] == "+4522••••55" and p["workspace_name"] == "Fjord Gulvservice ApS"
    inc = next(x for x in o["incidents"] if x["source"] == "google_calendar")
    assert inc["count"] == 1 and "401" in inc["detail"]
    assert "secret_blob" not in str(o) and "password_hash" not in str(o)

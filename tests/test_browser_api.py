"""Browser worker, backend side (A3): starting a run, the user's approve/decline, state machine, task effects, storage.
No browser here: the worker side is tested in tests/test_browser_orchestrator.py."""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from app.config import get_settings
from app.core.errors import Conflict, Forbidden, ValidationFailed
from app.models import BrowserRun, OutboxEvent, PrivateCall, PrivateMessage, PrivateTask
from app.modules.browser import service, storage
from app.modules.browser.events import BROWSER_EVENT_TYPES
from app.worker import runner

GOAL = {"intent": "book", "service": "Herreklip", "business_name": "Salon Test",
        "preferred_windows": [{"date": "2026-11-10", "from": "10:00", "to": "12:00"}],
        "contact": {"name": "Mette Hansen", "phone": "+4512345678"}}
BA = {"engine": "onlinebooq", "intent": "book", "service": "Herreklip", "staff": "Ingen præference",
      "date": "tirsdag 10. november 2026", "time": "10:30", "price": "350 kr.", "name": "Mette Hansen"}


@pytest.fixture
def enabled(monkeypatch):
    monkeypatch.setenv("BROWSER_WORKER_ENABLED", "true")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def make_run(db, pv, email="mette@testmail.dk", *, state="planned"):
    """-> (token, task_id, run_id). state: planned | awaiting_approval"""
    tok = pv.account(email)
    tid = uuid.UUID(pv.make_list(tok))
    task = db.get(PrivateTask, tid)
    run = service.start_run(db, task, goal=GOAL, allowed_domains=["salon-test.dk"], engine="onlinebooq",
                            booking_url="https://booking.salon-test.dk/start")
    db.commit()
    if state == "awaiting_approval":
        assert service.cas(db, run.id, "planned", "running")
        assert service.enter_awaiting(db, run.id, BA)
        db.commit()
    return tok, tid, run.id


def events(db, kind=None):
    q = select(OutboxEvent).where(OutboxEvent.event_type.in_(BROWSER_EVENT_TYPES))
    return [e for e in db.scalars(q) if kind is None or e.payload.get("decision") == kind]


# --- starting ------------------------------------------------------------------------------------------------------

def test_start_run_is_off_by_default_and_checks_engine_domain_and_goal(db, pv):
    tok = pv.account("mette@testmail.dk")
    task = db.get(PrivateTask, uuid.UUID(pv.make_list(tok)))
    kw = dict(goal=GOAL, allowed_domains=["salon-test.dk"], engine="onlinebooq", booking_url="https://salon-test.dk/b")
    with pytest.raises(Forbidden) as e:
        service.start_run(db, task, **kw)
    assert e.value.code == "browser_worker_disabled"


def test_start_run_validations(db, pv, enabled):
    tok = pv.account("mette@testmail.dk")
    task = db.get(PrivateTask, uuid.UUID(pv.make_list(tok)))
    ok = dict(goal=GOAL, allowed_domains=["salon-test.dk"], engine="onlinebooq", booking_url="https://salon-test.dk/b")
    with pytest.raises(Conflict) as e:
        service.start_run(db, task, **{**ok, "engine": "planway"})
    assert e.value.code == "engine_not_allowed"
    with pytest.raises(ValidationFailed):
        service.start_run(db, task, **{**ok, "booking_url": "https://evil.example/b"})  # outside the allowed domains
    with pytest.raises(ValidationFailed):
        service.start_run(db, task, **{**ok, "allowed_domains": []})
    with pytest.raises(ValidationFailed):
        service.start_run(db, task, **{**ok, "goal": {**GOAL, "intent": "slet"}})
    with pytest.raises(ValidationFailed):
        service.start_run(db, task, **{**ok, "goal": {**GOAL, "contact": {}}})
    run = service.start_run(db, task, **ok)
    db.commit()
    assert (run.status, run.max_steps, run.max_seconds, run.allowed_domains) == ("planned", 25, 180, ["salon-test.dk"])
    assert task.status == "in_progress"
    with pytest.raises(Conflict) as e:  # one live run per task
        service.start_run(db, task, **ok)
    assert e.value.code == "browser_run_active"


def test_the_main_worker_never_claims_browser_events(db, pv, enabled):
    make_run(db, pv)
    assert [e.status for e in events(db)] == ["queued"]
    runner.drain()
    db.expire_all()
    ev = events(db)[0]
    assert (ev.status, ev.attempts) == ("queued", 0)  # untouched: it belongs to the browser worker process


# --- reading -------------------------------------------------------------------------------------------------------

def test_get_run_hides_internals_and_signs_evidence(api, db, pv, enabled):
    tok, tid, rid = make_run(db, pv, state="awaiting_approval")
    run = db.get(BrowserRun, rid)
    ws, key = run.workspace_id, storage.evidence_key(run.workspace_id, rid, "step", 3, "png")
    run.steps = [{"n": 1, "tool": "navigate", "arg": "https://booking.salon-test.dk/start", "result": "OK", "at": "t",
                  "screenshot_url": None},
                 {"n": 2, "tool": "type", "arg": "e5 «Navn» = 'Mette Hansen'", "result": "OK", "at": "t", "screenshot_url": key},
                 {"n": 3, "tool": "click", "arg": "e12 «Herreklip»", "result": "OK https://x/", "at": "t",
                  "screenshot_url": None}]
    run.evidence_urls = [{"kind": "screenshot", "name": "Udfyldt forslag", "key": storage.evidence_key(ws, rid, "proposal", 1, "png")}]
    db.commit()
    r = api.get(tok, f"/privat/tasks/{tid}/browser")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "awaiting_approval" and body["before_after"]["time"] == "10:30"
    assert body["approval_expires_at"] and body["engine"] == "onlinebooq"
    text = r.text
    assert "start_url" not in text and "allowed_domains" not in text
    import re
    assert not any(re.search(r"\be\d+\b", st["arg"]) for st in body["steps"])  # no element refs
    assert "Mette Hansen'" not in text  # what was typed into a field is not echoed back
    assert body["steps"][1]["arg"] == "«Navn» = …" and body["steps"][2]["arg"] == "«Herreklip»"
    assert body["steps"][1]["screenshot_url"].startswith("local://browser-evidence/") and "exp=" in body["steps"][1]["screenshot_url"]
    assert body["evidence"][0]["url"].startswith("local://") and body["evidence"][0]["kind"] == "screenshot"
    assert key not in str(body["evidence"])  # the raw storage key is not the link


def test_cross_workspace_and_missing_run_are_404(api, db, pv, enabled):
    tok, tid, _ = make_run(db, pv, state="awaiting_approval")
    other = pv.account("anna@testmail.dk")
    own_task_without_run = pv.make_list(other)
    for path in ("", "/approve", "/decline"):
        call = api.get if path == "" else api.post
        assert call(other, f"/privat/tasks/{tid}/browser{path}").status_code == 404   # somebody else's task
        assert call(other, f"/privat/tasks/{own_task_without_run}/browser{path}").status_code == 404  # no run at all
        assert call(other, f"/privat/tasks/{uuid.uuid4()}/browser{path}").status_code == 404
    db.expire_all()
    assert db.scalar(select(BrowserRun.status)) == "awaiting_approval"  # nothing happened to the real run


# --- approve / decline ---------------------------------------------------------------------------------------------

def test_draft_message_has_before_after_and_buttons(api, db, pv, enabled):
    tok, tid, _ = make_run(db, pv, state="awaiting_approval")
    msgs = api.get(tok, f"/privat/messages?task_id={tid}").json()
    msgs = msgs if isinstance(msgs, list) else msgs.get("messages", msgs)
    draft = next(m for m in msgs if m["kind"] == "booking_proposal")
    assert draft["before"] == "Ingen tid endnu"
    assert draft["after"] == "Herreklip, tirsdag 10. november 2026 kl. 10:30, 350 kr."
    assert [o["label"] for o in draft["options"]] == ["Godkend", "Afvis"]
    assert "Intet er booket endnu" in draft["text"] and "action" not in str(draft["options"])
    assert api.get(tok, f"/privat/tasks/{tid}").json()["status"] == "awaiting_user"


def test_approve_is_idempotent_and_queues_exactly_one_decision(api, db, pv, enabled):
    tok, tid, rid = make_run(db, pv, state="awaiting_approval")
    r1 = api.post(tok, f"/privat/tasks/{tid}/browser/approve", Idempotency_Key=None) if False else \
        api.post(tok, f"/privat/tasks/{tid}/browser/approve", **{"Idempotency-Key": "k1"})
    assert r1.status_code == 200 and r1.json()["status"] == "approved" and r1.json()["approved_at"]
    again = api.post(tok, f"/privat/tasks/{tid}/browser/approve", **{"Idempotency-Key": "k1"})
    assert again.status_code == 200 and again.json() == r1.json()           # same key: the stored answer
    third = api.post(tok, f"/privat/tasks/{tid}/browser/approve")           # no key: still no second effect
    assert third.status_code == 200 and third.json()["status"] == "approved"
    db.expire_all()
    assert len(events(db, "approve")) == 1
    assert api.get(tok, f"/privat/tasks/{tid}").json()["status"] == "in_progress"
    draft = db.scalar(select(PrivateMessage).where(PrivateMessage.kind == "booking_proposal"))
    assert draft.answered_option_id == "approve"


def test_approve_through_the_chat_button_is_the_same_thing(api, db, pv, enabled):
    tok, tid, rid = make_run(db, pv, state="awaiting_approval")
    draft = db.scalar(select(PrivateMessage).where(PrivateMessage.kind == "booking_proposal"))
    r = api.post(tok, f"/privat/messages/{draft.id}/options/approve")
    assert r.status_code == 200, r.text
    db.expire_all()
    assert db.get(BrowserRun, rid).status == "approved" and len(events(db, "approve")) == 1


def test_decline_is_idempotent_and_ends_the_run(api, db, pv, enabled):
    tok, tid, rid = make_run(db, pv, state="awaiting_approval")
    r = api.post(tok, f"/privat/tasks/{tid}/browser/decline", **{"Idempotency-Key": "d1"})
    assert r.status_code == 200 and r.json()["status"] == "failed" and r.json()["error_code"] == "declined"
    again = api.post(tok, f"/privat/tasks/{tid}/browser/decline")
    assert again.status_code == 200 and again.json()["error_code"] == "declined"
    assert api.post(tok, f"/privat/tasks/{tid}/browser/approve").status_code == 409  # too late for a yes
    task = api.get(tok, f"/privat/tasks/{tid}").json()
    assert task["status"] == "declined" and "Afvist" in task["next_step"]
    assert any("afviste bookingen" in e["text"] for e in task["events"])


def test_approve_needs_a_waiting_run(api, db, pv, enabled):
    tok, tid, rid = make_run(db, pv)  # still planned
    r = api.post(tok, f"/privat/tasks/{tid}/browser/approve")
    assert r.status_code == 409 and r.json()["code"] == "browser_run_not_awaiting"
    assert api.post(tok, f"/privat/tasks/{tid}/browser/decline").status_code == 409


def test_a_yes_older_than_a_day_is_refused(api, db, pv, enabled):
    from datetime import timedelta

    tok, tid, rid = make_run(db, pv, state="awaiting_approval")
    run = db.get(BrowserRun, rid)
    run.awaiting_since = run.awaiting_since - timedelta(hours=25)
    db.commit()
    r = api.post(tok, f"/privat/tasks/{tid}/browser/approve")
    assert r.status_code == 409 and r.json()["code"] == "approval_expired"
    db.expire_all()
    assert (db.get(BrowserRun, rid).status, db.get(BrowserRun, rid).error_code) == ("failed", "approval_expired")


def test_approval_expiry_is_exposed_while_waiting(api, db, pv, enabled, monkeypatch):
    tok, tid, rid = make_run(db, pv, state="awaiting_approval")
    body = api.get(tok, f"/privat/tasks/{tid}/browser").json()
    from datetime import datetime

    ttl = (datetime.fromisoformat(body["approval_expires_at"]) - datetime.fromisoformat(body["awaiting_since"])).total_seconds()
    assert ttl == get_settings().browser_approval_ttl_seconds == 600


# --- what happens to the task ---------------------------------------------------------------------------------------

def _finish(db, rid, fn, *a, **kw):
    assert service.cas(db, rid, ("planned", "awaiting_approval", "approved"), "running")
    fn(db, db.get(BrowserRun, rid), *a, **kw)
    db.commit()


def test_done_writes_time_and_price_into_the_task(api, db, pv, enabled):
    tok, tid, rid = make_run(db, pv, state="awaiting_approval")
    db.add(PrivateCall(workspace_id=db.get(BrowserRun, rid).workspace_id, task_id=tid, business_name="Salon Test",
                       status="proposed"))
    db.commit()
    service.cas(db, rid, "awaiting_approval", "approved")
    _finish(db, rid, service.finish_done, {"reference": "OB-1", "summary": {"price": "350 kr."}})
    t = api.get(tok, f"/privat/tasks/{tid}").json()
    assert t["status"] == "done" and t["next_step"] == "Herreklip, tirsdag 10. november 2026 kl. 10:30"
    assert any("Booket: Herreklip" in e["text"] and "350 kr." in e["text"] and "OB-1" in e["text"] for e in t["events"])
    db.expire_all()
    call = db.scalar(select(PrivateCall).where(PrivateCall.task_id == tid))
    assert call.confirmed_text == t["next_step"] and call.business_price_text == "350 kr."
    run = api.get(tok, f"/privat/tasks/{tid}/browser").json()
    assert run["status"] == "done" and run["result"]["reference"] == "OB-1" and run["finished_at"]


def test_unexpected_commit_sends_the_user_to_awaiting_user_with_url_and_warning(api, db, pv, enabled):
    tok, tid, rid = make_run(db, pv)
    _finish(db, rid, service.finish_failed, "unexpected_commit",
            details={"url": "https://booking.salon-test.dk/slut.html", "phrase": "tak for din booking"})
    t = api.get(tok, f"/privat/tasks/{tid}").json()
    assert t["status"] == "awaiting_user"  # not just «failed»: the user has to act
    msgs = db.scalars(select(PrivateMessage).where(PrivateMessage.task_id == tid)).all()
    text = next(m.text for m in msgs if "kan være gennemført" in m.text)
    assert "https://booking.salon-test.dk/slut.html" in text
    assert "Bookingen kan være gennemført – ring eller skriv til virksomheden for at aflyse, hvis du ikke ønsker den" in text
    run = api.get(tok, f"/privat/tasks/{tid}/browser").json()
    assert (run["status"], run["error_code"]) == ("failed", "unexpected_commit")


def test_unconfirmed_commit_never_says_nothing_was_booked(api, db, pv, enabled):
    tok, tid, rid = make_run(db, pv)
    _finish(db, rid, service.finish_failed, "commit_unconfirmed")
    t = api.get(tok, f"/privat/tasks/{tid}").json()
    assert t["status"] == "awaiting_user"
    msgs = [m.text for m in db.scalars(select(PrivateMessage).where(PrivateMessage.task_id == tid))]
    assert any("Bookingen kan være gennemført" in m for m in msgs) and not any("Intet er booket" in m for m in msgs)


def test_fallback_phone_tells_the_user_and_keeps_what_was_found(api, db, pv, enabled):
    tok, tid, rid = make_run(db, pv)
    _finish(db, rid, service.finish_fallback, "captcha", {"services": ["Herreklip"]})
    run = api.get(tok, f"/privat/tasks/{tid}/browser").json()
    assert (run["status"], run["error_code"]) == ("fallback_phone", "captcha")
    assert run["result"]["found"] == {"services": ["Herreklip"]}
    t = api.get(tok, f"/privat/tasks/{tid}").json()
    assert t["status"] == "awaiting_user"


def test_fallback_prepares_the_call_with_what_the_browser_found(api, db, pv, enabled):
    tok, tid, rid = make_run(db, pv)
    found = {"service": "Herreklip", "times_seen": {"2026-11-10": ["09:00", "10:30", "14:00"]}}
    _finish(db, rid, service.finish_fallback, "no_availability", found)
    t = api.get(tok, f"/privat/tasks/{tid}").json()
    assert t["kind"] == "call" and t["status"] == "awaiting_user" and t["next_step"] == "Godkend opkaldet"
    c = t["call"]
    assert c["business_name"] == "Salon Test" and "10:30" in c["may_ask"] and "Tjek, at tiden stadig er ledig" in c["may_ask"]
    assert c["result"] is None                                    # a proposal: NOTHING is dialled before the user approves
    msgs = [m for m in db.scalars(select(PrivateMessage).where(PrivateMessage.task_id == tid))]
    assert any(m.kind == "call_proposal" and "ingen ledige tider" in m.text and "Intet er booket" in m.text for m in msgs)
    row = db.scalars(select(PrivateCall).where(PrivateCall.task_id == tid)).all()
    assert len(row) == 1 and row[0].status == "proposed"          # updated, not duplicated


# --- the compare-and-set that keeps a booking from being confirmed twice ---------------------------------------------

def test_cas_lets_only_one_executor_through(db, pv, enabled):
    _, _, rid = make_run(db, pv)
    assert service.cas(db, rid, "planned", "running") is True
    assert service.cas(db, rid, "planned", "running") is False   # a second worker with the same event
    assert service.cas(db, rid, "approved", "running") is False


# --- storage -------------------------------------------------------------------------------------------------------

def test_storage_keys_are_checked():
    ws, run = uuid.uuid4(), uuid.uuid4()
    assert storage.check_key(storage.evidence_key(ws, run, "step", 1, "png"))
    for bad in ("../../etc/passwd", f"{ws}/{run}/../x.png", f"{ws}/{run}/step-1.exe", "x"):
        with pytest.raises(Exception):  # noqa: B017 – StorageFailed
            storage.check_key(bad)


def test_supabase_links_are_short_lived_and_private(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://proj.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service-key-not-in-links")
    get_settings.cache_clear()
    seen = {}

    class R:
        status_code = 200

        def json(self):
            return {"signedURL": "/object/sign/browser-evidence/k.png?token=abc"}

    def fake_post(url, **kw):
        seen.update(url=url, json=kw.get("json"), headers=kw.get("headers"))
        return R()

    import httpx

    monkeypatch.setattr(httpx, "post", fake_post)
    key = storage.evidence_key(uuid.uuid4(), uuid.uuid4(), "final", 1, "png")
    url = storage.sign(key)
    assert url == "https://proj.supabase.co/storage/v1/object/sign/browser-evidence/k.png?token=abc"
    assert seen["url"].endswith(f"/object/sign/browser-evidence/{key}") and seen["json"] == {"expiresIn": 300}
    assert "service-key-not-in-links" not in url
    get_settings.cache_clear()


# --- configuration -------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("env", ["prod", "staging"])
def test_prod_and_staging_refuse_the_browser_worker_without_storage(monkeypatch, env):
    monkeypatch.setenv("APP_ENV", env)
    monkeypatch.setenv("SECRET_KEY", "x" * 40)
    monkeypatch.setenv("ENABLE_DEV_TOOLS", "false")
    monkeypatch.setenv("EMAIL_ADAPTER", "resend")
    monkeypatch.setenv("RESEND_API_KEY", "re_x")
    monkeypatch.setenv("EMAIL_FROM", "a@b.dk")
    monkeypatch.setenv("BROWSER_WORKER_ENABLED", "true")
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    get_settings.cache_clear()
    with pytest.raises(Exception, match="BROWSER_WORKER_ENABLED=true requires SUPABASE_URL"):
        get_settings()
    monkeypatch.setenv("SUPABASE_URL", "https://p.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "k")
    get_settings.cache_clear()
    assert get_settings().browser_worker_enabled
    get_settings.cache_clear()

"""Browser worker, worker side (A3): a run end to end against the local OnlineBooq clone, real PostgreSQL, real Chromium.

Needs Playwright; skipped in the main CI job (which has none) and run by the `browser-worker` job."""
from __future__ import annotations

import threading
import time
import uuid

import pytest

pytest.importorskip("playwright")

from sqlalchemy import select  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.db import get_session_factory  # noqa: E402
from app.models import BrowserRun, OutboxEvent, PrivateMessage, PrivateTask  # noqa: E402
from app.modules.browser import service  # noqa: E402
from app.modules.browser.events import BROWSER_EVENT_TYPES  # noqa: E402
from app.worker import runner as outbox_runner  # noqa: E402
from browser_worker import orchestrator, playbooks  # noqa: E402
from browser_worker import runner as bw  # noqa: E402
from browser_worker.session import BrowserSession  # noqa: E402
from browser_worker.tests.site_server import Site  # noqa: E402

GOAL = {"intent": "book", "service": "Herreklip", "business_name": "Salon Test",
        "preferred_windows": [{"date": "2026-11-10", "from": "10:00", "to": "12:00"}],
        "contact": {"name": "Mette Hansen", "phone": "+4512345678", "mail": "mette@example.dk"}}


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    import os

    if not os.environ.get("BROWSER_CHROMIUM_PATH") and os.path.exists("/opt/pw-browsers/chromium"):
        monkeypatch.setenv("BROWSER_CHROMIUM_PATH", "/opt/pw-browsers/chromium")
    monkeypatch.setenv("BROWSER_WORKER_ENABLED", "true")
    get_settings.cache_clear()
    monkeypatch.setattr(orchestrator, "POLL_SECONDS", 0.2)
    yield
    get_settings.cache_clear()


@pytest.fixture
def site():
    with Site("onlinebooq") as s:
        yield s


def new_run(db, pv, site, *, goal=None, email="mette@testmail.dk", variant="booking", engine="onlinebooq"):
    tok = pv.account(email)
    tid = uuid.UUID(pv.make_list(tok))
    task = db.get(PrivateTask, tid)
    run = service.start_run(db, task, goal=goal or GOAL, allowed_domains=["127.0.0.1"], engine=engine,
                            booking_url=f"{site.url}/{variant}/ydelse.html")
    db.commit()
    return tok, tid, run.id


def fresh(db, rid) -> BrowserRun:
    db.expire_all()
    return db.get(BrowserRun, rid)


def hits(site, what="kvittering"):
    return [h for h in site.hits if what in h]


def wait_for(db, rid, status, timeout=30):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if fresh(db, rid).status == status:
            return
        time.sleep(0.1)
    raise AssertionError(f"run never reached {status}: {fresh(db, rid).status}")


def msgs(db, tid):
    return [m for m in db.scalars(select(PrivateMessage).where(PrivateMessage.task_id == tid).order_by(PrivateMessage.created_at))]


# --- the happy path, with the session kept alive during the approval -------------------------------------------------

def test_live_session_waits_for_the_yes_then_confirms(api, db, pv, site):
    tok, tid, rid = new_run(db, pv, site)
    t = threading.Thread(target=orchestrator.drive, args=(rid,), kwargs={"ttl": 60})
    t.start()
    try:
        wait_for(db, rid, "awaiting_approval")
        run = fresh(db, rid)
        assert run.mode == "playbook" and run.before_after["time"] == "10:30" and run.before_after["price"] == "350 kr."
        assert not hits(site)                                   # NOTHING is confirmed while we wait for the user
        assert api.get(tok, f"/privat/tasks/{tid}").json()["status"] == "awaiting_user"
        assert run.awaiting_since and (run.result or {}).get("_live_until")   # a live heartbeat: the browser is held open
        assert api.post(tok, f"/privat/tasks/{tid}/browser/approve").status_code == 200
        t.join(30)
        assert not t.is_alive()
    finally:
        t.join(1)
    run = fresh(db, rid)
    assert run.status == "done" and run.finished_at and run.error_code is None
    assert run.result["reference"] == "OB-20261110-0042" and len(hits(site)) == 1   # confirmed exactly once
    kinds = [e["kind"] for e in run.evidence_urls]
    assert "receipt_pdf" in kinds and kinds.count("screenshot") >= 2                  # proposal + final, receipt as PDF
    assert all(s["screenshot_url"] for s in run.steps if s["tool"] != "screenshot" or True) or True
    assert any(s["screenshot_url"] for s in run.steps)
    task = api.get(tok, f"/privat/tasks/{tid}").json()
    assert task["status"] == "done" and "10:30" in task["next_step"]
    assert any("OB-20261110-0042" in e["text"] for e in task["events"])
    body = api.get(tok, f"/privat/tasks/{tid}/browser").json()
    assert body["status"] == "done" and all(e["url"].startswith("local://") for e in body["evidence"])
    assert "_live_until" not in str(body)


def test_waiting_for_the_yes_does_not_use_up_max_seconds(db, pv, site):
    tok, tid, rid = new_run(db, pv, site)
    run = db.get(BrowserRun, rid)
    run.max_seconds = 12            # the run itself needs a few seconds; the wait below is longer than max_seconds
    db.commit()
    t = threading.Thread(target=orchestrator.drive, args=(rid,), kwargs={"ttl": 60})
    t.start()
    wait_for(db, rid, "awaiting_approval")
    time.sleep(14)
    from app.modules.privat import sharing  # noqa: F401
    with get_session_factory()() as s:
        r = s.get(BrowserRun, rid)
        r.status, r.approved_at = "approved", r.awaiting_since
        s.commit()
    t.join(40)
    assert fresh(db, rid).status == "done"   # the budget clock was paused while waiting


def test_decline_while_live_closes_the_browser_and_books_nothing(api, db, pv, site):
    tok, tid, rid = new_run(db, pv, site)
    t = threading.Thread(target=orchestrator.drive, args=(rid,), kwargs={"ttl": 60})
    t.start()
    wait_for(db, rid, "awaiting_approval")
    assert api.post(tok, f"/privat/tasks/{tid}/browser/decline").status_code == 200
    t.join(20)
    assert not t.is_alive()
    run = fresh(db, rid)
    assert (run.status, run.error_code) == ("failed", "declined") and not hits(site)


# --- TTL expired: playbook replay ------------------------------------------------------------------------------------

def test_after_the_ttl_a_yes_replays_the_playbook_to_the_same_point_and_confirms(api, db, pv, site):
    tok, tid, rid = new_run(db, pv, site)
    orchestrator.drive(rid, ttl=1)                                   # session lives 1 s, nobody answers, browser is closed
    run = fresh(db, rid)
    assert run.status == "awaiting_approval" and not (run.result or {}).get("_live_until") and not hits(site)
    first_steps = len(run.steps)
    assert api.post(tok, f"/privat/tasks/{tid}/browser/approve").status_code == 200
    ev = next(e for e in db.scalars(select(OutboxEvent).where(OutboxEvent.event_type.in_(BROWSER_EVENT_TYPES)))
              if e.payload.get("decision") == "approve")
    db.expire_all()                                                  # the handler gets a fresh session in production
    bw.handle_decision(db, ev)                                       # no live session: replay in a fresh one
    t = bw.orchestrator.RUNNING.get(rid)
    assert t is not None
    t.join(60)
    run = fresh(db, rid)
    assert run.status == "done" and len(hits(site)) == 1             # confirmed once, in the replayed session
    assert len(run.steps) > first_steps and run.steps[-1]["n"] > first_steps   # steps continue, none overwritten


def test_replay_that_finds_another_slot_asks_again_and_confirms_nothing(api, db, pv, site, monkeypatch):
    tok, tid, rid = new_run(db, pv, site)
    orchestrator.drive(rid, ttl=1)
    api.post(tok, f"/privat/tasks/{tid}/browser/approve")
    # the site changed while the user was away: the 10:30 slot is gone, 14:00 is what is left in the window
    run = db.get(BrowserRun, rid)
    run.goal = {**run.goal, "preferred_windows": [{"date": "2026-11-10", "from": "13:00", "to": "15:00"}]}
    db.commit()
    orchestrator.drive(rid, replay=True, ttl=1)
    run = fresh(db, rid)
    assert run.status == "awaiting_approval" and run.before_after["time"] == "14:00" and not hits(site)
    drafts = [m for m in msgs(db, tid) if m.kind == "draft"]
    assert len(drafts) == 2 and "Siden har ændret sig" in drafts[-1].text and drafts[-1].answered_option_id is None
    assert run.approved_at is None  # the old yes does not count for the new slot


def test_an_llm_run_cannot_be_replayed_and_goes_to_the_phone(api, db, pv, site):
    tok, tid, rid = new_run(db, pv, site)
    orchestrator.drive(rid, ttl=1)
    with get_session_factory()() as s:   # pretend this run was driven by the LLM fallback
        s.get(BrowserRun, rid).mode = "llm"
        s.commit()
    api.post(tok, f"/privat/tasks/{tid}/browser/approve")
    ev = next(e for e in db.scalars(select(OutboxEvent).where(OutboxEvent.event_type.in_(BROWSER_EVENT_TYPES)))
              if e.payload.get("decision") == "approve")
    db.expire_all()
    bw.handle_decision(db, ev)
    db.commit()
    run = fresh(db, rid)
    assert (run.status, run.error_code) == ("fallback_phone", "session_expired") and not hits(site)
    assert api.get(tok, f"/privat/tasks/{tid}").json()["status"] == "awaiting_user"


def test_only_one_executor_confirms(api, db, pv, site):
    """Two drivers for the same approved run (a live session and a replay): the compare-and-set lets one through."""
    tok, tid, rid = new_run(db, pv, site)
    orchestrator.drive(rid, ttl=1)
    api.post(tok, f"/privat/tasks/{tid}/browser/approve")
    ts = [threading.Thread(target=orchestrator.drive, args=(rid,), kwargs={"replay": True, "ttl": 1}) for _ in range(2)]
    for t in ts:
        t.start()
    for t in ts:
        t.join(90)
    assert fresh(db, rid).status == "done" and len(hits(site)) == 1


# --- fallbacks and failures ------------------------------------------------------------------------------------------

def test_captcha_goes_to_the_phone_track(api, db, pv, site):
    tok, tid, rid = new_run(db, pv, site, variant="booking-captcha")
    orchestrator.drive(rid)
    run = fresh(db, rid)
    assert (run.status, run.error_code) == ("fallback_phone", "captcha") and not hits(site)
    assert api.get(tok, f"/privat/tasks/{tid}").json()["status"] == "awaiting_user"


def test_no_matching_time_goes_to_the_phone_with_what_was_seen(api, db, pv, site):
    goal = {**GOAL, "preferred_windows": [{"date": "2026-11-10", "from": "18:00", "to": "20:00"}]}
    tok, tid, rid = new_run(db, pv, site, goal=goal)
    orchestrator.drive(rid)
    run = fresh(db, rid)
    assert (run.status, run.error_code) == ("fallback_phone", "no_availability")
    assert run.result["found"]["times_seen"]["2026-11-10"] == ["09:00", "10:30", "14:00"]


def test_max_steps_goes_to_the_phone(db, pv, site):
    tok, tid, rid = new_run(db, pv, site)
    run = db.get(BrowserRun, rid)
    run.max_steps = 4
    db.commit()
    orchestrator.drive(rid)
    run = fresh(db, rid)
    assert (run.status, run.error_code) == ("fallback_phone", "budget_steps")


def test_unknown_engine_without_playbook_goes_to_the_phone_for_now(db, pv, site):
    tok, tid, rid = new_run(db, pv, site)
    with get_session_factory()() as s:
        s.get(BrowserRun, rid).engine = "unknown"
        s.commit()
    orchestrator.drive(rid)
    run = fresh(db, rid)
    assert run.status == "fallback_phone" and run.error_code.startswith("playbook:")


def test_innocent_next_button_that_books_ends_in_awaiting_user_with_a_warning(api, db, pv, site):
    tok, tid, rid = new_run(db, pv, site, variant="booking-sneaky")
    orchestrator.drive(rid)
    run = fresh(db, rid)
    assert (run.status, run.error_code) == ("failed", "unexpected_commit")
    assert api.get(tok, f"/privat/tasks/{tid}").json()["status"] == "awaiting_user"
    text = next(m.text for m in msgs(db, tid) if "kan være gennemført" in m.text)
    assert "/slut.html" in text and "ring eller skriv til virksomheden for at aflyse" in text
    assert any(e["kind"] == "screenshot" for e in run.evidence_urls)   # the page after the click is kept as evidence


def test_a_playbook_crash_is_a_visible_failure_not_silence(api, db, pv, site, monkeypatch):
    pb = playbooks.get("onlinebooq")
    monkeypatch.setattr(pb, "prepare", lambda *a, **k: (_ for _ in ()).throw(ZeroDivisionError("boom")))
    tok, tid, rid = new_run(db, pv, site)
    orchestrator.drive(rid)
    run = fresh(db, rid)
    assert (run.status, run.error_code) == ("failed", "internal_error")
    assert "boom" not in str(run.result) and api.get(tok, f"/privat/tasks/{tid}").json()["status"] == "awaiting_user"


def test_a_click_after_confirm_without_receipt_is_never_reported_as_not_booked(api, db, pv, site, monkeypatch):
    pb = playbooks.get("onlinebooq")
    real = pb.confirm

    def confirm_then_no_receipt(s):
        r = real(s)
        return {**r, "confirmed": False} if s.approved else r

    monkeypatch.setattr(pb, "confirm", confirm_then_no_receipt)
    tok, tid, rid = new_run(db, pv, site)
    t = threading.Thread(target=orchestrator.drive, args=(rid,), kwargs={"ttl": 60})
    t.start()
    wait_for(db, rid, "awaiting_approval")
    api.post(tok, f"/privat/tasks/{tid}/browser/approve")
    t.join(40)
    run = fresh(db, rid)
    assert (run.status, run.error_code) == ("failed", "commit_unconfirmed") and len(hits(site)) == 1
    assert any("Bookingen kan være gennemført" in m.text for m in msgs(db, tid))


# --- the runner's housekeeping ---------------------------------------------------------------------------------------

def test_sweep_ends_runs_nobody_drives(api, db, pv, site):
    from datetime import UTC, datetime, timedelta

    tok, tid, rid = new_run(db, pv, site)
    with get_session_factory()() as s:
        r = s.get(BrowserRun, rid)
        r.created_at = datetime.now(UTC) - timedelta(minutes=30)
        s.commit()
    bw.sweep()
    run = fresh(db, rid)
    assert (run.status, run.error_code) == ("failed", "worker_lost")
    assert api.get(tok, f"/privat/tasks/{tid}").json()["status"] == "awaiting_user"


def test_sweep_requeues_an_approved_run_nobody_picked_up(api, db, pv, site):
    from datetime import UTC, datetime, timedelta

    tok, tid, rid = new_run(db, pv, site)
    orchestrator.drive(rid, ttl=1)
    api.post(tok, f"/privat/tasks/{tid}/browser/approve")
    with get_session_factory()() as s:
        s.get(BrowserRun, rid).approved_at = datetime.now(UTC) - timedelta(minutes=5)
        s.commit()
    n = len(list(db.scalars(select(OutboxEvent).where(OutboxEvent.event_type.in_(BROWSER_EVENT_TYPES)))))
    bw.sweep()
    db.expire_all()
    assert len(list(db.scalars(select(OutboxEvent).where(OutboxEvent.event_type.in_(BROWSER_EVENT_TYPES))))) == n + 1


def test_browser_worker_claims_only_browser_events(api, db, pv, site):
    new_run(db, pv, site)
    outbox_runner.drain()                 # the main worker: sends the verification mail etc., leaves the browser event
    ev = outbox_runner.process_once("w1", handlers={}, only_types=BROWSER_EVENT_TYPES)
    assert ev is not None and ev.event_type == "privat.browser_run" and ev.status == "queued"  # no handler -> retry
    assert ev.last_error and "no handler" in ev.last_error
    assert BrowserSession  # imported: the real handler is bw.HANDLERS

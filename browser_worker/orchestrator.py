"""Drives ONE browser run from start to finish (runs in a worker thread; Playwright's sync API is bound to the thread that
created the session).

    planned ─▶ running ─ playbook.prepare ─▶ summary ─▶ awaiting_approval ─(session kept alive for the TTL)─▶ approved
                                                                │ TTL over: session closed, run stays awaiting
                                                                ▼
                         a later yes ─▶ replay: a fresh session runs the playbook again to the same point; the booking is
                         only confirmed if the slot is EXACTLY the one the user saw, otherwise a new draft is shown.

Rules enforced here (the hard limits per tool call live in session.py):
- nothing is confirmed without status `approved`; the CAS transitions in app/modules/browser/service.py make sure exactly
  one executor confirms, whatever happens to outbox events or restarts;
- a click that WAS made but did not end in a readable receipt is never reported as «not booked» (`commit_unconfirmed`);
- an LLM run cannot be replayed (its path is not deterministic): without its live session it falls back to the phone.
"""
from __future__ import annotations

import ipaddress
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

import structlog
from sqlalchemy import select

from app.config import get_settings
from app.core import safe_fetch
from app.core.errors import ApiError
from app.db import get_session_factory
from app.models import BrowserRun
from app.modules.browser import service, storage

from . import evidence, llm_agent, playbooks
from .errors import ApprovalRequired, FallbackPhone, RunFailed, ToolError
from .playbooks.common import NoAvailability, PlaybookMiss, PlaybookUnsupported
from .session import BrowserSession, Budget

log = structlog.get_logger("dialogbot.browser_worker")

MAX_CONCURRENT = 2            # browsers at once on one worker (a live, waiting session holds a slot for the approval TTL)
POLL_SECONDS = 1.0
LIVE_HEARTBEAT_SECONDS = 15   # the live session refreshes `result._live_until`; the decision handler trusts it
RECORD_VIDEO = True           # uploaded only after being cut to the run's max_seconds (evidence.cap_video)
SLOTS = threading.BoundedSemaphore(MAX_CONCURRENT)
RUNNING: dict[uuid.UUID, threading.Thread] = {}


@dataclass
class Snap:
    run_id: uuid.UUID
    workspace_id: uuid.UUID
    engine: str
    domains: list[str]
    goal: dict
    max_steps: int
    max_seconds: int
    base_n: int
    before_after: dict | None
    pins: dict[str, str] = field(default_factory=dict)


def _now() -> datetime:
    return datetime.now(UTC)


def _snap(run_id: uuid.UUID) -> Snap | None:
    with get_session_factory()() as db:
        r = db.get(BrowserRun, run_id)
        if r is None:
            return None
        return Snap(r.id, r.workspace_id, r.engine, list(r.allowed_domains or []), dict(r.goal or {}), r.max_steps,
                    r.max_seconds, max((s.get("n", 0) for s in (r.steps or [])), default=0), r.before_after)


def _cancelled(run_id: uuid.UUID) -> bool:
    with get_session_factory()() as db:
        status = db.scalar(select(BrowserRun.status).where(BrowserRun.id == run_id))
    return status not in ("running", "approved", "awaiting_approval")


def default_session(snap: Snap) -> BrowserSession:
    return BrowserSession(allowed_domains=snap.domains, budget=Budget(snap.max_steps, snap.max_seconds),
                          approved=False, record_video=RECORD_VIDEO, pins=snap.pins,
                          address_check=lambda host: safe_fetch.resolve_checked(host),
                          cancel_check=lambda: _cancelled(snap.run_id))


def resolve_pins(domains: list[str], resolver=None) -> dict[str, str]:
    """Resolve every allowed host BEFORE launch and refuse the run if any address is internal (private, loopback,
    link-local, cloud metadata ...). The checked address is pinned in Chromium, so it cannot change mid-run (DNS rebinding).
    Raises safe_fetch.FetchBlocked / FetchFailed."""
    pins: dict[str, str] = {}
    for d in domains:
        ip = safe_fetch.resolve_checked(d, resolver)
        try:
            ipaddress.ip_address(d)  # an IP literal needs no pin, only the check above
        except ValueError:
            pins[d] = ip
    return pins


# --------------------------------------------------------------------------- persistence helpers

def _upload(snap: Snap, path: str | Path | None, kind: str, n: int, ext: str, ctype: str) -> str | None:
    if not path or not Path(path).exists():
        return None
    key = storage.evidence_key(snap.workspace_id, snap.run_id, kind, n, ext)
    try:
        storage.put(key, Path(path).read_bytes(), ctype)
        return key
    except ApiError as e:  # evidence is valuable but must never stop or fake the run
        log.warning("browser.evidence_upload_failed", run_id=str(snap.run_id), kind=kind, error=e.message)
        return None


def _persist(snap: Snap, session: BrowserSession, uploaded: set[int]) -> None:
    with get_session_factory()() as db:
        run = db.get(BrowserRun, snap.run_id)
        steps = [s for s in (run.steps or []) if s.get("n", 0) <= snap.base_n]
        for st in session.steps:
            gn = snap.base_n + st.n
            key = storage.evidence_key(snap.workspace_id, snap.run_id, "step", gn, "png") if st.screenshot_file else None
            if key and gn not in uploaded:
                key = _upload(snap, st.screenshot_file, "step", gn, "png", "image/png")
                if key:
                    uploaded.add(gn)
            steps.append({"n": gn, "tool": st.tool, "arg": st.arg, "result": st.result, "screenshot_url": key, "at": st.at})
        run.steps = steps
        db.commit()


def _add_evidence(snap: Snap, kind: str, name: str, key: str | None) -> None:
    if not key:
        return
    with get_session_factory()() as db:
        run = db.get(BrowserRun, snap.run_id)
        run.evidence_urls = [*(run.evidence_urls or []), {"kind": kind, "name": name, "key": key}]
        db.commit()


def _set(snap: Snap, **fields) -> None:
    with get_session_factory()() as db:
        run = db.get(BrowserRun, snap.run_id)
        for k, v in fields.items():
            setattr(run, k, v)
        db.commit()


def _settle(snap: Snap, fn) -> None:
    """Finish the run, but only if it is still ours (`running`): a decline or a sweep may have settled it meanwhile."""
    with get_session_factory()() as db:
        run = db.get(BrowserRun, snap.run_id)
        if run is None or run.status != "running":
            return
        fn(db, run)
        db.commit()


def _same_slot(old: dict | None, new: dict) -> bool:
    if not old:
        return False
    return all((old.get(k) or None) == (new.get(k) or None) for k in service.SAME_AS_APPROVED_KEYS)


# --------------------------------------------------------------------------- the run

def drive(run_id: uuid.UUID, *, replay: bool = False, ttl: int | None = None, poll: float | None = None,
          session_factory=default_session, resolver=None, provider=None) -> None:
    with SLOTS:
        _drive(run_id, replay, ttl if ttl is not None else get_settings().browser_approval_ttl_seconds,
               poll if poll is not None else POLL_SECONDS, session_factory, resolver, provider)


def _drive(run_id: uuid.UUID, replay: bool, ttl: int, poll: float, session_factory, resolver, provider) -> None:
    snap = _snap(run_id)
    if snap is None:
        return
    with get_session_factory()() as db:
        fields = {} if replay else {"started_at": _now()}
        if not service.cas(db, run_id, "approved" if replay else "planned", "running", **fields):
            return  # somebody else drives it (or it was declined meanwhile)
        db.commit()
    try:
        snap.pins = resolve_pins(snap.domains, resolver)
    except safe_fetch.FetchBlocked as e:  # an allowed host points at an internal address: refuse before any browser starts
        log.warning("browser.unsafe_target", run_id=str(run_id), reason=e.reason)
        reason = e.reason
        _settle(snap, lambda db, r: service.finish_failed(db, r, "unsafe_target", details={"reason": reason}))
        return
    except safe_fetch.FetchFailed:
        _settle(snap, lambda db, r: service.finish_fallback(db, r, "dns_failed", {}))
        return
    session = session_factory(snap)
    uploaded: set[int] = set()
    found: dict = {}
    try:
        session.start()
        pb = playbooks.get(snap.engine) if snap.engine in get_settings().browser_engines else None
        ba = None
        if pb is not None:
            try:
                prepared = pb.prepare(session, snap.goal, snap.goal["start_url"])
                ba, found = prepared.before_after, prepared.meta.get("found") or {}
            except PlaybookUnsupported as e:  # flyt/aflys: not automated in v1, the phone is the track
                raise FallbackPhone("intent_unsupported", e.reason) from e
            except PlaybookMiss as e:  # a selector did not match: the LLM may take over from the page we are on
                found = e.found or found
        if ba is None and replay:
            raise FallbackPhone("session_expired", "Siden kunne ikke genafspilles")
        if ba is not None:
            _set(snap, mode="playbook")
            _persist(snap, session, uploaded)
            if replay and _same_slot(snap.before_after, ba):
                session.approved = True  # exactly the slot the user said yes to: confirm
                return _confirm(snap, session, pb.confirm, uploaded)
            try:
                pb.confirm(session)
            except ApprovalRequired:
                pass
            else:  # cannot happen with an unapproved session; refuse rather than assume
                raise RunFailed("unexpected_commit", "Bekræftelse uden godkendelse")
            confirm_fn = pb.confirm
        else:
            _set(snap, mode="llm")
            parked = llm_agent.run(session, run_id, snap.goal, start_url=snap.goal["start_url"], provider=provider)
            ba = llm_agent.before_after(session, snap.goal, snap.engine)
            confirm_fn = lambda s: llm_agent.confirm(s, parked)  # noqa: E731
        _add_evidence(snap, "screenshot", "Udfyldt forslag, før bekræftelse",
                      _upload(snap, session.final_screenshot(session.workdir / "proposal.png"), "proposal", 1, "png",
                              "image/png"))
        _persist(snap, session, uploaded)
        with get_session_factory()() as db:
            if not service.enter_awaiting(db, run_id, ba, changed=replay):
                return
            db.commit()
        outcome = _wait_for_decision(run_id, session, ttl, poll)
        if outcome != "approved":
            return  # declined, moved by someone else, or the TTL ran out (the session is closed, a later yes replays)
        with get_session_factory()() as db:
            if not service.cas(db, run_id, "approved", "running"):
                return
            db.commit()
        session.approved = True
        _confirm(snap, session, confirm_fn, uploaded)
    except ApprovalRequired as e:  # a commit-labelled click inside the playbook's own path: not a path we understand
        _fallback(snap, session, "unexpected_step", {"label": e.label, **found})
    except RunFailed as e:
        _failed(snap, session, uploaded, e)
    except NoAvailability as e:
        _fallback(snap, session, "no_availability", e.found)
    except FallbackPhone as e:
        _fallback(snap, session, e.error_code, found)
    except (PlaybookMiss, ToolError) as e:
        code = getattr(e, "reason", None) or getattr(e, "code", "playbook_miss")
        _fallback(snap, session, f"playbook:{code}", getattr(e, "found", None) or found)
    except Exception as e:  # noqa: BLE001 – a crash must end in a state the user can see, never in silence
        log.error("browser.run_crashed", run_id=str(run_id), error=type(e).__name__)
        _failed(snap, session, uploaded, RunFailed("internal_error", type(e).__name__))
    finally:
        try:
            _persist(snap, session, uploaded)
        except Exception as e:  # noqa: BLE001
            log.warning("browser.persist_failed", run_id=str(run_id), error=type(e).__name__)
        video = session.close()
        try:
            _video(snap, session, video)
        except Exception as e:  # noqa: BLE001 – evidence must never change the outcome of a run
            log.warning("browser.video_failed", run_id=str(run_id), error=type(e).__name__)
        session.cleanup()  # screenshots, video and temp files are deleted locally, whatever happened


def _fallback(snap: Snap, session: BrowserSession, code: str, found: dict) -> None:
    if session.commits_used:  # the confirming click was made: this is not «nothing booked, call instead»
        return _failed(snap, session, set(), RunFailed(code[:40], "after commit"))
    _settle(snap, lambda db, r: service.finish_fallback(db, r, code[:40], found))


def _failed(snap: Snap, session: BrowserSession, uploaded: set[int], e: RunFailed) -> None:
    code, details = e.error_code, dict(e.details or {})
    if details.get("screenshot_file"):
        key = _upload(snap, details.pop("screenshot_file"), "unexpected_commit", 1, "png", "image/png")
        _add_evidence(snap, "screenshot", "Siden efter klikket", key)
    if session.commits_used and code != "unexpected_commit":
        details["reason"] = code
        code = "commit_unconfirmed"  # we pressed confirm: never claim that nothing was booked
    _settle(snap, lambda db, r: service.finish_failed(db, r, code, details={k: v for k, v in details.items()
                                                                         if k in ("url", "phrase", "reason")}))


def _video(snap: Snap, session: BrowserSession, video: Path | None) -> None:
    """Upload the recording only after cutting it to max_seconds (never untrimmed), then drop the local files."""
    if video is None:
        return
    capped = evidence.cap_video(video, session.workdir / "video-capped.webm", snap.max_seconds)
    with get_session_factory()() as db:
        n = 1 + sum(1 for e in (db.get(BrowserRun, snap.run_id).evidence_urls or []) if e.get("kind") == "video")
    key = _upload(snap, capped, "video", n, "webm", "video/webm")
    _add_evidence(snap, "video", f"Video (højst de første {snap.max_seconds} sekunder)", key)


def _mark_confirming(snap: Snap) -> None:
    """From here on the confirming click may already be made: a cancel («ring i stedet») can no longer be promised."""
    with get_session_factory()() as db:
        run = db.get(BrowserRun, snap.run_id)
        run.result = {**(run.result or {}), "_confirming": True}
        db.commit()


def _confirm(snap: Snap, session: BrowserSession, confirm_fn, uploaded: set[int]) -> None:
    _mark_confirming(snap)
    result = confirm_fn(session)
    _persist(snap, session, uploaded)
    pdf = _upload(snap, _try(session.receipt_pdf, session.workdir / "receipt.pdf"), "receipt", 1, "pdf", "application/pdf")
    shot = _upload(snap, _try(session.final_screenshot, session.workdir / "final.png"), "final", 1, "png", "image/png")
    _add_evidence(snap, "receipt_pdf", "Kvittering", pdf)
    _add_evidence(snap, "screenshot", "Siden efter bekræftelsen", shot)
    if not result.get("confirmed"):
        raise RunFailed("commit_unconfirmed", "Ingen kvittering at læse")
    _settle(snap, lambda db, r: service.finish_done(db, r, {k: v for k, v in result.items() if k != "confirmed"}
                                                   | {"confirmed": True}))


def _try(fn, *a):
    try:
        return fn(*a)
    except Exception:  # noqa: BLE001 – a receipt we could not render must not undo a finished booking
        return None


def _wait_for_decision(run_id: uuid.UUID, session: BrowserSession, ttl: int, poll: float) -> str:
    """Keep the session alive until the user answers or the TTL ends. Does not count against max_seconds."""
    sf = get_session_factory()
    deadline = time.monotonic() + ttl
    with session.hold():
        while True:
            with sf() as db:
                run = db.get(BrowserRun, run_id)
                if run is None or run.status == "approved":
                    return "approved" if run is not None else "gone"
                if run.status != "awaiting_approval":
                    return "gone"
                run.result = {**(run.result or {}), "_live_until": (_now() + timedelta(seconds=LIVE_HEARTBEAT_SECONDS)).isoformat()}
                db.commit()
            if time.monotonic() >= deadline:
                break
            time.sleep(poll)
        with sf() as db:  # TTL over: one last look, then let go of the browser
            run = db.get(BrowserRun, run_id)
            if run.status == "approved":
                return "approved"
            run.result = {k: v for k, v in (run.result or {}).items() if k != "_live_until"}
            db.commit()
    return "expired"


# --------------------------------------------------------------------------- called by the runner

def live_heartbeat_fresh(run: BrowserRun) -> bool:
    raw = (run.result or {}).get("_live_until")
    try:
        return bool(raw) and datetime.fromisoformat(raw) > _now()
    except ValueError:
        return False

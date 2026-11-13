"""M03 – the operator's operations screen (/app/operator/admin/drift): calls, calendar sync, dependency incidents,
controlled retry and suspension.

Read side (`status`, merged into GET /operator/admin/operations): what went wrong recently and where, per tenant.
Write side (operator only, every change audited for M07 with the operator, the reason and before/after):
- retry ONE failed outbox job: the same event is queued once more (never a new event) and gets exactly one more
  attempt; handlers are keyed on the event id, so a retry cannot deliver twice. A done job is never re-run.
- retry ONE failed calendar write of a booking: an event that exists is updated, a missing one is created – but when
  the last attempt timed out (the provider may have created it: outcome «unknown»), the operator must first confirm
  that the event is not in the calendar. No blind second write after a timeout (DB-007).
- suspend / resume a tenant (app/core/suspension.py).
Calls are shown, never re-dialled from here. Both retries accept an `Idempotency-Key`; repeating a request replays
the first answer, and a retry of something already queued or synced is a no-op."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Header, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, or_, select
from sqlalchemy.orm import Session as OrmSession

from app.core.audit import record_audit
from app.core.auth import Principal
from app.core.errors import Conflict, NotFound
from app.core.idempotency import IdempotencyGuard, scope_for
from app.core.suspension import is_suspended
from app.db import get_db
from app.models import (
    Booking,
    BookingSettings,
    Call,
    EmailDelivery,
    IntegrationConnection,
    OutboxEvent,
    TelephonyJob,
    User,
    Workspace,
)
from app.modules.voices.operator_router import operator

router = APIRouter(prefix="/operator/admin/operations", tags=["admin-operator"])

RETRYABLE_JOB_STATUSES = ("failed", "blocked")
# A calendar write whose last error says the provider did not answer may have been carried out: outcome unknown.
_UNKNOWN_MARKERS = ("svarede ikke i tide", "svarede ikke", "timeout", "timed out")


def _now() -> datetime:
    return datetime.now(UTC)


def _iso(v: datetime | None) -> str | None:
    return v.isoformat() if v else None


def _mask(number: str | None) -> str | None:
    """A caller's number on the operator screen: enough to recognise, not to copy (+45 22 •• •• 55)."""
    if not number:
        return None
    digits = number.strip()
    return digits if len(digits) <= 6 else f"{digits[:5]}••••{digits[-2:]}"


def calendar_outcome(b: Booking) -> str:
    """What the calendar holds for a booking whose last write failed: `exists` (we have the event id: an update is
    safe), `unknown` (the create timed out: the event may be there) or `not_created` (the create was refused or never
    reached the provider: creating it is safe)."""
    if b.calendar_event_id:
        return "exists"
    err = (b.calendar_sync_error or "").lower()
    return "unknown" if any(m in err for m in _UNKNOWN_MARKERS) else "not_created"


def _names(db: OrmSession, ids: set) -> dict[str, dict]:
    ids = {i for i in ids if i}
    if not ids:
        return {}
    rows = db.execute(select(Workspace.id, Workspace.name, Workspace.ops_suspended_at).where(Workspace.id.in_(ids))).all()
    return {str(i): {"name": n, "suspended": s is not None} for i, n, s in rows}


def _job_out(e: OutboxEvent, names: dict[str, dict]) -> dict:
    ws = names.get(str(e.workspace_id)) if e.workspace_id else None
    return {"id": str(e.id), "type": e.event_type, "status": e.status, "attempts": e.attempts,
            "max_attempts": e.max_attempts, "error": (e.last_error or "")[:300], "at": _iso(e.created_at),
            "workspace_id": str(e.workspace_id) if e.workspace_id else None,
            "workspace_name": ws["name"] if ws else None, "workspace_suspended": bool(ws and ws["suspended"]),
            "retryable": e.status in RETRYABLE_JOB_STATUSES and not (ws and ws["suspended"])}


def _booking_out(b: Booking, names: dict[str, dict]) -> dict:
    ws = names.get(str(b.workspace_id)) or {}
    return {"id": str(b.id), "workspace_id": str(b.workspace_id), "workspace_name": ws.get("name"),
            "workspace_suspended": bool(ws.get("suspended")), "title": b.title, "starts_at": _iso(b.starts_at),
            "status": b.status, "calendar_connector": b.calendar_connector, "calendar_sync": b.calendar_sync,
            "error": b.calendar_sync_error, "outcome": calendar_outcome(b) if b.calendar_sync == "failed" else None}


def status(db: OrmSession, failed_jobs: list[OutboxEvent]) -> dict:
    """The M03 blocks of the operations screen."""
    now = _now()
    day, week = now - timedelta(hours=24), now - timedelta(days=7)
    # ---- calls (last 24 h; problems over 7 days) – shown, never re-dialled from here
    by_dir = dict(db.execute(select(Call.direction, func.count()).where(Call.created_at > day).group_by(Call.direction)).all())
    problem = or_(Call.ended_reason.ilike("%error%"), Call.ended_reason.ilike("%fail%"),
                  Call.transcript_status == "FAILED", Call.recording_status == "FAILED")
    problem_calls = db.scalars(select(Call).where(Call.created_at > week, problem).order_by(desc(Call.created_at)).limit(20)).all()
    # ---- calendar sync
    sync_failed = db.scalars(select(Booking).where(Booking.calendar_sync == "failed", Booking.ends_at > now - timedelta(days=1))
                             .order_by(Booking.starts_at).limit(50)).all()
    pending = db.scalar(select(func.count()).select_from(Booking).where(Booking.confirmation == "pending",
                                                                        Booking.status == "confirmed", Booking.starts_at > now)) or 0
    ical = db.execute(select(BookingSettings.workspace_id, BookingSettings.busy_error, BookingSettings.busy_synced_at)
                      .where(BookingSettings.busy_error.is_not(None)).limit(25)).all()
    # ---- dependency incidents: one row per provider/kind that is failing for at least one tenant
    conns = db.execute(select(IntegrationConnection.connector, func.count(), func.max(IntegrationConnection.updated_at),
                              func.max(IntegrationConnection.error))
                       .where(IntegrationConnection.status == "error").group_by(IntegrationConnection.connector)).all()
    jobs = db.execute(select(OutboxEvent.event_type, func.count(), func.max(OutboxEvent.created_at))
                      .where(OutboxEvent.status.in_(RETRYABLE_JOB_STATUSES), OutboxEvent.created_at > week)
                      .group_by(OutboxEvent.event_type)).all()
    mails = db.execute(select(func.count(), func.max(EmailDelivery.created_at))
                       .where(or_(EmailDelivery.status == "failed",
                                  EmailDelivery.provider_status.in_(("bounced", "complained", "failed"))),
                              EmailDelivery.created_at > day)).one()
    tel = db.execute(select(func.count(), func.max(TelephonyJob.updated_at), func.max(TelephonyJob.last_error))
                     .where(TelephonyJob.status == "failed", TelephonyJob.updated_at > week)).one()
    incidents = [{"kind": "integration", "source": c, "count": n, "since": _iso(at), "detail": (err or "")[:200],
                  "unit": "forbindelser"} for c, n, at, err in conns]
    incidents += [{"kind": "job", "source": t, "count": n, "since": _iso(at), "detail": "", "unit": "opgaver"} for t, n, at in jobs]
    if mails[0]:
        incidents.append({"kind": "email", "source": "e-mail", "count": mails[0], "since": _iso(mails[1]), "detail": "",
                          "unit": "e-mails"})
    if tel[0]:
        incidents.append({"kind": "telephony", "source": "telefoni-opsætning", "count": tel[0], "since": _iso(tel[1]),
                          "detail": (tel[2] or "")[:200], "unit": "jobs"})
    suspended = db.execute(select(Workspace.id, Workspace.name, Workspace.ops_suspended_at, Workspace.ops_suspended_reason,
                                  User.email).outerjoin(User, User.id == Workspace.ops_suspended_by)
                           .where(Workspace.ops_suspended_at.is_not(None)).order_by(desc(Workspace.ops_suspended_at))).all()
    names = _names(db, {e.workspace_id for e in failed_jobs} | {b.workspace_id for b in sync_failed}
                   | {c.workspace_id for c in problem_calls} | {w for w, _, _ in ical})
    return {
        "failed_jobs": [_job_out(e, names) for e in failed_jobs],
        "calls": {
            "last_24h": {"total": sum(by_dir.values()), "inbound": by_dir.get("inbound", 0), "outbound": by_dir.get("outbound", 0)},
            "problems": [{"id": str(c.id), "workspace_id": str(c.workspace_id),
                          "workspace_name": (names.get(str(c.workspace_id)) or {}).get("name"), "direction": c.direction,
                          "at": _iso(c.started_at or c.created_at), "ended_reason": c.ended_reason,
                          "transcript_status": c.transcript_status, "recording_status": c.recording_status,
                          "from": _mask(c.from_number)} for c in problem_calls],
        },
        "calendar_sync": {
            "failed": [_booking_out(b, names) for b in sync_failed],
            "pending_confirmation": pending,
            "ical_errors": [{"workspace_id": str(w), "workspace_name": (names.get(str(w)) or {}).get("name"), "error": err,
                             "synced_at": _iso(at)} for w, err, at in ical],
        },
        "incidents": sorted(incidents, key=lambda x: x["since"] or "", reverse=True),
        "suspended": [{"workspace_id": str(i), "workspace_name": n, "since": _iso(at), "reason": r, "by": by}
                      for i, n, at, r, by in suspended],
    }


# --------------------------------------------------------------------------- controlled retry

class RetryIn(BaseModel):
    note: str = Field(default="", max_length=300)


class CalendarRetryIn(RetryIn):
    # Required when the last write timed out (outcome «unknown»): the operator has looked in the calendar and the
    # event is not there.
    confirm_not_created: bool = False


def _guard(db: OrmSession, principal: Principal, endpoint: str, key: str | None, payload: dict) -> IdempotencyGuard:
    return IdempotencyGuard(db, scope_for(principal.user.id, endpoint), key, payload)


@router.post("/jobs/{job_id}/retry")
def retry_job(job_id: uuid.UUID, request: Request, response: Response, body: RetryIn | None = None,
              db: OrmSession = Depends(get_db), principal: Principal = Depends(operator),
              idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")):
    """Give one failed job exactly one more attempt. Idempotent: an already queued job is left alone."""
    body = body or RetryIn()
    guard = _guard(db, principal, f"ops.job_retry.{job_id}", idempotency_key, body.model_dump())
    if guard.replay:
        response.status_code = guard.replay[0]
        return guard.replay[1]
    ev = db.scalar(select(OutboxEvent).where(OutboxEvent.id == job_id).with_for_update())
    if ev is None:
        raise NotFound("Opgaven findes ikke")
    names = _names(db, {ev.workspace_id})
    if ev.status in ("queued", "processing"):
        out = {"result": "already_queued", "job": _job_out(ev, names)}
    elif ev.status == "done":
        raise Conflict("Opgaven er allerede udført og køres ikke igen", code="job_done")
    elif is_suspended(db, ev.workspace_id):
        raise Conflict("Kunden er sat på pause. Genoptag kunden, før opgaven køres igen", code="workspace_suspended")
    else:
        before = {"status": ev.status, "attempts": ev.attempts, "max_attempts": ev.max_attempts, "error": (ev.last_error or "")[:300]}
        ev.status, ev.next_attempt_at = "queued", _now()
        ev.max_attempts = ev.attempts + 1  # exactly one more attempt; a new failure leaves it «failed» again
        ev.lease_owner = ev.lease_expires_at = None
        record_audit(db, workspace_id=ev.workspace_id, actor_user_id=principal.user.id, action="operator.ops.job_retry",
                     object_type="outbox_event", object_id=ev.id, before=before,
                     after={"status": "queued", "type": ev.event_type, "note": body.note},
                     request_id=request.state.request_id)
        db.flush()
        out = {"result": "queued", "job": _job_out(ev, names)}
    guard.store(200, out)
    db.commit()
    return out


@router.post("/bookings/{booking_id}/calendar-retry")
def retry_calendar(booking_id: uuid.UUID, request: Request, response: Response, body: CalendarRetryIn | None = None,
                   db: OrmSession = Depends(get_db), principal: Principal = Depends(operator),
                   idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")):
    """Write a booking to its calendar once more: update when the event exists, create when it was not created,
    refuse (409 calendar_outcome_unknown) when the last attempt timed out and the operator has not confirmed."""
    from app.modules.integrations.connectors import calendar

    body = body or CalendarRetryIn()
    guard = _guard(db, principal, f"ops.calendar_retry.{booking_id}", idempotency_key, body.model_dump())
    if guard.replay:
        response.status_code = guard.replay[0]
        return guard.replay[1]
    b = db.scalar(select(Booking).where(Booking.id == booking_id).with_for_update())
    if b is None:
        raise NotFound("Aftalen findes ikke")
    names = _names(db, {b.workspace_id})
    if b.calendar_sync != "failed":
        out = {"result": "already_synced" if b.calendar_sync == "synced" else "nothing_to_do", "booking": _booking_out(b, names)}
        guard.store(200, out)
        db.commit()
        return out
    if is_suspended(db, b.workspace_id):
        raise Conflict("Kunden er sat på pause. Genoptag kunden, før kalenderen skrives igen", code="workspace_suspended")
    outcome = calendar_outcome(b)
    if outcome == "unknown" and not body.confirm_not_created:
        raise Conflict("Sidste forsøg fik intet svar fra kalenderen, så aftalen kan allerede stå der. Se efter i kundens "
                       "kalender, og bekræft at den ikke findes, før den skrives igen", code="calendar_outcome_unknown")
    before = {"calendar_sync": b.calendar_sync, "error": b.calendar_sync_error, "outcome": outcome}
    if b.status == "cancelled":
        calendar.mirror_cancel(db, b.workspace_id, b)
    else:
        calendar.mirror_update(db, b.workspace_id, b)  # event id → update; none → create (once)
    result = "synced" if b.calendar_sync == "synced" else "failed"
    record_audit(db, workspace_id=b.workspace_id, actor_user_id=principal.user.id, action="operator.ops.calendar_retry",
                 object_type="booking", object_id=b.id, before=before,
                 after={"calendar_sync": b.calendar_sync, "error": b.calendar_sync_error, "result": result,
                        "confirm_not_created": body.confirm_not_created, "note": body.note},
                 request_id=request.state.request_id)
    db.flush()
    out = {"result": result, "booking": _booking_out(b, names)}
    guard.store(200, out)
    db.commit()
    return out


# --------------------------------------------------------------------------- suspension

class SuspendIn(BaseModel):
    reason: str = Field(min_length=3, max_length=300)


class ResumeIn(BaseModel):
    note: str = Field(default="", max_length=300)


def _ws_out(w: Workspace) -> dict:
    return {"workspace_id": str(w.id), "workspace_name": w.name, "suspended": w.ops_suspended_at is not None,
            "since": _iso(w.ops_suspended_at), "reason": w.ops_suspended_reason}


def _workspace(db: OrmSession, workspace_id: uuid.UUID) -> Workspace:
    w = db.scalar(select(Workspace).where(Workspace.id == workspace_id).with_for_update())
    if w is None:
        raise NotFound("Kunden findes ikke")
    return w


@router.post("/workspaces/{workspace_id}/suspend")
def suspend(workspace_id: uuid.UUID, body: SuspendIn, request: Request, db: OrmSession = Depends(get_db),
            principal: Principal = Depends(operator)):
    """Pause one tenant's outbound work. Suspending a suspended tenant changes nothing (and writes no audit row)."""
    w = _workspace(db, workspace_id)
    if w.ops_suspended_at is None:
        w.ops_suspended_at, w.ops_suspended_reason, w.ops_suspended_by = _now(), body.reason.strip(), principal.user.id
        record_audit(db, workspace_id=w.id, actor_user_id=principal.user.id, action="operator.ops.workspace_suspended",
                     object_type="workspace", object_id=w.id, before={"suspended": False},
                     after={"suspended": True, "reason": w.ops_suspended_reason}, request_id=request.state.request_id)
    db.commit()
    return _ws_out(w)


@router.post("/workspaces/{workspace_id}/resume")
def resume(workspace_id: uuid.UUID, request: Request, body: ResumeIn | None = None, db: OrmSession = Depends(get_db),
           principal: Principal = Depends(operator)):
    """Lift the pause: the waiting jobs and campaigns continue where they stopped."""
    w = _workspace(db, workspace_id)
    if w.ops_suspended_at is not None:
        before = {"suspended": True, "since": _iso(w.ops_suspended_at), "reason": w.ops_suspended_reason}
        w.ops_suspended_at = w.ops_suspended_reason = w.ops_suspended_by = None
        record_audit(db, workspace_id=w.id, actor_user_id=principal.user.id, action="operator.ops.workspace_resumed",
                     object_type="workspace", object_id=w.id, before=before,
                     after={"suspended": False, "note": (body.note if body else "")}, request_id=request.state.request_id)
    db.commit()
    return _ws_out(w)

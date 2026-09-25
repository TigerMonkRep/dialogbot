"""Outbox worker.

Run: `python -m app.worker.runner` (loop) or call `process_once()` from tests.

Guarantees:
- at-least-once delivery with a time-bounded lease; a crashed worker's job is
  re-picked once the lease expires (resume after process interruption);
- controlled retries with exponential backoff up to max_attempts, then `failed`;
- handlers are idempotent: side effects are keyed on the event id via unique
  constraints (e.g. email_deliveries.outbox_event_id), so redelivery never
  produces a second domain effect.
"""
from __future__ import annotations

import os
import socket
import time
import uuid
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import or_, select, text
from sqlalchemy.orm import Session as OrmSession

from app.config import get_settings
from app.core.logging import configure_logging
from app.db import get_session_factory
from app.models import EmailDelivery, OutboxEvent
from app.modules.integrations.email import OutgoingEmail, get_email_adapter

log = structlog.get_logger("dialogbot.worker")


class HandlerError(Exception):
    pass


def _now() -> datetime:
    return datetime.now(UTC)


# --- handlers ---------------------------------------------------------------


def _send_mail(db: OrmSession, ev: OutboxEvent, subject: str, body: str) -> None:
    if db.scalar(select(EmailDelivery).where(EmailDelivery.outbox_event_id == ev.id)) is not None:
        return  # already delivered for this event: redelivery is a no-op
    adapter = get_email_adapter()
    adapter.deliver(db, ev.id, OutgoingEmail(to_email=ev.payload["to_email"], subject=subject, body_text=body,
                                             workspace_id=ev.workspace_id))


def handle_invitation(db: OrmSession, ev: OutboxEvent) -> None:
    p = ev.payload
    _send_mail(db, ev, f"Du er inviteret til {p['workspace_name']} på Dialogbot",
               f"{p['invited_by']} har inviteret dig som {p['role']} i arbejdsrummet {p['workspace_name']}.\n"
               f"Acceptér her: {p['link']}\n\n(Simuleret udviklingsmail)")


def handle_verify(db: OrmSession, ev: OutboxEvent) -> None:
    _send_mail(db, ev, "Bekræft din e-mail hos Dialogbot",
               f"Bekræft din adresse: {ev.payload['link']}\n\n(Simuleret udviklingsmail)")


def handle_reset(db: OrmSession, ev: OutboxEvent) -> None:
    _send_mail(db, ev, "Nulstil din adgangskode hos Dialogbot",
               f"Nulstil her: {ev.payload['link']}\n\n(Simuleret udviklingsmail)")


def handle_new_lead(db: OrmSession, ev: OutboxEvent) -> None:
    p = ev.payload
    _send_mail(db, ev, f"Ny henvendelse til {p['workspace_name']}: {p['contact_name']}",
               f"{p['contact_name']} vil gerne kontaktes via jeres webchat.\n\n"
               f"Behov: {p['need_summary'] or '(ikke angivet)'}\n\nSe henvendelsen: {p['link']}")


def handle_knowledge_approved(db: OrmSession, ev: OutboxEvent) -> None:
    # Downstream consumers (script regeneration, embeddings) belong to later
    # stages. The event is acknowledged so the audit/outbox trail is complete.
    log.info("knowledge.version_approved", version_id=ev.payload.get("version_id"))


HANDLERS = {
    "email.invitation": handle_invitation,
    "email.verify_address": handle_verify,
    "email.password_reset": handle_reset,
    "knowledge.version_approved": handle_knowledge_approved,
    "email.new_lead": handle_new_lead,
}

# Test hook: event types listed here raise, to exercise retry paths.
FAIL_EVENT_TYPES: set[str] = set()


# --- processing --------------------------------------------------------------


def _worker_id() -> str:
    return f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:6]}"


def claim_one(db: OrmSession, worker_id: str) -> OutboxEvent | None:
    s = get_settings()
    now = _now()
    ev = db.scalar(
        select(OutboxEvent)
        .where(OutboxEvent.next_attempt_at <= now,
               or_(OutboxEvent.status == "queued",
                   (OutboxEvent.status == "processing") & (OutboxEvent.lease_expires_at < now)))
        .order_by(OutboxEvent.next_attempt_at)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    if ev is None:
        return None
    ev.status = "processing"
    ev.lease_owner = worker_id
    ev.lease_expires_at = now + timedelta(seconds=s.worker_lease_seconds)
    ev.attempts += 1
    db.commit()
    return ev


def finish(db: OrmSession, ev_id: uuid.UUID, *, error: str | None) -> None:
    ev = db.scalar(select(OutboxEvent).where(OutboxEvent.id == ev_id).with_for_update())
    if ev is None:
        return
    if error is None:
        ev.status = "done"
        ev.processed_at = _now()
        ev.last_error = None
    else:
        ev.last_error = error[:2000]
        if ev.attempts >= ev.max_attempts:
            ev.status = "failed"
        else:
            ev.status = "queued"
            ev.next_attempt_at = _now() + timedelta(seconds=min(300, 2 ** ev.attempts))
    ev.lease_owner = None
    ev.lease_expires_at = None
    db.commit()


def process_once(worker_id: str | None = None) -> OutboxEvent | None:
    """Claim and process a single event. Returns the event (post-state) or None."""
    worker_id = worker_id or _worker_id()
    factory = get_session_factory()
    with factory() as db:
        ev = claim_one(db, worker_id)
        if ev is None:
            return None
        ev_id, ev_type = ev.id, ev.event_type
    error: str | None = None
    with factory() as db:
        try:
            ev = db.get(OutboxEvent, ev_id)
            if ev_type in FAIL_EVENT_TYPES:
                raise HandlerError("simulated failure")
            handler = HANDLERS.get(ev_type)
            if handler is None:
                raise HandlerError(f"no handler for {ev_type}")
            handler(db, ev)
            db.commit()
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            error = f"{type(exc).__name__}: {exc}"
            log.warning("outbox.handler_failed", event_id=str(ev_id), event_type=ev_type, error=error)
    with factory() as db:
        finish(db, ev_id, error=error)
        return db.get(OutboxEvent, ev_id)


def drain(max_events: int = 1000) -> int:
    n = 0
    while n < max_events and process_once() is not None:
        n += 1
    return n


def main() -> None:
    s = get_settings()
    configure_logging(s.log_level)
    wid = _worker_id()
    log.info("worker.start", worker_id=wid, env=s.app_env)
    with get_session_factory()() as db:
        db.execute(text("select 1"))
    while True:
        ev = process_once(wid)
        if ev is None:
            time.sleep(s.worker_poll_seconds)
        else:
            log.info("outbox.processed", event_id=str(ev.id), event_type=ev.event_type, status=ev.status,
                     attempts=ev.attempts)


if __name__ == "__main__":
    main()

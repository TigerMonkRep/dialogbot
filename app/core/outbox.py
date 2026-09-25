"""Transactional outbox. Events are written in the same transaction as the
domain change; the worker (app/worker) delivers them at-least-once."""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import OutboxEvent


def enqueue(
    db: Session,
    *,
    event_type: str,
    dedupe_key: str,
    payload: dict,
    workspace_id: uuid.UUID | None = None,
) -> OutboxEvent:
    """Enqueue an event. A repeated dedupe_key returns the existing event."""
    existing = db.scalar(select(OutboxEvent).where(OutboxEvent.dedupe_key == dedupe_key))
    if existing is not None:
        return existing
    ev = OutboxEvent(
        event_type=event_type,
        dedupe_key=dedupe_key,
        payload=payload,
        workspace_id=workspace_id,
        max_attempts=get_settings().worker_max_attempts,
    )
    db.add(ev)
    db.flush()
    return ev

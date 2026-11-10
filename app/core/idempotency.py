"""Durable idempotency keys for effectful commands.

Usage in a route:
    with idempotent(db, user_id, "invitations.create", key, body) as replay:
        if replay: return replay
        ... perform command, return (status, dict) via replay.store(...)

Semantics:
- same scope + key + same payload hash  -> stored response is replayed
- same scope + key + different payload  -> 409 idempotency_payload_mismatch
- storage happens in the same transaction as the domain change
"""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.errors import Conflict
from app.models import IdempotencyKey


def payload_hash(payload: Any) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


IN_PROGRESS = 0  # response_status of a reserved key whose command has not stored its response yet
STALE_AFTER = timedelta(minutes=5)


class IdempotencyGuard:
    """Insert-first: the key is reserved with INSERT … ON CONFLICT DO NOTHING before the command runs. A concurrent
    request with the same key waits on the unique index until the first transaction ends, then finds the stored
    response (replay) – or, if the first is still running after committing part of its work, a 409 – never a 500
    from a unique violation (QA F-VR-03-X11). A rolled-back first request leaves no row, so the second proceeds."""

    def __init__(self, db: Session, scope: str, key: str | None, payload: Any):
        self.db = db
        self.scope = scope
        self.key = key
        self.hash = payload_hash(payload)
        self.replay: tuple[int, dict] | None = None
        self._row_id: uuid.UUID | None = None
        if not key:
            return
        self._row_id = db.execute(
            pg_insert(IdempotencyKey)
            .values(id=uuid.uuid4(), scope=scope, key=key, payload_hash=self.hash, response_status=IN_PROGRESS,
                    response_body={})
            .on_conflict_do_nothing(constraint="uq_idempotency_scope_key")
            .returning(IdempotencyKey.id)
        ).scalar()
        if self._row_id is not None:
            return
        existing = db.scalar(select(IdempotencyKey).where(IdempotencyKey.scope == scope, IdempotencyKey.key == key))
        if existing is None:  # the other request's reservation vanished in between (rolled back): not a duplicate
            return
        if existing.payload_hash != self.hash:
            raise Conflict("Idempotency-Key er allerede brugt med et andet payload", code="idempotency_payload_mismatch")
        if existing.response_status == IN_PROGRESS:
            created = existing.created_at if existing.created_at.tzinfo else existing.created_at.replace(tzinfo=UTC)
            if datetime.now(UTC) - created > STALE_AFTER:
                self._row_id = existing.id  # an abandoned reservation: this request takes it over
                return
            raise Conflict("Den samme handling er allerede i gang – vent et øjeblik", code="idempotency_in_progress")
        self.replay = (existing.response_status, existing.response_body)

    def store(self, status: int, body: dict) -> None:
        if not self.key:
            return
        row = self.db.get(IdempotencyKey, self._row_id) if self._row_id else None
        if row is None:
            self.db.add(IdempotencyKey(scope=self.scope, key=self.key, payload_hash=self.hash, response_status=status,
                                       response_body=body))
            return
        row.response_status, row.response_body = status, body


def scope_for(user_id: uuid.UUID, endpoint: str, workspace_id: uuid.UUID | None = None) -> str:
    return f"{user_id}:{workspace_id or '-'}:{endpoint}"

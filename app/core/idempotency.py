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
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import Conflict
from app.models import IdempotencyKey


def payload_hash(payload: Any) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class IdempotencyGuard:
    def __init__(self, db: Session, scope: str, key: str | None, payload: Any):
        self.db = db
        self.scope = scope
        self.key = key
        self.hash = payload_hash(payload)
        self.replay: tuple[int, dict] | None = None
        if key:
            existing = db.scalar(
                select(IdempotencyKey).where(IdempotencyKey.scope == scope, IdempotencyKey.key == key)
            )
            if existing is not None:
                if existing.payload_hash != self.hash:
                    raise Conflict(
                        "Idempotency-Key er allerede brugt med et andet payload",
                        code="idempotency_payload_mismatch",
                    )
                self.replay = (existing.response_status, existing.response_body)

    def store(self, status: int, body: dict) -> None:
        if not self.key:
            return
        self.db.add(
            IdempotencyKey(
                scope=self.scope, key=self.key, payload_hash=self.hash, response_status=status, response_body=body
            )
        )


def scope_for(user_id: uuid.UUID, endpoint: str, workspace_id: uuid.UUID | None = None) -> str:
    return f"{user_id}:{workspace_id or '-'}:{endpoint}"

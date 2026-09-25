from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.models import AuditLog


def record_audit(
    db: Session,
    *,
    workspace_id: uuid.UUID | None,
    actor_user_id: uuid.UUID | None,
    action: str,
    object_type: str,
    object_id: Any = None,
    before: dict | None = None,
    after: dict | None = None,
    request_id: str | None = None,
) -> AuditLog:
    """Append an audit entry in the caller's transaction. Never pass credentials."""
    entry = AuditLog(
        workspace_id=workspace_id,
        actor_user_id=actor_user_id,
        action=action,
        object_type=object_type,
        object_id=str(object_id) if object_id is not None else None,
        before=before,
        after=after,
        request_id=request_id,
    )
    db.add(entry)
    return entry

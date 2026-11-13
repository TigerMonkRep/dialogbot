"""Operator suspension of one tenant (M03).

A Dialogbot operator can pause a workspace's outbound work from the operations screen while a dependency incident is
investigated. While `workspaces.ops_suspended_at` is set:
- the outbox worker does not claim the workspace's queued jobs (they wait; nothing is dropped or re-created);
- the campaign dialler places no calls for it;
- actions in its connected systems (calendar, SMS, webhooks) are refused, so the assistant offers a follow-up instead;
- an operator retry of one of its jobs or calendar writes is refused.
Inbound calls and the web chat are still answered: callers are not punished for a provider incident.
Every other workspace is untouched (tests/test_ops_m03.py checks the isolation)."""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Workspace

SUSPENDED_MESSAGE = ("Forbindelserne til eksterne systemer er midlertidigt sat på pause. Lov ikke kunden noget – "
                     "tilbyd at en medarbejder følger op.")


def suspended_ids():
    """Subquery of suspended workspace ids, for `column.not_in(suspended_ids())`."""
    return select(Workspace.id).where(Workspace.ops_suspended_at.is_not(None))


def is_suspended(db: Session, workspace_id: uuid.UUID | None) -> bool:
    if workspace_id is None:
        return False
    return db.scalar(select(Workspace.ops_suspended_at).where(Workspace.id == workspace_id)) is not None

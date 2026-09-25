"""Authentication and workspace authorisation dependencies.

Rules enforced here (see docs/ADR-001):
- Identity comes from a valid, unexpired, unrevoked server-side session.
- Every workspace-scoped route resolves the caller's membership in the
  workspace named in the path. A submitted workspace_id alone is never proof.
- Objects are always looked up with both id and workspace_id; a foreign id
  yields 404 so that existence in other workspaces is not revealed.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, TypeVar

from fastapi import Depends, Header, Request
from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from app.core.errors import Forbidden, NotFound, Unauthenticated
from app.core.security import token_digest
from app.db import get_db
from app.models import ROLE_RANK, Membership, Session, User, Workspace

T = TypeVar("T")

# Permission matrix: minimum role for each capability.
PERMISSIONS: dict[str, str] = {
    "workspace.read": "reader",
    "profile.edit": "staff",
    "goals.edit": "staff",
    "languages.edit": "staff",
    "knowledge.read": "reader",
    "knowledge.draft": "staff",
    "knowledge.submit": "staff",
    "knowledge.approve": "admin",
    "setup.read": "reader",
    "setup.edit": "staff",
    "setup.run_check": "staff",
    "members.read": "reader",
    "members.invite": "admin",
    "members.change_role": "admin",
    "members.remove": "admin",
    "members.assign_owner": "owner",
    "audit.read": "admin",
    "agreements.edit": "owner",  # reserved for the billing stage
}


@dataclass
class Principal:
    user: User
    session: Session


@dataclass
class WorkspaceContext:
    principal: Principal
    workspace: Workspace
    membership: Membership

    @property
    def role(self) -> str:
        return self.membership.role

    @property
    def user_id(self) -> uuid.UUID:
        return self.principal.user.id

    def can(self, capability: str) -> bool:
        required = PERMISSIONS[capability]
        return ROLE_RANK[self.role] >= ROLE_RANK[required]

    def require(self, capability: str) -> None:
        if not self.can(capability):
            raise Forbidden(
                f"Handlingen kræver rollen '{PERMISSIONS[capability]}' eller højere",
                code="insufficient_role",
                extra={"required_role": PERMISSIONS[capability], "your_role": self.role},
            )


def _bearer(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    return token.strip()


def get_current_principal(
    request: Request,
    db: OrmSession = Depends(get_db),
    authorization: str | None = Header(default=None),
) -> Principal:
    token = _bearer(authorization)
    if not token:
        raise Unauthenticated("Login påkrævet")
    now = datetime.now(UTC)
    sess = db.scalar(select(Session).where(Session.token_hash == token_digest(token)))
    if sess is None or sess.revoked_at is not None or sess.expires_at <= now:
        raise Unauthenticated("Sessionen er ugyldig eller udløbet", code="session_invalid")
    user = db.get(User, sess.user_id)
    if user is None or not user.is_active:
        raise Unauthenticated("Brugeren er deaktiveret", code="user_inactive")
    sess.last_seen_at = now
    request.state.user_id = str(user.id)
    return Principal(user=user, session=sess)


def get_workspace_context(
    workspace_id: uuid.UUID,
    principal: Principal = Depends(get_current_principal),
    db: OrmSession = Depends(get_db),
) -> WorkspaceContext:
    membership = db.scalar(
        select(Membership).where(Membership.workspace_id == workspace_id, Membership.user_id == principal.user.id)
    )
    if membership is None:
        # Not a member: respond as if the workspace does not exist.
        raise NotFound("Arbejdsrummet findes ikke")
    workspace = db.get(Workspace, workspace_id)
    if workspace is None or workspace.status == "closed":
        raise NotFound("Arbejdsrummet findes ikke")
    return WorkspaceContext(principal=principal, workspace=workspace, membership=membership)


def require_capability(capability: str):
    def _dep(ctx: WorkspaceContext = Depends(get_workspace_context)) -> WorkspaceContext:
        ctx.require(capability)
        return ctx

    return _dep


def get_scoped(db: OrmSession, model: type[T], object_id: Any, workspace_id: uuid.UUID) -> T:
    """Fetch an object by id AND workspace. Cross-workspace ids are 404."""
    obj = db.scalar(select(model).where(model.id == object_id, model.workspace_id == workspace_id))  # type: ignore[attr-defined]
    if obj is None:
        raise NotFound("Objektet findes ikke")
    return obj

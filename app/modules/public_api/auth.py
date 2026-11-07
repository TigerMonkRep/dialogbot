"""Authentication for api.dialogbot.app/v1: `Authorization: Bearer dbk_…`.

- 401 `unauthenticated`: no bearer token. 401 `api_key_invalid`: unknown, revoked or expired key, or a closed
  workspace. Nothing in the answer says which.
- 403 `insufficient_scope`: the key is valid but does not carry the scope the route needs (`required_scope` is in the
  body so the integrator knows what to ask the owner for).
- 404: the workspace id in the path is not the key's workspace. A key is bound to one workspace; other workspaces
  do not exist from its point of view (the same rule sessions follow in app.core.auth).
- Approval-first: public keys never act as a role. They cannot approve, publish or set a status; writes land as
  proposals or on safe lists (do-not-call), see docs/public-api.md.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session as OrmSession

from app.core.errors import Forbidden, NotFound, Unauthenticated
from app.db import get_db
from app.models import ApiKey, Workspace
from app.modules.public_api import keys

LAST_USED_GRANULARITY = timedelta(seconds=60)  # one UPDATE per key per minute, not per request

bearer = HTTPBearer(auto_error=False, scheme_name="ApiKey",
                    description="API-nøgle fra Integrationer → API-nøgler i appen: `Authorization: Bearer dbk_live_…`")


@dataclass
class PublicPrincipal:
    key: ApiKey
    workspace: Workspace

    @property
    def scopes(self) -> frozenset[str]:
        return frozenset(self.key.scopes or ())

    @property
    def workspace_id(self) -> uuid.UUID:
        return self.workspace.id

    def has(self, scope: str) -> bool:
        return scope in self.scopes

    def require(self, scope: str) -> None:
        if not self.has(scope):
            raise Forbidden(f"Nøglen mangler scopet '{scope}'", code="insufficient_scope",
                            extra={"required_scope": scope})

    @property
    def idempotency_scope(self) -> str:
        return f"api:{self.key.id}"


def get_public_principal(request: Request, db: OrmSession = Depends(get_db),
                         credentials: HTTPAuthorizationCredentials | None = Depends(bearer)) -> PublicPrincipal:
    token = (credentials.credentials or "").strip() if credentials else ""
    if not token:
        raise Unauthenticated("API-nøgle påkrævet: Authorization: Bearer dbk_…")
    if not token.startswith("dbk_"):
        raise Unauthenticated("Ugyldig API-nøgle", code="api_key_invalid")
    key = keys.find_by_token(db, token)
    now = datetime.now(UTC)
    if key is None or key.revoked_at is not None or (key.expires_at is not None and key.expires_at <= now):
        raise Unauthenticated("Ugyldig API-nøgle", code="api_key_invalid")
    ws = db.get(Workspace, key.workspace_id)
    if ws is None or ws.status != "active":
        raise Unauthenticated("Ugyldig API-nøgle", code="api_key_invalid")
    if key.last_used_at is None or now - key.last_used_at >= LAST_USED_GRANULARITY:
        key.last_used_at = now
        db.commit()
    request.state.api_key_id = str(key.id)
    return PublicPrincipal(key=key, workspace=ws)


def get_workspace_principal(workspace_id: uuid.UUID,
                            principal: PublicPrincipal = Depends(get_public_principal)) -> PublicPrincipal:
    """Business routes: the path's workspace must be the key's, and it must be a business workspace."""
    if principal.workspace.id != workspace_id or principal.workspace.kind != "business":
        raise NotFound("Arbejdsrummet findes ikke")
    return principal


def require_scope(scope: str):
    def _dep(principal: PublicPrincipal = Depends(get_workspace_principal)) -> PublicPrincipal:
        principal.require(scope)
        return principal

    return _dep

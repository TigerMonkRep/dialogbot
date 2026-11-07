"""Issuing, listing and revoking API keys. Used by the internal management endpoints (owner/admin in the app) and
by the public auth dependency (lookup by digest)."""
from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session as OrmSession

from app.core.audit import record_audit
from app.core.errors import Conflict, NotFound, ValidationFailed
from app.core.security import token_digest
from app.models import ApiKey, Workspace
from app.modules.public_api import scopes as scope_catalogue

MAX_ACTIVE_PER_WORKSPACE = 2
MAX_EXPIRES_DAYS = 3650


def new_plaintext(environment: str) -> str:
    """`dbk_live_<43 url-safe chars>` – 256 random bits from the OS CSPRNG."""
    return f"dbk_{environment}_" + secrets.token_urlsafe(32)


def active_count(db: OrmSession, workspace_id: uuid.UUID) -> int:
    return db.scalar(select(func.count()).select_from(ApiKey).where(ApiKey.workspace_id == workspace_id,
                                                                    ApiKey.revoked_at.is_(None))) or 0


def issue(db: OrmSession, workspace: Workspace, *, name: str, scopes: list[str], environment: str,
          expires_in_days: int | None, created_by: uuid.UUID | None, can, request_id: str | None) -> tuple[ApiKey, str]:
    """Create a key. Returns (row, plaintext) – the plaintext exists only in this return value.

    `can(capability)` is the issuer's own permission check: a scope is only granted when the issuer could do the
    same thing in the app."""
    if environment not in ("live", "test"):
        raise ValidationFailed("environment skal være live eller test", field_errors=[{"field": "environment"}])
    try:
        granted = scope_catalogue.validate(workspace.kind, scopes)
    except ValueError as e:
        raise ValidationFailed(f"Ukendt scope: {e}", field_errors=[{"field": "scopes"}]) from e
    if not granted:
        raise ValidationFailed("Vælg mindst ét scope", field_errors=[{"field": "scopes"}])
    catalogue = scope_catalogue.scopes_for(workspace.kind)
    refused = [s for s in granted if not can(catalogue[s].capability)]
    if refused:
        raise ValidationFailed("Du kan ikke give et scope, du ikke selv har rettighed til: " + ", ".join(refused),
                               code="scope_not_allowed", field_errors=[{"field": "scopes"}])
    db.scalar(select(Workspace).where(Workspace.id == workspace.id).with_for_update())  # serialises the limit check
    if active_count(db, workspace.id) >= MAX_ACTIVE_PER_WORKSPACE:
        raise Conflict(f"Der kan højst være {MAX_ACTIVE_PER_WORKSPACE} aktive nøgler pr. arbejdsrum – tilbagekald en først",
                       code="api_key_limit", extra={"max_active": MAX_ACTIVE_PER_WORKSPACE})
    expires_at = None
    if expires_in_days is not None:
        if not 1 <= expires_in_days <= MAX_EXPIRES_DAYS:
            raise ValidationFailed("expires_in_days skal være mellem 1 og 3650", field_errors=[{"field": "expires_in_days"}])
        expires_at = datetime.now(UTC) + timedelta(days=expires_in_days)
    plaintext = new_plaintext(environment)
    key = ApiKey(workspace_id=workspace.id, name=name.strip()[:120], prefix=f"dbk_{environment}_", last4=plaintext[-4:],
                 token_hash=token_digest(plaintext), scopes=granted, created_by=created_by, expires_at=expires_at)
    db.add(key)
    db.flush()
    record_audit(db, workspace_id=workspace.id, actor_user_id=created_by, action="api_key.created", object_type="api_key",
                 object_id=key.id, after={"name": key.name, "prefix": key.prefix, "last4": key.last4, "scopes": granted,
                                          "expires_at": expires_at.isoformat() if expires_at else None},
                 request_id=request_id)
    return key, plaintext


def list_keys(db: OrmSession, workspace_id: uuid.UUID) -> list[ApiKey]:
    return list(db.scalars(select(ApiKey).where(ApiKey.workspace_id == workspace_id)
                           .order_by(ApiKey.created_at.desc(), ApiKey.id.desc())))


def revoke(db: OrmSession, workspace_id: uuid.UUID, key_id: uuid.UUID, *, revoked_by: uuid.UUID | None,
           request_id: str | None) -> ApiKey:
    key = db.scalar(select(ApiKey).where(ApiKey.id == key_id, ApiKey.workspace_id == workspace_id).with_for_update())
    if key is None:
        raise NotFound("Nøglen findes ikke")
    if key.revoked_at is None:
        key.revoked_at = datetime.now(UTC)
        key.revoked_by = revoked_by
        record_audit(db, workspace_id=workspace_id, actor_user_id=revoked_by, action="api_key.revoked",
                     object_type="api_key", object_id=key.id, after={"name": key.name, "last4": key.last4},
                     request_id=request_id)
    return key


def find_by_token(db: OrmSession, token: str) -> ApiKey | None:
    return db.scalar(select(ApiKey).where(ApiKey.token_hash == token_digest(token)))


def public_view(key: ApiKey) -> dict:
    """What the app and the public `GET /v1/me` show. Never the digest."""
    now = datetime.now(UTC)
    if key.revoked_at is not None:
        status = "revoked"
    elif key.expires_at is not None and key.expires_at <= now:
        status = "expired"
    else:
        status = "active"
    return {"id": str(key.id), "name": key.name, "prefix": key.prefix, "last4": key.last4, "scopes": list(key.scopes),
            "status": status, "created_at": key.created_at.isoformat(),
            "expires_at": key.expires_at.isoformat() if key.expires_at else None,
            "last_used_at": key.last_used_at.isoformat() if key.last_used_at else None,
            "revoked_at": key.revoked_at.isoformat() if key.revoked_at else None}

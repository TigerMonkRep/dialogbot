"""API-key management inside the internal API (the app's Integrationer page and Privat's Konto page).

Business: `/workspaces/{id}/api-keys` – admin or owner. Privat: `/privat/api-keys` – the caller's own personal
workspace (no workspace id in the path, as everywhere in app/modules/privat). The plaintext key is in the creation
response only; a replay of the same Idempotency-Key does not return it again.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Header, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session as OrmSession

from app.core.auth import WorkspaceContext, get_workspace_context
from app.core.idempotency import IdempotencyGuard, scope_for
from app.db import get_db
from app.modules.privat.deps import PrivateCtx, private_ctx
from app.modules.public_api import keys, scopes

router = APIRouter(tags=["api-keys"])


class ApiKeyCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=120, description="Hvad nøglen bruges til, fx 'CRM-sync'")
    scopes: list[str] = Field(min_length=1, max_length=32)
    environment: str = Field(default="live", description="live | test – vælger præfikset dbk_live_ / dbk_test_")
    expires_in_days: int | None = Field(default=None, ge=1, le=keys.MAX_EXPIRES_DAYS)


class ApiKeyOut(BaseModel):
    id: str
    name: str
    prefix: str
    last4: str
    scopes: list[str]
    status: str
    created_at: str
    expires_at: str | None
    last_used_at: str | None
    revoked_at: str | None


class ApiKeyCreatedOut(ApiKeyOut):
    key: str | None = Field(description="Den fulde nøgle. Vises kun her – gem den straks.")


class ScopeOut(BaseModel):
    name: str
    description: str
    write: bool


def _catalogue(kind: str) -> list[ScopeOut]:
    return [ScopeOut(name=s.name, description=s.description, write=s.write) for s in scopes.scopes_for(kind).values()]


def _create(db: OrmSession, request: Request, *, workspace, body: ApiKeyCreateIn, user_id: uuid.UUID, can,
            idem_key: str | None) -> Response | dict:
    guard = IdempotencyGuard(db, scope_for(user_id, "api_keys.create", workspace.id), idem_key, body.model_dump())
    if guard.replay:
        st, replay_body = guard.replay
        return Response(content=ApiKeyCreatedOut(**replay_body, key=None).model_dump_json(), status_code=st,
                        media_type="application/json")
    key, plaintext = keys.issue(db, workspace, name=body.name, scopes=body.scopes, environment=body.environment,
                                expires_in_days=body.expires_in_days, created_by=user_id, can=can,
                                request_id=getattr(request.state, "request_id", None))
    view = keys.public_view(key)
    guard.store(201, view)  # the stored replay never contains the plaintext
    db.commit()
    return {**view, "key": plaintext}


# --------------------------------------------------------------------------- business workspaces

@router.get("/workspaces/{workspace_id}/api-keys/scopes", response_model=list[ScopeOut])
def business_scopes(ctx: WorkspaceContext = Depends(get_workspace_context)):
    ctx.require("api_keys.manage")
    return _catalogue(ctx.workspace.kind)


@router.get("/workspaces/{workspace_id}/api-keys", response_model=list[ApiKeyOut])
def business_list(ctx: WorkspaceContext = Depends(get_workspace_context), db: OrmSession = Depends(get_db)):
    ctx.require("api_keys.manage")
    return [keys.public_view(k) for k in keys.list_keys(db, ctx.workspace.id)]


@router.post("/workspaces/{workspace_id}/api-keys", status_code=status.HTTP_201_CREATED, response_model=ApiKeyCreatedOut)
def business_create(body: ApiKeyCreateIn, request: Request, ctx: WorkspaceContext = Depends(get_workspace_context),
                    db: OrmSession = Depends(get_db), idempotency_key: str | None = Header(default=None)):
    ctx.require("api_keys.manage")
    return _create(db, request, workspace=ctx.workspace, body=body, user_id=ctx.user_id, can=ctx.can,
                   idem_key=idempotency_key)


@router.delete("/workspaces/{workspace_id}/api-keys/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
def business_revoke(key_id: uuid.UUID, request: Request, ctx: WorkspaceContext = Depends(get_workspace_context),
                    db: OrmSession = Depends(get_db)):
    ctx.require("api_keys.manage")
    keys.revoke(db, ctx.workspace.id, key_id, revoked_by=ctx.user_id, request_id=getattr(request.state, "request_id", None))
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --------------------------------------------------------------------------- Dialogbot Privat (personal workspace)

@router.get("/privat/api-keys/scopes", response_model=list[ScopeOut])
def privat_scopes(ctx: PrivateCtx = Depends(private_ctx)):
    return _catalogue(ctx.workspace.kind)


@router.get("/privat/api-keys", response_model=list[ApiKeyOut])
def privat_list(ctx: PrivateCtx = Depends(private_ctx), db: OrmSession = Depends(get_db)):
    return [keys.public_view(k) for k in keys.list_keys(db, ctx.ws_id)]


@router.post("/privat/api-keys", status_code=status.HTTP_201_CREATED, response_model=ApiKeyCreatedOut)
def privat_create(body: ApiKeyCreateIn, request: Request, ctx: PrivateCtx = Depends(private_ctx),
                  db: OrmSession = Depends(get_db), idempotency_key: str | None = Header(default=None)):
    # The personal workspace has exactly one member, its owner: every personal scope is theirs to give.
    return _create(db, request, workspace=ctx.workspace, body=body, user_id=ctx.user_id, can=lambda _cap: True,
                   idem_key=idempotency_key)


@router.delete("/privat/api-keys/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
def privat_revoke(key_id: uuid.UUID, request: Request, ctx: PrivateCtx = Depends(private_ctx),
                  db: OrmSession = Depends(get_db)):
    keys.revoke(db, ctx.ws_id, key_id, revoked_by=ctx.user_id, request_id=getattr(request.state, "request_id", None))
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)

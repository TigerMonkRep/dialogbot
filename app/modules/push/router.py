"""Web Push subscriptions for the business PWA (internal API, session login).

`POST /push/subscriptions` {endpoint, keys{p256dh, auth}, audience: "erhverv", workspace_id} – the caller must be a
member of the workspace; `DELETE /push/subscriptions` {endpoint} removes the caller's own subscription. The VAPID
public key is at `GET /push/public-key`. Without VAPID keys on the server every route answers 501 push_not_configured.
"""
from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from app.core.auth import Principal, get_current_principal
from app.core.errors import NotFound
from app.db import get_db
from app.models import Membership, Workspace
from app.modules.push import service

router = APIRouter(prefix="/push", tags=["push"])


class WorkspacePushKeys(BaseModel):
    p256dh: str = Field(min_length=10, max_length=200)
    auth: str = Field(min_length=8, max_length=100)


class WorkspacePushSubIn(BaseModel):
    endpoint: str = Field(min_length=10, max_length=2000)
    keys: WorkspacePushKeys
    audience: Literal["erhverv"] = "erhverv"
    workspace_id: uuid.UUID


class WorkspacePushUnsubIn(BaseModel):
    endpoint: str = Field(min_length=10, max_length=2000)


def _member_workspace(db: OrmSession, user_id: uuid.UUID, workspace_id: uuid.UUID) -> Workspace:
    m = db.scalar(select(Membership).where(Membership.workspace_id == workspace_id, Membership.user_id == user_id))
    ws = db.get(Workspace, workspace_id) if m is not None else None
    if ws is None or ws.status == "closed" or ws.kind != "business":
        raise NotFound("Arbejdsrummet findes ikke")
    return ws


@router.get("/public-key")
def push_public_key(principal: Principal = Depends(get_current_principal)):
    return {"public_key": service.public_key()}


@router.post("/subscriptions")
def push_subscribe(body: WorkspacePushSubIn, request: Request, principal: Principal = Depends(get_current_principal),
                   db: OrmSession = Depends(get_db)):
    service.public_key()  # 501 push_not_configured without VAPID keys
    ws = _member_workspace(db, principal.user.id, body.workspace_id)
    sub = service.subscribe(db, principal.user.id, ws.id, endpoint=body.endpoint, p256dh=body.keys.p256dh,
                            auth=body.keys.auth, user_agent=request.headers.get("user-agent"))
    db.commit()
    return {"id": str(sub.id), "workspace_id": str(ws.id), "audience": service.AUDIENCE}


@router.delete("/subscriptions")
def push_unsubscribe(body: WorkspacePushUnsubIn, principal: Principal = Depends(get_current_principal),
                     db: OrmSession = Depends(get_db)):
    removed = service.unsubscribe(db, principal.user.id, body.endpoint)
    db.commit()
    return {"removed": removed}

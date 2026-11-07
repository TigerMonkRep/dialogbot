from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from app.core.auth import get_scoped
from app.db import get_db
from app.models import Call
from app.modules.public_api import cursor
from app.modules.public_api.auth import PublicPrincipal, require_scope
from app.modules.public_api.schemas import v1

router = APIRouter(prefix="/workspaces/{workspace_id}", tags=["calls"])


@router.get("/calls", response_model=v1.Page[v1.Call], summary="Opkald, nyeste først")
def list_calls(p: cursor.CursorParams = Depends(),
               since: datetime | None = Query(default=None, description="Kun opkald startet efter (ISO 8601)"),
               until: datetime | None = Query(default=None, description="Kun opkald startet før"),
               direction: str | None = Query(default=None, pattern="^(inbound|outbound)$"),
               principal: PublicPrincipal = Depends(require_scope("calls:read")), db: OrmSession = Depends(get_db)):
    q = select(Call).where(Call.workspace_id == principal.workspace_id)
    if since is not None:
        q = q.where(Call.created_at >= since)
    if until is not None:
        q = q.where(Call.created_at < until)
    if direction:
        q = q.where(Call.direction == direction)
    rows = list(db.scalars(cursor.apply(q, p, Call.created_at, Call.id)))
    reveal = principal.has("contacts:read")
    return cursor.page(rows, p, lambda c: c.created_at, lambda c: c.id, lambda c: v1.call_out(c, reveal))


@router.get("/calls/{call_id}", response_model=v1.Call, summary="Ét opkald")
def get_call(call_id: uuid.UUID, principal: PublicPrincipal = Depends(require_scope("calls:read")),
             db: OrmSession = Depends(get_db)) -> v1.Call:
    return v1.call_out(get_scoped(db, Call, call_id, principal.workspace_id), principal.has("contacts:read"))

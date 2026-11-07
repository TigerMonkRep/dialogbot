from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from app.core.auth import get_scoped
from app.db import get_db
from app.models import Lead
from app.modules.public_api import cursor
from app.modules.public_api.auth import PublicPrincipal, require_scope
from app.modules.public_api.schemas import v1

router = APIRouter(prefix="/workspaces/{workspace_id}", tags=["leads"])


@router.get("/leads", response_model=v1.Page[v1.Lead], summary="Henvendelser, nyeste først")
def list_leads(p: cursor.CursorParams = Depends(),
               since: datetime | None = Query(default=None, description="Oprettet efter (ISO 8601)"),
               pipeline_status: str | None = Query(default=None, pattern="^(new|contacted|won|lost)$"),
               qualification_status: str | None = Query(default=None, pattern="^(unqualified|qualified|disqualified)$"),
               principal: PublicPrincipal = Depends(require_scope("leads:read")), db: OrmSession = Depends(get_db)):
    q = select(Lead).where(Lead.workspace_id == principal.workspace_id)
    if since is not None:
        q = q.where(Lead.created_at >= since)
    if pipeline_status:
        q = q.where(Lead.pipeline_status == pipeline_status)
    if qualification_status:
        q = q.where(Lead.qualification_status == qualification_status)
    rows = list(db.scalars(cursor.apply(q, p, Lead.created_at, Lead.id)))
    reveal = principal.has("contacts:read")
    return cursor.page(rows, p, lambda x: x.created_at, lambda x: x.id, lambda x: v1.lead_out(x, reveal))


@router.get("/leads/{lead_id}", response_model=v1.Lead, summary="Én henvendelse")
def get_lead(lead_id: uuid.UUID, principal: PublicPrincipal = Depends(require_scope("leads:read")),
             db: OrmSession = Depends(get_db)) -> v1.Lead:
    return v1.lead_out(get_scoped(db, Lead, lead_id, principal.workspace_id), principal.has("contacts:read"))

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from app.core.errors import NotFound
from app.db import get_db
from app.models import KnowledgeItem, KnowledgeVersion
from app.modules.public_api.auth import PublicPrincipal, require_scope
from app.modules.public_api.schemas import v1

router = APIRouter(prefix="/workspaces/{workspace_id}", tags=["knowledge"])


@router.get("/knowledge", response_model=v1.Page[v1.KnowledgeItem],
            summary="Den godkendte viden (kun aktive, godkendte versioner af offentlig viden)")
def list_knowledge(kind: str | None = Query(default=None, max_length=32),
                   principal: PublicPrincipal = Depends(require_scope("knowledge:read")), db: OrmSession = Depends(get_db)):
    q = (select(KnowledgeItem, KnowledgeVersion).join(KnowledgeVersion, KnowledgeVersion.item_id == KnowledgeItem.id)
         .where(KnowledgeItem.workspace_id == principal.workspace_id, KnowledgeVersion.status == "approved",
                KnowledgeItem.archived_at.is_(None), KnowledgeVersion.audience == "public"))
    if kind:
        q = q.where(KnowledgeItem.kind == kind)
    rows = db.execute(q.order_by(KnowledgeItem.kind, KnowledgeItem.key)).all()
    return {"items": [v1.knowledge_out(i, v) for i, v in rows], "next_cursor": None}


@router.get("/knowledge/{item_id}", response_model=v1.KnowledgeItem, summary="Ét vidensemne (den godkendte version)")
def get_knowledge(item_id: uuid.UUID, principal: PublicPrincipal = Depends(require_scope("knowledge:read")),
                  db: OrmSession = Depends(get_db)) -> v1.KnowledgeItem:
    row = db.execute(select(KnowledgeItem, KnowledgeVersion)
                     .join(KnowledgeVersion, KnowledgeVersion.item_id == KnowledgeItem.id)
                     .where(KnowledgeItem.id == item_id, KnowledgeItem.workspace_id == principal.workspace_id,
                            KnowledgeVersion.status == "approved", KnowledgeItem.archived_at.is_(None),
                            KnowledgeVersion.audience == "public")).first()
    if row is None:
        raise NotFound("Objektet findes ikke")
    return v1.knowledge_out(row[0], row[1])

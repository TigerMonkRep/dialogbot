"""Operator: the wishes («ønsker») customers gave the assistant that Dialogbot cannot do yet, across all workspaces.

Only Dialogbot platform operators (`is_platform_operator`) may call these. Operators set a status (new → planned →
done, or declined) and a note; every change is audited on the customer's workspace."""
from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session as OrmSession

from app.core.audit import record_audit
from app.core.auth import Principal
from app.core.errors import NotFound, ValidationFailed
from app.db import get_db
from app.models import ASSISTANT_REQUEST_CATEGORIES, ASSISTANT_REQUEST_STATUSES, AssistantRequest, User, Workspace
from app.modules.assistant import requests as wishes
from app.modules.voices.operator_router import operator

router = APIRouter(prefix="/operator/assistant/requests", tags=["assistant-operator"])


def _filters(status: str | None, category: str | None, workspace_id: uuid.UUID | None, q: str | None) -> list:
    conds = []
    if status:
        if status not in ASSISTANT_REQUEST_STATUSES:
            raise ValidationFailed("Ukendt status", field_errors=[{"field": "status"}])
        conds.append(AssistantRequest.status == status)
    if category:
        if category not in ASSISTANT_REQUEST_CATEGORIES:
            raise ValidationFailed("Ukendt kategori", field_errors=[{"field": "category"}])
        conds.append(AssistantRequest.category == category)
    if workspace_id:
        conds.append(AssistantRequest.workspace_id == workspace_id)
    if q and q.strip():
        like = f"%{q.strip()[:100]}%"
        conds.append(or_(AssistantRequest.text.ilike(like), AssistantRequest.summary.ilike(like),
                         AssistantRequest.admin_note.ilike(like)))
    return conds


@router.get("")
def list_requests(status: str | None = None, category: str | None = None, workspace_id: uuid.UUID | None = None,
                  q: str | None = Query(default=None, max_length=100), limit: int = Query(default=100, ge=1, le=500),
                  offset: int = Query(default=0, ge=0), _: Principal = Depends(operator), db: OrmSession = Depends(get_db)):
    """Newest activity first, with counts per status and per category (the counts ignore the status/category filter
    so the page can show them as tabs)."""
    conds = _filters(status, category, workspace_id, q)
    rows = db.execute(
        select(AssistantRequest, Workspace.name, User.email, User.display_name)
        .join(Workspace, Workspace.id == AssistantRequest.workspace_id)
        .outerjoin(User, User.id == AssistantRequest.user_id)
        .where(*conds).order_by(AssistantRequest.updated_at.desc()).limit(limit).offset(offset)).all()
    total = db.scalar(select(func.count()).select_from(AssistantRequest).where(*conds)) or 0
    base = _filters(None, None, workspace_id, q)
    by_status = dict(db.execute(select(AssistantRequest.status, func.count()).where(*base).group_by(AssistantRequest.status)).all())
    open_ = base + [AssistantRequest.status.in_(wishes.OPEN)]
    by_category = dict(db.execute(select(AssistantRequest.category, func.count()).where(*open_)
                                  .group_by(AssistantRequest.category)).all())
    return {
        "items": [wishes.out(r, workspace_name=name, user=(email, dname) if email else None) for r, name, email, dname in rows],
        "total": total,
        "counts": {"status": {s: by_status.get(s, 0) for s in ASSISTANT_REQUEST_STATUSES},
                   "category_open": {c: by_category.get(c, 0) for c in ASSISTANT_REQUEST_CATEGORIES}},
        "categories": wishes.CATEGORY_DA,
    }


class RequestPatch(BaseModel):
    status: Literal["new", "planned", "done", "declined"] | None = None
    admin_note: str | None = Field(default=None, max_length=2000)
    category: str | None = Field(default=None, max_length=20)


@router.patch("/{request_id}")
def update_request(request_id: uuid.UUID, body: RequestPatch, request: Request, principal: Principal = Depends(operator),
                   db: OrmSession = Depends(get_db)):
    row = db.scalar(select(AssistantRequest).where(AssistantRequest.id == request_id).with_for_update())
    if row is None:
        raise NotFound("Ønsket findes ikke")
    if body.category is not None and body.category not in ASSISTANT_REQUEST_CATEGORIES:
        raise ValidationFailed("Ukendt kategori", field_errors=[{"field": "category"}])
    before = {"status": row.status, "admin_note": row.admin_note, "category": row.category}
    if body.status is not None:
        row.status = body.status
    if body.admin_note is not None:
        row.admin_note = body.admin_note.strip()
    if body.category is not None:
        row.category = body.category
    after = {"status": row.status, "admin_note": row.admin_note, "category": row.category}
    if after != before:
        record_audit(db, workspace_id=row.workspace_id, actor_user_id=principal.user.id, action="assistant.request_updated",
                     object_type="assistant_request", object_id=row.id, before=before, after=after,
                     request_id=request.state.request_id)
    db.commit()
    db.refresh(row)
    ws = db.get(Workspace, row.workspace_id)
    return wishes.out(row, workspace_name=ws.name if ws else "")

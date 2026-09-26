from __future__ import annotations

import uuid
from datetime import date, datetime

from fastapi import APIRouter, BackgroundTasks, Depends, Header, Query, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session as OrmSession

from app.core.auth import WorkspaceContext, get_scoped, get_workspace_context, require_capability
from app.core.errors import ValidationFailed
from app.core.idempotency import IdempotencyGuard, scope_for
from app.core.pagination import PageParams, page
from app.db import get_db
from app.models import KnowledgeItem, KnowledgeVersion
from app.modules.knowledge import importer, service

router = APIRouter(prefix="/workspaces/{workspace_id}", tags=["knowledge"])


class VersionOut(BaseModel):
    id: uuid.UUID
    item_id: uuid.UUID
    version_no: int
    status: str
    title: str
    content: dict
    source_type: str
    source_ref: str | None
    edit_version: int
    created_by: uuid.UUID | None
    created_at: datetime
    submitted_at: datetime | None
    approved_by: uuid.UUID | None
    approved_at: datetime | None
    superseded_at: datetime | None


class ItemOut(BaseModel):
    id: uuid.UUID
    kind: str
    key: str
    archived_at: datetime | None
    approved_version: VersionOut | None
    open_draft: VersionOut | None


class ItemCreateIn(BaseModel):
    kind: str
    title: str = Field(min_length=1, max_length=200)
    content: dict = Field(default_factory=dict)
    source_ref: str | None = Field(default=None, max_length=300)


class DraftIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    content: dict = Field(default_factory=dict)
    source_ref: str | None = Field(default=None, max_length=300)


class DraftEditIn(DraftIn):
    expected_edit_version: int


class RejectIn(BaseModel):
    reason: str = Field(min_length=1, max_length=1000)


def v_out(v: KnowledgeVersion | None) -> VersionOut | None:
    return VersionOut.model_validate(v, from_attributes=True) if v else None


def item_out(db: OrmSession, item: KnowledgeItem) -> ItemOut:
    return ItemOut(id=item.id, kind=item.kind, key=item.key, archived_at=item.archived_at,
                   approved_version=v_out(service.approved_version(db, item.id)),
                   open_draft=v_out(service.open_draft(db, item.id)))


@router.get("/knowledge/items")
def list_items(p: PageParams = Depends(), kind: str | None = Query(default=None),
               ctx: WorkspaceContext = Depends(require_capability("knowledge.read")), db: OrmSession = Depends(get_db)):
    q = select(KnowledgeItem).where(KnowledgeItem.workspace_id == ctx.workspace.id, KnowledgeItem.archived_at.is_(None))
    if kind:
        q = q.where(KnowledgeItem.kind == kind)
    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
    rows = db.scalars(q.order_by(KnowledgeItem.kind, KnowledgeItem.key).limit(p.limit).offset(p.offset))
    return page([item_out(db, i).model_dump(mode="json") for i in rows], total, p)


@router.post("/knowledge/items", status_code=status.HTTP_201_CREATED, response_model=ItemOut)
def create_item(body: ItemCreateIn, request: Request, ctx: WorkspaceContext = Depends(get_workspace_context),
                db: OrmSession = Depends(get_db)):
    item, _ = service.create_item(db, ctx, kind=body.kind, title=body.title, content=body.content,
                                  source_ref=body.source_ref, request_id=request.state.request_id)
    db.commit()
    return item_out(db, item)


@router.get("/knowledge/items/{item_id}", response_model=ItemOut)
def get_item(item_id: uuid.UUID, ctx: WorkspaceContext = Depends(require_capability("knowledge.read")),
             db: OrmSession = Depends(get_db)):
    return item_out(db, get_scoped(db, KnowledgeItem, item_id, ctx.workspace.id))


@router.get("/knowledge/items/{item_id}/versions", response_model=list[VersionOut])
def list_versions(item_id: uuid.UUID, ctx: WorkspaceContext = Depends(require_capability("knowledge.read")),
                  db: OrmSession = Depends(get_db)):
    item = get_scoped(db, KnowledgeItem, item_id, ctx.workspace.id)
    rows = db.scalars(select(KnowledgeVersion).where(KnowledgeVersion.item_id == item.id)
                      .order_by(KnowledgeVersion.version_no))
    return [v_out(v) for v in rows]


@router.post("/knowledge/items/{item_id}/drafts", status_code=status.HTTP_201_CREATED, response_model=VersionOut)
def new_draft(item_id: uuid.UUID, body: DraftIn, request: Request,
              ctx: WorkspaceContext = Depends(get_workspace_context), db: OrmSession = Depends(get_db)):
    v = service.new_draft(db, ctx, item_id, title=body.title, content=body.content, source_ref=body.source_ref,
                          request_id=request.state.request_id)
    db.commit()
    return v_out(v)


@router.put("/knowledge/versions/{version_id}", response_model=VersionOut)
def edit_draft(version_id: uuid.UUID, body: DraftEditIn, request: Request,
               ctx: WorkspaceContext = Depends(get_workspace_context), db: OrmSession = Depends(get_db)):
    v = service.edit_draft(db, ctx, version_id, expected_edit_version=body.expected_edit_version, title=body.title,
                           content=body.content, source_ref=body.source_ref, request_id=request.state.request_id)
    db.commit()
    return v_out(v)


@router.post("/knowledge/versions/{version_id}/submit", response_model=VersionOut)
def submit(version_id: uuid.UUID, request: Request, ctx: WorkspaceContext = Depends(get_workspace_context),
           db: OrmSession = Depends(get_db)):
    v = service.submit_for_review(db, ctx, version_id, request.state.request_id)
    db.commit()
    return v_out(v)


@router.post("/knowledge/versions/{version_id}/approve", response_model=VersionOut)
def approve(version_id: uuid.UUID, request: Request, response: Response,
            ctx: WorkspaceContext = Depends(get_workspace_context), db: OrmSession = Depends(get_db),
            idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")):
    guard = IdempotencyGuard(db, scope_for(ctx.user_id, "knowledge.approve", ctx.workspace.id), idempotency_key,
                             {"version_id": str(version_id)})
    if guard.replay:
        response.status_code = guard.replay[0]
        return guard.replay[1]
    v = service.approve(db, ctx, version_id, request.state.request_id)
    out = v_out(v).model_dump(mode="json")
    guard.store(200, out)
    db.commit()
    return out


@router.post("/knowledge/versions/{version_id}/reject", response_model=VersionOut)
def reject(version_id: uuid.UUID, body: RejectIn, request: Request,
           ctx: WorkspaceContext = Depends(get_workspace_context), db: OrmSession = Depends(get_db)):
    v = service.reject(db, ctx, version_id, body.reason, request.state.request_id)
    db.commit()
    return v_out(v)


@router.get("/knowledge/review-queue", response_model=list[VersionOut])
def review_queue(ctx: WorkspaceContext = Depends(require_capability("knowledge.read")), db: OrmSession = Depends(get_db)):
    rows = db.scalars(select(KnowledgeVersion).where(KnowledgeVersion.workspace_id == ctx.workspace.id,
                                                     KnowledgeVersion.status == "in_review")
                      .order_by(KnowledgeVersion.submitted_at))
    return [v_out(v) for v in rows]


@router.get("/assistant/knowledge")
def assistant_knowledge(ctx: WorkspaceContext = Depends(require_capability("knowledge.read")),
                        db: OrmSession = Depends(get_db)):
    """Read model for the assistant: only approved, current knowledge.
    The AI conversation itself is not implemented in this stage."""
    return {"workspace_id": str(ctx.workspace.id), "knowledge_revision": ctx.workspace.knowledge_revision,
            "items": service.active_knowledge(db, ctx.workspace.id)}


@router.get("/knowledge/offers/{item_id}/eligibility")
def offer_eligibility(item_id: uuid.UUID, area_m2: float | None = Query(default=None), on_date: date = Query(...),
                      ctx: WorkspaceContext = Depends(require_capability("knowledge.read")), db: OrmSession = Depends(get_db)):
    """Evaluates the APPROVED version of an offer (never a draft)."""
    item = get_scoped(db, KnowledgeItem, item_id, ctx.workspace.id)
    v = service.approved_version(db, item.id)
    if item.kind != "offer" or v is None:
        from app.core.errors import NotFound

        raise NotFound("Der findes ikke et godkendt tilbud med dette id")
    return {"item_id": str(item.id), "version_id": str(v.id), "area_m2": area_m2, "on_date": on_date.isoformat(),
            "eligible": service.offer_is_eligible(v.content, area_m2=area_m2, on_date=on_date)}


class ImportIn(BaseModel):
    url: str | None = Field(default=None, max_length=500)


@router.post("/knowledge/import", status_code=status.HTTP_202_ACCEPTED)
def start_import(body: ImportIn, background: BackgroundTasks,
                 ctx: WorkspaceContext = Depends(require_capability("knowledge.draft")),
                 db: OrmSession = Depends(get_db)):
    """Suggest services, facts and FAQs from the company's website as drafts (runs in the background)."""
    from app.models import BusinessProfile

    raw = body.url or (db.get(BusinessProfile, ctx.workspace.id) or BusinessProfile()).website_url or ""
    if not raw.strip():
        raise ValidationFailed("Angiv jeres hjemmesides adresse", field_errors=[{"field": "url"}])
    imp, is_new = importer.start(db, ctx.workspace, ctx.user_id, importer.normalize_url(raw))
    if is_new:
        background.add_task(importer.run, imp.id)
    return importer.import_out(imp)


@router.get("/knowledge/imports/latest")
def latest_import(ctx: WorkspaceContext = Depends(require_capability("knowledge.read")),
                  db: OrmSession = Depends(get_db)):
    from app.models import SourceImport

    imp = db.scalar(select(SourceImport).where(SourceImport.workspace_id == ctx.workspace.id)
                    .order_by(SourceImport.created_at.desc()).limit(1))
    return {"import": importer.import_out(imp)}

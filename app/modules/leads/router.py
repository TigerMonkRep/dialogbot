"""Leads (henvendelser), tasks and the reception agreement."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Header, Query, Request, Response, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session as OrmSession

from app.core.audit import record_audit
from app.core.auth import WorkspaceContext, get_scoped, require_capability
from app.core.errors import ValidationFailed
from app.core.idempotency import IdempotencyGuard, scope_for
from app.core.pagination import PageParams, page
from app.db import get_db
from app.models import Conversation, Lead, Task
from app.modules.billing import agreements
from app.modules.leads import service

router = APIRouter(prefix="/workspaces/{workspace_id}", tags=["leads"])


# --- Agreement ---------------------------------------------------------------

class AgreementIn(BaseModel):
    model: Literal["A", "B"]


@router.get("/agreement")
def get_agreement(ctx: WorkspaceContext = Depends(require_capability("agreements.read")), db: OrmSession = Depends(get_db)):
    return {"current": agreements.out(agreements.current(db, ctx.workspace.id)),
            "options": {"A": {"monthly_net_minor": agreements.MODEL_A_MONTHLY_NET_MINOR, "lead_fee_net_minor": 0},
                        "B": {"monthly_net_minor": 0, "lead_fee_net_minor": agreements.MODEL_B_LEAD_FEE_NET_MINOR}}}


@router.post("/agreement", status_code=status.HTTP_201_CREATED)
def choose_agreement(body: AgreementIn, request: Request, ctx: WorkspaceContext = Depends(require_capability("agreements.edit")),
                     db: OrmSession = Depends(get_db)):
    a = agreements.create(db, ctx.workspace.id, body.model, ctx.user_id)
    record_audit(db, workspace_id=ctx.workspace.id, actor_user_id=ctx.user_id, action="agreement.created",
                 object_type="reception_agreement", object_id=a.id, after={"version": a.version, "model": a.model},
                 request_id=request.state.request_id)
    db.commit()
    return agreements.out(a)


# --- Leads -------------------------------------------------------------------

class LeadIn(BaseModel):
    conversation_id: uuid.UUID | None = None
    contact_name: str = Field(default="", max_length=200)
    contact_email: EmailStr | None = None
    contact_phone: str | None = Field(default=None, max_length=40)
    need_summary: str = Field(default="", max_length=4000)


class LeadPatch(BaseModel):
    expected_version: int
    contact_name: str | None = Field(default=None, max_length=200)
    contact_email: EmailStr | None = None
    contact_phone: str | None = Field(default=None, max_length=40)
    need_summary: str | None = Field(default=None, max_length=4000)
    qualification_status: Literal["unqualified", "qualified", "disqualified"] | None = None
    qualification_reason: str | None = Field(default=None, max_length=500)
    pipeline_status: Literal["new", "contacted", "won", "lost"] | None = None


class DecisionIn(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


def _lead(db: OrmSession, ctx: WorkspaceContext, lead_id: uuid.UUID) -> Lead:
    return get_scoped(db, Lead, lead_id, ctx.workspace.id)


def _tasks_of(db: OrmSession, lead: Lead) -> list[Task]:
    return list(db.scalars(select(Task).where(Task.lead_id == lead.id).order_by(Task.status, Task.created_at)))


@router.get("/leads")
def list_leads(p: PageParams = Depends(), qualification: str | None = Query(default=None),
               pipeline: str | None = Query(default=None), billing: str | None = Query(default=None),
               ctx: WorkspaceContext = Depends(require_capability("leads.read")), db: OrmSession = Depends(get_db)):
    q = select(Lead).where(Lead.workspace_id == ctx.workspace.id)
    if qualification:
        q = q.where(Lead.qualification_status == qualification)
    if pipeline:
        q = q.where(Lead.pipeline_status == pipeline)
    if billing:
        q = q.where(Lead.billing_status == billing)
    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
    rows = db.scalars(q.order_by(Lead.created_at.desc()).limit(p.limit).offset(p.offset))
    return page([service.lead_out(x) for x in rows], total, p)


@router.post("/leads", status_code=status.HTTP_201_CREATED)
def create_lead(body: LeadIn, request: Request, ctx: WorkspaceContext = Depends(require_capability("leads.edit")),
                db: OrmSession = Depends(get_db)):
    conv = get_scoped(db, Conversation, body.conversation_id, ctx.workspace.id) if body.conversation_id else None
    lead = service.create_lead(db, ctx.workspace.id, source="webchat" if conv else "manual", created_by=ctx.user_id,
                               conversation=conv, contact_name=body.contact_name,
                               contact_email=str(body.contact_email) if body.contact_email else None,
                               contact_phone=body.contact_phone, need_summary=body.need_summary,
                               request_id=request.state.request_id)
    db.commit()
    return service.lead_out(lead, [])


@router.get("/leads/{lead_id}")
def get_lead(lead_id: uuid.UUID, ctx: WorkspaceContext = Depends(require_capability("leads.read")),
             db: OrmSession = Depends(get_db)):
    lead = _lead(db, ctx, lead_id)
    return service.lead_out(lead, _tasks_of(db, lead))


@router.patch("/leads/{lead_id}")
def update_lead(lead_id: uuid.UUID, body: LeadPatch, request: Request,
                ctx: WorkspaceContext = Depends(require_capability("leads.edit")), db: OrmSession = Depends(get_db)):
    lead = db.scalar(select(Lead).where(Lead.id == lead_id, Lead.workspace_id == ctx.workspace.id).with_for_update())
    if lead is None:
        _lead(db, ctx, lead_id)  # uniform 404
    changes = body.model_dump(exclude_unset=True, exclude={"expected_version"})
    if "contact_email" in changes and changes["contact_email"] is not None:
        changes["contact_email"] = str(changes["contact_email"])
    service.update_lead(db, lead, actor=ctx.user_id, expected_version=body.expected_version, changes=changes,
                        request_id=request.state.request_id)
    db.commit()
    return service.lead_out(lead, _tasks_of(db, lead))


def _decide(decision: str, lead_id: uuid.UUID, body: DecisionIn, request: Request, response: Response,
            ctx: WorkspaceContext, db: OrmSession, idempotency_key: str | None):
    guard = IdempotencyGuard(db, scope_for(ctx.user_id, f"leads.{decision}", ctx.workspace.id), idempotency_key,
                             {"lead_id": str(lead_id), "reason": body.reason})
    if guard.replay:
        response.status_code = guard.replay[0]
        return guard.replay[1]
    lead = db.scalar(select(Lead).where(Lead.id == lead_id, Lead.workspace_id == ctx.workspace.id).with_for_update())
    if lead is None:
        _lead(db, ctx, lead_id)
    service.decide_billing(db, lead, actor=ctx.user_id, decision=decision, reason=body.reason,
                           request_id=request.state.request_id)
    out = service.lead_out(lead, _tasks_of(db, lead))
    guard.store(200, out)
    db.commit()
    return out


@router.post("/leads/{lead_id}/approve")
def approve_lead(lead_id: uuid.UUID, request: Request, response: Response, body: DecisionIn | None = None,
                 ctx: WorkspaceContext = Depends(require_capability("leads.approve")), db: OrmSession = Depends(get_db),
                 idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")):
    """Approve a qualified lead as billable under the current agreement (idempotent with Idempotency-Key)."""
    return _decide("approve", lead_id, body or DecisionIn(), request, response, ctx, db, idempotency_key)


@router.post("/leads/{lead_id}/reject")
def reject_lead(lead_id: uuid.UUID, body: DecisionIn, request: Request, response: Response,
                ctx: WorkspaceContext = Depends(require_capability("leads.approve")), db: OrmSession = Depends(get_db),
                idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")):
    return _decide("reject", lead_id, body, request, response, ctx, db, idempotency_key)


@router.get("/conversations/{conversation_id}/lead")
def lead_of_conversation(conversation_id: uuid.UUID, ctx: WorkspaceContext = Depends(require_capability("leads.read")),
                         db: OrmSession = Depends(get_db)):
    conv = get_scoped(db, Conversation, conversation_id, ctx.workspace.id)
    lead = service.lead_for_conversation(db, conv.id)
    return {"lead": service.lead_out(lead) if lead else None}


# --- Tasks -------------------------------------------------------------------

class TaskIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    lead_id: uuid.UUID | None = None
    due_at: datetime | None = None
    assignee_user_id: uuid.UUID | None = None


class TaskPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    status: Literal["open", "done"] | None = None
    due_at: datetime | None = None
    assignee_user_id: uuid.UUID | None = None


@router.get("/tasks")
def list_tasks(p: PageParams = Depends(), status_: Literal["open", "done"] | None = Query(default="open", alias="status"),
               mine: bool = False, ctx: WorkspaceContext = Depends(require_capability("tasks.read")),
               db: OrmSession = Depends(get_db)):
    q = select(Task).where(Task.workspace_id == ctx.workspace.id)
    if status_:
        q = q.where(Task.status == status_)
    if mine:
        q = q.where(Task.assignee_user_id == ctx.user_id)
    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
    rows = db.scalars(q.order_by(Task.due_at.asc().nulls_last(), Task.created_at).limit(p.limit).offset(p.offset))
    return page([service.task_out(t) for t in rows], total, p)


@router.post("/tasks", status_code=status.HTTP_201_CREATED)
def create_task(body: TaskIn, request: Request, ctx: WorkspaceContext = Depends(require_capability("tasks.edit")),
                db: OrmSession = Depends(get_db)):
    lead = _lead(db, ctx, body.lead_id) if body.lead_id else None
    t = service.create_task(db, ctx.workspace.id, title=body.title, created_by=ctx.user_id, lead=lead, due_at=body.due_at,
                            assignee_user_id=body.assignee_user_id, request_id=request.state.request_id)
    db.commit()
    return service.task_out(t)


@router.patch("/tasks/{task_id}")
def update_task(task_id: uuid.UUID, body: TaskPatch, request: Request,
                ctx: WorkspaceContext = Depends(require_capability("tasks.edit")), db: OrmSession = Depends(get_db)):
    t = get_scoped(db, Task, task_id, ctx.workspace.id)
    changes = body.model_dump(exclude_unset=True)
    if "assignee_user_id" in changes and changes["assignee_user_id"] is not None:
        service._require_member(db, ctx.workspace.id, changes["assignee_user_id"])
    if "title" in changes and changes["title"] is None:
        raise ValidationFailed("Titel kan ikke være tom", field_errors=[{"field": "title"}])
    before = service.task_out(t)
    for k, v in changes.items():
        setattr(t, k, v)
    if "status" in changes:
        from datetime import UTC

        done = t.status == "done"
        t.completed_at = datetime.now(UTC) if done else None
        t.completed_by = ctx.user_id if done else None
    record_audit(db, workspace_id=ctx.workspace.id, actor_user_id=ctx.user_id, action="task.updated", object_type="task",
                 object_id=t.id, before={"status": before["status"], "title": before["title"]},
                 after={"status": t.status, "title": t.title}, request_id=request.state.request_id)
    db.commit()
    return service.task_out(t)

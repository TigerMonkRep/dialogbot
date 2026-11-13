"""M06 – the operators' support queue: every workspace's tickets, triage (status, priority, category, assignee),
replies the customer sees (and is mailed about) and internal notes the customer never sees (DB-016).

Only Dialogbot platform operators (`is_platform_operator`). Operator actions are audited in operator scope
(workspace_id=None, the customer's id in `after.workspace_id`) and without message bodies: an internal note must not
reach the customer's activity log (F-EA-01)."""
from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session as OrmSession

from app.core.audit import record_audit
from app.core.auth import Principal
from app.core.errors import NotFound, ValidationFailed
from app.db import get_db
from app.models import (
    SUPPORT_CATEGORIES,
    SUPPORT_PRIORITIES,
    SUPPORT_STATUSES,
    SupportAttachment,
    SupportTicket,
    User,
    Workspace,
)
from app.modules.support import attachments as files
from app.modules.support import service as svc
from app.modules.voices.operator_router import operator

router = APIRouter(prefix="/operator/support", tags=["support-operator"])
ACTIVE = ("open", "in_progress", "waiting_customer")


def _ticket(db: OrmSession, ticket_id: uuid.UUID, *, lock: bool = False) -> SupportTicket:
    q = select(SupportTicket).where(SupportTicket.id == ticket_id)
    t = db.scalar(q.with_for_update() if lock else q)
    if t is None:
        raise NotFound("Sagen findes ikke")
    return t


def _audit(db, request: Request, principal: Principal, action: str, t: SupportTicket, before: dict | None = None,
           after: dict | None = None):
    record_audit(db, workspace_id=None, actor_user_id=principal.user.id, action=action, object_type="support_ticket",
                 object_id=t.id, before=before,
                 after=(after or {}) | {"workspace_id": str(t.workspace_id), "number": t.number},
                 request_id=request.state.request_id)


@router.get("/tickets")
def list_tickets(status: str | None = Query(default=None, max_length=20), assigned: str | None = None,
                 workspace_id: uuid.UUID | None = None, priority: str | None = None, category: str | None = None,
                 q: str | None = Query(default=None, max_length=100), limit: int = Query(default=100, ge=1, le=500),
                 principal: Principal = Depends(operator), db: OrmSession = Depends(get_db)):
    """`status`: one of the statuses, or `active` (everything not resolved). `assigned`: `me`, `none` or an operator's
    id. Counts (for the tabs) ignore status and assignee but respect the other filters."""
    base = []
    if workspace_id:
        base.append(SupportTicket.workspace_id == workspace_id)
    if priority:
        if priority not in SUPPORT_PRIORITIES:
            raise ValidationFailed("Ukendt prioritet", field_errors=[{"field": "priority"}])
        base.append(SupportTicket.priority == priority)
    if category:
        if category not in SUPPORT_CATEGORIES:
            raise ValidationFailed("Ukendt kategori", field_errors=[{"field": "category"}])
        base.append(SupportTicket.category == category)
    if q and q.strip():
        term = q.strip().lstrip("#")
        conds = [SupportTicket.subject.ilike(f"%{term[:100]}%"), Workspace.name.ilike(f"%{term[:100]}%")]
        if term.isdigit():
            conds.append(SupportTicket.number == int(term))
        base.append(or_(*conds))
    conds = list(base)
    if status == "active":
        conds.append(SupportTicket.status.in_(ACTIVE))
    elif status:
        if status not in SUPPORT_STATUSES:
            raise ValidationFailed("Ukendt status", field_errors=[{"field": "status"}])
        conds.append(SupportTicket.status == status)
    if assigned == "me":
        conds.append(SupportTicket.assigned_to == principal.user.id)
    elif assigned == "none":
        conds.append(SupportTicket.assigned_to.is_(None))
    elif assigned:
        try:
            conds.append(SupportTicket.assigned_to == uuid.UUID(assigned))
        except ValueError:
            raise ValidationFailed("Ukendt operatør", field_errors=[{"field": "assigned"}])
    rows = db.execute(select(SupportTicket, Workspace.name).join(Workspace, Workspace.id == SupportTicket.workspace_id)
                      .where(*conds).order_by(SupportTicket.updated_at.desc()).limit(limit)).all()
    users = svc._names(db, {t.assigned_to for t, _ in rows} | {t.created_by for t, _ in rows})
    counted = select(SupportTicket.status, func.count()).join(Workspace, Workspace.id == SupportTicket.workspace_id)
    by_status = dict(db.execute(counted.where(*base).group_by(SupportTicket.status)).all())
    mine = db.scalar(select(func.count()).select_from(SupportTicket).join(Workspace, Workspace.id == SupportTicket.workspace_id)
                     .where(and_(*base, SupportTicket.assigned_to == principal.user.id,
                                 SupportTicket.status.in_(ACTIVE)))) or 0
    return {
        "items": [svc.operator_summary(t, name, users) for t, name in rows],
        "counts": {"all": sum(by_status.values()), "active": sum(by_status.get(s, 0) for s in ACTIVE), "mine": mine,
                   **{s: by_status.get(s, 0) for s in SUPPORT_STATUSES}},
        "workspaces": [{"id": str(i), "name": n} for i, n in db.execute(
            select(Workspace.id, Workspace.name).join(SupportTicket, SupportTicket.workspace_id == Workspace.id)
            .distinct().order_by(Workspace.name)).all()],
    }


@router.get("/tickets/{ticket_id}")
def get_ticket(ticket_id: uuid.UUID, _: Principal = Depends(operator), db: OrmSession = Depends(get_db)):
    return svc.operator_detail(db, _ticket(db, ticket_id))


class TicketPatch(BaseModel):
    status: Literal["open", "in_progress", "waiting_customer", "resolved"] | None = None
    priority: Literal["low", "normal", "high", "critical"] | None = None
    category: Literal["reception", "campaigns", "calendar", "billing", "other"] | None = None
    assigned_to: uuid.UUID | None = None
    unassign: bool = False  # «Frigiv til fælleskøen»


@router.patch("/tickets/{ticket_id}")
def update_ticket(ticket_id: uuid.UUID, body: TicketPatch, request: Request, principal: Principal = Depends(operator),
                  db: OrmSession = Depends(get_db)):
    t = _ticket(db, ticket_id, lock=True)
    fields = ("status", "priority", "category", "assigned_to")
    before = {k: (str(getattr(t, k)) if getattr(t, k) is not None else None) for k in fields}
    if body.assigned_to is not None:
        target = db.get(User, body.assigned_to)
        if target is None or not target.is_platform_operator or not target.is_active:
            raise ValidationFailed("Sagen kan kun tildeles en aktiv operatør", field_errors=[{"field": "assigned_to"}])
        t.assigned_to = target.id
    elif body.unassign:
        t.assigned_to = None
    if body.priority is not None:
        t.priority = body.priority
    if body.category is not None:
        t.category = body.category
    if body.status is not None and body.status != t.status:
        svc.set_status(t, body.status)
    after = {k: (str(getattr(t, k)) if getattr(t, k) is not None else None) for k in fields}
    if after != before:
        t.updated_at = svc.now()
        _audit(db, request, principal, "support.operator_updated", t, before=before, after=after)
    db.commit()
    return svc.operator_detail(db, t)


class OperatorMessage(BaseModel):
    body: str = Field(min_length=1, max_length=5000)
    visibility: Literal["public", "internal"]
    # A public reply sets «Afventer kunde» unless the operator picks another status (e.g. resolved: «Send og luk»).
    status: Literal["open", "in_progress", "waiting_customer", "resolved"] | None = None


@router.post("/tickets/{ticket_id}/messages", status_code=201)
def add_message(ticket_id: uuid.UUID, body: OperatorMessage, request: Request, principal: Principal = Depends(operator),
                db: OrmSession = Depends(get_db)):
    text = body.body.strip()
    if not text:
        raise ValidationFailed("Skriv en besked", field_errors=[{"field": "body"}])
    t = _ticket(db, ticket_id, lock=True)
    m = svc.add_message(db, t, author=principal.user.id, kind="operator", visibility=body.visibility, body=text)
    mailed = False
    if body.visibility == "public":
        svc.set_status(t, body.status or "waiting_customer")
        if t.assigned_to is None:
            t.assigned_to = principal.user.id  # whoever answers owns it until it is handed on
        mailed = svc.notify_customer(db, t, m.id)
    elif body.status is not None and body.status != t.status:
        svc.set_status(t, body.status)
    _audit(db, request, principal, "support.operator_replied" if body.visibility == "public" else "support.internal_note",
           t, after={"visibility": body.visibility, "status": t.status, "mailed": mailed})
    db.commit()
    return svc.operator_detail(db, t)


@router.get("/tickets/{ticket_id}/attachments/{attachment_id}")
def download(ticket_id: uuid.UUID, attachment_id: uuid.UUID, _: Principal = Depends(operator),
             db: OrmSession = Depends(get_db)):
    row = db.scalar(select(SupportAttachment).where(SupportAttachment.id == attachment_id,
                                                    SupportAttachment.ticket_id == ticket_id))
    if row is None:
        raise NotFound("Filen findes ikke")
    return files.download(row)

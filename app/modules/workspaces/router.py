from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Header, Request, Response, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session as OrmSession

from app.core.auth import Principal, WorkspaceContext, get_current_principal, get_workspace_context, require_capability
from app.core.idempotency import IdempotencyGuard, scope_for
from app.core.pagination import PageParams, page
from app.db import get_db
from app.models import AuditLog, Invitation, Membership, User
from app.modules.workspaces import service

router = APIRouter(tags=["workspaces"])


class WorkspaceCreateIn(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    product_intent: str | None = Field(default=None, description="reception | campaigns | both; defaults to signup intent")


class WorkspaceOut(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    status: str
    product_intent: str
    knowledge_revision: int
    role: str
    created_at: datetime


def ws_out(w, role: str) -> WorkspaceOut:
    return WorkspaceOut(id=w.id, name=w.name, slug=w.slug, status=w.status, product_intent=w.product_intent,
                        knowledge_revision=w.knowledge_revision, role=role, created_at=w.created_at)


class MemberOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    email: str
    display_name: str
    role: str
    created_at: datetime


class RoleIn(BaseModel):
    role: str


class InvitationCreateIn(BaseModel):
    email: EmailStr
    role: str = "staff"


class InvitationOut(BaseModel):
    id: uuid.UUID
    email: str
    role: str
    status: str
    expires_at: datetime
    created_at: datetime
    # NOTE: the raw token is never part of any API response.


def inv_out(i) -> InvitationOut:
    return InvitationOut(id=i.id, email=i.email, role=i.role, status=i.status, expires_at=i.expires_at,
                         created_at=i.created_at)


class InvitationPreviewOut(BaseModel):
    workspace_name: str
    email: str
    role: str
    status: str
    expires_at: datetime


class AcceptIn(BaseModel):
    token: str = Field(min_length=10, max_length=200)


class AuditOut(BaseModel):
    id: uuid.UUID
    actor_user_id: uuid.UUID | None
    action: str
    object_type: str
    object_id: str | None
    before: dict | None
    after: dict | None
    request_id: str | None
    created_at: datetime


@router.post("/workspaces", response_model=WorkspaceOut, status_code=status.HTTP_201_CREATED)
def create_workspace(body: WorkspaceCreateIn, request: Request, principal: Principal = Depends(get_current_principal),
                     db: OrmSession = Depends(get_db)):
    ws = service.create_workspace(db, user=principal.user, name=body.name, product_intent=body.product_intent,
                                  request_id=request.state.request_id)
    db.commit()
    return ws_out(ws, "owner")


@router.get("/workspaces", response_model=list[WorkspaceOut])
def list_workspaces(principal: Principal = Depends(get_current_principal), db: OrmSession = Depends(get_db)):
    return [ws_out(w, m.role) for w, m in service.list_workspaces_for_user(db, principal.user.id)]


@router.get("/workspaces/{workspace_id}", response_model=WorkspaceOut)
def get_workspace(ctx: WorkspaceContext = Depends(get_workspace_context)):
    return ws_out(ctx.workspace, ctx.role)


@router.get("/workspaces/{workspace_id}/members", response_model=list[MemberOut])
def list_members(ctx: WorkspaceContext = Depends(require_capability("members.read")), db: OrmSession = Depends(get_db)):
    rows = db.execute(select(Membership, User).join(User, User.id == Membership.user_id)
                      .where(Membership.workspace_id == ctx.workspace.id).order_by(Membership.created_at))
    return [MemberOut(id=m.id, user_id=u.id, email=u.email, display_name=u.display_name, role=m.role,
                      created_at=m.created_at) for m, u in rows]


@router.put("/workspaces/{workspace_id}/members/{membership_id}/role", response_model=MemberOut)
def change_role(membership_id: uuid.UUID, body: RoleIn, request: Request,
                ctx: WorkspaceContext = Depends(get_workspace_context), db: OrmSession = Depends(get_db)):
    m = service.change_role(db, ctx, membership_id, body.role, request_id=request.state.request_id)
    db.commit()
    u = db.get(User, m.user_id)
    return MemberOut(id=m.id, user_id=u.id, email=u.email, display_name=u.display_name, role=m.role,
                     created_at=m.created_at)


@router.delete("/workspaces/{workspace_id}/members/{membership_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_member(membership_id: uuid.UUID, request: Request, ctx: WorkspaceContext = Depends(get_workspace_context),
                  db: OrmSession = Depends(get_db)):
    service.remove_member(db, ctx, membership_id, request_id=request.state.request_id)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/workspaces/{workspace_id}/invitations", response_model=list[InvitationOut])
def list_invitations(ctx: WorkspaceContext = Depends(require_capability("members.invite")),
                     db: OrmSession = Depends(get_db)):
    rows = db.scalars(select(Invitation).where(Invitation.workspace_id == ctx.workspace.id)
                      .order_by(Invitation.created_at.desc()))
    return [inv_out(i) for i in rows]


@router.post("/workspaces/{workspace_id}/invitations", response_model=InvitationOut,
             status_code=status.HTTP_201_CREATED)
def create_invitation(body: InvitationCreateIn, request: Request, response: Response,
                      ctx: WorkspaceContext = Depends(get_workspace_context), db: OrmSession = Depends(get_db),
                      idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")):
    guard = IdempotencyGuard(db, scope_for(ctx.user_id, "invitations.create", ctx.workspace.id), idempotency_key,
                             body.model_dump())
    if guard.replay:
        response.status_code = guard.replay[0]
        return guard.replay[1]
    inv, created = service.create_invitation(db, ctx, email=body.email, role=body.role,
                                             request_id=request.state.request_id)
    out = inv_out(inv).model_dump(mode="json")
    code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    guard.store(code, out)
    db.commit()
    response.status_code = code
    return out


@router.post("/workspaces/{workspace_id}/invitations/{invitation_id}/revoke", response_model=InvitationOut)
def revoke_invitation(invitation_id: uuid.UUID, request: Request,
                      ctx: WorkspaceContext = Depends(get_workspace_context), db: OrmSession = Depends(get_db)):
    inv = service.revoke_invitation(db, ctx, invitation_id, request_id=request.state.request_id)
    db.commit()
    return inv_out(inv)


@router.post("/workspaces/{workspace_id}/invitations/{invitation_id}/resend", response_model=InvitationOut)
def resend_invitation(invitation_id: uuid.UUID, ctx: WorkspaceContext = Depends(get_workspace_context),
                      db: OrmSession = Depends(get_db)):
    inv = service.resend_invitation(db, ctx, invitation_id)
    db.commit()
    return inv_out(inv)


@router.get("/invitations/{token}", response_model=InvitationPreviewOut)
def preview_invitation(token: str, db: OrmSession = Depends(get_db)):
    """Public preview for /invite/:token (A05). Reveals only what the invitee needs."""
    inv = service.preview_invitation(db, token)
    from app.models import Workspace

    ws = db.get(Workspace, inv.workspace_id)
    st = inv.status
    if st == "pending" and inv.expires_at <= datetime.now(inv.expires_at.tzinfo):
        st = "expired"
    return InvitationPreviewOut(workspace_name=ws.name if ws else "", email=inv.email, role=inv.role, status=st,
                                expires_at=inv.expires_at)


@router.post("/invitations/accept", response_model=WorkspaceOut)
def accept_invitation(body: AcceptIn, request: Request, principal: Principal = Depends(get_current_principal),
                      db: OrmSession = Depends(get_db)):
    m = service.accept_invitation(db, user=principal.user, raw_token=body.token, request_id=request.state.request_id)
    db.commit()
    from app.models import Workspace

    ws = db.get(Workspace, m.workspace_id)
    return ws_out(ws, m.role)


@router.get("/workspaces/{workspace_id}/audit")
def list_audit(p: PageParams = Depends(), ctx: WorkspaceContext = Depends(require_capability("audit.read")),
               db: OrmSession = Depends(get_db)):
    q = select(AuditLog).where(AuditLog.workspace_id == ctx.workspace.id)
    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
    rows = db.scalars(q.order_by(AuditLog.created_at.desc()).limit(p.limit).offset(p.offset))
    items = [AuditOut(id=a.id, actor_user_id=a.actor_user_id, action=a.action, object_type=a.object_type,
                      object_id=a.object_id, before=a.before, after=a.after, request_id=a.request_id,
                      created_at=a.created_at).model_dump(mode="json") for a in rows]
    return page(items, total, p)

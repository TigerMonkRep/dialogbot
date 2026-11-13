"""H01 – customer support: a workspace's members open support tickets with attachments, follow the status and write
in the thread at /app/support/<number>. Staff and up (`support.read` / `support.write`); a reader sees the help page
but not the tickets. Every lookup is by (workspace, number): another workspace's ticket is 404."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from app.core.audit import record_audit
from app.core.auth import WorkspaceContext, require_capability
from app.core.errors import Conflict, NotFound, ValidationFailed
from app.db import get_db
from app.models import SUPPORT_CATEGORIES, SupportAttachment, SupportMessage, SupportTicket
from app.modules.support import attachments as files
from app.modules.support import service as svc

router = APIRouter(prefix="/workspaces/{workspace_id}/support/tickets", tags=["support"])


def _text(value: str | None, field: str, *, lo: int, hi: int, label: str) -> str:
    v = (value or "").strip()
    if len(v) < lo or len(v) > hi:
        raise ValidationFailed(f"{label} skal være {lo}–{hi} tegn", field_errors=[{"field": field}])
    return v


def _context(path: str | None) -> str:
    p = (path or "").strip()
    return p[:200] if p.startswith("/app") and "//" not in p and "\\" not in p else ""


def _audit(db, ctx: WorkspaceContext, request: Request, action: str, t: SupportTicket, after: dict | None = None):
    record_audit(db, workspace_id=ctx.workspace.id, actor_user_id=ctx.user_id, action=action,
                 object_type="support_ticket", object_id=t.id, after={"number": t.number} | (after or {}),
                 request_id=request.state.request_id)


@router.get("")
def list_tickets(ctx: WorkspaceContext = Depends(require_capability("support.read")), db: OrmSession = Depends(get_db)):
    rows = db.scalars(select(SupportTicket).where(SupportTicket.workspace_id == ctx.workspace.id)
                      .order_by(SupportTicket.status == "resolved", SupportTicket.updated_at.desc()).limit(200))
    items = [svc.customer_summary(t) for t in rows]
    return {"items": items, "open": sum(1 for i in items if i["status"] != "resolved"),
            "categories": list(SUPPORT_CATEGORIES), "max_files": files.MAX_FILES, "max_bytes": files.MAX_BYTES}


@router.post("", status_code=201)
async def create_ticket(request: Request, subject: str = Form(...), category: str = Form("other"),
                        body: str = Form(...), context: str | None = Form(None),
                        files_: list[UploadFile] | None = File(default=None, alias="files"),
                        ctx: WorkspaceContext = Depends(require_capability("support.write")),
                        db: OrmSession = Depends(get_db)):
    subject = _text(subject, "subject", lo=3, hi=160, label="Emnet")
    body = _text(body, "body", lo=1, hi=5000, label="Beskrivelsen")
    if category not in SUPPORT_CATEGORIES:
        raise ValidationFailed("Ukendt kategori", field_errors=[{"field": "category"}])
    uploads = await files.read_files(files_)
    svc.check_new_ticket_rate(db, ctx.workspace.id)
    t = SupportTicket(workspace_id=ctx.workspace.id, number=svc.next_number(db, ctx.workspace.id), subject=subject,
                      category=category, status="open", priority="normal", context_path=_context(context),
                      created_by=ctx.user_id)
    db.add(t)
    db.flush()
    svc.add_message(db, t, author=ctx.user_id, kind="customer", visibility="public", body=body, uploads=uploads)
    _audit(db, ctx, request, "support.ticket_created", t, {"category": category, "attachments": len(uploads)})
    db.commit()
    return svc.customer_detail(db, t)


@router.get("/{number}")
def get_ticket(number: int, ctx: WorkspaceContext = Depends(require_capability("support.read")),
               db: OrmSession = Depends(get_db)):
    return svc.customer_detail(db, svc.ticket_for_customer(db, ctx.workspace.id, number))


@router.post("/{number}/messages", status_code=201)
async def reply(number: int, request: Request, body: str = Form(...),
                files_: list[UploadFile] | None = File(default=None, alias="files"),
                ctx: WorkspaceContext = Depends(require_capability("support.write")), db: OrmSession = Depends(get_db)):
    body = _text(body, "body", lo=1, hi=5000, label="Beskeden")
    uploads = await files.read_files(files_)
    t = svc.ticket_for_customer(db, ctx.workspace.id, number, lock=True)
    svc.check_message_rate(db, t.id)
    svc.add_message(db, t, author=ctx.user_id, kind="customer", visibility="public", body=body, uploads=uploads)
    if t.status in ("waiting_customer", "resolved"):
        svc.set_status(t, "open")  # back to Dialogbot – a reply on a closed ticket reopens it
    _audit(db, ctx, request, "support.ticket_replied", t, {"attachments": len(uploads), "status": t.status})
    db.commit()
    return svc.customer_detail(db, t)


@router.post("/{number}/resolve")
def resolve(number: int, request: Request, ctx: WorkspaceContext = Depends(require_capability("support.write")),
            db: OrmSession = Depends(get_db)):
    t = svc.ticket_for_customer(db, ctx.workspace.id, number, lock=True)
    if t.status != "resolved":
        svc.set_status(t, "resolved")
        _audit(db, ctx, request, "support.ticket_resolved", t)
        db.commit()
    return svc.customer_detail(db, t)


@router.post("/{number}/reopen")
def reopen(number: int, request: Request, ctx: WorkspaceContext = Depends(require_capability("support.write")),
           db: OrmSession = Depends(get_db)):
    t = svc.ticket_for_customer(db, ctx.workspace.id, number, lock=True)
    if t.status != "resolved":
        raise Conflict("Sagen er ikke afsluttet", code="not_resolved")
    svc.set_status(t, "open")
    _audit(db, ctx, request, "support.ticket_reopened", t)
    db.commit()
    return svc.customer_detail(db, t)


@router.get("/{number}/attachments/{attachment_id}")
def download(number: int, attachment_id: uuid.UUID, ctx: WorkspaceContext = Depends(require_capability("support.read")),
             db: OrmSession = Depends(get_db)):
    t = svc.ticket_for_customer(db, ctx.workspace.id, number)
    # Only an attachment of a PUBLIC message on this workspace's ticket (DB-016: never one on an internal note).
    row = db.scalar(select(SupportAttachment).join(SupportMessage, SupportMessage.id == SupportAttachment.message_id)
                    .where(SupportAttachment.id == attachment_id, SupportAttachment.ticket_id == t.id,
                           SupportAttachment.workspace_id == ctx.workspace.id, SupportMessage.visibility == "public"))
    if row is None:
        raise NotFound("Filen findes ikke")
    return files.download(row)

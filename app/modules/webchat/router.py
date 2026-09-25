"""Workspace-side webchat: settings (W01), embed code and the conversation list."""
from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session as OrmSession

from app.core.audit import record_audit
from app.core.auth import WorkspaceContext, get_scoped, require_capability
from app.core.errors import Conflict
from app.core.pagination import PageParams, page
from app.db import get_db
from app.models import Conversation, ConversationMessage, WebchatSettings
from app.modules.setup.checks import invalidate_checks
from app.modules.webchat import service

router = APIRouter(prefix="/workspaces/{workspace_id}", tags=["webchat"])


class SettingsIn(BaseModel):
    expected_version: int
    enabled: bool
    allowed_origins: list[str] = Field(default_factory=list, max_length=service.MAX_ORIGINS)
    greeting: str = Field(default="", max_length=300)


def settings_out(db: OrmSession, s: WebchatSettings) -> dict:
    base = service.api_origin()
    return {
        "version": s.version,
        "enabled": s.enabled,
        "widget_key": s.widget_key,
        "allowed_origins": s.allowed_origins,
        "greeting": s.greeting,
        "effective_greeting": service.greeting_text(db, s),
        "available": not service.unavailable_reasons(db, s),
        "unavailable_reasons": service.unavailable_reasons(db, s),
        "last_seen_at": s.last_seen_at.isoformat() if s.last_seen_at else None,
        "last_seen_origin": s.last_seen_origin,
        "embed_code": f'<script src="{base}/api/v1/public/webchat/loader.js" data-dialogbot-key="{s.widget_key}" async></script>',
        "limits": {"max_message_chars": service.MAX_MESSAGE_CHARS, "max_visitor_messages": service.MAX_VISITOR_MESSAGES,
                   "max_new_conversations_per_hour": service.MAX_NEW_CONVERSATIONS_PER_HOUR},
    }


def _audit_view(s: WebchatSettings) -> dict:
    return {"enabled": s.enabled, "allowed_origins": list(s.allowed_origins), "greeting": s.greeting}


@router.get("/webchat")
def get_settings(ctx: WorkspaceContext = Depends(require_capability("webchat.read")), db: OrmSession = Depends(get_db)):
    s = service.get_or_create(db, ctx.workspace.id)
    db.commit()
    return settings_out(db, s)


@router.put("/webchat")
def update_settings(body: SettingsIn, request: Request, ctx: WorkspaceContext = Depends(require_capability("webchat.manage")),
                    db: OrmSession = Depends(get_db)):
    s = service.get_or_create(db, ctx.workspace.id)
    s = db.scalar(select(WebchatSettings).where(WebchatSettings.workspace_id == ctx.workspace.id).with_for_update())
    if body.expected_version != s.version:
        raise Conflict(f"Indstillingerne er ændret af en anden (version {s.version}). Genindlæs og prøv igen.",
                       code="version_conflict", extra={"current_version": s.version})
    origins = sorted({service.normalize_origin(o) for o in body.allowed_origins if o.strip()})
    before = _audit_view(s)
    s.allowed_origins, s.greeting = origins, body.greeting.strip()
    if body.enabled:
        reasons = service.unavailable_reasons(db, s, ignore_enabled=True)
        if reasons:
            raise Conflict("Widgetten kan ikke slås til endnu", code="webchat_not_ready", extra={"reasons": reasons})
    s.enabled = body.enabled
    s.version += 1
    invalidate_checks(db, ctx.workspace.id, changed_area="integrations", reason="webchat.updated")
    record_audit(db, workspace_id=ctx.workspace.id, actor_user_id=ctx.user_id, action="webchat.updated",
                 object_type="webchat_settings", object_id=ctx.workspace.id, before=before, after=_audit_view(s),
                 request_id=request.state.request_id)
    db.commit()
    return settings_out(db, s)


@router.post("/webchat/rotate-key")
def rotate_key(request: Request, ctx: WorkspaceContext = Depends(require_capability("webchat.manage")),
               db: OrmSession = Depends(get_db)):
    """New widget key: the old embed code stops working immediately."""
    s = service.get_or_create(db, ctx.workspace.id)
    s.widget_key = service.new_widget_key()
    s.version += 1
    s.last_seen_at = s.last_seen_origin = None
    invalidate_checks(db, ctx.workspace.id, changed_area="integrations", reason="webchat.key_rotated")
    record_audit(db, workspace_id=ctx.workspace.id, actor_user_id=ctx.user_id, action="webchat.key_rotated",
                 object_type="webchat_settings", object_id=ctx.workspace.id, request_id=request.state.request_id)
    db.commit()
    return settings_out(db, s)


class ConversationOut(BaseModel):
    id: uuid.UUID
    channel: str
    origin: str | None
    status: str
    visitor_message_count: int
    created_at: datetime
    last_message_at: datetime
    preview: str | None


@router.get("/conversations")
def list_conversations(p: PageParams = Depends(), ctx: WorkspaceContext = Depends(require_capability("conversations.read")),
                       db: OrmSession = Depends(get_db)):
    q = select(Conversation).where(Conversation.workspace_id == ctx.workspace.id)
    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
    rows = db.scalars(q.order_by(Conversation.last_message_at.desc()).limit(p.limit).offset(p.offset)).all()
    first = {}
    if rows:
        for cid, text in db.execute(
            select(ConversationMessage.conversation_id, ConversationMessage.text)
            .where(ConversationMessage.conversation_id.in_([c.id for c in rows]), ConversationMessage.role == "visitor")
            .order_by(ConversationMessage.conversation_id, ConversationMessage.created_at)
        ):
            first.setdefault(cid, text)
    items = [ConversationOut(id=c.id, channel=c.channel, origin=c.origin, status=c.status,
                             visitor_message_count=c.visitor_message_count, created_at=c.created_at,
                             last_message_at=c.last_message_at, preview=(first.get(c.id) or "")[:160] or None)
             .model_dump(mode="json") for c in rows]
    return page(items, total, p)


@router.get("/conversations/{conversation_id}")
def get_conversation(conversation_id: uuid.UUID, ctx: WorkspaceContext = Depends(require_capability("conversations.read")),
                     db: OrmSession = Depends(get_db)):
    conv = get_scoped(db, Conversation, conversation_id, ctx.workspace.id)
    return {"id": str(conv.id), "channel": conv.channel, "origin": conv.origin, "status": conv.status,
            "created_at": conv.created_at.isoformat(),
            "messages": [service.message_out(m) for m in service.messages_of(db, conv)]}

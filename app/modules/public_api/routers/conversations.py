from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from app.core.auth import get_scoped
from app.db import get_db
from app.models import Conversation, ConversationMessage
from app.modules.public_api import cursor
from app.modules.public_api.auth import PublicPrincipal, require_scope
from app.modules.public_api.schemas import v1

router = APIRouter(prefix="/workspaces/{workspace_id}", tags=["conversations"])


@router.get("/conversations", response_model=v1.Page[v1.Conversation], summary="Samtaler, nyeste aktivitet først")
def list_conversations(p: cursor.CursorParams = Depends(),
                       channel: str | None = Query(default=None, pattern="^(webchat|phone)$"),
                       status: str | None = Query(default=None, max_length=16),
                       principal: PublicPrincipal = Depends(require_scope("conversations:read")),
                       db: OrmSession = Depends(get_db)):
    q = select(Conversation).where(Conversation.workspace_id == principal.workspace_id)
    if channel:
        q = q.where(Conversation.channel == channel)
    if status:
        q = q.where(Conversation.status == status)
    rows = list(db.scalars(cursor.apply(q, p, Conversation.last_message_at, Conversation.id)))
    reveal = principal.has("contacts:read")
    return cursor.page(rows, p, lambda c: c.last_message_at, lambda c: c.id, lambda c: v1.conversation_out(c, reveal))


@router.get("/conversations/{conversation_id}", response_model=v1.Conversation, summary="Én samtale")
def get_conversation(conversation_id: uuid.UUID, principal: PublicPrincipal = Depends(require_scope("conversations:read")),
                     db: OrmSession = Depends(get_db)) -> v1.Conversation:
    return v1.conversation_out(get_scoped(db, Conversation, conversation_id, principal.workspace_id),
                               principal.has("contacts:read"))


@router.get("/conversations/{conversation_id}/messages", response_model=v1.Page[v1.Message],
                   summary="Beskederne i en samtale, ældste først")
def list_messages(conversation_id: uuid.UUID, limit: int = Query(200, ge=1, le=500),
                  principal: PublicPrincipal = Depends(require_scope("conversations:read")),
                  db: OrmSession = Depends(get_db)):
    conv = get_scoped(db, Conversation, conversation_id, principal.workspace_id)
    rows = db.scalars(select(ConversationMessage).where(ConversationMessage.conversation_id == conv.id)
                      .order_by(ConversationMessage.created_at, ConversationMessage.id).limit(limit)).all()
    return {"items": [v1.message_out(m) for m in rows], "next_cursor": None}

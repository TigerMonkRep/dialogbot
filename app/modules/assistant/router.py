"""The assistant in the app (customer side): ask or say what to change; apply or decline a proposed change."""
from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session as OrmSession

from app.core.auth import WorkspaceContext, require_capability
from app.db import get_db
from app.modules.assistant import service

router = APIRouter(prefix="/workspaces/{workspace_id}/assistant/changes", tags=["assistant"])


class Turn(BaseModel):
    role: Literal["user", "assistant"]
    text: str = Field(max_length=2000)


class ChangeIn(BaseModel):
    text: str = Field(min_length=2, max_length=1000)
    context: str | None = Field(default=None, max_length=80)  # the page the person is on, e.g. "/app/viden"
    history: list[Turn] = Field(default_factory=list, max_length=20)  # the conversation so far, oldest first


@router.post("")
def propose(body: ChangeIn, request: Request, ctx: WorkspaceContext = Depends(require_capability("workspace.read")),
            db: OrmSession = Depends(get_db)):
    """One turn: an answer with a link, a question, a change shown as before → after (nothing is saved before «Godkend»)
    or a wish recorded for Dialogbot's team. Anyone in the workspace may ask; a change needs the role it needs."""
    return service.propose(db, ctx, text=body.text, page=body.context, request_id=request.state.request_id,
                           history=[t.model_dump() for t in body.history])


@router.post("/{proposal_id}/apply")
def apply(proposal_id: uuid.UUID, request: Request, ctx: WorkspaceContext = Depends(require_capability("assistant.change")),
          db: OrmSession = Depends(get_db)):
    return service.apply(db, ctx, proposal_id, request_id=request.state.request_id)


@router.post("/{proposal_id}/decline")
def decline(proposal_id: uuid.UUID, request: Request, ctx: WorkspaceContext = Depends(require_capability("assistant.change")),
            db: OrmSession = Depends(get_db)):
    return service.decline(db, ctx, proposal_id, request_id=request.state.request_id)

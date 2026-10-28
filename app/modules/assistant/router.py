"""Assistant «Ændr noget» (customer side): propose a change in words, then apply or decline it."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session as OrmSession

from app.core.auth import WorkspaceContext, require_capability
from app.db import get_db
from app.modules.assistant import service

router = APIRouter(prefix="/workspaces/{workspace_id}/assistant/changes", tags=["assistant"])


class ChangeIn(BaseModel):
    text: str = Field(min_length=2, max_length=1000)
    context: str | None = Field(default=None, max_length=80)  # the page the person is on, e.g. "/app/viden"


@router.post("")
def propose(body: ChangeIn, request: Request, ctx: WorkspaceContext = Depends(require_capability("assistant.change")),
            db: OrmSession = Depends(get_db)):
    """The model turns the words into one known change and the answer shows it as before → after. Nothing is saved."""
    return service.propose(db, ctx, text=body.text, page=body.context, request_id=request.state.request_id)


@router.post("/{proposal_id}/apply")
def apply(proposal_id: uuid.UUID, request: Request, ctx: WorkspaceContext = Depends(require_capability("assistant.change")),
          db: OrmSession = Depends(get_db)):
    return service.apply(db, ctx, proposal_id, request_id=request.state.request_id)


@router.post("/{proposal_id}/decline")
def decline(proposal_id: uuid.UUID, request: Request, ctx: WorkspaceContext = Depends(require_capability("assistant.change")),
            db: OrmSession = Depends(get_db)):
    return service.decline(db, ctx, proposal_id, request_id=request.state.request_id)

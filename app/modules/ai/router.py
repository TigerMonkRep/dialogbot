from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session as OrmSession

from app.core.auth import WorkspaceContext, require_capability
from app.db import get_db
from app.modules.ai import service

router = APIRouter(prefix="/workspaces/{workspace_id}", tags=["ai"])


class PreviewIn(BaseModel):
    message: str = Field(min_length=1, max_length=2000)


@router.post("/assistant/preview")
def assistant_preview(body: PreviewIn, ctx: WorkspaceContext = Depends(require_capability("assistant.preview")),
                      db: OrmSession = Depends(get_db)):
    """Ask the assistant one question, answered only from approved knowledge. Internal test tool:
    nothing is sent to a customer. 501 when no AI provider is configured; 409 without approved knowledge."""
    return service.preview_reply(db, ctx.workspace, ctx.user_id, body.message.strip())


@router.get("/ai/usage")
def ai_usage(days: int = Query(default=30, ge=1, le=366),
             ctx: WorkspaceContext = Depends(require_capability("ai_usage.read")), db: OrmSession = Depends(get_db)):
    """Model calls and tokens for this workspace, grouped by model, prompt version and outcome."""
    return service.usage_summary(db, ctx.workspace.id, days)

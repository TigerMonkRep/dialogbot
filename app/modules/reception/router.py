from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session as OrmSession

from app.config import get_settings
from app.core.audit import record_audit
from app.core.auth import WorkspaceContext, require_capability
from app.core.errors import Conflict, ValidationFailed
from app.db import get_db
from app.models import Call, Conversation, Lead, PhoneNumber, ReceptionScript, WebchatSettings
from app.modules.reception import service

router = APIRouter(prefix="/workspaces/{workspace_id}/reception", tags=["reception"])


class ScriptIn(BaseModel):
    expected_version: int
    persona_name: str = Field(default="", max_length=60)
    address_form: str = "du"
    greeting: str = Field(default="", max_length=400)
    collect: list[str] = Field(default_factory=list, max_length=10)
    escalation: str = Field(default="", max_length=800)
    avoid: str = Field(default="", max_length=800)
    closing: str = Field(default="", max_length=300)


def script_out(s: ReceptionScript) -> dict:
    return {"version": s.version, **{k: getattr(s, k) for k in service.FIELDS},
            "updated_at": s.updated_at.isoformat() if s.updated_at else None}


@router.get("/script")
def get_script(ctx: WorkspaceContext = Depends(require_capability("reception.read")), db: OrmSession = Depends(get_db)):
    return script_out(service.get(db, ctx.workspace))


@router.put("/script")
def put_script(body: ScriptIn, request: Request, ctx: WorkspaceContext = Depends(require_capability("reception.manage")),
               db: OrmSession = Depends(get_db)):
    if body.address_form not in ("du", "De"):
        raise ValidationFailed("Tiltaleform skal være du eller De", field_errors=[{"field": "address_form"}])
    s = db.get(ReceptionScript, ctx.workspace.id)
    current = s.version if s else 0
    if body.expected_version != current:
        raise Conflict("Manuskriptet er ændret af en anden. Genindlæs.", code="version_conflict")
    before = script_out(s) if s else None
    if s is None:
        s = ReceptionScript(workspace_id=ctx.workspace.id, version=0)
        db.add(s)
    for k in service.FIELDS:
        v = getattr(body, k)
        setattr(s, k, [c.strip() for c in v if c.strip()] if k == "collect" else v.strip())
    s.version = current + 1
    s.updated_by = ctx.user_id
    db.flush()
    record_audit(db, workspace_id=ctx.workspace.id, actor_user_id=ctx.user_id, action="reception.script_updated",
                 object_type="reception_script", object_id=ctx.workspace.id, before=before,
                 after={k: getattr(s, k) for k in service.FIELDS}, request_id=request.state.request_id)
    db.commit()
    db.refresh(s)
    return script_out(s)


@router.post("/script/suggestions")
def suggest_script(ctx: WorkspaceContext = Depends(require_capability("reception.manage")),
                   db: OrmSession = Depends(get_db)):
    """AI proposal for the manuscript. Nothing is saved; the owner edits and saves."""
    from app.modules.ai import suggest

    return suggest.script(db, ctx.workspace, ctx.user_id)


@router.get("/overview")
def overview(ctx: WorkspaceContext = Depends(require_capability("reception.read")), db: OrmSession = Depends(get_db)):
    """Channel status and the last 7 days at a glance."""
    ws = ctx.workspace
    since = datetime.now(UTC) - timedelta(days=7)
    wc = db.get(WebchatSettings, ws.id)
    numbers = db.scalars(select(PhoneNumber).where(PhoneNumber.workspace_id == ws.id)).all()
    count = lambda q: db.scalar(q) or 0  # noqa: E731
    return {
        "channels": {
            "phone": {"configured": bool(get_settings().vapi_server_secret),
                      "numbers": [{"e164": n.e164, "active": n.active, "voice": bool(n.voice_id)} for n in numbers]},
            "webchat": {"enabled": bool(wc and wc.enabled), "origins": len(wc.allowed_origins) if wc else 0},
        },
        "script_configured": not service.is_empty(service.get(db, ws)),
        "last_7_days": {
            "conversations": count(select(func.count(Conversation.id)).where(Conversation.workspace_id == ws.id,
                                                                             Conversation.created_at >= since)),
            "calls": count(select(func.count(Call.id)).where(Call.workspace_id == ws.id, Call.created_at >= since)),
            "leads": count(select(func.count(Lead.id)).where(Lead.workspace_id == ws.id, Lead.created_at >= since)),
        },
    }

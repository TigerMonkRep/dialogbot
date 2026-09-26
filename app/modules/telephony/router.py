from __future__ import annotations

import json
import uuid

from fastapi import APIRouter, Depends, Header, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as OrmSession

from app.core.audit import record_audit
from app.core.auth import WorkspaceContext, get_scoped, require_capability
from app.core.errors import ApiError, Conflict, ValidationFailed
from app.db import get_db
from app.models import Call, PhoneNumber
from app.modules.setup.checks import invalidate_checks
from app.modules.telephony import vapi

webhook_router = APIRouter(prefix="/webhooks", tags=["webhooks"])
router = APIRouter(prefix="/workspaces/{workspace_id}", tags=["telephony"])


@webhook_router.post("/vapi")
async def vapi_webhook(request: Request, db: OrmSession = Depends(get_db),
                       authorization: str | None = Header(default=None),
                       x_vapi_secret: str | None = Header(default=None)):
    vapi.verify(authorization, x_vapi_secret)
    try:
        body = json.loads(await request.body())
    except ValueError as e:
        raise ValidationFailed("Ugyldig JSON") from e
    message = body.get("message") if isinstance(body, dict) else None
    if not isinstance(message, dict):
        raise ValidationFailed("Mangler 'message'")
    kind = str(message.get("type", ""))
    if kind == "assistant-request":
        number = vapi.find_number(db, message)
        if number is None or not number.active:
            return {"error": "Nummeret er ikke tilknyttet et aktivt arbejdsrum."}
        try:
            return vapi.assistant_config(db, number)
        except ApiError as e:  # e.g. no approved knowledge: the provider plays its error handling
            return {"error": e.message}
    if kind == "end-of-call-report":
        call_id = str((message.get("call") or {}).get("id") or "")
        if db.scalar(select(Call.id).where(Call.provider_call_id == call_id)) if call_id else None:
            return {"received": True, "duplicate": True}
        outcome = vapi.end_of_call(db, message)
        if outcome == "duplicate":
            return {"received": True, "duplicate": True}
        vapi.record_event(db, f"{call_id}:{kind}", kind, {"call_id": call_id, "type": kind}, outcome)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            return {"received": True, "duplicate": True}
        return {"received": True, "duplicate": False, "outcome": outcome}
    return {"received": True, "outcome": "ignored"}


class NumberIn(BaseModel):
    e164: str = Field(max_length=20)
    provider_number_id: str | None = Field(default=None, max_length=100)
    label: str = Field(default="", max_length=100)
    greeting: str = Field(default="", max_length=500)
    voice_id: str = Field(default="", max_length=64)
    voice_model: str = Field(default=vapi.VOICE_MODELS[0], max_length=40)
    speaking_style: str = Field(default="", max_length=1000)


class NumberPatch(BaseModel):
    active: bool | None = None
    label: str | None = Field(default=None, max_length=100)
    greeting: str | None = Field(default=None, max_length=500)
    voice_id: str | None = Field(default=None, max_length=64)
    voice_model: str | None = Field(default=None, max_length=40)
    speaking_style: str | None = Field(default=None, max_length=1000)


def _check_voice(voice_id: str | None, voice_model: str | None) -> None:
    if voice_id and not vapi.VOICE_ID.match(voice_id.strip()):
        raise ValidationFailed("Stemme-id'et skal være ElevenLabs' id (kun bogstaver og tal), fx fra stemmebiblioteket",
                               field_errors=[{"field": "voice_id"}])
    if voice_model is not None and voice_model not in vapi.VOICE_MODELS:
        raise ValidationFailed("Ukendt stemmemodel", field_errors=[{"field": "voice_model"}])


def number_out(n: PhoneNumber) -> dict:
    return {"id": str(n.id), "e164": n.e164, "provider": n.provider, "provider_number_id": n.provider_number_id,
            "label": n.label, "active": n.active, "greeting": n.greeting, "voice_id": n.voice_id,
            "voice_model": n.voice_model, "speaking_style": n.speaking_style, "voice": vapi.voice_config(n),
            "created_at": n.created_at.isoformat()}


@router.get("/phone-numbers")
def list_numbers(ctx: WorkspaceContext = Depends(require_capability("telephony.read")), db: OrmSession = Depends(get_db)):
    from app.config import get_settings

    rows = db.scalars(select(PhoneNumber).where(PhoneNumber.workspace_id == ctx.workspace.id).order_by(PhoneNumber.created_at))
    return {"items": [number_out(n) for n in rows],
            "webhook_url": f"{get_settings().public_base_url}/api/v1/webhooks/vapi",
            "configured": bool(get_settings().vapi_server_secret)}


@router.post("/phone-numbers", status_code=201)
def add_number(body: NumberIn, request: Request, ctx: WorkspaceContext = Depends(require_capability("telephony.manage")),
               db: OrmSession = Depends(get_db)):
    e164 = vapi.normalize_e164(body.e164)
    _check_voice(body.voice_id, body.voice_model)
    if not vapi.E164.match(e164):
        raise ValidationFailed("Nummeret skal være i internationalt format, fx +4570123456",
                               field_errors=[{"field": "e164"}])
    n = PhoneNumber(workspace_id=ctx.workspace.id, e164=e164, provider="vapi",
                    provider_number_id=(body.provider_number_id or "").strip() or None, label=body.label.strip(),
                    greeting=body.greeting.strip(), voice_id=body.voice_id.strip(), voice_model=body.voice_model,
                    speaking_style=body.speaking_style.strip())
    db.add(n)
    try:
        db.flush()
    except IntegrityError as e:
        db.rollback()
        raise Conflict("Nummeret er allerede tilknyttet", code="number_taken") from e
    invalidate_checks(db, ctx.workspace.id, changed_area="integrations", reason="telephony.number_added")
    record_audit(db, workspace_id=ctx.workspace.id, actor_user_id=ctx.user_id, action="telephony.number_added",
                 object_type="phone_number", object_id=n.id, after=number_out(n), request_id=request.state.request_id)
    db.commit()
    return number_out(n)


@router.patch("/phone-numbers/{number_id}")
def update_number(number_id: uuid.UUID, body: NumberPatch, request: Request,
                  ctx: WorkspaceContext = Depends(require_capability("telephony.manage")), db: OrmSession = Depends(get_db)):
    n = get_scoped(db, PhoneNumber, number_id, ctx.workspace.id)
    _check_voice(body.voice_id, body.voice_model)
    before = number_out(n)
    for k, v in body.model_dump(exclude_unset=True).items():
        if v is not None:
            setattr(n, k, v.strip() if isinstance(v, str) else v)
    invalidate_checks(db, ctx.workspace.id, changed_area="integrations", reason="telephony.number_updated")
    record_audit(db, workspace_id=ctx.workspace.id, actor_user_id=ctx.user_id, action="telephony.number_updated",
                 object_type="phone_number", object_id=n.id, before=before, after=number_out(n),
                 request_id=request.state.request_id)
    db.commit()
    return number_out(n)


class PreviewIn(BaseModel):
    voice_id: str | None = Field(default=None, max_length=64)
    voice_model: str | None = Field(default=None, max_length=40)
    text: str | None = Field(default=None, max_length=vapi.PREVIEW_TEXT_MAX)


@router.post("/phone-numbers/{number_id}/voice-preview", response_class=Response,
             responses={200: {"content": {"audio/mpeg": {}}}})
def voice_preview(number_id: uuid.UUID, body: PreviewIn,
                  ctx: WorkspaceContext = Depends(require_capability("telephony.manage")),
                  db: OrmSession = Depends(get_db)):
    """Play the (possibly unsaved) voice choice with the number's greeting. Nothing is stored."""
    n = get_scoped(db, PhoneNumber, number_id, ctx.workspace.id)
    voice_id = (body.voice_id if body.voice_id is not None else n.voice_id).strip()
    voice_model = body.voice_model or n.voice_model
    _check_voice(voice_id, voice_model)
    if not voice_id:
        raise ValidationFailed("Vælg en stemme først", field_errors=[{"field": "voice_id"}])
    text = (body.text or "").strip() or n.greeting.strip() or vapi.DEFAULT_GREETING.format(name=ctx.workspace.name)
    audio = vapi.voice_preview(voice_id, voice_model, text)
    return Response(content=audio, media_type="audio/mpeg", headers={"cache-control": "no-store"})


@router.get("/calls")
def list_calls(limit: int = 50, ctx: WorkspaceContext = Depends(require_capability("telephony.read")),
               db: OrmSession = Depends(get_db)):
    rows = db.scalars(select(Call).where(Call.workspace_id == ctx.workspace.id)
                      .order_by(Call.created_at.desc()).limit(max(1, min(limit, 200))))
    return {"items": [{"id": str(c.id), "from_number": c.from_number, "to_number": c.to_number,
                       "started_at": c.started_at.isoformat() if c.started_at else None,
                       "duration_seconds": c.duration_seconds, "ended_reason": c.ended_reason, "summary": c.summary,
                       "conversation_id": str(c.conversation_id) if c.conversation_id else None} for c in rows]}

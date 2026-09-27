"""Customer API for the Danish voice library (per workspace)."""
from __future__ import annotations

import threading
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from app.config import get_settings
from app.core.audit import record_audit
from app.core.auth import WorkspaceContext, get_scoped, require_capability
from app.core.errors import ApiError, Conflict, ValidationFailed
from app.db import get_db
from app.models import Campaign, PhoneNumber
from app.modules.setup.checks import invalidate_checks
from app.modules.voices import danish, engine, service, storage

router = APIRouter(prefix="/workspaces/{workspace_id}/voices", tags=["voices"])
_preview_slots = threading.BoundedSemaphore(4)  # per API process: previews never starve call audio
_ws_busy: set[uuid.UUID] = set()
_ws_lock = threading.Lock()


def _assignments(db: OrmSession, ws_id: uuid.UUID) -> dict:
    s = service.settings(db, ws_id)
    return {
        "workspace_default": str(s.default_profile_id) if s.default_profile_id else None,
        "phone_numbers": [{"id": str(n.id), "e164": n.e164, "label": n.label,
                           "voice_profile_id": str(n.voice_profile_id) if n.voice_profile_id else None}
                          for n in db.scalars(select(PhoneNumber).where(PhoneNumber.workspace_id == ws_id))],
        "campaigns": [{"id": str(c.id), "name": c.name, "status": c.status,
                       "voice_profile_id": str(c.voice_profile_id) if c.voice_profile_id else None}
                      for c in db.scalars(select(Campaign).where(Campaign.workspace_id == ws_id).order_by(Campaign.created_at))],
    }


def settings_out(db: OrmSession, ws_id: uuid.UUID) -> dict:
    s = service.settings(db, ws_id)
    return {"version": s.version, "default_profile_id": str(s.default_profile_id) if s.default_profile_id else None,
            "fallback": s.fallback, "pronunciations": s.pronunciations, "pronunciation_version": s.pronunciation_version}


@router.get("")
def list_voices(ctx: WorkspaceContext = Depends(require_capability("voices.read")), db: OrmSession = Depends(get_db)):
    items = [service.profile_out(db, p) for p, _v in service.selectable(db, ctx.workspace.id)]
    out = {"items": items, "engine": engine.status(), "assignments": _assignments(db, ctx.workspace.id),
           "settings": settings_out(db, ctx.workspace.id), "preview_max_chars": get_settings().voice_preview_max_chars}
    db.commit()
    return out


@router.get("/{profile_id}")
def get_voice(profile_id: uuid.UUID, ctx: WorkspaceContext = Depends(require_capability("voices.read")),
              db: OrmSession = Depends(get_db)):
    p, _v = service.get_selectable(db, ctx.workspace.id, profile_id)
    return service.profile_out(db, p, detail=True)


class PreviewIn(BaseModel):
    text: str | None = Field(default=None, max_length=1000)


@router.post("/{profile_id}/preview")
def preview(profile_id: uuid.UUID, body: PreviewIn, ctx: WorkspaceContext = Depends(require_capability("voices.preview")),
            db: OrmSession = Depends(get_db)):
    """A short Danish sample as WAV. Own text is limited, counted and never cached or logged."""
    s = get_settings()
    p, v = service.get_selectable(db, ctx.workspace.id, profile_id)
    own = (body.text or "").strip()
    if len(own) > s.voice_preview_max_chars:
        raise ValidationFailed(f"Højst {s.voice_preview_max_chars} tegn i en stemmeprøve", field_errors=[{"field": "text"}])
    text = own or p.sample_text or service.DEFAULT_SAMPLE
    ws_settings = service.settings(db, ctx.workspace.id)
    spoken = danish.normalize(text, ws_settings.pronunciations if own else None)
    key = None if own else service.cache_key(p, v, spoken, 24000)
    if key and (cached := storage.get(key)) is not None:
        db.commit()
        return Response(cached, media_type="audio/wav", headers={"cache-control": "no-store", "x-voice-version": str(v.id),
                                                                  "x-simulated": "0" if engine.status() == "available" else "1"})
    service.count_usage(db, ctx.workspace.id, "preview", len(spoken), limit_requests=s.voice_preview_daily_limit)
    db.commit()
    with _ws_lock:
        if ctx.workspace.id in _ws_busy:
            raise ApiError("Der er allerede en stemmeprøve i gang", code="voice_preview_busy", status_code=429)
        _ws_busy.add(ctx.workspace.id)
    if not _preview_slots.acquire(timeout=0.1):
        with _ws_lock:
            _ws_busy.discard(ctx.workspace.id)
        raise engine.EngineBusy("Talemotoren er optaget. Prøv igen om lidt.")
    try:
        parts = [engine.synthesize(v, chunk, sample_rate=24000) for chunk in danish.chunks(spoken)]
    finally:
        _preview_slots.release()
        with _ws_lock:
            _ws_busy.discard(ctx.workspace.id)
    audio = engine.wav(b"".join(x.pcm for x in parts), 24000)
    simulated = any(x.simulated for x in parts)
    if key and not simulated:
        storage.put(key, audio, "audio/wav")
    if not own:  # the standard sample proves the chosen voice was heard (setup check G-voice)
        ws = service.settings(db, ctx.workspace.id, lock=True)
        if ws.default_profile_id == p.id:
            ws.last_preview = {"version_id": str(v.id), "at": datetime.now(UTC).isoformat(), "simulated": simulated}
            db.commit()
    return Response(audio, media_type="audio/wav", headers={"cache-control": "no-store", "x-voice-version": str(v.id),
                                                            "x-simulated": "1" if simulated else "0"})


class SettingsIn(BaseModel):
    expected_version: int
    default_profile_id: uuid.UUID | None = None
    fallback: str = Field(default="provider_voice", pattern="^(provider_voice|transfer)$")
    pronunciations: list[dict] = Field(default_factory=list, max_length=200)


@router.put("/settings")
def put_settings(body: SettingsIn, request: Request, ctx: WorkspaceContext = Depends(require_capability("voices.manage")),
                 db: OrmSession = Depends(get_db)):
    s = service.settings(db, ctx.workspace.id, lock=True)
    if s.version != body.expected_version:
        raise Conflict("Stemmeindstillingerne er ændret af en anden. Genindlæs.", code="version_conflict")
    if body.default_profile_id:
        service.get_selectable(db, ctx.workspace.id, body.default_profile_id)
    clean = []
    for e in body.pronunciations:
        term, say = str(e.get("term", "")).strip()[:80], str(e.get("say", "")).strip()[:120]
        if term and say:
            clean.append({"term": term, "say": say})
    changed_voice = s.default_profile_id != body.default_profile_id
    changed_pron = clean != (s.pronunciations or [])
    s.default_profile_id, s.fallback = body.default_profile_id, body.fallback
    if changed_pron:
        s.pronunciations, s.pronunciation_version = clean, s.pronunciation_version + 1
    s.version += 1
    s.updated_at = datetime.now(UTC)
    if changed_voice or changed_pron:
        s.last_preview = None
        invalidate_checks(db, ctx.workspace.id, changed_area="voice", reason="voices.settings_updated")
    record_audit(db, workspace_id=ctx.workspace.id, actor_user_id=ctx.user_id, action="voices.settings_updated",
                 object_type="workspace_voice_settings", object_id=ctx.workspace.id,
                 after={"default_profile_id": str(body.default_profile_id) if body.default_profile_id else None,
                        "fallback": body.fallback, "pronunciation_version": s.pronunciation_version},
                 request_id=request.state.request_id)
    db.commit()
    return settings_out(db, ctx.workspace.id)


class AssignIn(BaseModel):
    voice_profile_id: uuid.UUID | None = None


@router.put("/assignments/phone-numbers/{number_id}")
def assign_number(number_id: uuid.UUID, body: AssignIn, request: Request,
                  ctx: WorkspaceContext = Depends(require_capability("voices.manage")), db: OrmSession = Depends(get_db)):
    n = get_scoped(db, PhoneNumber, number_id, ctx.workspace.id)
    if body.voice_profile_id:
        service.get_selectable(db, ctx.workspace.id, body.voice_profile_id)
    n.voice_profile_id = body.voice_profile_id
    invalidate_checks(db, ctx.workspace.id, changed_area="voice", reason="voices.assistant_voice_changed")
    record_audit(db, workspace_id=ctx.workspace.id, actor_user_id=ctx.user_id, action="voices.assistant_voice_changed",
                 object_type="phone_number", object_id=n.id,
                 after={"voice_profile_id": str(body.voice_profile_id) if body.voice_profile_id else None},
                 request_id=request.state.request_id)
    db.commit()
    return _assignments(db, ctx.workspace.id)


@router.put("/assignments/campaigns/{campaign_id}")
def assign_campaign(campaign_id: uuid.UUID, body: AssignIn, request: Request,
                    ctx: WorkspaceContext = Depends(require_capability("voices.manage")), db: OrmSession = Depends(get_db)):
    """Changing a campaign's voice never starts, pauses or re-prices it."""
    c = get_scoped(db, Campaign, campaign_id, ctx.workspace.id)
    if body.voice_profile_id:
        service.get_selectable(db, ctx.workspace.id, body.voice_profile_id)
    c.voice_profile_id = body.voice_profile_id
    record_audit(db, workspace_id=ctx.workspace.id, actor_user_id=ctx.user_id, action="voices.campaign_voice_changed",
                 object_type="campaign", object_id=c.id,
                 after={"voice_profile_id": str(body.voice_profile_id) if body.voice_profile_id else None},
                 request_id=request.state.request_id)
    db.commit()
    return _assignments(db, ctx.workspace.id)

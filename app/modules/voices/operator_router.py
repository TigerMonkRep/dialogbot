"""Operator API: rights records, voice profiles, immutable versions, checks, publication, suspension, rollback.

Only users with `is_platform_operator` (granted by scripts/grant_operator.py) may call these. Every change
is written to the audit log (workspace_id NULL for platform voices, else the owning workspace).
"""
from __future__ import annotations

import hashlib
import re
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session as OrmSession

from app.core.audit import record_audit
from app.core.auth import Principal, get_current_principal
from app.core.errors import Forbidden, NotFound, ValidationFailed
from app.db import get_db
from app.models import AuditLog, VoiceProfile, VoiceRightsRecord, VoiceVersion, Workspace
from app.modules.voices import danish, engine, service, storage

router = APIRouter(prefix="/operator", tags=["voice-operator"])
SLUG = r"^[a-z0-9][a-z0-9-]{2,79}$"
MAX_REFERENCE_BYTES = 20 * 1024 * 1024


def operator(principal: Principal = Depends(get_current_principal)) -> Principal:
    if not principal.user.is_platform_operator:
        raise Forbidden("Kun Dialogbot-operatører har adgang", code="operator_only")
    return principal


def _audit(db, request, principal, p: VoiceProfile | None, action: str, object_type: str, object_id, after: dict | None = None):
    record_audit(db, workspace_id=p.workspace_id if p else None, actor_user_id=principal.user.id, action=action,
                 object_type=object_type, object_id=object_id, after=after, request_id=request.state.request_id)


# --------------------------------------------------------------------------- rights

class RightsIn(BaseModel):
    kind: str = Field(pattern="^(code|model|dataset|speaker_agreement)$")
    subject: str = Field(min_length=2, max_length=200)
    license: str = Field(default="", max_length=200)
    source_url: str = Field(default="", max_length=1000)
    revision: str | None = Field(default=None, max_length=80)
    allowed_uses: str = ""
    restrictions: str = ""
    commercial_use: bool | None = None
    subprocessors: str = ""
    term: str = ""
    termination: str = ""
    basis: str = ""
    notes: str = ""


@router.get("/voice-rights")
def list_rights(_: Principal = Depends(operator), db: OrmSession = Depends(get_db)):
    return {"items": [service.rights_out(r) for r in db.scalars(select(VoiceRightsRecord).order_by(VoiceRightsRecord.created_at))]}


@router.post("/voice-rights", status_code=201)
def add_rights(body: RightsIn, request: Request, principal: Principal = Depends(operator), db: OrmSession = Depends(get_db)):
    r = VoiceRightsRecord(**body.model_dump(), status="unreviewed")
    db.add(r)
    db.flush()
    _audit(db, request, principal, None, "voice_rights.created", "voice_rights_record", r.id, {"subject": r.subject})
    db.commit()
    return service.rights_out(r)


class ReviewIn(BaseModel):
    status: str = Field(pattern="^(verified|blocked|unreviewed)$")
    notes: str = Field(min_length=10, max_length=4000)  # what was actually read, and where


@router.post("/voice-rights/{rights_id}/review")
def review_rights(rights_id: uuid.UUID, body: ReviewIn, request: Request, principal: Principal = Depends(operator),
                  db: OrmSession = Depends(get_db)):
    """A person's review outcome. The API records who and when; it never infers a verdict."""
    r = db.get(VoiceRightsRecord, rights_id)
    if r is None:
        raise NotFound("Rettighedsposten findes ikke")
    r.status, r.reviewed_by, r.reviewed_at = body.status, principal.user.id, datetime.now(UTC)
    r.notes = (r.notes + "\n\n" if r.notes else "") + f"[{r.reviewed_at:%Y-%m-%d} {principal.user.email}] {body.notes}"
    _audit(db, request, principal, None, "voice_rights.reviewed", "voice_rights_record", r.id, {"status": body.status})
    db.commit()
    return service.rights_out(r)


# --------------------------------------------------------------------------- profiles and versions

class ProfileIn(BaseModel):
    slug: str = Field(pattern=SLUG)
    display_name: str = Field(min_length=2, max_length=80)
    gender: str = Field(default="unknown", pattern="^(female|male|unknown)$")
    dialect: str | None = Field(default=None, max_length=80)
    dialect_basis: str = ""
    age_description: str | None = Field(default=None, max_length=80)
    timbre: str | None = Field(default=None, max_length=120)
    source: str = ""
    sample_text: str = Field(default="", max_length=300)
    visibility: str = Field(default="platform", pattern="^(platform|workspace)$")
    workspace_id: uuid.UUID | None = None


class ProfilePatch(BaseModel):
    display_name: str | None = Field(default=None, min_length=2, max_length=80)
    gender: str | None = Field(default=None, pattern="^(female|male|unknown)$")
    dialect: str | None = None
    dialect_basis: str | None = None
    age_description: str | None = None
    timbre: str | None = None
    sample_text: str | None = Field(default=None, max_length=300)


def _profile(db: OrmSession, profile_id: uuid.UUID) -> VoiceProfile:
    p = db.get(VoiceProfile, profile_id)
    if p is None:
        raise NotFound("Stemmen findes ikke")
    return p


def _full(db: OrmSession, p: VoiceProfile) -> dict:
    versions = db.scalars(select(VoiceVersion).where(VoiceVersion.profile_id == p.id).order_by(VoiceVersion.version.desc()))
    history = db.scalars(select(AuditLog).where(AuditLog.object_id == str(p.id)).order_by(AuditLog.created_at.desc()).limit(50))
    return service.profile_out(db, p, detail=True) | {
        "workspace_id": str(p.workspace_id) if p.workspace_id else None,
        "active_version_id": str(p.active_version_id) if p.active_version_id else None,
        "versions": [service.version_out(v) | {"missing_checks": service.missing_checks(v, p.visibility)} for v in versions],
        "history": [{"action": a.action, "at": a.created_at.isoformat(), "actor_user_id": str(a.actor_user_id) if a.actor_user_id else None,
                     "after": a.after} for a in history]}


@router.get("/voices")
def list_profiles(_: Principal = Depends(operator), db: OrmSession = Depends(get_db)):
    return {"items": [_full(db, p) for p in db.scalars(select(VoiceProfile).order_by(VoiceProfile.created_at))],
            "engine": engine.status(), "engine_health": engine.health()}


@router.post("/voices", status_code=201)
def create_profile(body: ProfileIn, request: Request, principal: Principal = Depends(operator), db: OrmSession = Depends(get_db)):
    if (body.visibility == "workspace") != (body.workspace_id is not None):
        raise ValidationFailed("En privat stemme kræver et arbejdsrum; en platformstemme må ikke have et",
                               field_errors=[{"field": "workspace_id"}])
    if body.workspace_id and db.get(Workspace, body.workspace_id) is None:
        raise NotFound("Arbejdsrummet findes ikke")
    if db.scalar(select(VoiceProfile.id).where(VoiceProfile.slug == body.slug)):
        raise ValidationFailed("ID'et er i brug", field_errors=[{"field": "slug"}])
    p = VoiceProfile(**body.model_dump(), created_by=principal.user.id)
    db.add(p)
    db.flush()
    _audit(db, request, principal, p, "voice.created", "voice_profile", p.id, {"slug": p.slug})
    db.commit()
    return _full(db, p)


@router.patch("/voices/{profile_id}")
def patch_profile(profile_id: uuid.UUID, body: ProfilePatch, request: Request, principal: Principal = Depends(operator),
                  db: OrmSession = Depends(get_db)):
    p = _profile(db, profile_id)
    changes = body.model_dump(exclude_unset=True)
    for k, val in changes.items():
        setattr(p, k, val)
    _audit(db, request, principal, p, "voice.metadata_changed", "voice_profile", p.id, changes)
    db.commit()
    return _full(db, p)


@router.post("/voices/{profile_id}/references", status_code=201)
async def upload_reference(profile_id: uuid.UUID, request: Request, source_id: str = Query(default="", max_length=200),
                           principal: Principal = Depends(operator), db: OrmSession = Depends(get_db)):
    """Upload one reference WAV (body = raw bytes). Stored privately under the voice's own scope."""
    p = _profile(db, profile_id)
    data = await request.body()
    if not data or len(data) > MAX_REFERENCE_BYTES or data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise ValidationFailed("Upload en WAV-fil på højst 20 MB", field_errors=[{"field": "body"}])
    import io
    import wave

    try:
        with wave.open(io.BytesIO(data)) as w:
            seconds = w.getnframes() / w.getframerate()
            rate, channels = w.getframerate(), w.getnchannels()
    except (wave.Error, EOFError) as e:
        raise ValidationFailed("Filen kunne ikke læses som WAV") from e
    sha = hashlib.sha256(data).hexdigest()
    key = f"{storage.workspace_prefix(p.workspace_id)}/voices/{p.slug}/refs/{sha}.wav"
    storage.put(key, data, "audio/wav")
    ref = {"key": key, "sha256": sha, "seconds": round(seconds, 2), "sample_rate": rate, "channels": channels,
           "source_id": re.sub(r"[^\w./:-]", "", source_id)[:200]}
    _audit(db, request, principal, p, "voice.reference_uploaded", "voice_profile", p.id, {"sha256": sha, "seconds": ref["seconds"]})
    db.commit()
    return ref


class VersionIn(BaseModel):
    engine: str = Field(default="chatterbox-multilingual", pattern="^[a-z0-9-]{3,40}$")
    method: str = Field(default="reference_conditioning",
                        pattern="^(reference_conditioning|finetuned_checkpoint|trained_from_scratch)$")
    model_repo: str = Field(min_length=3, max_length=200)
    model_revision: str = Field(pattern="^[0-9a-f]{40}$")  # a pinned commit, never "main"
    checkpoint_key: str | None = None
    references: list[dict] = Field(default_factory=list, max_length=20)
    settings: dict = Field(default_factory=dict)
    rights_record_ids: list[uuid.UUID] = Field(default_factory=list)
    notes: str = ""


ALLOWED_SETTINGS = {"exaggeration": (0.25, 1.0), "cfg_weight": (0.0, 1.0), "temperature": (0.3, 1.2)}


@router.post("/voices/{profile_id}/versions", status_code=201)
def create_version(profile_id: uuid.UUID, body: VersionIn, request: Request, principal: Principal = Depends(operator),
                   db: OrmSession = Depends(get_db)):
    p = _profile(db, profile_id)
    prefix = f"{storage.workspace_prefix(p.workspace_id)}/voices/{p.slug}/"
    refs = []
    for r in body.references:
        key = storage.check_key(str(r.get("key", "")))
        if not key.startswith(prefix):
            raise ValidationFailed("Referenceklip skal tilhøre stemmen selv", field_errors=[{"field": "references"}])
        data = storage.get(key)
        if data is None or hashlib.sha256(data).hexdigest() != r.get("sha256"):
            raise ValidationFailed("Referenceklip mangler eller har forkert checksum", field_errors=[{"field": "references"}])
        refs.append({k: r[k] for k in ("key", "sha256", "seconds", "source_id") if k in r})
    if body.method != "reference_conditioning":
        if not body.checkpoint_key or not body.checkpoint_key.startswith(prefix):
            raise ValidationFailed("Et checkpoint skal ligge under stemmens eget lager", field_errors=[{"field": "checkpoint_key"}])
    settings = {}
    for k, val in body.settings.items():
        if k not in ALLOWED_SETTINGS or not isinstance(val, int | float):
            raise ValidationFailed(f"Ukendt indstilling: {k}", field_errors=[{"field": "settings"}])
        lo, hi = ALLOWED_SETTINGS[k]
        settings[k] = min(hi, max(lo, float(val)))
    for rid in body.rights_record_ids:
        if db.get(VoiceRightsRecord, rid) is None:
            raise ValidationFailed("Ukendt rettighedspost", field_errors=[{"field": "rights_record_ids"}])
    n = (db.scalar(select(func.max(VoiceVersion.version)).where(VoiceVersion.profile_id == p.id)) or 0) + 1
    v = VoiceVersion(profile_id=p.id, version=n, engine=body.engine, method=body.method, model_repo=body.model_repo,
                     model_revision=body.model_revision, checkpoint_key=body.checkpoint_key, references=refs,
                     settings=settings, rights_record_ids=[str(x) for x in body.rights_record_ids], checks={},
                     notes=body.notes, created_by=principal.user.id)
    db.add(v)
    db.flush()
    _audit(db, request, principal, p, "voice.version_created", "voice_profile", p.id, {"version": n, "model_revision": v.model_revision})
    db.commit()
    return _full(db, p)


def _version(db: OrmSession, version_id: uuid.UUID) -> tuple[VoiceProfile, VoiceVersion]:
    v = db.get(VoiceVersion, version_id)
    if v is None:
        raise NotFound("Versionen findes ikke")
    return db.get(VoiceProfile, v.profile_id), v


@router.post("/voice-versions/{version_id}/checks/run")
def run_checks(version_id: uuid.UUID, request: Request, principal: Principal = Depends(operator), db: OrmSession = Depends(get_db)):
    p, v = _version(db, version_id)
    checks = service.run_auto_checks(db, v)
    _audit(db, request, principal, p, "voice.checks_run", "voice_profile", p.id,
           {"version": v.version, "results": {k: c.get("status") for k, c in checks.items()}})
    db.commit()
    return _full(db, p)


class HumanCheckIn(BaseModel):
    passed: bool
    evidence: dict = Field(default_factory=dict)


@router.post("/voice-versions/{version_id}/checks/{name}")
def record_check(version_id: uuid.UUID, name: str, body: HumanCheckIn, request: Request, principal: Principal = Depends(operator),
                 db: OrmSession = Depends(get_db)):
    p, v = _version(db, version_id)
    service.record_human_check(v, name, passed=body.passed, evidence=body.evidence, by=principal.user.id)
    _audit(db, request, principal, p, "voice.check_recorded", "voice_profile", p.id,
           {"version": v.version, "check": name, "passed": body.passed})
    db.commit()
    return _full(db, p)


@router.post("/voice-versions/{version_id}/{action}")
def act(version_id: uuid.UUID, action: str, request: Request, principal: Principal = Depends(operator),
        db: OrmSession = Depends(get_db)):
    if action not in service.TRANSITIONS:
        raise NotFound("Ukendt handling")
    p, v = _version(db, version_id)
    service.transition(db, p, v, action, principal.user.id)
    _audit(db, request, principal, p, f"voice.{action}", "voice_profile", p.id, {"version": v.version, "status": v.status})
    db.commit()
    return _full(db, p)


@router.post("/voices/{profile_id}/rollback")
def rollback(profile_id: uuid.UUID, request: Request, principal: Principal = Depends(operator), db: OrmSession = Depends(get_db)):
    p = _profile(db, profile_id)
    v = service.rollback(db, p, principal.user.id)
    _audit(db, request, principal, p, "voice.rollback", "voice_profile", p.id, {"version": v.version})
    db.commit()
    return _full(db, p)


class SynthIn(BaseModel):
    text: str = Field(min_length=1, max_length=1000)


@router.post("/voice-versions/{version_id}/synthesize")
def operator_synthesize(version_id: uuid.UUID, body: SynthIn, _: Principal = Depends(operator), db: OrmSession = Depends(get_db)):
    """Test clip of any version (also drafts) for review. Not cached."""
    p, v = _version(db, version_id)
    parts = [engine.synthesize(v, c, sample_rate=24000) for c in danish.chunks(danish.normalize(body.text))]
    return Response(engine.wav(b"".join(x.pcm for x in parts), 24000), media_type="audio/wav",
                    headers={"cache-control": "no-store", "x-simulated": "1" if any(x.simulated for x in parts) else "0"})

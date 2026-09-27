"""Own voice: customers record their own voice from a Dialogbot manuscript.

Flow: consent (the speaker types their name under a fixed text; stored verbatim and registered as a
speaker_agreement rights record for review) → record every manuscript sentence in the browser (16-bit PCM WAV,
checked on upload) → submit: a private workspace voice is created from the recordings (reference conditioning) with
a draft version whose automatic checks run. A platform operator reviews the consent record before the voice can be
approved; nothing here approves itself. Withdrawing deletes the recordings and suspends the voice.
"""
from __future__ import annotations

import array
import hashlib
import io
import json
import math
import re
import uuid
import wave
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from app.config import get_settings
from app.core.audit import record_audit
from app.core.auth import WorkspaceContext, require_capability
from app.core.errors import Conflict, NotFound, ValidationFailed
from app.db import get_db
from app.models import (
    BusinessProfile,
    OwnVoiceProject,
    OwnVoiceRecording,
    VoiceProfile,
    VoiceRightsRecord,
    VoiceVersion,
)
from app.modules.voices import danish, service, storage

router = APIRouter(prefix="/workspaces/{workspace_id}/own-voices", tags=["voices"])
MANUSCRIPTS = Path(__file__).resolve().parents[3] / "voice_pipeline" / "manuscripts"
MAX_WAV_BYTES = 6 * 1024 * 1024
RATES = (16000, 22050, 24000, 32000, 44100, 48000)
CONSENT_VERSION = 1
CONSENT_TEXT = (
    "Jeg, {name}, er den person, hvis stemme bliver optaget. Jeg giver {firma} og Dialogbot lov til at lave en "
    "syntetisk udgave af min stemme ud fra optagelserne. Stemmen må kun bruges i {firma}s telefonassistent og "
    "kampagner i Dialogbot og ikke til andre formål eller af andre virksomheder. Jeg ved, at samtalepartnere får "
    "at vide, at de taler med en digital assistent. Jeg kan til enhver tid trække samtykket tilbage. Så stoppes "
    "stemmen med det samme, og optagelserne slettes.")


def _now() -> datetime:
    return datetime.now(UTC)


def _manuscript(kind: str) -> dict:
    if kind not in ("kort", "standard"):
        raise NotFound("Manuskriptet findes ikke")
    return json.loads((MANUSCRIPTS / f"da_{kind}.json").read_text(encoding="utf-8"))


def _clean(v: str | None, default: str) -> str:
    v = re.sub(r"[{}\n\r\t]", "", (v or "").strip())[:60]
    return v or default


def _fill(m: dict, firma: str, ydelse: str, by: str) -> dict:
    out = dict(m)
    out["sentences"] = []
    for s in m["sentences"]:
        text = s["text"].format(firma=firma, ydelse=ydelse, by=by)
        out["sentences"].append(s | {"text": text, "spoken_hint": danish.normalize(text)})
    return out


def _defaults(db: OrmSession, ctx: WorkspaceContext) -> dict:
    bp = db.scalar(select(BusinessProfile).where(BusinessProfile.workspace_id == ctx.workspace.id))
    return {"firma": ctx.workspace.name, "ydelse": "vores ydelser", "by": (bp.city if bp and bp.city else "området")}


def qc_wav(data: bytes) -> dict:
    """Checks a recording without third-party libraries: format, length, level, clipping, silence at the edges."""
    try:
        with wave.open(io.BytesIO(data)) as w:
            ch, width, rate, n = w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()
            frames = w.readframes(n)
    except (wave.Error, EOFError) as e:
        raise ValidationFailed("Optagelsen er ikke en gyldig WAV-fil", field_errors=[{"field": "audio"}]) from e
    if width != 2 or ch not in (1, 2) or rate not in RATES:
        raise ValidationFailed("Optagelsen skal være 16-bit PCM, mono eller stereo, 16–48 kHz",
                               field_errors=[{"field": "audio"}])
    pcm = array.array("h")
    pcm.frombytes(frames[: len(frames) // 2 * 2])
    if ch == 2:
        pcm = array.array("h", ((pcm[i] + pcm[i + 1]) // 2 for i in range(0, len(pcm) - 1, 2)))
    seconds = len(pcm) / rate
    flags = []
    if seconds < 0.8:
        flags.append("for_kort")
    if seconds > 25:
        flags.append("for_lang")
    peak = max((abs(x) for x in pcm), default=0) / 32768
    hop = max(1, rate // 50)
    levels = []
    for i in range(0, len(pcm) - hop + 1, hop):
        seg = pcm[i:i + hop]
        levels.append(20 * math.log10(math.sqrt(sum(x * x for x in seg) / hop) / 32768 + 1e-9))
    loud = sorted(levels)[int(len(levels) * 0.9)] if levels else -120.0
    floor = sorted(levels)[int(len(levels) * 0.05)] if levels else -120.0
    clipped = sum(1 for x in pcm if abs(x) >= 32700) / max(1, len(pcm))
    if loud < -38:
        flags.append("for_lav")
    if clipped > 0.001:
        flags.append("overstyret")
    if loud - floor < 20:
        flags.append("meget_baggrundsstøj")
    return {"seconds": round(seconds, 2), "sample_rate": rate, "peak": round(peak, 3), "speech_db": round(loud, 1),
            "noise_db": round(floor, 1), "clipped_ratio": round(clipped, 5), "flags": flags, "ok": not flags}


def _project(db: OrmSession, ctx: WorkspaceContext, pid: uuid.UUID) -> OwnVoiceProject:
    p = db.get(OwnVoiceProject, pid)
    if p is None or p.workspace_id != ctx.workspace.id:
        raise NotFound("Indtalingen findes ikke")
    return p


def _out(db: OrmSession, p: OwnVoiceProject) -> dict:
    recs = {r.sentence_id: r for r in db.scalars(select(OwnVoiceRecording).where(OwnVoiceRecording.project_id == p.id))}
    total = len(_manuscript(p.manuscript)["sentences"])
    voice = None
    if p.profile_id and (prof := db.get(VoiceProfile, p.profile_id)):
        v = db.scalar(select(VoiceVersion).where(VoiceVersion.profile_id == prof.id).order_by(VoiceVersion.version.desc()))
        rights = db.get(VoiceRightsRecord, p.rights_record_id) if p.rights_record_id else None
        voice = {"profile_id": str(prof.id), "display_name": prof.display_name, "active": prof.active_version_id is not None,
                 "version_status": v.status if v else None,
                 "consent_review": rights.status if rights else "missing"}
    return {"id": str(p.id), "speaker_name": p.speaker_name, "manuscript": p.manuscript, "status": p.status,
            "created_at": p.created_at.isoformat(), "submitted_at": p.submitted_at.isoformat() if p.submitted_at else None,
            "recorded": len(recs), "approved_recordings": sum(1 for r in recs.values() if r.qc.get("ok")), "total": total,
            "recordings": {k: {"seconds": r.seconds, "qc": r.qc} for k, r in recs.items()}, "voice": voice,
            "values": p.consent.get("manuscript_values") or {},
            "consent": {"text": p.consent.get("text"), "typed_name": p.consent.get("typed_name"),
                        "accepted_at": p.consent.get("accepted_at")}}


@router.get("/manuscripts/{kind}")
def get_manuscript(kind: str, firma: str | None = None, ydelse: str | None = None, by: str | None = None,
                   ctx: WorkspaceContext = Depends(require_capability("voices.manage")), db: OrmSession = Depends(get_db)):
    d = _defaults(db, ctx)
    return _fill(_manuscript(kind), _clean(firma, d["firma"]), _clean(ydelse, d["ydelse"]), _clean(by, d["by"])) | {
        "values": {"firma": _clean(firma, d["firma"]), "ydelse": _clean(ydelse, d["ydelse"]), "by": _clean(by, d["by"])},
        "consent_text": CONSENT_TEXT, "consent_version": CONSENT_VERSION}


@router.get("")
def list_projects(ctx: WorkspaceContext = Depends(require_capability("voices.manage")), db: OrmSession = Depends(get_db)):
    ps = db.scalars(select(OwnVoiceProject).where(OwnVoiceProject.workspace_id == ctx.workspace.id)
                    .order_by(OwnVoiceProject.created_at.desc()))
    return {"items": [_out(db, p) for p in ps]}


class ProjectIn(BaseModel):
    speaker_name: str = Field(min_length=2, max_length=120)
    manuscript: str = Field(default="kort", pattern="^(kort|standard)$")
    consent_typed_name: str = Field(min_length=2, max_length=120)
    consent_accepted: bool
    firma: str | None = Field(default=None, max_length=60)
    ydelse: str | None = Field(default=None, max_length=60)
    by: str | None = Field(default=None, max_length=60)
    speaker_gender: str = Field(default="unknown", pattern="^(female|male|unknown)$")  # self-declared


@router.post("", status_code=201)
def create_project(body: ProjectIn, request: Request, ctx: WorkspaceContext = Depends(require_capability("voices.manage")),
                   db: OrmSession = Depends(get_db)):
    if not body.consent_accepted:
        raise ValidationFailed("Indtaleren skal give samtykke", field_errors=[{"field": "consent_accepted"}])
    if body.consent_typed_name.strip().casefold() != body.speaker_name.strip().casefold():
        raise ValidationFailed("Samtykket skal underskrives med indtalerens eget navn",
                               field_errors=[{"field": "consent_typed_name"}])
    d = _defaults(db, ctx)
    firma = _clean(body.firma, d["firma"])
    values = {"firma": firma, "ydelse": _clean(body.ydelse, d["ydelse"]), "by": _clean(body.by, d["by"])}
    text = CONSENT_TEXT.format(name=body.speaker_name.strip(), firma=firma)
    now = _now()
    consent = {"text": text, "version": CONSENT_VERSION, "typed_name": body.consent_typed_name.strip(),
               "accepted_at": now.isoformat(), "user_id": str(ctx.user_id), "workspace_id": str(ctx.workspace.id),
               "manuscript_values": values, "speaker_gender": body.speaker_gender}
    rights = VoiceRightsRecord(
        kind="speaker_agreement", subject=f"Egen stemme: {body.speaker_name.strip()} ({firma})"[:200],
        license=f"Samtykke givet i Dialogbot (version {CONSENT_VERSION})", status="unreviewed",
        allowed_uses=f"Kun {firma}s telefonassistent og kampagner i Dialogbot.", commercial_use=True,
        restrictions="Ikke til andre formål eller virksomheder. Tilbagetrækning stopper stemmen og sletter optagelserne.",
        basis=text, termination="Samtykket kan trækkes tilbage når som helst i Dialogbot.",
        notes=f"Accepteret {now.isoformat()} af bruger {ctx.user_id} i arbejdsrum {ctx.workspace.id}; underskrevet "
              f"'{body.consent_typed_name.strip()}'. Skal gennemgås af en operatør, før stemmen kan godkendes.")
    db.add(rights)
    db.flush()
    p = OwnVoiceProject(workspace_id=ctx.workspace.id, speaker_name=body.speaker_name.strip(), manuscript=body.manuscript,
                        consent=consent, rights_record_id=rights.id, created_by=ctx.user_id)
    db.add(p)
    db.flush()
    record_audit(db, workspace_id=ctx.workspace.id, actor_user_id=ctx.user_id, action="own_voice.consent_given",
                 object_type="own_voice_project", object_id=p.id,
                 after={"speaker_name": p.speaker_name, "consent_version": CONSENT_VERSION, "manuscript": p.manuscript})
    db.commit()
    return _out(db, p)


@router.put("/{project_id}/recordings/{sentence_id}")
async def put_recording(project_id: uuid.UUID, sentence_id: str, request: Request,
                        ctx: WorkspaceContext = Depends(require_capability("voices.manage")), db: OrmSession = Depends(get_db)):
    p = _project(db, ctx, project_id)
    if p.status != "recording":
        raise Conflict("Indtalingen er allerede sendt eller trukket tilbage", code="own_voice_state")
    ids = {s["id"] for s in _manuscript(p.manuscript)["sentences"]}
    if sentence_id not in ids:
        raise NotFound("Sætningen findes ikke i manuskriptet")
    data = await request.body()
    if not data or len(data) > MAX_WAV_BYTES:
        raise ValidationFailed("Optagelsen mangler eller er for stor (højst 6 MB)", field_errors=[{"field": "audio"}])
    qc = qc_wav(data)
    first = db.scalar(select(OwnVoiceRecording).where(OwnVoiceRecording.project_id == p.id))
    if first is not None and first.qc.get("sample_rate") != qc["sample_rate"] and first.sentence_id != sentence_id:
        raise ValidationFailed("Optag alle sætninger med samme mikrofon og indstillinger", field_errors=[{"field": "audio"}])
    key = f"ws/{ctx.workspace.id}/own-voices/{p.id}/{sentence_id}.wav"
    storage.put(key, data, "audio/wav")
    rec = db.scalar(select(OwnVoiceRecording).where(OwnVoiceRecording.project_id == p.id,
                                                    OwnVoiceRecording.sentence_id == sentence_id))
    if rec is None:
        rec = OwnVoiceRecording(project_id=p.id, sentence_id=sentence_id, key=key, sha256="", seconds=0, qc={})
        db.add(rec)
    rec.sha256, rec.seconds, rec.qc = hashlib.sha256(data).hexdigest(), qc["seconds"], qc
    db.commit()
    return {"sentence_id": sentence_id, "qc": qc, "progress": _out(db, p)["recorded"]}


@router.get("/{project_id}/recordings/{sentence_id}/audio")
def get_recording(project_id: uuid.UUID, sentence_id: str,
                  ctx: WorkspaceContext = Depends(require_capability("voices.manage")), db: OrmSession = Depends(get_db)):
    p = _project(db, ctx, project_id)
    rec = db.scalar(select(OwnVoiceRecording).where(OwnVoiceRecording.project_id == p.id,
                                                    OwnVoiceRecording.sentence_id == sentence_id))
    data = storage.get(rec.key) if rec else None
    if data is None:
        raise NotFound("Optagelsen findes ikke")
    return Response(data, media_type="audio/wav", headers={"cache-control": "no-store"})


def _reference(db: OrmSession, p: OwnVoiceProject) -> tuple[bytes, float]:
    """A 7–12 s reference from consecutive clean recordings (short pauses between), in manuscript order."""
    order = [s["id"] for s in _manuscript(p.manuscript)["sentences"]]
    recs = {r.sentence_id: r for r in db.scalars(select(OwnVoiceRecording).where(OwnVoiceRecording.project_id == p.id))}
    clean = [recs[i] for i in order if i in recs and recs[i].qc.get("ok")]
    best: list = []
    for start in range(len(clean)):
        run, total = [], 0.0
        for r in clean[start:]:
            if total + r.seconds > 12:
                break
            run.append(r)
            total += r.seconds + 0.3
            if total >= 7:
                break
        if total >= 7 and (not best or abs(total - 9.5) < abs(sum(x.seconds for x in best) - 9.5)):
            best = run
    if not best:
        raise Conflict("Optagelserne er for korte til en stemme. Optag flere sætninger.", code="own_voice_short")
    out, rate = array.array("h"), None
    for r in best:
        with wave.open(io.BytesIO(storage.get(r.key) or b"")) as w:
            rate = w.getframerate()
            pcm = array.array("h")
            pcm.frombytes(w.readframes(w.getnframes()))
            if w.getnchannels() == 2:
                pcm = array.array("h", ((pcm[i] + pcm[i + 1]) // 2 for i in range(0, len(pcm) - 1, 2)))
        out.extend(pcm)
        out.extend(array.array("h", [0]) * int(0.3 * rate))
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(out.tobytes())
    return buf.getvalue(), len(out) / rate


@router.post("/{project_id}/submit")
def submit(project_id: uuid.UUID, request: Request, ctx: WorkspaceContext = Depends(require_capability("voices.manage")),
           db: OrmSession = Depends(get_db)):
    s = get_settings()
    p = _project(db, ctx, project_id)
    if p.status != "recording":
        raise Conflict("Indtalingen er allerede sendt eller trukket tilbage", code="own_voice_state")
    info = _out(db, p)
    if info["approved_recordings"] < info["total"]:
        raise Conflict(f"Der mangler {info['total'] - info['approved_recordings']} godkendte optagelser",
                       code="own_voice_incomplete")
    ref, seconds = _reference(db, p)
    slug = f"egen-{str(ctx.workspace.id)[:8]}-{str(p.id)[:8]}"
    prof = VoiceProfile(slug=slug, display_name=f"{p.speaker_name} (egen stemme)"[:80],
                        gender=p.consent.get("speaker_gender") or "unknown", dialect=None,
                        dialect_basis="Indtalerens egen stemme. Dialekt er ikke vurderet.", origin="customer_recorded",
                        description=f"{p.speaker_name}s egen stemme, indtalt i Dialogbot. Bruges kun i jeres arbejdsrum.",
                        source=f"Egen indtaling ({p.manuscript}), samtykke version {p.consent.get('version')}",
                        visibility="workspace", workspace_id=ctx.workspace.id, created_by=ctx.user_id,
                        sample_text=service.DEFAULT_SAMPLE)
    db.add(prof)
    db.flush()
    key = f"{storage.workspace_prefix(ctx.workspace.id)}/voices/{slug}/refs/{hashlib.sha256(ref).hexdigest()[:16]}.wav"
    storage.put(key, ref, "audio/wav")
    code = db.scalar(select(VoiceRightsRecord).where(VoiceRightsRecord.kind == "code"))
    model = db.scalar(select(VoiceRightsRecord).where(VoiceRightsRecord.kind == "model",
                                                      VoiceRightsRecord.source_url.contains(s.voice_model_repo)))
    rights = [str(r.id) for r in (code, model) if r is not None] + [str(p.rights_record_id)]
    v = VoiceVersion(profile_id=prof.id, version=1, engine="chatterbox-multilingual", method="reference_conditioning",
                     model_repo=s.voice_model_repo, model_revision=s.voice_model_revision,
                     references=[{"key": key, "sha256": hashlib.sha256(ref).hexdigest(), "seconds": round(seconds, 2),
                                  "source_id": f"own-voice:{p.id}"}],
                     settings={}, rights_record_ids=rights, checks={}, notes="Oprettet fra kundens egen indtaling",
                     created_by=ctx.user_id)
    db.add(v)
    db.flush()
    service.run_auto_checks(db, v)
    v.status = "pending_review"
    p.status, p.profile_id, p.submitted_at = "submitted", prof.id, _now()
    record_audit(db, workspace_id=ctx.workspace.id, actor_user_id=ctx.user_id, action="own_voice.submitted",
                 object_type="own_voice_project", object_id=p.id, after={"profile_id": str(prof.id)})
    db.commit()
    return _out(db, p)


@router.delete("/{project_id}")
def withdraw(project_id: uuid.UUID, request: Request, ctx: WorkspaceContext = Depends(require_capability("voices.manage")),
             db: OrmSession = Depends(get_db)):
    """Consent withdrawn: recordings deleted, the voice stops at once (next calls use the fallback voice)."""
    p = _project(db, ctx, project_id)
    if p.status == "withdrawn":
        return _out(db, p)
    keys = []
    for r in db.scalars(select(OwnVoiceRecording).where(OwnVoiceRecording.project_id == p.id)):
        keys.append(r.key)
        db.delete(r)
    if p.profile_id and (prof := db.get(VoiceProfile, p.profile_id)):
        for v in db.scalars(select(VoiceVersion).where(VoiceVersion.profile_id == prof.id)):
            keys += [ref["key"] for ref in v.references or []]
            if v.status != "retired":
                v.status = "retired"
        prof.active_version_id = None
        service.invalidate_cache(prof)
    storage.delete(keys)
    if p.rights_record_id and (r := db.get(VoiceRightsRecord, p.rights_record_id)):
        r.status = "blocked"
        r.notes = (r.notes + f"\nSamtykket er trukket tilbage {_now().isoformat()}.").strip()
    p.status, p.withdrawn_at = "withdrawn", _now()
    record_audit(db, workspace_id=ctx.workspace.id, actor_user_id=ctx.user_id, action="own_voice.withdrawn",
                 object_type="own_voice_project", object_id=p.id, after={"deleted_objects": len(keys)})
    db.commit()
    return _out(db, p)

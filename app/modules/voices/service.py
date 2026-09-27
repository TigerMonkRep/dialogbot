"""Voice registry: lifecycle, publication checks, access, resolution per channel and session pinning.

Lifecycle (per version): draft → pending_review → approved → active; active ↔ suspended; any → retired.
Activating a new version keeps the previous one as 'approved' so a rollback is one command. The profile's
`active_version_id` is what customers get; nothing else is selectable.

Publication checks (never set by code on a human's behalf):
- rights            automatic: every referenced rights record is 'verified' by an operator, none 'blocked'
- normalization     automatic: the Danish test set normalises with every critical value intact
- synthesis_smoke   automatic: the real engine synthesised the standard sentences for this version
- listening_test    human: ≥3 Danish raters, mean ≥4/5 on intelligibility and naturalness, no critical errors
- telephony_test    human: a real call through the telephony provider with this version
Platform visibility requires all five. A workspace-private *pilot* requires the first three.
With TTS_ENGINE=fake (dev/test) synthesis_smoke is recorded as 'simulated' and only counts in dev/test.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from app.config import get_settings
from app.core.errors import ApiError, Conflict, NotFound, ValidationFailed
from app.models import (
    VoiceProfile,
    VoiceRightsRecord,
    VoiceSession,
    VoiceUsage,
    VoiceVersion,
    WorkspaceVoiceSettings,
)
from app.modules.voices import danish, engine

CHECKS_PLATFORM = ("rights", "normalization", "synthesis_smoke", "listening_test", "telephony_test")
CHECKS_PILOT = ("rights", "normalization", "synthesis_smoke")
HUMAN_CHECKS = ("listening_test", "telephony_test")
# A designed voice may not resemble any source speaker more than two different real speakers of the same group
# resemble each other, plus a small margin, and never above an absolute ceiling (speaker-encoder cosine similarity).
DISTINCT_MARGIN = 0.03
DISTINCT_CEILING = 0.90
SMOKE_SENTENCES = (
    "Hej, du taler med Dialogbots AI-assistent hos Fjord Gulvservice. Hvad kan jeg hjælpe med?",
    "Jeg har en ledig tid onsdag den 28. oktober klokken halv elleve.",
    "Tiden er endnu ikke bekræftet. Jeg undersøger, om den blev oprettet.",
    "Det koster 1.495 kroner om måneden eksklusive moms.",
)
DEFAULT_SAMPLE = "Hej, du taler med en digital assistent. Hvordan kan jeg hjælpe dig i dag?"
TRANSITIONS = {
    "submit": ({"draft"}, "pending_review"),
    "reject": ({"pending_review"}, "draft"),
    "approve": ({"pending_review"}, "approved"),
    "activate": ({"approved", "suspended"}, "active"),
    "suspend": ({"active"}, "suspended"),
    "retire": ({"draft", "pending_review", "approved", "suspended"}, "retired"),
}


def _now() -> datetime:
    return datetime.now(UTC)


# --------------------------------------------------------------------------- access

def accessible(p: VoiceProfile, ws_id: uuid.UUID) -> bool:
    return p.visibility == "platform" or p.workspace_id == ws_id


def active_version(db: OrmSession, p: VoiceProfile) -> VoiceVersion | None:
    if not p.active_version_id:
        return None
    v = db.get(VoiceVersion, p.active_version_id)
    return v if v is not None and v.status == "active" else None


def selectable(db: OrmSession, ws_id: uuid.UUID) -> list[tuple[VoiceProfile, VoiceVersion]]:
    out = []
    for p in db.scalars(select(VoiceProfile).order_by(VoiceProfile.display_name)):
        if accessible(p, ws_id) and (v := active_version(db, p)) is not None:
            out.append((p, v))
    return out


def get_selectable(db: OrmSession, ws_id: uuid.UUID, profile_id: uuid.UUID) -> tuple[VoiceProfile, VoiceVersion]:
    p = db.get(VoiceProfile, profile_id)
    if p is None or not accessible(p, ws_id):
        raise NotFound("Stemmen findes ikke")
    v = active_version(db, p)
    if v is None:
        raise Conflict("Stemmen er ikke tilgængelig lige nu", code="voice_not_active")
    return p, v


def settings(db: OrmSession, ws_id: uuid.UUID, *, lock: bool = False) -> WorkspaceVoiceSettings:
    q = select(WorkspaceVoiceSettings).where(WorkspaceVoiceSettings.workspace_id == ws_id)
    s = db.scalar(q.with_for_update() if lock else q)
    if s is None:
        s = WorkspaceVoiceSettings(workspace_id=ws_id, pronunciations=[])
        db.add(s)
        db.flush()
    return s


# --------------------------------------------------------------------------- lifecycle and checks

def _check_rights(db: OrmSession, v: VoiceVersion) -> dict:
    ids = [uuid.UUID(x) for x in v.rights_record_ids or []]
    recs = [db.get(VoiceRightsRecord, i) for i in ids]
    missing = [str(i) for i, r in zip(ids, recs, strict=True) if r is None]
    kinds = {r.kind for r in recs if r}
    needed = {"code", "model", "dataset"} if v.method == "reference_conditioning" else {"code", "model"}
    if not any(k in kinds for k in ("dataset", "speaker_agreement")):
        needed.add("dataset")
    status = "passed"
    problems = []
    if missing:
        problems.append(f"ukendte rettighedsposter: {', '.join(missing)}")
    for r in recs:
        if r and r.status != "verified":
            problems.append(f"{r.kind} '{r.subject}' er {r.status}")
    for k in sorted(needed - kinds):
        problems.append(f"mangler rettighedspost for {k}")
    if problems:
        status = "failed"
    return {"status": status, "problems": problems}


def _check_normalization() -> dict:
    from pathlib import Path

    path = Path(__file__).resolve().parents[3] / "voice_pipeline" / "eval" / "testset_da.jsonl"
    rows = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]
    failed = []
    for r in rows:
        spoken = danish.normalize(r["text"])
        if any(ch.isdigit() for ch in spoken) or any(m not in spoken for m in r.get("must_say", [])):
            failed.append(r["id"])
    return {"status": "passed" if not failed else "failed", "sentences": len(rows), "failed": failed[:20]}


def _check_smoke(v: VoiceVersion) -> dict:
    results = []
    simulated = False
    try:
        for text in SMOKE_SENTENCES:
            s = engine.synthesize(v, danish.normalize(text), sample_rate=24000)
            simulated = simulated or s.simulated
            seconds = len(s.pcm) / 2 / s.sample_rate
            if seconds < 0.3:
                return {"status": "failed", "reason": "for kort lyd", "results": results}
            results.append({"seconds": round(seconds, 2), "synth_ms": s.synth_ms})
    except ApiError as e:
        return {"status": "failed", "reason": e.message, "results": results}
    return {"status": "simulated" if simulated else "passed", "results": results}


def _check_distinct(v: VoiceVersion) -> dict:
    d = (v.provenance or {}).get("distinctness") or {}
    try:
        nearest, real_max = float(d["max_similarity_to_source"]), float(d["real_speaker_pairs_max"])
    except (KeyError, TypeError, ValueError):
        return {"status": "failed", "reason": "Mangler måling af lighed med kildepersonerne"}
    limit = round(min(DISTINCT_CEILING, real_max + DISTINCT_MARGIN), 3)
    sources = (v.provenance or {}).get("sources") or []
    if len(sources) < 4:
        return {"status": "failed", "reason": "En designet stemme skal bygges af mindst 4 personer", "sources": len(sources)}
    return {"status": "passed" if nearest <= limit else "failed", "nearest": nearest, "limit": limit,
            "nearest_source": d.get("nearest_source"), "sources": len(sources)}


def run_auto_checks(db: OrmSession, v: VoiceVersion) -> dict:
    checks = dict(v.checks or {})
    stamp = {"at": _now().isoformat(), "by": "system"}
    if v.method == "designed_blend":
        checks["distinctness"] = _check_distinct(v) | stamp
    checks["rights"] = _check_rights(db, v) | stamp
    checks["normalization"] = _check_normalization() | stamp
    checks["synthesis_smoke"] = _check_smoke(v) | stamp
    v.checks = checks
    return checks


def record_human_check(v: VoiceVersion, name: str, *, passed: bool, evidence: dict, by: uuid.UUID) -> dict:
    if name not in HUMAN_CHECKS:
        raise ValidationFailed("Ukendt kontrol", field_errors=[{"field": "name"}])
    if name == "listening_test" and passed:
        raters = int(evidence.get("raters") or 0)
        intel, nat = float(evidence.get("intelligibility") or 0), float(evidence.get("naturalness") or 0)
        if raters < 3 or intel < 4.0 or nat < 4.0 or evidence.get("critical_errors"):
            raise ValidationFailed("Lyttetesten opfylder ikke kravet (mindst 3 lyttere, gennemsnit ≥ 4 på forståelighed "
                                   "og naturlighed, ingen kritiske fejl)", field_errors=[{"field": "evidence"}])
    if name == "telephony_test" and passed and not evidence.get("provider_call_id"):
        raise ValidationFailed("Angiv opkalds-ID fra telefonileverandøren", field_errors=[{"field": "evidence"}])
    checks = dict(v.checks or {})
    checks[name] = {"status": "passed" if passed else "failed", "at": _now().isoformat(), "by": str(by), "evidence": evidence}
    v.checks = checks
    return checks


def missing_checks(v: VoiceVersion, visibility: str) -> list[str]:
    required = CHECKS_PLATFORM if visibility == "platform" else CHECKS_PILOT
    if v.method == "designed_blend":
        required = (*required, "distinctness")
    ok_sim = get_settings().app_env in ("dev", "test")
    missing = []
    for name in required:
        st = (v.checks or {}).get(name, {}).get("status")
        if st == "passed" or (st == "simulated" and ok_sim):
            continue
        missing.append(name)
    return missing


def transition(db: OrmSession, p: VoiceProfile, v: VoiceVersion, action: str, actor: uuid.UUID) -> VoiceVersion:
    if action not in TRANSITIONS:
        raise ValidationFailed("Ukendt handling")
    allowed, target = TRANSITIONS[action]
    if v.status not in allowed:
        raise Conflict(f"Kan ikke {action} en version med status {v.status}", code="voice_state")
    if action == "submit" and not (v.references or v.checkpoint_key):
        raise ValidationFailed("Versionen har hverken referenceklip eller checkpoint")
    if action in ("approve", "activate"):
        missing = missing_checks(v, p.visibility)
        if missing:
            raise Conflict("Kontroller mangler eller er ikke bestået: " + ", ".join(missing), code="voice_checks_missing",
                           extra={"missing": missing})
    if action == "approve":
        v.approved_by, v.approved_at = actor, _now()
    if action == "activate":
        prev = active_version(db, p)
        if prev is not None and prev.id != v.id:
            prev.status = "approved"  # kept for rollback
        p.active_version_id = v.id
        v.activated_at = _now()
    if action in ("suspend", "retire") and p.active_version_id == v.id:
        p.active_version_id = None
    v.status = target
    invalidate_cache(p)
    return v


def rollback(db: OrmSession, p: VoiceProfile, actor: uuid.UUID) -> VoiceVersion:
    """Activate the most recent other approved version."""
    current = p.active_version_id
    cand = db.scalars(select(VoiceVersion).where(VoiceVersion.profile_id == p.id, VoiceVersion.status == "approved",
                                                 VoiceVersion.id != current).order_by(VoiceVersion.version.desc())).first()
    if cand is None:
        raise Conflict("Der er ingen tidligere godkendt version at rulle tilbage til", code="no_rollback_target")
    cur = db.get(VoiceVersion, current) if current else None
    out = transition(db, p, cand, "activate", actor)
    if cur is not None and cur.status == "approved" and cur.id != cand.id:
        cur.status = "suspended"  # the replaced version is taken out of use, not deleted
    return out


# --------------------------------------------------------------------------- cache

def cache_prefix(p: VoiceProfile) -> str:
    return f"cache/{'platform' if p.visibility == 'platform' else f'ws/{p.workspace_id}'}/{p.id}"


def cache_key(p: VoiceProfile, v: VoiceVersion, text: str, sample_rate: int) -> str:
    h = hashlib.sha256(json.dumps([str(v.id), v.model_revision, v.settings, text, sample_rate, "wav"],
                                  sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    return f"{cache_prefix(p)}/{h}.wav"


def invalidate_cache(p: VoiceProfile) -> None:
    from app.modules.voices import storage

    storage.delete_prefix(cache_prefix(p))


# --------------------------------------------------------------------------- usage guard

def count_usage(db: OrmSession, ws_id: uuid.UUID, kind: str, characters: int, *, limit_requests: int | None = None,
                limit_chars: int | None = None) -> VoiceUsage:
    today = date.today()
    u = db.scalar(select(VoiceUsage).where(VoiceUsage.workspace_id == ws_id, VoiceUsage.day == today,
                                           VoiceUsage.kind == kind).with_for_update())
    if u is None:
        u = VoiceUsage(workspace_id=ws_id, day=today, kind=kind, requests=0, characters=0)
        db.add(u)
        db.flush()
    if limit_requests is not None and u.requests >= limit_requests:
        raise ApiError("Dagens grænse for stemmeprøver er nået. Prøv igen i morgen.", code="voice_preview_limit",
                       status_code=429)
    if limit_chars is not None and u.characters + characters > limit_chars:
        raise ApiError("Dagens grænse for talesyntese er nået", code="voice_char_limit", status_code=429)
    u.requests += 1
    u.characters += characters
    return u


# --------------------------------------------------------------------------- resolution and pinning

def resolve(db: OrmSession, ws_id: uuid.UUID, *, number=None, campaign=None) -> tuple[VoiceProfile | None, VoiceVersion | None, str]:
    """Voice for a conversation: campaign → assistant (number) → workspace standard. Returns (p, v, why)."""
    s = db.get(WorkspaceVoiceSettings, ws_id)
    for source, pid in (("campaign", getattr(campaign, "voice_profile_id", None)),
                        ("assistant", getattr(number, "voice_profile_id", None)),
                        ("workspace", s.default_profile_id if s else None)):
        if not pid:
            continue
        p = db.get(VoiceProfile, pid)
        if p is None or not accessible(p, ws_id):
            return None, None, f"{source}: stemmen findes ikke"
        v = active_version(db, p)
        if v is None:
            return p, None, f"{source}: stemmen er ikke aktiv"
        return p, v, source
    return None, None, "none"


def pin_session(db: OrmSession, ws_id: uuid.UUID, channel: str, p: VoiceProfile, v: VoiceVersion,
                fallback: dict) -> VoiceSession:
    s = db.get(WorkspaceVoiceSettings, ws_id)
    vs = VoiceSession(workspace_id=ws_id, channel=channel, profile_id=p.id, version_id=v.id, settings=dict(v.settings or {}),
                      pronunciations=list(s.pronunciations if s else []), fallback=fallback, stats={})
    db.add(vs)
    db.flush()
    return vs


def profile_out(db: OrmSession, p: VoiceProfile, *, detail: bool = False) -> dict:
    v = active_version(db, p)
    out = {"id": str(p.id), "slug": p.slug, "display_name": p.display_name, "language": p.language, "gender": p.gender,
           "dialect": p.dialect, "dialect_basis": p.dialect_basis, "age_description": p.age_description,
           "timbre": p.timbre, "origin": p.origin, "description": p.description, "source": p.source,
           "visibility": p.visibility, "sample_text": p.sample_text or DEFAULT_SAMPLE,
           "active_version": None}
    if v is not None:
        out["active_version"] = {"id": str(v.id), "version": v.version, "engine": v.engine, "method": v.method,
                                 "model_revision": v.model_revision, "pilot": p.visibility == "workspace",
                                 "listening_test": (v.checks or {}).get("listening_test", {}).get("status", "pending"),
                                 "telephony_test": (v.checks or {}).get("telephony_test", {}).get("status", "pending"),
                                 "simulated": (v.checks or {}).get("synthesis_smoke", {}).get("status") == "simulated"}
    return out


def version_out(v: VoiceVersion) -> dict:
    return {"id": str(v.id), "version": v.version, "status": v.status, "engine": v.engine, "method": v.method,
            "model_repo": v.model_repo, "model_revision": v.model_revision, "checkpoint_key": v.checkpoint_key,
            "references": v.references, "settings": v.settings, "rights_record_ids": v.rights_record_ids,
            "provenance": v.provenance,
            "checks": v.checks, "notes": v.notes, "created_at": v.created_at.isoformat(),
            "approved_at": v.approved_at.isoformat() if v.approved_at else None,
            "activated_at": v.activated_at.isoformat() if v.activated_at else None}


def rights_out(r: VoiceRightsRecord) -> dict:
    return {k: (str(getattr(r, k)) if isinstance(getattr(r, k), uuid.UUID) else
                getattr(r, k).isoformat() if isinstance(getattr(r, k), datetime) else getattr(r, k))
            for k in ("id", "kind", "subject", "license", "source_url", "revision", "status", "allowed_uses", "restrictions",
                      "commercial_use", "subprocessors", "term", "termination", "basis", "document_key", "notes",
                      "reviewed_by", "reviewed_at", "created_at")}


def vapi_voice(db: OrmSession, ws_id: uuid.UUID, *, channel: str, provider_voice: dict | None, number=None,
               campaign=None) -> tuple[dict | None, VoiceSession | None]:
    """Voice config for a Vapi assistant.

    - No Dialogbot voice chosen → (None, None): the existing provider voice is used unchanged.
    - Chosen voice active and a speech engine configured → custom-voice pointing at our pinned session, with the
      approved reserve voice (the number's ElevenLabs voice) as Vapi fallbackPlan when fallback=provider_voice.
    - Chosen but not usable → the reserve voice, and the reason is recorded on a session (never silent).
    """
    from app.config import get_settings

    p, v, why = resolve(db, ws_id, number=number, campaign=campaign)
    if p is None and why == "none":
        return None, None
    ws_settings = settings(db, ws_id)
    reserve = provider_voice if ws_settings.fallback == "provider_voice" else None
    if v is None or engine.status() == "not_configured":
        reason = why if v is None else "talemotoren er ikke sat op"
        vs = VoiceSession(workspace_id=ws_id, channel=channel, profile_id=p.id if p else None, version_id=None,
                          settings={}, pronunciations=[], stats={},
                          fallback={"used": "provider_voice" if provider_voice else "provider_default", "reason": reason})
        db.add(vs)
        db.flush()
        return None, vs
    vs = pin_session(db, ws_id, channel, p, v, fallback={"reserve": "provider_voice" if reserve else None,
                                                          "policy": ws_settings.fallback})
    s = get_settings()
    voice: dict = {"provider": "custom-voice",
                   "server": {"url": f"{s.public_base_url.rstrip('/')}/api/v1/voice/vapi/{vs.id}",
                              "secret": s.vapi_server_secret, "timeoutSeconds": int(s.tts_timeout_seconds)}}
    if reserve:
        voice["fallbackPlan"] = {"voices": [reserve]}
    return voice, vs

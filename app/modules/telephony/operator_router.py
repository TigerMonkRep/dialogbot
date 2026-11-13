"""Dialogbot operator API for telephony (platform operators only; audited). Provider configuration, technical
errors, provisioning jobs, documentation review, manual verification, number mapping and caller-ID permission live
here – never in the customer's settings. Secrets are never returned: configuration is reported as booleans."""
from __future__ import annotations

import re
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Request, Response, UploadFile
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as OrmSession

from app.core.audit import record_audit
from app.core.auth import Principal
from app.core.errors import Conflict, NotFound, ValidationFailed
from app.db import get_db
from app.models import PhoneNumber, TelephonyCost, TelephonyJob, TelephonySetup, TelephonyTest, Workspace
from app.modules.telephony import platform, providers
from app.modules.voices.operator_router import operator

router = APIRouter(prefix="/operator/telephony", tags=["telephony-operator"])


def _audit(db, request, principal, ws_id, action: str, after: dict) -> None:
    record_audit(db, workspace_id=ws_id, actor_user_id=principal.user.id, action=action, object_type="telephony_setup",
                 object_id=ws_id, after=after, request_id=request.state.request_id)


def _number(n: PhoneNumber) -> dict:
    return {"id": str(n.id), "workspace_id": str(n.workspace_id), "e164": n.e164, "source": n.source, "status": n.status,
            "provider_number_id": n.provider_number_id, "provider_sid": n.provider_sid,
            "outbound_allowed": n.outbound_allowed, "active": n.active}


def _row(db: OrmSession, ws: Workspace) -> dict:
    s = platform.setup_for(db, ws.id)
    job = platform.job_for(db, ws.id)
    t = platform.last_test(db, s)
    cost = db.scalar(select(func.coalesce(func.sum(TelephonyCost.amount_micros), 0))
                     .where(TelephonyCost.workspace_id == ws.id, TelephonyCost.currency == "USD")) or 0
    return {"workspace_id": str(ws.id), "workspace": ws.name, "status": platform.status(db, ws.id),
            "state": s.state, "business_number": s.business_number,
            "verified_by": s.business_number_verified_by, "documents_status": s.documents_status,
            "document_uploaded": s.document_key is not None, "company_name": s.company_name, "cvr": s.cvr,
            "company_address": s.company_address, "regulatory_bundle_sid": s.regulatory_bundle_sid,
            "wants_new_number": s.wants_new_number,
            "job": ({"id": str(job.id), "status": job.status, "step": job.step, "waiting_for": job.waiting_for,
                     "attempts": job.attempts, "last_error": job.last_error, "state": job.state,
                     "next_attempt_at": job.next_attempt_at.isoformat() if job.next_attempt_at else None} if job else None),
            "test": ({"status": t.status, "simulated": t.simulated, "result": t.result} if t else None),
            "numbers": [_number(n) for n in db.scalars(select(PhoneNumber).where(PhoneNumber.workspace_id == ws.id))],
            "provider_cost_usd": round(cost / 1_000_000, 2)}


def _ws(db: OrmSession, ws_id: uuid.UUID) -> Workspace:
    ws = db.get(Workspace, ws_id)
    if ws is None:
        raise NotFound("Arbejdsrummet findes ikke")
    return ws


@router.get("")
def overview(principal: Principal = Depends(operator), db: OrmSession = Depends(get_db)):
    ids = set(db.scalars(select(TelephonySetup.workspace_id))) | set(db.scalars(select(PhoneNumber.workspace_id)))
    rows = [_row(db, ws) for ws in db.scalars(select(Workspace).where(Workspace.id.in_(ids)).order_by(Workspace.name))]
    db.commit()
    return {"configuration": providers.configuration(), "workspaces": rows}


@router.get("/workspaces/{ws_id}")
def detail(ws_id: uuid.UUID, principal: Principal = Depends(operator), db: OrmSession = Depends(get_db)):
    out = _row(db, _ws(db, ws_id))
    out["tests"] = [{"status": t.status, "simulated": t.simulated, "started_at": t.started_at.isoformat(), "result": t.result}
                    for t in db.scalars(select(TelephonyTest).where(TelephonyTest.workspace_id == ws_id)
                                        .order_by(TelephonyTest.started_at.desc()).limit(10))]
    db.commit()
    return out


class NoteIn(BaseModel):
    note: str = Field(min_length=10, max_length=1000)


@router.post("/workspaces/{ws_id}/verify-manually")
def verify_manually(ws_id: uuid.UUID, body: NoteIn, request: Request, principal: Principal = Depends(operator),
                    db: OrmSession = Depends(get_db)):
    s = platform.setup_for(db, _ws(db, ws_id).id, lock=True)
    if not s.business_number:
        raise ValidationFailed("Kunden har ikke angivet et nummer")
    s.business_number_verified_at, s.business_number_verified_by = platform._now(), f"operator:{principal.user.id}"
    _audit(db, request, principal, ws_id, "telephony.verified_by_operator", {"note": body.note})
    db.commit()
    return _row(db, _ws(db, ws_id))


class ReviewIn(BaseModel):
    status: str = Field(pattern="^(approved|rejected)$")
    note: str = Field(min_length=10, max_length=1000)
    regulatory_bundle_sid: str | None = Field(default=None, pattern=r"^BU[0-9a-f]{32}$")
    regulatory_address_sid: str | None = Field(default=None, pattern=r"^AD[0-9a-f]{32}$")


@router.post("/workspaces/{ws_id}/documents/review")
def review_documents(ws_id: uuid.UUID, body: ReviewIn, request: Request, principal: Principal = Depends(operator),
                     db: OrmSession = Depends(get_db)):
    s = platform.setup_for(db, _ws(db, ws_id).id, lock=True)
    if body.status == "approved" and not body.regulatory_bundle_sid:
        raise ValidationFailed("Angiv det godkendte regulatoriske bundle (BU…) fra Twilio",
                               field_errors=[{"field": "regulatory_bundle_sid"}])
    s.documents_status, s.regulatory_note = body.status, body.note
    if body.status == "approved":
        s.regulatory_bundle_sid, s.regulatory_address_sid = body.regulatory_bundle_sid, body.regulatory_address_sid
    job = platform.job_for(db, ws_id)
    if job is not None and job.status == "waiting":
        job.next_attempt_at = platform._now()
    _audit(db, request, principal, ws_id, "telephony.documents_reviewed", {"status": body.status, "note": body.note})
    db.commit()
    return _row(db, _ws(db, ws_id))


@router.get("/workspaces/{ws_id}/documents")
def get_document(ws_id: uuid.UUID, request: Request, principal: Principal = Depends(operator),
                 db: OrmSession = Depends(get_db)):
    from app.modules.voices import storage

    s = platform.setup_for(db, _ws(db, ws_id).id)
    data = storage.get(s.document_key) if s.document_key else None
    if data is None:
        raise NotFound("Intet dokument")
    _audit(db, request, principal, ws_id, "telephony.document_viewed", {})
    db.commit()
    kind = "application/pdf" if s.document_key.endswith(".pdf") else "image/png" if s.document_key.endswith(".png") else "image/jpeg"
    return Response(data, media_type=kind, headers={"cache-control": "no-store"})


@router.post("/workspaces/{ws_id}/jobs/run")
def run_job(ws_id: uuid.UUID, request: Request, principal: Principal = Depends(operator), db: OrmSession = Depends(get_db)):
    job = platform.job_for(db, _ws(db, ws_id).id)
    if job is None:
        raise NotFound("Ingen klargøring for arbejdsrummet")
    if job.status == "failed":
        job.status, job.attempts = "pending", 0
    platform.run_job(db, job)
    _audit(db, request, principal, ws_id, "telephony.job_run", {"status": job.status, "step": job.step})
    db.commit()
    return _row(db, _ws(db, ws_id))


class MapIn(BaseModel):
    e164: str = Field(max_length=24)
    provider_number_id: str = Field(min_length=3, max_length=100)
    note: str = Field(min_length=10, max_length=1000)
    activate: bool = False


@router.post("/workspaces/{ws_id}/numbers", status_code=201)
def map_number(ws_id: uuid.UUID, body: MapIn, request: Request, principal: Principal = Depends(operator),
               db: OrmSession = Depends(get_db)):
    """Map a number that already exists in Dialogbot's Vapi org (e.g. migrating a hand-set-up customer)."""
    from app.modules.telephony.vapi import E164, normalize_e164

    ws = _ws(db, ws_id)
    e164 = normalize_e164(body.e164)
    if not E164.match(e164):
        raise ValidationFailed("Ugyldigt nummer", field_errors=[{"field": "e164"}])
    n = PhoneNumber(workspace_id=ws.id, e164=e164, provider="vapi", provider_number_id=body.provider_number_id.strip(),
                    source="legacy_customer", status="active", label="Dialogbot-nummer")
    db.add(n)
    try:
        db.flush()
    except IntegrityError as e:
        db.rollback()
        raise Conflict("Nummeret eller id'et er allerede tilknyttet et arbejdsrum", code="number_taken") from e
    s = platform.setup_for(db, ws.id, lock=True)
    if s.destination_number_id is None:
        s.destination_number_id = n.id
        s.state = "active" if body.activate else "provisioned"
        if body.activate:
            s.activated_at, s.activated_by = platform._now(), principal.user.id
    _audit(db, request, principal, ws.id, "telephony.number_mapped",
           {"e164": e164, "activate": body.activate, "note": body.note})
    db.commit()
    return _row(db, ws)


class NumberPatch(BaseModel):
    outbound_allowed: bool | None = None
    status: str | None = Field(default=None, pattern="^(active|suspended)$")
    note: str = Field(min_length=10, max_length=1000)


@router.patch("/numbers/{number_id}")
def patch_number(number_id: uuid.UUID, body: NumberPatch, request: Request, principal: Principal = Depends(operator),
                 db: OrmSession = Depends(get_db)):
    n = db.get(PhoneNumber, number_id)
    if n is None:
        raise NotFound("Nummeret findes ikke")
    before = _number(n)
    if body.outbound_allowed is not None:
        n.outbound_allowed = body.outbound_allowed
    if body.status is not None:
        n.status = body.status
    _audit(db, request, principal, n.workspace_id, "telephony.number_updated",
           {"before": before, "after": _number(n), "note": body.note})
    db.commit()
    return _number(n)


VAPI_INBOUND_URL = "https://api.vapi.ai/twilio/inbound_call"


@router.post("/numbers/{number_id}/inbound")
def route_inbound(number_id: uuid.UUID, request: Request, principal: Principal = Depends(operator),
                  db: OrmSession = Depends(get_db)):
    """Point a number's incoming calls at Vapi (and so at our assistant, voice and transcriber): Twilio's voice
    webhook back to Vapi's inbound URL, and the Vapi number's server URL to our webhook. Undoes what importing the
    same number into another engine (ElevenLabs Agents) did to the Twilio webhook. Platform credentials only."""
    from app.config import get_settings
    from app.core.errors import NotImplementedYet

    n = db.get(PhoneNumber, number_id)
    if n is None:
        raise NotFound("Nummeret findes ikke")
    pair = providers.providers()
    if pair is None:
        raise NotImplementedYet("Platformtelefoni er ikke sat op (Twilio/Vapi-nøgler mangler)", code="telephony_not_configured")
    twilio, vapi_client = pair
    s = get_settings()
    found = twilio.find_by_e164(n.e164)
    if found is None:
        raise NotFound(f"{n.e164} findes ikke på Dialogbots Twilio-konto", code="number_not_on_twilio")
    account_sid, number_sid = found
    twilio.set_voice_url(account_sid, number_sid, VAPI_INBOUND_URL)
    server_url = f"{s.public_base_url.rstrip('/')}/api/v1/webhooks/vapi"
    if n.provider_number_id and s.vapi_server_secret:
        vapi_client.set_server(n.provider_number_id, server_url, s.vapi_server_secret)
    n.provider_sid = number_sid
    _audit(db, request, principal, n.workspace_id, "telephony.inbound_routed",
           {"e164": n.e164, "engine": "vapi", "twilio_number_sid": number_sid, "server_url": server_url})
    db.commit()
    return {"e164": n.e164, "engine": "vapi", "voice_url": VAPI_INBOUND_URL, "server_url": server_url,
            "twilio_number_sid": number_sid}


@router.get("/linden/capture.wav")
def linden_capture(principal: Principal = Depends(operator)):
    """The raw audio Vapi sent at the start of the most recent bridged call, as a WAV an operator can listen to."""
    import io
    import wave

    from app.modules.telephony import linden

    cap = linden.CAPTURE
    if not cap["pcm"]:
        raise NotFound("Ingen optagelse endnu – broen gemmer de første sekunder af næste opkald", code="no_capture")
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(cap["channels"] or 1)
        w.setsampwidth(2)
        w.setframerate(cap["rate"] or 16000)
        w.writeframes(cap["pcm"])
    return Response(buf.getvalue(), media_type="audio/wav",
                    headers={"content-disposition": "attachment; filename=linden-capture.wav",
                             "x-capture-started": str(cap.get("started_at") or ""),
                             "x-capture-rate": str(cap["rate"]), "x-capture-channels": str(cap["channels"])})


FIXTURES = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "linden"


@router.post("/linden/replay")
async def linden_replay(file: UploadFile | None = File(default=None), fixture: str | None = None,
                        ws_id: uuid.UUID | None = None, principal: Principal = Depends(operator),
                        db: OrmSession = Depends(get_db)):
    """Run a WAV (mono or stereo, 8/16 kHz 16-bit) through the bridge's Speechmatics session without a phone call and
    return the segments. Stereo takes channel 0, like the bridge. `fixture` names a known recording from
    tests/fixtures/linden (Peter's voice, known text) instead of an upload. The offline test of Danish recognition."""
    import io
    import wave

    from app.core.errors import NotImplementedYet
    from app.modules.telephony import linden

    if not linden.configured():
        raise NotImplementedYet("Speechmatics er ikke sat op (SPEECHMATICS_API_KEY mangler)", code="speechmatics_not_configured")
    if fixture:
        name = re.sub(r"[^a-z0-9_]", "", fixture.lower())
        path = FIXTURES / f"{name}.wav"
        if not path.is_file():
            raise NotFound(f"Ukendt testlyd: {name}", code="fixture_not_found")
        raw = path.read_bytes()
    elif file is not None:
        raw = await file.read()
    else:
        raise ValidationFailed("Vedhæft en WAV eller angiv fixture", field_errors=[{"field": "file"}])
    try:
        with wave.open(io.BytesIO(raw), "rb") as w:
            channels, width, rate = w.getnchannels(), w.getsampwidth(), w.getframerate()
            pcm = w.readframes(w.getnframes())
    except (wave.Error, EOFError):
        raise ValidationFailed("Filen skal være en WAV (16-bit PCM)", field_errors=[{"field": "file"}])
    if width != 2:
        raise ValidationFailed("WAV skal være 16-bit PCM", field_errors=[{"field": "file"}])
    target = rate if rate in linden.SUPPORTED_RATES else 16000
    mono = linden.customer_channel(pcm, channels, rate, target)
    ws = await run_in_threadpool(_ws, db, ws_id) if ws_id else None  # sync DB: never on the event loop
    segments = await linden.replay(mono, db, ws, [], rate=target)
    return {"rate_in": rate, "channels_in": channels, "rate_sent": target, "seconds": round(len(mono) / 2 / target, 1),
            "segments": segments, "text": " ".join(s["text"] for s in segments).strip()}


@router.post("/tests/expire")
def expire(principal: Principal = Depends(operator), db: OrmSession = Depends(get_db)):
    n = platform.expire_tests(db)
    db.commit()
    return {"expired": n}


@router.get("/jobs")
def jobs(principal: Principal = Depends(operator), db: OrmSession = Depends(get_db)):
    return {"items": [{"id": str(j.id), "workspace_id": str(j.workspace_id), "status": j.status, "step": j.step,
                       "waiting_for": j.waiting_for, "attempts": j.attempts, "last_error": j.last_error}
                      for j in db.scalars(select(TelephonyJob).order_by(TelephonyJob.updated_at.desc()).limit(100))]}

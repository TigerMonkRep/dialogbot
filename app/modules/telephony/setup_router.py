"""Customer API for telephony: five guided steps, no provider accounts, ids, keys or webhooks.

1. Dit nuværende nummer   PUT  /telephony/business-number, POST /telephony/verify, POST /telephony/verify/confirm
                          (+ PUT /telephony/company and PUT /telephony/documents when a Danish local number needs them)
2. Forbind telefonen      POST /telephony/connect → Dialogbot provisions the destination; the forwarding guide follows
3. Sådan skal vi svare    summary of voice, greeting, opening hours and no-answer handling (links to their pages)
4. Test forbindelsen      POST /telephony/tests
5. Aktivér                POST /telephony/activate (only after a passed test and an accepted agreement), /pause
"""
from __future__ import annotations

import hashlib

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from app.core.auth import WorkspaceContext, require_capability
from app.core.errors import ValidationFailed
from app.db import get_db
from app.models import BusinessProfile, KnowledgeItem, ReceptionScript, TelephonyTest, WorkspaceVoiceSettings
from app.modules.setup.checks import invalidate_checks
from app.modules.telephony import platform

router = APIRouter(prefix="/workspaces/{workspace_id}/telephony", tags=["telephony"])
DOC_TYPES = {b"%PDF": ("application/pdf", "pdf"), b"\x89PNG": ("image/png", "png"), b"\xff\xd8\xff": ("image/jpeg", "jpg")}
MAX_DOC = 10 * 1024 * 1024


def _guide(s, dest_e164: str | None) -> dict:
    """How to forward, per subscription type. Mobile: the GSM standard codes (3GPP TS 22.030) that most mobile
    subscriptions accept; landline and IP/switchboard: done in the carrier's self-service or by the carrier."""
    if dest_e164 is None:
        return {"available": False}
    mode = s.forwarding_mode
    if s.subscription_type == "mobile":
        codes = {"always": [("Viderestil alle opkald", f"**21*{dest_e164}#")],
                 "no_answer": [("Ved ubesvaret opkald", f"**61*{dest_e164}#")],
                 "busy_or_no_answer": [("Ved ubesvaret opkald", f"**61*{dest_e164}#"),
                                       ("Ved optaget", f"**67*{dest_e164}#"),
                                       ("Når telefonen er slukket eller uden dækning", f"**62*{dest_e164}#")]}[mode]
        return {"available": True, "kind": "mobile_codes", "destination": dest_e164,
                "codes": [{"label": a, "code": b} for a, b in codes], "cancel_code": "##002#",
                "note": "Koderne er GSM-standard og virker hos de fleste mobilabonnementer. Taster du koden og trykker "
                        "ring op, får du en bekræftelse på skærmen. Virker det ikke, så gør det i teleselskabets app "
                        "eller selvbetjening, eller ring til teleselskabet."}
    what = {"always": "alle opkald", "no_answer": "opkald, der ikke bliver besvaret",
            "busy_or_no_answer": "opkald, der ikke bliver besvaret, eller når linjen er optaget"}[mode]
    where = ("i jeres omstillings- eller IP-telefoniløsning (ofte i administrationsportalen)" if s.subscription_type == "ip_pbx"
             else "i teleselskabets selvbetjening")
    return {"available": True, "kind": "carrier", "destination": dest_e164,
            "steps": [f"Log ind {where}{f' hos {s.carrier}' if s.carrier else ''}, og find viderestilling.",
                      f"Vælg viderestilling af {what} til {dest_e164}.",
                      "Kan I ikke finde det, så ring til teleselskabet og bed om viderestilling til nummeret ovenfor."],
            "note": "Fremgangsmåden afhænger af teleselskab og abonnement. Dialogbot kan ikke ændre det for jer."}


def _answering(db: OrmSession, ws_id) -> dict:
    vs = db.get(WorkspaceVoiceSettings, ws_id)
    script = db.get(ReceptionScript, ws_id)
    hours = db.scalar(select(KnowledgeItem.id).where(KnowledgeItem.workspace_id == ws_id,
                                                     KnowledgeItem.kind == "opening_hours",
                                                     KnowledgeItem.archived_at.is_(None)))
    return {"voice": {"done": True, "href": "/app/voices"},
            "greeting": {"done": bool(script and (script.greeting or "").strip()), "href": "/app/reception"},
            "opening_hours": {"done": hours is not None, "href": "/app/knowledge"},
            "no_answer": {"done": bool(vs), "value": (vs.fallback if vs else "provider_voice"), "href": "/app/voices"}}


def _test_out(t: TelephonyTest | None) -> dict | None:
    if t is None:
        return None
    return {"id": str(t.id), "status": t.status, "simulated": t.simulated, "started_at": t.started_at.isoformat(),
            "expires_at": t.expires_at.isoformat(), "finished_at": t.finished_at.isoformat() if t.finished_at else None,
            "reason": (t.result or {}).get("reason"), "conversation_stored": (t.result or {}).get("conversation_stored"),
            "called_business_number": t.called_business_number}


def overview(db: OrmSession, ctx: WorkspaceContext) -> dict:
    s = platform.setup_for(db, ctx.workspace.id)
    dest = platform.destination(db, s)
    st = platform.status(db, ctx.workspace.id)
    bp = db.scalar(select(BusinessProfile).where(BusinessProfile.workspace_id == ctx.workspace.id))
    return {
        "status": st,
        "business_number": s.business_number, "verified": s.business_number_verified_at is not None,
        "subscription_type": s.subscription_type, "carrier": s.carrier, "forwarding_mode": s.forwarding_mode,
        "wants_new_number": s.wants_new_number,
        "documents": {"required": platform.documents_required(), "status": s.documents_status,
                      "company_name": s.company_name or (bp.legal_name if bp else "") or ctx.workspace.name,
                      "cvr": s.cvr or (bp.cvr if bp else None),
                      "address": s.company_address or ", ".join(x for x in ((bp.address_line if bp else None),
                                                                            " ".join(y for y in ((bp.postal_code if bp else None),
                                                                                                 (bp.city if bp else None)) if y)) if x),
                      "uploaded": s.document_key is not None, "note": s.regulatory_note if s.documents_status == "rejected" else ""},
        "agreement_accepted": platform.agreement(db, ctx.workspace.id) is not None,
        "destination": {"e164": dest.e164} if dest is not None and dest.status == "active" else None,
        "guide": _guide(s, dest.e164 if dest is not None and dest.status == "active" else None),
        "answering": _answering(db, ctx.workspace.id),
        "test": _test_out(platform.last_test(db, s)),
        "active": s.state == "active", "activated_at": s.activated_at.isoformat() if s.activated_at else None,
    }


def _done(db: OrmSession, ctx: WorkspaceContext, action: str, after: dict, request: Request) -> dict:
    invalidate_checks(db, ctx.workspace.id, changed_area="integrations", reason=action)
    platform.audit(db, ctx.workspace.id, ctx.user_id, action, after, request.state.request_id)
    db.commit()
    return overview(db, ctx)


@router.get("")
def get_telephony(ctx: WorkspaceContext = Depends(require_capability("telephony.read")), db: OrmSession = Depends(get_db)):
    out = overview(db, ctx)
    db.commit()
    return out


class BusinessNumberIn(BaseModel):
    e164: str = Field(max_length=24)
    subscription_type: str = Field(pattern="^(mobile|landline|ip_pbx|unknown)$")
    carrier: str = Field(default="", max_length=80)
    forwarding_mode: str = Field(default="busy_or_no_answer", pattern="^(always|no_answer|busy_or_no_answer)$")
    wants_new_number: bool = False


@router.put("/business-number")
def put_business_number(body: BusinessNumberIn, request: Request,
                        ctx: WorkspaceContext = Depends(require_capability("telephony.manage")), db: OrmSession = Depends(get_db)):
    s = platform.set_business_number(db, ctx.workspace.id, e164=body.e164, subscription_type=body.subscription_type,
                                     carrier=body.carrier, forwarding_mode=body.forwarding_mode,
                                     wants_new_number=body.wants_new_number)
    return _done(db, ctx, "telephony.business_number_set", {"business_number": s.business_number,
                                                            "subscription_type": s.subscription_type}, request)


@router.post("/verify")
def verify(request: Request, ctx: WorkspaceContext = Depends(require_capability("telephony.manage")),
           db: OrmSession = Depends(get_db)):
    out = platform.start_verification(db, ctx.workspace)
    platform.audit(db, ctx.workspace.id, ctx.user_id, "telephony.verification_call", {"expires_at": out["expires_at"]},
                   request.state.request_id)
    db.commit()
    return {"sent": True, "expires_at": out["expires_at"]}


class CodeIn(BaseModel):
    code: str = Field(min_length=4, max_length=10)


@router.post("/verify/confirm")
def verify_confirm(body: CodeIn, request: Request, ctx: WorkspaceContext = Depends(require_capability("telephony.manage")),
                   db: OrmSession = Depends(get_db)):
    try:
        platform.confirm_verification(db, ctx.workspace.id, body.code)
    except ValidationFailed:
        db.commit()  # keep the attempt counter
        raise
    return _done(db, ctx, "telephony.business_number_verified", {"method": "code_call"}, request)


class CompanyIn(BaseModel):
    company_name: str = Field(min_length=2, max_length=200)
    cvr: str = Field(pattern=r"^\d{8}$")
    address: str = Field(min_length=5, max_length=300)


@router.put("/company")
def put_company(body: CompanyIn, request: Request, ctx: WorkspaceContext = Depends(require_capability("telephony.manage")),
                db: OrmSession = Depends(get_db)):
    s = platform.setup_for(db, ctx.workspace.id, lock=True)
    s.company_name, s.cvr, s.company_address = body.company_name.strip(), body.cvr, body.address.strip()
    return _done(db, ctx, "telephony.company_set", {"cvr": s.cvr}, request)


@router.put("/documents")
async def put_documents(request: Request, ctx: WorkspaceContext = Depends(require_capability("telephony.manage")),
                        db: OrmSession = Depends(get_db)):
    from app.modules.voices import storage

    data = await request.body()
    if not data or len(data) > MAX_DOC:
        raise ValidationFailed("Upload en PDF, PNG eller JPG på højst 10 MB", field_errors=[{"field": "document"}])
    kind = next((v for k, v in DOC_TYPES.items() if data.startswith(k)), None)
    if kind is None:
        raise ValidationFailed("Filen skal være PDF, PNG eller JPG", field_errors=[{"field": "document"}])
    s = platform.setup_for(db, ctx.workspace.id, lock=True)
    if not (s.company_name and s.cvr and s.company_address):
        raise ValidationFailed("Udfyld virksomhedsnavn, CVR og adresse først", field_errors=[{"field": "company"}])
    key = f"ws/{ctx.workspace.id}/telephony/company-{hashlib.sha256(data).hexdigest()[:16]}.{kind[1]}"
    storage.put(key, data, kind[0])
    s.document_key, s.documents_status = key, "submitted"
    return _done(db, ctx, "telephony.documents_submitted", {"bytes": len(data), "type": kind[0]}, request)


@router.post("/connect")
def connect(request: Request, ctx: WorkspaceContext = Depends(require_capability("telephony.manage")),
            db: OrmSession = Depends(get_db)):
    job = platform.request_connection(db, ctx.workspace.id)
    db.commit()
    platform.run_job(db, job)  # first attempt now; the worker retries/reconciles
    return _done(db, ctx, "telephony.connect_requested", {"job_status": job.status}, request)


class TestIn(BaseModel):
    called_business_number: bool = True


@router.post("/tests")
def start_test(body: TestIn, request: Request, ctx: WorkspaceContext = Depends(require_capability("telephony.manage")),
               db: OrmSession = Depends(get_db)):
    t = platform.start_test(db, ctx.workspace.id, ctx.user_id, called_business_number=body.called_business_number)
    return _done(db, ctx, "telephony.test_started", {"test_id": str(t.id)}, request)


@router.post("/activate")
def activate(request: Request, ctx: WorkspaceContext = Depends(require_capability("telephony.manage")),
             db: OrmSession = Depends(get_db)):
    platform.activate(db, ctx.workspace.id, ctx.user_id)
    return _done(db, ctx, "telephony.activated", {}, request)


@router.post("/pause")
def pause(request: Request, ctx: WorkspaceContext = Depends(require_capability("telephony.manage")),
          db: OrmSession = Depends(get_db)):
    platform.pause(db, ctx.workspace.id)
    return _done(db, ctx, "telephony.paused", {}, request)

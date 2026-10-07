"""Demo calls: the public "Ring mig op nu" door on dialogbot.dk and the operator (seller) door. See service.py."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from app.core.audit import record_audit
from app.core.auth import Principal
from app.core.errors import ApiError, NotFound, ValidationFailed
from app.db import get_db
from app.models import DemoCall
from app.modules.sales import service
from app.modules.voices.operator_router import operator

public_router = APIRouter(prefix="/demo-call", tags=["sales"])
operator_router = APIRouter(prefix="/operator/sales", tags=["sales-operator"])


@public_router.get("")
def demo_info(db: OrmSession = Depends(get_db)):
    """Whether the website may offer "Ring mig op nu", the calling hours and the public demo number."""
    return service.info(db)


class WebIn(BaseModel):
    phone: str = Field(min_length=8, max_length=30)
    name: str = Field(default="", max_length=200)
    company: str = Field(default="", max_length=200)
    consent: bool
    consent_version: str = Field(default=service.CONSENT_VERSION_WEB, max_length=40)
    website: str = Field(default="", max_length=200)  # honeypot: hidden in the form
    voice: str | None = Field(default=None, max_length=40, description="Standard voice to call with (camilla | peter)")
    industry: str | None = Field(default=None, max_length=40, description="Line of business; adapts the sales script")


@public_router.post("", status_code=status.HTTP_202_ACCEPTED)
def request_demo_call(body: WebIn, db: OrmSession = Depends(get_db)):
    if not body.consent:
        raise ValidationFailed("Sæt kryds, hvis vores assistent må ringe dig op",
                               field_errors=[{"field": "consent", "message": "Påkrævet"}])
    if body.consent_version != service.CONSENT_VERSION_WEB:
        raise ValidationFailed("Genindlæs siden og prøv igen", code="consent_outdated")
    if body.website:  # a bot filled the hidden field: same answer, nothing stored, nobody called
        return {"status": "calling"}
    from app.modules.voices import standard

    if body.voice is not None and body.voice not in standard.STANDARD_VOICES:
        raise ValidationFailed("Vælg en af stemmerne", field_errors=[{"field": "voice", "message": "Ukendt stemme"}])
    d = service.request_web(db, phone=body.phone, name=body.name, company=body.company, voice=body.voice,
                            industry=body.industry)
    db.commit()
    if d is not None and d.status == "failed":
        raise ApiError("Vi kunne ikke ringe op lige nu. Prøv igen om lidt, eller ring selv til vores demonummer.",
                       code="demo_call_failed", status_code=502)
    return {"status": "calling"}


@public_router.get("/voices/{key}/sample")
def demo_voice_sample(key: str):
    """A short sample of a voice the visitor can choose before being called. Rendered once, then served from cache."""
    from app.modules.voices import standard

    if key not in standard.STANDARD_VOICES:
        raise NotFound("Stemmen findes ikke")
    return Response(standard.sample_audio(key), media_type="audio/mpeg",
                    headers={"cache-control": "public, max-age=86400"})


class SellerIn(BaseModel):
    phone: str = Field(min_length=8, max_length=30)
    name: str = Field(default="", max_length=200)
    company: str = Field(min_length=1, max_length=200)
    cvr: str | None = Field(default=None, max_length=12)
    consent_confirmed: bool
    note: str = Field(default="", max_length=500)


@operator_router.get("")
def sales_status(db: OrmSession = Depends(get_db), _: Principal = Depends(operator)):
    return service.info(db) | {"problem": service.problem(db)}


@operator_router.get("/cvr/{cvr}")
def cvr_check(cvr: str, _: Principal = Depends(operator)):
    """CVR lookup incl. advertising protection, so the seller checks a company before ringing it."""
    from app.modules.business import cvr as cvr_register

    return cvr_register.lookup(cvr)


@operator_router.post("/demo-calls", status_code=status.HTTP_201_CREATED)
def seller_demo_call(body: SellerIn, request: Request, db: OrmSession = Depends(get_db),
                     principal: Principal = Depends(operator)):
    if not body.consent_confirmed:
        raise ValidationFailed("Bekræft at kontakten har sagt ja i telefonen",
                               field_errors=[{"field": "consent_confirmed", "message": "Påkrævet"}])
    d = service.request_seller(db, seller_id=principal.user.id, phone=body.phone, name=body.name, company=body.company,
                               cvr=body.cvr, note=body.note)
    record_audit(db, workspace_id=d.workspace_id, actor_user_id=principal.user.id, action="sales.demo_call",
                 object_type="demo_call", object_id=d.id,
                 after={"phone": d.phone, "company": d.company, "cvr": d.cvr, "status": d.status},
                 request_id=request.state.request_id)
    db.commit()
    return service.out(d)


@operator_router.get("/demo-calls")
def list_demo_calls(limit: int = Query(default=100, ge=1, le=500), db: OrmSession = Depends(get_db),
                    _: Principal = Depends(operator)):
    rows = db.scalars(select(DemoCall).order_by(DemoCall.created_at.desc()).limit(limit))
    return {"items": [service.out(d) for d in rows]}

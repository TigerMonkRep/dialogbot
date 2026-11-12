"""Demo calls: the public "Ring mig op nu" door on dialogbot.dk and the operator (seller) door. See service.py."""
from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from app.core.audit import record_audit
from app.core.auth import Principal
from app.core.errors import ApiError, NotFound, ValidationFailed
from app.db import get_db
from app.models import DemoCall
from app.modules.sales import service, verification
from app.modules.voices.operator_router import operator

public_router = APIRouter(prefix="/demo-call", tags=["sales"])
operator_router = APIRouter(prefix="/operator/sales", tags=["sales-operator"])


@public_router.get("")
def demo_info(db: OrmSession = Depends(get_db)):
    """Whether the website may offer "Ring mig op nu" (Peter then rings at once, day and night) and the public demo
    number."""
    return service.info(db)


class WebIn(BaseModel):
    phone: str = Field(min_length=8, max_length=30)
    name: str = Field(default="", max_length=200)
    company: str = Field(default="", max_length=200)
    consent: bool
    consent_version: str = Field(default=service.CONSENT_VERSION_WEB, max_length=40)
    website: str = Field(default="", max_length=200)  # honeypot: hidden in the form
    voice: str | None = Field(default=None, max_length=40, description="Ignored: the assistant that rings is always Peter (kept so older clients keep working)")
    industry: str | None = Field(default=None, max_length=40, description="Line of business; adapts the sales script")
    industry_other: str | None = Field(default=None, max_length=120, description="The visitor's own words when industry is 'andet'")
    verification_token: str | None = Field(default=None, max_length=100, description="From POST /demo-call/verify: proves the visitor holds `phone` (one use, 10 minutes). Required.")


def _check_consent(consent: bool, version: str) -> None:
    if not consent:
        raise ValidationFailed("Sæt kryds, hvis vores assistent må ringe dig op",
                               field_errors=[{"field": "consent", "message": "Påkrævet"}])
    if version != service.CONSENT_VERSION_WEB:  # incl. the retired «ring later» consent of 11/11
        raise ValidationFailed("Genindlæs siden og prøv igen", code="consent_outdated")


class DemoCodeIn(BaseModel):
    phone: str = Field(min_length=8, max_length=30)
    consent: bool
    consent_version: str = Field(default=service.CONSENT_VERSION_WEB, max_length=40)
    website: str = Field(default="", max_length=200)  # honeypot
    language: Literal["da", "en", "de", "es", "fr", "it", "no", "sv"] | None = Field(
        default=None, description="Language of the SMS text (the page's language); Danish by default")


@public_router.post("/code", status_code=status.HTTP_202_ACCEPTED)
def request_code(body: DemoCodeIn, request: Request, db: OrmSession = Depends(get_db)):
    """Step 1 of «Ring mig op nu»: a 6-digit code by SMS to the number (10 minutes, 5 attempts). Peter rings only
    after the code is entered (F-AUD26-02-P06). Limits per number and per client IP; 429 `sms_rate_limited`."""
    from app.modules.privat.lookup_limits import client_ip

    _check_consent(body.consent, body.consent_version)
    if body.website:  # a bot filled the hidden field: same answer, nothing stored, no SMS
        return {"status": "code_sent", "verification_id": str(uuid.uuid4()), "phone_display": None,
                "resend_after": int(verification.RESEND_AFTER.total_seconds()),
                "expires_in": int(verification.CODE_TTL.total_seconds())}
    out = verification.start(db, phone=body.phone, ip=client_ip(request), language=body.language)
    db.commit()
    return out


class DemoVerifyIn(BaseModel):
    verification_id: str = Field(min_length=1, max_length=64)
    code: str = Field(min_length=1, max_length=12)


@public_router.post("/verify")
def verify_code(body: DemoVerifyIn, db: OrmSession = Depends(get_db)):
    """Step 2: the code → `verification_token` (one use, bound to the number, 10 minutes). A wrong code answers 422
    `code_invalid` with `attempts_left`; after 5 attempts 409 `too_many_attempts`; expired 409 `code_expired`."""
    try:
        out = verification.verify(db, verification_id=body.verification_id, code=body.code)
    except ValidationFailed:
        db.commit()  # the attempt counts even though the request fails
        raise
    db.commit()
    return out


@public_router.post("", status_code=status.HTTP_202_ACCEPTED)
def request_demo_call(body: WebIn, request: Request, db: OrmSession = Depends(get_db)):
    """Step 3: Peter rings at once, day and night – only with a verified, unused token for this very number
    (422 `verification_required` without one, 409 `verification_invalid` for a used/expired/other number's token)."""
    from app.modules.privat.lookup_limits import client_ip

    _check_consent(body.consent, body.consent_version)
    if body.website:  # a bot filled the hidden field: same answer, nothing stored, nobody called
        return {"status": "calling"}
    from app.modules.voices import standard

    if body.voice is not None and body.voice not in standard.STANDARD_VOICES:
        raise ValidationFailed("Vælg en af stemmerne", field_errors=[{"field": "voice", "message": "Ukendt stemme"}])
    v = verification.consume(db, token=body.verification_token, phone=body.phone, ip=client_ip(request))
    d = service.request_web(db, phone=body.phone, name=body.name, company=body.company, voice=body.voice,
                            industry=body.industry, industry_other=body.industry_other,
                            consent_version=body.consent_version)
    if d is not None:
        v.demo_call_id = d.id
    db.commit()
    if d is not None and d.status == "failed":
        raise ApiError("Vi kunne ikke ringe op lige nu. Prøv igen om lidt, eller ring selv til vores demonummer.",
                       code="demo_call_failed", status_code=502)
    return {"status": "calling"}  # also for a do-not-call number: the same answer, nobody rung


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(..., min_length=1, max_length=service.CHAT_MAX_CHARS)


class ChatIn(BaseModel):
    messages: list[ChatTurn] = Field(..., min_length=1, max_length=service.CHAT_MAX_TURNS)
    website: str = Field(default="", max_length=200)  # honeypot


@public_router.post("/chat")
def demo_chat(body: ChatIn, db: OrmSession = Depends(get_db)):
    """The website chat: a visitor writes freely to Peter, who answers from the sales workspace's approved
    knowledge (the same knowledge the demo call uses). Nothing is stored about the visitor; every call is logged
    as AI usage on the sales workspace."""
    if body.messages[-1].role != "user":
        raise ValidationFailed("Sidste besked skal være fra kunden", code="chat_turn_order")
    if body.website:
        return {"reply": "Tak for din besked.", "refused": False}
    return service.chat_reply(db, [m.model_dump() for m in body.messages])


@public_router.get("/voices/{key}/sample")
def demo_voice_sample(key: str):
    """A short sample of Peter's voice, so a visitor can hear who will ring. Rendered once, then served from cache."""
    from app.modules.voices import standard

    if key != service.AGENT_VOICE:
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

"""Public quiz-funnel API (docs/funnel-api.md). No login until the reveal; per-IP limits; honeypot on the gate."""
from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, Header, Query, Request, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session as OrmSession

from app.core.auth import Principal, get_current_principal
from app.db import get_db
from app.modules.funnel import estimates, limits, service

router = APIRouter(prefix="/funnel", tags=["funnel"])


class UtmIn(BaseModel):
    source: str | None = Field(default=None, max_length=120)
    medium: str | None = Field(default=None, max_length=120)
    campaign: str | None = Field(default=None, max_length=120)
    content: str | None = Field(default=None, max_length=120)


class CreateIn(BaseModel):
    kind: Literal["erhverv", "privat"]
    hook: str | None = Field(default=None, max_length=80)
    industry: str | None = Field(default=None, max_length=40)
    utm: UtmIn | None = None


class PatchIn(BaseModel):
    step: int = Field(ge=1, le=service.MAX_STEP)
    answers: dict = Field(default_factory=dict)


class GateIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    email: EmailStr
    phone: str = Field(min_length=8, max_length=30)
    consent: bool
    website: str = Field(default="", max_length=200)  # honeypot: hidden in the form, bots fill it


class VerifyIn(BaseModel):
    code: str = Field(min_length=1, max_length=12)
    # The language the visitor saw the funnel in: the new account and its mails follow it (F-JE-08); default Danish.
    interface_language: Literal["da", "en", "de", "es", "fr", "it", "no", "sv"] | None = None


@router.get("/industries")
def industries():
    """The six buttons of «Hvad laver I?» and the «hvornår tager I ikke telefonen» chips."""
    return {"industries": [{"key": k, "label": v["label"], "playbook": estimates.playbook_label(k), "voice": v["voice"]}
                           for k, v in estimates.INDUSTRIES.items()],
            "missed": list(estimates.MISSED_CHOICES), "estimate_source": estimates.SOURCE}


@router.post("/drafts", status_code=status.HTTP_201_CREATED)
def create_draft(body: CreateIn, request: Request, db: OrmSession = Depends(get_db)):
    limits.hit(db, request, "create")
    d = service.create(db, kind=body.kind, hook=body.hook, industry=body.industry,
                       utm=body.utm.model_dump() if body.utm else None)
    db.commit()
    return service.out(db, d)


@router.get("/drafts/{draft_id}")
def get_draft(draft_id: uuid.UUID, db: OrmSession = Depends(get_db)):
    return service.out(db, service.get(db, draft_id))


@router.patch("/drafts/{draft_id}")
def patch_draft(draft_id: uuid.UUID, body: PatchIn, request: Request, background: BackgroundTasks,
                db: OrmSession = Depends(get_db)):
    """Idempotent: answers are merged. Step 2 looks the company up, step 4 fetches its website in the background."""
    limits.hit(db, request, "patch")
    d = service.get(db, draft_id, lock=True)
    d, crawl = service.patch(db, d, step=body.step, answers=body.answers)
    db.commit()
    if crawl:
        background.add_task(service.crawl_draft, d.id)
    return service.out(db, d)


@router.get("/places")
def places(request: Request, q: str = Query(min_length=1, max_length=120), industry: str | None = Query(default=None),
           db: OrmSession = Depends(get_db)):
    """Suggestions for «Hvad hedder virksomheden?». Google data (or demo data without a key) – nothing is stored."""
    limits.hit(db, request, "places")
    return {"items": service.search_places(q, estimates.normalize_industry(industry))}


@router.post("/drafts/{draft_id}/gate", status_code=status.HTTP_202_ACCEPTED)
def gate(draft_id: uuid.UUID, body: GateIn, request: Request, db: OrmSession = Depends(get_db)):
    """Name, e-mail and mobile → an SMS code. The consent text is shown next to the box (GET /funnel/consent)."""
    limits.hit(db, request, "gate")
    if body.website:  # a bot filled the hidden field: same answer, nothing stored, no SMS
        return {"status": "code_sent", "phone_display": None}
    d = service.get(db, draft_id, lock=True)
    out = service.gate(db, d, name=body.name, email=str(body.email), phone=body.phone, consent=body.consent)
    db.commit()
    return out


@router.get("/consent")
def consent():
    return {"version": service.CONSENT_VERSION, "erhverv": service.CONSENT_TEXT_ERHVERV,
            "privat": service.CONSENT_TEXT_PRIVAT}


@router.post("/drafts/{draft_id}/verify")
def verify(draft_id: uuid.UUID, body: VerifyIn, request: Request, background: BackgroundTasks,
           db: OrmSession = Depends(get_db), user_agent: str | None = Header(default=None)):
    """The code → the account, the session (same shape as POST /auth/login plus `session_token`), and the build."""
    limits.hit(db, request, "verify")
    d = service.get(db, draft_id, lock=True)
    out, jobs = service.verify(db, d, code=body.code, user_agent=user_agent, request_id=request.state.request_id,
                               lang=body.interface_language)
    db.commit()
    for fn, *args in jobs:
        background.add_task(fn, *args)
    return out


@router.get("/drafts/{draft_id}/reveal")
def reveal(draft_id: uuid.UUID, principal: Principal = Depends(get_current_principal),
           db: OrmSession = Depends(get_db)):
    """After verify, for the user the draft belongs to: the demo call's state (erhverv) or the private workspace."""
    return service.reveal(db, service.get(db, draft_id), principal.user)

"""Public early-access waitlist (P00).

The answer is identical whether the e-mail is new or already on the list, so the endpoint
cannot be used to find out who has signed up. A filled honeypot field is accepted silently
and not stored.
"""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session as OrmSession

from app.core.errors import ValidationFailed
from app.db import get_db
from app.models import WaitlistSignup

router = APIRouter(prefix="/waitlist", tags=["waitlist"])

CONSENT_VERSION = "waitlist-v1"
Industry = Literal["craft", "clinic", "service", "retail", "other"]
Interest = Literal["missed_calls", "calendar_booking", "quote_followup"]


class SignupIn(BaseModel):
    email: EmailStr
    industry: Industry | None = None
    interests: list[Interest] = Field(default_factory=list, max_length=3)
    source: Literal["p00", "p01"] = "p00"
    consent: bool
    # Honeypot: hidden in the form; people leave it empty.
    website: str = Field(default="", max_length=200)


@router.post("", status_code=status.HTTP_202_ACCEPTED)
def join_waitlist(body: SignupIn, db: OrmSession = Depends(get_db)):
    if not body.consent:
        raise ValidationFailed("Du skal acceptere, at vi må skrive til dig om lanceringen",
                               field_errors=[{"field": "consent", "message": "Påkrævet"}])
    if not body.website:
        values = {"email": str(body.email).strip().lower(), "industry": body.industry,
                  "interests": sorted(set(body.interests)), "source": body.source, "consent_version": CONSENT_VERSION}
        stmt = insert(WaitlistSignup).values(**values)
        db.execute(stmt.on_conflict_do_update(
            index_elements=[WaitlistSignup.email],
            set_={k: stmt.excluded[k] for k in ("industry", "interests", "consent_version")} | {"updated_at": stmt.excluded.created_at},
        ))
        db.commit()
    return {"status": "received"}

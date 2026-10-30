"""The customer's side of an offer: /public/offers/{token}. Reading needs only the link; accepting needs a logged-in,
e-mail-verified user (the existing signup flow) and creates the workspace (or uses one they administer), the
agreement with the offer's snapshot, and returns the card checkout to continue to."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session as OrmSession

from app.core.auth import Principal, get_current_principal
from app.db import get_db
from app.modules.sales import offers

router = APIRouter(prefix="/public/offers", tags=["public"])


@router.get("/{token}")
def view(token: str, db: OrmSession = Depends(get_db)):
    o = offers.by_token(db, token)
    out = offers.public_view(db, o)
    db.commit()  # an expired offer is stored as expired
    return out


class OfferAcceptIn(BaseModel):
    confirm: bool
    workspace_id: uuid.UUID | None = None
    workspace_name: str | None = Field(default=None, max_length=120)


@router.post("/{token}/accept")
def accept(token: str, body: OfferAcceptIn, request: Request, db: OrmSession = Depends(get_db),
           principal: Principal = Depends(get_current_principal)):
    from app.core.errors import ValidationFailed

    if not body.confirm:
        raise ValidationFailed("Bekræft, at du accepterer tilbuddet og vilkårene.", field_errors=[{"field": "confirm"}])
    out = offers.accept(db, token, principal.user, workspace_id=body.workspace_id, workspace_name=body.workspace_name,
                        request_id=request.state.request_id)
    db.commit()
    return out

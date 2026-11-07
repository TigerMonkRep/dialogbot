from __future__ import annotations

import re

from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from app.core.audit import record_audit
from app.core.errors import ValidationFailed
from app.core.idempotency import IdempotencyGuard
from app.db import get_db
from app.models import Campaign, CampaignContact, DoNotCall
from app.modules.public_api import cursor
from app.modules.public_api.auth import PublicPrincipal, require_scope
from app.modules.public_api.deps import idempotency_key_required
from app.modules.public_api.schemas import v1

router = APIRouter(prefix="/workspaces/{workspace_id}", tags=["campaigns"])


@router.get("/campaigns", response_model=v1.Page[v1.Campaign], summary="Kampagner, nyeste først")
def list_campaigns(p: cursor.CursorParams = Depends(),
                   status_filter: str | None = Query(default=None, alias="status",
                                                     pattern="^(draft|running|paused|completed|stopped)$"),
                   principal: PublicPrincipal = Depends(require_scope("campaigns:read")), db: OrmSession = Depends(get_db)):
    q = select(Campaign).where(Campaign.workspace_id == principal.workspace_id, Campaign.kind == "customer")
    if status_filter:
        q = q.where(Campaign.status == status_filter)
    rows = list(db.scalars(cursor.apply(q, p, Campaign.created_at, Campaign.id)))
    return cursor.page(rows, p, lambda c: c.created_at, lambda c: c.id, v1.campaign_out)


@router.get("/do-not-call", response_model=v1.Page[v1.DoNotCallEntry], summary="Ring-ikke-listen, nyeste først")
def list_dnc(p: cursor.CursorParams = Depends(), principal: PublicPrincipal = Depends(require_scope("campaigns:read")),
             db: OrmSession = Depends(get_db)):
    q = select(DoNotCall).where(DoNotCall.workspace_id == principal.workspace_id)
    rows = list(db.scalars(cursor.apply(q, p, DoNotCall.created_at, DoNotCall.id)))
    reveal = principal.has("contacts:read")
    return cursor.page(rows, p, lambda r: r.created_at, lambda r: r.id, lambda r: v1.dnc_out(r, reveal))


@router.post("/do-not-call", status_code=status.HTTP_201_CREATED, response_model=v1.DoNotCallEntry,
                summary="Tilføj et nummer til ring-ikke-listen (sikker skrivning)")
def add_dnc(body: v1.DoNotCallIn, request: Request, response: Response,
            idem: str = Depends(idempotency_key_required),
            principal: PublicPrincipal = Depends(require_scope("campaigns:write")), db: OrmSession = Depends(get_db)):
    """Never calls the number in any campaign again; pending campaign contacts with the number are skipped. Entries
    cannot be removed through the API (only an admin in the app can, and never those a person asked for in a call)."""
    from app.modules.campaigns.service import normalize_phone

    guard = IdempotencyGuard(db, f"{principal.idempotency_scope}:do_not_call.add", idem, body.model_dump())
    if guard.replay:
        st, replay = guard.replay
        response.status_code = st
        return replay
    phone = normalize_phone(body.phone)
    if phone is None:
        raise ValidationFailed("Ugyldigt telefonnummer", field_errors=[{"field": "phone"}])
    ws_id = principal.workspace_id
    row = db.scalar(select(DoNotCall).where(DoNotCall.workspace_id == ws_id, DoNotCall.phone == phone))
    created = row is None
    if created:
        row = DoNotCall(workspace_id=ws_id, phone=phone, reason=re.sub(r"\s+", " ", body.reason).strip(), source="api")
        db.add(row)
        db.flush()
        record_audit(db, workspace_id=ws_id, actor_user_id=None, action="do_not_call.added", object_type="do_not_call",
                     object_id=row.id, after={"phone": phone, "source": "api", "api_key_id": str(principal.key.id)},
                     request_id=getattr(request.state, "request_id", None))
    for x in db.scalars(select(CampaignContact).where(CampaignContact.workspace_id == ws_id, CampaignContact.phone == phone,
                                                      CampaignContact.status == "pending")):
        x.status = "skipped"
    out = v1.dnc_out(row, principal.has("contacts:read")).model_dump(mode="json")
    st = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    guard.store(st, out)
    db.commit()
    response.status_code = st
    return out

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from app.core.audit import record_audit
from app.core.auth import WorkspaceContext, get_scoped, require_capability
from app.core.errors import Conflict, NotFound, NotImplementedYet, ValidationFailed
from app.db import get_db
from app.models import Campaign, CampaignContact, DoNotCall, PhoneNumber
from app.modules.billing.agreements import TAX_BASIS_POINTS
from app.modules.billing.money import Money
from app.modules.campaigns import service

router = APIRouter(prefix="/workspaces/{workspace_id}", tags=["campaigns"])
HHMM = r"^([01]\d|2[0-3]):[0-5]\d$"


def campaign_out(db: OrmSession, c: Campaign) -> dict:
    return {"id": str(c.id), "name": c.name, "status": c.status, "version": c.version, "purpose": c.purpose,
            "opening": c.opening, "questions": list(c.questions or []), "success": c.success,
            "phone_number_id": str(c.phone_number_id) if c.phone_number_id else None,
            "call_days": list(c.call_days or []), "call_from": c.call_from, "call_to": c.call_to,
            "package": {"net_minor": c.package_net_minor, "max_attempts": c.max_attempts,
                        "max_connected_seconds": c.max_connected_seconds},
            "counts": service.counts(db, c), "max_cost": Money("DKK", service.max_cost_net_minor(db, c), TAX_BASIS_POINTS).snapshot(),
            "outbound_problem": service.outbound_problem(db, c), "legal_confirmation": c.legal_confirmation,
            "created_at": c.created_at.isoformat(), "started_at": c.started_at.isoformat() if c.started_at else None,
            "completed_at": c.completed_at.isoformat() if c.completed_at else None}


class CampaignIn(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    purpose: str = Field(default="", max_length=2000)
    opening: str = Field(default="", max_length=400)
    questions: list[str] = Field(default_factory=list, max_length=8)
    success: str = Field(default="", max_length=500)
    phone_number_id: uuid.UUID | None = None
    call_days: list[str] = Field(default_factory=lambda: ["mon", "tue", "wed", "thu", "fri"])
    call_from: str = Field(default="09:00", pattern=HHMM)
    call_to: str = Field(default="17:00", pattern=HHMM)


class CampaignUpdate(CampaignIn):
    expected_version: int


def _apply(db: OrmSession, c: Campaign, body: CampaignIn, ws_id) -> None:
    if any(d not in service.DAYS for d in body.call_days) or not body.call_days:
        raise ValidationFailed("Vælg mindst én ugedag", field_errors=[{"field": "call_days"}])
    if body.call_from >= body.call_to:
        raise ValidationFailed("Sluttidspunktet skal ligge efter starttidspunktet", field_errors=[{"field": "call_to"}])
    if body.phone_number_id is not None:
        get_scoped(db, PhoneNumber, body.phone_number_id, ws_id)
    c.name, c.purpose, c.opening, c.success = body.name.strip(), body.purpose.strip(), body.opening.strip(), body.success.strip()
    c.questions = [q.strip()[:200] for q in body.questions if q.strip()]
    c.phone_number_id = body.phone_number_id
    c.call_days = [d for d in service.DAYS if d in body.call_days]
    c.call_from, c.call_to = body.call_from, body.call_to


@router.get("/campaigns")
def list_campaigns(ctx: WorkspaceContext = Depends(require_capability("campaigns.read")), db: OrmSession = Depends(get_db)):
    rows = db.scalars(select(Campaign).where(Campaign.workspace_id == ctx.workspace.id).order_by(Campaign.created_at.desc()))
    return {"items": [campaign_out(db, c) for c in rows],
            "package": {"net_minor": service.PACKAGE_NET_MINOR, "max_attempts": service.MAX_ATTEMPTS,
                        "max_connected_seconds": service.MAX_CONNECTED_SECONDS},
            "legal_checklist": list(service.LEGAL_CHECKLIST)}


@router.post("/campaigns", status_code=201)
def create_campaign(body: CampaignIn, request: Request, ctx: WorkspaceContext = Depends(require_capability("campaigns.manage")),
                    db: OrmSession = Depends(get_db)):
    c = Campaign(workspace_id=ctx.workspace.id, name=body.name, created_by=ctx.user_id,
                 package_net_minor=service.PACKAGE_NET_MINOR, max_attempts=service.MAX_ATTEMPTS,
                 max_connected_seconds=service.MAX_CONNECTED_SECONDS)
    if body.phone_number_id is None:  # default: the workspace's first active number
        n = db.scalar(select(PhoneNumber).where(PhoneNumber.workspace_id == ctx.workspace.id, PhoneNumber.active)
                      .order_by(PhoneNumber.created_at))
        body.phone_number_id = n.id if n else None
    _apply(db, c, body, ctx.workspace.id)
    db.add(c)
    db.flush()
    record_audit(db, workspace_id=ctx.workspace.id, actor_user_id=ctx.user_id, action="campaigns.created",
                 object_type="campaign", object_id=c.id, request_id=request.state.request_id)
    db.commit()
    return campaign_out(db, c)


class SuggestIn(BaseModel):
    purpose: str = Field(default="", max_length=2000)


@router.post("/campaigns/script-suggestions")
def suggest_script(body: SuggestIn, ctx: WorkspaceContext = Depends(require_capability("campaigns.manage")),
                   db: OrmSession = Depends(get_db)):
    from app.modules.ai import suggest

    return suggest.campaign(db, ctx.workspace, ctx.user_id, body.purpose)


@router.get("/campaigns/{campaign_id}")
def get_campaign(campaign_id: uuid.UUID, ctx: WorkspaceContext = Depends(require_capability("campaigns.read")),
                 db: OrmSession = Depends(get_db)):
    return campaign_out(db, get_scoped(db, Campaign, campaign_id, ctx.workspace.id))


@router.put("/campaigns/{campaign_id}")
def update_campaign(campaign_id: uuid.UUID, body: CampaignUpdate, request: Request,
                    ctx: WorkspaceContext = Depends(require_capability("campaigns.manage")), db: OrmSession = Depends(get_db)):
    c = get_scoped(db, Campaign, campaign_id, ctx.workspace.id)
    if c.version != body.expected_version:
        raise Conflict("Kampagnen er ændret af en anden. Genindlæs.", code="version_conflict")
    if c.status in ("running", "completed"):
        raise Conflict("Sæt kampagnen på pause, før den ændres", code="campaign_running")
    _apply(db, c, body, ctx.workspace.id)
    c.version += 1
    record_audit(db, workspace_id=ctx.workspace.id, actor_user_id=ctx.user_id, action="campaigns.updated",
                 object_type="campaign", object_id=c.id, request_id=request.state.request_id)
    db.commit()
    return campaign_out(db, c)


class StartIn(BaseModel):
    expected_version: int
    legal_confirmed: bool
    accept_max_net_minor: int = Field(ge=0)


@router.post("/campaigns/{campaign_id}/start")
def start_campaign(campaign_id: uuid.UUID, body: StartIn, request: Request,
                   ctx: WorkspaceContext = Depends(require_capability("campaigns.manage")), db: OrmSession = Depends(get_db)):
    """The only way a campaign starts calling. Payment never starts calls."""
    from app.modules.ai.service import build_system_prompt

    c = db.scalar(select(Campaign).where(Campaign.id == campaign_id, Campaign.workspace_id == ctx.workspace.id)
                  .with_for_update())
    if c is None:
        raise NotFound("Kampagnen findes ikke")
    if c.version != body.expected_version:
        raise Conflict("Kampagnen er ændret af en anden. Genindlæs.", code="version_conflict")
    if c.status in ("running", "completed"):
        raise Conflict("Kampagnen kører allerede eller er afsluttet", code="campaign_state")
    if not body.legal_confirmed:
        raise ValidationFailed("Bekræft reglerne for opkald, før kampagnen startes", field_errors=[{"field": "legal_confirmed"}])
    if not c.purpose:
        raise ValidationFailed("Skriv formålet med opkaldet", field_errors=[{"field": "purpose"}])
    if not service.counts(db, c)["by_status"].get("pending"):
        raise ValidationFailed("Tilføj kontakter, der kan ringes op", field_errors=[{"field": "contacts"}])
    maximum = service.max_cost_net_minor(db, c)
    if body.accept_max_net_minor < maximum:
        raise Conflict("Prisen er ændret, siden du så den. Genindlæs og bekræft igen.", code="price_changed",
                       extra={"max_net_minor": maximum})
    build_system_prompt(db, ctx.workspace)  # 409 without approved knowledge: the assistant must know the business
    if problem := service.outbound_problem(db, c):
        raise NotImplementedYet(problem, code="outbound_not_configured", extra={"capability": "telephony.outbound"})
    now = datetime.now(UTC)
    c.status, c.started_at, c.version = "running", c.started_at or now, c.version + 1
    c.legal_confirmation = {"user_id": str(ctx.user_id), "at": now.isoformat(), "text_version": service.LEGAL_TEXT_VERSION,
                            "checklist": list(service.LEGAL_CHECKLIST), "accepted_max_net_minor": body.accept_max_net_minor}
    record_audit(db, workspace_id=ctx.workspace.id, actor_user_id=ctx.user_id, action="campaigns.started",
                 object_type="campaign", object_id=c.id, after={"max_net_minor": maximum},
                 request_id=request.state.request_id)
    db.commit()
    return campaign_out(db, c)


@router.post("/campaigns/{campaign_id}/pause")
def pause_campaign(campaign_id: uuid.UUID, request: Request,
                   ctx: WorkspaceContext = Depends(require_capability("campaigns.manage")), db: OrmSession = Depends(get_db)):
    c = get_scoped(db, Campaign, campaign_id, ctx.workspace.id)
    if c.status == "running":
        c.status, c.version = "paused", c.version + 1
        record_audit(db, workspace_id=ctx.workspace.id, actor_user_id=ctx.user_id, action="campaigns.paused",
                     object_type="campaign", object_id=c.id, request_id=request.state.request_id)
    db.commit()
    return campaign_out(db, c)


class ImportIn(BaseModel):
    csv: str = Field(min_length=1, max_length=2_000_000)
    kind: str
    consent_source: str = Field(default="", max_length=500)


@router.post("/campaigns/{campaign_id}/contacts/import")
def import_contacts(campaign_id: uuid.UUID, body: ImportIn, request: Request,
                    ctx: WorkspaceContext = Depends(require_capability("campaigns.manage")), db: OrmSession = Depends(get_db)):
    c = get_scoped(db, Campaign, campaign_id, ctx.workspace.id)
    if c.status == "completed":
        raise Conflict("Kampagnen er afsluttet", code="campaign_state")
    out = service.import_contacts(db, c, body.csv, kind=body.kind, consent_source=body.consent_source)
    record_audit(db, workspace_id=ctx.workspace.id, actor_user_id=ctx.user_id, action="campaigns.contacts_imported",
                 object_type="campaign", object_id=c.id, after={k: out[k] for k in ("added", "duplicates", "blocked")},
                 request_id=request.state.request_id)
    db.commit()
    return out | {"campaign": campaign_out(db, c)}


@router.get("/campaigns/{campaign_id}/contacts")
def list_contacts(campaign_id: uuid.UUID, status: str | None = None, limit: int = Query(default=200, ge=1, le=1000),
                  ctx: WorkspaceContext = Depends(require_capability("campaigns.read")), db: OrmSession = Depends(get_db)):
    c = get_scoped(db, Campaign, campaign_id, ctx.workspace.id)
    q = select(CampaignContact).where(CampaignContact.campaign_id == c.id)
    if status:
        q = q.where(CampaignContact.status == status)
    return {"items": [service.contact_out(x) for x in db.scalars(q.order_by(CampaignContact.created_at).limit(limit))]}


@router.delete("/campaigns/{campaign_id}/contacts/{contact_id}")
def delete_contact(campaign_id: uuid.UUID, contact_id: uuid.UUID,
                   ctx: WorkspaceContext = Depends(require_capability("campaigns.manage")), db: OrmSession = Depends(get_db)):
    c = get_scoped(db, Campaign, campaign_id, ctx.workspace.id)
    x = get_scoped(db, CampaignContact, contact_id, ctx.workspace.id)
    if x.campaign_id != c.id:
        raise NotFound("Kontakten findes ikke")
    if x.charged_at is not None or x.status == "calling":
        raise Conflict("Kontakten er allerede ringet op og kan ikke fjernes", code="contact_called")
    db.delete(x)
    db.commit()
    return {"deleted": True}


# --------------------------------------------------------------------------- do-not-call list

class DncIn(BaseModel):
    phone: str = Field(min_length=6, max_length=40)
    reason: str = Field(default="", max_length=300)


@router.get("/do-not-call")
def list_dnc(ctx: WorkspaceContext = Depends(require_capability("campaigns.read")), db: OrmSession = Depends(get_db)):
    rows = db.scalars(select(DoNotCall).where(DoNotCall.workspace_id == ctx.workspace.id).order_by(DoNotCall.created_at.desc()))
    return {"items": [{"id": str(r.id), "phone": r.phone, "reason": r.reason, "source": r.source,
                       "created_at": r.created_at.isoformat()} for r in rows]}


@router.post("/do-not-call", status_code=201)
def add_dnc(body: DncIn, ctx: WorkspaceContext = Depends(require_capability("campaigns.read")), db: OrmSession = Depends(get_db)):
    """Any staff member can block a number (someone asked not to be called); only admins can unblock."""
    phone = service.normalize_phone(body.phone)
    if phone is None:
        raise ValidationFailed("Ugyldigt telefonnummer", field_errors=[{"field": "phone"}])
    if not db.scalar(select(DoNotCall.id).where(DoNotCall.workspace_id == ctx.workspace.id, DoNotCall.phone == phone)):
        db.add(DoNotCall(workspace_id=ctx.workspace.id, phone=phone, reason=re.sub(r"\s+", " ", body.reason).strip(),
                         source="manual"))
    for x in db.scalars(select(CampaignContact).where(CampaignContact.workspace_id == ctx.workspace.id,
                                                      CampaignContact.phone == phone, CampaignContact.status == "pending")):
        x.status = "skipped"
    db.commit()
    return {"phone": phone}


@router.delete("/do-not-call/{entry_id}")
def delete_dnc(entry_id: uuid.UUID, ctx: WorkspaceContext = Depends(require_capability("campaigns.manage")),
               db: OrmSession = Depends(get_db)):
    r = get_scoped(db, DoNotCall, entry_id, ctx.workspace.id)
    if r.source == "call":
        raise Conflict("Personen har selv frabedt sig opkald i et opkald og kan ikke fjernes fra listen", code="opted_out")
    db.delete(r)
    db.commit()
    return {"deleted": True}

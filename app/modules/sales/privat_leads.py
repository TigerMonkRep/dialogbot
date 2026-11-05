"""Operator surface for the lead loop: the businesses that heard the closing line in a Privat call, with the lead, the cooldown
and two actions: «Send intro-mail» and «Spær». Only admin/owner of the sales workspace (SALES_WORKSPACE_ID); anyone else gets 404
(not a member) or 403 (member without the role). docs/sales/privat-opkald-leads.md."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session as OrmSession

from app.config import get_settings
from app.core.audit import record_audit
from app.core.auth import ROLE_RANK, Principal, get_current_principal
from app.core.errors import Conflict, Forbidden, NotFound
from app.core.outbox import enqueue
from app.db import get_db
from app.models import BusinessBookingProfile, ExternalBusinessContact, Lead, Membership, Task
from app.modules.integrations import email_templates as tpl
from app.modules.leads import service as leads
from app.modules.sales import outbound, service

router = APIRouter(prefix="/operator/sales/privat-leads", tags=["sales-operator"])


class BlockIn(BaseModel):
    reason: str = Field(default="Spærret af en sælger", max_length=300)


def sales_admin(principal: Principal = Depends(get_current_principal), db: OrmSession = Depends(get_db)) -> Principal:
    ws = service.sales_workspace(db)
    m = db.scalar(select(Membership).where(Membership.workspace_id == ws.id, Membership.user_id == principal.user.id)) if ws else None
    if m is None:
        raise NotFound("Findes ikke")                                   # nothing reveals that the sales workspace exists
    if ROLE_RANK[m.role] < ROLE_RANK["admin"]:
        raise Forbidden("Kun admin og ejer i salgsarbejdsrummet kan se og bruge Privat-opkald som kilde", code="forbidden")
    return principal


def _out(db: OrmSession, r: ExternalBusinessContact) -> dict:
    days = get_settings().lead_pitch_cooldown_days
    engine = None
    if r.booking_profile_id:
        prof = db.get(BusinessBookingProfile, r.booking_profile_id)
        engine = prof.engine if prof else None
    return {"id": str(r.id), "source": "Privat-opkald", "name": r.name, "phone": r.phone_e164, "cvr": r.cvr,
            "booking_engine": engine, "outcome": r.last_outcome, "last_pitch_at": r.last_pitch_at.isoformat() if r.last_pitch_at else None,
            "cooldown_until": (r.last_pitch_at + timedelta(days=days)).isoformat() if r.last_pitch_at else None,
            "pitch_count": r.pitch_count, "blocklisted": r.blocklisted, "blocklist_reason": r.blocklist_reason,
            "consent_to_email": r.consent_to_email, "email": r.email if r.consent_to_email else None,
            "lead_id": str(r.lead_id) if r.lead_id else None,
            "intro_mail_sent": _mail_sent(db, r.id)}


def _key(contact_id: uuid.UUID) -> str:
    return f"intro-mail:{contact_id}"


def _mail_sent(db: OrmSession, contact_id: uuid.UUID) -> bool:
    from app.models import OutboxEvent

    return db.scalar(select(OutboxEvent.id).where(OutboxEvent.dedupe_key == _key(contact_id))) is not None


def _contact(db: OrmSession, contact_id: uuid.UUID) -> ExternalBusinessContact:
    r = db.get(ExternalBusinessContact, contact_id)
    if r is None or (r.lead_id is None and r.last_pitch_at is None):
        raise NotFound("Virksomheden findes ikke")
    return r


@router.get("")
def list_privat_leads(db: OrmSession = Depends(get_db), _: Principal = Depends(sales_admin)):
    rows = db.scalars(select(ExternalBusinessContact).where(or_(ExternalBusinessContact.last_pitch_at.is_not(None),
                                                               ExternalBusinessContact.lead_id.is_not(None)))
                      .order_by(ExternalBusinessContact.last_pitch_at.desc().nullslast()).limit(200))
    return {"items": [_out(db, r) for r in rows], "cooldown_days": get_settings().lead_pitch_cooldown_days}


@router.post("/{contact_id}/intro-mail")
def send_intro_mail(contact_id: uuid.UUID, db: OrmSession = Depends(get_db), p: Principal = Depends(sales_admin)):
    """One fixed mail (email_templates.intro_mail) through the normal outbox. Only to an address given with an explicit yes, once."""
    r = _contact(db, contact_id)
    if r.blocklisted or not r.consent_to_email or not r.email:
        raise Conflict("Virksomheden har ikke sagt ja til en mail, eller den er spærret", code="no_consent")
    ws = service.sales_workspace(db)
    if _mail_sent(db, r.id):
        return {"sent": False, "already_sent": True}
    enqueue(db, event_type="email.branded", dedupe_key=_key(r.id), workspace_id=ws.id,
            payload={"to_email": r.email, "email": tpl.to_payload(tpl.intro_mail(r.name))})
    lead = db.get(Lead, r.lead_id) if r.lead_id else None
    if lead is not None:
        leads.update_lead(db, lead, actor=p.user.id, expected_version=lead.version, changes={"pipeline_status": "contacted"},
                          request_id=None)
        for t in db.scalars(select(Task).where(Task.lead_id == lead.id, Task.status == "open", Task.title.like("Send intro-mail%"))):
            t.status, t.completed_at, t.completed_by = "done", datetime.now(UTC), p.user.id
    record_audit(db, workspace_id=ws.id, actor_user_id=p.user.id, action="privat_lead.intro_mail", object_type="external_business_contact",
                 object_id=r.id, after={"to": "consented address"}, request_id=None)
    db.commit()
    return {"sent": True, "already_sent": False}


@router.post("/{contact_id}/block")
def block_business(contact_id: uuid.UUID, body: BlockIn, db: OrmSession = Depends(get_db), p: Principal = Depends(sales_admin)):
    """Never contact this business again: block list (phone + CVR), and the stored address and consent are dropped."""
    r = _contact(db, contact_id)
    for kind, value in (("phone", r.phone_e164), ("cvr", r.cvr)):
        if value:
            outbound.block(db, kind=kind, value=value, reason=body.reason, source="manual", user_id=p.user.id)
    r.blocklisted, r.blocklist_reason = True, "manual"
    r.email, r.consent_to_email, r.consent_at = None, False, None
    ws = service.sales_workspace(db)
    record_audit(db, workspace_id=ws.id, actor_user_id=p.user.id, action="privat_lead.blocked", object_type="external_business_contact",
                 object_id=r.id, after={"reason": body.reason}, request_id=None)
    db.commit()
    return _out(db, r)

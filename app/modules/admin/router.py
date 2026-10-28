"""Operator admin: one simple overview, customers, users and operations – all READ-ONLY – plus "se som kunde".

Everything here is for Dialogbot platform operators only. The overview answers "is everything fine, and what needs me?";
every detail view carries an `advanced` block with the raw rows for when the simple picture is not enough. Secrets
(password hashes, token hashes, encrypted CPR/bank, provider keys) are never returned.

"View as" opens a normal session for the chosen user that is read-only (see app.core.auth), lasts one hour, cannot open
another view-as and is audited when it starts and when it is ended."""
from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel
from sqlalchemy import desc, func, inspect, or_, select
from sqlalchemy.orm import Session as OrmSession

from app.core.audit import record_audit
from app.core.auth import Principal
from app.core.errors import Forbidden, NotFound, ValidationFailed
from app.core.security import new_token, token_digest
from app.db import get_db
from app.models import (
    Ambassador,
    AuditLog,
    BillingAccount,
    Call,
    Campaign,
    Conversation,
    EmailDelivery,
    Invoice,
    Lead,
    Membership,
    OutboxEvent,
    Referral,
    Session,
    SocialPost,
    TelephonySetup,
    User,
    Workspace,
)
from app.modules.voices.operator_router import operator

router = APIRouter(prefix="/operator/admin", tags=["admin-operator"])

VIEW_AS_MINUTES = 60
_SECRET_PARTS = ("password", "token_hash", "_enc", "secret", "api_key", "access_token", "refresh_token", "cpr", "bank_enc")


def _now() -> datetime:
    return datetime.now(UTC)


def _json(v: Any) -> Any:
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    if isinstance(v, (uuid.UUID, Decimal)):
        return str(v)
    if isinstance(v, (bytes, bytearray, memoryview)):
        return "<binært>"
    return v


def raw(obj: Any) -> dict:
    """All columns of a row for the 'avanceret' view, without anything secret."""
    out = {}
    for col in inspect(obj).mapper.column_attrs:
        k = col.key
        out[k] = "<skjult>" if any(p in k.lower() for p in _SECRET_PARTS) and getattr(obj, k) is not None else _json(getattr(obj, k))
    return out


def _iso(d: datetime | None) -> str | None:
    return d.isoformat() if d else None


# --------------------------------------------------------------------------- overview

@router.get("/overview")
def overview(db: OrmSession = Depends(get_db), principal: Principal = Depends(operator)):
    """Traffic light + the few numbers that matter + the list of things that need attention."""
    from app.config import get_settings
    from app.migrations_head import schema_status

    now = _now()
    day, week = now - timedelta(days=1), now - timedelta(days=7)
    st = schema_status(db)
    queued = db.scalar(select(func.count()).select_from(OutboxEvent).where(OutboxEvent.status.in_(("queued", "processing")))) or 0
    oldest = db.scalar(select(func.min(OutboxEvent.created_at)).where(OutboxEvent.status == "queued"))
    failed = db.scalars(select(OutboxEvent).where(OutboxEvent.status.in_(("failed", "blocked")), OutboxEvent.created_at > week)
                        .order_by(desc(OutboxEvent.created_at)).limit(10)).all()
    mail_failed = db.scalar(select(func.count()).select_from(EmailDelivery).where(EmailDelivery.status == "failed", EmailDelivery.created_at > day)) or 0
    drafts = db.scalars(select(SocialPost).where(SocialPost.status == "draft", SocialPost.slot_date >= now.date())
                        .order_by(SocialPost.scheduled_for).limit(5)).all()
    bad_invoices = db.scalars(select(Invoice).where(Invoice.status.in_(("payment_failed", "failed"))).order_by(desc(Invoice.created_at)).limit(5)).all()
    pending_amb = db.scalar(select(func.count()).select_from(Ambassador).where(Ambassador.status == "pending")) or 0

    attention: list[dict] = []
    if not st["ok"]:
        attention.append({"level": "red", "title": "Databasen og koden er ikke på samme version",
                          "detail": f"Database {st['database']}, kode {st['code']}. Workeren holder pause i planlagte jobs.", "href": "/app/operator/admin/drift"})
    if oldest and now - oldest > timedelta(minutes=10):
        attention.append({"level": "red", "title": "Opgavekøen sidder fast",
                          "detail": f"Ældste ventende opgave er fra {oldest.astimezone(UTC):%H:%M} UTC.", "href": "/app/operator/admin/drift"})
    for e in failed[:3]:
        attention.append({"level": "amber", "title": f"Opgave fejlede: {e.event_type}", "detail": (e.last_error or "")[:140], "href": "/app/operator/admin/drift"})
    if mail_failed:
        attention.append({"level": "amber", "title": f"{mail_failed} e-mails fejlede det seneste døgn", "detail": "", "href": "/app/operator/admin/drift"})
    for p in drafts:
        attention.append({"level": "blue", "title": f"Opslag venter på godkendelse ({p.platform})",
                          "detail": p.scheduled_for.isoformat(), "href": "/app/operator/social"})
    for i in bad_invoices:
        attention.append({"level": "amber", "title": f"Faktura {i.month:%Y-%m} er ikke betalt ({i.status})", "detail": str(i.workspace_id), "href": f"/app/operator/admin/kunder/{i.workspace_id}"})
    if pending_amb:
        attention.append({"level": "blue", "title": f"{pending_amb} ambassadør(er) venter på svar", "detail": "", "href": "/app/operator/ambassadors"})

    level = "red" if any(a["level"] == "red" for a in attention) else "amber" if any(a["level"] == "amber" for a in attention) else "green"
    s = get_settings()
    return {
        "status": level,
        "environment": s.app_env,
        "schema": st,
        "tiles": {
            "workspaces": db.scalar(select(func.count()).select_from(Workspace).where(Workspace.status == "active")) or 0,
            "users": db.scalar(select(func.count()).select_from(User).where(User.is_active.is_(True))) or 0,
            "new_workspaces_7d": db.scalar(select(func.count()).select_from(Workspace).where(Workspace.created_at > week)) or 0,
            "calls_7d": db.scalar(select(func.count()).select_from(Call).where(Call.started_at > week)) or 0,
            "conversations_7d": db.scalar(select(func.count()).select_from(Conversation).where(Conversation.created_at > week)) or 0,
            "leads_7d": db.scalar(select(func.count()).select_from(Lead).where(Lead.created_at > week)) or 0,
            "campaigns_running": db.scalar(select(func.count()).select_from(Campaign).where(Campaign.status == "running")) or 0,
            "ambassadors_active": db.scalar(select(func.count()).select_from(Ambassador).where(Ambassador.status == "active")) or 0,
            "queue": queued,
        },
        "attention": attention,
    }


# --------------------------------------------------------------------------- customers

def _owner(db: OrmSession, ws_id: uuid.UUID) -> User | None:
    return db.scalar(select(User).join(Membership, Membership.user_id == User.id)
                     .where(Membership.workspace_id == ws_id, Membership.role == "owner").order_by(Membership.created_at).limit(1))


@router.get("/customers")
def customers(q: str = Query(default="", max_length=100), limit: int = Query(default=50, ge=1, le=200),
              db: OrmSession = Depends(get_db), principal: Principal = Depends(operator)):
    stmt = select(Workspace).order_by(desc(Workspace.created_at)).limit(limit)
    if q.strip():
        like = f"%{q.strip().lower()}%"
        member_ws = select(Membership.workspace_id).join(User, User.id == Membership.user_id).where(
            or_(func.lower(User.email).like(like), func.lower(User.display_name).like(like)))
        stmt = select(Workspace).where(or_(func.lower(Workspace.name).like(like), Workspace.id.in_(member_ws))) \
            .order_by(desc(Workspace.created_at)).limit(limit)
    week = _now() - timedelta(days=30)
    out = []
    for ws in db.scalars(stmt):
        owner = _owner(db, ws.id)
        members = db.scalar(select(func.count()).select_from(Membership).where(Membership.workspace_id == ws.id)) or 0
        calls = db.scalar(select(func.count()).select_from(Call).where(Call.workspace_id == ws.id, Call.started_at > week)) or 0
        seen = db.scalar(select(func.max(Session.last_seen_at)).join(Membership, Membership.user_id == Session.user_id)
                         .where(Membership.workspace_id == ws.id, Session.impersonator_user_id.is_(None)))
        out.append({"id": str(ws.id), "name": ws.name, "status": ws.status, "product_intent": ws.product_intent,
                    "created_at": _iso(ws.created_at), "owner_email": owner.email if owner else None, "members": members,
                    "calls_30d": calls, "last_seen_at": _iso(seen)})
    return {"items": out}


@router.get("/customers/{workspace_id}")
def customer(workspace_id: uuid.UUID, db: OrmSession = Depends(get_db), principal: Principal = Depends(operator)):
    ws = db.get(Workspace, workspace_id)
    if ws is None:
        raise NotFound("Kunden findes ikke")
    members = db.execute(select(Membership, User).join(User, User.id == Membership.user_id)
                         .where(Membership.workspace_id == ws.id).order_by(Membership.created_at)).all()
    seen = {uid: ts for uid, ts in db.execute(select(Session.user_id, func.max(Session.last_seen_at))
                                              .where(Session.impersonator_user_id.is_(None)).group_by(Session.user_id))}
    billing = db.get(BillingAccount, ws.id)
    tel = db.scalar(select(TelephonySetup).where(TelephonySetup.workspace_id == ws.id))
    ref = db.get(Referral, ws.id)
    amb = db.get(Ambassador, ref.ambassador_id) if ref else None
    invoices = db.scalars(select(Invoice).where(Invoice.workspace_id == ws.id).order_by(desc(Invoice.month)).limit(12)).all()
    calls = db.scalars(select(Call).where(Call.workspace_id == ws.id).order_by(desc(Call.started_at)).limit(10)).all()
    campaigns = db.scalars(select(Campaign).where(Campaign.workspace_id == ws.id).order_by(desc(Campaign.created_at)).limit(10)).all()
    audit = db.scalars(select(AuditLog).where(AuditLog.workspace_id == ws.id).order_by(desc(AuditLog.created_at)).limit(25)).all()
    return {
        "id": str(ws.id), "name": ws.name, "status": ws.status, "product_intent": ws.product_intent,
        "created_at": _iso(ws.created_at),
        "members": [{"user_id": str(u.id), "email": u.email, "name": u.display_name, "role": m.role, "active": u.is_active,
                     "verified": u.email_verified_at is not None, "is_operator": u.is_platform_operator,
                     "last_seen_at": _iso(seen.get(u.id))} for m, u in members],
        "billing": ({"card": f"{billing.card_brand} ····{billing.card_last4}" if billing.card_last4 else None,
                     "billing_email": billing.billing_email, "stripe_customer": bool(billing.stripe_customer_id)} if billing else None),
        "telephony": ({"state": tel.state, "business_number": tel.business_number, "documents_status": tel.documents_status} if tel else None),
        "ambassador": ({"id": str(amb.id), "name": amb.full_name, "via": ref.via} if amb and ref else None),
        "invoices": [{"month": i.month.isoformat(), "status": i.status, "gross_minor": i.gross_minor, "number": i.number} for i in invoices],
        "calls": [{"started_at": _iso(c.started_at), "from": c.from_number, "seconds": c.duration_seconds, "reason": c.ended_reason,
                   "summary": c.summary[:200]} for c in calls],
        "campaigns": [{"id": str(c.id), "name": c.name, "status": c.status, "created_at": _iso(c.created_at)} for c in campaigns],
        "audit": [{"at": _iso(a.created_at), "action": a.action, "actor": str(a.actor_user_id) if a.actor_user_id else None,
                   "object": f"{a.object_type}:{a.object_id}"} for a in audit],
        "advanced": {"workspace": raw(ws), "billing_account": raw(billing) if billing else None,
                     "telephony_setup": raw(tel) if tel else None, "invoices": [raw(i) for i in invoices],
                     "campaigns": [raw(c) for c in campaigns], "audit": [raw(a) for a in audit]},
    }


# --------------------------------------------------------------------------- users

@router.get("/users")
def users(q: str = Query(default="", max_length=100), limit: int = Query(default=50, ge=1, le=200),
          db: OrmSession = Depends(get_db), principal: Principal = Depends(operator)):
    stmt = select(User).order_by(desc(User.created_at)).limit(limit)
    if q.strip():
        like = f"%{q.strip().lower()}%"
        stmt = select(User).where(or_(func.lower(User.email).like(like), func.lower(User.display_name).like(like))) \
            .order_by(desc(User.created_at)).limit(limit)
    out = []
    for u in db.scalars(stmt):
        ms = db.execute(select(Membership.role, Workspace.id, Workspace.name).join(Workspace, Workspace.id == Membership.workspace_id)
                        .where(Membership.user_id == u.id)).all()
        amb = db.scalar(select(Ambassador).where(Ambassador.user_id == u.id))
        seen = db.scalar(select(func.max(Session.last_seen_at)).where(Session.user_id == u.id, Session.impersonator_user_id.is_(None)))
        out.append({"id": str(u.id), "email": u.email, "name": u.display_name, "active": u.is_active,
                    "verified": u.email_verified_at is not None, "is_operator": u.is_platform_operator,
                    "created_at": _iso(u.created_at), "last_seen_at": _iso(seen),
                    "workspaces": [{"id": str(w), "name": n, "role": r} for r, w, n in ms],
                    "ambassador": ({"id": str(amb.id), "status": amb.status, "kind": amb.kind} if amb else None)})
    return {"items": out}


@router.get("/users/{user_id}")
def user_detail(user_id: uuid.UUID, db: OrmSession = Depends(get_db), principal: Principal = Depends(operator)):
    u = db.get(User, user_id)
    if u is None:
        raise NotFound("Brugeren findes ikke")
    amb = db.scalar(select(Ambassador).where(Ambassador.user_id == u.id))
    sessions = db.scalars(select(Session).where(Session.user_id == u.id).order_by(desc(Session.created_at)).limit(10)).all()
    return {"user": raw(u), "ambassador": raw(amb) if amb else None,
            "sessions": [{"created_at": _iso(s.created_at), "last_seen_at": _iso(s.last_seen_at), "revoked": s.revoked_at is not None,
                          "view_as": s.impersonator_user_id is not None, "user_agent": s.user_agent} for s in sessions]}


# --------------------------------------------------------------------------- operations

@router.get("/operations")
def operations(db: OrmSession = Depends(get_db), principal: Principal = Depends(operator)):
    now = _now()
    by_status = dict(db.execute(select(OutboxEvent.status, func.count()).where(OutboxEvent.created_at > now - timedelta(days=7))
                                .group_by(OutboxEvent.status)).all())
    failed = db.scalars(select(OutboxEvent).where(OutboxEvent.status.in_(("failed", "blocked"))).order_by(desc(OutboxEvent.created_at)).limit(25)).all()
    mails = db.scalars(select(EmailDelivery).order_by(desc(EmailDelivery.created_at)).limit(25)).all()
    audit = db.scalars(select(AuditLog).order_by(desc(AuditLog.created_at)).limit(40)).all()
    from app.migrations_head import schema_status
    return {"schema": schema_status(db), "outbox_7d": by_status,
            "failed_jobs": [{"id": str(e.id), "type": e.event_type, "status": e.status, "attempts": e.attempts, "error": (e.last_error or "")[:300],
                             "at": _iso(e.created_at), "workspace_id": str(e.workspace_id) if e.workspace_id else None} for e in failed],
            "emails": [{"at": _iso(m.created_at), "to": m.to_email, "subject": m.subject, "status": m.status,
                        "provider_status": m.provider_status, "adapter": m.adapter} for m in mails],
            "audit": [{"at": _iso(a.created_at), "action": a.action, "workspace_id": str(a.workspace_id) if a.workspace_id else None,
                       "actor": str(a.actor_user_id) if a.actor_user_id else None, "object": f"{a.object_type}:{a.object_id}"} for a in audit],
            "links": {"render": "https://dashboard.render.com", "supabase": "https://supabase.com/dashboard", "vercel": "https://vercel.com"}}


# --------------------------------------------------------------------------- view as

class ViewAsIn(BaseModel):
    user_id: uuid.UUID
    workspace_id: uuid.UUID | None = None


@router.post("/view-as")
def view_as(body: ViewAsIn, request: Request, db: OrmSession = Depends(get_db), principal: Principal = Depends(operator)):
    """Open a read-only session as this user. The raw token is returned once; the caller (the web BFF) keeps it in an
    httpOnly cookie. Operators cannot be viewed (and a view-as session cannot start another one)."""
    if principal.session.impersonator_user_id is not None:
        raise Forbidden("Afslut den nuværende visning først", code="view_as_nested")
    target = db.get(User, body.user_id)
    if target is None or not target.is_active:
        raise NotFound("Brugeren findes ikke eller er deaktiveret")
    if target.is_platform_operator:
        raise ValidationFailed("Dialogbot-operatører kan ikke ses som kunde", code="view_as_operator")
    if body.workspace_id is not None and db.scalar(select(Membership).where(Membership.user_id == target.id, Membership.workspace_id == body.workspace_id)) is None:
        raise ValidationFailed("Brugeren er ikke medlem af det arbejdsrum", code="not_a_member")
    raw_token = new_token()
    exp = _now() + timedelta(minutes=VIEW_AS_MINUTES)
    db.add(Session(user_id=target.id, token_hash=token_digest(raw_token), expires_at=exp,
                   user_agent="se-som-kunde", impersonator_user_id=principal.user.id))
    record_audit(db, workspace_id=body.workspace_id, actor_user_id=principal.user.id, action="admin.view_as.start", object_type="user",
                 object_id=target.id, after={"email": target.email, "expires_at": exp.isoformat()}, request_id=request.state.request_id)
    db.commit()
    return {"token": raw_token, "expires_at": exp.isoformat(), "user": {"id": str(target.id), "email": target.email, "name": target.display_name},
            "ambassador": db.scalar(select(func.count()).select_from(Ambassador).where(Ambassador.user_id == target.id)) > 0}


from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session as OrmSession

from app.config import get_settings
from app.core.audit import record_audit
from app.core.auth import WorkspaceContext
from app.core.errors import Conflict, Forbidden, NotFound, ValidationFailed
from app.core.outbox import enqueue
from app.core.security import new_token, normalize_email, token_digest
from app.models import (
    ROLE_RANK,
    BusinessProfile,
    GoalSelection,
    Invitation,
    LanguageSettings,
    Membership,
    User,
    Workspace,
)
from app.modules.identity.service import INTENTS


def _now() -> datetime:
    return datetime.now(UTC)


def _slugify(name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.lower().replace("æ", "ae").replace("ø", "oe").replace("å", "aa")).strip("-")
    return (base or "arbejdsrum")[:100]


def create_workspace(db: OrmSession, *, user: User, name: str, product_intent: str | None,
                     request_id: str | None = None) -> Workspace:
    if user.email_verified_at is None:
        raise Forbidden("Bekræft din e-mail, før du opretter et arbejdsrum", code="email_not_verified")
    intent = product_intent or user.signup_intent or "reception"
    if intent not in INTENTS:
        raise ValidationFailed("Ugyldig produktintention", field_errors=[{"field": "product_intent"}])
    slug = _slugify(name)
    n = 1
    while db.scalar(select(Workspace).where(Workspace.slug == slug)):
        n += 1
        slug = f"{_slugify(name)}-{n}"
    ws = Workspace(name=name.strip(), slug=slug, product_intent=intent, created_by=user.id)
    db.add(ws)
    db.flush()
    db.add(Membership(workspace_id=ws.id, user_id=user.id, role="owner"))
    # Seed the editable configuration rows with the preserved intent (A06 → O03).
    db.add(BusinessProfile(workspace_id=ws.id, legal_name=name.strip()))
    db.add(GoalSelection(workspace_id=ws.id, product_intent=intent,
                         inbound_phone=intent in ("reception", "both")))
    db.add(LanguageSettings(workspace_id=ws.id, interface_language=user.interface_language or "da"))
    record_audit(db, workspace_id=ws.id, actor_user_id=user.id, action="workspace.created", object_type="workspace",
                 object_id=ws.id, after={"name": ws.name, "product_intent": intent}, request_id=request_id)
    return ws


def list_workspaces_for_user(db: OrmSession, user_id: uuid.UUID) -> list[tuple[Workspace, Membership]]:
    rows = db.execute(
        select(Workspace, Membership).join(Membership, Membership.workspace_id == Workspace.id)
        .where(Membership.user_id == user_id, Workspace.status != "closed").order_by(Workspace.created_at)
    )
    return [(w, m) for w, m in rows]


def count_owners(db: OrmSession, workspace_id: uuid.UUID) -> int:
    return db.scalar(select(func.count()).select_from(Membership)
                     .where(Membership.workspace_id == workspace_id, Membership.role == "owner")) or 0


def change_role(db: OrmSession, ctx: WorkspaceContext, membership_id: uuid.UUID, new_role: str,
                request_id: str | None = None) -> Membership:
    if new_role not in ROLE_RANK:
        raise ValidationFailed("Ugyldig rolle", field_errors=[{"field": "role"}])
    m = db.scalar(select(Membership).where(Membership.id == membership_id,
                                           Membership.workspace_id == ctx.workspace.id).with_for_update())
    if m is None:
        raise NotFound("Medlemskabet findes ikke")
    ctx.require("members.change_role")
    # Nobody may grant a role above their own; only owners may grant/revoke owner.
    if ROLE_RANK[new_role] > ROLE_RANK[ctx.role] or (m.role == "owner" and ctx.role != "owner"):
        raise Forbidden("Du kan ikke tildele eller ændre en rolle over din egen", code="role_escalation")
    if new_role == "owner":
        ctx.require("members.assign_owner")
    if m.role == "owner" and new_role != "owner" and count_owners(db, ctx.workspace.id) <= 1:
        raise Conflict("Arbejdsrummet skal have mindst én ejer. Tildel ejerrollen til en anden først.",
                       code="last_owner")
    before = m.role
    m.role = new_role
    record_audit(db, workspace_id=ctx.workspace.id, actor_user_id=ctx.user_id, action="membership.role_changed",
                 object_type="membership", object_id=m.id, before={"role": before}, after={"role": new_role},
                 request_id=request_id)
    return m


def remove_member(db: OrmSession, ctx: WorkspaceContext, membership_id: uuid.UUID,
                  request_id: str | None = None) -> None:
    m = db.scalar(select(Membership).where(Membership.id == membership_id,
                                           Membership.workspace_id == ctx.workspace.id).with_for_update())
    if m is None:
        raise NotFound("Medlemskabet findes ikke")
    if m.user_id != ctx.user_id:
        ctx.require("members.remove")
        if m.role == "owner" and ctx.role != "owner":
            raise Forbidden("Kun en ejer kan fjerne en ejer", code="role_escalation")
    if m.role == "owner" and count_owners(db, ctx.workspace.id) <= 1:
        raise Conflict("Den sidste ejer kan ikke fjernes uden overdragelse af ejerskab", code="last_owner")
    record_audit(db, workspace_id=ctx.workspace.id, actor_user_id=ctx.user_id, action="membership.removed",
                 object_type="membership", object_id=m.id, before={"user_id": str(m.user_id), "role": m.role},
                 request_id=request_id)
    db.delete(m)


# --- Invitations ------------------------------------------------------------


def create_invitation(db: OrmSession, ctx: WorkspaceContext, *, email: str, role: str,
                      request_id: str | None = None) -> tuple[Invitation, bool]:
    """Returns (invitation, created). An existing pending invitation for the same
    email is returned unchanged (created=False) instead of a duplicate."""
    ctx.require("members.invite")
    if role not in ("admin", "staff", "reader"):
        raise ValidationFailed("Rollen skal være admin, staff eller reader", field_errors=[{"field": "role"}])
    if ROLE_RANK[role] > ROLE_RANK[ctx.role]:
        raise Forbidden("Du kan ikke invitere til en rolle over din egen", code="role_escalation")
    norm = normalize_email(email)
    existing_member = db.scalar(select(Membership).join(User, User.id == Membership.user_id)
                                .where(Membership.workspace_id == ctx.workspace.id, User.email_normalized == norm))
    if existing_member:
        raise Conflict("Personen er allerede medlem", code="already_member")
    pending = db.scalar(select(Invitation).where(Invitation.workspace_id == ctx.workspace.id,
                                                 Invitation.email_normalized == norm, Invitation.status == "pending"))
    if pending is not None:
        if pending.expires_at > _now():
            return pending, False
        pending.status = "expired"
        db.flush()
    s = get_settings()
    raw = new_token()
    inv = Invitation(workspace_id=ctx.workspace.id, email=email.strip(), email_normalized=norm, role=role,
                     token_hash=token_digest(raw), invited_by=ctx.user_id,
                     expires_at=_now() + timedelta(hours=s.invitation_ttl_hours))
    db.add(inv)
    db.flush()
    link = f"{s.frontend_base_url}/invite/{raw}"
    enqueue(db, event_type="email.invitation", dedupe_key=f"invitation:{inv.id}", workspace_id=ctx.workspace.id,
            payload={"invitation_id": str(inv.id), "to_email": inv.email, "workspace_name": ctx.workspace.name,
                     "role": role, "link": link, "invited_by": ctx.principal.user.display_name})
    record_audit(db, workspace_id=ctx.workspace.id, actor_user_id=ctx.user_id, action="invitation.created",
                 object_type="invitation", object_id=inv.id, after={"email": norm, "role": role},
                 request_id=request_id)
    return inv, True


def revoke_invitation(db: OrmSession, ctx: WorkspaceContext, invitation_id: uuid.UUID,
                      request_id: str | None = None) -> Invitation:
    ctx.require("members.invite")
    inv = db.scalar(select(Invitation).where(Invitation.id == invitation_id,
                                             Invitation.workspace_id == ctx.workspace.id).with_for_update())
    if inv is None:
        raise NotFound("Invitationen findes ikke")
    if inv.status != "pending":
        raise Conflict(f"Invitationen er allerede {inv.status}", code="invitation_not_pending")
    inv.status = "revoked"
    inv.revoked_at = _now()
    record_audit(db, workspace_id=ctx.workspace.id, actor_user_id=ctx.user_id, action="invitation.revoked",
                 object_type="invitation", object_id=inv.id, before={"status": "pending"},
                 after={"status": "revoked"}, request_id=request_id)
    return inv


def resend_invitation(db: OrmSession, ctx: WorkspaceContext, invitation_id: uuid.UUID) -> Invitation:
    """Re-queues the mail for a pending, unexpired invitation. No new token."""
    ctx.require("members.invite")
    inv = db.scalar(select(Invitation).where(Invitation.id == invitation_id,
                                             Invitation.workspace_id == ctx.workspace.id))
    if inv is None:
        raise NotFound("Invitationen findes ikke")
    if inv.status != "pending" or inv.expires_at <= _now():
        raise Conflict("Kun en aktiv invitation kan gensendes", code="invitation_not_pending")
    # The raw token is not stored, so a resend must issue a fresh token.
    raw = new_token()
    inv.token_hash = token_digest(raw)
    link = f"{get_settings().frontend_base_url}/invite/{raw}"
    enqueue(db, event_type="email.invitation", dedupe_key=f"invitation:{inv.id}:resend:{token_digest(raw)[:12]}",
            workspace_id=ctx.workspace.id,
            payload={"invitation_id": str(inv.id), "to_email": inv.email, "workspace_name": ctx.workspace.name,
                     "role": inv.role, "link": link, "invited_by": ctx.principal.user.display_name})
    return inv


def preview_invitation(db: OrmSession, raw_token: str) -> Invitation:
    inv = db.scalar(select(Invitation).where(Invitation.token_hash == token_digest(raw_token)))
    if inv is None:
        raise NotFound("Invitationen findes ikke")
    return inv


def accept_invitation(db: OrmSession, *, user: User, raw_token: str,
                      request_id: str | None = None) -> Membership:
    inv = db.scalar(select(Invitation).where(Invitation.token_hash == token_digest(raw_token)).with_for_update())
    if inv is None:
        raise NotFound("Invitationen findes ikke")
    if inv.status == "revoked":
        raise Conflict("Invitationen er tilbagekaldt", code="invitation_revoked")
    if inv.status == "accepted":
        raise Conflict("Invitationen er allerede brugt", code="invitation_used")
    if inv.status == "expired" or inv.expires_at <= _now():
        if inv.status == "pending":
            inv.status = "expired"
        raise Conflict("Invitationen er udløbet", code="invitation_expired")
    if user.email_normalized != inv.email_normalized:
        raise Forbidden("Invitationen er sendt til en anden e-mailadresse", code="invitation_email_mismatch")
    ws = db.get(Workspace, inv.workspace_id)
    if ws is None or ws.status == "closed":
        raise Conflict("Arbejdsrummet er lukket", code="workspace_closed")
    membership = db.scalar(select(Membership).where(Membership.workspace_id == inv.workspace_id,
                                                    Membership.user_id == user.id))
    if membership is None:
        membership = Membership(workspace_id=inv.workspace_id, user_id=user.id, role=inv.role)
        db.add(membership)
        db.flush()
    inv.status = "accepted"
    inv.accepted_at = _now()
    inv.accepted_by = user.id
    record_audit(db, workspace_id=inv.workspace_id, actor_user_id=user.id, action="invitation.accepted",
                 object_type="invitation", object_id=inv.id, after={"membership_id": str(membership.id),
                                                                     "role": membership.role},
                 request_id=request_id)
    return membership

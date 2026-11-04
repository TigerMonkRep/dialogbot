"""Who is calling and which personal workspace is theirs.

Strict isolation: a private endpoint never takes a workspace id. It resolves the caller's OWN personal workspace from
`private_profiles.user_id`; tasks are then reached only through `private_task_members` (sharing.py). Business
endpoints refuse personal workspaces in app.core.auth.get_workspace_context.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from app.config import get_settings
from app.core.auth import Principal, get_current_principal
from app.core.errors import Forbidden, NotFound
from app.db import get_db
from app.models import Membership, PrivateProfile, User, Workspace
from app.modules.privat import ledger, rules


@dataclass
class PrivateCtx:
    principal: Principal
    workspace: Workspace
    profile: PrivateProfile

    @property
    def user(self) -> User:
        return self.principal.user

    @property
    def user_id(self) -> uuid.UUID:
        return self.principal.user.id

    @property
    def ws_id(self) -> uuid.UUID:
        return self.workspace.id


def check_allowed(user: User) -> None:
    s = get_settings()
    if not s.privat_enabled:
        raise Forbidden("Dialogbot Privat er ikke åbnet endnu", code="privat_not_enabled")
    allowed = {e.strip().lower() for e in s.privat_allowed_emails.split(",") if e.strip()}
    if allowed and user.email_normalized not in allowed:
        raise Forbidden("Dialogbot Privat er i lukket pilot. Din e-mail er ikke på listen endnu.",
                        code="privat_not_enabled")


def find_profile(db: OrmSession, user_id: uuid.UUID) -> PrivateProfile | None:
    return db.scalar(select(PrivateProfile).where(PrivateProfile.user_id == user_id))


def ensure_account(db: OrmSession, user: User, *, signup_source: str | None = None) -> tuple[PrivateProfile, bool]:
    """The user's personal workspace, created once (owner membership, NO business seed rows, 3 welcome credits,
    the 14-day trial, default add-ons). Idempotent: the user row is locked, and private_profiles.user_id is unique.

    Proof of identity: a verified e-mail OR a verified mobile number (users.phone_verified_at, set by the quiz-funnel
    after the SMS code) – see docs/privat-api.md «Konto via telefon»."""
    check_allowed(user)
    if user.email_verified_at is None and user.phone_verified_at is None:
        raise Forbidden("Bekræft din e-mail først", code="email_not_verified")
    p = find_profile(db, user.id)
    if p is not None:
        return p, False
    db.scalar(select(User).where(User.id == user.id).with_for_update())
    p = find_profile(db, user.id)
    if p is not None:
        return p, False
    ws = Workspace(name=f"Privat – {user.display_name}"[:200], slug=f"privat-{uuid.uuid4().hex[:16]}", kind="personal",
                   created_by=user.id)
    db.add(ws)
    db.flush()
    db.add(Membership(workspace_id=ws.id, user_id=user.id, role="owner"))
    p = PrivateProfile(workspace_id=ws.id, user_id=user.id)
    db.add(p)
    db.flush()
    ledger.add(db, ws.id, kind="grant", amount=rules.WELCOME_CREDITS, source_ref=f"welcome:{ws.id}",
               text="Velkomstcredits (én gang)")
    from app.modules.privat import addons, subscriptions

    subscriptions.start_free(db, ws.id)  # no rights yet: the 14-day trial starts at Stripe Checkout, with a card
    addons.enable_defaults(db, ws.id)
    if signup_source and not user.signup_source:
        user.signup_source = signup_source[:80]
    return p, True


def _ctx(db: OrmSession, principal: Principal, p: PrivateProfile) -> PrivateCtx:
    ws = db.get(Workspace, p.workspace_id)
    if ws is None or ws.kind != "personal" or ws.status == "closed":
        raise NotFound("Din private konto findes ikke")
    return PrivateCtx(principal=principal, workspace=ws, profile=p)


def private_ctx(request: Request, principal: Principal = Depends(get_current_principal),
                db: OrmSession = Depends(get_db)) -> PrivateCtx:
    """The caller's own private context. Reads need an existing account; writes create it on first use."""
    if principal.session.impersonator_user_id is not None:
        # "Se som kunde" is for business support; a consumer's private life is not part of it.
        raise Forbidden("Private data kan ikke ses i «se som kunde»", code="view_as_not_allowed")
    check_allowed(principal.user)
    p = find_profile(db, principal.user.id)
    if p is None:
        if request.method in ("GET", "HEAD"):
            raise NotFound("Opret din private konto først (POST /privat/account)", code="privat_account_missing")
        p, _ = ensure_account(db, principal.user)
        db.commit()
    return _ctx(db, principal, p)

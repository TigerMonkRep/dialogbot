"""Referral reward: a NEW user who joins through an invite and becomes active (verified e-mail + first OWN task) gives
+3 credits to the invitee and +3 to the inviter (at most 10 inviter rewards per Copenhagen month).

- "New" = the account was created after the invite (an existing user never earns anything), and not a self-invite.
- One referral row per invitee for life (unique invitee_user_id) and ledger source_refs referral:<invitee>:invitee /
  referral:<invitee>:inviter, so neither a second invite nor a replay can reward twice.
"""
from __future__ import annotations

import uuid
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session as OrmSession

from app.models import (
    CreditLedger,
    PrivateInvite,
    PrivateProfile,
    PrivateReferral,
    PrivateTask,
    PrivateTaskMember,
    User,
)
from app.modules.privat import ledger, rules

REWARD = 3
MONTHLY_CAP = 10


def on_accept(db: OrmSession, inv: PrivateInvite, invitee: User) -> PrivateReferral | None:
    if invitee.id == inv.inviter_user_id or invitee.created_at < inv.created_at:
        return None  # self-invite or an existing user: no referral
    if db.scalar(select(PrivateReferral.id).where(PrivateReferral.invitee_user_id == invitee.id)) is not None:
        return None
    r = PrivateReferral(inviter_user_id=inv.inviter_user_id, invitee_user_id=invitee.id, invite_id=inv.id,
                        addon_key=inv.addon_key, accepted_at=rules.now())
    try:
        with db.begin_nested():
            db.add(r)
    except Exception:  # noqa: BLE001 - unique invitee: someone else recorded it first
        return None
    return r


def _month_start():
    return rules.local().replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def inviter_rewards_this_month(db: OrmSession, inviter_ws: uuid.UUID) -> int:
    return db.scalar(select(func.count()).select_from(CreditLedger).where(
        CreditLedger.workspace_id == inviter_ws, CreditLedger.kind == "referral",
        CreditLedger.source_ref.like("referral:%:inviter"), CreditLedger.created_at >= _month_start())) or 0


def has_own_task(db: OrmSession, user_id: uuid.UUID) -> bool:
    return db.scalar(select(PrivateTask.id).join(PrivateTaskMember, PrivateTaskMember.task_id == PrivateTask.id)
                     .where(PrivateTaskMember.user_id == user_id, PrivateTaskMember.role == "owner").limit(1)) is not None


def try_activate(db: OrmSession, user_id: uuid.UUID) -> bool:
    """Reward once when the invitee is active. Safe to call after every own task; True when it rewarded now."""
    r = db.scalar(select(PrivateReferral).where(PrivateReferral.invitee_user_id == user_id,
                                                PrivateReferral.rewarded_at.is_(None)).with_for_update())
    if r is None:
        return False
    invitee = db.get(User, user_id)
    if invitee is None or invitee.email_verified_at is None or not has_own_task(db, user_id):
        return False
    me = db.scalar(select(PrivateProfile).where(PrivateProfile.user_id == user_id))
    inviter = db.scalar(select(PrivateProfile).where(PrivateProfile.user_id == r.inviter_user_id))
    if me is None:
        return False
    now = rules.now()
    r.activated_at = r.activated_at or now
    ledger.add(db, me.workspace_id, kind="referral", amount=REWARD, source_ref=f"referral:{user_id}:invitee",
               text="Velkomstbonus: du kom med via en invitation")
    if inviter is not None and inviter_rewards_this_month(db, inviter.workspace_id) < MONTHLY_CAP:
        r.inviter_rewarded = ledger.add(
            db, inviter.workspace_id, kind="referral", amount=REWARD, source_ref=f"referral:{user_id}:inviter",
            text=f"{rules.first_name(invitee.display_name)} kom med via din invitation")
    r.rewarded_at = now
    return True


def summary(db: OrmSession, ctx) -> dict:
    invited = db.scalar(select(func.count()).select_from(PrivateInvite)
                        .where(PrivateInvite.inviter_user_id == ctx.user_id)) or 0
    joined = db.scalar(select(func.count()).select_from(PrivateReferral)
                       .where(PrivateReferral.inviter_user_id == ctx.user_id)) or 0
    activated = db.scalar(select(func.count()).select_from(PrivateReferral).where(
        PrivateReferral.inviter_user_id == ctx.user_id, PrivateReferral.activated_at.is_not(None))) or 0
    earned = db.scalar(select(func.coalesce(func.sum(CreditLedger.amount), 0)).where(
        CreditLedger.workspace_id == ctx.ws_id, CreditLedger.kind == "referral")) or 0
    return {"invited": invited, "joined": joined, "activated": activated, "credits_earned": int(earned),
            "monthly_left": max(0, MONTHLY_CAP - inviter_rewards_this_month(db, ctx.ws_id))}


def growth(db: OrmSession, days: int | None = None) -> dict:
    """Operator numbers. k_factor = new users from invites / private accounts (in the period)."""
    since = rules.now() - timedelta(days=days) if days else None

    def block(addon_key: str | None, all_keys: bool) -> dict:
        iq = select(func.count(), func.coalesce(func.sum(PrivateInvite.opened_count), 0),
                    func.coalesce(func.sum(PrivateInvite.accepted_count), 0))
        rq = select(func.count()).select_from(PrivateReferral)
        aq = select(func.count()).select_from(PrivateReferral).where(PrivateReferral.activated_at.is_not(None))
        if not all_keys:
            iq = iq.where(PrivateInvite.addon_key.is_(None) if addon_key is None else PrivateInvite.addon_key == addon_key)
            cond = PrivateReferral.addon_key.is_(None) if addon_key is None else PrivateReferral.addon_key == addon_key
            rq, aq = rq.where(cond), aq.where(cond)
        if since is not None:
            iq = iq.where(PrivateInvite.created_at >= since)
            rq, aq = rq.where(PrivateReferral.accepted_at >= since), aq.where(PrivateReferral.accepted_at >= since)
        created, opened, accepted = db.execute(iq).one()
        return {"invites_created": int(created), "opened": int(opened), "accepted": int(accepted),
                "new_users_from_invites": int(db.scalar(rq) or 0), "activated": int(db.scalar(aq) or 0)}

    total = block(None, True)
    pq = select(func.count()).select_from(PrivateProfile)
    if since is not None:
        pq = pq.where(PrivateProfile.created_at >= since)
    accounts = int(db.scalar(pq) or 0)
    keys = sorted({k for k in db.scalars(select(PrivateInvite.addon_key).distinct())}, key=lambda k: k or "")
    by_addon = {(k or "dialogbot"): block(k, False) for k in keys}
    return total | {"private_accounts": accounts,
                    "k_factor": round(total["new_users_from_invites"] / accounts, 3) if accounts else 0.0,
                    "by_addon": by_addon, "days": days}

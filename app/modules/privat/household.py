"""Familie: the household («Op til 5 personer», docs/pricing.md).

The owner of a Familie plan invites up to 4 people (5 with the owner) through the ordinary invitation mechanism
(invites.py: a link the owner texts from their OWN phone, resource_type "household"). The invitee accepts with their
own Dialogbot Privat account (created on accept if needed) and from then on has the plan's rights:
- the apps in the Butik that come with Familie (Plus apps),
- the plan's calls. The quota is the HOUSEHOLD's: Familie is «25 opkald om måneden» for the plan, next to Plus' 10 for
  one person, so the 25 are shared by everyone in it (counted over all the household's workspaces, calendar month).
Nothing else is shared: every member keeps their own personal workspace, tasks, lists, calls and apps, and nobody in the
household can see anybody else's (a household ≠ sharing everything – lists are shared the usual way, one by one).

Rights are derived LIVE from the owner's subscription (subscriptions.entitlements), so the owner removing a member, a
member leaving, a downgrade from Familie and a cancellation all take effect on the very next request. On a downgrade or
cancellation the rows stay (the household is paused and comes back with Familie); the members' own data is kept, and
their plan apps follow the general rule for plan apps without a plan.

A member who pays for a plan of their own uses that one (and their calls count on it, not on the household's).
"""
from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session as OrmSession

from app.core.errors import Conflict, NotFound
from app.models import PrivateHouseholdMember, PrivateProfile, PrivateSubscription, User
from app.modules.privat import rules

RESOURCE = "household"
PLAN = "familie"
MAX_PEOPLE = 5  # prices.PRIVAT_PLANS familie.people – the owner included


def _people_limit() -> int:
    from app.modules.privat import subscriptions

    return int(subscriptions.PLANS[PLAN]["people"] or MAX_PEOPLE)


def membership(db: OrmSession, ws_id: uuid.UUID) -> PrivateHouseholdMember | None:
    """The household this workspace is a MEMBER of (not the one it owns)."""
    return db.scalar(select(PrivateHouseholdMember).where(PrivateHouseholdMember.member_workspace_id == ws_id))


def members(db: OrmSession, owner_ws_id: uuid.UUID) -> list[PrivateHouseholdMember]:
    return list(db.scalars(select(PrivateHouseholdMember).where(PrivateHouseholdMember.owner_workspace_id == owner_ws_id)
                           .order_by(PrivateHouseholdMember.joined_at, PrivateHouseholdMember.id)))


def _own_state(db: OrmSession, ws_id: uuid.UUID) -> tuple[str, str, bool]:
    from app.modules.privat import subscriptions

    return subscriptions._state(db.get(PrivateSubscription, ws_id), rules.now())


def owner_has_familie(db: OrmSession, owner_ws_id: uuid.UUID) -> bool:
    _status, plan, entitled = _own_state(db, owner_ws_id)
    return entitled and plan == PLAN


def lent_row(db: OrmSession, ws_id: uuid.UUID) -> PrivateSubscription | None:
    """The owner's subscription row whose Familie rights this workspace borrows (None = no household rights now)."""
    m = membership(db, ws_id)
    if m is None or not owner_has_familie(db, m.owner_workspace_id):
        return None
    return db.get(PrivateSubscription, m.owner_workspace_id)


def quota_workspaces(db: OrmSession, ws_id: uuid.UUID) -> list[uuid.UUID]:
    """The workspaces whose plan calls count on the same Familie quota as `ws_id`: the owner and every member that
    draws on the household (not one paying for a plan of their own). Just [ws_id] outside a household."""
    m = membership(db, ws_id)
    owner = m.owner_workspace_id if m is not None else ws_id
    if m is not None and _own_state(db, ws_id)[2]:
        return [ws_id]  # pays for itself: its own quota
    rows = members(db, owner)
    if not rows:
        return [ws_id]
    return [owner] + [r.member_workspace_id for r in rows if not _own_state(db, r.member_workspace_id)[2]]


# --------------------------------------------------------------------------- reading

def _first_name(db: OrmSession, ws_id: uuid.UUID) -> str:
    p = db.get(PrivateProfile, ws_id)
    u = db.get(User, p.user_id) if p else None
    return rules.first_name(u.display_name if u else None) or "?"


def state(db: OrmSession, ctx) -> dict:
    """GET /privat/household. role: owner (has members or a Familie plan) | member | null. Only first names – never
    anything from anybody's account."""
    limit = _people_limit()
    m = membership(db, ctx.ws_id)
    if m is not None:
        owner = m.owner_workspace_id
        rows = members(db, owner)
        return {"role": "member", "active": owner_has_familie(db, owner), "can_invite": False, "limit": limit,
                "count": 1 + len(rows), "owner_first_name": _first_name(db, owner),
                "members": [{"id": str(r.id), "name": _first_name(db, r.member_workspace_id),
                             "is_me": r.member_workspace_id == ctx.ws_id} for r in rows]}
    rows = members(db, ctx.ws_id)
    familie = owner_has_familie(db, ctx.ws_id)
    if not rows and not familie:
        return {"role": None, "active": False, "can_invite": False, "limit": limit, "count": 1,
                "owner_first_name": None, "members": []}
    return {"role": "owner", "active": familie, "can_invite": familie and 1 + len(rows) < limit, "limit": limit,
            "count": 1 + len(rows), "owner_first_name": rules.first_name(ctx.user.display_name),
            "members": [{"id": str(r.id), "name": _first_name(db, r.member_workspace_id), "is_me": False} for r in rows]}


# --------------------------------------------------------------------------- the owner

def invite(db: OrmSession, ctx) -> dict:
    """A household invitation the owner texts from their own phone (nothing is sent by Dialogbot)."""
    from app.modules.privat import invites

    if membership(db, ctx.ws_id) is not None:
        raise Conflict("Du er med i en andens husstand – kun den, der har Familie, kan invitere",
                       code="household_member")
    if not owner_has_familie(db, ctx.ws_id):
        raise Conflict("Husstanden er med i Familie – skift til Familie for at invitere", code="needs_plan",
                       extra={"plans": [PLAN]})
    if 1 + len(members(db, ctx.ws_id)) >= _people_limit():
        raise Conflict(f"Husstanden er fuld ({_people_limit()} personer)", code="household_full")
    inv, raw = invites.create(db, ctx, addon_key=None)
    inv.resource_type, inv.resource_id = RESOURCE, ctx.ws_id
    db.flush()
    return invites.invite_out(db, inv, raw, ctx.user.display_name)


def remove(db: OrmSession, ctx, member_id: uuid.UUID) -> None:
    """The owner takes a member out: the rights stop at once; the member's own data is untouched."""
    row = db.get(PrivateHouseholdMember, member_id)
    if row is None or row.owner_workspace_id != ctx.ws_id:
        raise NotFound("Personen er ikke i din husstand")
    db.delete(row)
    db.flush()


def leave(db: OrmSession, ctx) -> None:
    row = membership(db, ctx.ws_id)
    if row is None:
        raise NotFound("Du er ikke med i en husstand")
    db.delete(row)
    db.flush()


# --------------------------------------------------------------------------- the invitation

def _owner_ws(db: OrmSession, inv) -> uuid.UUID:
    """The household's workspace – and it must still be the inviter's own."""
    p = db.scalar(select(PrivateProfile).where(PrivateProfile.user_id == inv.inviter_user_id))
    if p is None or inv.resource_id is None or p.workspace_id != inv.resource_id:
        raise NotFound("Invitationen er ugyldig eller udløbet", code="invite_invalid")
    return p.workspace_id


def preview(db: OrmSession, inv) -> dict:
    owner = _owner_ws(db, inv)
    n = 1 + int(db.scalar(select(func.count()).select_from(PrivateHouseholdMember)
                          .where(PrivateHouseholdMember.owner_workspace_id == owner)) or 0)
    return {"title": "Familie", "household": {"count": n, "limit": _people_limit(),
                                              "active": owner_has_familie(db, owner)}}


def accept(db: OrmSession, inv, ctx) -> tuple[dict, bool]:
    """Join the household. Serialised per household (the owner's subscription row is locked), so two people accepting
    at the same time can never make it six. Accepting again is a no-op (joined False: no second «sagde ja»)."""
    owner = _owner_ws(db, inv)
    db.scalar(select(PrivateSubscription).where(PrivateSubscription.workspace_id == owner).with_for_update())
    if owner == ctx.ws_id:
        raise Conflict("Det er din egen husstand", code="own_household")
    mine = membership(db, ctx.ws_id)
    if mine is not None:
        if mine.owner_workspace_id == owner:
            return {"household": state(db, ctx)}, False  # double accept
        raise Conflict("Du er allerede med i en anden husstand. Forlad den først under Konto.",
                       code="already_in_household")
    if members(db, ctx.ws_id):
        raise Conflict("Du har selv en husstand med andre i. Fjern dem først under Konto.", code="has_household")
    if not owner_has_familie(db, owner):
        raise Conflict("Husstanden er sat på pause – den kræver Familie", code="household_inactive")
    if 1 + len(members(db, owner)) >= _people_limit():
        raise Conflict(f"Husstanden er fuld ({_people_limit()} personer)", code="household_full")
    db.add(PrivateHouseholdMember(owner_workspace_id=owner, member_workspace_id=ctx.ws_id, invite_id=inv.id,
                                  joined_at=rules.now()))
    db.flush()
    from app.modules.privat import addons

    addons.enable_defaults(db, ctx.ws_id)  # the plan's default apps («Ring for mig» …) come on with the rights
    return {"household": state(db, ctx)}, True

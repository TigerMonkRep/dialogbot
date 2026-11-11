"""Task access and shared lists.

Every task is reached ONLY through `private_task_members` (the owner has a row too) – never through a workspace id.
Share modes:
- group: members with role editor add and tick off; every item says who added / ticked it.
- wishlist: only the owner adds wishes; other members reserve ("Jeg køber den"). The owner NEVER learns whether or by
  whom anything is reserved – not in the task, not in events, not in the chat, not even through `updated_at`. Other
  members see "reserved" but not by whom (only `reserved_by_me`).
This module is also the `resource_hooks` of the shareable list add-ons (authorize / preview / accept), used by the
generic invitation mechanism in invites.py.
"""
from __future__ import annotations

import uuid

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session as OrmSession

from app.core.errors import Conflict, Forbidden, NotFound, ValidationFailed
from app.models import PrivateInvite, PrivateProfile, PrivateTask, PrivateTaskItem, PrivateTaskMember, User
from app.modules.privat import addons, rules

ROLE_RANK = {"viewer": 1, "editor": 2, "owner": 3}


def member(db: OrmSession, task_id: uuid.UUID, user_id: uuid.UUID) -> PrivateTaskMember | None:
    return db.scalar(select(PrivateTaskMember).where(PrivateTaskMember.task_id == task_id,
                                                     PrivateTaskMember.user_id == user_id))


def owner_member(db: OrmSession, task_id: uuid.UUID) -> PrivateTaskMember | None:
    return db.scalar(select(PrivateTaskMember).where(PrivateTaskMember.task_id == task_id,
                                                     PrivateTaskMember.role == "owner"))


def add_owner(db: OrmSession, task: PrivateTask, user_id: uuid.UUID) -> None:
    db.add(PrivateTaskMember(task_id=task.id, user_id=user_id, role="owner"))


def sharing_paused(db: OrmSession, task: PrivateTask) -> bool:
    """The owner switched the add-on behind this share mode off: members cannot reach the list meanwhile."""
    key = addons.SHARE_MODE_ADDON.get(task.share_mode or "")
    return bool(key) and not addons.is_enabled(db, task.workspace_id, key)


def access(db: OrmSession, task_id: uuid.UUID, user_id: uuid.UUID, *, min_role: str = "viewer",
           lock: bool = False) -> tuple[PrivateTask, PrivateTaskMember]:
    """The task and the caller's membership. 404 for anyone who is not a member (existence is not revealed)."""
    m = member(db, task_id, user_id)
    if m is None:
        raise NotFound("Opgaven findes ikke")
    q = select(PrivateTask).where(PrivateTask.id == task_id)
    task = db.scalar(q.with_for_update() if lock else q)
    if task is None:
        raise NotFound("Opgaven findes ikke")
    if m.role != "owner" and sharing_paused(db, task):
        raise Forbidden("Ejeren har sat delingen af listen på pause", code="sharing_paused")
    if ROLE_RANK[m.role] < ROLE_RANK[min_role]:
        raise Forbidden("Du kan kun se denne liste", code="read_only")
    return task, m


def members_out(db: OrmSession, task: PrivateTask, viewer_id: uuid.UUID) -> list[dict]:
    rows = db.execute(select(PrivateTaskMember, User.display_name).join(User, User.id == PrivateTaskMember.user_id)
                      .where(PrivateTaskMember.task_id == task.id).order_by(PrivateTaskMember.created_at)).all()
    return [{"id": str(m.id), "name": name, "role": m.role, "is_me": m.user_id == viewer_id} for m, name in rows]


def member_count(db: OrmSession, task_id: uuid.UUID) -> int:
    return db.scalar(select(func.count()).select_from(PrivateTaskMember)
                     .where(PrivateTaskMember.task_id == task_id)) or 0


def remove_member(db: OrmSession, task: PrivateTask, me: PrivateTaskMember, member_id: uuid.UUID) -> None:
    target = db.scalar(select(PrivateTaskMember).where(PrivateTaskMember.id == member_id,
                                                       PrivateTaskMember.task_id == task.id))
    if target is None:
        raise NotFound("Medlemmet findes ikke")
    if target.role == "owner":
        raise Conflict("Ejeren kan ikke forlade sin egen liste", code="owner_cannot_leave")
    if me.role != "owner" and target.id != me.id:
        raise Forbidden("Kun ejeren kan fjerne andre", code="owner_only")
    # their reservations and open pledges go with them (the owner never sees that either)
    from app.modules.privat import group_gifts

    group_gifts.on_member_removed(db, task, target.user_id)
    db.execute(update(PrivateTaskItem).where(PrivateTaskItem.task_id == task.id,
                                             PrivateTaskItem.reserved_by_user_id == target.user_id)
               .values(reserved_by_user_id=None))
    db.delete(target)
    db.flush()


def reserve(db: OrmSession, task: PrivateTask, m: PrivateTaskMember, item_id: uuid.UUID, *, on: bool) -> None:
    if task.share_mode != "wishlist":
        raise Conflict("Kun ønskelister har reservationer", code="not_a_wishlist")
    if m.role == "owner":
        raise Forbidden("Ejeren af en ønskeliste kan ikke reservere", code="owner_cannot_reserve")
    item = db.scalar(select(PrivateTaskItem).where(PrivateTaskItem.id == item_id, PrivateTaskItem.task_id == task.id)
                     .with_for_update())
    if item is None or item.archived_at is not None:
        raise NotFound("Ønsket findes ikke")
    if on:
        from app.modules.privat import group_gifts

        if item.reserved_by_user_id not in (None, m.user_id):
            raise Conflict("En anden har allerede reserveret dette ønske", code="already_reserved")
        if item.reserved_by_user_id is None and group_gifts.blocks_reservation(db, item):
            raise Conflict("Flere er gået sammen om dette ønske som fællesgave – vær med i gaven i stedet",
                           code="group_gift_active")
        item.reserved_by_user_id = m.user_id
    else:
        if item.reserved_by_user_id != m.user_id:
            raise Conflict("Du har ikke reserveret dette ønske", code="not_reserved_by_you")
        item.reserved_by_user_id = None
    # deliberately NOT touching task.updated_at or writing an event: the owner must not notice anything


def pause_sharing(db: OrmSession, ws_id: uuid.UUID) -> None:
    """on_disable of the list add-ons: open invitation links to the owner's lists stop working (data is kept;
    members are paused through sharing_paused while the add-on is off)."""
    owned = select(PrivateTask.id).where(PrivateTask.workspace_id == ws_id, PrivateTask.share_mode.is_not(None))
    db.execute(update(PrivateInvite).where(PrivateInvite.resource_type == "list", PrivateInvite.resource_id.in_(owned),
                                           PrivateInvite.revoked_at.is_(None)).values(revoked_at=rules.now()))


# --------------------------------------------------------------------------- invitation hooks (resource_type "list")

def authorize(db: OrmSession, ctx, resource_id: uuid.UUID | None, mode: str | None, role: str) -> dict:
    """Only the owner of a list may share it; the share mode is fixed once someone has joined."""
    if resource_id is None:
        raise ValidationFailed("Vælg en liste", field_errors=[{"field": "resource_id"}])
    task, m = access(db, resource_id, ctx.user_id, lock=True)
    if m.role != "owner":
        raise Forbidden("Kun ejeren kan dele listen", code="owner_only")
    if task.kind != "list":
        raise Conflict("Kun lister kan deles", code="not_a_list")
    if mode not in ("group", "wishlist"):
        raise ValidationFailed("Vælg group eller wishlist", field_errors=[{"field": "mode"}])
    if task.share_mode and task.share_mode != mode and member_count(db, task.id) > 1:
        raise Conflict("Listen er allerede delt på en anden måde", code="share_mode_locked")
    task.share_mode = mode
    if mode == "wishlist" and task.list_type is None:
        task.list_type = "wishlist"
    task.updated_at = rules.now()
    # A wishlist guest can see and reserve («kan reservere») – never change the owner's wishes: viewer (F-UX-03).
    # Reserving needs no editor role (reserve() only refuses the owner).
    return {"mode": mode, "role": "viewer" if mode == "wishlist" else role}


def preview(db: OrmSession, inv: PrivateInvite) -> dict:
    """Title, list type and item COUNT only – never items, notes, links or reservations."""
    task = db.get(PrivateTask, inv.resource_id) if inv.resource_id else None
    if task is None or sharing_paused(db, task):
        raise NotFound("Invitationen er ugyldig eller udløbet", code="invite_invalid")
    live = (PrivateTaskItem.task_id == task.id, PrivateTaskItem.archived_at.is_(None))
    n = db.scalar(select(func.count()).select_from(PrivateTaskItem).where(*live)) or 0
    gg = db.scalar(select(func.count()).select_from(PrivateTaskItem).where(*live, PrivateTaskItem.group_gift_enabled)) or 0
    out = {"title": task.title, "list_type": task.list_type, "item_count": n, "share_mode": task.share_mode,
           "group_gift_count": gg}
    if task.list_type == "wishlist":
        from app.modules.privat import wish_design

        d = wish_design.resolved(task.design)
        # the look only – never the cover photo (a personal picture) on a page anyone with the link can open
        out["design"] = {k: d[k] for k in ("theme", "accent", "background", "text", "font", "decorations")}
    return out


def accept(db: OrmSession, inv: PrivateInvite, ctx) -> tuple[dict, bool]:
    """Join the list. Returns (Task for the new member, newly_joined)."""
    from app.modules.privat import service

    task = db.get(PrivateTask, inv.resource_id) if inv.resource_id else None
    if task is None or sharing_paused(db, task):
        raise NotFound("Invitationen er ugyldig eller udløbet", code="invite_invalid")
    m = member(db, task.id, ctx.user_id)
    joined = False
    if m is None:
        m = PrivateTaskMember(task_id=task.id, user_id=ctx.user_id, role=inv.role)
        db.add(m)
        db.flush()
        joined = True
        service.event(db, task, f"{rules.first_name(ctx.user.display_name)} er med på listen")
        from app.modules.privat import push

        push.notify_list_activity(db, task, actor_user_id=ctx.user_id,
                                  text=f"{rules.first_name(ctx.user.display_name)} er med på listen")
    return service.task_out(db, task, ctx.user_id), joined


def is_owner_profile(db: OrmSession, task: PrivateTask, user_id: uuid.UUID) -> bool:
    p = db.get(PrivateProfile, task.workspace_id)
    return p is not None and p.user_id == user_id

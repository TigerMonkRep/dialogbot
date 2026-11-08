"""«Deles om en gave»: several givers pledge an amount of their own choice towards one wish.

This coordinates PLEDGES – no money is moved, nothing is charged and nothing is «betalt» or «indsamlet».

Who sees what (enforced here, never in the browser):
- The wishlist's owner sets «Tillad fællesgave» and a proposed target on the wish – and NOTHING else: never the
  agreement, its status, pledges, totals, participants or the coordinator, and nothing about it changes the task's
  updated_at, events, chat or notifications. Every giver endpoint answers the owner 403 owner_cannot_give, whatever the
  state, so the answer reveals nothing.
- A giver is a member of the shared wishlist (logged in, joined through a personal invitation). Givers see the target,
  the total pledged, what is left, the number of participants, their own pledge and the coordinator's first name.
  Nobody sees what another person pledged. Each giver changes only their own pledge.

Amounts: integers in the currency's minor unit, computed on the server. One currency per gift. The agreement's target
is copied from the wish when the first pledge arrives and is frozen from then on (later edits of the wish's price or
target do not move it). A pledge above what is left is refused with remaining_minor – the web proposes that amount
and the giver must confirm it. Every write locks the wish row first, so two simultaneous pledges are serialised and can
never exceed the target; one pledge row per giver (unique), so a retry or a double click updates the same row.

States: open → (sum = target: «Fuldt tilsagn», derived) → bought (only the coordinator marks it; the sum never does).
cancelled when the owner removes the wish or switches the group gift off while it is open: the pledges stay, the
givers see «Annulleret» and get a notification. A separate reservation and an active group gift exclude each other.
The coordinator role is taken actively by a participant, and handed over only when the receiver accepts.
"""
from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session as OrmSession

from app.core.errors import ApiError, Conflict, Forbidden, NotFound, ValidationFailed
from app.models import PrivateGiftPledge, PrivateGroupGift, PrivateTask, PrivateTaskItem, PrivateTaskMember, User
from app.modules.privat import rules

MAX_MINOR = 10**10  # 100 mio. kr. – far beyond any gift, below every integer limit


def _now():
    return rules.now()


# --------------------------------------------------------------------------- reading

def live_gift(db: OrmSession, item_id: uuid.UUID, *, lock: bool = False) -> PrivateGroupGift | None:
    q = select(PrivateGroupGift).where(PrivateGroupGift.item_id == item_id, PrivateGroupGift.status != "cancelled")
    return db.scalar(q.with_for_update() if lock else q)


def _active(db: OrmSession, gift_id: uuid.UUID):
    return select(PrivateGiftPledge).where(PrivateGiftPledge.gift_id == gift_id, PrivateGiftPledge.status == "active")


def totals(db: OrmSession, gift_id: uuid.UUID) -> tuple[int, int]:
    """(sum of active pledges, number of active participants)."""
    row = db.execute(select(func.coalesce(func.sum(PrivateGiftPledge.amount_minor), 0), func.count())
                     .where(PrivateGiftPledge.gift_id == gift_id, PrivateGiftPledge.status == "active")).one()
    return int(row[0]), int(row[1])


def has_active_pledges(db: OrmSession, gift: PrivateGroupGift | None) -> bool:
    return gift is not None and totals(db, gift.id)[1] > 0


def _mine(db: OrmSession, gift_id: uuid.UUID, user_id: uuid.UUID, *, lock: bool = False) -> PrivateGiftPledge | None:
    q = select(PrivateGiftPledge).where(PrivateGiftPledge.gift_id == gift_id, PrivateGiftPledge.user_id == user_id)
    return db.scalar(q.with_for_update() if lock else q)


def _first(db: OrmSession, user_id: uuid.UUID | None) -> str | None:
    if not user_id:
        return None
    u = db.get(User, user_id)
    return rules.first_name(u.display_name) if u else None


def state(gift: PrivateGroupGift, pledged: int) -> str:
    if gift.status in ("bought", "cancelled"):
        return gift.status
    return "full" if pledged >= gift.target_minor else "open"


def out_for_giver(db: OrmSession, item: PrivateTaskItem, viewer_id: uuid.UUID) -> dict | None:
    """The group gift as a giver sees it, or None. Never call this for the owner (service.items_out does not)."""
    gift = live_gift(db, item.id)
    if gift is None:
        # A cancelled agreement stays visible to the people who had pledged on it.
        gift = db.scalar(select(PrivateGroupGift).join(PrivateGiftPledge, PrivateGiftPledge.gift_id == PrivateGroupGift.id)
                         .where(PrivateGroupGift.item_id == item.id, PrivateGroupGift.status == "cancelled",
                                PrivateGiftPledge.user_id == viewer_id, PrivateGiftPledge.status == "active")
                         .order_by(PrivateGroupGift.cancelled_at.desc()).limit(1))
        if gift is None and item.group_gift_enabled and item.group_gift_target_minor and item.archived_at is None:
            # Not started yet: the owner's proposed target is what a first pledge would agree on.
            target = item.group_gift_target_minor
            return {"status": "open", "target_minor": target, "currency": item.currency or "DKK", "pledged_minor": 0,
                    "remaining_minor": target, "participants": 0, "my_pledge_minor": None, "coordinator": None,
                    "pending_coordinator_is_me": False, "is_coordinator": False, "cancel_reason": None,
                    "can_join": item.reserved_by_user_id is None, "reserved_by_me": item.reserved_by_user_id == viewer_id,
                    "participant_names": None}
        if gift is None:
            return None
    pledged, n = totals(db, gift.id)
    mine = _mine(db, gift.id, viewer_id)
    my_amount = mine.amount_minor if mine is not None and mine.status == "active" else None
    is_coord = gift.coordinator_user_id == viewer_id
    names = None
    if is_coord and gift.status != "cancelled":  # the coordinator may hand over to another participant
        rows = db.execute(select(PrivateGiftPledge.user_id, User.display_name).join(User, User.id == PrivateGiftPledge.user_id)
                          .where(PrivateGiftPledge.gift_id == gift.id, PrivateGiftPledge.status == "active",
                                 PrivateGiftPledge.user_id != viewer_id)).all()
        names = [{"user_ref": str(uid), "name": rules.first_name(nm)} for uid, nm in rows]
    return {"status": state(gift, pledged), "target_minor": gift.target_minor, "currency": gift.currency,
            "pledged_minor": pledged, "remaining_minor": max(0, gift.target_minor - pledged), "participants": n,
            "my_pledge_minor": my_amount,
            "coordinator": ({"name": _first(db, gift.coordinator_user_id), "is_me": is_coord}
                            if gift.coordinator_user_id else None),
            "pending_coordinator_is_me": gift.pending_coordinator_user_id == viewer_id,
            "pending_coordinator_name": _first(db, gift.pending_coordinator_user_id) if is_coord else None,
            "is_coordinator": is_coord, "cancel_reason": gift.cancel_reason,
            "can_join": gift.status == "open" and (my_amount is not None or pledged < gift.target_minor)
                        and item.reserved_by_user_id in (None,),
            "reserved_by_me": item.reserved_by_user_id == viewer_id, "participant_names": names}


def blocks_reservation(db: OrmSession, item: PrivateTaskItem) -> bool:
    gift = live_gift(db, item.id)
    return gift is not None and (gift.status == "bought" or has_active_pledges(db, gift))


# --------------------------------------------------------------------------- the owner's side (settings only)

def on_owner_settings(db: OrmSession, item: PrivateTaskItem, *, enabled: bool, target_minor: int | None,
                      currency: str | None) -> None:
    """Validates and stores «Tillad fællesgave». Switching it off cancels an OPEN agreement (pledges are kept and the
    givers are told); a bought one is left alone. The owner's answer is the same in every case."""
    if enabled:
        if not currency or len(currency) != 3:
            raise ValidationFailed("Vælg en valuta for fællesgaven", field_errors=[{"field": "currency"}])
        if target_minor is None or target_minor <= 0 or target_minor > MAX_MINOR:
            raise ValidationFailed("Skriv et målbeløb over 0", field_errors=[{"field": "group_gift_target_minor",
                                                                             "message": "Skriv et målbeløb over 0"}])
    item.group_gift_enabled = enabled
    item.group_gift_target_minor = target_minor if enabled else item.group_gift_target_minor
    if not enabled:
        cancel(db, item, reason="disabled")


def cancel(db: OrmSession, item: PrivateTaskItem, *, reason: str) -> bool:
    """Cancel the open agreement on this wish (if any) and tell its participants. True if there were pledges."""
    gift = live_gift(db, item.id, lock=True)
    if gift is None or gift.status != "open":
        return gift is not None and gift.status == "bought"
    pledgers = list(db.scalars(_active(db, gift.id).with_only_columns(PrivateGiftPledge.user_id)))
    gift.status, gift.cancel_reason, gift.cancelled_at, gift.updated_at = "cancelled", reason, _now(), _now()
    gift.pending_coordinator_user_id = None
    db.flush()
    if pledgers:
        text = (f"Fællesgaven «{item.text}» er annulleret – ønsket er fjernet fra ønskesedlen." if reason == "wish_removed"
                else f"Fællesgaven «{item.text}» er stoppet af ønskesedlens ejer. Dit tilsagn gælder ikke længere.")
        _tell(db, item, pledgers, text, dedupe=f"gift-cancelled:{gift.id}")
    return bool(pledgers)


# --------------------------------------------------------------------------- the givers' side

class PledgeTooHigh(ApiError):
    status_code = 409
    code = "pledge_exceeds_remaining"


def _giver_access(db: OrmSession, task: PrivateTask, m: PrivateTaskMember, item_id: uuid.UUID) -> PrivateTaskItem:
    if task.share_mode != "wishlist":
        raise Conflict("Kun delte ønskelister har fællesgaver", code="not_a_wishlist")
    if m.role == "owner":
        raise Forbidden("Fællesgaven tilhører gavegiverne – ejeren af ønskesedlen kan ikke se eller ændre den",
                        code="owner_cannot_give")
    item = db.scalar(select(PrivateTaskItem).where(PrivateTaskItem.id == item_id, PrivateTaskItem.task_id == task.id)
                     .with_for_update())  # serialises every write on this wish (pledges, reservations, coordinator)
    if item is None:
        raise NotFound("Ønsket findes ikke")
    return item


def pledge(db: OrmSession, task: PrivateTask, m: PrivateTaskMember, item_id: uuid.UUID, amount_minor: int) -> None:
    """Set my pledge to amount_minor (join or change). Idempotent: the same amount again changes nothing."""
    item = _giver_access(db, task, m, item_id)
    if not isinstance(amount_minor, int) or amount_minor <= 0 or amount_minor > MAX_MINOR:
        raise ValidationFailed("Skriv et beløb over 0", field_errors=[{"field": "amount_minor",
                                                                     "message": "Skriv et beløb over 0"}])
    gift = live_gift(db, item.id, lock=True)
    if gift is None:
        if item.archived_at is not None or not item.group_gift_enabled or not item.group_gift_target_minor:
            raise Conflict("Dette ønske er ikke en fællesgave", code="group_gift_off")
        if item.reserved_by_user_id is not None:
            raise Conflict("Ønsket er allerede reserveret – det kan ikke også være en fællesgave"
                           if item.reserved_by_user_id != m.user_id else
                           "Du har reserveret ønsket. Fortryd reservationen, hvis I vil gå sammen om det.",
                           code="already_reserved")
        gift = PrivateGroupGift(item_id=item.id, task_id=task.id, target_minor=item.group_gift_target_minor,
                                currency=item.currency or "DKK", status="open", created_at=_now(), updated_at=_now())
        db.add(gift)
        db.flush()
    if gift.status == "bought":
        raise Conflict("Gaven er markeret som købt – tilsagn kan ikke ændres", code="gift_bought")
    mine = _mine(db, gift.id, m.user_id, lock=True)
    current = mine.amount_minor if mine is not None and mine.status == "active" else 0
    pledged, _n = totals(db, gift.id)
    remaining = gift.target_minor - (pledged - current)
    if amount_minor > remaining:
        if remaining <= 0:
            raise Conflict("Gaven har allerede fuldt tilsagn", code="gift_full",
                           extra={"remaining_minor": 0, "currency": gift.currency})
        raise PledgeTooHigh("Beløbet er højere end det, der mangler", extra={"remaining_minor": remaining,
                                                                             "currency": gift.currency})
    if mine is None:
        db.add(PrivateGiftPledge(gift_id=gift.id, user_id=m.user_id, amount_minor=amount_minor, status="active",
                                 created_at=_now(), updated_at=_now()))
    elif mine.status != "active" or mine.amount_minor != amount_minor:
        mine.amount_minor, mine.status, mine.updated_at = amount_minor, "active", _now()
    gift.updated_at = _now()
    db.flush()


def withdraw(db: OrmSession, task: PrivateTask, m: PrivateTaskMember, item_id: uuid.UUID) -> None:
    """Cancel my pledge (idempotent). The coordinator's role (and a pending handover to me) goes with it."""
    item = _giver_access(db, task, m, item_id)
    gift = live_gift(db, item.id, lock=True)
    if gift is None:
        return
    if gift.status == "bought":
        raise Conflict("Gaven er markeret som købt – tilsagn kan ikke ændres", code="gift_bought")
    mine = _mine(db, gift.id, m.user_id, lock=True)
    if mine is None or mine.status != "active":
        return
    mine.status, mine.updated_at = "cancelled", _now()
    if gift.coordinator_user_id == m.user_id:
        gift.coordinator_user_id, gift.pending_coordinator_user_id = None, None
    if gift.pending_coordinator_user_id == m.user_id:
        gift.pending_coordinator_user_id = None
    gift.updated_at = _now()
    db.flush()


def _require_participant(db: OrmSession, gift: PrivateGroupGift, user_id: uuid.UUID) -> None:
    mine = _mine(db, gift.id, user_id)
    if mine is None or mine.status != "active":
        raise Forbidden("Kun deltagere i fællesgaven kan det", code="not_a_participant")


def coordinator(db: OrmSession, task: PrivateTask, m: PrivateTaskMember, item_id: uuid.UUID, action: str,
                to_user_ref: str | None = None) -> None:
    item = _giver_access(db, task, m, item_id)
    gift = live_gift(db, item.id, lock=True)
    if gift is None:
        raise Conflict("Fællesgaven er ikke startet endnu", code="gift_not_started")
    _require_participant(db, gift, m.user_id)
    if action == "take":
        if gift.coordinator_user_id not in (None, m.user_id):
            raise Conflict("Der er allerede en koordinator – bed om at få rollen overdraget", code="has_coordinator")
        gift.coordinator_user_id = m.user_id
    elif action == "transfer":
        if gift.coordinator_user_id != m.user_id:
            raise Forbidden("Kun koordinatoren kan overdrage rollen", code="not_coordinator")
        try:
            to = uuid.UUID(str(to_user_ref))
        except ValueError as e:
            raise ValidationFailed("Vælg en deltager", field_errors=[{"field": "to"}]) from e
        target = _mine(db, gift.id, to)
        if to == m.user_id or target is None or target.status != "active":
            raise ValidationFailed("Vælg en anden deltager i gaven", field_errors=[{"field": "to"}])
        gift.pending_coordinator_user_id = to
        _tell(db, item, [to], f"{_first(db, m.user_id)} vil gerne overdrage koordinatorrollen for «{item.text}» til dig.",
              dedupe=f"gift-handover:{gift.id}:{to}")
    elif action == "accept":
        if gift.pending_coordinator_user_id != m.user_id:
            raise Conflict("Der er ingen overdragelse til dig", code="no_handover")
        gift.coordinator_user_id, gift.pending_coordinator_user_id = m.user_id, None
    elif action == "decline":
        if gift.pending_coordinator_user_id == m.user_id:
            gift.pending_coordinator_user_id = None
    elif action == "cancel_transfer":
        if gift.coordinator_user_id == m.user_id:
            gift.pending_coordinator_user_id = None
    elif action == "release":
        if gift.coordinator_user_id == m.user_id:
            if gift.status == "bought":
                raise Conflict("Overdrag rollen i stedet – gaven er markeret som købt", code="gift_bought")
            gift.coordinator_user_id, gift.pending_coordinator_user_id = None, None
    else:
        raise ValidationFailed("Ukendt handling", field_errors=[{"field": "action"}])
    gift.updated_at = _now()
    db.flush()


def mark_bought(db: OrmSession, task: PrivateTask, m: PrivateTaskMember, item_id: uuid.UUID, bought: bool) -> None:
    item = _giver_access(db, task, m, item_id)
    gift = live_gift(db, item.id, lock=True)
    if gift is None or gift.coordinator_user_id != m.user_id:
        raise Forbidden("Kun gavens koordinator kan markere den som købt", code="not_coordinator")
    if bought and gift.status == "open":
        gift.status, gift.bought_at = "bought", _now()
        others = [u for u in db.scalars(_active(db, gift.id).with_only_columns(PrivateGiftPledge.user_id)) if u != m.user_id]
        _tell(db, item, others, f"{_first(db, m.user_id)} har markeret fællesgaven «{item.text}» som købt.",
              dedupe=f"gift-bought:{gift.id}")
    elif not bought and gift.status == "bought":
        gift.status, gift.bought_at = "open", None
    gift.updated_at = _now()
    db.flush()


def on_member_removed(db: OrmSession, task: PrivateTask, user_id: uuid.UUID) -> None:
    """A giver left (or was removed from) the list: their open pledges and roles end; bought gifts are kept."""
    gifts = db.scalars(select(PrivateGroupGift).where(PrivateGroupGift.task_id == task.id,
                                                      PrivateGroupGift.status == "open").with_for_update())
    for g in gifts:
        p = _mine(db, g.id, user_id, lock=True)
        if p is not None and p.status == "active":
            p.status, p.updated_at = "cancelled", _now()
        if g.coordinator_user_id == user_id:
            g.coordinator_user_id, g.pending_coordinator_user_id = None, None
        if g.pending_coordinator_user_id == user_id:
            g.pending_coordinator_user_id = None


def _tell(db: OrmSession, item: PrivateTaskItem, user_ids, text: str, *, dedupe: str) -> None:
    """A service message to givers only (push, else e-mail). Never to the wishlist's owner."""
    from app.config import get_settings
    from app.modules.integrations import email_templates as tpl
    from app.modules.privat import push

    owner_id = db.scalar(select(PrivateTaskMember.user_id).where(PrivateTaskMember.task_id == item.task_id,
                                                                 PrivateTaskMember.role == "owner"))
    url = f"{get_settings().frontend_base_url.rstrip('/')}/privat/opgaver/{item.task_id}"
    for uid in set(user_ids):
        if uid == owner_id:
            continue
        u = db.get(User, uid)
        if u is None:
            continue
        mail = tpl.Email(subject="Fællesgave", heading="Fællesgave", paragraphs=[text], button_label="Se ønskesedlen",
                         button_url=url, footer_reason="Du får denne e-mail, fordi du er med i en fællesgave i Dialogbot.")
        push.notify(db, uid, title="Fællesgave", body=text, url=url, dedupe=f"{dedupe}:{uid}",
                    email={"to_email": u.email, "email": tpl.to_payload(mail)})

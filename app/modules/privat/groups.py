"""Saved groups («Mine folk»): share with many people in one tap.

Data rules: a group is readable ONLY by its owner. The phone numbers in it are used for exactly two things – giving
them back to the owner (so the owner texts from their OWN phone) and nothing else. A typed number is NEVER looked up
against Dialogbot's users (F-P2-02-X10): that would tell the owner whether – and as whom – any number is registered,
and would put strangers on lists they never agreed to. Dialogbot never contacts them and never markets to them; they
are deleted with the group (cascade) or the account (owner_user_id cascade).

Sharing a list with a group: only people who have themselves said yes to the owner before – a member row with a
user_id, set when they accepted one of the owner's invitations (`suggested`, or a personal link from this group) or
joined the group by its link – are added to the list directly and get an in-app message; everyone else (every typed
number) gets an invitation the owner texts from their own phone, and joins only by accepting it – one group SMS with one link, or a one-by-one queue
with a personal short link and text per person (then GET invite-status shows member / opened / invited per person).
"""
from __future__ import annotations

import re
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from app.core.errors import NotFound, ValidationFailed
from app.models import (
    PrivateGroup,
    PrivateGroupLink,
    PrivateGroupMember,
    PrivateInvite,
    PrivateProfile,
    PrivateTask,
    PrivateTaskMember,
    User,
)
from app.modules.privat import addons, invites, lookup_limits, rules, service, sharing

MAX_MEMBERS = 100


def normalize(raw: str | None) -> str | None:
    from app.modules.campaigns.service import normalize_phone

    return normalize_phone(raw or "") if raw else None


def get_own(db: OrmSession, ctx, group_id: uuid.UUID) -> PrivateGroup:
    """Only the owner: anyone else gets 404."""
    g = db.scalar(select(PrivateGroup).where(PrivateGroup.id == group_id, PrivateGroup.owner_user_id == ctx.user_id))
    if g is None:
        raise NotFound("Gruppen findes ikke")
    return g


def members(db: OrmSession, g: PrivateGroup) -> list[PrivateGroupMember]:
    return list(db.scalars(select(PrivateGroupMember).where(PrivateGroupMember.group_id == g.id)
                           .order_by(PrivateGroupMember.created_at, PrivateGroupMember.name)))


def group_out(db: OrmSession, g: PrivateGroup) -> dict:
    """For the OWNER only (it contains the numbers the owner saved)."""
    return {"id": str(g.id), "name": g.name, "created_at": g.created_at.isoformat(),
            "members": [{"id": str(m.id), "name": m.name, "phone_e164": m.phone_e164,
                         "user_id": str(m.user_id) if m.user_id else None,
                         "phone_display": rules.phone_display(m.phone_e164), "has_dialogbot": _known_user(db, m) is not None}
                        for m in members(db, g)]}


def list_groups(db: OrmSession, ctx) -> list[PrivateGroup]:
    return list(db.scalars(select(PrivateGroup).where(PrivateGroup.owner_user_id == ctx.user_id)
                           .order_by(PrivateGroup.created_at)))


def find_by_name(db: OrmSession, ctx, name: str) -> PrivateGroup | None:
    n = (name or "").strip().lower()
    if not n:
        return None
    for g in list_groups(db, ctx):
        if g.name.lower() == n:
            return g
    return next((g for g in list_groups(db, ctx) if n and (n in g.name.lower() or g.name.lower() in n)), None)


def create(db: OrmSession, ctx, name: str, people: list[dict] | None = None) -> PrivateGroup:
    name = (name or "").strip()[:100]
    if not name:
        raise ValidationFailed("Giv gruppen et navn", field_errors=[{"field": "name"}])
    g = PrivateGroup(owner_user_id=ctx.user_id, name=name)
    db.add(g)
    db.flush()
    if people:
        add_members(db, ctx, g, people)
    return g


def rename(db: OrmSession, ctx, g: PrivateGroup, name: str) -> None:
    name = (name or "").strip()[:100]
    if not name:
        raise ValidationFailed("Giv gruppen et navn", field_errors=[{"field": "name"}])
    g.name = name


def suggested(db: OrmSession, ctx) -> list[dict]:
    """People who accepted my invitations (members of lists I own). Names only – they are on Dialogbot already."""
    owned = select(PrivateTaskMember.task_id).where(PrivateTaskMember.user_id == ctx.user_id,
                                                    PrivateTaskMember.role == "owner")
    rows = db.execute(select(User.id, User.display_name).join(PrivateTaskMember, PrivateTaskMember.user_id == User.id)
                      .where(PrivateTaskMember.task_id.in_(owned), PrivateTaskMember.user_id != ctx.user_id)
                      .distinct()).all()
    return [{"user_id": str(uid), "name": name, "has_dialogbot": True} for uid, name in rows]


def add_members(db: OrmSession, ctx, g: PrivateGroup, people: list[dict], paste: str | None = None) -> dict:
    """Normalises numbers to E.164 (+45 default) and drops duplicates (same number or same person)."""
    existing = members(db, g)
    phones = {m.phone_e164 for m in existing if m.phone_e164}
    users = {m.user_id for m in existing if m.user_id}
    allowed_users = {s["user_id"] for s in suggested(db, ctx)}
    entries = list(people or [])
    for part in re.split(r"[,;\n]+", paste or ""):
        if part.strip():
            entries.append({"name": "", "phone": part.strip()})
    from datetime import timedelta

    base = max([m.created_at for m in existing] + [rules.now()])  # keeps the order people were added in
    added, duplicates, invalid = 0, 0, []
    for p in entries:
        name = str(p.get("name") or "").strip()[:100]
        uid = None
        if p.get("user_id"):
            if str(p["user_id"]) not in allowed_users:
                invalid.append({"name": name, "reason": "Ukendt person"})
                continue
            uid = uuid.UUID(str(p["user_id"]))
        phone = normalize(str(p.get("phone") or "")) if p.get("phone") else None
        if p.get("phone") and phone is None:
            invalid.append({"name": name, "value": str(p["phone"])[:30], "reason": "Ugyldigt telefonnummer"})
            continue
        if phone is None and uid is None:
            invalid.append({"name": name, "reason": "Mangler telefonnummer"})
            continue
        if (phone and phone in phones) or (uid and uid in users):
            duplicates += 1
            continue
        if len(existing) + added >= MAX_MEMBERS:
            raise ValidationFailed(f"Højst {MAX_MEMBERS} personer i en gruppe")
        if not name and uid:
            u = db.get(User, uid)
            name = u.display_name if u else ""
        db.add(PrivateGroupMember(group_id=g.id, name=name or rules.phone_display(phone) or "Ukendt", phone_e164=phone,
                                  user_id=uid, created_at=base + timedelta(microseconds=added + 1)))
        phones.add(phone)
        users.add(uid)
        added += 1
    db.flush()
    return {"added": added, "duplicates": duplicates, "invalid": invalid}


def remove_member(db: OrmSession, g: PrivateGroup, member_id: uuid.UUID) -> None:
    m = db.scalar(select(PrivateGroupMember).where(PrivateGroupMember.id == member_id, PrivateGroupMember.group_id == g.id))
    if m is None:
        raise NotFound("Personen findes ikke i gruppen")
    db.delete(m)


def _known_user(db: OrmSession, m: PrivateGroupMember) -> uuid.UUID | None:
    """The person has accepted the owner before (the member row carries their user id) and is on Dialogbot Privat.
    Never by phone number: matching a typed number against users' verified phones leaked membership + real name and
    enrolled strangers without consent (F-P2-02-X10)."""
    if m.user_id and db.scalar(select(PrivateProfile.workspace_id).where(PrivateProfile.user_id == m.user_id)):
        return m.user_id
    return None


def share(db: OrmSession, ctx, task_id: uuid.UUID, group_id: uuid.UUID, *, mode: str, role: str, style: str) -> dict:
    g = get_own(db, ctx, group_id)
    if style not in ("group_sms", "one_by_one"):
        raise ValidationFailed("Vælg group_sms eller one_by_one", field_errors=[{"field": "style"}])
    key = addons.SHARE_MODE_ADDON.get(mode)
    if key is None:
        raise ValidationFailed("Vælg group eller wishlist", field_errors=[{"field": "mode"}])
    task, me = sharing.access(db, task_id, ctx.user_id, lock=True)
    # authorizes (owner, list, add-on on) and fixes the share mode, exactly like a single invitation
    addons.require(db, ctx.ws_id, key)
    fixed = sharing.authorize(db, ctx, task.id, mode, role)
    role = fixed["role"]
    added, rest = [], []
    for m in members(db, g):
        uid = _known_user(db, m)
        if uid is not None and uid != ctx.user_id:
            if sharing.member(db, task.id, uid) is None:
                db.add(PrivateTaskMember(task_id=task.id, user_id=uid, role=role))
                db.flush()
                p = db.scalar(select(PrivateProfile).where(PrivateProfile.user_id == uid))
                shared_text = f"{rules.first_name(ctx.user.display_name)} har delt «{task.title}» med dig."
                service.add_message(db, p.workspace_id, kind="text", task_id=task.id, text=shared_text)
                from app.modules.privat import push

                push.notify(db, uid, title=task.title, body=shared_text, url=service._task_url(task),
                            dedupe=f"shared:{task.id}:{uid}")
                u = db.get(User, uid)  # the person's own name – never the owner's label for them
                service.event(db, task, f"{rules.first_name(u.display_name if u else None)} er med på listen")
            added.append({"name": m.name})
        elif uid is None and m.phone_e164:
            rest.append(m)
    sms_group, sms_queue = None, None
    if rest and style == "group_sms":
        inv, raw = invites.create(db, ctx, addon_key=key, resource_id=task.id, mode=mode, role=role)
        o = invites.invite_out(db, inv, raw, ctx.user.display_name)
        sms_group = {"recipients": [m.phone_e164 for m in rest], "body": o["suggested_text"], "short_url": o["short_url"]}
    elif rest:
        sms_queue = []
        for m in rest:
            inv, raw = invites.create(db, ctx, addon_key=key, resource_id=task.id, mode=mode, role=role,
                                      recipient_group_member_id=m.id)
            o = invites.invite_out(db, inv, raw, ctx.user.display_name, to_name=m.name)
            sms_queue.append({"member_id": str(m.id), "name": m.name, "phone_e164": m.phone_e164,
                              "body": o["suggested_text"], "short_url": o["short_url"]})
    service.touch(task)
    return {"added_in_app": added, "sms_group": sms_group, "sms_queue": sms_queue}


def invite_status(db: OrmSession, ctx, task: PrivateTask) -> list[dict]:
    """Per person, for the OWNER: member (on the list) / opened (opened their personal link) / invited."""
    out, seen = [], set()
    for tm, name in db.execute(select(PrivateTaskMember, User.display_name).join(User, User.id == PrivateTaskMember.user_id)
                               .where(PrivateTaskMember.task_id == task.id, PrivateTaskMember.role != "owner")):
        out.append({"name": name, "status": "member"})
        seen.add(tm.user_id)
    rows = db.execute(select(PrivateInvite, PrivateGroupMember).join(
        PrivateGroupMember, PrivateGroupMember.id == PrivateInvite.recipient_group_member_id).where(
        PrivateInvite.resource_type == "list", PrivateInvite.resource_id == task.id,
        PrivateInvite.revoked_at.is_(None)).order_by(PrivateInvite.created_at)).all()
    latest: dict = {}
    for inv, gm in rows:
        latest[gm.id] = (inv, gm)
    for inv, gm in latest.values():
        if gm.user_id and gm.user_id in seen:
            continue
        out.append({"name": gm.name, "status": "opened" if inv.opened_count else "invited",
                    "member_id": str(gm.id)})
    return out


# --------------------------------------------------------------------------- join links («Byg gruppen selv»)

JOINS_PER_HOUR = 50        # new members per link per hour
CODES_PER_LINK_HOUR = 20   # SMS codes per link per hour (anti SMS-pumping)
CODES_PER_PHONE_HOUR = 3
CODES_PER_OWNER_HOUR = 20  # all of one owner's links together: minting more links never buys more SMS (F-PS-01)


def _rate_limited(msg: str):
    from app.core.errors import ApiError

    return ApiError(msg, code="rate_limited", status_code=429)


def create_link(db: OrmSession, ctx, g: PrivateGroup) -> tuple[PrivateGroupLink, dict]:
    from datetime import timedelta

    from sqlalchemy.exc import IntegrityError

    from app.config import get_settings

    for _ in range(8):
        code = invites.new_short_code()
        if db.scalar(select(PrivateGroupLink.id).where(PrivateGroupLink.short_code == code)) is not None:
            continue
        link = PrivateGroupLink(group_id=g.id, short_code=code, created_by=ctx.user_id,
                                expires_at=rules.now() + timedelta(days=rules.INVITE_DAYS))
        try:
            with db.begin_nested():
                db.add(link)
        except IntegrityError:
            continue
        url = f"{get_settings().privat_group_url_base}{code}"
        name = invites._gsm(rules.first_name(ctx.user.display_name))[:20].strip()
        text = invites._gsm(f"Tryk her for at komme med i {g.name[:40]} på Dialogbot, så kan jeg dele lister med jer: "
                            f"{url.split('://', 1)[-1]}" + (f" - {name}" if name else ""))[:160]
        return link, {"short_url": url, "short_code": code, "suggested_text": text,
                      "expires_at": link.expires_at.isoformat()}
    from app.core.errors import ApiError

    raise ApiError("Kunne ikke lave et link. Prøv igen.", code="short_code_exhausted", status_code=503)


def revoke_links(db: OrmSession, g: PrivateGroup) -> None:
    from sqlalchemy import update

    db.execute(update(PrivateGroupLink).where(PrivateGroupLink.group_id == g.id, PrivateGroupLink.revoked_at.is_(None))
               .values(revoked_at=rules.now()))


def link_by_code(db: OrmSession, code: str) -> tuple[PrivateGroupLink, PrivateGroup]:
    link = db.scalar(select(PrivateGroupLink).where(PrivateGroupLink.short_code == (code or "").strip().upper()[:8]))
    if link is None or link.revoked_at is not None or link.expires_at <= rules.now():
        raise NotFound("Linket er ugyldigt eller udløbet", code="invite_invalid")
    return link, db.get(PrivateGroup, link.group_id)


def link_preview(db: OrmSession, code: str) -> dict:
    """Public: group name, owner's first name and member COUNT. Never names or numbers."""
    _link, g = link_by_code(db, code)
    owner = db.get(User, g.owner_user_id)
    return {"group_name": g.name, "owner_first_name": rules.first_name(owner.display_name if owner else None),
            "member_count": len(members(db, g))}


def _code_hash(link_id, phone: str, code: str) -> str:
    import hashlib
    import hmac

    from app.config import get_settings

    return hmac.new((get_settings().secret_key or "").encode(), f"group_join:{link_id}:{phone}:{code}".encode(),
                    hashlib.sha256).hexdigest()


def join(db: OrmSession, code: str, *, principal=None, name: str | None, phone: str | None,
         sms_code: str | None, ip: str = "unknown") -> dict:
    """Join a group by its link. Logged in: linked to the user id. Not logged in: the name, plus a number only once
    it is verified with an SMS code (first call sends the code, second call with `code` joins). Deduped by user id or
    number (and by exact name for name-only joins)."""
    import secrets
    from datetime import timedelta

    from sqlalchemy import func

    from app.models import PrivatePhoneCode

    link, g = link_by_code(db, code)
    db.scalar(select(PrivateGroup).where(PrivateGroup.id == g.id).with_for_update())
    now = rules.now()
    existing = members(db, g)
    name = (name or "").strip()[:100]

    def rate_check():
        n = db.scalar(select(func.count()).select_from(PrivateGroupMember).where(
            PrivateGroupMember.joined_via_link_id == link.id, PrivateGroupMember.created_at >= now - timedelta(hours=1)))
        if (n or 0) >= JOINS_PER_HOUR:
            raise _rate_limited("For mange er kommet med via dette link den sidste time. Prøv igen senere.")

    if principal is not None:
        user = principal.user
        if user.id == g.owner_user_id:
            return {"joined": True, "already": True}
        prof_phone = db.scalar(select(PrivateProfile.phone_e164).where(PrivateProfile.user_id == user.id,
                                                                       PrivateProfile.phone_verified_at.is_not(None)))
        for m in existing:
            if m.user_id == user.id or (prof_phone and m.phone_e164 == prof_phone):
                if m.user_id is None:
                    m.user_id = user.id
                return {"joined": True, "already": True}
        rate_check()
        db.add(PrivateGroupMember(group_id=g.id, name=name or user.display_name, user_id=user.id,
                                  joined_via_link_id=link.id, created_at=now))
        db.flush()
        return {"joined": True, "already": False}
    if not name:
        raise ValidationFailed("Skriv dit navn", field_errors=[{"field": "name"}])
    if not phone:
        if any(m.name.lower() == name.lower() and not m.phone_e164 and not m.user_id for m in existing):
            return {"joined": True, "already": True}
        rate_check()
        db.add(PrivateGroupMember(group_id=g.id, name=name, joined_via_link_id=link.id, created_at=now))
        db.flush()
        return {"joined": True, "already": False}
    e164 = _danish_mobile(phone)
    if any(m.phone_e164 == e164 for m in existing):
        return {"joined": True, "already": True}
    q = select(PrivatePhoneCode).where(PrivatePhoneCode.purpose == "group_join", PrivatePhoneCode.ref_id == link.id,
                                       PrivatePhoneCode.phone_e164 == e164)
    if not sms_code:
        hour = now - timedelta(hours=1)
        per_link = db.scalar(select(func.count()).select_from(PrivatePhoneCode).where(
            PrivatePhoneCode.purpose == "group_join", PrivatePhoneCode.ref_id == link.id,
            PrivatePhoneCode.created_at >= hour)) or 0
        per_phone = db.scalar(select(func.count()).select_from(PrivatePhoneCode).where(
            PrivatePhoneCode.phone_e164 == e164, PrivatePhoneCode.created_at >= hour)) or 0
        if per_link >= CODES_PER_LINK_HOUR or per_phone >= CODES_PER_PHONE_HOUR:
            raise _rate_limited("Der er sendt for mange koder. Prøv igen senere.")
        rate_check()
        lookup_limits.sms_budget(db, ip=ip, account=f"user:{g.owner_user_id}", per_account=CODES_PER_OWNER_HOUR)
        c = f"{secrets.randbelow(1_000_000):06d}"
        db.add(PrivatePhoneCode(purpose="group_join", ref_id=link.id, phone_e164=e164, code_hash=_code_hash(link.id, e164, c),
                                expires_at=now + timedelta(minutes=10), created_at=now))
        _send_code(db, g, e164, c)
        return {"joined": False, "code_sent": True}
    pc = db.scalar(q.order_by(PrivatePhoneCode.created_at.desc()).limit(1).with_for_update())
    from app.core.errors import Conflict

    if pc is None or pc.expires_at <= now or pc.verified_at is not None:
        raise Conflict("Koden er udløbet. Bed om en ny.", code="code_expired")
    if pc.attempts >= 5:
        raise Conflict("For mange forsøg. Bed om en ny kode.", code="too_many_attempts")
    pc.attempts += 1
    import hmac as _hmac

    if not _hmac.compare_digest(pc.code_hash, _code_hash(link.id, e164, sms_code.strip())):
        db.commit()
        raise ValidationFailed("Koden passer ikke", field_errors=[{"field": "code"}])
    pc.verified_at = now
    rate_check()
    db.add(PrivateGroupMember(group_id=g.id, name=name, phone_e164=e164, joined_via_link_id=link.id, created_at=now))
    db.flush()
    return {"joined": True, "already": False}


def _danish_mobile(raw: str | None) -> str:
    """Codes go only to Danish numbers (+45, 8 digits, not premium 90xx) – what Privat's SMS path supports and what
    the UI asks for («8 cifre»; the funnel has the same rule). Any other E.164 number would let a public link pump paid
    SMS abroad (F-PS-01)."""
    from app.modules.sales.service import danish_number

    try:
        return danish_number(raw or "")
    except ValidationFailed:
        raise ValidationFailed("Skriv dit mobilnummer med 8 cifre", field_errors=[{"field": "phone"}]) from None


def _send_code(db: OrmSession, g: PrivateGroup, e164: str, code: str) -> None:
    from app.core.errors import ApiError
    from app.modules.integrations import privat_mails
    from app.modules.integrations.connectors import sms
    from app.modules.privat import phone

    owner_ws = db.scalar(select(PrivateProfile.workspace_id).where(PrivateProfile.user_id == g.owner_user_id))
    from app.models import Workspace

    try:
        sms.send(db, db.get(Workspace, owner_ws), sender=phone.SENDER, to=e164,
                 body=privat_mails.sms_code(code), simulated=phone._simulated())
    except Exception as e:  # noqa: BLE001
        raise ApiError("SMS kunne ikke sendes lige nu. Prøv igen om lidt.", code="sms_failed", status_code=502) from e

"""ONE invitation mechanism for every shareable add-on (and for plain "try Dialogbot" links).

An invite points at (resource_type, resource_id) and, for an add-on, at its key. The add-on's `resource_hooks`
module (optional) authorizes the share, builds the public preview and performs the accept; without hooks the invite
simply invites the person to the add-on. Every invite gets the same public landing page (preview), the same accept
(creates the private account if needed) and the same referral reward (referrals.py). Dialogbot never sends these
invitations itself: the web opens the user's OWN SMS app with `suggested_text` prefilled (short link /i/<code>).
No contacts are uploaded or stored, and no recipient ever reaches the server (no marketing to invitees).
"""
from __future__ import annotations

import re
import uuid
from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as OrmSession

from app.config import get_settings
from app.core.errors import ApiError, Forbidden, NotFound, ValidationFailed
from app.core.security import new_token, token_digest
from app.models import PrivateInvite, PrivateProfile, User
from app.modules.privat import addons, rules

CTA_TEXT = ("{name} bruger Dialogbot – en personlig assistent, der laver lister, minder dig om ting og ringer for dig. "
            "Få din egen: 10 gratis opgaver hver måned")
TRY_RESOURCE = "dialogbot"  # an invitation to Dialogbot itself (Konto → «Inviter venner»)


SHORT_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # A-Z2-9 without 0/O/1/I/L
SHORT_LEN = 8
# GSM 03.38 basic character set (+ the extension table's common characters are deliberately NOT used).
GSM7 = set("@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞÆæßÉ !\"#¤%&'()*+,-./0123456789:;<=>?¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§"
           "¿abcdefghijklmnopqrstuvwxyzäöñüà")


def new_short_code() -> str:
    import secrets

    return "".join(secrets.choice(SHORT_ALPHABET) for _ in range(SHORT_LEN))


def _gsm(s: str) -> str:
    s = s.replace("–", "-").replace("—", "-").replace("«", '"').replace("»", '"')
    return "".join(ch for ch in s if ch in GSM7)


def short_url(code: str) -> str:
    return f"{get_settings().privat_short_url_base}{code}"


def suggested_text(inv: PrivateInvite, inviter_name: str, list_type: str | None, to_name: str | None = None) -> str:
    """The SMS the user sends from their OWN phone (Dialogbot never sends it): Danish, as the user, GSM-7 only,
    at most 160 characters, no emoji."""
    link = short_url(inv.short_code).split("://", 1)[-1]
    name = _gsm(rules.first_name(inviter_name))[:20].strip()
    if inv.mode == "wishlist" or list_type == "wishlist":
        body = f"Hej! Jeg har lavet en ønskeliste - se den og reservér her: {link}"
    elif list_type == "shopping":
        body = f"Hej! Jeg har delt vores indkøbsliste - tilføj det, du mangler: {link}"
    elif inv.mode == "group":
        body = f"Hej! Jeg har delt en liste med dig - se den og tilføj her: {link}"
    else:
        body = f"Hej! Jeg bruger Dialogbot til lister og påmindelser. Prøv selv: {link}"
    if to_name and (first := _gsm(rules.first_name(to_name))[:20].strip()):
        body = body.replace("Hej!", f"Hej {first}!", 1)
    text = _gsm(f"{body} - {name}" if name else body)
    return text[:160]


def url_for(raw: str) -> str:
    return f"{get_settings().frontend_base_url.rstrip('/')}/privat/invitation/{raw}"


def create(db: OrmSession, ctx, *, addon_key: str | None, resource_id: uuid.UUID | None = None,
           mode: str | None = None, role: str = "editor",
           recipient_group_member_id: uuid.UUID | None = None) -> tuple[PrivateInvite, str]:
    if role not in ("editor", "viewer"):
        raise ValidationFailed("Rollen skal være editor eller viewer", field_errors=[{"field": "role"}])
    resource_type = TRY_RESOURCE
    if addon_key is not None:
        a = addons.get(addon_key)
        if not a.shareable:
            raise Forbidden(f"«{a.name}» kan ikke deles", code="addon_not_shareable", extra={"addon": addon_key})
        addons.require(db, ctx.ws_id, addon_key)
        resource_type = a.resource_type or a.key
        h = addons.hooks(a)
        if h is not None and hasattr(h, "authorize"):
            fixed = h.authorize(db, ctx, resource_id, mode, role)
            mode, role = fixed.get("mode", mode), fixed.get("role", role)
    raw = new_token()
    for _attempt in range(8):  # a short code that is already taken is simply drawn again
        code = new_short_code()
        if db.scalar(select(PrivateInvite.id).where(PrivateInvite.short_code == code)) is not None:
            continue
        inv = PrivateInvite(token_hash=token_digest(raw), short_code=code, resource_type=resource_type,
                            resource_id=resource_id, addon_key=addon_key, inviter_user_id=ctx.user_id, mode=mode,
                            role=role, expires_at=rules.now() + timedelta(days=rules.INVITE_DAYS),
                            recipient_group_member_id=recipient_group_member_id)
        try:
            with db.begin_nested():
                db.add(inv)
        except IntegrityError:
            continue
        return inv, raw
    raise ApiError("Kunne ikke lave en invitationskode. Prøv igen.", code="short_code_exhausted", status_code=503)


def invite_out(db: OrmSession, inv: PrivateInvite, raw: str, inviter_name: str, to_name: str | None = None) -> dict:
    """What the web needs to open the user's own SMS app with the text prefilled. Nothing is sent by Dialogbot."""
    from app.models import PrivateTask

    list_type = None
    if inv.resource_type == "list" and inv.resource_id:
        t = db.get(PrivateTask, inv.resource_id)
        list_type = t.list_type if t else None
    text = suggested_text(inv, inviter_name, list_type, to_name)
    return {"invite_url": url_for(raw), "token": raw, "short_code": inv.short_code, "short_url": short_url(inv.short_code),
            "expires_at": inv.expires_at.isoformat(), "suggested_text": text, "share_text": text}


def lookup(db: OrmSession, raw: str | None = None, *, code: str | None = None, lock: bool = False) -> PrivateInvite:
    """A usable invite, by token or by short code (case-insensitive). Unknown, revoked and expired all answer the
    same 404 (nothing to probe)."""
    if code is None and raw and re.fullmatch(r"[A-HJ-NP-Za-hj-np-z2-9]{8}", raw.strip()):
        code = raw  # the web may pass a short code where a token is expected
    if code is not None:
        q = select(PrivateInvite).where(PrivateInvite.short_code == (code or "").strip().upper()[:8])
    else:
        q = select(PrivateInvite).where(PrivateInvite.token_hash == token_digest(raw or ""))
    inv = db.scalar(q.with_for_update() if lock else q)
    if inv is None or inv.revoked_at is not None or inv.expires_at <= rules.now():
        raise NotFound("Invitationen er ugyldig eller udløbet", code="invite_invalid")
    if inv.addon_key and inv.addon_key not in addons.CATALOG:
        raise NotFound("Invitationen er ugyldig eller udløbet", code="invite_invalid")
    return inv


def preview(db: OrmSession, raw: str | None = None, *, code: str | None = None) -> dict:
    """Public landing page data: what is shared (title, owner's first name, item COUNT) and the Dialogbot card.
    Never items, notes, links, reservations, e-mail or phone. Counts the open."""
    inv = lookup(db, raw, code=code, lock=True)
    inviter = db.get(User, inv.inviter_user_id)
    first = rules.first_name(inviter.display_name if inviter else None)
    out = {"title": "Dialogbot", "owner_first_name": first, "list_type": None, "item_count": 0, "share_mode": inv.mode}
    if inv.addon_key:
        a = addons.CATALOG[inv.addon_key]
        out["title"] = a.name
        h = addons.hooks(a)
        if h is not None and hasattr(h, "preview"):
            out.update(h.preview(db, inv))
    inv.opened_count += 1
    return out | {"inviter_first_name": first, "resource_type": inv.resource_type, "addon_key": inv.addon_key,
                  "cta_text": CTA_TEXT.format(name=first)}


def accept(db: OrmSession, principal, raw: str | None = None, *, code: str | None = None) -> dict:
    """Join through an invite: creates the private account if needed (signup_source invite:<id>), runs the add-on's
    accept hook, records a referral for a NEW user. Returns the hook's result (a Task for lists) or {}."""
    from app.modules.privat import deps, referrals

    inv = lookup(db, raw, code=code, lock=True)
    user = principal.user
    _p, _created = deps.ensure_account(db, user, signup_source=f"invite:{inv.id}")
    p = db.scalar(select(PrivateProfile).where(PrivateProfile.user_id == user.id))
    ctx = deps._ctx(db, principal, p)
    result: dict = {}
    joined = True
    if inv.addon_key:
        h = addons.hooks(addons.CATALOG[inv.addon_key])
        if h is not None and hasattr(h, "accept") and inv.inviter_user_id != user.id:
            result, joined = h.accept(db, inv, ctx)
    if joined and inv.inviter_user_id != user.id:
        inv.accepted_count += 1
        _notify_inviter(db, inv, user)
    if inv.recipient_group_member_id and inv.inviter_user_id != user.id:
        from app.models import PrivateGroupMember

        gm = db.get(PrivateGroupMember, inv.recipient_group_member_id)
        taken = gm is not None and db.scalar(select(PrivateGroupMember.id).where(
            PrivateGroupMember.group_id == gm.group_id, PrivateGroupMember.user_id == user.id)) is not None
        if gm is not None and gm.user_id is None and not taken:
            gm.user_id, gm.joined_via_invite_id = user.id, inv.id  # recognised next time the owner shares
    referrals.on_accept(db, inv, user)
    referrals.try_activate(db, user.id)
    return result


def revoke_for(db: OrmSession, resource_type: str, resource_id: uuid.UUID) -> int:
    r = db.execute(update(PrivateInvite).where(PrivateInvite.resource_type == resource_type,
                                               PrivateInvite.resource_id == resource_id,
                                               PrivateInvite.revoked_at.is_(None)).values(revoked_at=rules.now()))
    return r.rowcount or 0


def _notify_inviter(db: OrmSession, inv: PrivateInvite, user: User) -> None:
    """The inviter hears that someone said yes (push; e-mail without a subscription). Never anything to the invitee."""
    from app.modules.integrations import email_templates as tpl
    from app.modules.privat import push

    inviter = db.get(User, inv.inviter_user_id)
    if inviter is None:
        return
    text = f"{rules.first_name(user.display_name)} har sagt ja til din invitation."
    mail = tpl.Email(subject=text, heading=text, paragraphs=["Du kan se det i Dialogbot."],
                     footer_reason="Du får denne e-mail, fordi du har inviteret nogen i Dialogbot.")
    push.notify(db, inviter.id, title="Dialogbot", body=text, url=None, dedupe=f"invite-accepted:{inv.id}:{user.id}",
                email={"to_email": inviter.email, "email": tpl.to_payload(mail)})

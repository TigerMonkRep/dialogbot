"""Dialogbot Privat API (docs/privat-api.md). Every route resolves the caller's OWN personal workspace (deps.py) and
reaches tasks only through membership (sharing.py). Public: the invitation previews. Operator: growth numbers."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session as OrmSession

from app.config import get_settings
from app.core.auth import Principal, get_current_principal
from app.core.errors import NotFound, Unauthenticated
from app.core.idempotency import IdempotencyGuard, scope_for
from app.db import get_db
from app.modules.privat import (
    addons,
    calls,
    chat,
    deps,
    groups,
    invites,
    ledger,
    lookup_limits,
    payments,
    phone,
    places,
    push,
    referrals,
    service,
    sharing,
    subscriptions,
)
from app.modules.privat.deps import PrivateCtx, private_ctx
from app.modules.voices.operator_router import operator

router = APIRouter(prefix="/privat", tags=["privat"])
public_router = APIRouter(prefix="/privat", tags=["privat"])
operator_router = APIRouter(prefix="/operator/privat", tags=["privat"])


class MessageIn(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    about_task_id: uuid.UUID | None = None


class ApproveIn(BaseModel):
    window: str | None = Field(default=None, max_length=200)
    share_phone: bool = False
    confirm_business: bool = Field(default=False, description="Påkrævet, når nummeret ligner et mobilnummer")
    at_next_open: bool = Field(default=False, description="Ring ved næste åbningstid, hvis virksomheden har lukket nu "
                                                          "(eller uden for kl. 8–18)")


class ActivateIn(BaseModel):
    method: str = Field(pattern="^(credit|sponsor)$")


class SponsorIn(BaseModel):
    task_id: uuid.UUID


class PhoneStartIn(BaseModel):
    phone: str = Field(min_length=8, max_length=20)


class PhoneVerifyIn(BaseModel):
    code: str = Field(min_length=4, max_length=10)


class SubscriptionCheckoutIn(BaseModel):
    plan: str = Field(pattern="^(basis|plus|familie)$")
    interval: str = Field(default="month", pattern="^(month|year)$")
    code: str | None = Field(default=None, max_length=40, description="rabatkode (valgfri)")


class ItemIn(BaseModel):
    text: str = Field(min_length=1, max_length=300)
    note: str | None = Field(default=None, max_length=500)
    link: str | None = Field(default=None, max_length=1000)


class ShareIn(BaseModel):
    mode: str = Field(pattern="^(group|wishlist)$")
    role: str = Field(default="editor", pattern="^(editor|viewer)$")


class AddonInviteIn(BaseModel):
    resource_id: uuid.UUID | None = None
    mode: str | None = Field(default=None, max_length=16)
    role: str = Field(default="editor", pattern="^(editor|viewer)$")


def _task(db: OrmSession, ctx: PrivateCtx, task_id: uuid.UUID) -> dict:
    t, _m = sharing.access(db, task_id, ctx.user_id)
    return service.task_out(db, t, ctx.user_id)


def _chat_out(db: OrmSession, ctx: PrivateCtx, msgs) -> dict:
    return {"messages": [service.message_out(m) for m in msgs], "balance": service.balance_out(db, ctx)}


# --------------------------------------------------------------------------- account

@router.post("/account")
def create_account(principal: Principal = Depends(get_current_principal), db: OrmSession = Depends(get_db)):
    """Create (idempotently) the caller's personal workspace: owner membership, no business rows, 3 welcome credits."""
    p, created = deps.ensure_account(db, principal.user)
    db.commit()
    return {"workspace_id": str(p.workspace_id), "created": created}


@router.get("/me")
def me(ctx: PrivateCtx = Depends(private_ctx), db: OrmSession = Depends(get_db)):
    out = service.balance_out(db, ctx)
    db.commit()  # an account from before subscriptions gets its trial row on first read
    return out


@router.get("/bootstrap")
def bootstrap(ctx: PrivateCtx = Depends(private_ctx), db: OrmSession = Depends(get_db)):
    """Everything the app needs on load and after an action, in ONE request: before this the web made eleven
    (me, day, tasks ×2, messages, ledger, addons, referrals, groups, subscription), each paying for its own
    session lookup and the Frankfurt↔database round trips – about a second of pure waiting after every message."""
    me = service.balance_out(db, ctx)
    own = [service.task_out(db, t, ctx.user_id) for t in service.list_tasks(db, ctx)]
    seen = {t["id"] for t in own}
    shared = [service.task_out(db, t, ctx.user_id) for t in service.list_tasks(db, ctx, shared=True) if str(t.id) not in seen]
    out = {
        "me": me, "day": service.day(db, ctx), "tasks": own + shared,
        "messages": [service.message_out(m) for m in service.messages(db, ctx, None)],
        "ledger": [{"id": str(r.id), "kind": r.kind, "amount": r.amount, "text": r.text, "created_at": r.created_at.isoformat()}
                   for r in ledger.rows(db, ctx.ws_id)],
        "addons": addons.catalog_out(db, ctx.ws_id), "referrals": referrals.summary(db, ctx),
        "groups": [groups.group_out(db, g) for g in groups.list_groups(db, ctx)],
        "subscription": subscriptions.subscription_out(db, ctx.ws_id),
    }
    db.commit()
    return out


# --------------------------------------------------------------------------- subscription

@router.get("/subscription")
def subscription(session_id: str | None = Query(default=None, max_length=200), ctx: PrivateCtx = Depends(private_ctx),
                 db: OrmSession = Depends(get_db)):
    """The trial / plan and this month's call quota. With ?session_id= (back from Stripe Checkout) the session is read
    from Stripe first, so the page is right before the webhook lands."""
    if session_id:
        subscriptions.sync_from_session(db, ctx, session_id)
    out = subscriptions.subscription_out(db, ctx.ws_id)
    db.commit()
    return out


@router.post("/subscription/checkout")
def subscription_checkout(body: SubscriptionCheckoutIn, ctx: PrivateCtx = Depends(private_ctx),
                          db: OrmSession = Depends(get_db)):
    """Stripe Checkout (mode=subscription). The plan becomes active through the webhook / the return sync."""
    url = subscriptions.checkout(db, ctx, plan=body.plan, interval=body.interval, code=body.code)
    db.commit()
    return {"url": url}


@router.post("/subscription/portal")
def subscription_portal(ctx: PrivateCtx = Depends(private_ctx), db: OrmSession = Depends(get_db)):
    """Stripe Billing Portal: change plan, cancel, update card. 501 not_configured without Stripe or a customer."""
    url = subscriptions.portal(db, ctx)
    db.commit()
    return {"url": url}


@router.get("/day")
def day(ctx: PrivateCtx = Depends(private_ctx), db: OrmSession = Depends(get_db)):
    return service.day(db, ctx)


@router.get("/ledger")
def ledger_rows(ctx: PrivateCtx = Depends(private_ctx), db: OrmSession = Depends(get_db)):
    return [{"id": str(r.id), "kind": r.kind, "amount": r.amount, "text": r.text, "created_at": r.created_at.isoformat()}
            for r in ledger.rows(db, ctx.ws_id)]


# --------------------------------------------------------------------------- tasks

@router.get("/tasks")
def list_tasks(status: str | None = Query(default=None, max_length=200), shared: bool | None = None,
               ctx: PrivateCtx = Depends(private_ctx), db: OrmSession = Depends(get_db)):
    return [service.task_out(db, t, ctx.user_id) for t in service.list_tasks(db, ctx, status=status, shared=shared)]


@router.get("/tasks/{task_id}")
def get_task(task_id: uuid.UUID, ctx: PrivateCtx = Depends(private_ctx), db: OrmSession = Depends(get_db)):
    return _task(db, ctx, task_id)


@router.post("/tasks/{task_id}/items")
def add_item(task_id: uuid.UUID, body: ItemIn, ctx: PrivateCtx = Depends(private_ctx), db: OrmSession = Depends(get_db)):
    t, m = sharing.access(db, task_id, ctx.user_id, lock=True)
    service.add_items(db, t, m, [body.text], note=body.note, link=body.link)
    db.commit()
    return service.task_out(db, t, ctx.user_id)


@router.delete("/tasks/{task_id}/items/{item_id}")
def delete_item(task_id: uuid.UUID, item_id: uuid.UUID, ctx: PrivateCtx = Depends(private_ctx),
                db: OrmSession = Depends(get_db)):
    t, m = sharing.access(db, task_id, ctx.user_id, lock=True)
    service.delete_item(db, t, m, item_id)
    db.commit()
    return service.task_out(db, t, ctx.user_id)


@router.post("/tasks/{task_id}/items/{item_id}/toggle")
def toggle_item(task_id: uuid.UUID, item_id: uuid.UUID, ctx: PrivateCtx = Depends(private_ctx),
                db: OrmSession = Depends(get_db)):
    t, m = sharing.access(db, task_id, ctx.user_id)
    service.toggle_item(db, t, m, item_id)
    db.commit()
    return service.task_out(db, t, ctx.user_id)


@router.post("/tasks/{task_id}/items/{item_id}/reserve")
def reserve_item(task_id: uuid.UUID, item_id: uuid.UUID, ctx: PrivateCtx = Depends(private_ctx),
                 db: OrmSession = Depends(get_db)):
    t, m = sharing.access(db, task_id, ctx.user_id)
    sharing.reserve(db, t, m, item_id, on=True)
    db.commit()
    return service.task_out(db, t, ctx.user_id)


@router.post("/tasks/{task_id}/items/{item_id}/unreserve")
def unreserve_item(task_id: uuid.UUID, item_id: uuid.UUID, ctx: PrivateCtx = Depends(private_ctx),
                   db: OrmSession = Depends(get_db)):
    t, m = sharing.access(db, task_id, ctx.user_id)
    sharing.reserve(db, t, m, item_id, on=False)
    db.commit()
    return service.task_out(db, t, ctx.user_id)


@router.post("/tasks/{task_id}/activate")
def activate(task_id: uuid.UUID, body: ActivateIn, ctx: PrivateCtx = Depends(private_ctx),
             db: OrmSession = Depends(get_db)):
    t, m = sharing.access(db, task_id, ctx.user_id, min_role="owner")
    service.activate(db, ctx, t, body.method)
    db.commit()
    return service.task_out(db, t, ctx.user_id)


@router.post("/sponsor/claim")
def sponsor_claim(body: SponsorIn, ctx: PrivateCtx = Depends(private_ctx), db: OrmSession = Depends(get_db)):
    """Pilot: a simulated, voluntary sponsor spot (max 2 a day) activates one draft task."""
    t, m = sharing.access(db, body.task_id, ctx.user_id, min_role="owner")
    service.activate(db, ctx, t, "sponsor")
    db.commit()
    return service.task_out(db, t, ctx.user_id)


# --------------------------------------------------------------------------- sharing

@router.post("/tasks/{task_id}/share")
def share(task_id: uuid.UUID, body: ShareIn, ctx: PrivateCtx = Depends(private_ctx), db: OrmSession = Depends(get_db)):
    """An invitation link the user sends from their OWN phone (suggested_text). Dialogbot sends nothing."""
    inv, raw = invites.create(db, ctx, addon_key=addons.SHARE_MODE_ADDON[body.mode], resource_id=task_id,
                              mode=body.mode, role=body.role)
    out = invites.invite_out(db, inv, raw, ctx.user.display_name)
    db.commit()
    return out


@router.post("/tasks/{task_id}/share/revoke")
def share_revoke(task_id: uuid.UUID, ctx: PrivateCtx = Depends(private_ctx), db: OrmSession = Depends(get_db)):
    t, m = sharing.access(db, task_id, ctx.user_id, min_role="owner")
    invites.revoke_for(db, "list", t.id)
    service.event(db, t, "Alle invitationslinks er gjort ugyldige")
    db.commit()
    return service.task_out(db, t, ctx.user_id)


@router.get("/tasks/{task_id}/members")
def members(task_id: uuid.UUID, ctx: PrivateCtx = Depends(private_ctx), db: OrmSession = Depends(get_db)):
    t, _m = sharing.access(db, task_id, ctx.user_id)
    return sharing.members_out(db, t, ctx.user_id)


@router.delete("/tasks/{task_id}/members/{member_id}")
def remove_member(task_id: uuid.UUID, member_id: uuid.UUID, ctx: PrivateCtx = Depends(private_ctx),
                  db: OrmSession = Depends(get_db)):
    t, m = sharing.access(db, task_id, ctx.user_id, lock=True)
    leaving = m.id == member_id
    snapshot = service.task_out(db, t, ctx.user_id) if leaving else None
    sharing.remove_member(db, t, m, member_id)
    db.commit()
    return snapshot if leaving else service.task_out(db, t, ctx.user_id)


def _public_enabled() -> None:
    if not get_settings().privat_enabled:
        raise NotFound("Invitationen er ugyldig eller udløbet", code="invite_invalid")


@public_router.get("/invites/by-code/{code}")
def invite_preview_by_code(code: str, request: Request, db: OrmSession = Depends(get_db)):
    """Public (no login): the short link /i/{code}. Same preview as by token; nothing personal beyond first name.
    Rate limited per IP, misses (unknown codes) much more strictly (429 rate_limited)."""
    _public_enabled()
    out = lookup_limits.guarded(db, request, lambda: invites.preview(db, code=code))
    db.commit()
    return out


@public_router.get("/invites/{token}")
def invite_preview(token: str, request: Request, db: OrmSession = Depends(get_db)):
    """Public (no login): title, owner's first name, list type, item COUNT, share mode, and the Dialogbot card.
    Rate limited per IP (429 rate_limited)."""
    _public_enabled()
    out = lookup_limits.guarded(db, request, lambda: invites.preview(db, token))
    db.commit()
    return out


@router.post("/invites/by-code/{code}/accept")
def invite_accept_by_code(code: str, request: Request, principal: Principal = Depends(get_current_principal),
                          db: OrmSession = Depends(get_db)):
    out = lookup_limits.guarded(db, request, lambda: invites.accept(db, principal, code=code))
    db.commit()
    return out


@router.post("/invites/{token}/accept")
def invite_accept(token: str, request: Request, principal: Principal = Depends(get_current_principal),
                  db: OrmSession = Depends(get_db)):
    """Join (creates the private account if needed). Returns the shared Task (or {} for a non-list invite)."""
    out = lookup_limits.guarded(db, request, lambda: invites.accept(db, principal, token))
    db.commit()
    return out


# --------------------------------------------------------------------------- groups («Mine folk»), owner-only

class PersonIn(BaseModel):
    name: str = Field(default="", max_length=100)
    phone: str | None = Field(default=None, max_length=30)
    user_id: uuid.UUID | None = None


class GroupIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    members: list[PersonIn] = Field(default_factory=list, max_length=100)


class GroupPatch(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class GroupMembersIn(BaseModel):
    members: list[PersonIn] = Field(default_factory=list, max_length=100)
    paste: str | None = Field(default=None, max_length=5000, description="Several numbers, comma or newline separated")


class ShareGroupIn(BaseModel):
    group_id: uuid.UUID
    mode: str = Field(pattern="^(group|wishlist)$")
    role: str = Field(default="editor", pattern="^(editor|viewer)$")
    style: str = Field(default="one_by_one", pattern="^(group_sms|one_by_one)$")


@router.get("/groups")
def group_list(ctx: PrivateCtx = Depends(private_ctx), db: OrmSession = Depends(get_db)):
    return [groups.group_out(db, g) for g in groups.list_groups(db, ctx)]


@router.post("/groups", status_code=201)
def group_create(body: GroupIn, ctx: PrivateCtx = Depends(private_ctx), db: OrmSession = Depends(get_db)):
    g = groups.create(db, ctx, body.name, [m.model_dump(mode="json") for m in body.members])
    db.commit()
    return groups.group_out(db, g)


@router.patch("/groups/{group_id}")
def group_rename(group_id: uuid.UUID, body: GroupPatch, ctx: PrivateCtx = Depends(private_ctx),
                 db: OrmSession = Depends(get_db)):
    g = groups.get_own(db, ctx, group_id)
    groups.rename(db, ctx, g, body.name)
    db.commit()
    return groups.group_out(db, g)


@router.delete("/groups/{group_id}", status_code=204)
def group_delete(group_id: uuid.UUID, ctx: PrivateCtx = Depends(private_ctx), db: OrmSession = Depends(get_db)):
    """Deletes the group and every number in it."""
    db.delete(groups.get_own(db, ctx, group_id))
    db.commit()
    return Response(status_code=204)


@router.post("/groups/{group_id}/members")
def group_add_members(group_id: uuid.UUID, body: GroupMembersIn, ctx: PrivateCtx = Depends(private_ctx),
                      db: OrmSession = Depends(get_db)):
    g = groups.get_own(db, ctx, group_id)
    result = groups.add_members(db, ctx, g, [m.model_dump(mode="json") for m in body.members], body.paste)
    db.commit()
    return groups.group_out(db, g) | {"result": result}


@router.delete("/groups/{group_id}/members/{member_id}")
def group_remove_member(group_id: uuid.UUID, member_id: uuid.UUID, ctx: PrivateCtx = Depends(private_ctx),
                        db: OrmSession = Depends(get_db)):
    g = groups.get_own(db, ctx, group_id)
    groups.remove_member(db, g, member_id)
    db.commit()
    return groups.group_out(db, g)


@router.post("/groups/{group_id}/join-link")
def group_join_link(group_id: uuid.UUID, ctx: PrivateCtx = Depends(private_ctx), db: OrmSession = Depends(get_db)):
    """«Byg gruppen selv»: ONE link the owner posts in an existing group chat from their own phone."""
    g = groups.get_own(db, ctx, group_id)
    _link, out = groups.create_link(db, ctx, g)
    db.commit()
    return out


@router.post("/groups/{group_id}/join-link/revoke")
def group_join_link_revoke(group_id: uuid.UUID, ctx: PrivateCtx = Depends(private_ctx),
                           db: OrmSession = Depends(get_db)):
    g = groups.get_own(db, ctx, group_id)
    groups.revoke_links(db, g)
    db.commit()
    return groups.group_out(db, g)


class GroupJoinIn(BaseModel):
    name: str = Field(default="", max_length=100)
    phone: str | None = Field(default=None, max_length=30)
    code: str | None = Field(default=None, max_length=10)


def optional_principal(request: Request, db: OrmSession = Depends(get_db),
                       authorization: str | None = Header(default=None)) -> Principal | None:
    if not authorization:
        return None
    try:
        return get_current_principal(request, db, authorization)
    except Unauthenticated:
        return None


@public_router.get("/group-invites/by-code/{code}")
def group_invite_preview(code: str, request: Request, db: OrmSession = Depends(get_db)):
    """Public: group name, owner's first name, member COUNT. Never names or numbers. Rate limited per IP."""
    _public_enabled()
    out = lookup_limits.guarded(db, request, lambda: groups.link_preview(db, code))
    db.commit()
    return out


@public_router.post("/group-invites/by-code/{code}/join")
def group_invite_join(code: str, body: GroupJoinIn, request: Request, db: OrmSession = Depends(get_db),
                      principal: Principal | None = Depends(optional_principal)):
    """Login optional. Without login: name, and a number only after an SMS code (first call: code_sent; then again
    with `code`). Max 50 new members per link per hour."""
    _public_enabled()
    out = lookup_limits.guarded(db, request, lambda: groups.join(db, code, principal=principal, name=body.name,
                                                                 phone=body.phone, sms_code=body.code))
    db.commit()
    return out


@router.get("/people/suggested")
def people_suggested(ctx: PrivateCtx = Depends(private_ctx), db: OrmSession = Depends(get_db)):
    return groups.suggested(db, ctx)


@router.post("/tasks/{task_id}/share-group")
def share_group(task_id: uuid.UUID, body: ShareGroupIn, ctx: PrivateCtx = Depends(private_ctx),
                db: OrmSession = Depends(get_db)):
    """People already on Dialogbot join in-app; the rest get SMS texts the user sends from their OWN phone."""
    out = groups.share(db, ctx, task_id, body.group_id, mode=body.mode, role=body.role, style=body.style)
    db.commit()
    return out


@router.get("/tasks/{task_id}/invite-status")
def invite_status(task_id: uuid.UUID, ctx: PrivateCtx = Depends(private_ctx), db: OrmSession = Depends(get_db)):
    t, m = sharing.access(db, task_id, ctx.user_id, min_role="owner")
    return groups.invite_status(db, ctx, t)


# --------------------------------------------------------------------------- add-ons and referrals

@router.get("/addons")
def addon_list(ctx: PrivateCtx = Depends(private_ctx), db: OrmSession = Depends(get_db)):
    return addons.catalog_out(db, ctx.ws_id)


@router.post("/addons/{key}/enable")
def addon_enable(key: str, ctx: PrivateCtx = Depends(private_ctx), db: OrmSession = Depends(get_db)):
    a = addons.enable(db, ctx.ws_id, key)
    db.commit()
    return addons.out(db, ctx.ws_id, a)


@router.post("/addons/{key}/disable")
def addon_disable(key: str, ctx: PrivateCtx = Depends(private_ctx), db: OrmSession = Depends(get_db)):
    """Data is kept; shared lists I own are paused (members cannot open them; invite links stop working)."""
    a = addons.disable(db, ctx.ws_id, key)
    db.commit()
    return addons.out(db, ctx.ws_id, a)


@router.post("/addons/{key}/invites")
def addon_invite(key: str, body: AddonInviteIn, ctx: PrivateCtx = Depends(private_ctx),
                 db: OrmSession = Depends(get_db)):
    """Generic invitation for any shareable add-on (same link, landing page and referral reward)."""
    inv, raw = invites.create(db, ctx, addon_key=key, resource_id=body.resource_id, mode=body.mode, role=body.role)
    out = invites.invite_out(db, inv, raw, ctx.user.display_name)
    db.commit()
    return out


@router.get("/referrals")
def referral_summary(ctx: PrivateCtx = Depends(private_ctx), db: OrmSession = Depends(get_db)):
    return referrals.summary(db, ctx)


@router.post("/referrals/link")
def referral_link(ctx: PrivateCtx = Depends(private_ctx), db: OrmSession = Depends(get_db)):
    """«Inviter venner»: a link to Dialogbot itself, with the same short link and suggested SMS text. ONE link per user:
    while it is valid for at least another week the same one comes back (Konto made a new invitation on every visit)."""
    out = invites.general_link(db, ctx)
    db.commit()
    return out


@operator_router.get("/growth")
def growth(days: int | None = Query(default=None, ge=1, le=3650), db: OrmSession = Depends(get_db),
           principal: Principal = Depends(operator)):
    return referrals.growth(db, days)


@operator_router.get("/business-referrals")
def business_referrals(days: int | None = Query(default=None, ge=1, le=3650), db: OrmSession = Depends(get_db),
                       principal: Principal = Depends(operator)):
    """The lead ledger (docs/sales/privat-revenue.md): per business, how often Privat users asked it for a quote through
    Dialogbot and how often they chose it – the sales argument «we sent you N customers». Business side only."""
    from datetime import timedelta

    from sqlalchemy import func, select

    from app.models import PrivateBusinessReferral as R
    from app.modules.privat import rules as _rules

    q = select(R.business_name, R.business_phone_e164, func.count().label("asked"),
               func.count().filter(R.status == "chosen").label("chosen"), func.max(R.created_at).label("last"))
    if days:
        q = q.where(R.created_at >= _rules.now() - timedelta(days=days))
    rows = db.execute(q.group_by(R.business_name, R.business_phone_e164)
                      .order_by(func.count().filter(R.status == "chosen").desc(), func.count().desc()).limit(500)).all()
    return {"items": [{"business_name": r.business_name, "phone": r.business_phone_e164, "asked": r.asked,
                       "chosen": r.chosen, "last_at": r.last.isoformat()} for r in rows]}


# --------------------------------------------------------------------------- chat

@router.get("/messages")
def list_messages(task_id: uuid.UUID | None = None, ctx: PrivateCtx = Depends(private_ctx),
                  db: OrmSession = Depends(get_db)):
    if task_id is not None:
        sharing.access(db, task_id, ctx.user_id)
    return [service.message_out(m) for m in service.messages(db, ctx, task_id)]


@router.post("/messages")
def post_message(body: MessageIn, response: Response, ctx: PrivateCtx = Depends(private_ctx),
                 db: OrmSession = Depends(get_db),
                 idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")):
    guard = IdempotencyGuard(db, scope_for(ctx.user_id, "privat.messages", ctx.ws_id), idempotency_key,
                             body.model_dump(mode="json"))
    if guard.replay:
        response.status_code = guard.replay[0]
        return guard.replay[1]
    msgs = chat.run(db, ctx, body.text, body.about_task_id)
    out = _chat_out(db, ctx, msgs)
    guard.store(200, out)
    db.commit()
    return out


@router.post("/messages/{message_id}/options/{option_id}")
def answer_option(message_id: uuid.UUID, option_id: str, ctx: PrivateCtx = Depends(private_ctx),
                  db: OrmSession = Depends(get_db)):
    msgs = chat.answer_option(db, ctx, message_id, option_id[:320])
    db.commit()
    return _chat_out(db, ctx, msgs)


# --------------------------------------------------------------------------- calls («Ring for mig»)

@router.post("/calls/{task_id}/approve")
def approve_call(task_id: uuid.UUID, body: ApproveIn, response: Response, ctx: PrivateCtx = Depends(private_ctx),
                 db: OrmSession = Depends(get_db),
                 idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")):
    guard = IdempotencyGuard(db, scope_for(ctx.user_id, "privat.calls.approve", ctx.ws_id), idempotency_key,
                             {"task_id": str(task_id), **body.model_dump(mode="json")})
    if guard.replay:
        response.status_code = guard.replay[0]
        return guard.replay[1]
    t = calls.approve(db, ctx, task_id, window=body.window, share_phone=body.share_phone,
                      at_next_open=body.at_next_open, confirm_business=body.confirm_business)
    out = service.task_out(db, t, ctx.user_id)
    guard.store(200, out)
    db.commit()
    return out


@router.post("/calls/{task_id}/decline")
def decline_call(task_id: uuid.UUID, ctx: PrivateCtx = Depends(private_ctx), db: OrmSession = Depends(get_db)):
    t = calls.decline(db, ctx, task_id)
    db.commit()
    return service.task_out(db, t, ctx.user_id)


@router.post("/calls/{task_id}/retry")
def retry_call(task_id: uuid.UUID, ctx: PrivateCtx = Depends(private_ctx), db: OrmSession = Depends(get_db)):
    t = calls.retry(db, ctx, task_id)
    db.commit()
    return service.task_out(db, t, ctx.user_id)


# --------------------------------------------------------------------------- business search and location

class LocationIn(BaseModel):
    city: str | None = Field(default=None, max_length=100)
    postcode: str | None = Field(default=None, max_length=10)
    lat: float | None = None
    lng: float | None = None


@router.get("/businesses/search")
def business_search(q: str = Query(min_length=1, max_length=120), lat: float | None = None, lng: float | None = None,
                    city: str | None = Query(default=None, max_length=100), ctx: PrivateCtx = Depends(private_ctx),
                    db: OrmSession = Depends(get_db)):
    """At most 3 businesses (Google Places; demo data without a key). 30 searches per user per hour (429).
    Show «Data fra Google» with results whose source is "google"."""
    addons.require(db, ctx.ws_id, "ring-for-mig")
    out = [{k: v for k, v in r.items() if k != "phone_kind"} for r in places.search(db, ctx, q, lat=lat, lng=lng,
                                                                                    city=city)]
    db.commit()
    return out


@router.patch("/me/location")
def set_location(body: LocationIn, ctx: PrivateCtx = Depends(private_ctx), db: OrmSession = Depends(get_db)):
    """Only what the user gives (city, postcode or the browser's position); used to find businesses near them."""
    places.set_location(db, ctx, city=body.city, postcode=body.postcode, lat=body.lat, lng=body.lng)
    db.commit()
    return service.balance_out(db, ctx)


class AssistantNameIn(BaseModel):
    name: str = Field(default="", max_length=40, description="Empty = the default «Peter»")
    pronoun: str | None = Field(default=None, max_length=4, description="han | hun | den; empty = han for Peter, den otherwise")


@router.patch("/me/assistant")
def set_assistant_name(body: AssistantNameIn, ctx: PrivateCtx = Depends(private_ctx), db: OrmSession = Depends(get_db)):
    """What the assistant is called in the app and the chat (calls and e-mails still say «Dialogbot»)."""
    from app.modules.privat import naming

    ctx.profile.assistant_name = naming.clean(body.name)
    ctx.profile.assistant_pronoun = naming.clean_pronoun(body.pronoun)
    db.commit()
    return service.balance_out(db, ctx)


# --------------------------------------------------------------------------- web push

class PushKeys(BaseModel):
    p256dh: str = Field(min_length=10, max_length=200)
    auth: str = Field(min_length=8, max_length=100)


class PushSubIn(BaseModel):
    endpoint: str = Field(min_length=10, max_length=2000)
    keys: PushKeys


class PushUnsubIn(BaseModel):
    endpoint: str = Field(min_length=10, max_length=2000)


@router.get("/push/public-key")
def push_public_key(ctx: PrivateCtx = Depends(private_ctx)):
    return {"public_key": push.public_key()}


@router.post("/push/subscriptions")
def push_subscribe(body: PushSubIn, request: Request, ctx: PrivateCtx = Depends(private_ctx),
                   db: OrmSession = Depends(get_db)):
    push.public_key()  # 501 push_not_configured without VAPID keys
    sub = push.subscribe(db, ctx.user_id, endpoint=body.endpoint, p256dh=body.keys.p256dh, auth=body.keys.auth,
                         user_agent=request.headers.get("user-agent"))
    db.commit()
    return {"id": str(sub.id)}


@router.delete("/push/subscriptions")
def push_unsubscribe(body: PushUnsubIn, ctx: PrivateCtx = Depends(private_ctx), db: OrmSession = Depends(get_db)):
    removed = push.unsubscribe(db, ctx.user_id, body.endpoint)
    db.commit()
    return {"removed": removed}


@router.post("/push/test")
def push_test(ctx: PrivateCtx = Depends(private_ctx), db: OrmSession = Depends(get_db)):
    """Sends «Det virker – du får besked her» to every subscription of the caller."""
    push.public_key()
    n = push.test(db, ctx.user_id)
    db.commit()
    return {"sent": n}


# --------------------------------------------------------------------------- phone and credits

@router.post("/phone/start")
def phone_start(body: PhoneStartIn, ctx: PrivateCtx = Depends(private_ctx), db: OrmSession = Depends(get_db)):
    phone.start(db, ctx, body.phone)
    db.commit()
    return {"sent": True}


@router.post("/phone/verify")
def phone_verify(body: PhoneVerifyIn, ctx: PrivateCtx = Depends(private_ctx), db: OrmSession = Depends(get_db)):
    phone.verify(db, ctx, body.code)
    db.commit()
    db.refresh(ctx.profile)
    return service.balance_out(db, ctx)


@router.post("/credits/checkout")
def credits_checkout(ctx: PrivateCtx = Depends(private_ctx), db: OrmSession = Depends(get_db)):
    """Stripe Checkout (mode=payment): 10 credits, 29 kr. incl. moms. Credits arrive with the webhook."""
    return {"url": payments.checkout(db, ctx)}

"""Privat: wishes with product details, group gifts and the wishlist's design (docs/privat-api.md «Ønsker, fællesgaver og
design»). Every route resolves the caller's own personal workspace and reaches a list only through membership
(sharing.access). Owner-only routes ask for min_role="owner"; the giver routes refuse the owner (group_gifts.py)."""
from __future__ import annotations

import uuid
from datetime import timedelta

from fastapi import APIRouter, Depends, Header, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session as OrmSession

from app.core.body import raw_body
from app.core.errors import ApiError, Conflict, NotFound, ValidationFailed
from app.core.idempotency import IdempotencyGuard, scope_for
from app.db import get_db
from app.models import AiUsage, PrivateBusinessSearch
from app.modules.privat import files, group_gifts, rules, service, sharing, wish_design, wish_images, wishes
from app.modules.privat.deps import PrivateCtx, private_ctx

router = APIRouter(prefix="/privat", tags=["privat-wishes"])

SEARCHES_PER_HOUR, LOOKUPS_PER_HOUR = 30, 60


class LookupRateLimited(ApiError):
    status_code = 429
    code = "rate_limited"


def _rate(db: OrmSession, ctx: PrivateCtx, limit: int) -> None:
    """Search and import fetch other sites for the user: a per-account ceiling (counted with the business searches'
    rows; nothing of the query is stored)."""
    n = db.scalar(select(func.count()).select_from(PrivateBusinessSearch).where(
        PrivateBusinessSearch.workspace_id == ctx.ws_id,
        PrivateBusinessSearch.created_at >= rules.now() - timedelta(hours=1))) or 0
    if n >= limit:
        raise LookupRateLimited("Du har hentet mange produkter den sidste time. Prøv igen lidt senere.")
    db.add(PrivateBusinessSearch(workspace_id=ctx.ws_id, created_at=rules.now()))
    db.flush()


class WishFields(BaseModel):
    note: str | None = Field(default=None, max_length=500)
    link: str | None = Field(default=None, max_length=2000)
    quantity: int | None = Field(default=None, ge=1, le=99)
    price_minor: int | None = Field(default=None, ge=0, le=10**10)
    currency: str | None = Field(default=None, max_length=3)
    price_source: str | None = Field(default=None, pattern="^(shop|user)$")
    price_fetched_at: str | None = Field(default=None, max_length=40)
    shop: str | None = Field(default=None, max_length=120)
    size: str | None = Field(default=None, max_length=80)
    color: str | None = Field(default=None, max_length=80)
    variant: str | None = Field(default=None, max_length=120)
    image_key: str | None = Field(default=None, max_length=200)
    image_origin: str | None = Field(default=None, pattern="^(shop|upload)$")
    details: dict | None = None
    group_gift_enabled: bool | None = None
    group_gift_target_minor: int | None = Field(default=None, ge=1, le=10**10)


class WishIn(WishFields):
    text: str = Field(min_length=1, max_length=300, description="Titel")


class WishPatch(WishFields):
    text: str | None = Field(default=None, min_length=1, max_length=300)


class ImportIn(BaseModel):
    link: str = Field(min_length=4, max_length=2000)


class PledgeIn(BaseModel):
    amount_minor: int = Field(ge=1, le=10**10, description="I valutaens mindste enhed (øre)")


class CoordinatorIn(BaseModel):
    action: str = Field(pattern="^(take|transfer|accept|decline|cancel_transfer|release)$")
    to: str | None = Field(default=None, max_length=40, description="user_ref fra participant_names (kun transfer)")


class BoughtIn(BaseModel):
    bought: bool = True


class CoverIn(BaseModel):
    key: str = Field(max_length=200)
    zoom: float = Field(default=1, ge=1, le=3)
    x: float = Field(default=50, ge=0, le=100)
    y: float = Field(default=50, ge=0, le=100)


class DesignBody(BaseModel):
    theme: str = Field(max_length=24)
    accent: str | None = Field(default=None, max_length=7)
    background: str | None = Field(default=None, max_length=7)
    text: str | None = Field(default=None, max_length=7)
    font: str | None = Field(default=None, max_length=16)
    decorations: bool | None = None
    subtitle: str | None = Field(default=None, max_length=200)
    date: str | None = Field(default=None, max_length=10)
    cover: CoverIn | None = None


class DesignIn(BaseModel):
    title: str | None = Field(default=None, max_length=300)
    design: DesignBody | None = Field(default=None, description="null = tilbage til standardtemaet (kun designet)")


def _checked(data: bytes) -> bytes:
    if len(data) > files.MAX_BYTES:
        raise ValidationFailed("Billedet er for stort (højst 6 MB)", field_errors=[{"field": "file"}])
    return data


def _out(db: OrmSession, ctx: PrivateCtx, task) -> dict:
    return service.task_out(db, task, ctx.user_id)


# --------------------------------------------------------------------------- adding a wish

@router.get("/wishes/search")
def wish_search(q: str = Query(min_length=2, max_length=120), ctx: PrivateCtx = Depends(private_ctx),
                db: OrmSession = Depends(get_db)):
    """«Søg efter produkt»: real product pages (web search + each page's own structured data). 503 search_unavailable
    when web search is not configured – then the web offers «Indsæt link» / «Opret selv». 30 a hour (429)."""
    if not wishes.search_available():
        raise wishes.SearchUnavailable("Produktsøgning er ikke sat op endnu. Indsæt et link, eller opret ønsket selv.")
    _rate(db, ctx, SEARCHES_PER_HOUR)
    db.commit()
    rows, completion = wishes.search(q, ctx.profile.location_city)
    if completion is not None:
        from app.modules.ai.provider import get_provider
        from app.modules.ai.service import fill_usage

        row = AiUsage(workspace_id=ctx.ws_id, user_id=ctx.user_id, purpose="privat_wish_search",
                      provider=get_provider().name, requested_model=completion.requested_model,
                      prompt_version="privat-wish-search-v1", knowledge_revision=0)
        db.add(fill_usage(row, completion))
        db.commit()
    return {"results": rows}


@router.post("/wishes/import")
def wish_import(body: ImportIn, ctx: PrivateCtx = Depends(private_ctx), db: OrmSession = Depends(get_db)):
    """«Indsæt link»: what the shop's page declares (title, image, price + currency, shop, variants), for the owner to
    check. `readable: false` keeps the link so the wish can still be saved by hand. Nothing is saved on the list."""
    _rate(db, ctx, LOOKUPS_PER_HOUR)
    db.commit()
    return wishes.import_link(ctx.ws_id, body.link)


@router.post("/wishes/images")
def wish_image(ctx: PrivateCtx = Depends(private_ctx), data: bytes = Depends(raw_body)):
    """The owner's own photo for a wish (raw JPEG/PNG/WebP body, ≤ 6 MB). Returns image_key for the wish form."""
    stored = wish_images.store(ctx.ws_id, _checked(data), "oensker")
    return {"image_key": stored["key"], "image": wish_images.urls(stored["key"])}


@router.post("/tasks/{task_id}/wishes")
def add_wish(task_id: uuid.UUID, body: WishIn, ctx: PrivateCtx = Depends(private_ctx),
             db: OrmSession = Depends(get_db)):
    t, m = sharing.access(db, task_id, ctx.user_id, lock=True)
    service.add_items(db, t, m, [body.text], wish=body.model_dump(exclude_unset=True) | {"text": body.text})
    db.commit()
    return _out(db, ctx, t)


@router.patch("/tasks/{task_id}/wishes/{item_id}")
def edit_wish(task_id: uuid.UUID, item_id: uuid.UUID, body: WishPatch, ctx: PrivateCtx = Depends(private_ctx),
              db: OrmSession = Depends(get_db)):
    t, m = sharing.access(db, task_id, ctx.user_id, lock=True)
    service.update_wish(db, t, m, item_id, body.model_dump(exclude_unset=True))
    db.commit()
    return _out(db, ctx, t)


# --------------------------------------------------------------------------- group gift (givers only)

@router.put("/tasks/{task_id}/items/{item_id}/gift/pledge")
def gift_pledge(task_id: uuid.UUID, item_id: uuid.UUID, body: PledgeIn, response: Response,
                ctx: PrivateCtx = Depends(private_ctx), db: OrmSession = Depends(get_db),
                idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")):
    """Join or change my pledge. Refused above what is left (409 pledge_exceeds_remaining, remaining_minor)."""
    guard = IdempotencyGuard(db, scope_for(ctx.user_id, "privat.gift.pledge", ctx.ws_id), idempotency_key,
                             {"task_id": str(task_id), "item_id": str(item_id), **body.model_dump()})
    if guard.replay:
        response.status_code = guard.replay[0]
        return guard.replay[1]
    t, m = sharing.access(db, task_id, ctx.user_id)
    group_gifts.pledge(db, t, m, item_id, body.amount_minor)
    out = _out(db, ctx, t)
    guard.store(200, out)
    db.commit()
    return out


@router.delete("/tasks/{task_id}/items/{item_id}/gift/pledge")
def gift_withdraw(task_id: uuid.UUID, item_id: uuid.UUID, ctx: PrivateCtx = Depends(private_ctx),
                  db: OrmSession = Depends(get_db)):
    t, m = sharing.access(db, task_id, ctx.user_id)
    group_gifts.withdraw(db, t, m, item_id)
    db.commit()
    return _out(db, ctx, t)


@router.post("/tasks/{task_id}/items/{item_id}/gift/coordinator")
def gift_coordinator(task_id: uuid.UUID, item_id: uuid.UUID, body: CoordinatorIn,
                     ctx: PrivateCtx = Depends(private_ctx), db: OrmSession = Depends(get_db)):
    t, m = sharing.access(db, task_id, ctx.user_id)
    group_gifts.coordinator(db, t, m, item_id, body.action, body.to)
    db.commit()
    return _out(db, ctx, t)


@router.post("/tasks/{task_id}/items/{item_id}/gift/bought")
def gift_bought(task_id: uuid.UUID, item_id: uuid.UUID, body: BoughtIn, ctx: PrivateCtx = Depends(private_ctx),
                db: OrmSession = Depends(get_db)):
    t, m = sharing.access(db, task_id, ctx.user_id)
    group_gifts.mark_bought(db, t, m, item_id, body.bought)
    db.commit()
    return _out(db, ctx, t)


# --------------------------------------------------------------------------- design (owner only)

@router.put("/tasks/{task_id}/design")
def save_design(task_id: uuid.UUID, body: DesignIn, ctx: PrivateCtx = Depends(private_ctx),
                db: OrmSession = Depends(get_db)):
    """«Gem design». design null = «Nulstil til tema» saved: only the look changes, never the wishes or members."""
    t, _m = sharing.access(db, task_id, ctx.user_id, min_role="owner", lock=True)
    wish_design.save(db, t, body.design.model_dump() if body.design else None, title=body.title)
    db.commit()
    return _out(db, ctx, t)


@router.post("/tasks/{task_id}/design/cover")
def upload_cover(task_id: uuid.UUID, ctx: PrivateCtx = Depends(private_ctx), db: OrmSession = Depends(get_db),
                 data: bytes = Depends(raw_body)):
    """Upload a cover (raw image body). Not applied until «Gem design» sends its key."""
    t, _m = sharing.access(db, task_id, ctx.user_id, min_role="owner")
    if t.list_type != "wishlist":
        raise Conflict("Kun ønskelister har et design", code="not_a_wishlist")
    stored = wish_images.store(t.workspace_id, _checked(data), "cover")
    return {"key": stored["key"], "image": wish_images.urls(stored["key"]), "width": stored["width"],
            "height": stored["height"]}


# --------------------------------------------------------------------------- local images (dev/test only)

@router.get("/dev-files")
def dev_file(key: str = Query(max_length=200), exp: int = Query(), sig: str = Query(max_length=64)):
    """Without Supabase (dev/test) files.sign() returns local:// links; the web maps them here. Never in prod/staging."""
    import hashlib
    import hmac
    import time

    from app.config import get_settings

    s = get_settings()
    if s.app_env in ("staging", "prod") or files._remote() or not files._KEY.match(key) or exp < time.time():
        raise NotFound("Findes ikke")
    want = hmac.new(s.secret_key.encode(), f"{key}:{exp}".encode(), hashlib.sha256).hexdigest()[:32]
    p = files._local(key)
    if not hmac.compare_digest(want, sig) or not p.exists():
        raise NotFound("Findes ikke")
    ext = key.rsplit(".", 1)[1]
    return Response(p.read_bytes(), media_type={"jpg": "image/jpeg", "png": "image/png", "webp": "image/webp",
                                                "heic": "image/heic"}[ext], headers={"cache-control": "private, max-age=300"})

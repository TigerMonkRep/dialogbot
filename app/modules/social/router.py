"""Operator API for Dialogbot's own social posts, and the public image URLs the platforms download from.

Only platform operators (scripts/grant_operator.py) may use /operator/social. The image route is public by design:
Meta and TikTok fetch the pictures themselves, so the (random, unguessable) id in the URL is the only key and the
pictures contain nothing but the post's own slide text.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from app.core.audit import record_audit
from app.core.auth import Principal
from app.core.errors import Conflict, NotFound, NotImplementedYet, ValidationFailed
from app.db import get_db
from app.models import SocialMedia, SocialPost, SocialProspect
from app.modules.social import insights, prospects, publishers, service
from app.modules.voices.operator_router import operator

router = APIRouter(prefix="/operator/social", tags=["social-operator"])
public_router = APIRouter(prefix="/social", tags=["social"])

Platform = Literal["facebook", "instagram", "tiktok"]


def _out(db: OrmSession, p: SocialPost) -> dict:
    ids = db.scalars(select(SocialMedia.id).where(SocialMedia.post_id == p.id).order_by(SocialMedia.position)).all()
    return {"id": str(p.id), "platform": p.platform, "status": p.status, "topic": p.topic,
            "slot_date": p.slot_date.isoformat(), "scheduled_for": p.scheduled_for.isoformat(), "caption": p.caption,
            "hashtags": p.hashtags, "slides": p.slides, "link": p.link, "generator": p.generator,
            "generator_model": p.generator_model, "external_id": p.external_id, "external_url": p.external_url,
            "attempts": p.attempts, "last_error": p.last_error, "approved_by": str(p.approved_by_user_id) if p.approved_by_user_id else None,
            "published_at": p.published_at.isoformat() if p.published_at else None,
            "metrics": p.metrics, "metrics_at": p.metrics_at.isoformat() if p.metrics_at else None,
            "images": [publishers.media_url(i) for i in ids]}


@router.get("/dashboard")
def dashboard(days: int = Query(default=30, ge=7, le=365), _: Principal = Depends(operator),
              db: OrmSession = Depends(get_db)):
    """One call for the operator page: followers per platform (today + curve + 7/30-day change), posts waiting for
    approval, scheduled, recently published with engagement, and failed."""
    d = service.dashboard(db, days=days)
    return {**d, "pending": [_out(db, p) for p in d["pending"]], "scheduled": [_out(db, p) for p in d["scheduled"]],
            "recent": [_out(db, p) for p in d["recent"]], "failed": [_out(db, p) for p in d["failed"]]}


@router.post("/metrics/refresh")
def refresh_metrics(_: Principal = Depends(operator), db: OrmSession = Depends(get_db)):
    """Read today's profile numbers and the engagement of recent posts from the platforms right now."""
    return insights.refresh_all(db, force=True)


# --- profiles to follow (found by the system, acted on by a person) ---------------------------------------------------

@router.get("/prospects")
def list_prospects(status: Literal["new", "done", "skipped"] | None = None, limit: int = Query(default=60, ge=1, le=200),
                   _: Principal = Depends(operator), db: OrmSession = Depends(get_db)):
    """Companies in Dialogbot's industries with their Facebook/Instagram/TikTok links, newest batch first."""
    q = select(SocialProspect).order_by(SocialProspect.found_on.desc(), SocialProspect.name).limit(limit)
    if status:
        q = q.where(SocialProspect.status == status)
    return {"items": [prospects.to_dict(p) for p in db.scalars(q).all()], "enabled": prospects.configured(),
            "industries": {k: v["label"] for k, v in prospects.INDUSTRIES.items()}}


class DiscoverIn(BaseModel):
    industry: Literal["haandvaerkere", "klinikker", "frisoerer", "autovaerksteder", "raadgivere", "restauranter"] | None = None
    limit: int = Field(default=prospects.BATCH_SIZE, ge=1, le=50)


@router.post("/prospects/discover")
def discover_prospects(body: DiscoverIn, _: Principal = Depends(operator), db: OrmSession = Depends(get_db)):
    """Make a batch now (the worker makes one every morning by itself). Needs CVR access; answers 501 without it."""
    if not prospects.configured():
        raise NotImplementedYet("Kræver adgang til CVR-registret (CVR_USERNAME/CVR_PASSWORD)", code="cvr_not_configured")
    added = prospects.discover(db, industry=body.industry, limit=body.limit)
    return {"created": [prospects.to_dict(p) for p in added]}


class ProspectActIn(BaseModel):
    platforms: list[Platform] = Field(default_factory=list, description="Where the operator followed/commented")
    note: str | None = Field(default=None, max_length=500)


def _prospect(db: OrmSession, prospect_id: uuid.UUID) -> SocialProspect:
    p = db.get(SocialProspect, prospect_id)
    if p is None:
        raise NotFound("Virksomheden findes ikke på listen")
    return p


@router.post("/prospects/{prospect_id}/done")
def prospect_done(prospect_id: uuid.UUID, body: ProspectActIn, request: Request, principal: Principal = Depends(operator),
                  db: OrmSession = Depends(get_db)):
    """The operator followed/commented from Dialogbot's profiles — record it so the company is never suggested again."""
    p = _prospect(db, prospect_id)
    if p.status != "new":
        raise Conflict("Virksomheden er allerede behandlet", code="prospect_not_new")
    p.status, p.acted_platforms, p.note = "done", list(dict.fromkeys(body.platforms)), body.note
    p.acted_by_user_id, p.acted_at = principal.user.id, datetime.now(timezone.utc)
    record_audit(db, workspace_id=None, actor_user_id=principal.user.id, action="social.prospect_done",
                 object_type="social_prospect", object_id=p.id, request_id=request.state.request_id,
                 after={"platforms": p.acted_platforms})
    db.commit()
    return prospects.to_dict(p)


@router.post("/prospects/{prospect_id}/skip")
def prospect_skip(prospect_id: uuid.UUID, body: ProspectActIn, request: Request, principal: Principal = Depends(operator),
                  db: OrmSession = Depends(get_db)):
    p = _prospect(db, prospect_id)
    if p.status != "new":
        raise Conflict("Virksomheden er allerede behandlet", code="prospect_not_new")
    p.status, p.note = "skipped", body.note
    p.acted_by_user_id, p.acted_at = principal.user.id, datetime.now(timezone.utc)
    record_audit(db, workspace_id=None, actor_user_id=principal.user.id, action="social.prospect_skip",
                 object_type="social_prospect", object_id=p.id, request_id=request.state.request_id)
    db.commit()
    return prospects.to_dict(p)


@router.get("")
def overview(_: Principal = Depends(operator), db: OrmSession = Depends(get_db)):
    """Provider, which platforms are connected, the schedule and counts per platform and status."""
    return service.status_overview(db)


@router.get("/posts")
def list_posts(status: str | None = Query(default=None, max_length=12), platform: Platform | None = None,
               limit: int = Query(default=30, ge=1, le=100), _: Principal = Depends(operator),
               db: OrmSession = Depends(get_db)):
    q = select(SocialPost).order_by(SocialPost.scheduled_for.desc()).limit(limit)
    if status:
        q = q.where(SocialPost.status == status)
    if platform:
        q = q.where(SocialPost.platform == platform)
    return {"items": [_out(db, p) for p in db.scalars(q)]}


@router.get("/posts/{post_id}")
def get_post(post_id: uuid.UUID, _: Principal = Depends(operator), db: OrmSession = Depends(get_db)):
    return _out(db, service.get_post(db, post_id))


class PlanIn(BaseModel):
    day: date | None = Field(default=None, description="Plan this day; omit to run the normal rolling plan")
    topic: str | None = Field(default=None, max_length=40)
    platforms: list[Platform] | None = None


@router.post("/plan")
def plan_now(body: PlanIn, _: Principal = Depends(operator), db: OrmSession = Depends(get_db)):
    """Create the missing posts now (for one day and topic, or for the whole planning window)."""
    if body.day:
        created = service.plan_day(db, body.day, topic_key=body.topic, platforms=body.platforms)
    elif body.topic or body.platforms:
        raise ValidationFailed("Angiv en dag sammen med emne eller platforme")
    else:
        created = service.plan(db)
    return {"created": [_out(db, p) for p in created]}


class CaptionIn(BaseModel):
    caption: str = Field(min_length=1, max_length=4000)


@router.patch("/posts/{post_id}")
def edit_post(post_id: uuid.UUID, body: CaptionIn, request: Request, principal: Principal = Depends(operator),
              db: OrmSession = Depends(get_db)):
    p = service.edit_caption(db, service.get_post(db, post_id), body.caption, principal.user.id, request.state.request_id)
    return _out(db, p)


@router.post("/posts/{post_id}/approve")
def approve_post(post_id: uuid.UUID, request: Request, principal: Principal = Depends(operator),
                 db: OrmSession = Depends(get_db)):
    return _out(db, service.approve(db, service.get_post(db, post_id), principal.user.id, request.state.request_id))


@router.post("/posts/{post_id}/cancel")
def cancel_post(post_id: uuid.UUID, request: Request, principal: Principal = Depends(operator),
                db: OrmSession = Depends(get_db)):
    return _out(db, service.cancel(db, service.get_post(db, post_id), principal.user.id, request.state.request_id))


@router.post("/posts/{post_id}/publish-now")
def publish_post_now(post_id: uuid.UUID, request: Request, principal: Principal = Depends(operator),
                     db: OrmSession = Depends(get_db)):
    """Post immediately (may take up to a minute while Instagram processes the images). For a failed post, check the
    profile first: after an 'uncertain' error the post may already be out."""
    return _out(db, service.publish_now(db, service.get_post(db, post_id), principal.user.id, request.state.request_id))


@public_router.get("/media/{filename}")
def media(filename: str, db: OrmSession = Depends(get_db)):
    stem, _, ext = filename.rpartition(".")
    try:
        media_id = uuid.UUID(stem)
    except ValueError:
        raise NotFound("Billedet findes ikke") from None
    m = db.get(SocialMedia, media_id) if ext == "jpg" else None
    if m is None:
        raise NotFound("Billedet findes ikke")
    return Response(m.data, media_type="image/jpeg", headers={"Cache-Control": "public, max-age=86400, immutable"})

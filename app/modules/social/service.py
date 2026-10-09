"""Planning and publishing of Dialogbot's own social posts.

The worker calls `run_due` every minute (app/worker/runner.py):
1. `plan` makes sure that, for every posting weekday in the next SOCIAL_PLAN_DAYS_AHEAD days, each connected platform
   has a post: one topic per day (the one used longest ago), three different posts, images rendered and stored.
   Posts wait as `scheduled` (or `draft` when SOCIAL_REQUIRE_APPROVAL=true) so there is time to look at them.
2. `publish_due` posts what is due. The row is set to `publishing` and committed BEFORE the platform is called; a crash
   in between is reported as uncertain after 30 minutes instead of being retried, because a duplicate public post is
   worse than a missed one. Errors the platform reports before creating anything are retried (5 min, then 30 min).

Only platforms that are switched on (SOCIAL_PLATFORMS) and configured get posts; with SOCIAL_PROVIDER=none nothing at
all happens.
"""
from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import structlog
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session as OrmSession

from app.config import get_settings
from app.core.audit import record_audit
from app.core.errors import Conflict, NotFound, ValidationFailed
from app.models import SocialAccountSnapshot, SocialMedia, SocialPost, SocialProspect
from app.modules.social import content, publishers, render
from app.modules.social.publishers import PublishError
from app.modules.social.topics import TOPICS, TOPICS_BY_KEY, Topic

log = structlog.get_logger("dialogbot.social")

TZ = ZoneInfo("Europe/Copenhagen")
# Local time each platform posts: Facebook in the morning coffee break, Instagram at lunch, TikTok in the evening.
SLOT_TIMES = {"facebook": time(9, 30), "instagram": time(12, 15), "tiktok": time(19, 0)}
PLAN_LOCK_KEY = 7301
MAX_ATTEMPTS = 3
RETRY_AFTER = (timedelta(minutes=5), timedelta(minutes=30))
STALE_PUBLISHING = timedelta(minutes=30)
ACTIVE = ("draft", "scheduled", "publishing", "published", "failed")


def _now() -> datetime:
    return datetime.now(UTC)


def posting_weekdays() -> set[int]:
    return {int(x) for x in get_settings().social_weekdays.split(",") if x.strip().isdigit() and 0 <= int(x) <= 6}


def slot_time(day: date, platform: str) -> datetime:
    return datetime.combine(day, SLOT_TIMES[platform], tzinfo=TZ).astimezone(UTC)


# --- planning ---------------------------------------------------------------------------------------------------------

def next_topic(db: OrmSession) -> Topic:
    """The topic used longest ago (never used first); ties follow the order in topics.py."""
    last = dict(db.execute(select(SocialPost.topic, func.max(SocialPost.slot_date)).group_by(SocialPost.topic)).all())
    return min(TOPICS, key=lambda t: (last.get(t.key) or date.min, TOPICS.index(t)))


def _recent_hooks(db: OrmSession, n: int = 8) -> list[str]:
    rows = db.scalars(select(SocialPost).order_by(SocialPost.created_at.desc()).limit(n * 3)).all()
    seen: list[str] = []
    for r in rows:
        if r.slides and r.slides[0].get("title") not in seen:
            seen.append(r.slides[0]["title"])
    return seen[:n]


def _store_media(db: OrmSession, post: SocialPost) -> None:
    for i, (data, w, h) in enumerate(render.render_post(post.platform, post.slides)):
        db.add(SocialMedia(post_id=post.id, position=i, width=w, height=h, data=data,
                           sha256=hashlib.sha256(data).hexdigest()))


def create_post(db: OrmSession, day: date, topic: Topic, draft: content.Draft, *, extra: bool = False,
                scheduled_for: datetime | None = None, status: str | None = None) -> SocialPost:
    s = get_settings()
    post = SocialPost(platform=draft.platform, slot_date=day, scheduled_for=scheduled_for or slot_time(day, draft.platform),
                      status=status or ("draft" if s.social_require_approval else "scheduled"), topic=topic.key,
                      extra=extra, group_key=f"{day.isoformat()}:{topic.key}{':extra' if extra else ''}",
                      caption=draft.caption, hashtags=draft.hashtags,
                      slides=draft.slides, link=draft.link, generator=draft.generator, generator_model=draft.model)
    db.add(post)
    db.flush()
    _store_media(db, post)
    db.flush()
    return post


def plan_day(db: OrmSession, day: date, *, topic_key: str | None = None, platforms: list[str] | None = None,
             now: datetime | None = None, past_ok: bool = False, respect_cancelled: bool = False) -> list[SocialPost]:
    """Create the missing posts for one day. Existing live posts are left alone; the day's topic is shared.
    `respect_cancelled`: the rolling plan must not undo an operator's cancel; an explicit plan request may."""
    now = now or _now()
    # One planner per day at a time (until the commit below): two workers must not both ask the AI for the same day.
    if not db.scalar(text("select pg_try_advisory_xact_lock(:a, :b)"), {"a": PLAN_LOCK_KEY, "b": day.toordinal()}):
        return []
    wanted = [p for p in (platforms or publishers.active_platforms(db)) if publishers.get_publisher(db, p)]
    statuses = (*ACTIVE, "cancelled") if respect_cancelled else ACTIVE
    taken = {p.platform: p for p in db.scalars(select(SocialPost).where(SocialPost.slot_date == day,
                                                                         SocialPost.status.in_(statuses),
                                                                         SocialPost.extra.is_(False)))}
    missing = [p for p in wanted if p not in taken and (past_ok or slot_time(day, p) > now)]
    if not missing:
        db.rollback()
        return []
    if topic_key:
        topic = TOPICS_BY_KEY.get(topic_key)
        if topic is None:
            raise ValidationFailed(f"Ukendt emne: {topic_key}")
    elif taken:
        topic = TOPICS_BY_KEY.get(next(iter(taken.values())).topic) or next_topic(db)
    else:
        topic = next_topic(db)
    drafts = content.generate(db, topic, tuple(missing), _recent_hooks(db))
    out = []
    for d in drafts:
        try:
            with db.begin_nested():
                out.append(create_post(db, day, topic, d))
        except Exception as e:  # noqa: BLE001 - one broken platform (or a lost race on the slot) must not block the others
            log.warning("social.plan_failed", platform=d.platform, day=day.isoformat(), error=f"{type(e).__name__}: {e}")
    db.commit()
    for p in out:
        log.info("social.planned", platform=p.platform, day=day.isoformat(), topic=topic.key, generator=p.generator,
                 status=p.status)
    return out


def create_extra(db: OrmSession, *, day: date | None = None, topic_key: str | None = None,
                 platforms: list[str] | None = None, at: datetime | None = None,
                 now: datetime | None = None) -> list[SocialPost]:
    """Operator button "Generér nye opslag": fresh drafts on top of the daily plan — for today or any later day, on
    any topic, for the chosen platforms — regardless of what the day already has. Always drafts: the operator
    reads them and presses Godkend or Post nu. `at` is when they should go out once approved (default: in ten
    minutes, so "approve → out" is the normal path); a time more than SOCIAL_MAX_LATE_MINUTES in the past would be
    skipped by the worker, so it is clamped to now."""
    now = now or _now()
    day = day or now.astimezone(TZ).date()
    if day < now.astimezone(TZ).date():
        raise ValidationFailed("Dagen er allerede gået", field_errors=[{"field": "day"}])
    wanted = [p for p in (platforms or publishers.active_platforms(db)) if publishers.get_publisher(db, p)]
    if not wanted:
        raise ValidationFailed("Ingen af de valgte platforme er forbundet", field_errors=[{"field": "platforms"}])
    topic = TOPICS_BY_KEY.get(topic_key) if topic_key else next_topic(db)
    if topic is None:
        raise ValidationFailed(f"Ukendt emne: {topic_key}", field_errors=[{"field": "topic"}])
    when = max(at, now) if at else now + timedelta(minutes=10)
    if when.astimezone(TZ).date() != day:
        when = max(slot_time(day, wanted[0]), now)
    drafts = content.generate(db, topic, tuple(wanted), _recent_hooks(db))
    out = []
    for d in drafts:
        try:
            with db.begin_nested():
                out.append(create_post(db, day, topic, d, extra=True, scheduled_for=when, status="draft"))
        except Exception as e:  # noqa: BLE001 - one broken platform must not block the others
            log.warning("social.extra_failed", platform=d.platform, day=day.isoformat(), error=f"{type(e).__name__}: {e}")
    db.commit()
    for p in out:
        log.info("social.extra_planned", platform=p.platform, day=day.isoformat(), topic=topic.key, generator=p.generator)
    return out


def plan(db: OrmSession, now: datetime | None = None) -> list[SocialPost]:
    s = get_settings()
    if s.social_provider == "none" or not publishers.active_platforms(db):
        return []
    now = now or _now()
    today = now.astimezone(TZ).date()
    out: list[SocialPost] = []
    for offset in range(0, max(0, s.social_plan_days_ahead) + 1):
        day = today + timedelta(days=offset)
        if day.weekday() in posting_weekdays():
            out += plan_day(db, day, now=now, respect_cancelled=True)
    return out


# --- publishing -------------------------------------------------------------------------------------------------------

def _image_urls(db: OrmSession, post: SocialPost) -> list[str]:
    ids = db.scalars(select(SocialMedia.id).where(SocialMedia.post_id == post.id).order_by(SocialMedia.position)).all()
    return [publishers.media_url(i) for i in ids]


def _claim(db: OrmSession, now: datetime, platforms: list[str]) -> SocialPost | None:
    return db.scalar(
        select(SocialPost)
        .where(SocialPost.status == "scheduled", SocialPost.platform.in_(platforms), SocialPost.scheduled_for <= now,
               (SocialPost.next_attempt_at.is_(None)) | (SocialPost.next_attempt_at <= now))
        .order_by(SocialPost.scheduled_for).limit(1).with_for_update(skip_locked=True))


def publish_one(db: OrmSession, post: SocialPost, now: datetime | None = None) -> SocialPost:
    """Post one scheduled post now. The state is committed before and after the platform call."""
    now = now or _now()
    publisher = publishers.get_publisher(db, post.platform)
    if publisher is None:
        raise Conflict(f"{post.platform} er ikke forbundet eller slået til", code="social_platform_unavailable")
    urls = _image_urls(db, post)
    if not urls:
        raise Conflict("Opslaget har ingen billeder", code="social_no_media")
    if get_settings().social_provider == "live" and not get_settings().public_base_url.startswith("https://"):
        raise Conflict("PUBLIC_BASE_URL skal være en offentlig https-adresse, så platformene kan hente billederne",
                       code="social_public_url")
    post.status, post.attempts, post.next_attempt_at = "publishing", post.attempts + 1, None
    db.commit()  # from here on a crash means "uncertain", never "post it again"
    try:
        res = publisher.publish(db, post, urls)
    except PublishError as e:
        db.rollback()
        post = db.get(SocialPost, post.id)
        retry = e.retryable and post.attempts < MAX_ATTEMPTS
        post.last_error = str(e)
        if retry:
            post.status, post.next_attempt_at = "scheduled", now + RETRY_AFTER[min(post.attempts, len(RETRY_AFTER)) - 1]
        else:
            post.status = "failed"
        log.warning("social.publish_failed", platform=post.platform, post_id=str(post.id), retry=retry, error=str(e))
        db.commit()
        return post
    except Exception as e:  # noqa: BLE001 - after an unknown error the post may exist; do not retry blindly
        db.rollback()
        post = db.get(SocialPost, post.id)
        post.status, post.last_error = "failed", f"Uventet fejl ({type(e).__name__}) – tjek profilen, før der postes igen"
        log.error("social.publish_crashed", platform=post.platform, post_id=str(post.id), error=type(e).__name__)
        db.commit()
        return post
    post = db.get(SocialPost, post.id)
    post.status, post.external_id, post.external_url = "published", res.external_id, res.url
    post.published_at, post.last_error, post.next_attempt_at = _now(), res.note, None
    db.commit()
    log.info("social.published", platform=post.platform, post_id=str(post.id), external_id=res.external_id)
    return post


def publish_due(db: OrmSession, now: datetime | None = None, limit: int = 10) -> int:
    now = now or _now()
    stale = db.scalars(select(SocialPost).where(SocialPost.status == "publishing",
                                                SocialPost.updated_at < now - STALE_PUBLISHING)).all()
    for p in stale:
        p.status = "failed"
        p.last_error = "Usikkert: opslaget blev sendt, men svaret kom aldrig tilbage. Tjek profilen, før du prøver igen."
        log.error("social.publish_uncertain", platform=p.platform, post_id=str(p.id))
    if stale:
        db.commit()
    max_late = timedelta(minutes=get_settings().social_max_late_minutes)
    expired = db.scalars(select(SocialPost).where(SocialPost.status == "draft",
                                                  SocialPost.scheduled_for < now - max_late)).all()
    for p in expired:
        p.status, p.last_error = "skipped", "Ikke godkendt, før tidspunktet var overskredet"
    if expired:
        db.commit()
    done = 0
    platforms = publishers.active_platforms(db)
    for _ in range(limit if platforms else 0):
        post = _claim(db, now, platforms)
        if post is None:
            break
        if now - post.scheduled_for > max_late:
            post.status, post.last_error = "skipped", "Tidspunktet var overskredet, da workeren nåede det"
            db.commit()
            continue
        publish_one(db, post, now)
        done += 1
    return done


MEDIA_KEPT_DAYS = 45


def prune_media(db: OrmSession, now: datetime | None = None) -> int:
    """The platforms have long since fetched the images of finished posts; free the database space."""
    cutoff = (now or _now()) - timedelta(days=MEDIA_KEPT_DAYS)
    done = select(SocialPost.id).where(SocialPost.status.in_(("published", "failed", "skipped", "cancelled")),
                                       SocialPost.updated_at < cutoff)
    n = db.query(SocialMedia).filter(SocialMedia.post_id.in_(done)).delete(synchronize_session=False)
    db.commit()
    return n


def run_due(db: OrmSession) -> int:
    """Worker entry point (every minute): plan ahead, then post what is due. Returns the number of posts attempted."""
    if get_settings().social_provider == "none":
        return 0
    try:
        plan(db)
    except Exception as e:  # noqa: BLE001 - planning trouble must not stop publishing
        db.rollback()
        log.warning("social.plan_error", error=f"{type(e).__name__}: {e}")
    n = publish_due(db)
    now = _now()
    if now.minute == 0:  # housekeeping once an hour is plenty
        prune_media(db)
    if now.minute == 7:  # dashboard numbers: today's follower snapshot + stale engagement, once an hour
        from app.modules.social import insights

        insights.refresh_all(db, now=now)
    if now.minute == 13:  # the day's "profiles to follow" batch (prospects.discover_if_due makes at most one a day)
        from app.modules.social import prospects

        try:
            prospects.discover_if_due(db, now=now)
        except Exception as e:  # noqa: BLE001 - CVR or a website misbehaving must not stop publishing
            db.rollback()
            log.warning("social.prospects_error", error=f"{type(e).__name__}: {e}")
    return n


# --- operator actions ---------------------------------------------------------------------------------------------------

def get_post(db: OrmSession, post_id: uuid.UUID) -> SocialPost:
    post = db.get(SocialPost, post_id)
    if post is None:
        raise NotFound("Opslaget findes ikke")
    return post


def approve(db: OrmSession, post: SocialPost, user_id: uuid.UUID, request_id: str | None = None) -> SocialPost:
    if post.status != "draft":
        raise Conflict("Kun kladder kan godkendes", code="social_not_draft")
    post.status, post.approved_by_user_id = "scheduled", user_id
    record_audit(db, workspace_id=None, actor_user_id=user_id, action="social.approve", object_type="social_post",
                 object_id=post.id, request_id=request_id)
    db.commit()
    return post


def cancel(db: OrmSession, post: SocialPost, user_id: uuid.UUID, request_id: str | None = None) -> SocialPost:
    if post.status not in ("draft", "scheduled", "failed"):
        raise Conflict("Opslaget kan ikke annulleres i den tilstand", code="social_not_cancellable")
    post.status = "cancelled"
    record_audit(db, workspace_id=None, actor_user_id=user_id, action="social.cancel", object_type="social_post",
                 object_id=post.id, request_id=request_id)
    db.commit()
    return post


def edit_caption(db: OrmSession, post: SocialPost, caption: str, user_id: uuid.UUID, request_id: str | None = None):
    if post.status not in ("draft", "scheduled"):
        raise Conflict("Teksten kan kun rettes, før opslaget går ud", code="social_not_editable")
    limit = {"facebook": 2000, "instagram": 2200, "tiktok": 4000}[post.platform]
    caption = caption.strip()
    if not caption or len(caption) > limit:
        raise ValidationFailed(f"Teksten skal være 1-{limit} tegn")
    post.caption = caption
    record_audit(db, workspace_id=None, actor_user_id=user_id, action="social.edit", object_type="social_post",
                 object_id=post.id, request_id=request_id)
    db.commit()
    return post


def publish_now(db: OrmSession, post: SocialPost, user_id: uuid.UUID, request_id: str | None = None) -> SocialPost:
    """Post immediately. A failed post may be retried this way once the operator has checked the profile."""
    if post.status not in ("draft", "scheduled", "failed"):
        raise Conflict("Opslaget kan ikke sendes i den tilstand", code="social_not_postable")
    if post.status == "draft":
        post.approved_by_user_id = user_id
    post.status, post.attempts = "scheduled", 0
    record_audit(db, workspace_id=None, actor_user_id=user_id, action="social.publish_now", object_type="social_post",
                 object_id=post.id, request_id=request_id)
    db.commit()
    return publish_one(db, post)


def status_overview(db: OrmSession) -> dict:
    s = get_settings()
    configured = publishers.live_configured(db) if s.social_provider == "live" else {}
    counts = db.execute(select(SocialPost.platform, SocialPost.status, func.count()).group_by(
        SocialPost.platform, SocialPost.status)).all()
    return {
        "provider": s.social_provider, "require_approval": s.social_require_approval,
        "weekdays": sorted(posting_weekdays()), "plan_days_ahead": s.social_plan_days_ahead,
        "slot_times": {p: t.strftime("%H:%M") for p, t in SLOT_TIMES.items()},
        "platforms": [{"platform": p, "enabled": p in publishers.enabled_platforms(),
                       "connected": publishers.get_publisher(db, p) is not None,
                       "configured": configured.get(p)} for p in ("facebook", "instagram", "tiktok")],
        "counts": [{"platform": p, "status": st, "count": n} for p, st, n in counts],
        "topics": [t.key for t in TOPICS],
    }


# --- operator dashboard ---------------------------------------------------------------------------------------------------

def dashboard(db: OrmSession, *, days: int = 30, now: datetime | None = None) -> dict:
    """Everything the operator page shows in one call: follower curve and deltas per platform, the posts waiting for
    approval, what is scheduled, what went out lately (with engagement) and what failed."""
    now = now or _now()
    today = now.astimezone(TZ).date()
    since = today - timedelta(days=days)
    # load a month more than the curve shows, so the 30-day change can be computed at the start of the window
    snaps = db.scalars(select(SocialAccountSnapshot).where(SocialAccountSnapshot.captured_on >= since - timedelta(days=31))
                       .order_by(SocialAccountSnapshot.platform, SocialAccountSnapshot.captured_on)).all()
    by_platform: dict[str, list[SocialAccountSnapshot]] = {}
    for sn in snaps:
        by_platform.setdefault(sn.platform, []).append(sn)

    def _delta(rows: list[SocialAccountSnapshot], back: int) -> int | None:
        with_numbers = [r for r in rows if r.followers is not None]
        if not with_numbers:
            return None
        latest = with_numbers[-1]
        target = latest.captured_on - timedelta(days=back)
        older = [r for r in with_numbers if r.captured_on <= target]
        if not older:
            return None
        return latest.followers - older[-1].followers

    overview = status_overview(db)
    platforms = []
    for pl in overview["platforms"]:
        rows = by_platform.get(pl["platform"], [])
        latest = next((r for r in reversed(rows) if r.followers is not None), None)
        last_row = rows[-1] if rows else None
        platforms.append({**pl,
                          "followers": latest.followers if latest else None,
                          "following": latest.following if latest else None,
                          "posts": latest.posts if latest else None,
                          "likes": latest.likes if latest else None,
                          "captured_on": latest.captured_on.isoformat() if latest else None,
                          "delta_7d": _delta(rows, 7), "delta_30d": _delta(rows, 30),
                          "series": [{"date": r.captured_on.isoformat(), "followers": r.followers}
                                     for r in rows if r.captured_on >= since],
                          "error": (last_row.raw or {}).get("error") if last_row and last_row.followers is None else None})

    def _posts(where, order, limit):
        return db.scalars(select(SocialPost).where(*where).order_by(order).limit(limit)).all()

    pending = _posts([SocialPost.status == "draft"], SocialPost.scheduled_for.asc(), 60)
    scheduled = _posts([SocialPost.status.in_(("scheduled", "publishing"))], SocialPost.scheduled_for.asc(), 60)
    recent = _posts([SocialPost.status == "published", SocialPost.published_at >= now - timedelta(days=days)],
                    SocialPost.published_at.desc(), 90)
    failed = _posts([SocialPost.status == "failed"], SocialPost.scheduled_for.desc(), 30)
    totals: dict[str, dict[str, int]] = {}
    for p in recent:
        m = p.metrics or {}
        t = totals.setdefault(p.platform, {"posts": 0, "likes": 0, "comments": 0, "shares": 0, "views": 0})
        t["posts"] += 1
        for k in ("likes", "comments", "shares", "views"):
            if isinstance(m.get(k), int):
                t[k] += m[k]
    from app.modules.social import prospects as _prospects

    open_prospects = db.scalars(select(SocialProspect).where(SocialProspect.status == "new")
                                .order_by(SocialProspect.found_on.desc(), SocialProspect.name).limit(60)).all()
    prospect_counts = dict(db.execute(select(SocialProspect.status, func.count()).group_by(SocialProspect.status)).all())
    return {"overview": overview, "platforms": platforms, "pending": pending, "scheduled": scheduled,
            "recent": recent, "failed": failed, "engagement_totals": totals, "days": days,
            "prospects": [_prospects.to_dict(p) for p in open_prospects],
            "prospects_enabled": _prospects.configured(),
            "prospect_counts": {k: prospect_counts.get(k, 0) for k in ("new", "done", "skipped")},
            "generated_at": now.isoformat()}

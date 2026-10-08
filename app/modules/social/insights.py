"""Numbers from the platforms for the operator dashboard: profile followers per day and engagement per post.

Everything here is read-only against the platforms and best effort: a platform that fails (missing permission,
outage) is logged and skipped, the others still get their numbers. Nothing is ever posted from this module.

- Facebook Page:    GET /{page}?fields=followers_count,fan_count            (pages_read_engagement)
                    GET /{post}?fields=likes.summary(true),comments.summary(true),shares
- Instagram:        GET /{ig}?fields=followers_count,follows_count,media_count   (instagram_basic)
                    GET /{media}?fields=like_count,comments_count
- TikTok:           POST /v2/user/info/?fields=follower_count,following_count,likes_count,video_count
                    (needs the user.info.stats scope; without it the row is stored with followers=None and an
                    explanation in `raw.error`), POST /v2/video/query/ (video.list) for per-post numbers.
"""
from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from app.config import get_settings
from app.models import SocialAccountSnapshot, SocialPost
from app.modules.social import publishers
from app.modules.social.publishers import PublishError, _graph, _tiktok

log = structlog.get_logger("dialogbot.social.insights")

COPENHAGEN = ZoneInfo("Europe/Copenhagen")
POST_METRICS_DAYS = 60       # how far back published posts keep being refreshed
POST_METRICS_MAX_AGE = dt.timedelta(hours=6)
TIKTOK_STATS_SCOPES = ("user.info.stats", "video.list")


def _now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def _int(v) -> int | None:
    try:
        return int(v) if v is not None else None
    except (TypeError, ValueError):
        return None


# --- profile numbers -----------------------------------------------------------------------------------------------------

def fetch_account(db: OrmSession, platform: str) -> dict:
    """The profile's numbers right now, in the snapshot's shape. Raises PublishError when the platform says no."""
    s = get_settings()
    if platform == "facebook":
        body = _graph("GET", s.meta_page_id, fields="followers_count,fan_count,name")
        return {"followers": _int(body.get("followers_count")), "following": None, "posts": None,
                "likes": _int(body.get("fan_count")), "raw": body}
    if platform == "instagram":
        body = _graph("GET", s.meta_instagram_user_id, fields="followers_count,follows_count,media_count,username")
        return {"followers": _int(body.get("followers_count")), "following": _int(body.get("follows_count")),
                "posts": _int(body.get("media_count")), "likes": None, "raw": body}
    if platform == "tiktok":
        token = publishers.tiktok_access_token(db)
        body = _tiktok("/v2/user/info/?fields=follower_count,following_count,likes_count,video_count,display_name",
                       token=token, method="GET")
        user = (body.get("data") or {}).get("user") or {}
        return {"followers": _int(user.get("follower_count")), "following": _int(user.get("following_count")),
                "posts": _int(user.get("video_count")), "likes": _int(user.get("likes_count")), "raw": user}
    raise PublishError(f"Ukendt platform {platform}")


def snapshot_accounts(db: OrmSession, *, now: dt.datetime | None = None, force: bool = False) -> int:
    """Write today's snapshot for every connected platform that has none yet (or all of them with `force`).
    Returns how many rows were written or updated."""
    today = (now or _now()).astimezone(COPENHAGEN).date()
    n = 0
    for platform in publishers.active_platforms(db):
        row = db.scalar(select(SocialAccountSnapshot).where(SocialAccountSnapshot.platform == platform,
                                                              SocialAccountSnapshot.captured_on == today))
        if row is not None and not force and row.followers is not None:
            continue
        try:
            data = fetch_account(db, platform)
        except PublishError as e:
            log.warning("social.insights.account_failed", platform=platform, error=str(e))
            data = {"followers": None, "following": None, "posts": None, "likes": None, "raw": {"error": str(e)}}
            if row is not None:
                continue  # keep whatever we had today rather than overwrite it with an error
        if row is None:
            row = SocialAccountSnapshot(platform=platform, captured_on=today)
            db.add(row)
        row.followers, row.following, row.posts, row.likes, row.raw = (
            data["followers"], data["following"], data["posts"], data["likes"], data["raw"])
        n += 1
    db.commit()
    return n


# --- per-post engagement ---------------------------------------------------------------------------------------------------

def fetch_post_metrics(db: OrmSession, post: SocialPost) -> dict:
    """Engagement for one published post: only the keys the platform offers."""
    if not post.external_id:
        raise PublishError("Opslaget har intet id hos platformen")
    if post.platform == "facebook":
        body = _graph("GET", post.external_id, fields="likes.summary(true),comments.summary(true),shares")
        return {"likes": _int(((body.get("likes") or {}).get("summary") or {}).get("total_count")),
                "comments": _int(((body.get("comments") or {}).get("summary") or {}).get("total_count")),
                "shares": _int((body.get("shares") or {}).get("count")) or 0}
    if post.platform == "instagram":
        body = _graph("GET", post.external_id, fields="like_count,comments_count")
        return {"likes": _int(body.get("like_count")), "comments": _int(body.get("comments_count"))}
    if post.platform == "tiktok":
        if post.external_id.startswith("p_pub"):
            raise PublishError("TikTok gav kun et publish-id for opslaget; statistik kræver opslagets video-id")
        token = publishers.tiktok_access_token(db)
        body = _tiktok("/v2/video/query/?fields=id,like_count,comment_count,share_count,view_count", token=token,
                       json={"filters": {"video_ids": [post.external_id]}})
        videos = (body.get("data") or {}).get("videos") or []
        if not videos:
            raise PublishError("TikTok kender ikke opslaget (endnu)")
        v = videos[0]
        return {"likes": _int(v.get("like_count")), "comments": _int(v.get("comment_count")),
                "shares": _int(v.get("share_count")), "views": _int(v.get("view_count"))}
    raise PublishError(f"Ukendt platform {post.platform}")


def refresh_post_metrics(db: OrmSession, *, now: dt.datetime | None = None, force: bool = False, limit: int = 40) -> int:
    """Re-read engagement for recently published posts whose numbers are older than POST_METRICS_MAX_AGE."""
    now = now or _now()
    since = now - dt.timedelta(days=POST_METRICS_DAYS)
    stale = now - POST_METRICS_MAX_AGE
    q = (select(SocialPost).where(SocialPost.status == "published", SocialPost.published_at >= since,
                                  SocialPost.external_id.is_not(None))
         .order_by(SocialPost.metrics_at.asc().nulls_first(), SocialPost.published_at.desc()).limit(limit))
    n = 0
    active = set(publishers.active_platforms(db))
    for post in db.scalars(q).all():
        if post.platform not in active or (not force and post.metrics_at is not None and post.metrics_at > stale):
            continue
        try:
            post.metrics = fetch_post_metrics(db, post)
            n += 1
        except PublishError as e:
            log.info("social.insights.post_failed", post_id=str(post.id), platform=post.platform, error=str(e))
            post.metrics = post.metrics or {"error": str(e)[:200]}
        post.metrics_at = now
        db.commit()
    return n


def refresh_all(db: OrmSession, *, now: dt.datetime | None = None, force: bool = False) -> dict:
    """Operator button and hourly worker job. Returns counts; never raises for platform trouble."""
    out = {"accounts": 0, "posts": 0}
    try:
        out["accounts"] = snapshot_accounts(db, now=now, force=force)
    except Exception as e:  # noqa: BLE001 - one platform must not block the other numbers
        db.rollback()
        log.warning("social.insights.accounts_error", error=f"{type(e).__name__}: {e}")
    try:
        out["posts"] = refresh_post_metrics(db, now=now, force=force)
    except Exception as e:  # noqa: BLE001
        db.rollback()
        log.warning("social.insights.posts_error", error=f"{type(e).__name__}: {e}")
    return out

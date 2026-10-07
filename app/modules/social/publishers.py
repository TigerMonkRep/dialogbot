"""Posting to the platforms. SOCIAL_PROVIDER picks the engine: none (off), fake (tests) or live.

Live engines (request shapes follow the vendors' public docs; they could not be exercised against real accounts when
this was written, so every call is covered by a mocked-transport test and the first live post should be watched):
- Facebook Page photo post:       POST graph.facebook.com/{version}/{page-id}/photos
- Instagram single image/carousel: POST /{ig-user-id}/media (+ children), poll status_code, POST /media_publish
- TikTok photo carousel:           POST open.tiktokapis.com/v2/post/publish/content/init/ (PULL_FROM_URL), poll status

Rules shared by all of them:
- the platforms download the images from our public media URL, so PUBLIC_BASE_URL must be reachable (https) by them;
- an error is `retryable` only when the platform cannot have created the post (connection refused, rate limit, 5xx);
  after a request that may have reached the platform (read timeout on the final call) the post is reported as uncertain
  and NOT retried, because a duplicate public post is worse than a missed one;
- tokens are never logged or put in error messages.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Protocol

import httpx
import structlog
from sqlalchemy.orm import Session as OrmSession

from app.config import get_settings
from app.core import crypto
from app.models import SocialCredential, SocialPost

log = structlog.get_logger("dialogbot.social")

TRANSPORT: httpx.BaseTransport | None = None  # tests inject httpx.MockTransport here
_sleep = time.sleep  # tests replace it so polling does not wait


class PublishError(Exception):
    def __init__(self, message: str, *, retryable: bool = False):
        super().__init__(message[:300])
        self.retryable = retryable


@dataclass
class Result:
    external_id: str
    url: str | None = None
    note: str | None = None  # something the operator should know although the post went out


class Publisher(Protocol):
    platform: str

    def publish(self, db: OrmSession, post: SocialPost, image_urls: list[str]) -> Result: ...


def _http() -> httpx.Client:
    return httpx.Client(timeout=30.0, transport=TRANSPORT)


def _json(r: httpx.Response) -> dict:
    try:
        data = r.json()
    except ValueError:
        data = {}
    return data if isinstance(data, dict) else {}


def _send(method: str, url: str, *, final: bool = False, **kw) -> httpx.Response:
    """One HTTP call. `final` marks the call that creates the public post: a read timeout there is uncertain."""
    try:
        with _http() as c:
            return c.request(method, url, **kw)
    except httpx.ConnectError as e:
        raise PublishError("Platformen kunne ikke nås", retryable=True) from e
    except httpx.TimeoutException as e:
        if final:
            raise PublishError("Intet svar fra platformen på selve opslaget – tjek profilen, før der postes igen",
                               retryable=False) from e
        raise PublishError("Platformen svarede ikke i tide", retryable=True) from e
    except httpx.HTTPError as e:
        raise PublishError(f"Netværksfejl mod platformen ({type(e).__name__})", retryable=True) from e


# --- Meta (Facebook page + Instagram business account) --------------------------------------------------------------

META_RETRYABLE_CODES = {1, 2, 4, 17, 32, 341, 613}


def _graph(method: str, path: str, *, final: bool = False, **params) -> dict:
    s = get_settings()
    params["access_token"] = s.meta_page_access_token
    kw = {"data": params} if method == "POST" else {"params": params}
    r = _send(method, f"https://graph.facebook.com/{s.meta_graph_version}/{path}", final=final, **kw)
    body = _json(r)
    err = body.get("error")
    if r.status_code >= 400 or err:
        err = err if isinstance(err, dict) else {}
        code = err.get("code")
        retryable = r.status_code >= 500 or code in META_RETRYABLE_CODES
        raise PublishError(f"Meta {r.status_code}/{code}: {str(err.get('message') or 'ukendt fejl')[:200]}",
                           retryable=retryable)
    return body


class FacebookPublisher:
    platform = "facebook"

    def publish(self, db, post, image_urls):
        s = get_settings()
        body = _graph("POST", f"{s.meta_page_id}/photos", final=True, url=image_urls[0], caption=post.caption,
                      published="true")
        pid = str(body.get("post_id") or body.get("id") or "")
        if not pid:
            raise PublishError("Meta svarede uden opslags-id – tjek siden, før der postes igen")
        return Result(pid, f"https://www.facebook.com/{pid}")


class InstagramPublisher:
    platform = "instagram"

    def _wait_ready(self, container_id: str) -> None:
        for _ in range(20):
            status = _graph("GET", container_id, fields="status_code").get("status_code")
            if status == "FINISHED":
                return
            if status in ("ERROR", "EXPIRED"):
                raise PublishError(f"Instagram kunne ikke behandle billedet ({status})", retryable=True)
            _sleep(3)
        raise PublishError("Instagram blev ikke færdig med billederne i tide", retryable=True)

    def publish(self, db, post, image_urls):
        ig = get_settings().meta_instagram_user_id
        if len(image_urls) == 1:
            container = str(_graph("POST", f"{ig}/media", image_url=image_urls[0], caption=post.caption)["id"])
        else:
            children = []
            for u in image_urls:
                children.append(str(_graph("POST", f"{ig}/media", image_url=u, is_carousel_item="true")["id"]))
            for cid in children:
                self._wait_ready(cid)
            container = str(_graph("POST", f"{ig}/media", media_type="CAROUSEL", children=",".join(children),
                                   caption=post.caption)["id"])
        self._wait_ready(container)
        media_id = str(_graph("POST", f"{ig}/media_publish", final=True, creation_id=container)["id"])
        url = None
        try:
            url = _graph("GET", media_id, fields="permalink").get("permalink")
        except PublishError:
            pass  # the post is out; the link is a nicety
        return Result(media_id, url)


# --- TikTok (photo carousel) -----------------------------------------------------------------------------------------

TIKTOK_API = "https://open.tiktokapis.com"
TIKTOK_RETRYABLE = {"rate_limit_exceeded", "internal_error", "service_unavailable"}


def _tiktok(path: str, *, token: str | None = None, final: bool = False, **kw) -> dict:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    r = _send("POST", f"{TIKTOK_API}{path}", final=final, headers=headers, **kw)
    body = _json(r)
    err = body.get("error")
    code = err.get("code") if isinstance(err, dict) else body.get("error")
    if r.status_code >= 400 or (code and code != "ok"):
        msg = (err.get("message") if isinstance(err, dict) else body.get("error_description")) or "ukendt fejl"
        raise PublishError(f"TikTok {r.status_code}/{code}: {str(msg)[:200]}",
                           retryable=r.status_code >= 500 or code in TIKTOK_RETRYABLE)
    return body


def _tiktok_refresh_token(db: OrmSession) -> str | None:
    cred = db.get(SocialCredential, "tiktok")
    if cred is not None:
        try:
            return crypto.decrypt(crypto.Envelope(cred.key_version, cred.secret_blob), aad=b"social:tiktok").decode()
        except (crypto.DecryptFailed, crypto.CredentialsKeyUnavailable):
            log.warning("social.tiktok_credential_unreadable")
    return get_settings().tiktok_refresh_token


def store_tiktok_refresh_token(db: OrmSession, token: str) -> None:
    env = crypto.encrypt(token.encode(), aad=b"social:tiktok")
    cred = db.get(SocialCredential, "tiktok")
    if cred is None:
        db.add(SocialCredential(platform="tiktok", key_version=env.key_version, secret_blob=env.blob))
    else:
        cred.key_version, cred.secret_blob = env.key_version, env.blob
    db.flush()


def tiktok_access_token(db: OrmSession) -> str:
    s = get_settings()
    refresh = _tiktok_refresh_token(db)
    if not (refresh and s.tiktok_client_key and s.tiktok_client_secret):
        raise PublishError("TikTok er ikke forbundet (klient-nøgle/-hemmelighed eller refresh-token mangler)")
    body = _tiktok("/v2/oauth/token/", data={"client_key": s.tiktok_client_key, "client_secret": s.tiktok_client_secret,
                                             "grant_type": "refresh_token", "refresh_token": refresh})
    token = body.get("access_token")
    if not token:
        raise PublishError("TikTok udleverede ikke et adgangstoken – forbind kontoen igen")
    new_refresh = body.get("refresh_token")
    if new_refresh and new_refresh != refresh:
        store_tiktok_refresh_token(db, new_refresh)  # the old one is dead: commit now, whatever happens to the post
        db.commit()
    return token


class TikTokPublisher:
    platform = "tiktok"

    def publish(self, db, post, image_urls):
        token = tiktok_access_token(db)
        creator = _tiktok("/v2/post/publish/creator_info/query/", token=token).get("data", {})
        options = creator.get("privacy_level_options") or []
        level = "PUBLIC_TO_EVERYONE" if "PUBLIC_TO_EVERYONE" in options else ("SELF_ONLY" if "SELF_ONLY" in options else
                                                                              (options[0] if options else "SELF_ONLY"))
        title = (post.slides[0]["title"] if post.slides else "Dialogbot")[:90]
        payload = {"post_info": {"title": title, "description": post.caption[:4000], "disable_comment": False,
                                 "privacy_level": level, "auto_add_music": True},
                   "source_info": {"source": "PULL_FROM_URL", "photo_cover_index": 0, "photo_images": image_urls},
                   "post_mode": "DIRECT_POST", "media_type": "PHOTO"}
        data = _tiktok("/v2/post/publish/content/init/", token=token, final=True, json=payload).get("data", {})
        publish_id = str(data.get("publish_id") or "")
        if not publish_id:
            raise PublishError("TikTok svarede uden publish_id – tjek profilen, før der postes igen")
        note = None if level == "PUBLIC_TO_EVERYONE" else (
            "TikTok tillader kun private opslag, indtil appen er godkendt (audit) – opslaget er kun synligt for dig")
        for _ in range(20):
            st = _tiktok("/v2/post/publish/status/fetch/", token=token, json={"publish_id": publish_id}).get("data", {})
            status = st.get("status")
            if status == "PUBLISH_COMPLETE":
                ids = st.get("publicaly_available_post_id") or st.get("publicly_available_post_id") or []
                return Result(str(ids[0]) if ids else publish_id, None, note)
            if status == "FAILED":
                raise PublishError(f"TikTok afviste opslaget: {str(st.get('fail_reason') or 'ukendt årsag')[:200]}")
            _sleep(4)
        return Result(publish_id, None, (note + ". " if note else "") + "TikTok behandlede stadig opslaget ved sidste tjek")


# --- test double --------------------------------------------------------------------------------------------------------

FAKE_PUBLISHED: list[dict] = []
FAKE_FAIL: dict[str, PublishError] = {}  # platform → error to raise (tests)


class FakePublisher:
    def __init__(self, platform: str):
        self.platform = platform

    def publish(self, db, post, image_urls):
        if self.platform in FAKE_FAIL:
            raise FAKE_FAIL[self.platform]
        FAKE_PUBLISHED.append({"platform": self.platform, "post_id": str(post.id), "caption": post.caption,
                               "images": list(image_urls)})
        return Result(f"fake-{self.platform}-{post.id}", None)


# --- selection ----------------------------------------------------------------------------------------------------------

def enabled_platforms() -> list[str]:
    return [p.strip() for p in get_settings().social_platforms.split(",") if p.strip() in ("facebook", "instagram", "tiktok")]


def live_configured(db: OrmSession) -> dict[str, bool]:
    s = get_settings()
    meta = bool(s.meta_page_access_token)
    return {"facebook": meta and bool(s.meta_page_id), "instagram": meta and bool(s.meta_instagram_user_id),
            "tiktok": bool(s.tiktok_client_key and s.tiktok_client_secret and _tiktok_refresh_token(db))}


def get_publisher(db: OrmSession, platform: str) -> Publisher | None:
    """The engine for a platform, or None when it is switched off or not configured."""
    s = get_settings()
    if platform not in enabled_platforms() or s.social_provider == "none":
        return None
    if s.social_provider == "fake":
        return FakePublisher(platform)
    if not live_configured(db).get(platform):
        return None
    return {"facebook": FacebookPublisher, "instagram": InstagramPublisher, "tiktok": TikTokPublisher}[platform]()


def active_platforms(db: OrmSession) -> list[str]:
    return [p for p in enabled_platforms() if get_publisher(db, p) is not None]


def media_url(media_id) -> str:
    return f"{get_settings().public_base_url.rstrip('/')}/api/v1/social/media/{media_id}.jpg"

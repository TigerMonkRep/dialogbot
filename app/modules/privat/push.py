"""Web Push (VAPID) for Dialogbot Privat.

Push is the primary channel for reminders, call outcomes, business call-backs, accepted invitations and activity on
shared lists. E-mail is only the fallback: when the user has no working subscription, or when push fails for good
(the push service says 404/410 → the subscription is deleted; other errors are retried by the outbox and, after the
last attempt, the e-mail goes instead). Shared-list activity is push-only and batched: at most one push per list per
recipient per 2 minutes. Sending runs in the worker (outbox event push.send) through pywebpush.
Keys: VAPID_PUBLIC_KEY / VAPID_PRIVATE_KEY / VAPID_SUBJECT (`python -m scripts.generate_vapid` prints a pair).
"""
from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from app.config import get_settings
from app.core.errors import NotImplementedYet, ValidationFailed
from app.core.outbox import enqueue
from app.models import OutboxEvent, PushSubscription, User
from app.modules.privat import rules

LIST_BATCH_SECONDS = 120
TTL_SECONDS = 24 * 3600


class PushNotConfigured(NotImplementedYet):
    code = "push_not_configured"


def configured() -> bool:
    s = get_settings()
    return bool(s.vapid_public_key and s.vapid_private_key)


def public_key() -> str:
    if not configured():
        raise PushNotConfigured("Push-notifikationer er ikke sat op på serveren (VAPID-nøgler mangler)")
    return get_settings().vapid_public_key


def subscribe(db: OrmSession, user_id: uuid.UUID, *, endpoint: str, p256dh: str, auth: str,
              user_agent: str | None) -> PushSubscription:
    """One row per endpoint: subscribing the same browser again updates it (also when another user logs in there)."""
    if not endpoint.startswith("https://"):
        raise ValidationFailed("Ugyldigt push-endpoint", field_errors=[{"field": "endpoint"}])
    sub = db.scalar(select(PushSubscription).where(PushSubscription.endpoint == endpoint).with_for_update())
    if sub is None:
        sub = PushSubscription(user_id=user_id, endpoint=endpoint, p256dh=p256dh, auth=auth,
                               user_agent=(user_agent or "")[:400] or None)
        db.add(sub)
    else:
        sub.user_id, sub.p256dh, sub.auth, sub.failures = user_id, p256dh, auth, 0
        sub.user_agent = (user_agent or "")[:400] or sub.user_agent
    db.flush()
    return sub


def unsubscribe(db: OrmSession, user_id: uuid.UUID, endpoint: str) -> bool:
    sub = db.scalar(select(PushSubscription).where(PushSubscription.endpoint == endpoint,
                                                   PushSubscription.user_id == user_id))
    if sub is None:
        return False
    db.delete(sub)
    return True


def subscriptions(db: OrmSession, user_id: uuid.UUID) -> list[PushSubscription]:
    if not configured():
        return []
    return list(db.scalars(select(PushSubscription).where(PushSubscription.user_id == user_id)))


def has_subscriptions(db: OrmSession, user_id: uuid.UUID) -> bool:
    return bool(subscriptions(db, user_id))


def _enqueue(db: OrmSession, sub: PushSubscription, *, key: str, title: str, body: str, url: str | None,
             tag: str | None, fallback: dict | None, at: datetime | None = None) -> None:
    ev = enqueue(db, event_type="push.send", dedupe_key=f"push:{key}:{sub.id}"[:200],
                 payload={"subscription_id": str(sub.id), "user_id": str(sub.user_id), "title": title[:120],
                          "body": body[:300], "url": url, "tag": tag, "fallback": fallback})
    if at is not None:
        ev.next_attempt_at = at


def notify(db: OrmSession, user_id: uuid.UUID, *, title: str, body: str, url: str | None, dedupe: str,
           email: dict | None = None, workspace_id: uuid.UUID | None = None) -> str:
    """Push to every subscription of the user; e-mail (`email` = {"to_email", "email": tpl.to_payload(...)}) only when
    there is none. Returns "push", "email" or "none"."""
    subs = subscriptions(db, user_id)
    if subs:
        for s in subs:
            _enqueue(db, s, key=dedupe, title=title, body=body, url=url, tag=dedupe.split(":")[0], fallback=email)
        return "push"
    if email:
        enqueue(db, event_type="email.branded", dedupe_key=f"privat-notify:{dedupe}"[:200], workspace_id=workspace_id,
                payload=email)
        return "email"
    return "none"


def notify_list_activity(db: OrmSession, task, *, actor_user_id: uuid.UUID | None, text: str) -> None:
    """New items or members on a shared list → the OTHER members, push only, at most one per list per recipient per
    2 minutes (later activity in the same window joins the push that is already waiting). Never for reservations."""
    from app.models import PrivateTaskMember

    if task.share_mode is None:
        return
    now = rules.now()
    bucket = int(now.timestamp()) // LIST_BATCH_SECONDS
    send_at = datetime.fromtimestamp((bucket + 1) * LIST_BATCH_SECONDS, UTC)
    url = f"{get_settings().frontend_base_url.rstrip('/')}/privat/opgaver/{task.id}"
    for uid in db.scalars(select(PrivateTaskMember.user_id).where(PrivateTaskMember.task_id == task.id)):
        if uid == actor_user_id:
            continue
        for s in subscriptions(db, uid):
            _enqueue(db, s, key=f"list:{task.id}:{uid}:{bucket}", title=task.title, body=text, url=url,
                     tag=f"list-{task.id}", fallback=None, at=send_at)


def test(db: OrmSession, user_id: uuid.UUID) -> int:
    subs = subscriptions(db, user_id)
    for s in subs:
        _enqueue(db, s, key=f"test:{uuid.uuid4().hex}", title="Dialogbot", body="Det virker – du får besked her",
                 url=None, tag="test", fallback=None)
    return len(subs)


# --------------------------------------------------------------------------- worker

def _webpush(subscription_info: dict, data: str) -> None:
    """The one place pywebpush is called (tests replace it)."""
    from pywebpush import webpush

    s = get_settings()
    webpush(subscription_info=subscription_info, data=data, vapid_private_key=s.vapid_private_key,
            vapid_claims={"sub": s.vapid_subject}, ttl=TTL_SECONDS, timeout=10)


def _status(exc: Exception) -> int | None:
    resp = getattr(exc, "response", None)
    return getattr(resp, "status_code", None)


def _fallback(db: OrmSession, ev: OutboxEvent) -> None:
    fb = (ev.payload or {}).get("fallback")
    if fb and not has_subscriptions(db, uuid.UUID(ev.payload["user_id"])):
        enqueue(db, event_type="email.branded", dedupe_key=f"push-fallback:{ev.id}", payload=fb)


def handle_send(db: OrmSession, ev: OutboxEvent) -> None:
    """push.send: 404/410 → the subscription is gone (deleted, e-mail fallback if it was the last one); other errors
    are retried by the outbox, and after the last attempt the e-mail fallback is sent instead."""
    from pywebpush import WebPushException

    p = ev.payload
    sub = db.get(PushSubscription, uuid.UUID(p["subscription_id"]))
    if sub is None or not configured():
        _fallback(db, ev)
        return
    data = json.dumps({"title": p.get("title"), "body": p.get("body"), "url": p.get("url"), "tag": p.get("tag")},
                      ensure_ascii=False)
    try:
        _webpush({"endpoint": sub.endpoint, "keys": {"p256dh": sub.p256dh, "auth": sub.auth}}, data)
    except WebPushException as e:
        if _status(e) in (404, 410):
            db.delete(sub)
            db.flush()
            _fallback(db, ev)
            return
        sub.failures += 1
        if ev.attempts >= ev.max_attempts:  # push failed for good: the e-mail goes instead
            fb = (ev.payload or {}).get("fallback")
            if fb:
                enqueue(db, event_type="email.branded", dedupe_key=f"push-fallback:{ev.id}", payload=fb)
            return
        raise
    sub.last_success_at, sub.failures = rules.now(), 0


def user_email_payload(db: OrmSession, user_id: uuid.UUID, mail) -> dict | None:
    from app.modules.integrations import email_templates as tpl

    u = db.get(User, user_id)
    return {"to_email": u.email, "email": tpl.to_payload(mail)} if u else None


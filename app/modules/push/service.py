"""Web Push for the business app (the Erhverv PWA): subscriptions per user and workspace, and the notifications that
go to them. Sending reuses Dialogbot Privat's VAPID machinery (app/modules/privat/push: outbox event `push.send`,
pywebpush, 404/410 handling) – the subscription rows carry `audience='erhverv'` and the workspace, so neither app
ever pushes to the other's subscriptions.

Opt-in is the subscription itself: a member who has not subscribed from the PWA in a browser gets nothing, and
unsubscribing (or the browser revoking the endpoint) ends it. Nothing is pushed to members of other workspaces.
"""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from app.config import get_settings
from app.models import Call, Membership, PushSubscription
from app.modules.privat import push as privat_push

AUDIENCE = "erhverv"


def configured() -> bool:
    return privat_push.configured()


def public_key() -> str:
    return privat_push.public_key()


def subscribe(db: OrmSession, user_id: uuid.UUID, workspace_id: uuid.UUID, *, endpoint: str, p256dh: str, auth: str,
              user_agent: str | None) -> PushSubscription:
    return privat_push.subscribe(db, user_id, endpoint=endpoint, p256dh=p256dh, auth=auth, user_agent=user_agent,
                                 audience=AUDIENCE, workspace_id=workspace_id)


def unsubscribe(db: OrmSession, user_id: uuid.UUID, endpoint: str) -> bool:
    return privat_push.unsubscribe(db, user_id, endpoint)


def subscriptions(db: OrmSession, user_id: uuid.UUID, workspace_id: uuid.UUID) -> list[PushSubscription]:
    return privat_push.subscriptions(db, user_id, audience=AUDIENCE, workspace_id=workspace_id)


def notify_workspace(db: OrmSession, workspace_id: uuid.UUID, *, key: str, title: str, body: str, url: str | None,
                     tag: str | None) -> int:
    """Push to every subscribed member of the workspace. Returns the number of subscriptions queued."""
    if not configured():
        return 0
    n = 0
    for uid in db.scalars(select(Membership.user_id).where(Membership.workspace_id == workspace_id)):
        for sub in subscriptions(db, uid, workspace_id):
            privat_push._enqueue(db, sub, key=f"{key}:{uid}", title=title, body=body, url=url, tag=tag, fallback=None)
            n += 1
    return n


def notify_call_completed(db: OrmSession, call: Call) -> int:
    """`call.completed` → «Nyt opkald» with the summary, opening the call in the app."""
    body = (call.summary or "").strip() or (f"Opkald fra {call.from_number}" if call.from_number else "Nyt opkald er gemt")
    url = f"{get_settings().frontend_base_url.rstrip('/')}/app/opkald/{call.id}"
    return notify_workspace(db, call.workspace_id, key=f"call:{call.id}", title="Nyt opkald", body=body[:300], url=url,
                            tag=f"call-{call.id}")

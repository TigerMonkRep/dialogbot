"""Outgoing webhooks of the public API: fan-out, signing and delivery.

Fan-out: `fan_out()` is called from app.modules.integrations.events.emit – the one place domain events are raised –
and writes one outbox event (`public_webhook.deliver`) per active endpoint subscribed to the event type, in the same
transaction as the domain change. The event id is deterministic (uuid5 of workspace, type and business key), so
every endpoint and every retry sees the same `id`, which lets receivers de-duplicate.

Delivery (worker): POST JSON `{"id", "type", "created_at", "workspace_id", "data"}` with
`Dialogbot-Signature: t=<unix seconds>,v1=<hex HMAC-SHA256 over "<t>.<body>">` and a 10 s timeout, through
app.core.safe_fetch (public https only, pinned address, no redirects). 2xx = delivered. 5xx, 429, timeouts and
network errors are retried by the outbox with backoff up to OutboxEvent.max_attempts; 4xx (except 429) is final.
Every failed attempt increments the endpoint's consecutive `failure_count`; a success resets it. At
PUBLIC_API_WEBHOOK_DISABLE_AFTER the endpoint is switched off and its pending deliveries are dropped on arrival.

The attempt history is the outbox itself (`GET …/webhooks/{id}/deliveries` reads it); there is no separate
deliveries table.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import time
import uuid
from datetime import UTC, datetime

import httpx
import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from app.config import get_settings
from app.core import crypto, safe_fetch
from app.core.outbox import enqueue
from app.models import OutboxEvent, WebhookEndpoint

log = structlog.get_logger("dialogbot.public_webhooks")

EVENT_TYPE = "public_webhook.deliver"
SIGNATURE_HEADER = "Dialogbot-Signature"
TIMEOUT_SECONDS = 10.0
MAX_BODY = 200_000
EVENT_NAMESPACE = uuid.UUID("7f0c2a2e-5f0e-4a52-9d4d-3c3e1b6d9e01")

# What a customer can subscribe to. `payload` in docs/public-api.md.
EVENTS: dict[str, str] = {
    "call.completed": "Et opkald er afsluttet og gemt (resumé, varighed, udfald)",
    "booking.created": "En aftale er oprettet (webchat, telefon eller manuelt)",
    "booking.cancelled": "En aftale er aflyst",
    "lead.created": "En ny henvendelse er oprettet",
    "conversation.ended": "En samtale er afsluttet (telefon)",
    "knowledge.version_approved": "En vidensversion er godkendt (den aktive viden ændrede sig)",
}

# Tests set this to an httpx.MockTransport; production uses the real network through safe_fetch.
TRANSPORT: httpx.BaseTransport | None = None


# --------------------------------------------------------------------------- secrets

def new_secret() -> str:
    return "whsec_" + secrets.token_urlsafe(32)


def _aad(endpoint: WebhookEndpoint) -> bytes:
    return f"{endpoint.workspace_id}:{endpoint.id}".encode()


def put_secret(endpoint: WebhookEndpoint, secret: str) -> None:
    env = crypto.encrypt(secret.encode(), aad=_aad(endpoint))
    endpoint.key_version, endpoint.secret_blob = env.key_version, env.blob


def get_secret(endpoint: WebhookEndpoint) -> str:
    return crypto.decrypt(crypto.Envelope(endpoint.key_version, bytes(endpoint.secret_blob)), aad=_aad(endpoint)).decode()


# --------------------------------------------------------------------------- signing

def sign(secret: str, body: bytes, ts: int | None = None) -> str:
    ts = ts or int(time.time())
    mac = hmac.new(secret.encode(), f"{ts}.".encode() + body, hashlib.sha256).hexdigest()
    return f"t={ts},v1={mac}"


def verify(secret: str, body: bytes, header: str, *, tolerance_seconds: int = 300, now: int | None = None) -> bool:
    """Reference implementation for receivers (docs/public-api.md has the same in Python and Node)."""
    parts = dict(p.split("=", 1) for p in (header or "").split(",") if "=" in p)
    try:
        ts = int(parts.get("t", ""))
    except ValueError:
        return False
    if abs((now or int(time.time())) - ts) > tolerance_seconds:
        return False
    expected = hmac.new(secret.encode(), f"{ts}.".encode() + body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, parts.get("v1", ""))


# --------------------------------------------------------------------------- fan-out

def event_id(workspace_id: uuid.UUID, event: str, key: str) -> str:
    return "evt_" + uuid.uuid5(EVENT_NAMESPACE, f"{workspace_id}:{event}:{key}").hex


def endpoints_for(db: OrmSession, workspace_id: uuid.UUID, event: str) -> list[WebhookEndpoint]:
    rows = db.scalars(select(WebhookEndpoint).where(WebhookEndpoint.workspace_id == workspace_id,
                                                    WebhookEndpoint.active.is_(True)))
    return [w for w in rows if event in (w.events or [])]


def fan_out(db: OrmSession, workspace_id: uuid.UUID, event: str, data: dict, *, key: str) -> int:
    """One outbox event per subscribed endpoint. Returns how many were queued."""
    if event not in EVENTS:
        return 0
    n = 0
    occurred = datetime.now(UTC).isoformat()
    eid = event_id(workspace_id, event, key)
    for w in endpoints_for(db, workspace_id, event):
        enqueue(db, event_type=EVENT_TYPE, dedupe_key=f"pubhook:{w.id}:{event}:{key}"[:200], workspace_id=workspace_id,
                payload={"endpoint_id": str(w.id), "event_id": eid, "type": event, "created_at": occurred, "data": data})
        n += 1
    return n


def body_for(p: dict, workspace_id: uuid.UUID) -> bytes:
    doc = {"id": p["event_id"], "type": p["type"], "created_at": p["created_at"], "workspace_id": str(workspace_id),
           "data": p.get("data") or {}}
    body = json.dumps(doc, ensure_ascii=False, default=str, separators=(",", ":")).encode()
    if len(body) > MAX_BODY:
        doc["data"] = {"truncated": True}
        body = json.dumps(doc, ensure_ascii=False, separators=(",", ":")).encode()
    return body


# --------------------------------------------------------------------------- delivery

class DeliveryFailed(Exception):
    def __init__(self, message: str, *, retryable: bool):
        super().__init__(message)
        self.retryable = retryable


def post(url: str, secret: str, body: bytes) -> int:
    """One signed POST. Raises DeliveryFailed; returns the status on 2xx."""
    headers = {"content-type": "application/json", "user-agent": "Dialogbot-Webhooks/1.0", SIGNATURE_HEADER: sign(secret, body)}
    try:
        r = safe_fetch.send("POST", url, content=body, headers=headers, timeout=TIMEOUT_SECONDS, transport=TRANSPORT)
    except safe_fetch.FetchBlocked as e:
        raise DeliveryFailed(f"Adressen er ikke tilladt ({e})", retryable=False) from e
    except safe_fetch.FetchFailed as e:
        if e.reason == "timeout":
            raise DeliveryFailed("Modtageren svarede ikke inden 10 s", retryable=True) from e
        raise DeliveryFailed(f"Modtageren kunne ikke nås ({e.reason})", retryable=True) from e
    if 200 <= r.status < 300:
        return r.status
    if r.status == 410:
        raise DeliveryFailed("Modtageren har afmeldt webhooken (410)", retryable=False)
    raise DeliveryFailed(f"Modtageren svarede {r.status}", retryable=r.status == 429 or r.status >= 500)


def _record_failure(db: OrmSession, w: WebhookEndpoint, reason: str) -> None:
    w.failure_count += 1
    w.last_error = reason[:300]
    limit = get_settings().public_api_webhook_disable_after
    if w.failure_count >= limit and w.active:
        w.active = False
        w.disabled_at = datetime.now(UTC)
        w.disabled_reason = f"Slået fra efter {w.failure_count} fejlede leveringer i træk: {reason}"[:300]
        log.warning("public_webhook.disabled", endpoint_id=str(w.id), failures=w.failure_count)
    db.commit()  # survives the rollback the worker does when the handler raises for a retry


def handle_deliver(db: OrmSession, ev: OutboxEvent) -> None:
    """Worker handler for `public_webhook.deliver`."""
    p = ev.payload or {}
    w = db.scalar(select(WebhookEndpoint).where(WebhookEndpoint.id == uuid.UUID(p["endpoint_id"])).with_for_update())
    if w is None or not w.active:
        return  # deleted or switched off meanwhile: nothing to deliver, nothing to retry
    try:
        secret = get_secret(w)
    except (crypto.CredentialsKeyUnavailable, crypto.DecryptFailed) as e:
        _record_failure(db, w, f"Hemmeligheden kan ikke læses ({type(e).__name__})")
        return
    body = body_for(p, w.workspace_id)
    try:
        post(w.url, secret, body)
    except DeliveryFailed as e:
        _record_failure(db, w, str(e))
        if e.retryable and ev.attempts < ev.max_attempts:
            raise  # the worker backs off and tries again
        return
    w.last_delivery_at = datetime.now(UTC)
    w.failure_count = 0
    w.last_error = None


def deliveries(db: OrmSession, endpoint_id: uuid.UUID, limit: int = 50) -> list[OutboxEvent]:
    return list(db.scalars(select(OutboxEvent).where(OutboxEvent.event_type == EVENT_TYPE,
                                                     OutboxEvent.payload["endpoint_id"].astext == str(endpoint_id))
                           .order_by(OutboxEvent.created_at.desc()).limit(limit)))

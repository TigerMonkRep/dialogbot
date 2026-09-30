"""Domain events fanned out to the workspace's webhook connectors (webhook, Zapier, Make) via the outbox.

`emit()` is called from the places where something the customer cares about happened – a lead, a booking, an
executed action, an ended conversation. It writes one outbox event per connected sink in the same transaction
as the domain change; the worker delivers it with retries. A sink that keeps failing gets `status=error` with the
last reason, visible under Integrationer. Nothing here raises into the caller.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from app.core.outbox import enqueue
from app.models import IntegrationConnection, OutboxEvent

EVENT_TYPE = "webhook.deliver"
SINKS = ("webhook", "zapier", "make")


def sinks(db: OrmSession, workspace_id: uuid.UUID) -> list[IntegrationConnection]:
    return list(db.scalars(select(IntegrationConnection).where(
        IntegrationConnection.workspace_id == workspace_id, IntegrationConnection.connector.in_(SINKS),
        IntegrationConnection.status == "connected")))


def emit(db: OrmSession, workspace_id: uuid.UUID, event: str, data: dict, *, key: str) -> int:
    """Queue `event` for every connected sink. `key` makes the delivery idempotent per business object."""
    n = 0
    occurred = datetime.now(UTC).isoformat()
    for conn in sinks(db, workspace_id):
        enqueue(db, event_type=EVENT_TYPE, dedupe_key=f"webhook:{conn.id}:{event}:{key}",
                payload={"connection_id": str(conn.id), "event": event, "occurred_at": occurred, "data": data},
                workspace_id=workspace_id)
        n += 1
    return n


def handle_deliver(db: OrmSession, ev: OutboxEvent) -> None:
    """Worker handler. Raises on a retryable failure (the worker backs off); marks the connection on the last try."""
    from app.modules.integrations import credentials
    from app.modules.integrations.connectors import webhook
    from app.modules.integrations.connectors.base import ActionError

    p = ev.payload
    conn = db.get(IntegrationConnection, uuid.UUID(p["connection_id"]))
    if conn is None or conn.status != "connected":
        return  # disconnected meanwhile: nothing to deliver, nothing to retry
    body = webhook.payload(p["event"], str(ev.id), str(conn.workspace_id), p["occurred_at"], p.get("data") or {})
    secret = (credentials.get_secret(conn) or {}).get("signing_secret", "")
    try:
        webhook.deliver(url=str(conn.config.get("url") or ""), secret=secret, body=body, simulated=conn.simulated)
    except ActionError as e:
        if not e.retryable or ev.attempts >= ev.max_attempts:
            credentials.mark_error(conn, f"Hændelsen {p['event']} kunne ikke leveres: {e.message}")
            db.commit()
        if e.retryable:
            raise  # the worker retries with backoff
        return  # permanent: recorded on the connection, no further attempts
    credentials.mark_ok(conn)

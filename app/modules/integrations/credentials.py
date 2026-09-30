"""Reading and writing the encrypted part of an integration connection.

The plaintext secret is a small JSON object (OAuth: access_token, refresh_token, token_type; api_key: key;
secret: secret). It is encrypted with app/core/crypto bound to the connection's workspace and connector as
associated data, so a blob copied onto another row does not decrypt. Callers get a dict and must not log it.
"""
from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from app.core import crypto
from app.models import IntegrationConnection


def _aad(workspace_id: uuid.UUID, connector: str) -> bytes:
    return f"{workspace_id}:{connector}".encode()


def put_secret(conn: IntegrationConnection, secret: dict | None) -> None:
    if secret is None:
        conn.key_version, conn.secret_blob = None, None
        return
    env = crypto.encrypt(json.dumps(secret, separators=(",", ":")).encode(), aad=_aad(conn.workspace_id, conn.connector))
    conn.key_version, conn.secret_blob = env.key_version, env.blob


def get_secret(conn: IntegrationConnection) -> dict | None:
    if conn.secret_blob is None or conn.key_version is None:
        return None
    raw = crypto.decrypt(crypto.Envelope(conn.key_version, bytes(conn.secret_blob)),
                         aad=_aad(conn.workspace_id, conn.connector))
    return json.loads(raw)


def connection(db: OrmSession, workspace_id: uuid.UUID, connector: str, *, lock: bool = False) -> IntegrationConnection | None:
    q = select(IntegrationConnection).where(IntegrationConnection.workspace_id == workspace_id,
                                            IntegrationConnection.connector == connector)
    return db.scalar(q.with_for_update() if lock else q)


def connections(db: OrmSession, workspace_id: uuid.UUID) -> dict[str, IntegrationConnection]:
    rows = db.scalars(select(IntegrationConnection).where(IntegrationConnection.workspace_id == workspace_id))
    return {c.connector: c for c in rows}


def mark_ok(conn: IntegrationConnection) -> None:
    conn.status, conn.error, conn.last_ok_at = "connected", None, datetime.now(UTC)


def mark_error(conn: IntegrationConnection, message: str) -> None:
    conn.status, conn.error = "error", message[:300]


def rewrap_all(db: OrmSession) -> int:
    """Re-encrypt every secret with the current CREDENTIALS_KEY (after a rotation). Returns rows rewritten."""
    n = 0
    current = crypto.current_key_version()
    for c in db.scalars(select(IntegrationConnection).where(IntegrationConnection.secret_blob.is_not(None))):
        if c.key_version != current:
            put_secret(c, get_secret(c))
            n += 1
    return n

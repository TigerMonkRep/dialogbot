"""Cursor pagination for the public API: `{"items": [...], "next_cursor": "…" | null}`.

Keyset on (sort column, id), both descending – newest first – so a page is stable while new rows arrive. The cursor
is opaque to the client: base64url of `<iso timestamp>|<uuid>`. `limit` is 1–200, default 50.
"""
from __future__ import annotations

import base64
import binascii
import uuid
from datetime import datetime
from typing import Any

from fastapi import Query
from sqlalchemy import and_, or_

from app.core.errors import ValidationFailed


class CursorParams:
    def __init__(self, limit: int = Query(50, ge=1, le=200), cursor: str | None = Query(default=None)):
        self.limit = limit
        self.cursor = cursor


def encode(ts: datetime, id_: uuid.UUID) -> str:
    return base64.urlsafe_b64encode(f"{ts.isoformat()}|{id_}".encode()).decode().rstrip("=")


def decode(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)).decode()
        ts, id_ = raw.split("|", 1)
        return datetime.fromisoformat(ts), uuid.UUID(id_)
    except (binascii.Error, ValueError, UnicodeDecodeError) as e:
        raise ValidationFailed("Ugyldig cursor", field_errors=[{"field": "cursor"}], code="invalid_cursor") from e


def apply(query, p: CursorParams, ts_col, id_col):
    """Order the query newest-first and start after the cursor. Fetches one extra row to know if there is more."""
    if p.cursor:
        ts, id_ = decode(p.cursor)
        query = query.where(or_(ts_col < ts, and_(ts_col == ts, id_col < id_)))
    return query.order_by(ts_col.desc(), id_col.desc()).limit(p.limit + 1)


def page(rows: list[Any], p: CursorParams, ts_of, id_of, render) -> dict:
    more = len(rows) > p.limit
    rows = rows[: p.limit]
    nxt = encode(ts_of(rows[-1]), id_of(rows[-1])) if more and rows else None
    return {"items": [render(r) for r in rows], "next_cursor": nxt}

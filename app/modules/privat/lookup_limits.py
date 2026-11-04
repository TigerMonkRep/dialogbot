"""Rate limits on the PUBLIC lookups of invitation and group links (by token or 8-character short code), so codes
cannot be enumerated.

Per IP (a keyed hash of it is stored, never the IP): all lookups 30/minute and 300/day; misses (unknown, revoked or
expired codes) are counted far more strictly: 10/minute and 50/day. On top of that a global ceiling on misses
(1000/hour across all IPs) stops enumeration spread over many addresses. Over a limit → 429 `rate_limited`, also for
codes that exist, so the answer reveals nothing.

The IP is the first address in X-Forwarded-For (Render's proxy and the web BFF set it), else the socket address. The
web BFF must forward the visitor's address in X-Forwarded-For when it proxies these calls server-side.
"""
from __future__ import annotations

import hashlib
import hmac
from collections.abc import Callable
from datetime import timedelta
from typing import TypeVar

from fastapi import Request
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session as OrmSession

from app.config import get_settings
from app.core.errors import ApiError, NotFound
from app.models import PrivateLookup
from app.modules.privat import rules

T = TypeVar("T")

PER_MINUTE, PER_DAY = 30, 300
MISSES_PER_MINUTE, MISSES_PER_DAY = 10, 50
GLOBAL_MISSES_PER_HOUR = 1000
MESSAGE = "Der er prøvet for mange links fra din forbindelse. Vent lidt, og prøv igen."


class LookupRateLimited(ApiError):
    status_code = 429
    code = "rate_limited"


def client_ip(request: Request) -> str:
    fwd = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
    return fwd or (request.client.host if request.client else "unknown")


def _ip_hash(ip: str) -> str:
    return hmac.new((get_settings().secret_key or "").encode(), f"lookup:{ip}".encode(), hashlib.sha256).hexdigest()


def _count(db: OrmSession, *, ip_hash: str | None, outcome: str | None, since) -> int:
    q = select(func.count()).select_from(PrivateLookup).where(PrivateLookup.created_at >= since)
    if ip_hash is not None:
        q = q.where(PrivateLookup.ip_hash == ip_hash)
    if outcome is not None:
        q = q.where(PrivateLookup.outcome == outcome)
    return int(db.scalar(q) or 0)


def check(db: OrmSession, ip_hash: str) -> None:
    now = rules.now()
    minute, day, hour = now - timedelta(minutes=1), now - timedelta(days=1), now - timedelta(hours=1)
    if (_count(db, ip_hash=ip_hash, outcome="miss", since=minute) >= MISSES_PER_MINUTE
            or _count(db, ip_hash=ip_hash, outcome="miss", since=day) >= MISSES_PER_DAY
            or _count(db, ip_hash=ip_hash, outcome=None, since=minute) >= PER_MINUTE
            or _count(db, ip_hash=ip_hash, outcome=None, since=day) >= PER_DAY
            or _count(db, ip_hash=None, outcome="miss", since=hour) >= GLOBAL_MISSES_PER_HOUR):
        raise LookupRateLimited(MESSAGE)


def guarded(db: OrmSession, request: Request, fn: Callable[[], T]) -> T:
    """Run one public lookup under the limits and record it as a hit or a miss (the miss is committed even though
    the lookup answers 404)."""
    ip_hash = _ip_hash(client_ip(request))
    check(db, ip_hash)
    try:
        out = fn()
    except NotFound:
        db.rollback()
        db.add(PrivateLookup(ip_hash=ip_hash, outcome="miss", created_at=rules.now()))
        db.commit()
        raise
    db.add(PrivateLookup(ip_hash=ip_hash, outcome="hit", created_at=rules.now()))
    return out


def prune(db: OrmSession) -> int:
    r = db.execute(delete(PrivateLookup).where(PrivateLookup.created_at < rules.now() - timedelta(days=2)))
    db.commit()
    return r.rowcount or 0

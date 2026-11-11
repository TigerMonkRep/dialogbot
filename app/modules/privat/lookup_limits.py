"""Rate limits on the PUBLIC lookups of invitation and group links (by token or 8-character short code), so codes
cannot be enumerated.

Per IP (a keyed hash of it is stored, never the IP): all lookups 30/minute and 300/day; misses (unknown, revoked or
expired codes) are counted far more strictly: 10/minute and 50/day. On top of that a global ceiling on misses
(1000/hour across all IPs) stops enumeration spread over many addresses. Over a limit → 429 `rate_limited`, also for
codes that exist, so the answer reveals nothing.

The IP is `client_ip()`: with CLIENT_IP_SECRET set, the visitor address the web BFF signed, else the X-Forwarded-For
entry Render's edge appended (TRUSTED_PROXY_HOPS from the right); without it the first X-Forwarded-For entry (legacy,
forgeable – F-PS-02). The web BFF forwards and signs the visitor's address when it proxies these calls server-side.

The same module holds the overall budget on Privat verification SMS (`sms_budget`, F-PS-01).
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


CLIENT_IP_HEADER, CLIENT_IP_SIG_HEADER = "x-dialogbot-client-ip", "x-dialogbot-client-ip-sig"


def client_ip_sig(secret: str, ip: str) -> str:
    return hmac.new(secret.encode(), f"client-ip:{ip}".encode(), hashlib.sha256).hexdigest()


def client_ip(request: Request) -> str:
    """The address the per-IP limits count (F-PS-02).

    With CLIENT_IP_SECRET set: the visitor IP the web BFF signed (X-Dialogbot-Client-IP + -Sig), else the
    X-Forwarded-For entry TRUSTED_PROXY_HOPS from the right. Assumption: every request to the API passes Render's edge
    (Cloudflare → Render load balancer), which APPENDS the connecting address – so the right-most entry is the real
    caller and everything to its left may be written by the client. Without the secret: the first entry (legacy), so
    the BFF's server-side calls keep counting each visitor until the web side signs."""
    s = get_settings()
    fwd = [p.strip() for p in (request.headers.get("x-forwarded-for") or "").split(",") if p.strip()]
    if s.client_ip_secret:
        ip, sig = request.headers.get(CLIENT_IP_HEADER, "").strip(), request.headers.get(CLIENT_IP_SIG_HEADER, "")
        if ip and hmac.compare_digest(sig.strip().lower(), client_ip_sig(s.client_ip_secret, ip)):
            return ip
        if fwd:
            return fwd[-min(s.trusted_proxy_hops, len(fwd))]
    elif fwd:
        return fwd[0]
    return request.client.host if request.client else "unknown"


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


# Privat verification SMS (group-link joins and /phone/start), on top of the per-link/per-number/resend limits: per
# caller IP, per account (the group's owner, or the user verifying their own number) and for all of Privat, per hour.
# Counted as keyed hashes in private_lookups under their own keys, so they never mix with the lookup counts.
SMS_PER_IP_HOUR = 10
SMS_GLOBAL_HOUR = 300
SMS_MESSAGE = "Der er sendt for mange koder. Prøv igen senere."


def _sms_key(kind: str, value: str) -> str:
    return hmac.new((get_settings().secret_key or "").encode(), f"privat-sms:{kind}:{value}".encode(),
                    hashlib.sha256).hexdigest()


def sms_budget(db: OrmSession, *, ip: str, account: str, per_account: int) -> None:
    """Spend one verification SMS for `account` from `ip`, or raise 429 when a limit for the hour is reached (F-PS-01:
    minting more links, rotating numbers or accounts never buys unbounded SMS). Call right before sending; the rows
    are committed with the request (a failed send rolls them back)."""
    hour = rules.now() - timedelta(hours=1)
    keys = {"ip": _sms_key("ip", ip), "account": _sms_key("account", account), "all": _sms_key("all", "*")}
    limits = {"ip": SMS_PER_IP_HOUR, "account": per_account, "all": SMS_GLOBAL_HOUR}
    for kind, key in keys.items():
        if _count(db, ip_hash=key, outcome=None, since=hour) >= limits[kind]:
            if kind == "all":
                import structlog

                structlog.get_logger("dialogbot.privat.sms").warning("privat.sms_global_ceiling", limit=SMS_GLOBAL_HOUR)
            raise LookupRateLimited(SMS_MESSAGE)
    now = rules.now()
    for key in keys.values():
        db.add(PrivateLookup(ip_hash=key, outcome="hit", created_at=now))
    db.flush()


def prune(db: OrmSession) -> int:
    r = db.execute(delete(PrivateLookup).where(PrivateLookup.created_at < rules.now() - timedelta(days=2)))
    db.commit()
    return r.rowcount or 0

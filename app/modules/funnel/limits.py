"""Per-IP limits on the public funnel endpoints (no login, no CAPTCHA): a bot must not be able to burn SMS codes or
Places lookups. Counted in private_lookups (the same keyed-IP-hash table the invitation lookups use – only an HMAC
of the address is stored, rows are pruned after two days by the worker), under a funnel-specific bucket so the two
limits never mix. Over a limit → 429 `rate_limited`."""
from __future__ import annotations

import hashlib
import hmac
from datetime import UTC, datetime, timedelta

from fastapi import Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session as OrmSession

from app.config import get_settings
from app.core.errors import ApiError
from app.models import PrivateLookup
from app.modules.privat.lookup_limits import client_ip

# bucket → (per IP per hour, global per hour)
LIMITS = {"create": (20, 2000), "patch": (300, 20000), "places": (30, 3000), "gate": (5, 300), "verify": (30, 3000)}
MESSAGE = "Der er sendt mange forespørgsler fra din forbindelse. Vent lidt, og prøv igen."


class FunnelRateLimited(ApiError):
    status_code = 429
    code = "rate_limited"


def _hash(bucket: str, ip: str) -> str:
    return hmac.new((get_settings().secret_key or "").encode(), f"funnel:{bucket}:{ip}".encode(),
                    hashlib.sha256).hexdigest()


def _hash_global(bucket: str) -> str:
    return _hash(bucket, "*")


def _count(db: OrmSession, ip_hash: str, since: datetime) -> int:
    return int(db.scalar(select(func.count()).select_from(PrivateLookup).where(
        PrivateLookup.ip_hash == ip_hash, PrivateLookup.created_at >= since)) or 0)


def hit(db: OrmSession, request: Request, bucket: str) -> None:
    """Count one request in `bucket` for the caller's IP; raise when the hour's limit is reached. Called first in a
    request and committed at once, so a request that fails later (wrong code, Places error) still counts."""
    per_ip, per_all = LIMITS[bucket]
    now = datetime.now(UTC)
    hour = now - timedelta(hours=1)
    ip_hash, all_hash = _hash(bucket, client_ip(request)), _hash_global(bucket)
    if _count(db, ip_hash, hour) >= per_ip or _count(db, all_hash, hour) >= per_all:
        raise FunnelRateLimited(MESSAGE)
    db.add(PrivateLookup(ip_hash=ip_hash, outcome="hit", created_at=now))
    db.add(PrivateLookup(ip_hash=all_hash, outcome="hit", created_at=now))
    db.commit()

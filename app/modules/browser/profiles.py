"""Which booking engine does this business use? Found once from its public website, then remembered.

Detection itself is browser_worker/engine_detect.py (pure). Fetching goes through app/core/safe_fetch.py: every address is
resolved and checked (no internal addresses), redirects are followed by hand, robots.txt is honoured, size/time are capped.
"""
from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from app.core import safe_fetch
from app.models import BusinessBookingProfile
from browser_worker import engine_detect

KNOWN_TTL = timedelta(days=90)    # a business rarely changes booking system
UNKNOWN_TTL = timedelta(days=7)   # «unknown» is looked at again sooner (we may have learned a new signature)

Fetch = Callable[[str], tuple[str, str]]


def normalize_website(raw: str) -> tuple[str, str]:
    """-> (host, canonical url). Raises ValueError when it is not a plain http(s) website."""
    s = (raw or "").strip()
    if not s:
        raise ValueError("website is empty")
    if "//" not in s:
        s = "https://" + s
    p = urlsplit(s)
    host = (p.hostname or "").lower().rstrip(".")
    if p.scheme not in ("http", "https") or not host or "." not in host:
        raise ValueError("not a website")
    return host, f"{p.scheme}://{host}{p.path or '/'}"


def default_fetch(url: str) -> tuple[str, str]:
    page = safe_fetch.get(url, budget=safe_fetch.Budget(max_pages=1, page_bytes=500_000, timeout=8.0))
    if "html" not in (page.content_type or "").lower():
        raise safe_fetch.FetchFailed("content_type", page.content_type or "")
    return page.url, page.text


def get_or_detect(db: OrmSession, *, website: str, cvr: str | None = None, phone: str | None = None,
                  fetch: Fetch | None = None, now: datetime | None = None) -> BusinessBookingProfile:
    """The stored profile when fresh, otherwise detect (front page + booking links) and store. Never raises on a failing
    fetch: the profile then says «unknown» and is looked at again after UNKNOWN_TTL."""
    now = now or datetime.now(UTC)
    host, url = normalize_website(website)
    row = db.scalar(select(BusinessBookingProfile).where(BusinessBookingProfile.website_host == host))
    if row is not None:
        ttl = UNKNOWN_TTL if row.engine == "unknown" else KNOWN_TTL
        if now - row.detected_at < ttl:
            changed = False
            if cvr and not row.cvr:
                row.cvr, changed = cvr, True
            if phone and not row.phone_e164:
                row.phone_e164, changed = phone, True
            if changed:
                db.flush()
            return row
    d = engine_detect.detect(url, fetch or default_fetch)
    if row is None:
        row = BusinessBookingProfile(website_host=host, website=url)
        db.add(row)
    row.engine, row.confidence, row.booking_url = d.engine, d.confidence, (d.booking_url or "")[:1000] or None
    row.detected_at = now
    row.cvr = cvr or row.cvr
    row.phone_e164 = phone or row.phone_e164
    db.flush()
    return row

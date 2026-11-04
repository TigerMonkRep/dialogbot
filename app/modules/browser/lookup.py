"""«find_business»: who is this business? CVR register (name, address, phone, CVR number, reklamebeskyttet) and Google Places
(website and opening hours: the website comes from Google ONLY; phone only as a fallback), remembered in `external_business_contacts` so the same lookup is not paid
for twice.

- Without GOOGLE_PLACES_API_KEY the website lookup is skipped (we have no website, so the track is the phone).
- Without CVR credentials the register part is skipped.
- Google content is cached for GOOGLE_PLACES_CACHE_DAYS only (Google's rules); `place_id` is kept. `scrub_expired` drops the rest.
- CVR facts are public register data and are refreshed after CVR_TTL.
Nothing here is verified against the real register or the real Places API.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from difflib import SequenceMatcher

import structlog
from sqlalchemy import select, update
from sqlalchemy.orm import Session as OrmSession

from app.config import get_settings
from app.core.errors import ApiError, ValidationFailed
from app.models import ExternalBusinessContact
from app.modules.business import cvr as cvr_register
from app.modules.privat import places, rules
from app.modules.sales import places as gp

log = structlog.get_logger("dialogbot.browser")

CVR_TTL = timedelta(days=30)
_LEGAL_SUFFIX = re.compile(r"\b(aps|a/s|as|ivs|k/s|i/s|p/s|smba|fmba|amba|holding)\b\.?", re.IGNORECASE)


@dataclass
class Business:
    id: str
    name: str
    address: str
    city: str | None
    phone_e164: str | None
    phone_kind: str
    website: str | None
    opening_hours: list | None
    cvr: str | None
    advertising_protected: bool | None
    place_id: str | None
    sources: tuple[str, ...]


def _norm(s: str | None) -> str:
    return re.sub(r"[^\wæøå]+", " ", _LEGAL_SUFFIX.sub("", (s or "").lower())).strip()


def _similar(a: str, b: str) -> float:
    return SequenceMatcher(None, _norm(a), _norm(b)).ratio()


def key_for(name: str, city: str | None) -> str:
    return f"{_norm(name)}|{_norm(city)}"[:300]


def _phone(contacts: list[str]) -> str | None:
    for c in contacts:
        if "@" in c or not c.replace(" ", "").replace("+", "").isdigit():
            continue
        e164, kind = places.classify_phone(c)
        if e164 and kind != "invalid":
            return e164
    return None


def google_configured() -> bool:
    return bool(get_settings().google_places_api_key) or gp._override is not None


def _cvr_part(name: str, city: str | None) -> dict | None:
    if not cvr_register.configured():
        return None
    try:
        hits = cvr_register.search_by_name(name, city)
    except ApiError as e:
        log.warning("browser.cvr_lookup_failed", code=e.code)
        return None
    best = max(hits, key=lambda h: _similar(name, h["legal_name"]), default=None)
    if best is None or _similar(name, best["legal_name"]) < 0.75 or not cvr_register.cvr_valid(best["cvr"]):
        return None
    return best


def _google_part(db: OrmSession, ctx, name: str, city: str | None) -> dict | None:
    if not google_configured():
        return None
    c = places.client()
    try:
        places._rate(db, ctx.ws_id)
        center = places._center(db, ctx, c, None, None, city)
        found, _ = c.search(text_query=f"{name} i {city}" if city else name, included_type=None, center=center,
                            radius_m=places.RADIUS_M)
        found = [p for p in found if p.business_status in (None, "OPERATIONAL")]
        best = max(found, key=lambda p: _similar(name, p.name), default=None)
        if best is None or _similar(name, best.name) < 0.6:
            return None
        d = c.details(best.id)
    except (gp.PlacesError, ApiError) as e:
        log.warning("browser.places_lookup_failed", error=type(e).__name__)
        return None
    e164, kind = places.classify_phone(d.phone_international or d.phone_national)
    return {"place_id": best.id, "name": best.name, "address": best.address, "website": getattr(d, "website", None),
            "periods": d.periods, "phone": e164 if kind in ("business", "mobile") else None}


def _row_for(db: OrmSession, *, cvr: str | None, phone: str | None, key: str) -> ExternalBusinessContact | None:
    for col, val in ((ExternalBusinessContact.cvr, cvr), (ExternalBusinessContact.lookup_key, key),
                     (ExternalBusinessContact.phone_e164, phone)):
        if val:
            row = db.scalar(select(ExternalBusinessContact).where(col == val))
            if row is not None:
                return row
    return None


def _out(row: ExternalBusinessContact, sources: tuple[str, ...]) -> Business:
    _, kind = places.classify_phone(row.phone_e164)
    return Business(id=str(row.id), name=row.name, address=row.address or "", city=row.city, phone_e164=row.phone_e164,
                    phone_kind=kind, website=row.website, opening_hours=row.opening_hours, cvr=row.cvr,
                    advertising_protected=row.advertising_protected, place_id=row.place_id, sources=sources)


def find_business(db: OrmSession, ctx, name: str, city: str | None = None, *, now: datetime | None = None) -> Business | None:
    """A cached business, or a fresh lookup. None when neither source knows it."""
    name = " ".join((name or "").split())[:200]
    city = " ".join((city or "").split())[:100] or None
    if not name:
        raise ValidationFailed("Skriv virksomhedens navn", field_errors=[{"field": "name"}])
    now = now or rules.now()
    key = key_for(name, city)
    ttl = timedelta(days=get_settings().google_places_cache_days)
    row = db.scalar(select(ExternalBusinessContact).where(ExternalBusinessContact.lookup_key == key))
    need_cvr = row is None or row.cvr_looked_up_at is None or now - row.cvr_looked_up_at > CVR_TTL
    need_google = google_configured() and (row is None or row.google_looked_up_at is None or now - row.google_looked_up_at > ttl)
    if row is not None and not need_cvr and not need_google:
        return _out(row, ("cache",))
    cvr_hit = _cvr_part(name, city) if need_cvr else None
    g = _google_part(db, ctx, name, city) if need_google else None
    if row is None:
        if cvr_hit is None and g is None:
            return None
        cvr_no = cvr_hit["cvr"] if cvr_hit else None
        phone = (_phone(cvr_hit["contacts"]) if cvr_hit else None) or (g or {}).get("phone")
        row = _row_for(db, cvr=cvr_no, phone=phone, key=key)
        if row is None:
            # the name people know (Google's, else what the user wrote), not the register's legal name («… ApS»)
            row = ExternalBusinessContact(name=(g["name"] if g else name)[:200])
            db.add(row)
        row.lookup_key = row.lookup_key or key
    sources: list[str] = []
    if cvr_hit:
        sources.append("cvr")
        row.cvr = row.cvr or cvr_hit["cvr"]
        row.address = row.address or cvr_hit["address_line"]
        row.city = row.city or cvr_hit["city"] or city
        row.advertising_protected = cvr_hit["advertising_protected"]
        phone = _phone(cvr_hit["contacts"])
        if phone and not row.phone_e164:
            row.phone_e164 = phone                       # CVR first ...
        row.cvr_looked_up_at = now
    if need_cvr and not cvr_hit:
        row.cvr_looked_up_at = now if cvr_register.configured() else row.cvr_looked_up_at
    if g:
        sources.append("google")
        row.place_id = g["place_id"]
        row.address = row.address or g["address"]
        row.city = row.city or city
        row.website = g["website"] or row.website         # the website comes from Google only
        row.opening_hours = g["periods"]
        if g["phone"] and not row.phone_e164:
            row.phone_e164 = g["phone"]                  # ... Google only as the fallback
        row.google_looked_up_at = now
    elif need_google:
        row.google_looked_up_at = now
    db.flush()
    return _out(row, tuple(sources))


def scrub_expired(db: OrmSession, now: datetime | None = None) -> int:
    """Google's caching rule: after GOOGLE_PLACES_CACHE_DAYS only the place_id may stay. Website and opening hours that came
    from Google go; the CVR number, the CVR phone and the register facts stay (public register data)."""
    now = now or rules.now()
    cutoff = now - timedelta(days=get_settings().google_places_cache_days)
    res = db.execute(update(ExternalBusinessContact).where(ExternalBusinessContact.google_looked_up_at < cutoff)
                     .values(website=None, opening_hours=None, google_looked_up_at=None))
    db.flush()
    return res.rowcount or 0

"""Find the business to call (add-on «Ring for mig»).

Uses the existing Google Places client (app/modules/sales/places.py – not duplicated): one Text Search with Pro fields,
then Place Details (phone, opening hours, rating) ONLY for the ≤ 3 candidates shown. Without GOOGLE_PLACES_API_KEY in
this process the search logs one clear warning and uses DemoPlaces (fictitious, numbers in the 1x range that can never
be dialled). FakeProvider/dev uses a tiny fixture of fictional Aarhus bike shops (FixturePlaces).

Google's caching rules: only place_id is stored long-term (private_calls.place_id). Other Places content in a proposal
(address, phone, opening hours as next_open_at) lives on the call/message and is scrubbed after GOOGLE_PLACES_CACHE_DAYS
(scrub_cached). Search results themselves are never stored; only a count row for the 30/hour rate limit.

Numbers: only Danish numbers that sales.service.danish_number accepts (+45, 8 digits, not 1x/90) can be dialled.
A mobile-looking number needs the user's «Det er en virksomhed» before a proposal is made.
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timedelta

import structlog
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session as OrmSession

from app.config import get_settings
from app.core.errors import ApiError, Conflict, ValidationFailed
from app.models import PrivateBusinessSearch, PrivateCall, PrivateMessage
from app.modules.privat import rules
from app.modules.sales import places as gp

log = structlog.get_logger("dialogbot.privat")

SEARCHES_PER_HOUR = 30
MAX_RESULTS = 3
RADIUS_M = 15_000
# Danish mobile ranges (numbering plan): a number here may be a person, so the user confirms it is a business.
MOBILE_PREFIXES = ("2", "30", "31", "40", "41", "42", "50", "51", "52", "53", "60", "61", "71", "81", "91", "92", "93")
CITY_CENTERS = {"aarhus": (56.1567, 10.2108), "københavn": (55.6761, 12.5683), "odense": (55.4038, 10.4024),
                "aalborg": (57.0488, 9.9217), "esbjerg": (55.4765, 8.4594), "randers": (56.4607, 10.0364),
                "kolding": (55.4904, 9.4722), "vejle": (55.7113, 9.5357), "horsens": (55.8607, 9.8503)}
DEFAULT_CENTER = CITY_CENTERS["aarhus"]
_warned = {"key": False}


class SearchRateLimited(ApiError):
    status_code = 429
    code = "rate_limited"


# --------------------------------------------------------------------------- clients

class FixturePlaces:
    """FakeProvider/dev only: the fictional Aarhus bike shops of the prototype, behind the Places interface. Unlike
    DemoPlaces they can be "dialled" in dev/test (against a faked Vapi); outside dev/test approve refuses them."""

    source = "fixture"

    def _fixtures(self):
        from app.modules.privat.chat import FIXTURES

        return FIXTURES

    def search(self, *, text_query: str, included_type, center, radius_m: int, page_token=None):
        low = text_query.lower()
        hits = [f for f in self._fixtures() if any(w in low for w in ("cykel", f["name"].lower()))]
        return [gp.Place(id=f["id"], name=f["name"], address=f["address"], lat=f.get("lat"), lng=f.get("lng"),
                         business_status="OPERATIONAL", maps_uri=f"https://maps.example.invalid/{f['id']}")
                for f in hits], None

    def details(self, place_id: str) -> gp.Details:
        f = next(x for x in self._fixtures() if x["id"] == place_id)
        periods = [{"open": {"day": d, "hour": 9, "minute": 0}, "close": {"day": d, "hour": 17, "minute": 30}}
                   for d in range(1, 6)]
        return gp.Details(phone_national=rules.phone_display(f["phone"]), phone_international=f["phone"],
                          rating=f.get("rating"), user_rating_count=f.get("rating_count"), periods=periods)

    def geocode(self, text: str):
        return None


def client():
    """Google when the key is set; FixturePlaces with FakeProvider in dev/test; else DemoPlaces with one warning."""
    if gp._override is not None:
        return gp._override
    s = get_settings()
    if s.google_places_api_key:
        return gp.GooglePlaces(s.google_places_api_key)
    if s.ai_provider == "fake" and s.app_env in ("dev", "test"):
        return FixturePlaces()
    if not _warned["key"]:
        log.warning("privat.places_key_missing",
                    detail="GOOGLE_PLACES_API_KEY mangler i API-tjenesten – virksomhedssøgning bruger fiktive demodata")
        _warned["key"] = True
    return gp.DemoPlaces()


# --------------------------------------------------------------------------- numbers and hours

def classify_phone(raw: str | None) -> tuple[str | None, str]:
    """(e164 or None, kind): business | mobile | invalid | none."""
    from app.modules.sales.service import danish_number

    if not raw:
        return None, "none"
    try:
        n = danish_number(raw)
    except ValidationFailed:
        return None, "invalid"
    return n, "mobile" if n[3:].startswith(MOBILE_PREFIXES) else "business"


def _minutes(day_google: int, hour: int, minute: int) -> int:
    """Minutes since Monday 00:00 (Google's day 0 = Sunday)."""
    return ((day_google - 1) % 7) * 1440 + hour * 60 + minute


def is_open(periods: list[dict] | None, t: datetime) -> bool | None:
    if not periods:
        return None
    lt = rules.local(t)
    m = lt.weekday() * 1440 + lt.hour * 60 + lt.minute
    for p in periods:
        o, c = p.get("open") or {}, p.get("close")
        if c is None:  # open 24/7
            return True
        a = _minutes(o.get("day", 0), o.get("hour", 0), o.get("minute", 0))
        b = _minutes(c.get("day", 0), c.get("hour", 0), c.get("minute", 0))
        if (a <= b and a <= m < b) or (a > b and (m >= a or m < b)):  # a period across Sunday→Monday wraps
            return True
    return False


def next_call_time(periods: list[dict] | None, after: datetime) -> datetime | None:
    """The first moment (15-minute steps, within 8 days) the business is open AND we may call (weekday 08–18)."""
    t = rules.local(after).replace(second=0, microsecond=0)
    t += timedelta(minutes=(15 - t.minute % 15) % 15)
    for _ in range(8 * 24 * 4):
        if rules.in_call_hours(t) and is_open(periods, t) is not False:
            return t
        t += timedelta(minutes=15)
    return None


# --------------------------------------------------------------------------- search

def _center(db: OrmSession, ctx, c, lat: float | None, lng: float | None, city: str | None) -> tuple[float, float]:
    if lat is not None and lng is not None:
        return lat, lng
    p = ctx.profile
    city = (city or "").strip() or p.location_city or p.location_postcode
    if not city and p.location_lat is not None and p.location_lng is not None:
        return p.location_lat, p.location_lng
    if city:
        if (known := CITY_CENTERS.get(city.lower())) is not None:
            return known
        try:
            if (g := c.geocode(f"{city}, Danmark")) is not None:
                return g
        except gp.PlacesError:
            pass
    if getattr(c, "source", "") != "google":
        return DEFAULT_CENTER  # demo data is in Aarhus
    raise Conflict("Hvilken by skal jeg lede i?", code="needs_location")


def _rate(db: OrmSession, ws_id: uuid.UUID) -> None:
    n = db.scalar(select(func.count()).select_from(PrivateBusinessSearch).where(
        PrivateBusinessSearch.workspace_id == ws_id, PrivateBusinessSearch.created_at >= rules.now() - timedelta(hours=1)))
    if (n or 0) >= SEARCHES_PER_HOUR:
        raise SearchRateLimited("Du har søgt mange gange den sidste time. Prøv igen lidt senere.")
    db.add(PrivateBusinessSearch(workspace_id=ws_id, created_at=rules.now()))
    db.flush()


def search(db: OrmSession, ctx, q: str, *, lat: float | None = None, lng: float | None = None,
           city: str | None = None) -> list[dict]:
    """At most 3 candidates: Text Search (Pro fields) in Google's relevance order, operational only, then Place Details
    for those 3 only. Nothing of the result is stored."""
    q = (q or "").strip()[:120]
    if not q:
        raise ValidationFailed("Skriv hvad du leder efter", field_errors=[{"field": "q"}])
    _rate(db, ctx.ws_id)
    c = client()
    center = _center(db, ctx, c, lat, lng, city)
    text = f"{q} i {city.strip()}" if city and city.strip() and city.lower() not in q.lower() else q
    try:
        found, _next = c.search(text_query=text, included_type=None, center=center, radius_m=RADIUS_M)
    except gp.PlacesError as e:
        raise ApiError("Søgningen virker ikke lige nu. Skriv virksomhedens navn og nummer.", code="search_failed",
                       status_code=502) from e
    found = [p for p in found if p.business_status in (None, "OPERATIONAL")][:MAX_RESULTS]
    now = rules.now()
    out = []
    for p in found:
        try:
            d = c.details(p.id)
        except gp.PlacesError:
            d = gp.Details()
        e164, kind = classify_phone(d.phone_international or d.phone_national)
        open_now = is_open(d.periods, now)
        nxt = next_call_time(d.periods, now) if open_now is False else None
        dist = round(gp.distance_km(center, (p.lat, p.lng)), 1) if p.lat is not None and p.lng is not None else None
        out.append({"place_id": p.id, "name": p.name, "address": p.address or "",
                    "phone_display": d.phone_national or rules.phone_display(e164),
                    "phone_e164": e164 if kind in ("business", "mobile") else None, "phone_kind": kind,
                    "rating": d.rating, "rating_count": d.user_rating_count, "open_now": open_now,
                    "next_open_at": nxt.isoformat() if nxt else None,
                    "next_open_text": rules.when_text(nxt) if nxt else None, "distance_km": dist,
                    "maps_url": p.maps_uri, "source": getattr(c, "source", "google")})
    return out


def option_sub(r: dict) -> str:
    bits = [r["address"]]
    if r.get("distance_km") is not None:
        bits.append(f"{str(r['distance_km']).replace('.', ',')} km")
    if r.get("open_now") is True:
        bits.append("åben nu")
    elif r.get("open_now") is False:
        bits.append("lukket nu")
    if r.get("rating"):
        n = f" ({r['rating_count']})" if r.get("rating_count") else ""
        bits.append(f"★ {r['rating']:.1f}".replace(".", ",") + n)
    if r.get("phone_display"):
        bits.append(r["phone_display"])
    return " · ".join(b for b in bits if b)


def set_location(db: OrmSession, ctx, *, city: str | None, postcode: str | None, lat: float | None,
                 lng: float | None) -> None:
    p = ctx.profile
    if lat is not None or lng is not None:
        if lat is None or lng is None or not (54 <= lat <= 58.5 and 7 <= lng <= 16):
            raise ValidationFailed("Placeringen skal være i Danmark", field_errors=[{"field": "lat"}])
    if postcode and not re.fullmatch(r"\d{4}", postcode.strip()):
        raise ValidationFailed("Postnummeret skal have 4 cifre", field_errors=[{"field": "postcode"}])
    p.location_city = (city or "").strip()[:100] or None
    p.location_postcode = (postcode or "").strip() or None
    p.location_lat, p.location_lng = lat, lng


def scrub_cached(db: OrmSession) -> None:
    """Google content older than GOOGLE_PLACES_CACHE_DAYS: keep place_id (and the name/number of a call that was
    actually made, our own call record), drop addresses, opening hours and option texts."""
    cutoff = rules.now() - timedelta(days=get_settings().google_places_cache_days)
    db.execute(update(PrivateCall).where(PrivateCall.place_id.is_not(None), PrivateCall.created_at < cutoff,
                                         PrivateCall.business_address != "")
               .values(business_address="", next_open_at=None))
    for m in db.scalars(select(PrivateMessage).where(PrivateMessage.created_at < cutoff,
                                                     PrivateMessage.options.is_not(None))):
        if any(isinstance(o, dict) and o.get("place_id") for o in m.options or []):
            m.options = [{"id": o.get("id"), "label": o.get("label"), "sub": "", "action": "expired"}
                         if o.get("place_id") else o for o in m.options]
    db.commit()

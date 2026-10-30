"""Google Places API (New): Text Search and Place Details, plus a deterministic demo double.

Verified against Google's documentation on 30 October 2026 (developers.google.com/maps/documentation/places/web-service:
text-search, place-details, data-fields, policies):
- Text Search: POST https://places.googleapis.com/v1/places:searchText, headers X-Goog-Api-Key and X-Goog-FieldMask
  (mandatory). Body: textQuery, includedType (one Table A type), strictTypeFiltering, locationBias.circle
  {center {latitude, longitude}, radius ≤ 50 000 m}, languageCode, regionCode, pageSize (1–20; replaces the
  deprecated maxResultCount), pageToken. At most 60 results across all pages. Fields in the mask carry the `places.`
  prefix; `nextPageToken` is requested in the mask as Google's own examples do.
- Place Details: GET https://places.googleapis.com/v1/places/{id}, same headers, fields WITHOUT the `places.` prefix,
  query params languageCode/regionCode.
- Billing is at the highest SKU the mask touches. In Text Search, id is Essentials (IDs only); displayName,
  formattedAddress, addressComponents, location, types, primaryType, businessStatus, googleMapsUri are Pro;
  websiteUri, phone numbers, regularOpeningHours, rating, userRatingCount are Enterprise. So the search asks only for
  Pro fields and the Enterprise contact fields are fetched with Place Details only for companies we keep.
- Place ids may be stored indefinitely; other Places content may not be cached beyond Google's allowed exceptions
  (the analysis document states 30 days; the policies page we read links to the Service Specific Terms for the exact
  rule) – hence GOOGLE_PLACES_CACHE_DAYS and the refresh job in search.py.

No key → `DemoPlaces`: clearly fictitious companies (.invalid domains, numbers in the unassigned Danish 1x range that
`sales.service.danish_number` refuses to ring), so the whole flow can be tried without Google.
"""
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path

import httpx

from app.config import get_settings

SEARCH_FIELDS = ("places.id,places.displayName,places.formattedAddress,places.addressComponents,places.location,"
                 "places.types,places.primaryType,places.businessStatus,places.googleMapsUri,nextPageToken")
DETAIL_FIELDS = "websiteUri,nationalPhoneNumber,internationalPhoneNumber,regularOpeningHours,rating,userRatingCount"
GEOCODE_FIELDS = "places.id,places.location"
MAX_PAGES = 3  # 3 × 20 = Google's 60-result ceiling per query
PAGE_SIZE = 20
MAX_RADIUS_M = 50_000

# Price per request in øre, for the estimate shown before a search starts. Source: the analysis document
# (docs/sales/intern-salgskanal.md, C.2: Pro $32 and Enterprise $35 per 1,000) at 6.9 kr./USD – NOT re-verified
# against Google's price list, which the documentation pages defer to. Free monthly caps are not subtracted.
SEARCH_REQUEST_COST_MINOR = 22   # Text Search Pro
DETAILS_REQUEST_COST_MINOR = 24  # Place Details Enterprise


class PlacesError(Exception):
    def __init__(self, message: str, *, retryable: bool = False, status: int | None = None):
        super().__init__(message)
        self.retryable = retryable
        self.status = status


@dataclass
class Place:
    id: str
    name: str
    address: str | None = None
    postal_code: str | None = None
    city: str | None = None
    lat: float | None = None
    lng: float | None = None
    types: list[str] = field(default_factory=list)
    primary_type: str | None = None
    business_status: str | None = None
    maps_uri: str | None = None


@dataclass
class Details:
    website: str | None = None
    phone_national: str | None = None
    phone_international: str | None = None
    opening_hours: list[str] | None = None
    rating: float | None = None
    user_rating_count: int | None = None


def _component(components: list, kind: str) -> str | None:
    for c in components or []:
        if kind in (c.get("types") or []):
            return c.get("longText") or c.get("shortText")
    return None


def parse_place(p: dict) -> Place:
    addr = p.get("formattedAddress")
    comps = p.get("addressComponents") or []
    postal = _component(comps, "postal_code")
    city = _component(comps, "postal_town") or _component(comps, "locality")
    if not postal and addr and (m := re.search(r"\b(\d{4})\s+([^,]+)", addr)):
        postal, city = m.group(1), city or m.group(2).strip()
    loc = p.get("location") or {}
    return Place(id=str(p.get("id") or ""), name=((p.get("displayName") or {}).get("text") or "").strip(),
                 address=addr, postal_code=postal, city=city, lat=loc.get("latitude"), lng=loc.get("longitude"),
                 types=list(p.get("types") or []), primary_type=p.get("primaryType"),
                 business_status=p.get("businessStatus"), maps_uri=p.get("googleMapsUri"))


def parse_details(d: dict) -> Details:
    hours = (d.get("regularOpeningHours") or {}).get("weekdayDescriptions")
    return Details(website=d.get("websiteUri"), phone_national=d.get("nationalPhoneNumber"),
                   phone_international=d.get("internationalPhoneNumber"),
                   opening_hours=list(hours) if hours else None, rating=d.get("rating"),
                   user_rating_count=d.get("userRatingCount"))


class GooglePlaces:
    source = "google"

    def __init__(self, api_key: str, *, transport: httpx.BaseTransport | None = None):
        s = get_settings()
        self.key, self.search_url, self.details_url = api_key, s.google_places_url, s.google_places_details_url
        self.transport = transport

    def _client(self) -> httpx.Client:
        return httpx.Client(timeout=20.0, transport=self.transport)

    def _check(self, r: httpx.Response) -> dict:
        if r.status_code == 200:
            return r.json() or {}
        # Never echo the request (it carries the key in a header); Google's message is safe to show.
        try:
            msg = ((r.json() or {}).get("error") or {}).get("message") or ""
        except ValueError:
            msg = ""
        raise PlacesError(f"Google Places svarede {r.status_code}{f': {msg[:200]}' if msg else ''}",
                          retryable=r.status_code in (429, 500, 502, 503, 504), status=r.status_code)

    def search(self, *, text_query: str, included_type: str | None, center: tuple[float, float], radius_m: int,
               page_token: str | None = None) -> tuple[list[Place], str | None]:
        body: dict = {"textQuery": text_query, "languageCode": "da", "regionCode": "DK", "pageSize": PAGE_SIZE,
                      "locationBias": {"circle": {"center": {"latitude": center[0], "longitude": center[1]},
                                                  "radius": float(min(radius_m, MAX_RADIUS_M))}}}
        if included_type:
            body |= {"includedType": included_type, "strictTypeFiltering": True}
        if page_token:
            body["pageToken"] = page_token
        try:
            with self._client() as c:
                r = c.post(self.search_url, json=body,
                           headers={"X-Goog-Api-Key": self.key, "X-Goog-FieldMask": SEARCH_FIELDS})
        except httpx.HTTPError as e:
            raise PlacesError("Google Places kunne ikke nås", retryable=True) from e
        data = self._check(r)
        return [parse_place(p) for p in data.get("places") or []], data.get("nextPageToken") or None

    def details(self, place_id: str) -> Details:
        try:
            with self._client() as c:
                r = c.get(f"{self.details_url}/{place_id}", params={"languageCode": "da", "regionCode": "DK"},
                          headers={"X-Goog-Api-Key": self.key, "X-Goog-FieldMask": DETAIL_FIELDS})
        except httpx.HTTPError as e:
            raise PlacesError("Google Places kunne ikke nås", retryable=True) from e
        return parse_details(self._check(r))

    def geocode(self, text: str) -> tuple[float, float] | None:
        try:
            with self._client() as c:
                r = c.post(self.search_url, json={"textQuery": text, "languageCode": "da", "regionCode": "DK",
                                                  "pageSize": 1},
                           headers={"X-Goog-Api-Key": self.key, "X-Goog-FieldMask": GEOCODE_FIELDS})
        except httpx.HTTPError as e:
            raise PlacesError("Google Places kunne ikke nås", retryable=True) from e
        places = self._check(r).get("places") or []
        loc = (places[0].get("location") or {}) if places else {}
        return (loc["latitude"], loc["longitude"]) if "latitude" in loc else None


DEMO_FILE = Path(__file__).parent / "data" / "demo_places.json"


def distance_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lng1, lat2, lng2 = map(math.radians, (*a, *b))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lng2 - lng1) / 2) ** 2
    return 6371.0 * 2 * math.asin(math.sqrt(h))


class DemoPlaces:
    """Deterministic stand-in with the same interface. Every company is fictitious."""

    source = "demo"

    def __init__(self, data: list[dict] | None = None):
        self.data = data if data is not None else json.loads(DEMO_FILE.read_text(encoding="utf-8"))["places"]
        self.calls: list[tuple] = []

    def search(self, *, text_query: str, included_type: str | None, center: tuple[float, float], radius_m: int,
               page_token: str | None = None) -> tuple[list[Place], str | None]:
        self.calls.append(("search", text_query, included_type, page_token))
        term = text_query.split(" i ")[0].strip().lower()
        hits = []
        for p in self.data:
            loc = p.get("location") or {}
            if distance_km(center, (loc["latitude"], loc["longitude"])) * 1000 > radius_m:
                continue
            if included_type:
                if included_type not in p.get("types", []):
                    continue
            elif term not in p["displayName"]["text"].lower() and term not in " ".join(p.get("searchTerms", [])):
                continue
            hits.append(p)
        start = int(page_token or 0)
        page = hits[start:start + PAGE_SIZE]
        nxt = str(start + PAGE_SIZE) if start + PAGE_SIZE < min(len(hits), PAGE_SIZE * MAX_PAGES) else None
        return [parse_place(p) for p in page], nxt

    def details(self, place_id: str) -> Details:
        self.calls.append(("details", place_id))
        for p in self.data:
            if p["id"] == place_id:
                return parse_details(p.get("details") or {})
        raise PlacesError("Ukendt sted", status=404)

    def geocode(self, text: str) -> tuple[float, float] | None:
        self.calls.append(("geocode", text))
        return None


_override = None


def set_client_override(c) -> None:
    """Test hook."""
    global _override
    _override = c


def client(source: str | None = None):
    """The Places client. `source` is a job's recorded source: a job created as "google" must run against Google –
    never silently on demo data – so a process without the key raises instead."""
    if _override is not None:
        return _override
    key = get_settings().google_places_api_key
    if source == "google" and not key:
        raise PlacesError("GOOGLE_PLACES_API_KEY mangler på workeren – søgningen kan ikke køre mod Google. Sæt "
                          "nøglen på worker-tjenesten og genoptag søgningen.")
    if source == "demo":
        return DemoPlaces()
    return GooglePlaces(key) if key else DemoPlaces()

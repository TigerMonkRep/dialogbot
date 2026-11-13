"""Find businesses for a campaign: a market, a city and a category in, candidate leads out.

1. The market is checked against the matrix first – a blocked or held market is never searched.
2. Google Places (Text Search, GOOGLE_PLACES_API_KEY) gives name, address, website and phone.
3. The business's own website (front page + one contact page, through app/core/safe_fetch: public addresses only,
   robots.txt respected) gives the e-mail address it publishes itself. That page is kept as the source – it is what
   implied consent rests on in CA and AU and what the footer names in the GDPR markets.
Nothing is stored here: the operator picks from the candidates, and only those go through the ComplianceEngine as leads.
"""
from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from urllib.parse import urljoin, urlparse

import httpx

from app.config import get_settings
from app.core import safe_fetch
from app.core.errors import NotImplementedYet, ValidationFailed
from app.modules.knowledge import importer
from app.modules.outreach.compliance import matrix as m
from app.modules.outreach.schemas import NICHES
from app.modules.sales.research import sanitize

FIELDS = ("places.id,places.displayName,places.formattedAddress,places.addressComponents,places.websiteUri,"
          "places.internationalPhoneNumber,places.businessStatus")
QUERY = {"plumber": "plumber", "hvac": "HVAC contractor", "dentist": "dentist", "med spa": "med spa",
         "auto repair": "auto repair shop", "hair salon": "hair salon"}
MAX_RESULTS = 20
_EMAIL = re.compile(r"[a-z0-9][a-z0-9._%+-]{0,63}@(?:[a-z0-9-]+\.)+[a-z]{2,}", re.I)
_NOT_AN_ADDRESS = re.compile(r"\.(png|jpe?g|gif|webp|svg|css|js)$|@(sentry|example|domain|email|yourdomain)\.|wixpress\.com$|"
                             r"^(noreply|no-reply|donotreply)@", re.I)
_CONTACT = re.compile(r"contact|kontakt|about|get-in-touch|enquir", re.I)

_transport: httpx.BaseTransport | None = None
_fetch = None


def set_overrides(*, transport: httpx.BaseTransport | None = None, fetch=None) -> None:
    """Test hook: a mock transport for Google Places and a stand-in for safe_fetch.get."""
    global _transport, _fetch
    _transport, _fetch = transport, fetch


@dataclass
class Candidate:
    company_name: str
    country: str
    city: str | None
    niche: str
    website: str | None = None
    phone: str | None = None
    email: str | None = None
    email_source: str = "unknown"
    email_source_url: str | None = None
    context: str | None = None
    problem: str | None = None       # why this one cannot be used (shown to the operator), else None


def market_open(country: str) -> tuple[bool, str]:
    """May this market be searched for e-mail leads at all? (False, why) for blocked, held and unknown markets."""
    j = m.MATRIX.get(country)
    if j is None:
        return False, "Markedet er ikke i den godkendte matrix."
    if j.status == "blocked":
        return False, "Opt-in-marked: kold e-mail er ikke tilladt her."
    if j.status == "hold" and country not in get_settings().outreach_signed_off:
        return False, "Markedet afventer juridisk godkendelse (OUTREACH_SIGNED_OFF_MARKETS)."
    return True, ""


def pick_email(html: str, site_host: str) -> str | None:
    """The address a business publishes: one on its own domain first, then a generic mailbox, then the first found."""
    found: list[str] = []
    for e in _EMAIL.findall(html.replace("%40", "@")):
        e = e.strip(".").lower()
        if not _NOT_AN_ADDRESS.search(e) and e not in found:
            found.append(e)
    if not found:
        return None
    host = site_host.removeprefix("www.")
    own = [e for e in found if e.rsplit("@", 1)[1] == host]
    pool = own or found
    return next((e for e in pool if e.split("@", 1)[0] in m.ROLE_LOCAL_PARTS), pool[0])


def _published(site: str) -> tuple[str | None, str | None, str | None]:
    """(email, page it was read on, page text) from the front page, else from one contact/about page."""
    fetch = _fetch or (lambda u, b: safe_fetch.get(u, budget=b))
    budget = safe_fetch.Budget(max_pages=2, page_bytes=600_000, timeout=8.0)
    try:
        first = fetch(site, budget)
    except (safe_fetch.FetchBlocked, safe_fetch.FetchFailed):
        return None, None, None
    host = urlparse(first.url).hostname or ""
    _title, text, links = importer.parse(first.text)
    text = sanitize(text)[0][:3000]
    email = pick_email(first.text, host)
    if email:
        return email, first.url, text
    nxt = next((urljoin(first.url, h) for h in links if _CONTACT.search(h)
                and (urlparse(urljoin(first.url, h)).hostname or "") == host), None)
    if nxt:
        try:
            page = fetch(nxt, budget)
            email = pick_email(page.text, host)
            if email:
                return email, page.url, text
        except (safe_fetch.FetchBlocked, safe_fetch.FetchFailed):
            pass
    return None, None, text


def _component(place: dict, kind: str, short: bool = False) -> str | None:
    for c in place.get("addressComponents") or []:
        if kind in (c.get("types") or []):
            return c.get("shortText" if short else "longText")
    return None


def search(*, country: str, city: str, niche: str, limit: int = 10) -> list[Candidate]:
    s = get_settings()
    country = m.normalize_country(country)
    ok, why = market_open(country)
    if not ok:
        raise ValidationFailed(why, code="market_closed", field_errors=[{"field": "country", "message": why}])
    if niche not in NICHES:
        raise ValidationFailed("Ukendt kategori", field_errors=[{"field": "niche"}])
    if not s.google_places_api_key and _transport is None:
        raise NotImplementedYet("Virksomhedssøgning kræver GOOGLE_PLACES_API_KEY. Upload en CSV i stedet, eller sæt nøglen.",
                                code="places_not_configured")
    region = "GB" if country == "UK" else country
    try:
        with httpx.Client(timeout=20.0, transport=_transport) as c:
            r = c.post(s.google_places_url, headers={"X-Goog-Api-Key": s.google_places_api_key or "", "X-Goog-FieldMask": FIELDS},
                       json={"textQuery": f"{QUERY[niche]} in {city}", "regionCode": region, "languageCode": "en",
                             "pageSize": max(1, min(limit, MAX_RESULTS))})
    except httpx.HTTPError as e:
        raise ValidationFailed("Google Places kunne ikke nås – prøv igen.", code="places_unreachable") from e
    if r.status_code != 200:
        raise ValidationFailed(f"Google Places svarede {r.status_code}.", code="places_error")
    places = [p for p in (r.json() or {}).get("places") or []
              if p.get("businessStatus", "OPERATIONAL") == "OPERATIONAL" and (_component(p, "country", short=True) or region) == region]

    def one(p: dict) -> Candidate:
        cand = Candidate(company_name=(p.get("displayName") or {}).get("text") or "", country=country, niche=niche,
                         city=_component(p, "locality") or _component(p, "postal_town") or city,
                         website=p.get("websiteUri"), phone=p.get("internationalPhoneNumber"))
        if not cand.website:
            cand.problem = "Ingen hjemmeside – ingen offentliggjort e-mail at skrive til."
            return cand
        email, source, text = _published(cand.website)
        cand.context = f"Website ({cand.website}): {text}" if text else None
        if not email:
            cand.problem = "Ingen e-mailadresse fundet på hjemmesiden."
            return cand
        cand.email, cand.email_source, cand.email_source_url = email, "published_website", source
        return cand

    with ThreadPoolExecutor(max_workers=6) as pool:
        return list(pool.map(one, places[:MAX_RESULTS]))


def as_dict(c: Candidate) -> dict:
    return asdict(c)

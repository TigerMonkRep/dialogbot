"""Find Danish companies in Dialogbot's industries and their social profiles, for the operator to follow by hand.

Why by hand: Meta and TikTok forbid automated following, liking and messaging, and their APIs do not offer it. So the
system does the lawful half — *finding* — and the operator does the human half from the dashboard. Nothing here
touches the platforms at all; the only calls go to the CVR register and the companies' own websites.

How a batch is made (once a day, or on the operator's button):
1. Pick the industry that has had the fewest prospects so far (round robin over the six site industries).
2. Ask the CVR register for active companies in that industry's branch codes (DB07), skipping companies that have
   asked not to be contacted for marketing (`reklamebeskyttet`) and companies already in the table. A random seed
   spreads the picks over the whole register rather than always the same first page.
3. Open each company's website (from CVR's contact details), read the HTML and keep the Facebook / Instagram /
   TikTok profile links. Companies without a website or without any profile link are dropped.
4. Store the rest with a short suggested comment written from the industry's own wording on dialogbot.dk.
"""
from __future__ import annotations

import datetime as dt
import random
import re
from html import unescape
from zoneinfo import ZoneInfo

import httpx
import structlog
from sqlalchemy import func, select
from sqlalchemy.orm import Session as OrmSession

from app.config import get_settings
from app.models import SocialProspect
from app.modules.business import cvr as cvr_register

log = structlog.get_logger("dialogbot.social.prospects")

COPENHAGEN = ZoneInfo("Europe/Copenhagen")
BATCH_SIZE = 20          # prospects per day; well under what a person follows by hand in a day
CANDIDATES_PER_RUN = 120  # CVR hits to look at to find BATCH_SIZE with a social profile
SITE_TIMEOUT = 6.0
SITE_MAX_BYTES = 400_000

# Dialogbot's industries (same keys/wording as web/src/lib/industries.ts) with their DB07 branch codes and the
# comment the operator can post. The comments state nothing about the company and promise nothing — a greeting
# from one small Danish business to another. NOT externally verified: the branch codes follow Danmarks Statistik's
# DB07 list as published; check a code in CVR if a batch looks off.
INDUSTRIES: dict[str, dict] = {
    "haandvaerkere": {
        "label": "Håndværkere",
        "codes": ["432100", "432200", "433200", "433410", "433420", "439910", "433300", "439100", "412000"],
        "comment": "Flot arbejde! Hilsen fra Dialogbot – vi hjælper håndværkere med at få taget telefonen, når hænderne er optaget.",
    },
    "klinikker": {
        "label": "Klinikker",
        "codes": ["862300", "869010", "869020", "869030", "862100", "869090"],
        "comment": "Dejligt at se en klinik, der er aktiv herinde. Hilsen fra Dialogbot – vi tager telefonen for klinikker, når der er patienter i stolen.",
    },
    "frisoerer": {
        "label": "Frisører og saloner",
        "codes": ["960210", "960220"],
        "comment": "Skønt arbejde! Hilsen fra Dialogbot – vi tager telefonen for saloner, mens I har hænderne i håret på en kunde.",
    },
    "autovaerksteder": {
        "label": "Autoværksteder",
        "codes": ["452010", "452020", "452030", "454000"],
        "comment": "Godt gået! Hilsen fra Dialogbot – vi hjælper værksteder med at få svaret på opkald, mens I ligger under bilen.",
    },
    "raadgivere": {
        "label": "Rådgivere og kontorer",
        "codes": ["692000", "691000", "702200", "711100", "661900", "682000"],
        "comment": "Hilsen fra Dialogbot – vi tager telefonen for rådgivere og kontorer, når I sidder i møde.",
    },
    "restauranter": {
        "label": "Restauranter og hoteller",
        "codes": ["561010", "561020", "563000", "551010", "562100"],
        "comment": "Det ser lækkert ud! Hilsen fra Dialogbot – vi tager imod bordbestillinger i telefonen, når køkkenet har travlt.",
    },
}

CVR_SOURCE = [
    "Vrvirksomhed.cvrNummer",
    "Vrvirksomhed.virksomhedMetadata.nyesteNavn",
    "Vrvirksomhed.virksomhedMetadata.nyesteBeliggenhedsadresse",
    "Vrvirksomhed.virksomhedMetadata.nyesteHovedbranche",
    "Vrvirksomhed.virksomhedMetadata.sammensatStatus",
    "Vrvirksomhed.virksomhedMetadata.nyesteKontaktoplysninger",
    "Vrvirksomhed.reklamebeskyttet",
]

_SOCIAL_RE = re.compile(
    r"https?://(?:www\.|m\.|da-dk\.)?(facebook\.com|instagram\.com|tiktok\.com)/([A-Za-z0-9_.@\-/]+)", re.I)
_SOCIAL_SKIP = ("sharer", "share", "share.php", "plugins", "dialog", "login", "policies", "privacy", "help", "intent",
                "hashtag", "explore", "p/", "reel/", "tr?", "legal", "about", "pages/", "groups/", "events/",
                "accounts/", "embed", "music/", "tag/", "discover", "upload", "video/")
# sammensatStatus values that mean the company is gone (the register writes them in mixed case)
_CLOSED = {"Ophørt", "OPHØRT", "ophørt", "Opløst", "OPLØST", "opløst", "Under konkurs", "UNDER KONKURS",
           "Under tvangsopløsning", "UNDER TVANGSOPLØSNING", "Opløst efter konkurs", "OPLØST EFTER KONKURS",
           "Opløst efter frivillig likvidation", "OPLØST EFTER FRIVILLIG LIKVIDATION"}
_URL_RE = re.compile(r"(?:https?://)?(?:www\.)?[a-z0-9æøå.-]+\.[a-z]{2,}(?:/\S*)?", re.I)


def _now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def configured() -> bool:
    return cvr_register.configured()


# --- CVR ------------------------------------------------------------------------------------------------------------------

def _cvr_candidates(industry: str, *, size: int, seed: int) -> list[dict]:
    """Active, non-advertising-protected companies in the industry's branch codes, in a seeded random order."""
    s = get_settings()
    codes = INDUSTRIES[industry]["codes"]
    body = {
        "_source": CVR_SOURCE, "size": size,
        "query": {"function_score": {
            "query": {"bool": {
                "filter": [
                    {"terms": {"Vrvirksomhed.virksomhedMetadata.nyesteHovedbranche.branchekode": codes}},
                ],
                "must_not": [
                    {"term": {"Vrvirksomhed.reklamebeskyttet": True}},
                    {"terms": {"Vrvirksomhed.virksomhedMetadata.sammensatStatus": list(_CLOSED)}},
                ],
            }},
            "random_score": {"seed": seed, "field": "_seq_no"},
        }},
    }
    r = httpx.post(s.cvr_url, json=body, auth=(s.cvr_username, s.cvr_password), timeout=20.0)
    if r.status_code >= 400:
        raise RuntimeError(f"CVR-registret afviste søgningen ({r.status_code})")
    hits = ((r.json() or {}).get("hits") or {}).get("hits") or []
    out = []
    for h in hits:
        v = (h.get("_source") or {}).get("Vrvirksomhed") or {}
        if v.get("reklamebeskyttet") is True:
            continue  # belt and braces: never suggest a company that asked not to be contacted
        p = cvr_register.parse(h)
        if not _active(p.get("status")):
            continue
        contacts = (v.get("virksomhedMetadata") or {}).get("nyesteKontaktoplysninger") or []
        p["website"] = _website_from_contacts(contacts)
        out.append(p)
    return out


def _active(status: str | None) -> bool:
    st = (status or "").lower()
    return not any(w in st for w in ("ophørt", "opløst", "konkurs", "tvangsopløsning", "likvidation"))


def _website_from_contacts(contacts: list) -> str | None:
    for c in contacts:
        c = str(c).strip()
        if "@" in c or not c or c.replace(" ", "").replace("+", "").isdigit():
            continue
        if _URL_RE.fullmatch(c):
            return c if c.lower().startswith("http") else f"https://{c}"
    return None


# --- the company's website ------------------------------------------------------------------------------------------------

def social_links(html: str) -> dict[str, str]:
    """The first Facebook, Instagram and TikTok *profile* links in a page (share buttons and the like skipped)."""
    found: dict[str, str] = {}
    for m in _SOCIAL_RE.finditer(unescape(html)):
        host, path = m.group(1).lower(), m.group(2)
        path = path.split("?")[0].split("#")[0].strip("/")
        if not path or any(path.lower().startswith(x) or f"/{x}" in path.lower() for x in _SOCIAL_SKIP):
            continue
        key = host.split(".")[0]
        if key not in found:
            handle = path.split("/")[0] if key != "facebook" else path
            found[key] = f"https://www.{host}/{handle}"
    return found


def fetch_social_links(website: str) -> dict[str, str]:
    try:
        with httpx.Client(follow_redirects=True, timeout=SITE_TIMEOUT,
                          headers={"User-Agent": "Mozilla/5.0 (compatible; DialogbotBot/1.0; +https://www.dialogbot.dk)"}) as c:
            with c.stream("GET", website) as r:
                if r.status_code >= 400 or "html" not in (r.headers.get("content-type") or ""):
                    return {}
                buf = b""
                for chunk in r.iter_bytes():
                    buf += chunk
                    if len(buf) > SITE_MAX_BYTES:
                        break
        return social_links(buf.decode("utf-8", errors="ignore"))
    except (httpx.HTTPError, ValueError) as e:
        log.info("social.prospects.site_failed", website=website, error=type(e).__name__)
        return {}


# --- the batch ------------------------------------------------------------------------------------------------------------

def next_industry(db: OrmSession) -> str:
    counts = dict(db.execute(select(SocialProspect.industry, func.count()).group_by(SocialProspect.industry)).all())
    return min(INDUSTRIES, key=lambda k: (counts.get(k, 0), k))


def discover(db: OrmSession, *, industry: str | None = None, limit: int = BATCH_SIZE, now: dt.datetime | None = None,
             fetch=fetch_social_links) -> list[SocialProspect]:
    """Make today's batch. Returns the prospects added (empty when CVR is not configured or nothing was found)."""
    if not configured():
        log.warning("social.prospects.cvr_not_configured")
        return []
    now = now or _now()
    today = now.astimezone(COPENHAGEN).date()
    industry = industry or next_industry(db)
    seen = set(db.scalars(select(SocialProspect.cvr)).all())
    added: list[SocialProspect] = []
    try:
        candidates = _cvr_candidates(industry, size=CANDIDATES_PER_RUN, seed=random.randint(1, 10**9))
    except (httpx.HTTPError, RuntimeError, ValueError) as e:
        log.warning("social.prospects.cvr_failed", error=f"{type(e).__name__}: {e}")
        return []
    for c in candidates:
        if len(added) >= limit:
            break
        if not c["cvr"] or c["cvr"] in seen or not c.get("website"):
            continue
        links = fetch(c["website"])
        if not links:
            continue
        seen.add(c["cvr"])
        row = SocialProspect(
            cvr=c["cvr"], name=c["legal_name"][:200] or c["cvr"], industry=industry, industry_text=c.get("industry"),
            city=c.get("city"), website=c["website"][:300], facebook_url=links.get("facebook"),
            instagram_url=links.get("instagram"), tiktok_url=links.get("tiktok"),
            suggested_comment=INDUSTRIES[industry]["comment"], status="new", found_on=today)
        db.add(row)
        added.append(row)
    db.commit()
    log.info("social.prospects.batch", industry=industry, candidates=len(candidates), added=len(added))
    return added


def discover_if_due(db: OrmSession, *, now: dt.datetime | None = None) -> int:
    """Worker hook: one batch per Copenhagen day, made in the morning so it is ready when the operator looks."""
    now = now or _now()
    local = now.astimezone(COPENHAGEN)
    if local.hour < 6:
        return 0
    if db.scalar(select(func.count()).select_from(SocialProspect).where(SocialProspect.found_on == local.date())):
        return 0
    return len(discover(db, now=now))


def to_dict(p: SocialProspect) -> dict:
    return {"id": str(p.id), "cvr": p.cvr, "name": p.name, "industry": p.industry,
            "industry_label": INDUSTRIES.get(p.industry, {}).get("label", p.industry), "industry_text": p.industry_text,
            "city": p.city, "website": p.website, "facebook_url": p.facebook_url, "instagram_url": p.instagram_url,
            "tiktok_url": p.tiktok_url, "suggested_comment": p.suggested_comment, "status": p.status,
            "found_on": p.found_on.isoformat(), "acted_platforms": p.acted_platforms, "note": p.note,
            "acted_at": p.acted_at.isoformat() if p.acted_at else None}

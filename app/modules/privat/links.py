"""«Hvor kan den købes?» – a verified buy link for a list item.

The chat model never writes a link itself. It calls find_buy_link (or sets find_links on create_list/add_items), and
this module does the work in three steps, outside the chat turn's context:

1. Search: one small, focused model call with Anthropic's server-side web search, asked for up to three candidate
   *product pages* at Danish shops, as JSON. The chat model never sees the search results (they are 15-25k tokens
   per turn – the reason the chat felt slow).
2. Verify: every candidate is fetched. It must answer 200, must not be a search or category page, and the HTML must
   look like a product page (schema.org Product / og:type product / «Læg i kurv» / a price). A Saxo search URL the
   model made up, or a 404 dressed as a page, never gets through.
3. Set: the first verified link goes on the item, with shop and price in the note; the chat says so.

Items are searched in parallel (one model call each), so a wishlist with three products takes about as long as one.
"""
from __future__ import annotations

import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from urllib.parse import urlparse

from app.config import get_settings
from app.modules.ai.provider import AIProviderError, get_provider

log = logging.getLogger(__name__)

MAX_ITEMS = 4
SEARCH_MAX_TOKENS = 700
FETCH_TIMEOUT = 6.0
UA = "Mozilla/5.0 (compatible; Dialogbot/1.0; +https://dialogbot.app)"

SEARCH_SYSTEM = """Du finder, hvor et produkt kan købes online i Danmark – til en ønskeliste.
Søg med web_search (gerne 2-3 søgninger: dansk butik, produktnavn + "køb", evt. engelsk titel).
Svar KUN med JSON, en liste med op til 3 kandidater, bedste først:
[{"url": "https://…", "shop": "Butikkens navn", "price": "129 kr." eller null, "title": "produktets navn på siden"}]
Krav til url: den konkrete PRODUKTSIDE, hvor varen kan lægges i kurven – aldrig en søgeside, kategoriside, forside,
prissammenligning (PriceRunner o.l.) eller markedsplads med brugte varer. Foretræk danske webshops (.dk, priser i kr.).
Brug kun URL'er, du har set i søgeresultaterne – opfind aldrig en URL. Finder du intet brugbart, svar []."""

SEARCHY = re.compile(r"(/search|/soeg|/s%C3%B8g|/søg|[?&](q|query|search|s|keyword|text)=|/catalogsearch|/find\b|/kategori|/category|/c/)", re.I)
COMPARE_HOSTS = ("pricerunner", "prisjagt", "google.", "bing.", "duckduckgo", "amazon.", "ebay.", "dba.dk", "facebook.", "youtube.")
PRODUCT_SIGNALS = (
    re.compile(r'"@type"\s*:\s*"Product"', re.I),
    re.compile(r'property="og:type"\s+content="(product|og:product)"|content="(product|og:product)"\s+property="og:type"', re.I),
    re.compile(r'itemtype="https?://schema\.org/Product"', re.I),
    re.compile(r"læg i kurv|tilføj til kurv|læg i indkøbskurv|køb nu|add to cart|add-to-cart|addtocart|add_to_cart|i kurven", re.I),
)
PRICE_RE = re.compile(r"(\d{1,3}(?:[.\s]\d{3})*(?:,\d{2})?)\s*(?:kr\.?|DKK)|(?:kr\.?|DKK)\s*(\d{1,3}(?:[.\s]\d{3})*(?:,\d{2})?)", re.I)
NOT_FOUND_RE = re.compile(r"siden findes ikke|findes ikke\.|page not found|404|kunne ikke findes|ingen resultater|no results", re.I)


@dataclass
class BuyLink:
    item: str
    url: str | None
    shop: str | None = None
    price: str | None = None
    title: str | None = None
    tried: int = 0

    @property
    def found(self) -> bool:
        return bool(self.url)


def enabled() -> bool:
    s = get_settings()
    return s.ai_provider in ("anthropic", "fake") and s.privat_web_search


# --------------------------------------------------------------------------- 1. search

def search_candidates(item: str, city: str | None) -> tuple[list[dict], object | None]:
    """Up to three candidate product pages for `item`, from one model call with web search. Returns (candidates,
    completion) – the completion is recorded in ai_usage by the caller (this runs in a worker thread, without a db)."""
    s = get_settings()
    provider = get_provider()
    if provider.name == "fake":
        return [], None
    loc: dict = {"type": "approximate", "country": "DK", "timezone": "Europe/Copenhagen"}
    if city:
        loc["city"] = city[:100]
    tools = [{"type": "web_search_20250305", "name": "web_search", "max_uses": 3, "user_location": loc}]
    try:
        c = provider.complete(system=SEARCH_SYSTEM, messages=[{"role": "user", "content": f"Produkt: {item}"}],
                              max_tokens=SEARCH_MAX_TOKENS, tools=tools, model=s.privat_ai_model_id, effort="low")
    except AIProviderError:
        log.warning("privat links: search failed for %r", item, exc_info=True)
        return [], None
    return parse_candidates(c.text), c


def parse_candidates(text: str) -> list[dict]:
    m = re.search(r"\[.*\]", text or "", re.S)
    if not m:
        return []
    try:
        raw = json.loads(m.group(0))
    except ValueError:
        return []
    out = []
    for x in raw if isinstance(raw, list) else []:
        if isinstance(x, dict) and isinstance(x.get("url"), str) and x["url"].startswith(("https://", "http://")):
            out.append({"url": x["url"].strip()[:1000], "shop": str(x.get("shop") or "").strip()[:80] or None,
                        "price": str(x.get("price") or "").strip()[:40] or None,
                        "title": str(x.get("title") or "").strip()[:200] or None})
    return out[:3]


# --------------------------------------------------------------------------- 2. verify

def fetch(url: str) -> tuple[int, str, str]:
    """(status, final_url, html[:300k]) – replaced in tests. Through the SSRF-safe fetcher: the URL comes from a model,
    so every hop must be a public http(s) address."""
    from app.modules.privat import safe_fetch

    f = safe_fetch.fetch(url, max_bytes=1_000_000)
    return f.status, f.url, f.text[:300_000]


def looks_like_search(url: str) -> bool:
    u = urlparse(url)
    host = (u.hostname or "").lower()
    if any(h in host for h in COMPARE_HOSTS):
        return True
    path = u.path or "/"
    if path in ("", "/") and not u.query:
        return True
    return bool(SEARCHY.search(path + ("?" + u.query if u.query else "")))


def is_product_page(html: str) -> bool:
    head = html[:200_000]
    if len(head) < 500:
        return False
    title = re.search(r"<title[^>]*>(.*?)</title>", head, re.I | re.S)
    if title and NOT_FOUND_RE.search(title.group(1)):
        return False
    hits = sum(1 for p in PRODUCT_SIGNALS if p.search(head))
    return hits >= 1 and (hits >= 2 or bool(PRICE_RE.search(head)))


def price_from(html: str) -> str | None:
    m = re.search(r'"price"\s*:\s*"?(\d+(?:[.,]\d{1,2})?)"?', html[:200_000])
    if m:
        v = m.group(1).replace(".", ",")
        return f"{v[:-3] if v.endswith(',00') else v} kr."
    return None


def verify(url: str) -> tuple[str, str | None] | None:
    """(final_url, price) when the page is a real product page, else None."""
    if looks_like_search(url):
        return None
    try:
        status, final, html = fetch(url)
    except Exception:  # noqa: BLE001 – timeouts, TLS, DNS: the candidate is just not usable
        return None
    if status != 200 or looks_like_search(final) or not is_product_page(html):
        return None
    return final, price_from(html)


# --------------------------------------------------------------------------- 3. find

def find_one(item: str, city: str | None) -> tuple[BuyLink, object | None]:
    cands, completion = search_candidates(item, city)
    out = BuyLink(item=item, url=None, tried=len(cands))
    for cand in cands:
        ok = verify(cand["url"])
        if ok is None:
            continue
        out.url, out.shop, out.title = ok[0], cand.get("shop") or shop_name(ok[0]), cand.get("title")
        out.price = ok[1] or cand.get("price")
        break
    return out, completion


def shop_name(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    host = re.sub(r"^(www|shop|m)\.", "", host)
    return host.split(".")[0].capitalize() if host else "butikken"


def find_buy_links(items: list[str], city: str | None) -> list[tuple[BuyLink, object | None]]:
    """Verified links for up to MAX_ITEMS items, searched in parallel."""
    items = [x.strip()[:200] for x in items if x and x.strip()][:MAX_ITEMS]
    if not items:
        return []
    if len(items) == 1:
        return [find_one(items[0], city)]
    with ThreadPoolExecutor(max_workers=len(items)) as ex:
        return list(ex.map(lambda x: find_one(x, city), items))

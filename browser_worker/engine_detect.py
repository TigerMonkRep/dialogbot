"""Recognise which booking engine a business uses, from its public website (front page + booking links only).

Pure functions: the HTML is fetched by the caller (app/modules/browser/profiles.py uses app/core/safe_fetch, which
resolves and checks addresses, honours robots.txt and follows redirects by hand). The result is stored per business in
`business_booking_profiles`, so the site is not looked up on every run.

!!! The SIGNATURES are NOT verified against real pages. They are what a booking widget typically leaves in a page
(a script or iframe from the vendor's domain, a link to the vendor's booking page). Correct them here, in one block. !!!
"""
from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

# engine -> regexes matched against the host + path of a script/iframe/link/form/anchor URL. NOT verified.
SIGNATURES: dict[str, list[str]] = {
    "onlinebooq": [r"onlinebooq"],
}
# a link on the business's own site that probably leads to online booking
BOOKING_LINK_RE = re.compile(r"\bbook(?:ing|e)?\b|bestil\s*(?:en\s+)?tid|online\s*booking|reserver\s+tid|book\s+tid", re.IGNORECASE)
MAX_PAGES = 3          # front page + at most two booking pages
CONFIDENCE_EMBED = 0.9  # a script/iframe/form from the engine's own address
CONFIDENCE_LINK = 0.8   # an ordinary link to it
MIN_CONFIDENCE = 0.6


@dataclass
class Detection:
    engine: str = "unknown"
    confidence: float = 0.0
    booking_url: str | None = None
    evidence: list[str] = field(default_factory=list)
    pages_checked: list[str] = field(default_factory=list)


class _Refs(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.embeds: list[tuple[str, str]] = []   # (tag, url): script/iframe/form/link[rel=stylesheet]
        self.anchors: list[tuple[str, str]] = []  # (text, url)
        self._a: list | None = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ("script", "iframe") and a.get("src"):
            self.embeds.append((tag, a["src"]))
        elif tag == "form" and a.get("action"):
            self.embeds.append(("form", a["action"]))
        elif tag == "link" and a.get("href"):
            self.embeds.append(("link", a["href"]))
        elif tag == "a" and a.get("href"):
            self._a = [a["href"], (a.get("aria-label") or "") + " "]

    def handle_data(self, data):
        if self._a is not None:
            self._a[1] += data

    def handle_endtag(self, tag):
        if tag == "a" and self._a is not None:
            self.anchors.append((" ".join(self._a[1].split()), self._a[0]))
            self._a = None


def parse_refs(html: str) -> _Refs:
    p = _Refs()
    p.feed(html or "")
    p.close()
    return p


def _sig_match(url: str) -> str | None:
    try:
        parts = urlsplit(url)
    except ValueError:
        return None
    hay = f"{parts.hostname or ''}{parts.path}".lower()
    for engine, patterns in SIGNATURES.items():
        if any(re.search(p, hay) for p in patterns):
            return engine
    return None


def detect_in_html(html: str, page_url: str) -> Detection:
    refs = parse_refs(html)
    best = Detection()
    for tag, url in refs.embeds:
        eng = _sig_match(url)
        if eng and CONFIDENCE_EMBED > best.confidence:
            best = Detection(eng, CONFIDENCE_EMBED, None, [f"{tag} {url[:160]}"])
    for text, url in refs.anchors:
        eng = _sig_match(url)
        if eng:
            full = urljoin(page_url, url)
            if CONFIDENCE_LINK > best.confidence:
                best = Detection(eng, CONFIDENCE_LINK, full, [f"a «{text[:60]}» {url[:160]}"])
            elif best.engine == eng and best.booking_url is None:
                best.booking_url = full
    return best


def booking_links(html: str, page_url: str, site_host: str) -> list[str]:
    """Same-site links whose text or address says «book/booking/bestil tid» (the pages worth one more fetch)."""
    out: list[str] = []
    for text, url in parse_refs(html).anchors:
        full = urljoin(page_url, url)
        host = (urlsplit(full).hostname or "").lower()
        if urlsplit(full).scheme not in ("http", "https"):
            continue
        if not (host == site_host or host.endswith("." + site_host)):
            continue
        if (BOOKING_LINK_RE.search(text) or BOOKING_LINK_RE.search(urlsplit(full).path)) and full not in out:
            out.append(full)
    return out


def detect(website: str, fetch: Callable[[str], tuple[str, str]]) -> Detection:
    """`fetch(url) -> (final_url, html)` raises on a refused/failed fetch (that page is then simply skipped)."""
    site_host = (urlsplit(website if "//" in website else "//" + website).hostname or "").lower()
    start = website if "//" in website else "https://" + website
    if not urlsplit(start).path:
        start += "/"
    result = Detection()
    queue = [start]
    seen: list[str] = []
    first_booking_link: str | None = None
    while queue and len(seen) < MAX_PAGES:
        url = queue.pop(0)
        if url in seen:
            continue
        try:
            final_url, html = fetch(url)
        except Exception:  # noqa: BLE001 – a page we cannot read is not evidence
            seen.append(url)
            continue
        seen.append(url)
        d = detect_in_html(html, final_url)
        if d.confidence > result.confidence:
            result = Detection(d.engine, d.confidence, d.booking_url or final_url, d.evidence)
        links = booking_links(html, final_url, site_host)
        first_booking_link = first_booking_link or (links[0] if links else None)
        if result.confidence < MIN_CONFIDENCE:
            queue.extend(u for u in links if u not in seen and u not in queue)
    result.pages_checked = seen
    if result.confidence < MIN_CONFIDENCE:
        return Detection("unknown", 0.0, first_booking_link, [], seen)
    return result

"""Orkestrering: crawl, kør tjek, saml i en Report."""
from __future__ import annotations

import re
import urllib.robotparser
from collections import deque
from datetime import datetime, timezone
from urllib.parse import urldefrag, urlparse

from . import checks as C
from .fetch import Fetcher, Response
from .parse import Page, parse_html
from .psi import run_psi
from .report import Report

_SKIP_EXT = re.compile(r"\.(png|jpe?g|gif|webp|avif|svg|ico|pdf|zip|mp3|mp4|webm|woff2?|ttf|css|js|json|xml|txt|webmanifest)$", re.I)


def _clean(url: str) -> str:
    """Fjerner #fragment og ?query, så /signup?plan=x ikke tæller som en ny side."""
    return urldefrag(url)[0].split("?")[0]


def scan(start_url: str, fetcher: Fetcher | None = None, max_pages: int = 60, psi: bool = False, psi_key: str | None = None,
         psi_strategy: str = "mobile") -> Report:
    fetcher = fetcher or Fetcher()
    if "://" not in start_url:
        start_url = "https://" + start_url
    p = urlparse(start_url)
    origin = f"{p.scheme}://{p.netloc}"
    notes: list[str] = []
    results: list[C.Result] = []

    home = fetcher.get(origin + "/")
    if home.error:
        raise RuntimeError(f"Kunne ikke hente {origin}: {home.error}")
    final = urlparse(home.final_url)
    root = f"{final.scheme}://{final.netloc}"
    host_key = C._norm_host(root)

    robots = fetcher.get(f"{root}/robots.txt")
    results += C.robots_checks(root, robots)
    rp = urllib.robotparser.RobotFileParser()
    rp.parse(robots.text.splitlines() if robots.ok else [])

    sm = fetcher.get(f"{root}/sitemap.xml")
    sm_items, sm_err = C.parse_sitemap(sm) if sm.ok else ([], None)
    for loc, _ in list(sm_items):  # sitemap-index: hent under-sitemaps
        if loc.endswith(".xml"):
            sub = fetcher.get(loc)
            sm_items += C.parse_sitemap(sub)[0] if sub.ok else []
    sitemap_urls = list(dict.fromkeys(_clean(loc) for loc, _ in sm_items if not loc.endswith(".xml")))

    # --- crawl ----------------------------------------------------------------------------------
    responses: dict[str, Response] = {root + "/": home}
    pages: dict[str, Page] = {}
    queue: deque[str] = deque([root + "/", *sitemap_urls])
    seen: set[str] = set()
    fetched_sitemap: dict[str, tuple[int, int]] = {}
    while queue:
        url = queue.popleft()
        key = url.rstrip("/")
        if key in seen:
            continue
        seen.add(key)
        if C._norm_host(url) != host_key or _SKIP_EXT.search(urlparse(url).path) or not rp.can_fetch("*", url):
            continue
        if len(responses) >= max_pages and url not in sitemap_urls:
            continue
        resp = responses.get(url) or fetcher.get(url, accept="text/html,*/*")
        responses[url] = resp
        if url in sitemap_urls:
            fetched_sitemap[url] = (resp.status, len(resp.redirects))
        if resp.ok and resp.content_type in ("text/html", "application/xhtml+xml"):
            page = parse_html(resp.text, resp.final_url)
            pages[url] = page
            for ln in page.internal_links():
                nxt = _clean(ln.href)
                if nxt.rstrip("/") not in seen:
                    queue.append(nxt)
    status_of = {u: r.status for u, r in responses.items()}
    status_of.update({u.rstrip("/"): r.status for u, r in responses.items()})

    # --- tjek -----------------------------------------------------------------------------------
    sitemap_keys = {u.rstrip("/") for u in sitemap_urls}
    noindex_pages = {u for u, p in pages.items() if C.is_noindex(p, responses[u]) and u.rstrip("/") not in sitemap_keys}
    for url, page in pages.items():
        results += C.page_checks(page, responses[url], in_sitemap=url.rstrip("/") in sitemap_keys)
    for url, resp in responses.items():
        if url not in pages:
            results.append(C.Result("page_status", C.PASS if resp.ok else C.FAIL, url, f"HTTP {resp.status or resp.error}"))
    results += C.cross_page_checks(pages, skip=noindex_pages)
    results += C.link_checks(pages, status_of, set(sitemap_urls))
    results += C.sitemap_checks(root, sm, sm_items, sm_err, fetched_sitemap)

    http_resp = fetcher.get("http://" + root.split("://", 1)[1] + "/") if root.startswith("https://") else None
    other = ("www." + final.netloc) if not final.netloc.startswith("www.") else final.netloc.removeprefix("www.")
    www_resp = fetcher.get(f"{final.scheme}://{other}/")
    results += C.transport_checks(root, http_resp, www_resp, home)

    home_page = pages.get(root + "/")
    asset = None
    if home_page:
        static = next((s for s in [*home_page.stylesheets, *[x["src"] for x in home_page.scripts]] if s and C._norm_host(s) == host_key), None)
        asset = fetcher.get(static) if static else None
    results += C.asset_cache_check(asset)
    results += C.misc_checks(
        root, fetcher.get(f"{root}/findes-ikke-seo-agent-{int(datetime.now().timestamp())}"),
        fetcher.get(f"{root}/favicon.ico"), fetcher.get(f"{root}/llms.txt"), fetcher.get(f"{root}/.well-known/security.txt"))

    metrics: dict = {}
    if psi:
        psi_results, metrics, psi_notes = run_psi(fetcher, root + "/", psi_key, strategy=psi_strategy)
        results += psi_results
        notes += psi_notes

    return Report(site=root, scanned_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                  pages_scanned=len(pages), results=results, notes=notes, metrics=metrics,
                  page_list=sorted(_p(u) for u in pages), sitemap=sitemap_urls)


def _p(url: str) -> str:
    return urlparse(url).path or "/"

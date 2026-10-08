"""Selve tjekkene. Side-tjek kører pr. crawlet side, site-tjek kører én gang pr. scanning."""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from .fetch import Response
from .parse import Page

PASS, WARN, FAIL, INFO = "pass", "warn", "fail", "info"
UTILITY_PREFIXES = ("/vilkaar", "/privatliv", "/kontakt", "/signup", "/login", "/password", "/verify-email", "/invite")
GENERIC_ANCHORS = {"klik her", "læs mere", "læs mere »", "her", "click here", "read more", "mere", "link"}
STOPWORDS = set("""og i jeg det at en den til er som på de med han af for ikke der var mig sig men et har om vi min havde ham hun nu over da fra du ud sin dem os op man hans hvor eller hvad skal selv her alle vil blev kunne ind når være dog noget ville jo deres efter ned skulle denne end dette mit også under have dig anden hende mine alt meget sit sine vor mod disse hvis din nogle hos blive mange ad bliver hendes været thi jer sådan the and of to a in is you for your that with are our dit jeres vores kan får få uden bare både""".split())


@dataclass
class Result:
    check: str
    status: str
    url: str
    detail: str = ""


def _norm_host(url: str) -> str:
    return urlparse(url).netloc.lower().removeprefix("www.")


def _path(url: str) -> str:
    return urlparse(url).path or "/"


def _is_utility(url: str) -> bool:
    return _path(url).startswith(UTILITY_PREFIXES)


def _is_article(url: str) -> bool:
    parts = [p for p in _path(url).split("/") if p]
    return len(parts) >= 2 and parts[0] == "viden"


def _is_home(url: str) -> bool:
    return _path(url) in ("", "/")


def _ok(cond: bool, check: str, url: str, detail_fail: str = "", detail_pass: str = "", warn: bool = False) -> Result:
    return Result(check, PASS if cond else (WARN if warn else FAIL), url, detail_pass if cond else detail_fail)


# ---------------------------------------------------------------------------------------------------
# Side-tjek
# ---------------------------------------------------------------------------------------------------
def is_noindex(page: Page, resp: Response) -> bool:
    directives = page.robots_directives | {d.strip().lower() for d in resp.headers.get("x-robots-tag", "").split(",") if d.strip()}
    return "noindex" in directives or "none" in directives


def page_checks(page: Page, resp: Response, in_sitemap: bool = True) -> list[Result]:
    """Alle tjek for én side. En side med noindex, som ikke står i sitemap, regnes som bevidst holdt ude af Google
    (login, app, onboarding): den får kun de tekniske tjek, ikke title/canonical/schema-kravene til indekserbare sider."""
    u = page.url
    r: list[Result] = []
    # status / redirect
    r.append(_ok(resp.ok, "page_status", u, f"HTTP {resp.status or resp.error}"))
    r.append(_ok(len(resp.redirects) <= 1, "redirect_chain", u, f"{len(resp.redirects)} redirects: " + " → ".join(f"{s} {x}" for x, s in resp.redirects), warn=True))
    # noindex
    noindex = is_noindex(page, resp)
    if noindex and not in_sitemap:
        r.append(Result("noindex", INFO, u, "noindex – bevidst (siden står ikke i sitemap)"))
        r.append(_ok(bool(page.lang), "lang_attr", u, "mangler lang på <html>"))
        r.append(_ok("viewport" in page.meta, "viewport", u, "mangler viewport"))
        if u.startswith("https://"):
            mixed = [x for x in [*page.stylesheets, *[s["src"] for s in page.scripts], *[i.src for i in page.images]] if x.startswith("http://")]
            r.append(_ok(not mixed, "mixed_content", u, f"{len(mixed)} http-ressourcer: {', '.join(mixed[:2])}"))
        return r
    r.append(_ok(not noindex, "noindex", u, "siden har noindex, men står i sitemap" if in_sitemap else "siden har noindex"))
    # title
    t = page.title or ""
    r.append(_ok(bool(t), "title_present", u, "mangler <title>"))
    if t:
        r.append(_ok(30 <= len(t) <= 65, "title_length", u, f"{len(t)} tegn: «{t}»", warn=True))
    # description
    d = page.meta.get("description", "").strip()
    r.append(_ok(bool(d), "desc_present", u, "mangler meta description"))
    if d:
        r.append(_ok(70 <= len(d) <= 175, "desc_length", u, f"{len(d)} tegn", warn=True))
    # headings
    h1 = page.h1
    r.append(_ok(len(h1) == 1, "h1_single", u, "ingen H1" if not h1 else f"{len(h1)} H1-overskrifter"))
    levels = [lvl for lvl, _ in page.headings]
    skipped = any(b - a > 1 for a, b in zip(levels, levels[1:], strict=False))
    r.append(_ok(not skipped, "heading_order", u, "overskriftsniveau springes over (fx H2→H4)", warn=True))
    # canonical
    r.append(_ok(bool(page.canonical), "canonical_present", u, "mangler canonical"))
    if page.canonical:
        final = resp.final_url if resp.final_url else u
        same = page.canonical.rstrip("/") == final.rstrip("/") or page.canonical.rstrip("/") == u.rstrip("/")
        r.append(_ok(same, "canonical_self", u, f"canonical peger på {page.canonical}"))
    # sprog, viewport, doctype, charset
    r.append(_ok(bool(page.lang), "lang_attr", u, "mangler lang på <html>"))
    r.append(_ok("viewport" in page.meta, "viewport", u, "mangler viewport"))
    charset = "charset" in page.meta or "utf-8" in resp.headers.get("content-type", "").lower()
    r.append(_ok(page.has_doctype and charset, "doctype_charset", u, "doctype eller tegnsæt mangler", warn=True))
    # URL
    path = _path(u)
    bad_url = bool(re.search(r"[A-Z_]", path)) or "?" in u or len(u) > 100
    r.append(_ok(not bad_url, "url_quality", u, "store bogstaver, underscore, parametre eller > 100 tegn", warn=True))
    # indhold
    n = len(page.words)
    if not _is_utility(u):
        r.append(_ok(n >= 300, "thin_content", u, f"kun {n} ord", warn=n >= 100))
    # billeder
    imgs = [i for i in page.images if i.src and not i.src.startswith("data:")]
    if imgs:
        no_alt = [i.src for i in imgs if i.alt is None]
        r.append(_ok(not no_alt, "img_alt", u, f"{len(no_alt)} af {len(imgs)} billeder uden alt: {', '.join(no_alt[:3])}"))
        no_dim = [i.src for i in imgs if not (i.width and i.height)]
        r.append(_ok(not no_dim, "img_dims", u, f"{len(no_dim)} billeder uden width/height", warn=True))
        below = [i for i in imgs[2:] if (i.loading or "").lower() != "lazy"]
        if len(imgs) > 3:
            r.append(_ok(not below, "img_lazy", u, f"{len(below)} billeder under folden uden loading=lazy", warn=True))
    # links
    internal = page.internal_links()
    r.append(_ok(len(internal) >= 3, "internal_links", u, f"kun {len(internal)} interne links", warn=True))
    generic = [ln for ln in page.links if ln.text.strip().lower() in GENERIC_ANCHORS]
    r.append(_ok(not generic, "anchor_text", u, f"{len(generic)} links med generisk tekst (fx «{generic[0].text if generic else ''}»)", warn=True))
    # nøgleord
    if n >= 150 and not _is_utility(u):
        kw = top_keyword(page)
        if kw:
            in_title, in_h1 = kw in t.lower(), any(kw in x.lower() for x in h1)
            r.append(_ok(in_title and in_h1, "keyword_focus", u, f"mest brugte ord «{kw}» mangler i " + ", ".join(
                x for x, ok in (("title", in_title), ("H1", in_h1)) if not ok), warn=True))
    # hastighed
    r.append(_ok(resp.elapsed_ms < 600, "ttfb", u, f"{resp.elapsed_ms} ms", warn=resp.elapsed_ms < 1500, detail_pass=f"{resp.elapsed_ms} ms"))
    r.append(_ok(len(resp.body) < 200_000, "html_size", u, f"{len(resp.body) // 1024} KB HTML", warn=True))
    blocking = [s["src"] for s in page.scripts if s["src"] and s["in_head"] and not (s["async"] or s["defer"] or s["nomodule"])]
    r.append(_ok(not blocking, "render_blocking", u, f"{len(blocking)} blokerende scripts i head", warn=True))
    # sikkerhed
    if u.startswith("https://"):
        mixed = [x for x in [*page.stylesheets, *[s["src"] for s in page.scripts], *[i.src for i in imgs]] if x.startswith("http://")]
        r.append(_ok(not mixed, "mixed_content", u, f"{len(mixed)} http-ressourcer: {', '.join(mixed[:2])}"))
    # sociale
    og_missing = [k for k in ("og:title", "og:description", "og:image", "og:url") if not page.meta.get(k)]
    r.append(_ok(not og_missing, "og_tags", u, "mangler " + ", ".join(og_missing), warn=len(og_missing) < 3))
    r.append(_ok(bool(page.meta.get("twitter:card")), "twitter_card", u, "mangler twitter:card", warn=True))
    # struktureret data
    objs, errors = page.jsonld()
    if page.jsonld_raw:
        r.append(_ok(not errors, "jsonld_valid", u, "; ".join(errors)))
    types = page.schema_types()
    if _is_home(u):
        r.append(_ok(bool(types & {"Organization", "LocalBusiness", "WebSite", "SoftwareApplication", "Corporation"}),
                     "schema_org", u, "ingen Organization/WebSite-schema", warn=bool(types)))
    if _is_article(u):
        r.append(_ok(bool(types & {"Article", "BlogPosting", "FAQPage", "NewsArticle", "HowTo"}), "schema_article", u, "ingen Article/FAQPage-schema", warn=True))
    if not _is_home(u):
        r.append(_ok("BreadcrumbList" in types, "schema_breadcrumb", u, "ingen BreadcrumbList", warn=True))
    return r


def top_keyword(page: Page) -> str | None:
    brand = _norm_host(page.url).split(".")[0]
    words = [w.lower() for w in page.main_words if len(w) > 3 and w.lower() not in STOPWORDS and not w.isdigit() and brand not in w.lower()]
    if not words:
        return None
    word, count = Counter(words).most_common(1)[0]
    return word if count >= 4 else None


# ---------------------------------------------------------------------------------------------------
# Tværgående tjek over alle sider
# ---------------------------------------------------------------------------------------------------
def cross_page_checks(pages: dict[str, Page], skip: set[str] | None = None) -> list[Result]:
    """Unikke titler/beskrivelser på tværs af sider. `skip` er sider (fx noindex), der ikke konkurrerer i Google."""
    pages = {u: p for u, p in pages.items() if u not in (skip or set())}
    r: list[Result] = []
    for check, getter in (("title_unique", lambda p: (p.title or "").strip().lower()),
                          ("desc_unique", lambda p: p.meta.get("description", "").strip().lower())):
        groups: dict[str, list[str]] = defaultdict(list)
        for url, p in pages.items():
            if (val := getter(p)):
                groups[val].append(url)
        dupes = {v: urls for v, urls in groups.items() if len(urls) > 1}
        dupe_urls = {u for urls in dupes.values() for u in urls}
        for url, p in pages.items():
            if getter(p):
                others = sorted({_path(x) for v in dupes.values() if url in v for x in v if x != url})
                r.append(_ok(url not in dupe_urls, check, url, "deles med " + ", ".join(others[:3]) + (" …" if len(others) > 3 else "")))
    return r


def link_checks(pages: dict[str, Page], status_of: dict[str, int], sitemap_urls: set[str]) -> list[Result]:
    r: list[Result] = []
    broken: dict[str, list[str]] = defaultdict(list)
    inbound: Counter[str] = Counter()
    for url, p in pages.items():
        for ln in p.internal_links():
            target = ln.href.split("#")[0]
            if target.rstrip("/") != url.rstrip("/"):
                inbound[target.rstrip("/")] += 1
            st = status_of.get(target, status_of.get(target.rstrip("/")))
            if st is not None and st >= 400:
                broken[url].append(f"{_path(target)} ({st})")
    for url in pages:
        r.append(_ok(url not in broken, "broken_links", url, "døde links: " + ", ".join(sorted(set(broken[url]))[:5])))
    for url in sitemap_urls:
        if url.rstrip("/") in {x.rstrip("/") for x in pages} and not _is_home(url):
            r.append(_ok(inbound[url.rstrip("/")] > 0, "orphan_pages", url, "ingen interne links peger hertil", warn=True))
    return r


# ---------------------------------------------------------------------------------------------------
# Site-tjek
# ---------------------------------------------------------------------------------------------------
def robots_checks(root: str, resp: Response) -> list[Result]:
    url = f"{root}/robots.txt"
    present = resp.ok and "text" in resp.content_type and "<html" not in resp.text[:200].lower()
    r = [_ok(present, "robots_present", url, f"HTTP {resp.status or resp.error}")]
    if not present:
        return r
    text = resp.text
    groups = _robots_groups(text)
    star = groups.get("*", [])
    blocks_all = any(d == "disallow" and v.strip() == "/" for d, v in star)
    r.append(_ok(not blocks_all, "robots_open", url, "Disallow: / for alle bots"))
    r.append(_ok(bool(re.search(r"(?im)^\s*sitemap:\s*\S+", text)), "robots_sitemap", url, "ingen Sitemap-linje", warn=True))
    asset_blocks = [v for d, v in star if d == "disallow" and re.search(r"(_next|static|assets|\.css|\.js)", v)]
    r.append(_ok(not asset_blocks, "robots_assets", url, "blokerer " + ", ".join(asset_blocks)))
    return r


def _robots_groups(text: str) -> dict[str, list[tuple[str, str]]]:
    groups: dict[str, list[tuple[str, str]]] = defaultdict(list)
    agents: list[str] = []
    last_was_agent = False
    for line in text.splitlines():
        line = line.split("#")[0].strip()
        if ":" not in line:
            continue
        k, _, v = line.partition(":")
        k, v = k.strip().lower(), v.strip()
        if k == "user-agent":
            if not last_was_agent:
                agents = []
            agents.append(v.lower())
            last_was_agent = True
        else:
            last_was_agent = False
            for a in agents:
                groups[a].append((k, v))
    return groups


def parse_sitemap(resp: Response) -> tuple[list[tuple[str, str | None]], str | None]:
    """([(loc, lastmod)], fejl). Sitemap-index returneres som loc'er for under-sitemaps."""
    try:
        root = ET.fromstring(resp.body)
    except ET.ParseError as exc:
        return [], f"ugyldig XML: {exc}"
    ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    items = []
    for node in root.findall(".//s:url", ns) + root.findall(".//s:sitemap", ns):
        loc = node.findtext("s:loc", default="", namespaces=ns).strip()
        if loc:
            items.append((loc, node.findtext("s:lastmod", default=None, namespaces=ns)))
    return items, None


def sitemap_checks(root: str, resp: Response, items: list[tuple[str, str | None]], error: str | None,
                   url_status: dict[str, tuple[int, int]]) -> list[Result]:
    url = f"{root}/sitemap.xml"
    present = resp.ok and ("xml" in resp.content_type or resp.body.lstrip().startswith(b"<?xml"))
    r = [_ok(present, "sitemap_present", url, f"HTTP {resp.status or resp.error}")]
    if not present:
        return r
    r.append(_ok(error is None and bool(items), "sitemap_valid", url, error or "ingen URL'er i sitemap"))
    bad = [f"{_path(u)} ({'redirect' if st in (301, 302, 307, 308) else st})" for u, (st, hops) in url_status.items() if st != 200 or hops]
    r.append(_ok(not bad, "sitemap_urls_ok", url, f"{len(bad)} af {len(url_status)} URL'er: " + ", ".join(bad[:5])))
    stamps = [lm for _, lm in items if lm]
    if len(stamps) >= 3:
        try:
            parsed = [datetime.fromisoformat(s.replace("Z", "+00:00")) for s in stamps]
            parsed = [p if p.tzinfo else p.replace(tzinfo=timezone.utc) for p in parsed]
            identical = max(parsed) - min(parsed) < timedelta(seconds=5)
            fresh = datetime.now(timezone.utc) - max(parsed) < timedelta(days=1)
            r.append(_ok(not (identical and fresh), "sitemap_lastmod", url,
                         "alle sider har samme lastmod = lige nu (genereres ved hver forespørgsel)", warn=True))
        except ValueError:
            pass
    return r


def transport_checks(root: str, http_resp: Response | None, www_resp: Response | None, home: Response) -> list[Result]:
    r = [_ok(home.final_url.startswith("https://"), "https_final", root, f"slutter på {home.final_url}")]
    if http_resp is not None:
        ok = bool(http_resp.redirects) and http_resp.redirects[0][1] in (301, 308) and http_resp.final_url.startswith("https://")
        r.append(_ok(ok, "http_redirect", root, "http:// redirecter ikke permanent til https://"
                     if http_resp.redirects else "http:// svarer uden redirect", warn=bool(http_resp.redirects)))
    if www_resp is not None:
        host_a, host_b = urlparse(www_resp.final_url).netloc, urlparse(home.final_url).netloc
        r.append(_ok(host_a == host_b and not www_resp.error, "www_redirect", root,
                     f"{www_resp.url} ender på {www_resp.final_url}"))
    h = home.headers
    r.append(_ok("strict-transport-security" in h, "hsts", root, "mangler Strict-Transport-Security", warn=True))
    r.append(_ok("nosniff" in h.get("x-content-type-options", "").lower(), "sec_nosniff", root, "mangler header", warn=True))
    r.append(_ok("x-frame-options" in h or "frame-ancestors" in h.get("content-security-policy", ""), "sec_frame", root, "mangler header", warn=True))
    r.append(_ok("referrer-policy" in h, "sec_referrer", root, "mangler header", warn=True))
    csp_ro = "content-security-policy-report-only" in h
    r.append(_ok("content-security-policy" in h or csp_ro, "sec_csp", root, "mangler header", warn=True,
                 detail_pass="kun Content-Security-Policy-Report-Only – håndhæves ikke endnu" if csp_ro and "content-security-policy" not in h else ""))
    r.append(_ok("permissions-policy" in h, "sec_permissions", root, "mangler header", warn=True))
    enc = h.get("content-encoding", "").lower()
    r.append(_ok(enc in ("gzip", "br", "zstd", "deflate"), "compression", root, "HTML leveres ukomprimeret"))
    return r


def asset_cache_check(asset: Response | None) -> list[Result]:
    if asset is None or not asset.ok:
        return []
    cc = asset.headers.get("cache-control", "")
    m = re.search(r"max-age=(\d+)", cc)
    age = int(m.group(1)) if m else 0
    return [_ok(age >= 2_592_000 or "immutable" in cc, "cache_static", asset.url, f"Cache-Control: «{cc or 'mangler'}»", warn=age > 0)]


def misc_checks(root: str, notfound: Response, favicon: Response | None, llms: Response | None, sectxt: Response | None) -> list[Result]:
    r = [_ok(notfound.status == 404, "notfound_page", f"{root}/findes-ikke-seo-agent",
             f"ukendt URL svarede {notfound.status or notfound.error}")]
    r.append(_ok(favicon is not None and favicon.ok, "favicon", f"{root}/favicon.ico", "ingen /favicon.ico", warn=True))
    r.append(_ok(llms is not None and llms.ok and "html" not in llms.content_type, "llms_txt", f"{root}/llms.txt", "findes ikke", warn=True))
    r.append(_ok(sectxt is not None and sectxt.ok and "html" not in sectxt.content_type, "security_txt", f"{root}/.well-known/security.txt", "findes ikke", warn=True))
    return r

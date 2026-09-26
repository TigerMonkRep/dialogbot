"""Suggest knowledge from the company's own website.

1. Fetch the start page and a handful of same-site pages (services, prices, about, contact …).
   Only http(s), no private/loopback addresses (checked on every redirect hop), size and page caps.
2. Ask the AI provider to extract services, facts and frequent questions as JSON — strictly what
   the pages say. Prices are never guessed and never stored as numbers: a price the site mentions
   is quoted in the description for the owner to confirm (sites usually show prices incl. VAT).
3. Store every suggestion as an ordinary knowledge *draft* (source_type 'extraction', source_ref =
   page URL). Nothing reaches the assistant until a person edits/approves it.
"""
from __future__ import annotations

import ipaddress
import json
import re
import socket
import uuid
from datetime import UTC, datetime
from html.parser import HTMLParser
from urllib.parse import urldefrag, urljoin, urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from app.config import get_settings
from app.core.audit import record_audit
from app.core.errors import ApiError, ValidationFailed
from app.models import KnowledgeItem, KnowledgeVersion, SourceImport, Workspace
from app.modules.ai.provider import get_provider
from app.modules.ai.service import log_call
from app.modules.knowledge.service import _key
from app.modules.setup.checks import invalidate_checks

PROMPT_VERSION = "website-extract-v1"
MAX_PAGES = 12
MAX_BYTES = 1_500_000
MAX_TEXT_PER_PAGE = 12_000
MAX_TEXT_TOTAL = 60_000
UNITS = ("m2", "hour", "item", "job")
USER_AGENT = "DialogbotImport/1.0 (henter kun virksomhedens egne sider efter anmodning)"
SKIP_EXT = re.compile(r"\.(pdf|jpe?g|png|gif|webp|svg|zip|mp4|mp3|docx?|xlsx?|css|js|ico|xml)$", re.I)
PRIORITY = ("ydelse", "service", "pris", "priser", "produkt", "behandling", "om-os", "om", "kontakt", "aabning",
            "åbning", "omraade", "område", "faq", "spoergsmaal", "spørgsmål", "tilbud")


class ImportFailed(ApiError):
    status_code = 422
    code = "import_failed"


# --------------------------------------------------------------------------- fetching

def _host_is_public(host: str) -> bool:
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        return False
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast \
                or ip.is_unspecified:
            return False
    return True


def normalize_url(raw: str) -> str:
    url = (raw or "").strip()
    if url and "://" not in url:
        url = "https://" + url
    p = urlparse(url)
    if p.scheme not in ("http", "https") or not p.hostname:
        raise ValidationFailed("Angiv en gyldig adresse, fx https://www.jeres-firma.dk", field_errors=[{"field": "url"}])
    return urldefrag(url)[0]


def _allowed(url: str) -> bool:
    p = urlparse(url)
    if p.scheme not in ("http", "https") or not p.hostname:
        return False
    if get_settings().app_env in ("dev", "test"):
        return True  # local test sites; staging/prod only fetch public addresses
    return _host_is_public(p.hostname)


def fetch(url: str) -> tuple[str, str] | None:
    """GET one HTML page with manual, re-checked redirects. Returns (final_url, html) or None."""
    import httpx

    with httpx.Client(timeout=10.0, follow_redirects=False, headers={"user-agent": USER_AGENT}) as client:
        for _ in range(4):
            if not _allowed(url):
                return None
            try:
                with client.stream("GET", url) as r:
                    if r.status_code in (301, 302, 303, 307, 308) and r.headers.get("location"):
                        url = urljoin(url, r.headers["location"])
                        continue
                    if r.status_code != 200 or "html" not in r.headers.get("content-type", "text/html"):
                        return None
                    body = b""
                    for chunk in r.iter_bytes():
                        body += chunk
                        if len(body) > MAX_BYTES:
                            break
                    return url, body.decode(r.encoding or "utf-8", errors="replace")
            except httpx.HTTPError:
                return None
    return None


class _Text(HTMLParser):
    """HTML → readable text: headings as '## ', list items as '- ', no scripts/styles/navigation."""

    SKIP = {"script", "style", "noscript", "svg", "template", "nav", "footer", "form"}
    BLOCK = {"p", "div", "section", "article", "br", "tr", "li", "h1", "h2", "h3", "h4", "header", "main", "td"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.links: list[str] = []
        self.title = ""
        self._skip = 0
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self._skip += 1
        if tag == "title":
            self._in_title = True
        if tag == "a":
            href = dict(attrs).get("href")
            if href:
                self.links.append(href)
        if self._skip:
            return
        if tag in self.BLOCK:
            self.parts.append("\n")
        if tag in ("h1", "h2", "h3", "h4"):
            self.parts.append("## ")
        elif tag == "li":
            self.parts.append("- ")

    def handle_endtag(self, tag):
        if tag in self.SKIP and self._skip:
            self._skip -= 1
        if tag == "title":
            self._in_title = False
        if tag in self.BLOCK and not self._skip:
            self.parts.append("\n")

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        elif not self._skip:
            self.parts.append(data)

    def text(self) -> str:
        lines = [re.sub(r"\s+", " ", ln).strip() for ln in "".join(self.parts).split("\n")]
        out = [ln for ln in lines if ln and ln not in ("##", "-")]
        return "\n".join(out)


def parse(html: str) -> tuple[str, str, list[str]]:
    p = _Text()
    p.feed(html)
    return p.title.strip(), p.text()[:MAX_TEXT_PER_PAGE], p.links


def _same_site(a: str, b: str) -> bool:
    ha, hb = (urlparse(x).hostname or "" for x in (a, b))
    return ha.removeprefix("www.") == hb.removeprefix("www.")


def _score(url: str) -> int:
    path = urlparse(url).path.lower()
    return -sum(1 for k in PRIORITY if k in path) * 10 + path.count("/")


def crawl(start: str, fetcher=None) -> list[dict]:
    """Start page plus the most relevant same-site pages. Returns [{url, title, text}]."""
    fetcher = fetcher or fetch
    first = fetcher(start)
    if first is None:
        raise ImportFailed("Hjemmesiden kunne ikke hentes. Tjek adressen, og at siden er offentlig.")
    base, html = first
    title, text, links = parse(html)
    pages = [{"url": base, "title": title, "text": text}]
    seen = {urldefrag(base)[0].rstrip("/")}
    candidates = []
    for href in links:
        u = urldefrag(urljoin(base, href))[0]
        key = u.rstrip("/")
        if key in seen or not u.startswith(("http://", "https://")) or not _same_site(base, u) or SKIP_EXT.search(u):
            continue
        seen.add(key)
        candidates.append(u)
    total = len(text)
    for u in sorted(candidates, key=_score)[: MAX_PAGES * 2]:
        if len(pages) >= MAX_PAGES or total >= MAX_TEXT_TOTAL:
            break
        got = fetcher(u)
        if got is None:
            continue
        t, body, _ = parse(got[1])
        if len(body) < 40:
            continue
        pages.append({"url": got[0], "title": t, "text": body})
        total += len(body)
    return pages


# --------------------------------------------------------------------------- extraction

SYSTEM = """WEBSITE_EXTRACTION
Du hjælper en dansk virksomhed med at oprette viden til deres digitale receptionist. Du får teksten fra virksomhedens egen hjemmeside.
Udtræk KUN det, der faktisk står på siderne. Opfind intet, og gæt aldrig på priser, tider eller vilkår.

Svar med ét JSON-objekt og intet andet:
{"services": [{"title": "kort navn på ydelsen", "description": "2-4 sætninger til assistenten om hvad ydelsen er, hvem den er til og hvad den omfatter", "unit": "m2|hour|item|job|null", "price_text": "prisen præcis som den står på siden, eller null", "source_url": "siden den stammer fra"}],
 "facts": [{"title": "fx Om virksomheden, Åbningstider, Område vi dækker, Kontakt", "text": "faktuel tekst til assistenten", "source_url": "..."}],
 "faq": [{"question": "spørgsmål en kunde typisk stiller", "answer": "svar der står på siden", "source_url": "..."}]}

Regler: højst 15 ydelser, 8 fakta og 8 spørgsmål. Skriv på naturligt dansk. Beskrivelser skal være skrevet til assistenten (tredje person om virksomheden). Hvis noget ikke står på siderne, så udelad det."""


def _json_block(text: str) -> dict:
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ImportFailed("AI-udtrækket kunne ikke læses. Prøv igen.")
    try:
        data = json.loads(text[start:end + 1])
    except ValueError as e:
        raise ImportFailed("AI-udtrækket kunne ikke læses. Prøv igen.") from e
    return data if isinstance(data, dict) else {}


def _s(v, n: int) -> str:
    return re.sub(r"\s+", " ", str(v or "")).strip()[:n]


def suggestions(data: dict, pages: list[dict]) -> list[tuple[str, str, dict, str | None]]:
    """(kind, title, content, source_url) — validated and trimmed."""
    urls = {p["url"] for p in pages}
    out: list[tuple[str, str, dict, str | None]] = []

    def src(v) -> str | None:
        u = _s(v, 500)
        return u if u in urls else pages[0]["url"]

    for s in (data.get("services") or [])[:15]:
        title = _s(s.get("title"), 120)
        if not title:
            continue
        desc = _s(s.get("description"), 1500)
        price_text = _s(s.get("price_text"), 200)
        if price_text and price_text.lower() != "null":
            desc = f"{desc}\n\nHjemmesiden nævner prisen: \"{price_text}\" – bekræft og indtast prisen ekskl. moms.".strip()
        unit = s.get("unit") if s.get("unit") in UNITS else "job"
        out.append(("service", title, {"description": desc, "unit": unit, "price_net_minor": None, "currency": "DKK"},
                    src(s.get("source_url"))))
    for f in (data.get("facts") or [])[:8]:
        title, text = _s(f.get("title"), 120), _s(f.get("text"), 2000)
        if title and text:
            out.append(("fact", title, {"text": text}, src(f.get("source_url"))))
    for q in (data.get("faq") or [])[:8]:
        question, answer = _s(q.get("question"), 300), _s(q.get("answer"), 2000)
        if question and answer:
            out.append(("known_answer", question[:120], {"question": question, "answer": answer},
                        src(q.get("source_url"))))
    return out


def extract(db: OrmSession, ws: Workspace, user_id: uuid.UUID | None, pages: list[dict]) -> dict:
    provider = get_provider()
    body = "\n\n".join(f"<side url=\"{p['url']}\" titel=\"{p['title']}\">\n{p['text']}\n</side>" for p in pages)
    c, row = log_call(db, ws, provider, user_id=user_id, purpose="source_import", system=SYSTEM,
                      messages=[{"role": "user", "content": f"Virksomhed: {ws.name}\n\n{body}"}],
                      prompt_version=PROMPT_VERSION, revision=ws.knowledge_revision, max_tokens=8000)
    db.commit()
    if row.outcome == "refused":
        raise ImportFailed("AI-udbyderen afviste at behandle siderne.")
    return _json_block(c.text)


# --------------------------------------------------------------------------- run

def start(db: OrmSession, ws: Workspace, user_id: uuid.UUID, url: str) -> tuple[SourceImport, bool]:
    """Returns (import, is_new). A run already in progress (< 10 min) is returned instead of a second one."""
    get_provider()  # 501 up front when AI is not configured
    running = db.scalar(select(SourceImport).where(SourceImport.workspace_id == ws.id,
                                                   SourceImport.status == "running"))
    if running and (datetime.now(UTC) - running.created_at).total_seconds() < 600:
        return running, False
    if running:  # a run that never finished (process restart): close it honestly
        running.status, running.error, running.finished_at = "failed", "Afbrudt", datetime.now(UTC)
    imp = SourceImport(workspace_id=ws.id, url=url, status="running", created_by=user_id)
    db.add(imp)
    db.commit()
    return imp, True


def run(import_id: uuid.UUID, fetcher=None) -> None:
    """Background job (own DB session). Never raises: failures are stored on the import row."""
    from app.db import get_session_factory

    db = get_session_factory()()
    try:
        imp = db.get(SourceImport, import_id)
        ws = db.get(Workspace, imp.workspace_id)
        try:
            pages = crawl(imp.url, fetcher)
            imp.pages = [{"url": p["url"], "title": p["title"][:200], "chars": len(p["text"])} for p in pages]
            db.commit()
            data = extract(db, ws, imp.created_by, pages)
            created, skipped = [], 0
            for kind, title, content, source in suggestions(data, pages):
                key = _key(kind, title)
                if db.scalar(select(KnowledgeItem.id).where(KnowledgeItem.workspace_id == ws.id,
                                                            KnowledgeItem.kind == kind, KnowledgeItem.key == key)):
                    skipped += 1
                    continue
                item = KnowledgeItem(workspace_id=ws.id, kind=kind, key=key)
                db.add(item)
                db.flush()
                v = KnowledgeVersion(item_id=item.id, workspace_id=ws.id, version_no=1, status="draft", title=title,
                                     content=content, source_type="extraction", source_ref=source,
                                     created_by=imp.created_by)
                db.add(v)
                db.flush()
                created.append({"kind": kind, "title": title, "item_id": str(item.id), "version_id": str(v.id)})
            imp.created_items, imp.skipped, imp.status = created, skipped, "done"
            record_audit(db, workspace_id=ws.id, actor_user_id=imp.created_by, action="knowledge.import_suggested",
                         object_type="source_import", object_id=imp.id,
                         after={"url": imp.url, "pages": len(pages), "created": len(created), "skipped": skipped})
            if created:
                invalidate_checks(db, ws.id, changed_area="knowledge", reason="knowledge.import_suggested")
        except ApiError as e:
            db.rollback()
            imp = db.get(SourceImport, import_id)
            imp.status, imp.error = "failed", e.message
        except Exception:  # noqa: BLE001 - stored for the user, logged by the caller's logger
            db.rollback()
            imp = db.get(SourceImport, import_id)
            imp.status, imp.error = "failed", "Uventet fejl under importen. Prøv igen."
        imp.finished_at = datetime.now(UTC)
        db.commit()
    finally:
        db.close()


def import_out(imp: SourceImport | None) -> dict | None:
    if imp is None:
        return None
    return {"id": str(imp.id), "url": imp.url, "status": imp.status, "pages": imp.pages,
            "created_items": imp.created_items, "skipped": imp.skipped, "error": imp.error,
            "created_at": imp.created_at.isoformat(), "finished_at": imp.finished_at.isoformat() if imp.finished_at else None}

"""Suggest knowledge from an uploaded document or pasted text – the same pipeline as the website import.

1. The text is read server-side (app/modules/knowledge/documents.py) into referenced sections ("prisliste.pdf · side 3")
   and grouped into AI-sized chunks. The raw file is never stored: its bytes live only in memory until the text is
   read; the text lives only until the drafts are written.
2. Each chunk goes to the AI provider (prompt `document-extract-v1`, one ai_usage row per chunk via log_call) together
   with a catalogue of the workspace's existing knowledge (approved and open drafts, e.g. from the website import).
   The model sorts what the text says into the existing kinds, and points at a catalogue entry when it is the same
   thing.
3. Everything is checked against the text before it becomes a draft: every suggestion needs a verbatim quote that is
   found in its chunk (otherwise it is dropped – nothing invented); a price, discount, area or time must occur in the
   text; prices are never stored as numbers, only quoted for the owner to confirm (as for the website).
4. Overlap with existing knowledge becomes a NEW DRAFT VERSION of that item (an update proposal), never a duplicate;
   an identical one is skipped. A different price / opening hours than the existing knowledge is flagged as a
   conflict on the draft's review note. Nothing reaches the assistant before a person approves it.
"""
from __future__ import annotations

import re
import uuid
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session as OrmSession

from app.core.audit import record_audit
from app.core.errors import ApiError, Conflict
from app.models import KnowledgeItem, KnowledgeVersion, LanguageSettings, SourceImport, Workspace
from app.modules.ai.provider import get_provider
from app.modules.ai.service import log_call
from app.modules.knowledge import documents
from app.modules.knowledge.documents import Section
from app.modules.knowledge.importer import UNITS, ImportFailed, _json_block, _s, opening_hours
from app.modules.knowledge.service import _key, validate_content
from app.modules.setup.checks import invalidate_checks

PROMPT_VERSION = "document-extract-v1"
MAX_TEXT_CHARS = documents.MAX_TEXT_CHARS
UPLOADS_PER_HOUR = 20  # file + text imports per workspace
MAX_ITEMS_PER_CHUNK = 40
CATALOGUE_MAX = 300

# AI category → (knowledge kind, review group). Policies, contact details and facts are all `fact` knowledge (the
# assistant may say them); `rule` is what the assistant must NOT answer itself (unknown_answer).
CATEGORIES = {
    "service": "service", "opening_hours": "opening_hours", "faq": "known_answer", "policy": "fact",
    "contact": "fact", "fact": "fact", "offer": "offer", "coverage_area": "coverage_area", "rule": "unknown_answer",
}
SINGLETON_KINDS = ("opening_hours", "coverage_area")  # one per workspace: always an update of the existing one
LANG_NAMES = {"da": "dansk", "en": "engelsk", "de": "tysk", "es": "spansk", "fr": "fransk", "it": "italiensk",
              "no": "norsk (bokmål)", "sv": "svensk"}


class UploadRateLimited(ApiError):
    status_code = 429
    code = "rate_limited"


SYSTEM = """DOCUMENT_EXTRACTION
Du hjælper en virksomhed med at opsætte viden til deres digitale receptionist. Du får et udsnit af et dokument eller en tekst, som virksomheden selv har givet dig, delt i afsnit (<afsnit ref="...">). Du får også et katalog over den viden, virksomheden allerede har (<katalog>).

Find ALT i teksten, som receptionisten kan bruge over for kunder, og sortér det i kategorier:
- service: en ydelse/et produkt virksomheden sælger
- opening_hours: åbnings- eller telefontider
- faq: et spørgsmål en kunde typisk stiller, med svaret fra teksten
- policy: regler og vilkår over for kunden (afbestilling, betaling, garanti, levering, reklamation …)
- contact: kontaktoplysninger (telefon, e-mail, adresse, kontaktpersoner)
- fact: andre fakta om virksomheden (historie, certificeringer, mærker, medarbejdere …)
- offer: et tidsbegrænset tilbud eller en rabat
- coverage_area: område/byer/postnumre virksomheden dækker
- rule: noget receptionisten IKKE selv må svare på eller love (fx "giv aldrig pris uden besigtigelse")

Regler:
1. Udtræk KUN det, der faktisk står i teksten. Opfind intet, og gæt aldrig på priser, tider, vilkår eller kontaktdata.
2. Hver post skal have "quote": et kort ORDRET uddrag (højst 200 tegn) fra teksten, som viser, at det står der.
3. Priser skrives aldrig om til tal: "price_text" er prisen præcis som den står i teksten.
4. Skriv titler og tekster på {lang}, til receptionisten (tredje person om virksomheden), også hvis teksten er på et andet sprog.
5. Hvis en post handler om det samme som en post i kataloget, så sæt "existing" til katalogets id (fx "K3"). Hvis teksten siger noget andet end katalogposten (fx en anden pris eller andre tider), så beskriv forskellen kort i "conflict".
6. Samme ting må kun optræde én gang. Højst 40 poster.

Svar med ét JSON-objekt og intet andet:
{{"items": [{{"category": "service|opening_hours|faq|policy|contact|fact|offer|coverage_area|rule",
  "title": "kort titel",
  "text": "2-4 sætninger til receptionisten (for faq: svaret)",
  "question": "kun for faq: spørgsmålet",
  "price_text": "kun for service: prisen præcis som i teksten, ellers null",
  "unit": "kun for service: m2|hour|item|job|null",
  "discount_percent": "kun for offer: rabatten i procent som tal, hvis den står i teksten, ellers null",
  "starts_on": "kun for offer: ÅÅÅÅ-MM-DD eller null", "ends_on": "kun for offer: ÅÅÅÅ-MM-DD eller null",
  "weekly": "kun for opening_hours: [{{\\"days\\": [\\"mon\\",...], \\"open\\": \\"08:00\\", \\"close\\": \\"16:00\\"}}]",
  "note": "kun for opening_hours: fx 'Lukket på helligdage' eller null",
  "zones": "kun for coverage_area: [\\"Aarhus\\", \\"8000\\", ...]",
  "quote": "ordret uddrag", "source": "ref fra det afsnit, det står i",
  "existing": "K-id eller null", "conflict": "kort beskrivelse af modstrid eller null"}}]}}"""


# --------------------------------------------------------------------------- grounding

def _norm(s: str) -> str:
    s = str(s or "").lower().replace(" ", " ")
    s = re.sub(r"[\"'«»“”„‘’`*_#|]", "", s)
    return re.sub(r"\s+", " ", s).strip()


def _words(s: str) -> list[str]:
    return [w for w in re.findall(r"[\wæøåäöüé]+", _norm(s)) if len(w) >= 3 or w.isdigit()]


def grounded(quote: str, text: str) -> bool:
    """The quote is in the text: verbatim (whitespace/case/quotes ignored), or ≥ 80 % of its words occur in the text
    and every number in it does. An empty quote is never grounded."""
    q = _norm(quote)
    if len(q) < 4:
        return False
    t = _norm(text)
    if q in t:
        return True
    words = _words(q)
    if not words:
        return False
    tw = set(_words(t))
    if any(w.isdigit() and w not in tw for w in words):
        return False
    return sum(1 for w in words if w in tw) / len(words) >= 0.8


def _numbers(s: str) -> list[float]:
    """Danish/English amounts in a string: '1.200,50 kr' → 1200.5, '450,-' → 450, '12.5%' → 12.5."""
    out = []
    for m in re.finditer(r"\d{1,3}(?:[.\s]\d{3})+(?:,\d{1,2})?|\d+(?:[.,]\d{1,2})?", s or ""):
        raw = m.group(0).replace(" ", "")
        if re.fullmatch(r"\d{1,3}(?:\.\d{3})+(?:,\d{1,2})?", raw):
            raw = raw.replace(".", "").replace(",", ".")
        else:
            raw = raw.replace(",", ".")
        try:
            out.append(float(raw))
        except ValueError:
            continue
    return out


def _digits_in(needle: str, hay: str) -> bool:
    d = re.sub(r"\D", "", needle or "")
    return bool(d) and d in re.sub(r"\D", "", hay or "")


# --------------------------------------------------------------------------- catalogue of existing knowledge

def _summary_text(kind: str, c: dict) -> str:
    if kind == "service":
        price = f" · pris {c['price_net_minor'] / 100:g} kr. ekskl. moms" if isinstance(c.get("price_net_minor"), int) else ""
        return f"{_s(c.get('description'), 200)}{price}"
    if kind == "opening_hours":
        return "; ".join(f"{','.join(w.get('days', []))} {w.get('open')}-{w.get('close')}" for w in c.get("weekly") or [])
    if kind == "coverage_area":
        return ", ".join(str(z) for z in (c.get("zones") or [])[:20])
    if kind == "known_answer":
        return f"{_s(c.get('question'), 150)} → {_s(c.get('answer'), 200)}"
    if kind == "unknown_answer":
        return _s(c.get("rule"), 200)
    if kind == "offer":
        return f"{c.get('discount_percent')} % {_s(c.get('description'), 150)}"
    return _s(c.get("text"), 250)


def catalogue(db: OrmSession, ws_id: uuid.UUID) -> list[dict]:
    """Existing (non-archived) items with their current content: the approved version, else the open draft (e.g. a
    website-import suggestion not yet approved). ids K1…Kn are for the prompt only."""
    rows = db.execute(select(KnowledgeItem, KnowledgeVersion)
                      .join(KnowledgeVersion, KnowledgeVersion.item_id == KnowledgeItem.id)
                      .where(KnowledgeItem.workspace_id == ws_id, KnowledgeItem.archived_at.is_(None),
                             KnowledgeVersion.status.in_(("approved", "draft", "in_review")))
                      .order_by(KnowledgeItem.kind, KnowledgeItem.key, KnowledgeVersion.version_no)).all()
    by_item: dict[uuid.UUID, dict] = {}
    for item, v in rows:
        e = by_item.setdefault(item.id, {"item": item, "approved": None, "draft": None})
        e["approved" if v.status == "approved" else "draft"] = v
    out = []
    for n, e in enumerate(list(by_item.values())[:CATALOGUE_MAX], start=1):
        cur = e["approved"] or e["draft"]
        out.append({"id": f"K{n}", "item": e["item"], "approved": e["approved"], "draft": e["draft"],
                    "kind": e["item"].kind, "title": cur.title, "content": cur.content or {}})
    return out


def _catalogue_prompt(cat: list[dict]) -> str:
    if not cat:
        return "<katalog>\n(ingen viden endnu)\n</katalog>"
    lines = [f"{c['id']} · {c['kind']} · {c['title']}: {_summary_text(c['kind'], c['content'])}" for c in cat]
    return "<katalog>\n" + "\n".join(lines) + "\n</katalog>"


# --------------------------------------------------------------------------- one chunk → validated suggestions

def suggestions(data: dict, chunk: list[Section]) -> tuple[list[dict], int]:
    """Validate the model's items against the chunk. Returns (suggestions, dropped_ungrounded)."""
    text = "\n\n".join(s.text for s in chunk)
    refs = [s.ref for s in chunk]
    out: list[dict] = []
    dropped = 0
    for it in (data.get("items") or [])[:MAX_ITEMS_PER_CHUNK]:
        if not isinstance(it, dict):
            continue
        cat = str(it.get("category") or "").strip().lower()
        kind = CATEGORIES.get(cat)
        title = _s(it.get("title"), 120)
        quote = _s(it.get("quote"), 300)
        if kind is None or not title:
            continue
        if not grounded(quote, text):
            dropped += 1
            continue
        src = _s(it.get("source"), 300)
        if src not in refs:  # the quote tells where it is
            src = next((s.ref for s in chunk if grounded(quote, s.text)), refs[0])
        body = _s(it.get("text"), 2000)
        content: dict | None = None
        if kind == "service":
            price_text = _s(it.get("price_text"), 200)
            if price_text.lower() in ("null", "none"):
                price_text = ""
            if price_text and not _digits_in(price_text, text):
                price_text = ""  # a price that is not in the text is never passed on
            desc = body
            if price_text:
                desc = f"{desc}\n\nDokumentet nævner prisen: \"{price_text}\" – bekræft og indtast prisen ekskl. moms.".strip()
            unit = it.get("unit") if it.get("unit") in UNITS else "job"
            content = {"description": desc, "unit": unit, "price_net_minor": None, "currency": "DKK"}
            if price_text:
                content["_price_text"] = price_text  # popped before saving; used for conflict detection
        elif kind == "opening_hours":
            hours = opening_hours({"opening_hours": {"weekly": it.get("weekly"), "note": it.get("note")}})
            if hours:
                times = [t for w in hours["weekly"] for t in (w["open"], w["close"])]
                if all(_digits_in(t.split(":")[0].lstrip("0") or "0", text) for t in times):
                    content = hours
        elif kind == "coverage_area":
            zones = [_s(z, 80) for z in (it.get("zones") or []) if isinstance(z, str)]
            zones = [z for z in zones if z and _norm(z) in _norm(text)][:50]
            if zones:
                content = {"zones": zones}
        elif kind == "known_answer":
            question = _s(it.get("question") or title, 300)
            if question and body:
                content = {"question": question, "answer": body}
                title = question[:120]
        elif kind == "unknown_answer":
            if body or title:
                content = {"rule": body or title}
        elif kind == "offer":
            pct = it.get("discount_percent")
            try:
                pct = float(str(pct).replace(",", ".").replace("%", "")) if pct not in (None, "", "null") else None
            except ValueError:
                pct = None
            if pct is not None and 0 < pct <= 100 and _digits_in(f"{pct:g}", text):
                content = {"discount_percent": int(pct) if pct == int(pct) else pct, "description": body}
                for src_key, dst in (("starts_on", "starts_on"), ("ends_on", "ends_on_inclusive")):
                    try:
                        content[dst] = date.fromisoformat(str(it.get(src_key))).isoformat()
                    except ValueError:
                        pass
                if content.get("starts_on", "") > content.get("ends_on_inclusive", "9999") :
                    content.pop("starts_on", None)
                    content.pop("ends_on_inclusive", None)
            elif body:  # a discount without a stated percentage is a fact for the owner to complete
                kind, cat, content = "fact", "offer", {"text": body}
        else:  # fact / policy / contact
            if body:
                content = {"text": body}
        if content is None:
            continue
        try:
            validate_content(kind, {k: v for k, v in content.items() if not k.startswith("_")})
        except ApiError:
            continue
        existing = _s(it.get("existing"), 10)
        conflict = _s(it.get("conflict"), 400)
        out.append({"kind": kind, "category": cat, "title": title, "content": content, "source": src,
                    "quote": quote[:200], "existing": existing if re.fullmatch(r"K\d+", existing) else None,
                    "conflict": None if conflict.lower() in ("", "null", "none") else conflict})
    return out, dropped


def merge(found: list[dict]) -> list[dict]:
    """The same thing found in two chunks is one suggestion (first wins; zones are combined)."""
    out: list[dict] = []
    seen: dict[str, dict] = {}
    for s in found:
        k = s["kind"] if s["kind"] in SINGLETON_KINDS else _key(s["kind"], s["title"])
        if k in seen:
            first = seen[k]
            if s["kind"] == "coverage_area":
                first["content"]["zones"] = list(dict.fromkeys(first["content"]["zones"] + s["content"]["zones"]))[:50]
            continue
        seen[k] = s
        out.append(s)
    return out


# --------------------------------------------------------------------------- overlap and conflicts

def _title_tokens(t: str) -> set[str]:
    return set(_words(t))


def match(s: dict, cat: list[dict]) -> dict | None:
    """The catalogue entry a suggestion is about: the model's pointer (same kind), the same key, the singleton of the
    kind, or a near-identical title (≥ 80 % shared words)."""
    same = [c for c in cat if c["kind"] == s["kind"]]
    if s["existing"]:
        hit = next((c for c in same if c["id"] == s["existing"]), None)
        if hit:
            return hit
    key = _key(s["kind"], s["title"])
    hit = next((c for c in same if c["item"].key == key), None)
    if hit:
        return hit
    if s["kind"] in SINGLETON_KINDS and same:
        return same[0]
    tt = _title_tokens(s["title"])
    for c in same:
        ct = _title_tokens(c["title"])
        if tt and ct and len(tt & ct) / len(tt | ct) >= 0.8:
            return c
    return None


def _existing_prices(c: dict) -> tuple[list[float], str]:
    content = c["content"]
    nums: list[float] = []
    shown = ""
    if isinstance(content.get("price_net_minor"), int):
        net = content["price_net_minor"] / 100
        nums += [net, round(net * 1.25, 2)]
        shown = f"{net:g} kr. ekskl. moms"
    quoted = re.search(r'nævner prisen: "([^"]+)"', str(content.get("description") or ""))
    if quoted:
        nums += _numbers(quoted.group(1))
        shown = shown or quoted.group(1)
    return nums, shown


def conflict_of(s: dict, c: dict) -> str | None:
    """A deterministic conflict (different price, different opening hours) – else the model's own note."""
    if s["kind"] == "service" and s["content"].get("_price_text"):
        theirs, shown = _existing_prices(c)
        ours = _numbers(s["content"]["_price_text"])
        if theirs and ours and not any(abs(a - b) < 0.51 for a in ours for b in theirs):
            return f"Anden pris: teksten siger «{s['content']['_price_text']}», den eksisterende viden siger «{shown}»."
    if s["kind"] == "opening_hours":
        def norm(w):
            return sorted((tuple(sorted(r.get("days", []))), r.get("open"), r.get("close")) for r in w or [])
        if c["content"].get("weekly") and norm(c["content"].get("weekly")) != norm(s["content"].get("weekly")):
            return "Andre åbningstider end den eksisterende viden."
    return s["conflict"]


def _same(kind: str, a: dict, b: dict) -> bool:
    keys = {"service": ("description",), "known_answer": ("answer",), "unknown_answer": ("rule",),
            "fact": ("text",), "offer": ("discount_percent", "starts_on", "ends_on_inclusive")}.get(kind)
    if kind == "opening_hours":
        return conflict_of({"kind": kind, "content": a, "conflict": None}, {"content": b}) is None
    if kind == "coverage_area":
        return {_norm(z) for z in a.get("zones", [])} <= {_norm(z) for z in b.get("zones", [])}
    if kind == "service":  # the description carries the quoted price; a different price is never "the same"
        return _norm(re.sub(r"\n\n(Dokumentet|Hjemmesiden) nævner prisen.*", "", str(a.get("description") or ""))) == \
            _norm(re.sub(r"\n\n(Dokumentet|Hjemmesiden) nævner prisen.*", "", str(b.get("description") or "")))
    return all(_norm(str(a.get(k) or "")) == _norm(str(b.get(k) or "")) for k in keys or ())


# --------------------------------------------------------------------------- run

def _language(db: OrmSession, ws_id: uuid.UUID) -> str:
    ls = db.get(LanguageSettings, ws_id)
    return LANG_NAMES.get(ls.default_conversation_language if ls else "da", "dansk")


def extract_chunk(db: OrmSession, ws: Workspace, user_id: uuid.UUID | None, chunk: list[Section], cat_text: str,
                  lang: str, part: int, parts: int) -> dict:
    provider = get_provider()
    body = "\n\n".join(f"<afsnit ref=\"{s.ref}\">\n{s.text}\n</afsnit>" for s in chunk)
    c, row = log_call(db, ws, provider, user_id=user_id, purpose="source_import", system=SYSTEM.format(lang=lang),
                      messages=[{"role": "user", "content": f"Virksomhed: {ws.name}\nUdsnit {part} af {parts}\n\n"
                                                            f"{cat_text}\n\n<tekst>\n{body}\n</tekst>"}],
                      prompt_version=PROMPT_VERSION, revision=ws.knowledge_revision, max_tokens=8000)
    db.commit()
    if row.outcome == "refused":
        raise ImportFailed("AI-udbyderen afviste at behandle teksten.")
    return _json_block(c.text)


def check_rate(db: OrmSession, ws_id: uuid.UUID) -> None:
    since = datetime.now(UTC) - timedelta(hours=1)
    n = db.scalar(select(func.count()).select_from(SourceImport).where(
        SourceImport.workspace_id == ws_id, SourceImport.source_type.in_(("file", "text")),
        SourceImport.created_at >= since)) or 0
    if n >= UPLOADS_PER_HOUR:
        raise UploadRateLimited(f"I har importeret {n} filer eller tekster den seneste time. Vent lidt, og prøv igen.")


def start(db: OrmSession, ws: Workspace, user_id: uuid.UUID, source_type: str, name: str) -> SourceImport:
    """A new file/text import (status running). Refuses while another import of this workspace runs (< 10 min)."""
    get_provider()  # 501 up front when AI is not configured
    check_rate(db, ws.id)
    running = db.scalar(select(SourceImport).where(SourceImport.workspace_id == ws.id,
                                                   SourceImport.status == "running"))
    if running and (datetime.now(UTC) - running.created_at).total_seconds() < 600:
        raise Conflict("Der kører allerede en import. Vent, til den er færdig, og prøv igen.", code="import_running")
    if running:
        running.status, running.error, running.finished_at = "failed", "Afbrudt", datetime.now(UTC)
    imp = SourceImport(workspace_id=ws.id, source_type=source_type, source_name=name[:200], url=None,
                       status="running", created_by=user_id)
    db.add(imp)
    db.commit()
    return imp


def run(import_id: uuid.UUID, *, data: bytes | None = None, kind: str | None = None, text: str | None = None) -> None:
    """Background job (own DB session). Never raises: failures are stored on the import row. `data` (file bytes) or
    `text` is read here and dropped when the function returns – neither is ever persisted."""
    from app.db import get_session_factory

    db = get_session_factory()()
    try:
        imp = db.get(SourceImport, import_id)
        ws = db.get(Workspace, imp.workspace_id)
        try:
            if data is not None:
                sections = documents.read_document(data, imp.source_name or "dokument", kind)
            else:
                sections = documents.split_text(text or "", "Indsat tekst")
                if not sections:
                    raise ImportFailed("Teksten er tom.")
            data = text = None  # noqa: F841 - drop the raw input as early as possible
            chunks = documents.chunk(sections)
            imp.pages = [{"url": s.ref, "title": s.ref[:200], "chars": len(s.text)} for s in sections[:400]]
            db.commit()
            cat = catalogue(db, ws.id)
            cat_text, lang = _catalogue_prompt(cat), _language(db, ws.id)
            found, dropped, failed_chunks = [], 0, 0
            for n, ch in enumerate(chunks, start=1):
                try:
                    got, d = suggestions(extract_chunk(db, ws, imp.created_by, ch, cat_text, lang, n, len(chunks)), ch)
                except ImportFailed:
                    failed_chunks += 1
                    continue
                found += got
                dropped += d
            if failed_chunks == len(chunks):
                raise ImportFailed("AI-udtrækket kunne ikke læses. Prøv igen.")
            imp.created_items, imp.summary = save(db, ws, imp, merge(found), cat)
            imp.summary.update({"sections": len(sections), "chunks": len(chunks), "failed_chunks": failed_chunks,
                                "unverified": dropped, "chars": sum(len(s.text) for s in sections)})
            imp.skipped = imp.summary["duplicates"]
            imp.status, imp.profile_suggestion = "done", {}
            record_audit(db, workspace_id=ws.id, actor_user_id=imp.created_by, action="knowledge.import_suggested",
                         object_type="source_import", object_id=imp.id,
                         after={"source_type": imp.source_type, "sections": len(sections), "chunks": len(chunks),
                                "created": len(imp.created_items), "skipped": imp.skipped,
                                "conflicts": imp.summary["conflicts"]})
            if imp.created_items:
                invalidate_checks(db, ws.id, changed_area="knowledge", reason="knowledge.import_suggested")
        except ApiError as e:
            db.rollback()
            imp = db.get(SourceImport, import_id)
            imp.status, imp.error = "failed", e.message
        except Exception:  # noqa: BLE001 - stored for the user; no content is logged
            db.rollback()
            imp = db.get(SourceImport, import_id)
            imp.status, imp.error = "failed", "Uventet fejl under importen. Prøv igen."
        imp.finished_at = datetime.now(UTC)
        db.commit()
    finally:
        db.close()


def save(db: OrmSession, ws: Workspace, imp: SourceImport, found: list[dict], cat: list[dict]) -> tuple[list, dict]:
    """Write the drafts. Returns (created_items, summary)."""
    created: list[dict] = []
    summary = {"found": len(found), "by_category": {}, "by_kind": {}, "new": 0, "updates": 0, "duplicates": 0,
               "conflicts": 0, "pending": 0}
    for s in found:
        summary["by_category"][s["category"]] = summary["by_category"].get(s["category"], 0) + 1
        summary["by_kind"][s["kind"]] = summary["by_kind"].get(s["kind"], 0) + 1
        price_text = s["content"].pop("_price_text", None)
        target = match(s, cat)
        note = {"import_id": str(imp.id), "source_type": imp.source_type, "relation": "new",
                "category": s["category"], "source": s["source"][:300], "quote": s["quote"], "conflict": None}
        if target is not None:
            s["content"]["_price_text"] = price_text
            conflict = conflict_of(s, target)
            s["content"].pop("_price_text", None)
            if conflict is None and _same(s["kind"], s["content"], target["content"]):
                summary["duplicates"] += 1
                continue
            open_v = target["draft"]
            if open_v is not None:
                # Already awaiting review (e.g. from the website): no second draft. A conflict is added to that draft's
                # note so the reviewer sees both sources disagree; otherwise it is a duplicate.
                if conflict:
                    rn = dict(open_v.review_note or {})
                    rn["conflicts"] = [*(rn.get("conflicts") or []), {"source": s["source"][:300], "text": conflict}][:10]
                    open_v.review_note = rn
                    summary["conflicts"] += 1
                    summary["pending"] += 1
                else:
                    summary["duplicates"] += 1
                continue
            item = target["item"]
            content = s["content"]
            if s["kind"] == "service":  # keep the owner's own price, unit and promote flag; propose the new text
                content = {**target["content"], "description": s["content"]["description"]}
            max_no = db.scalar(select(func.max(KnowledgeVersion.version_no))
                               .where(KnowledgeVersion.item_id == item.id)) or 0
            title = target["title"] if s["kind"] in SINGLETON_KINDS else s["title"]
            v = KnowledgeVersion(item_id=item.id, workspace_id=ws.id, version_no=max_no + 1, status="draft",
                                 title=title, content=content, source_type="extraction", source_ref=s["source"][:300],
                                 created_by=imp.created_by, audience=(target["approved"].audience if target["approved"]
                                                                      else "public"),
                                 review_note={**note, "relation": "update", "conflict": conflict,
                                              "previous_title": target["title"]})
            db.add(v)
            db.flush()
            target["draft"] = v  # a later suggestion for the same item is now "pending"
            summary["updates"] += 1
            summary["conflicts"] += 1 if conflict else 0
            created.append({"kind": s["kind"], "title": title, "item_id": str(item.id), "version_id": str(v.id),
                            "category": s["category"], "relation": "update", "conflict": conflict,
                            "source": s["source"][:300]})
            continue
        key = _key(s["kind"], s["title"])
        if db.scalar(select(KnowledgeItem.id).where(KnowledgeItem.workspace_id == ws.id, KnowledgeItem.kind == s["kind"],
                                                    KnowledgeItem.key == key)):
            summary["duplicates"] += 1  # an archived/odd key clash: never a duplicate item
            continue
        item = KnowledgeItem(workspace_id=ws.id, kind=s["kind"], key=key)
        db.add(item)
        db.flush()
        v = KnowledgeVersion(item_id=item.id, workspace_id=ws.id, version_no=1, status="draft", title=s["title"],
                             content=s["content"], source_type="extraction", source_ref=s["source"][:300],
                             created_by=imp.created_by, review_note=note)
        db.add(v)
        db.flush()
        cat.append({"id": f"N{len(cat) + 1}", "item": item, "approved": None, "draft": v, "kind": s["kind"],
                    "title": s["title"], "content": s["content"]})
        summary["new"] += 1
        created.append({"kind": s["kind"], "title": s["title"], "item_id": str(item.id), "version_id": str(v.id),
                        "category": s["category"], "relation": "new", "conflict": None, "source": s["source"][:300]})
    return created, summary

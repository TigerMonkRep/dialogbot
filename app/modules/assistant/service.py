"""The assistant in the app («Ændr noget» / «Hjælp»): a short conversation in which the person asks about Dialogbot or
their own setup, or says what to change.

Each turn the model returns exactly one of:
* `answer`   – guidance from the product guide (guide.md) and the workspace's current state, with at most one link to
               a page in the app (only hrefs from PAGES are passed on);
* `question` – one short clarifying question;
* `change`   – one of the known change kinds (kinds.KINDS); the server validates it and shows before → after, and
               nothing is changed until `apply` (the person's «Godkend»);
* `request`  – the app cannot do it (or the person asks for a feature): the wish is recorded for Dialogbot's team
               (requests.py) and the person is told so.

Rules this module enforces itself, whatever the model says:
* only the kinds in `kinds.KINDS`; params are re-validated here;
* anyone in the workspace may ask; a change needs `assistant.change` and the role the change itself needs (e.g.
  approving knowledge = owner/admin) – checked when proposing, so a proposal the person could not apply is never shown;
* a proposal belongs to one workspace and one person, is applied at most once and expires after 30 minutes;
* the model is told to answer in the person's interface language and never to invent facts;
* if the model cannot be reached or does not understand, the answer is a question or a link – never an error."""
from __future__ import annotations

import json
import re
import uuid
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session as OrmSession

from app.core.audit import record_audit
from app.core.auth import PERMISSIONS, WorkspaceContext
from app.core.errors import ApiError, Conflict, NotFound
from app.core.languages import NAME_DA, normalize
from app.models import (
    ASSISTANT_REQUEST_CATEGORIES,
    AssistantProposal,
    BusinessProfile,
    Campaign,
    IntegrationConnection,
    LanguageSettings,
    Membership,
    PhoneNumber,
    ReceptionScript,
    TelephonySetup,
    WebchatSettings,
)
from app.modules.ai.provider import get_provider
from app.modules.ai.service import log_call
from app.modules.assistant import requests as wishes
from app.modules.assistant.kinds import KINDS, UNITS, hours_text, kr
from app.modules.bookings import service as bookings
from app.modules.knowledge import service as knowledge
from app.modules.reports import service as reports

PROMPT_VERSION = "assistant-guide-v2"
TTL = timedelta(minutes=30)
HISTORY_TURNS = 10

# The pages the assistant may link to: (key, href, label, what is there). The web translates the label by key.
PAGES: list[tuple[str, str, str, str]] = [
    ("today", "/app", "I dag", "dagens overblik: aftaler, beskeder og om Dialogbot er tændt (pause)"),
    ("knowledge", "/app/viden", "Viden", "ydelser, priser, åbningstider, faste svar, emner den ikke må svare på; godkend kladder; test som kunde"),
    ("calls", "/app/opkald", "Opkald", "opkald og chats med udskrift og opsummering; overtag en webchat"),
    ("leads", "/app/opkald/henvendelser", "Henvendelser", "kunder der vil kontaktes, og opgaverne"),
    ("week", "/app/ugen", "Ugen", "ugens tal, forbrug og dagsrapporten"),
    ("bookings", "/app/aftaler", "Aftaler", "bookinger, aftaletyper og bookingregler"),
    ("campaigns", "/app/kampagner", "Kampagner", "udgående opkald til kontakter, der har sagt ja"),
    ("settings", "/app/indstillinger", "Alle indstillinger", "alle indstillinger samlet"),
    ("phone", "/app/indstillinger?ark=telefoni", "Telefon", "nummer, bekræftelse, viderestilling, prøveopkald, tænd/pause, samtalesprog"),
    ("greeting", "/app/indstillinger?ark=hilsen", "Hilsen og manuskript", "hilsen, navn, du/De, hvad den spørger om, hvornår en medarbejder overtager"),
    ("voice", "/app/indstillinger?ark=stemmer", "Stemme", "standardstemme, egen stemme, udtale af ord"),
    ("webchat", "/app/indstillinger?ark=webchat", "Webchat", "slå til, domæner, kode til hjemmesiden, velkomst"),
    ("booking", "/app/indstillinger?ark=booking", "Booking", "online booking, aftaletyper, iCal"),
    ("integrations", "/app/indstillinger?ark=integrationer", "Kalender og integrationer", "Google/Microsoft-kalender, SMS og andre systemer"),
    ("log", "/app/indstillinger?ark=log", "Aktivitetslog", "hvem ændrede hvad og hvornår"),
    ("account", "/app/konto", "Konto", "team, roller, invitationer, abonnement, kort, fakturaer, appens sprog"),
    ("help", "/app/hjaelp", "Hjælp", "hjælpeartikler"),
    ("setup1", "/opsaetning/virksomhed", "Om virksomheden", "guiden, trin 1: hjemmeside, navn, telefon, adresse, åbningstider, telefon og/eller chat"),
    ("setup_knowledge", "/opsaetning/viden", "Viden i guiden", "guiden: hent viden fra hjemmeside, fil eller tekst og godkend forslagene"),
    ("setup_phone", "/opsaetning/telefon", "Telefon i guiden", "guiden: stemme, nummer, viderestilling"),
    ("setup_chat", "/opsaetning/chat", "Chat i guiden", "guiden: domæne, velkomst, kode til hjemmesiden, prøv chatten"),
    ("setup2", "/opsaetning/kalender", "Kalender", "guiden: forbind kalenderen"),
    ("setup3", "/opsaetning/betaling", "Betaling og gå live", "guiden, sidste trin: abonnement, betalingskort, prøveopkald, gå live"),
]
PAGE_BY_HREF = {href: (key, label) for key, href, label, _ in PAGES}

# Where to send the person when the model is not available or did not understand.
LINKS = [
    (("lukket", "åbent", "åbning", "åbn"), "setup1"),
    (("pris", "koster", "ydelse"), "knowledge"),
    (("booking", "aftale", "kalender"), "bookings"),
    (("rapport",), "week"),
    (("telefon", "viderestil", "nummer"), "phone"),
    (("stemme", "udtal"), "voice"),
    (("hilsen", "manuskript"), "greeting"),
    (("faktura", "betal", "kort", "abonnement", "team", "invit"), "account"),
]

SYSTEM = """ASSISTANT_CHANGE
Du er Dialogbots assistent inde i appen. Du hjælper ejeren og medarbejderne i en virksomhed, der bruger Dialogbot (en digital receptionist til telefon og webchat). Personen skriver med egne ord. Du kan fire ting – vælg præcis én pr. svar:

1. "answer": svar på et spørgsmål om Dialogbot eller om deres egen opsætning. Brug KUN fakta fra PRODUKTVIDEN og NUVÆRENDE TILSTAND nedenfor. Fortæl konkret, hvor i appen det gøres, og giv højst ét link fra SIDER. Opfind aldrig priser, funktioner, tider eller trin. Er du ikke sikker, så sig det ærligt og vælg "request" i stedet.
2. "question": stil ét kort spørgsmål, hvis du mangler noget vigtigt for at svare eller lave ændringen (fx hvilken ydelse, eller hvilket klokkeslæt).
3. "change": personen vil have noget ændret, som passer til en af de KENDTE ÆNDRINGER. Udfyld den; du ændrer ikke selv noget – personen ser før → efter og trykker «Godkend». Opfind aldrig tal, priser, tider, tekster eller svar, som personen ikke har sagt. Højst én ændring ad gangen; vil de mere, så tag det første og sig, at du tager resten bagefter.
4. "request": personen vil have noget, Dialogbot ikke kan (ingen kendt ændring og ikke noget, produktviden beskriver), eller beder udtrykkeligt om en ny funktion, eller vil opsige. Skriv i "summary" én linje PÅ DANSK om ønsket og vælg "category". Sig venligt i "reply", at ønsket er sendt videre til Dialogbot-teamet – lov aldrig, at eller hvornår det bliver lavet. Kan noget beslægtet allerede gøres, så nævn det kort.

Regler:
- Svar kort og venligt (højst 4 korte sætninger), som til en travl håndværker. Ingen markdown.
- Skriv "reply" og "question" på {lang_name}, uanset sproget i produktviden. "summary" er altid på dansk.
- Priser er ekskl. moms. I "change" er priser i hele øre.
- Brug kun links fra SIDER, og kun deres href præcis som skrevet.
- Personens rolle står i tilstanden. Kræver ændringen en højere rolle, så vælg "change" alligevel – serveren siger det til personen.
- Tidligere beskeder i samtalen er kontekst; svar på den sidste besked.

Svar med ét JSON-objekt og intet andet:
{{"type": "answer|question|change|request", "reply": "…", "link": "/app/… eller null", "question": "kun ved question", "kind": "kun ved change", "params": {{…}}, "summary": "kun ved request", "category": "{categories}"}}

KENDTE ÆNDRINGER:
{kinds}

SIDER (href – navn: indhold):
{pages}

PRODUKTVIDEN:
{guide}

NUVÆRENDE TILSTAND:
{state}
Siden personen står på: {page}"""


@lru_cache
def guide() -> str:
    """The maintained product guide (guide.md), from its first section on (without the title and maintenance note)."""
    text = (Path(__file__).with_name("guide.md")).read_text(encoding="utf-8")
    return "## " + text.split("\n## ", 1)[1] if "\n## " in text else text


def _role_text(ctx: WorkspaceContext) -> str:
    names = {"owner": "ejer", "admin": "administrator", "staff": "medarbejder", "reader": "læser"}
    can = sorted({k.label for k in KINDS.values() if ctx.can("assistant.change") and ctx.can(k.needs)})
    return f"{names.get(ctx.role, ctx.role)} (kan få ændret: {', '.join(can) if can else 'intet – kun spørge'})"


def _state(db: OrmSession, ctx: WorkspaceContext) -> str:
    ws_id = ctx.workspace.id
    lines = [f"Virksomhed: {ctx.workspace.name}", f"Personens rolle: {_role_text(ctx)}"]
    prof = db.get(BusinessProfile, ws_id)
    if prof is not None:
        addr = ", ".join(x for x in (prof.address_line, " ".join(y for y in (prof.postal_code, prof.city) if y)) if x)
        lines.append(f"Profil: telefon {prof.phone or 'ikke angivet'}; hjemmeside {prof.website_url or 'ikke angivet'}; "
                     f"adresse {addr or 'ikke angivet'}; beskrivelse: {(prof.description or 'ikke angivet')[:300]}")
    items = knowledge.active_knowledge(db, ws_id, ("public", "customer_docs"))  # goes into a prompt: never internal
    hours = next((i for i in items if i["kind"] == "opening_hours"), None)
    lines.append("Åbningstider: " + ((hours_text((hours["content"] or {}).get("weekly")) if hours else "") or "ikke angivet"))
    services = 0
    for i in items:
        if i["kind"] == "service" and services < 40:
            services += 1
            c = i["content"] or {}
            price = kr(c["price_net_minor"]) + (f" {UNITS[c['unit']]}" if c.get("unit") in UNITS else "") if isinstance(c.get("price_net_minor"), int) else "ingen pris"
            lines.append(f"Ydelse: {i['title']} – {price}")
    lines.append(f"Godkendt viden i alt: {len(items)} emner")
    tel = db.get(TelephonySetup, ws_id)
    numbers = db.scalars(select(PhoneNumber).where(PhoneNumber.workspace_id == ws_id, PhoneNumber.status != "released")).all()
    tel_state = {"active": "tændt", "paused": "sat på pause"}.get(tel.state, "under opsætning") if tel else "ikke påbegyndt"
    lines.append(f"Telefon: {tel_state}; virksomhedens nummer {(tel.business_number if tel else None) or 'ikke angivet'}; "
                 f"viderestilling {({'always': 'altid', 'no_answer': 'ved ingen svar', 'busy_or_no_answer': 'ved optaget eller ingen svar'}.get(tel.forwarding_mode, '?') if tel else 'ikke valgt')}; "
                 f"Dialogbot-numre: {len(numbers)}")
    s = db.get(ReceptionScript, ws_id)
    lines.append(f"Hilsen: {(s.greeting if s and s.greeting else 'standardhilsen')[:300]}; navn: {(s.persona_name if s else '') or 'intet'}; "
                 f"tiltale: {s.address_form if s else 'du'}; medarbejder overtager når: {((s.escalation if s else '') or 'ikke angivet')[:300]}")
    from app.modules.assistant.kinds import _voice_text

    lines.append(f"Stemme: {_voice_text(db, ws_id)}")
    ls = db.get(LanguageSettings, ws_id)
    if ls is not None:
        lines.append(f"Samtalesprog: standard {NAME_DA.get(normalize(ls.default_conversation_language), '?')}; slået til: "
                     + ", ".join(NAME_DA.get(normalize(c), c) for c in ls.enabled_conversation_languages or []))
    wc = db.get(WebchatSettings, ws_id)
    lines.append(f"Webchat: {'slået til' if wc and wc.enabled else 'slået fra'}; domæner: {len(wc.allowed_origins) if wc else 0}; "
                 f"velkomst: {(wc.greeting if wc and wc.greeting else 'standard')[:200]}")
    b = bookings.settings(db, ws_id)
    lines.append(f"Booking: {'online booking slået til' if b.enabled else 'online booking slået fra'}; pause {b.buffer_minutes} min, "
                 f"tidligst om {b.lead_time_hours} timer, op til {b.horizon_days} dage frem; iCal: {'ja' if b.busy_ics_url else 'nej'}")
    conns = db.scalars(select(IntegrationConnection.connector).where(IntegrationConnection.workspace_id == ws_id,
                                                                      IntegrationConnection.status == "connected")).all()
    lines.append("Forbundne systemer: " + (", ".join(conns) if conns else "ingen"))
    r = reports.settings_for(db, ws_id)
    lines.append(f"Dagsrapport: kl. {r.send_hour_local:02d}, {'slået til' if r.email_enabled else 'slået fra'}")
    camps = db.execute(select(Campaign.status, func.count()).where(Campaign.workspace_id == ws_id).group_by(Campaign.status)).all()
    lines.append("Kampagner: " + (", ".join(f"{n} {st}" for st, n in camps) if camps else "ingen"))
    members = db.scalar(select(func.count()).select_from(Membership).where(Membership.workspace_id == ws_id)) or 0
    lines.append(f"Team: {members} personer")
    return "\n".join(lines)


def _parse(text: str) -> dict:
    start, end = text.find("{"), text.rfind("}")
    try:
        data = json.loads(text[start:end + 1]) if start >= 0 < end else {}
    except ValueError:
        data = {}
    return data if isinstance(data, dict) else {}


def _clean(v, n: int) -> str:
    return re.sub(r"\s+", " ", str(v or "")).strip()[:n]


def _link(key: str) -> dict:
    href = next(h for k, h, _, _ in PAGES if k == key)
    return {"key": key, "label": PAGE_BY_HREF[href][1], "href": href}


def _link_for(href) -> dict | None:
    if not isinstance(href, str) or href.strip() not in PAGE_BY_HREF:
        return None
    key, label = PAGE_BY_HREF[href.strip()]
    return {"key": key, "label": label, "href": href.strip()}


def _result(type_: str, reply: str, *, link: dict | None = None, proposal: dict | None = None, request: dict | None = None,
            code: str | None = None, **vars_) -> dict:
    return {"type": type_, "reply": reply, "link": link, "proposal": proposal, "request": request, "code": code, "vars": vars_ or None}


def _fallback(text: str) -> dict:
    low = text.lower()
    for words, key in LINKS:
        if any(w in low for w in words):
            ln = _link(key)
            return _result("fallback", f"Det kan jeg ikke ændre ud fra det, du skrev. Du kan gøre det under «{ln['label']}».",
                           link=ln, code="link_only")
    return _result("fallback", "Det er jeg ikke sikker på, at jeg forstod. Spørg om noget i Dialogbot, eller fortæl, hvad der skal "
                   "ændres – fx åbningstider, en pris, hilsenen, stemmen eller bookingregler – eller find det under Alle indstillinger.",
                   link=_link("settings"), code="not_understood")


def _out(p: AssistantProposal, reply: str) -> dict:
    return _result("change", reply, proposal={"id": str(p.id), "kind": p.kind, "label": KINDS[p.kind].label, "summary": p.summary,
                                              "before": p.before, "after": p.after, "expires_at": p.expires_at.isoformat()})


def _messages(history: list[dict] | None, text: str) -> list[dict]:
    """The last turns plus this one, as alternating user/assistant messages that start and end with the person."""
    turns = [(h["role"], _clean(h.get("text"), 2000)) for h in (history or [])[-HISTORY_TURNS:]
             if h.get("role") in ("user", "assistant") and _clean(h.get("text"), 10)]
    turns.append(("user", text))
    while turns and turns[0][0] != "user":
        turns.pop(0)
    out: list[dict] = []
    for role, t in turns:
        if out and out[-1]["role"] == role:
            out[-1]["content"] += "\n" + t
        else:
            out.append({"role": role, "content": t})
    return out


def propose(db: OrmSession, ctx: WorkspaceContext, *, text: str, page: str | None, request_id: str | None,
            history: list[dict] | None = None) -> dict:
    """One turn of the conversation. Returns {type, reply, link, proposal, request, code, vars}."""
    text = re.sub(r"\s+", " ", text).strip()
    lang = normalize(getattr(ctx.principal.user, "interface_language", None))
    system = SYSTEM.format(kinds="\n".join(f"- {k.key} ({k.label}): {k.help}" for k in KINDS.values()),
                           pages="\n".join(f"- {href} – {label}: {what}" for _, href, label, what in PAGES),
                           guide=guide(), state=_state(db, ctx), page=(page or "ukendt")[:80],
                           lang_name=NAME_DA.get(lang, "dansk"), categories="|".join(ASSISTANT_REQUEST_CATEGORIES))
    try:
        provider = get_provider()
        c, row = log_call(db, ctx.workspace, provider, user_id=ctx.user_id, purpose="assistant_change", system=system,
                          messages=_messages(history, text), prompt_version=PROMPT_VERSION,
                          revision=ctx.workspace.knowledge_revision, max_tokens=900)
        db.commit()
    except ApiError:
        db.rollback()
        return {**_fallback(text), "reply": "Jeg kan ikke tolke fri tekst lige nu. Brug en genvej, eller find det under Alle indstillinger.",
                "code": "ai_off"}
    if row.outcome != "ok":
        return _fallback(text)
    data = _parse(c.text)
    reply = _clean(data.get("reply"), 700)
    kind_key = str(data.get("kind") or "")
    type_ = str(data.get("type") or ("change" if kind_key else "question" if data.get("question") else ""))
    if type_ == "question" or (data.get("question") and type_ not in ("answer", "request")):
        q = _clean(data.get("question"), 400) or reply
        return _result("question", q, link=_link_for(data.get("link"))) if q else _fallback(text)
    if type_ == "answer":
        return _result("answer", reply, link=_link_for(data.get("link"))) if reply else _fallback(text)
    if type_ == "request":
        cat = str(data.get("category") or "other")
        row_, duplicate = wishes.record(db, ctx, text=text, summary=_clean(data.get("summary"), 300), category=cat, page=page,
                                        request_id=request_id)
        db.commit()
        return _result("request", reply or "Det kan Dialogbot ikke endnu. Jeg har sendt ønsket videre til Dialogbot-teamet.",
                       link=_link_for(data.get("link")), code="request_duplicate" if duplicate else "request_logged",
                       request={"id": str(row_.id), "summary": row_.summary, "duplicate": duplicate})
    kind = KINDS.get(kind_key)
    if kind is None:
        return {**_fallback(text), **({"reply": reply, "code": None} if reply else {})}
    if not (ctx.can("assistant.change") and ctx.can(kind.needs)):
        role = {"owner": "en ejer", "admin": "en ejer eller administrator", "staff": "en medarbejder eller højere"}.get(PERMISSIONS[kind.needs], "en ejer eller administrator")
        if not ctx.can("assistant.change"):
            role = "en medarbejder eller højere"
        return _result("fallback", f"{kind.label} kan kun ændres af {role}. Bed dem om at gøre det, eller sig det til dem.",
                       code="role_needed", label=kind.label)
    try:
        params = kind.validate(data.get("params") if isinstance(data.get("params"), dict) else {})
        summary, before, after = kind.describe(db, ctx, params)
    except Conflict as e:
        return _result("fallback", e.message, link=_link_for(kind.href))
    except ApiError:
        return _result("question", "Jeg fik ikke fat i alle detaljerne. Skriv det gerne lidt mere præcist – fx hvilken ydelse, og hvad den skal koste.",
                       code="details_missing")
    if before == after:
        return _result("fallback", "Det er allerede sådan, så der er intet at ændre.", code="already")
    p = AssistantProposal(workspace_id=ctx.workspace.id, user_id=ctx.user_id, kind=kind.key, params=params, request_text=text[:1000],
                          summary=summary[:500], before=before[:1000], after=after[:1500], status="proposed",
                          expires_at=datetime.now(UTC) + TTL)
    db.add(p)
    db.flush()
    record_audit(db, workspace_id=ctx.workspace.id, actor_user_id=ctx.user_id, action="assistant.change_proposed", object_type="assistant_proposal",
                 object_id=p.id, after={"kind": kind.key, "summary": p.summary}, request_id=request_id)
    db.commit()
    return _out(p, reply or "Sådan ser det ud – godkend, hvis det er rigtigt.")


def _load(db: OrmSession, ctx: WorkspaceContext, pid: uuid.UUID) -> AssistantProposal:
    p = db.scalar(select(AssistantProposal).where(AssistantProposal.id == pid, AssistantProposal.workspace_id == ctx.workspace.id,
                                                  AssistantProposal.user_id == ctx.user_id).with_for_update())
    if p is None:
        raise NotFound("Forslaget findes ikke")
    return p


def apply(db: OrmSession, ctx: WorkspaceContext, pid: uuid.UUID, *, request_id: str | None) -> dict:
    ctx.require("assistant.change")
    p = _load(db, ctx, pid)
    if p.status != "proposed":
        raise Conflict("Forslaget er allerede behandlet.", code="assistant_proposal_closed")
    if p.expires_at <= datetime.now(UTC):
        p.status = "expired"
        db.commit()
        raise Conflict("Forslaget er udløbet. Sig det igen, så laver jeg et nyt.", code="assistant_proposal_expired")
    kind = KINDS[p.kind]
    ctx.require(kind.needs)
    params = kind.validate(p.params)
    message = kind.apply(db, ctx, params, request_id)
    p.status, p.decided_at = "applied", datetime.now(UTC)
    record_audit(db, workspace_id=ctx.workspace.id, actor_user_id=ctx.user_id, action="assistant.change_applied", object_type="assistant_proposal",
                 object_id=p.id, before={"text": p.before}, after={"kind": p.kind, "text": p.after, "request": p.request_text}, request_id=request_id)
    db.commit()
    return {"ok": True, "message": message, "href": kind.href}


def decline(db: OrmSession, ctx: WorkspaceContext, pid: uuid.UUID, *, request_id: str | None) -> dict:
    ctx.require("assistant.change")
    p = _load(db, ctx, pid)
    if p.status == "proposed":
        p.status, p.decided_at = "declined", datetime.now(UTC)
        record_audit(db, workspace_id=ctx.workspace.id, actor_user_id=ctx.user_id, action="assistant.change_declined", object_type="assistant_proposal",
                     object_id=p.id, after={"kind": p.kind}, request_id=request_id)
        db.commit()
    return {"ok": True}

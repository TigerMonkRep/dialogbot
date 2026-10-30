"""«Ændr noget»: the person says what to change; the model picks one of the known change kinds; the server validates it
and shows before → after. Nothing is changed until `apply` (the person's «Godkend»).

Rules this module enforces itself, whatever the model says:
* only the kinds in `kinds.KINDS`; params are re-validated here;
* the person needs the role the change itself needs (e.g. approving knowledge = owner/admin) – checked when proposing, so a
  proposal the person could not apply is never shown;
* a proposal belongs to one workspace and one person, is applied at most once and expires after 30 minutes;
* if the model cannot be reached or does not understand, the answer is a question or a link – never an error."""
from __future__ import annotations

import json
import re
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from app.core.audit import record_audit
from app.core.auth import WorkspaceContext
from app.core.errors import ApiError, Conflict, NotFound
from app.models import AssistantProposal
from app.modules.ai.provider import get_provider
from app.modules.ai.service import log_call
from app.modules.assistant.kinds import KINDS, UNITS, hours_text, kr
from app.modules.bookings import service as bookings
from app.modules.knowledge import service as knowledge
from app.modules.reports import service as reports

PROMPT_VERSION = "assistant-change-v1"
TTL = timedelta(minutes=30)

# Where to send the person when the assistant cannot make the change itself.
LINKS = [
    (("lukket", "åbent", "åbning", "åbn"), "Åbningstider", "/opsaetning/1"),
    (("pris", "koster", "ydelse"), "Det I sælger", "/app/viden"),
    (("booking", "aftale", "kalender"), "Aftaler", "/app/aftaler"),
    (("rapport",), "Ugen", "/app/ugen"),
    (("telefon", "viderestil", "nummer", "stemme", "hilsen"), "Telefon", "/app/indstillinger/telefoni"),
]

SYSTEM = """ASSISTANT_CHANGE
Du hjælper ejeren af en dansk virksomhed med at ændre indstillinger i deres digitale receptionist. Personen skriver med egne ord, hvad der skal ændres. Din opgave er KUN at vælge én af de kendte ændringer og udfylde den – du ændrer ikke selv noget, og personen ser og godkender ændringen bagefter.

Kendte ændringer:
{kinds}

Regler:
- Vælg højst én ændring. Opfind aldrig tal, priser, tider eller svar, som personen ikke har sagt.
- Hvis personen mangler at sige noget vigtigt (fx hvilken ydelse, eller hvilket klokkeslæt), så stil ét kort spørgsmål i stedet.
- Hvis ønsket ikke passer til nogen af ændringerne, så sæt kind til null og forklar kort i "reply", hvor det kan ændres (fx "Det ændrer du under Alle indstillinger").
- Priser opgives ekskl. moms, i hele øre.
Svar med ét JSON-objekt og intet andet:
{{"kind": "<en af ovenstående eller null>", "params": {{...}}, "reply": "kort besked til personen på dansk", "question": "kun hvis du mangler noget"}}

Nuværende tilstand:
{state}
Siden personen står på: {page}"""


def _state(db: OrmSession, ws_id: uuid.UUID) -> str:
    lines = []
    items = knowledge.active_knowledge(db, ws_id, ("public", "customer_docs"))  # goes into a prompt: never internal
    hours = next((i for i in items if i["kind"] == "opening_hours"), None)
    lines.append("Åbningstider: " + ((hours_text((hours["content"] or {}).get("weekly")) if hours else "") or "ikke angivet"))
    for i in items:
        if i["kind"] == "service":
            c = i["content"] or {}
            price = kr(c["price_net_minor"]) + (f" {UNITS[c['unit']]}" if c.get("unit") in UNITS else "") if isinstance(c.get("price_net_minor"), int) else "ingen pris"
            lines.append(f"Ydelse: {i['title']} – {price}")
    b = bookings.settings(db, ws_id)
    lines.append(f"Booking: pause {b.buffer_minutes} min, tidligst om {b.lead_time_hours} timer, op til {b.horizon_days} dage frem")
    r = reports.settings_for(db, ws_id)
    lines.append(f"Dagsrapport: kl. {r.send_hour_local:02d}, {'slået til' if r.email_enabled else 'slået fra'}")
    return "\n".join(lines)


def _parse(text: str) -> dict:
    start, end = text.find("{"), text.rfind("}")
    try:
        data = json.loads(text[start:end + 1]) if start >= 0 < end else {}
    except ValueError:
        data = {}
    return data if isinstance(data, dict) else {}


def _fallback(text: str) -> dict:
    low = text.lower()
    for words, label, href in LINKS:
        if any(w in low for w in words):
            return {"proposal": None, "reply": f"Det kan jeg ikke ændre ud fra det, du skrev. Du kan gøre det under «{label}».", "link": {"label": label, "href": href}}
    return {"proposal": None, "reply": "Det er jeg ikke sikker på, at jeg forstod. Fortæl, hvad der skal ændres – fx åbningstider, en pris, et svar, bookingregler eller dagsrapporten – eller find det under Alle indstillinger.",
            "link": {"label": "Alle indstillinger", "href": "/app/indstillinger"}}


def _out(p: AssistantProposal, reply: str) -> dict:
    return {"proposal": {"id": str(p.id), "kind": p.kind, "label": KINDS[p.kind].label, "summary": p.summary, "before": p.before,
                         "after": p.after, "expires_at": p.expires_at.isoformat()}, "reply": reply}


def propose(db: OrmSession, ctx: WorkspaceContext, *, text: str, page: str | None, request_id: str | None) -> dict:
    ctx.require("assistant.change")
    text = re.sub(r"\s+", " ", text).strip()
    system = SYSTEM.format(kinds="\n".join(f"- {k.key} ({k.label}): {k.help}" for k in KINDS.values()),
                           state=_state(db, ctx.workspace.id), page=(page or "ukendt")[:80])
    try:
        provider = get_provider()
        c, row = log_call(db, ctx.workspace, provider, user_id=ctx.user_id, purpose="assistant_change", system=system,
                          messages=[{"role": "user", "content": text}], prompt_version=PROMPT_VERSION,
                          revision=ctx.workspace.knowledge_revision, max_tokens=700)
        db.commit()
    except ApiError:
        db.rollback()
        return {**_fallback(text), "reply": "Jeg kan ikke tolke fri tekst lige nu. Brug en genvej, eller find det under Alle indstillinger."}
    if row.outcome != "ok":
        return _fallback(text)
    data = _parse(c.text)
    reply = re.sub(r"\s+", " ", str(data.get("reply") or "")).strip()[:400]
    if data.get("question"):
        return {"proposal": None, "reply": re.sub(r"\s+", " ", str(data["question"])).strip()[:300]}
    kind = KINDS.get(str(data.get("kind") or ""))
    if kind is None:
        return {**_fallback(text), **({"reply": reply} if reply else {})}
    if not ctx.can(kind.needs):
        return {"proposal": None, "reply": f"{kind.label} kan kun ændres af en ejer eller administrator. Bed dem om at gøre det, eller sig det til dem.",
                "link": None}
    try:
        params = kind.validate(data.get("params") if isinstance(data.get("params"), dict) else {})
        summary, before, after = kind.describe(db, ctx, params)
    except Conflict as e:
        return {"proposal": None, "reply": e.message}
    except ApiError:
        return {"proposal": None, "reply": "Jeg fik ikke fat i alle detaljerne. Skriv det gerne lidt mere præcist – fx hvilken ydelse, og hvad den skal koste."}
    if before == after:
        return {"proposal": None, "reply": "Det er allerede sådan, så der er intet at ændre."}
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

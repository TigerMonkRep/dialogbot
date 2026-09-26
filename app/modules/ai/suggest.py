"""AI suggestions for the setup guide: the model proposes, the owner edits and saves.

Nothing here writes to the workspace – the endpoint returns suggestions only. The context is the
business profile, chosen categories and the knowledge titles (drafts included: this is owner-facing
setup help, never an answer to a customer). Every call is logged in `ai_usage` (purpose
`setup_suggestion`).
"""
from __future__ import annotations

import json
import re

from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from app.core.errors import ApiError
from app.models import BusinessProfile, KnowledgeItem, KnowledgeVersion, Workspace, WorkspaceCategory
from app.modules.ai.provider import get_provider
from app.modules.ai.service import log_call

PROMPT_VERSION = "setup-suggest-v1"

GOALS_SYSTEM = """SUGGEST_GOALS
Du hjælper en dansk virksomhed med at sætte deres digitale receptionist op. Ud fra oplysningerne om virksomheden skal du foreslå:
1) 3-6 samtalemål: korte, konkrete formuleringer af hvad kunderne typisk henvender sig for, og hvad receptionisten skal opnå (fx "Uforpligtende tilbud på gulvafslibning – få kvadratmeter, gulvtype og adresse"). Skriv på naturligt dansk, uden nummerering.
2) Hvilke kanaler der giver mening: inbound_phone (tager telefonen), webchat (chat på hjemmesiden – kun hvis de har en hjemmeside), callback (kunden bestiller et opkald), booking (kunden booker selv en tid – kun hvis ydelserne passer til faste tider, fx konsultationer eller besigtigelser).
Byg kun på oplysningerne. Svar med ét JSON-objekt og intet andet:
{"conversation_goals": ["..."], "channels": {"inbound_phone": true, "webchat": true, "callback": true, "booking": false}, "reason": "én sætning om valget af kanaler"}"""


class SuggestionFailed(ApiError):
    status_code = 502
    code = "suggestion_failed"


def context(db: OrmSession, ws: Workspace) -> str:
    p = db.get(BusinessProfile, ws.id)
    cats = db.scalars(select(WorkspaceCategory.label).where(WorkspaceCategory.workspace_id == ws.id)).all()
    rows = db.execute(
        select(KnowledgeItem.kind, KnowledgeVersion.title, KnowledgeVersion.content)
        .join(KnowledgeVersion, KnowledgeVersion.item_id == KnowledgeItem.id)
        .where(KnowledgeItem.workspace_id == ws.id, KnowledgeItem.archived_at.is_(None),
               KnowledgeVersion.status.in_(("draft", "in_review", "approved")))
        .limit(60)).all()
    lines = [f"Virksomhed: {ws.name}"]
    if p:
        for label, v in (("Beskrivelse", p.description), ("Hjemmeside", p.website_url), ("By", p.city)):
            if v:
                lines.append(f"{label}: {v}")
    if cats:
        lines.append("Brancher: " + ", ".join(cats))
    for kind, title, content in rows:
        desc = (content or {}).get("description") or (content or {}).get("text") or ""
        lines.append(f"- {kind}: {title}" + (f" – {str(desc)[:200]}" if desc else ""))
    return "\n".join(lines)


def _json(text: str) -> dict:
    start, end = text.find("{"), text.rfind("}")
    try:
        data = json.loads(text[start:end + 1]) if start >= 0 < end else {}
    except ValueError:
        data = {}
    if not isinstance(data, dict) or not data:
        raise SuggestionFailed("AI-forslaget kunne ikke læses. Prøv igen.")
    return data


def goals(db: OrmSession, ws: Workspace, user_id) -> dict:
    provider = get_provider()
    ctx = context(db, ws)
    c, row = log_call(db, ws, provider, user_id=user_id, purpose="setup_suggestion", system=GOALS_SYSTEM,
                      messages=[{"role": "user", "content": ctx}], prompt_version=PROMPT_VERSION,
                      revision=ws.knowledge_revision, max_tokens=1500)
    db.commit()
    if row.outcome == "refused":
        raise SuggestionFailed("AI-udbyderen afviste at lave forslag.")
    data = _json(c.text)
    goals_out = []
    for g in (data.get("conversation_goals") or [])[:6]:
        g = re.sub(r"\s+", " ", str(g)).strip().lstrip("-•0123456789. ").strip()[:200]
        if g:
            goals_out.append(g)
    ch = data.get("channels") if isinstance(data.get("channels"), dict) else {}
    p = db.get(BusinessProfile, ws.id)
    channels = {k: bool(ch.get(k, default)) for k, default in
                (("inbound_phone", True), ("webchat", False), ("callback", True), ("booking", False))}
    if not (p and p.website_url):
        channels["webchat"] = False  # a chat widget needs a website
    return {"conversation_goals": goals_out, "channels": channels,
            "reason": re.sub(r"\s+", " ", str(data.get("reason") or "")).strip()[:300]}

"""Assistant prompt building and per-workspace usage logging.

The system prompt is built ONLY from `knowledge.service.active_knowledge` (approved, current,
non-archived versions). Drafts, submissions and raw sources never reach a model. Every call,
including a failed one, writes one `ai_usage` row with model, prompt version, knowledge
revision and tokens; the prompt text itself is not stored.
"""
from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session as OrmSession

from app.config import get_settings
from app.core.errors import ApiError, Conflict
from app.models import AiUsage, Workspace
from app.modules.ai.provider import Completion, get_provider
from app.modules.knowledge import service as knowledge

# Bump whenever the instructions below change, so usage and quality can be compared per version.
PROMPT_VERSION = "assistant-v1"

INSTRUCTIONS = """Du er den digitale receptionist for virksomheden "{name}". Du svarer kunder på vegne af virksomheden.

Regler:
- Brug udelukkende oplysningerne i <godkendt_viden> nedenfor. Det er virksomhedens godkendte viden; intet andet er bekræftet.
- Hvis svaret ikke fremgår af den godkendte viden, så sig det ærligt og tilbyd, at en medarbejder vender tilbage. Gæt aldrig på priser, tider, tilbud eller vilkår.
- Priser i den godkendte viden er angivet i hele øre ekskl. moms (fx price_net_minor 14500 = 145,00 kr. ekskl. moms), medmindre andet står.
- Du kan ikke booke, ringe op, tage imod betaling eller love noget på virksomhedens vegne. Sig det, hvis kunden beder om det.
- Svar kort, venligt og på kundens sprog (standard dansk).

<godkendt_viden revision="{revision}">
{knowledge}
</godkendt_viden>"""

REFUSAL_TEXT = "Det kan jeg desværre ikke hjælpe med. En medarbejder kan kontakte dig, hvis du ønsker det."

# Public list prices in USD per million tokens (input, output). Cache writes cost 1.25x input,
# cache reads 0.1x input. Unknown models are logged without a cost estimate.
PRICES_USD_PER_MTOK: dict[str, tuple[float, float]] = {
    "claude-opus-5": (5.0, 25.0),
    "claude-fable-5-1": (5.0, 25.0),
    "claude-sonnet-5": (3.0, 15.0),
    "claude-haiku-4-5": (1.0, 5.0),
}


def _price(model: str) -> tuple[float, float] | None:
    for prefix, p in PRICES_USD_PER_MTOK.items():
        if model == prefix or model.startswith(prefix + "-"):
            return p
    return None


def estimate_cost_usd_micros(c: Completion) -> int | None:
    p = _price(c.served_model or c.requested_model)
    if p is None:
        return None
    inp, out = p
    u = c.usage
    usd = (u.input_tokens * inp + u.cache_creation_input_tokens * inp * 1.25
           + u.cache_read_input_tokens * inp * 0.1 + u.output_tokens * out) / 1_000_000
    return round(usd * 1_000_000)


def build_system_prompt(db: OrmSession, workspace: Workspace) -> tuple[str, int]:
    items = knowledge.active_knowledge(db, workspace.id)
    if not items:
        raise Conflict("Der er ingen godkendt viden endnu. Godkend mindst ét vidensemne, før assistenten kan svare.",
                       code="no_approved_knowledge")
    body = "\n".join(json.dumps({"type": i["kind"], "titel": i["title"], "indhold": i["content"]}, ensure_ascii=False)
                     for i in items)
    return INSTRUCTIONS.format(name=workspace.name, revision=workspace.knowledge_revision, knowledge=body), \
        workspace.knowledge_revision


# Channel-specific additions to the system prompt; the logged prompt version includes the suffix.
CHANNEL_INSTRUCTIONS: dict[str, tuple[str, str]] = {
    "webchat": ("webchat-v1", "Kanal: webchat på virksomhedens hjemmeside. Hvis kunden vil kontaktes, have et tilbud, "
                              "booke eller tale med en medarbejder, så bed dem trykke på knappen \"Bliv kontaktet\" "
                              "under chatten og efterlade navn og e-mail eller telefon. Bed ikke om CPR-nummer eller "
                              "betalingsoplysninger."),
    "phone": ("phone-v1", "Kanal: telefonopkald. Svar kort og i hele sætninger, uden punktopstillinger, links eller "
                          "formatering – alt bliver læst højt. Hvis kunden vil kontaktes, have et tilbud, booke eller tale "
                          "med en medarbejder, så sig, at en medarbejder ringer tilbage på det nummer, de ringer fra, og "
                          "spørg om deres navn. Du kan ikke stille om, booke eller tage imod betaling."),
}


def complete_logged(db: OrmSession, workspace: Workspace, *, user_id: uuid.UUID | None, purpose: str,
                    messages: list[dict], channel: str | None = None) -> tuple[Completion, AiUsage]:
    """Call the provider with the approved-knowledge prompt and log one `ai_usage` row.

    Commits the usage row (also on failure, then re-raises). `messages` is the conversation so far,
    alternating user/assistant and ending with the user's turn."""
    provider = get_provider()  # 501 before anything else when AI is not configured
    system, revision = build_system_prompt(db, workspace)
    prompt_version = PROMPT_VERSION
    if channel in CHANNEL_INSTRUCTIONS:
        suffix, text = CHANNEL_INSTRUCTIONS[channel]
        system, prompt_version = f"{system}\n\n{text}", f"{PROMPT_VERSION}+{suffix}"
    settings = get_settings()
    row = AiUsage(workspace_id=workspace.id, user_id=user_id, purpose=purpose, provider=provider.name,
                  requested_model=provider.model, prompt_version=prompt_version, knowledge_revision=revision)
    try:
        c = provider.complete(system=system, messages=messages, max_tokens=settings.ai_max_output_tokens)
    except ApiError as e:
        row.outcome, row.error_code = "error", e.code
        row.provider_request_id = (e.extra or {}).get("provider_request_id")
        db.add(row)
        db.commit()
        raise
    row.outcome = "refused" if c.stop_reason == "refusal" else "truncated" if c.stop_reason == "max_tokens" else "ok"
    row.served_model, row.stop_reason = c.served_model, c.stop_reason[:32]
    row.input_tokens, row.output_tokens = c.usage.input_tokens, c.usage.output_tokens
    row.cache_creation_input_tokens = c.usage.cache_creation_input_tokens
    row.cache_read_input_tokens = c.usage.cache_read_input_tokens
    row.est_cost_usd_micros = estimate_cost_usd_micros(c)
    row.latency_ms, row.provider_request_id = c.latency_ms, c.request_id
    db.add(row)
    db.flush()
    return c, row


def visible_reply(c: Completion) -> str:
    """What a person may see: never a refusal's partial text, never an empty bubble."""
    if c.stop_reason == "refusal" or not c.text:
        return REFUSAL_TEXT
    return c.text


def preview_reply(db: OrmSession, workspace: Workspace, user_id: uuid.UUID, message: str) -> dict:
    """One-turn answer for staff testing the assistant against the approved knowledge."""
    c, row = complete_logged(db, workspace, user_id=user_id, purpose="assistant_preview",
                             messages=[{"role": "user", "content": message}])
    db.commit()
    return {
        "reply": visible_reply(c),
        "refused": row.outcome == "refused",
        "truncated": row.outcome == "truncated",
        "stop_reason": c.stop_reason,
        "model": c.served_model,
        "prompt_version": PROMPT_VERSION,
        "knowledge_revision": row.knowledge_revision,
        "usage": {"input_tokens": row.input_tokens, "output_tokens": row.output_tokens,
                  "cache_creation_input_tokens": row.cache_creation_input_tokens,
                  "cache_read_input_tokens": row.cache_read_input_tokens,
                  "est_cost_usd_micros": row.est_cost_usd_micros},
    }


def usage_summary(db: OrmSession, workspace_id: uuid.UUID, days: int) -> dict:
    since = datetime.now(UTC) - timedelta(days=days)
    where = (AiUsage.workspace_id == workspace_id, AiUsage.created_at >= since)
    rows = db.execute(
        select(AiUsage.served_model, AiUsage.requested_model, AiUsage.prompt_version, AiUsage.outcome,
               func.count(), func.sum(AiUsage.input_tokens), func.sum(AiUsage.output_tokens),
               func.sum(AiUsage.cache_creation_input_tokens), func.sum(AiUsage.cache_read_input_tokens),
               func.sum(AiUsage.est_cost_usd_micros))
        .where(*where)
        .group_by(AiUsage.served_model, AiUsage.requested_model, AiUsage.prompt_version, AiUsage.outcome)
        .order_by(AiUsage.requested_model, AiUsage.prompt_version, AiUsage.outcome)
    ).all()
    groups = [{"model": served or requested, "requested_model": requested, "prompt_version": pv, "outcome": outcome,
               "calls": n, "input_tokens": int(i or 0), "output_tokens": int(o or 0),
               "cache_creation_input_tokens": int(cw or 0), "cache_read_input_tokens": int(cr or 0),
               "est_cost_usd_micros": int(cost) if cost is not None else None}
              for served, requested, pv, outcome, n, i, o, cw, cr, cost in rows]
    return {
        "workspace_id": str(workspace_id),
        "since": since.isoformat(),
        "days": days,
        "totals": {k: sum(g[k] for g in groups) for k in
                   ("calls", "input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")}
        | {"est_cost_usd_micros": sum(g["est_cost_usd_micros"] or 0 for g in groups)},
        "groups": groups,
    }

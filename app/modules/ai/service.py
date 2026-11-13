"""Assistant prompt building and per-workspace usage logging.

The system prompt is built ONLY from `knowledge.service.active_knowledge` (approved, current,
non-archived versions). Drafts, submissions and raw sources never reach a model. Every call,
including a failed one, writes one `ai_usage` row with model, prompt version, knowledge
revision and tokens; the prompt text itself is not stored.
"""
from __future__ import annotations

import json
import uuid
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session as OrmSession

from app.config import get_settings
from app.core.errors import ApiError, Conflict
from app.models import AiUsage, Workspace
from app.modules.ai.provider import Completion, get_provider
from app.modules.knowledge import service as knowledge

# Bump whenever the instructions below change, so usage and quality can be compared per version.
PROMPT_VERSION = "assistant-v2"

INSTRUCTIONS = """Du er den digitale receptionist for virksomheden "{name}". Du svarer kunder på vegne af virksomheden.

Regler:
- Brug udelukkende oplysningerne i <godkendt_viden> nedenfor. Det er virksomhedens godkendte viden; intet andet er bekræftet.
- Hvis svaret ikke fremgår af den godkendte viden, så sig det ærligt og tilbyd, at en medarbejder vender tilbage. Gæt aldrig på priser, tider, tilbud eller vilkår.
- Hver linje i <godkendt_viden> er ét emne: type · titel: indhold. Priser er angivet i hele øre ekskl. moms (fx price_net_minor 14500 = 145,00 kr. ekskl. moms), medmindre andet står.
- Du kan ikke booke, ringe op, tage imod betaling eller love noget på virksomhedens vegne. Sig det, hvis kunden beder om det.
- Ydelser med "promote": false nævner du kun, hvis kunden selv spørger om dem. Ydelser uden feltet eller med "promote": true må du gerne nævne, når det passer til samtalen.
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


PROMPT_AUDIENCES = ("public", "customer_docs")  # `internal` knowledge never reaches any prompt


def knowledge_line(item: dict) -> str:
    """One approved item as one compact line: `type · titel: {content}`. The content keeps its JSON (the fields are
    what the rules refer to), but without the wrapper object and the spaces – on the phone every token in the system
    prompt is paid for in waiting time on every turn, and this is about 40 % shorter than the old JSON-per-line."""
    content = item["content"]
    if isinstance(content, dict) and set(content) == {"text"}:
        content = content["text"]
    body = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False, separators=(",", ":"))
    return f"{item['kind']} · {item['title']}: {body}"


def build_system_prompt(db: OrmSession, workspace: Workspace,
                        audiences: tuple[str, ...] = ("public",)) -> tuple[str, int]:
    """Instructions + approved knowledge for `audiences` (default: what every assistant may say). Dialogbot's sales
    Peter passes ("public", "customer_docs"); "internal" is refused here so it can never end in a prompt."""
    if "internal" in audiences or not set(audiences) <= set(PROMPT_AUDIENCES):
        raise ValueError("internal knowledge never goes into a prompt")
    from app.modules.reports.service import tz_of

    now = datetime.now(ZoneInfo(tz_of(db, workspace.id)))
    # An offer outside its dates is not something the assistant may give (DB-005: «1 Dec expired») – F-E2C-05-K04.
    items = [i for i in knowledge.active_knowledge(db, workspace.id, audiences) if offer_current(i, now.date())]
    if not items:
        raise Conflict("Der er ingen godkendt viden endnu. Godkend mindst ét vidensemne, før assistenten kan svare.",
                       code="no_approved_knowledge")
    body = "\n".join(knowledge_line(i) for i in items)
    from app.modules.reception import service as reception

    prompt = INSTRUCTIONS.format(name=workspace.name, revision=workspace.knowledge_revision, knowledge=body)
    script = reception.prompt_section(db.get(reception.ReceptionScript, workspace.id))
    prompt = f"{prompt}\n\n{script}" if script else prompt
    return f"{prompt}\n\n{now_section(now)}", workspace.knowledge_revision


def offer_current(item: dict, today: date) -> bool:
    """False for an offer whose starts_on is in the future or whose ends_on_inclusive has passed (business's local date).
    Every other kind, and offers without dates, are always current."""
    c = item.get("content")
    if item.get("kind") != "offer" or not isinstance(c, dict):
        return True
    try:
        if c.get("starts_on") and today < date.fromisoformat(c["starts_on"]):
            return False
        if c.get("ends_on_inclusive") and today > date.fromisoformat(c["ends_on_inclusive"]):
            return False
    except (TypeError, ValueError):
        return True
    return True


_WEEKDAYS = ("mandag", "tirsdag", "onsdag", "torsdag", "fredag", "lørdag", "søndag")
_MONTHS = ("januar", "februar", "marts", "april", "maj", "juni", "juli", "august", "september", "oktober", "november",
           "december")
NOW_OPEN, NOW_CLOSE = "<nu>", "</nu>"


def now_section(now: datetime) -> str:
    """Date, weekday and time in the business's time zone (F-V2-05-R07: «har I åbent nu?», «i morgen», fra_dato). Kept
    in its own <nu> block at the end, so the provider can leave it out of the cached prefix (provider.split_now)."""
    return (f"{NOW_OPEN}Lige nu er det {_WEEKDAYS[now.weekday()]} den {now.day}. {_MONTHS[now.month - 1]} {now.year}, "
            f"klokken {now:%H.%M} ({now.tzinfo}); dato {now:%Y-%m-%d}. Brug det til åbningstider, datoer og tilbuds "
            f"gyldighed.{NOW_CLOSE}")


_ONES = ["nul", "en", "to", "tre", "fire", "fem", "seks", "syv", "otte", "ni", "ti", "elleve", "tolv", "tretten", "fjorten",
         "femten", "seksten", "sytten", "atten", "nitten"]
_TENS = {2: "tyve", 3: "tredive", 4: "fyrre", 5: "halvtreds", 6: "tres", 7: "halvfjerds", 8: "firs", 9: "halvfems"}


def spoken_pair(n: int) -> str:
    """0–99 as Danish words, the way a phone number is read out: 7 → "nul syv", 21 → "enogtyve"."""
    if n < 10:
        return f"nul {_ONES[n]}"
    if n < 20:
        return _ONES[n]
    tens, ones = divmod(n, 10)
    return _TENS[tens] if ones == 0 else f"{_ONES[ones]}og{_TENS[tens]}"


def spoken_phone(e164: str) -> str:
    """A Danish number as it is said: "+45 20 30 40 50" → "tyve, tredive, fyrre, halvtreds". Other countries: the
    country code first ("plus fireogfyrre, …"). Odd digit counts end with a single digit."""
    digits = "".join(ch for ch in (e164 or "") if ch.isdigit())
    prefix = ""
    if e164.startswith("+") and not digits.startswith("45"):
        prefix = "plus " + " ".join(_ONES[int(d)] for d in digits[:2]) + ", "
        digits = digits[2:]
    elif digits.startswith("45") and len(digits) == 10:
        digits = digits[2:]
    pairs = [digits[i:i + 2] for i in range(0, len(digits), 2)]
    words = [spoken_pair(int(p)) if len(p) == 2 else _ONES[int(p)] for p in pairs if p]
    return prefix + ", ".join(words)


def known_number_section(e164: str | None, *, how: str) -> str:
    """What the assistant knows about the caller's number, so it never asks a person to dictate a number it already
    has. `how` says where the number comes from, in the caller's own perspective: "det nummer, du ringer fra",
    "det nummer, du skrev på hjemmesiden", "det nummer, jeg ringer til nu"."""
    if not e164:
        return ("Kundens nummer er skjult, så du kender det ikke. Skal en medarbejder ringe tilbage, så bed om nummeret "
                "ét ciffer-par ad gangen, og gentag det i par (fx \"tyve, tredive, fyrre, halvtreds\"), så kunden kan rette.")
    last = spoken_phone(e164).split(", ")[-2:]
    tail = " ".join(last)
    return (f"Du kender allerede kundens telefonnummer: {how}, er {spoken_phone(e164)}. Bed ALDRIG kunden om at "
            f"diktere et nummer, du allerede har. Skal en medarbejder ringe tilbage, så spørg i stedet: \"Skal vi ringe "
            f"på {how} – det, der ender på {tail}?\" Siger kunden ja, er nummeret bekræftet, og du går videre. Vil "
            "kunden hellere ringes op på et andet nummer, så tag det ét ciffer-par ad gangen, gentag det i par (fx "
            "\"tyve, tredive, fyrre, halvtreds\"), og bekræft. Spørg højst to gange; derefter bruger du det nummer, du "
            "kender, og siger, at medarbejderen bekræfter det.")


# Channel-specific additions to the system prompt; the logged prompt version includes the suffix.
CHANNEL_INSTRUCTIONS: dict[str, tuple[str, str]] = {
    "webchat": ("webchat-v1", "Kanal: webchat på virksomhedens hjemmeside. Hvis kunden vil kontaktes, have et tilbud, "
                              "booke eller tale med en medarbejder, så bed dem trykke på knappen \"Bliv kontaktet\" "
                              "under chatten og efterlade navn og e-mail eller telefon. Bed ikke om CPR-nummer eller "
                              "betalingsoplysninger."),
    "phone": ("phone-v8", "Kanal: telefonopkald. Alt, hvad du skriver, bliver læst højt af en dansk stemme, og kunden "
                          "hører det kun én gang. Lyd som en rigtig, venlig og erfaren dansk receptionist – ikke som en "
                          "maskine. Tal naturligt dansk talesprog i korte sætninger, som regel én eller to ad gangen, og "
                          "stil ét spørgsmål ad gangen. Begynd altid med en kort, naturlig reaktion på det, kunden lige "
                          "sagde – to-fem ord, fx \"Ja, selvfølgelig.\", \"Det forstår jeg godt.\", \"Åh, det lyder "
                          "irriterende.\", \"Lige et øjeblik.\" – sæt punktum efter den, og kom så med det vigtigste "
                          "i én sætning; variér reaktionerne, og gentag aldrig den samme vending to gange i træk. Det "
                          "vigtigste først, detaljerne kun hvis kunden spørger. Når du skal slå noget op eller bruge et "
                          "værktøj, så sig først \"Lige et øjeblik, jeg kigger.\" og vent med resten. Hold hvert svar "
                          "under cirka tyve ord, medmindre kunden beder om en forklaring. Brug du-form, "
                          "medmindre kunden selv siger De. Brug kundens navn en enkelt gang, når du kender det, ikke i "
                          "hver sætning. Gentag ikke, hvad virksomheden laver, hvis du allerede har sagt det. Brug danske "
                          "vendinger frem for oversat engelsk – sig fx \"Det kan jeg godt hjælpe med\" i stedet for "
                          "\"Absolut!\" eller \"Godt spørgsmål\". Sig aldrig \"AI\", \"KI\" eller \"AI-assistent\"; "
                          "sig \"digital assistent\" eller \"telefonassistent\". Skriv aldrig punktopstillinger, "
                          "overskrifter, links, e-mailadresser, emojis, parenteser eller forkortelser; skriv tal, beløb, "
                          "datoer og klokkeslæt, som man siger dem (fx \"tusind fire hundrede og femoghalvfems kroner\", "
                          "\"kvart over ti\"). Gentag ikke hilsenen. Hvis du ikke forstod kunden, så sig det naturligt, "
                          "fx \"Undskyld, den fangede jeg ikke helt – hvad sagde du?\". Navne bliver ofte hørt forkert i "
                          "telefonen: spørg efter fornavn og efternavn i ét spørgsmål, og gentag navnet præcis som du "
                          "hørte det i din næste sætning, så kunden kan rette (\"Tak, André.\"). Brug ALDRIG et andet "
                          "eller mere almindeligt navn end det, kunden sagde – André er ikke Andreas, Kjeld er ikke Keld, "
                          "Majbritt er ikke Maibrit. Er navnet usædvanligt, eller retter kunden dig, så bed kunden stave "
                          "det. Når kunden staver, så sæt bogstaverne sammen præcis som stavet (fx \"R e n é\" bliver "
                          "René) og bekræft ved at stave det tilbage. Et navn, kunden har bekræftet, ændrer du aldrig "
                          "senere i samtalen. Nævner kunden et firmanavn eller et navn, du ikke kender fra den godkendte "
                          "viden, så bekræft det første gang ved at STAVE det, bogstav for bogstav med komma imellem, i "
                          "stedet for at udtale det (\"Berle – B, E, R, L, E – Pool, er det rigtigt?\"): bogstaver bliver "
                          "altid sagt rigtigt, og kunden hører med det samme, om du har hørt B eller P. Når navnet er "
                          "bekræftet, siger du det højst én gang mere i samtalen; sig ellers \"jer\", \"virksomheden\" eller "
                          "kundens fornavn. Spørg højst to gange efter det "
                          "samme; derefter går du videre med det, du har, og siger, at medarbejderen bekræfter det, når de "
                          "ringer tilbage. Hvis kunden vil kontaktes, have et tilbud, booke eller tale med en medarbejder, så "
                          "sig, at en medarbejder ringer tilbage, bekræft nummeret som beskrevet under \"Kundens "
                          "telefonnummer\", og spørg om deres navn. Når du siger et telefonnummer højt, så sig det i "
                          "ciffer-par (\"tyve, tredive, fyrre, halvtreds\"), aldrig som ét langt tal. Du kan ikke stille om, booke eller tage "
                          "imod betaling. Når kunden ikke har mere, så afslut kort og venligt med en sætning, der "
                          "slutter med \"Hav en god dag\", og læg derefter på med værktøjet endCall. Bliv ikke "
                          "hængende i røret efter farvel."),
}


def complete_logged(db: OrmSession, workspace: Workspace, *, user_id: uuid.UUID | None, purpose: str,
                    messages: list[dict], channel: str | None = None, tools: list[dict] | None = None,
                    extra_instructions: str | None = None, release_db: bool = False) -> tuple[Completion, AiUsage]:
    """Call the provider with the approved-knowledge prompt and log one `ai_usage` row.

    Commits the usage row (also on failure, then re-raises). `messages` is the conversation so far,
    alternating user/assistant and ending with the user's turn (or the tool results answering the model's calls).
    `tools` are function tools from connected connectors; `extra_instructions` tells the model about them.
    `release_db`: see `log_call`."""
    provider = get_provider()  # 501 before anything else when AI is not configured
    system, revision = build_system_prompt(db, workspace)
    prompt_version = PROMPT_VERSION
    if channel in CHANNEL_INSTRUCTIONS:
        suffix, text = CHANNEL_INSTRUCTIONS[channel]
        system, prompt_version = f"{system}\n\n{text}", f"{PROMPT_VERSION}+{suffix}"
    if extra_instructions:
        system, prompt_version = f"{system}\n\n{extra_instructions}", f"{prompt_version}+actions"
    return log_call(db, workspace, provider, user_id=user_id, purpose=purpose, system=system, messages=messages,
                    prompt_version=prompt_version, revision=revision, max_tokens=get_settings().ai_max_output_tokens,
                    tools=tools, release_db=release_db)


def log_call(db: OrmSession, workspace: Workspace, provider, *, user_id: uuid.UUID | None, purpose: str, system: str,
             messages: list[dict], prompt_version: str, revision: int, max_tokens: int,
             tools: list[dict] | None = None, model: str | None = None, effort: str | None = None,
             release_db: bool = False) -> tuple[Completion, AiUsage]:
    """Run one provider call and write its `ai_usage` row (committed on failure, flushed on success).
    `model` / `effort` override the provider's defaults for this call.

    `release_db=True` ends the session's transaction before the provider is called, so no pooled connection is held
    while the model answers (seconds); the row is then written on a fresh connection. Only for callers whose session
    has nothing uncommitted they might still want to roll back (the transaction is committed, not discarded): a
    request waiting on the model must not take one of the API's few connections from the calls and webhooks that
    share the pool (loadtest-2026-11-13 §1.4.3)."""
    row = AiUsage(workspace_id=workspace.id, user_id=user_id, purpose=purpose, provider=provider.name,
                  requested_model=model or provider.model, prompt_version=prompt_version[:32], knowledge_revision=revision)
    if release_db:
        db.commit()  # returns the connection to the pool; expire_on_commit=False keeps loaded objects usable
    try:
        c = provider.complete(system=system, messages=messages, max_tokens=max_tokens, tools=tools, model=model, effort=effort)
    except ApiError as e:
        row.outcome, row.error_code = "error", e.code
        row.provider_request_id = (e.extra or {}).get("provider_request_id")
        db.add(row)
        db.commit()
        raise
    fill_usage(row, c)
    db.add(row)
    db.flush()
    return c, row


def fill_usage(row: AiUsage, c: Completion) -> AiUsage:
    """Copy a completion's outcome and usage onto an ai_usage row (also for calls made outside log_call, such as the
    link finder's parallel searches, which record their rows afterwards)."""
    row.outcome = "refused" if c.stop_reason == "refusal" else "truncated" if c.stop_reason == "max_tokens" else "ok"
    row.served_model, row.stop_reason = c.served_model, c.stop_reason[:32]
    row.input_tokens, row.output_tokens = c.usage.input_tokens, c.usage.output_tokens
    row.cache_creation_input_tokens = c.usage.cache_creation_input_tokens
    row.cache_read_input_tokens = c.usage.cache_read_input_tokens
    row.est_cost_usd_micros = estimate_cost_usd_micros(c)
    row.latency_ms, row.provider_request_id = c.latency_ms, c.request_id
    return row


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

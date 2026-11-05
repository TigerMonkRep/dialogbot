"""The private assistant's chat: one model turn with tools, at most a few tool rounds.

Core tools (always): create_list, add_items, create_reminder, move_reminder, list_waiting, ask_clarifying,
suggest_addon. Add-on tools (propose_call, share_list, …) come from the catalog (addons.py) and are only offered when
the add-on is on; for a switched-off add-on the model can only offer it (suggest_addon → a kind "addon" message).

Calls: the assistant NEVER invents a business or a number. A call needs a number the user wrote themselves, or a pick
among ≤ 3 businesses found with Google Places (privat/places.py). FIXTURES (fictional Aarhus bike shops) are only
used with FakeProvider in dev/test.
Nothing is ever dialled from the chat: propose_call only creates a proposal the user approves in /privat/calls.
"""
from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session as OrmSession

from app.core.errors import ApiError, NotFound
from app.models import AiUsage, PrivateMessage, PrivateProfile, PrivateTask, PrivateTaskItem, PrivateTaskMember
from app.modules.privat import addons, links, rules, service, sharing

PROMPT_VERSION = "privat-v1"
MAX_TOOL_ROUNDS = 4
HISTORY = 10

FIXTURES = (
    {"id": "cykelmageren", "name": "Cykelmageren", "category": "cykelværksted", "address": "Nørregade 12, 8000 Aarhus C",
     "phone": "+4586123456", "sub": "Nørregade 12, 8000 Aarhus C · 600 m",
     "price": "450 kr. for et almindeligt eftersyn"},
    {"id": "oestbyens-cykler", "name": "Østbyens Cykler", "category": "cykelværksted",
     "address": "Østergade 3, 8000 Aarhus C", "phone": "+4586987654", "sub": "Østergade 3, 8000 Aarhus C · 1,2 km",
     "price": "395 kr. for et almindeligt eftersyn"},
)

SYSTEM = """PRIVAT_ASSISTANT
Du er Dialogbot, en personlig dansk assistent for {name}. Du hjælper med lister, påmindelser{call_part}.
Nu er det {now} (Europe/Copenhagen, {weekday}).

Regler:
- Svar kort på dansk. Brug værktøjerne til at gøre tingene; skriv ikke lange forklaringer.
- Tidspunkter til værktøjer skrives som lokal tid i ISO-format, fx 2026-11-05T16:00.
- Er du i tvivl om, hvad brugeren vil, så brug ask_clarifying med 2-3 korte valg.
- Opfind aldrig virksomheder, telefonnumre, priser eller aftaler. Du ringer aldrig selv: et opkald er kun et forslag,
  som brugeren skal godkende.
- Beder brugeren om noget, som kræver en tilføjelse, der ikke er slået til, så brug suggest_addon.
- En rettelse af en eksisterende opgave er gratis; brug add_items/move_reminder i stedet for at lave en ny opgave.
{search}{lists}{about}{addons}"""

SEARCH_RULE = """- Købslinks: vil brugeren have et link til, hvor noget kan købes, så kald find_buy_link med punktets tekst – den
  søger, tjekker at siden er en rigtig købsside, og sætter linket på punktet selv. Spørg ikke først. På en ønskeliste
  sætter du find_links: true i create_list/add_items, når punkterne er konkrete produkter (en bog, et spil, mærke +
  model), så linket er der fra starten. Skriv aldrig selv et link.
"""
NO_SEARCH_RULE = """- Du kan ikke slå links eller priser op; beder brugeren om det, så sig det kort og foreslå, at de sender linket.
"""


@dataclass
class Turn:
    db: OrmSession
    ctx: object
    text: str
    about: PrivateTask | None
    out: list[PrivateMessage] = field(default_factory=list)

    def say(self, kind: str, text: str, about_task_id_override=None, **kw) -> PrivateMessage:
        about = about_task_id_override or (self.about.id if self.about else None)
        m = service.add_message(self.db, self.ctx.ws_id, kind=kind, text=text, about_task_id=about, **kw)
        self.out.append(m)
        return m


def _obj(props: dict, required: list[str] | None = None) -> dict:
    return {"type": "object", "properties": props, "required": required or []}


ITEM = {"anyOf": [{"type": "string"},
                  _obj({"text": {"type": "string"}, "link": {"type": "string", "description": "https://… hvor det kan købes"},
                        "note": {"type": "string"}}, ["text"])]}
CORE_TOOLS = [
    {"name": "create_list", "description": "Lav en ny liste (kræver prøveperiode eller plan – ellers gemmes den som udkast). Punkter er tekst "
                                           "eller {text, link, note}. find_links: true finder købslinks til punkterne "
                                           "(ønskelister med konkrete produkter).",
     "input_schema": _obj({"title": {"type": "string"}, "type": {"type": "string", "enum": list(service.LIST_TYPES)},
                           "items": {"type": "array", "items": ITEM}, "find_links": {"type": "boolean"}}, ["title"])},
    {"name": "add_items", "description": "Tilføj punkter til en eksisterende liste (gratis). Udelad task_id for den "
                                         "liste, samtalen handler om, eller den nyeste liste. Punkter er tekst eller "
                                         "{text, link, note}. find_links: true finder købslinks til de nye punkter.",
     "input_schema": _obj({"task_id": {"type": "string"}, "items": {"type": "array", "items": ITEM},
                           "find_links": {"type": "boolean"}}, ["items"])},
    {"name": "set_item_link", "description": "Sæt et link, brugeren selv har sendt, på et punkt, der allerede står på "
                                             "listen. item er punktets tekst, som den står på listen.",
     "input_schema": _obj({"task_id": {"type": "string"}, "item": {"type": "string"}, "link": {"type": "string"},
                           "note": {"type": "string"}}, ["item", "link"])},
    {"name": "find_buy_link", "description": "Find og sæt et verificeret købslink (dansk webshop, rigtig produktside) "
                                             "på et eller flere punkter, der står på listen. items er punkternes tekst.",
     "input_schema": _obj({"task_id": {"type": "string"}, "items": {"type": "array", "items": {"type": "string"}}},
                          ["items"])},
    {"name": "create_reminder", "description": "Lav en påmindelse på et bestemt tidspunkt.",
     "input_schema": _obj({"title": {"type": "string"}, "remind_at": {"type": "string"}}, ["title", "remind_at"])},
    {"name": "move_reminder", "description": "Flyt en eksisterende påmindelse (gratis). remind_at er et fuldt "
                                             "tidspunkt, eller kun 'HH:MM' for samme dag som før.",
     "input_schema": _obj({"task_id": {"type": "string"}, "remind_at": {"type": "string"}}, ["remind_at"])},
    {"name": "list_waiting", "description": "Vis hvad der venter på brugerens svar.", "input_schema": _obj({})},
    {"name": "ask_clarifying", "description": "Stil et opklarende spørgsmål med 2-3 valg.",
     "input_schema": _obj({"question": {"type": "string"},
                           "options": {"type": "array", "items": _obj({"label": {"type": "string"},
                                                                       "sub": {"type": "string"}}, ["label"])}},
                          ["question", "options"])},
]


def _suggest_tool(offer: list[addons.Addon]) -> dict | None:
    if not offer:
        return None
    desc = "; ".join(f"{a.key}: {a.name} ({', '.join(a.keywords)})" for a in offer)
    return {"name": "suggest_addon", "description": "Tilbyd at slå en tilføjelse til, når brugeren beder om noget, "
            f"den kan. Mulige: {desc}", "input_schema": _obj({"key": {"type": "string",
                                                                    "enum": [a.key for a in offer]}}, ["key"])}


def tools_for(db: OrmSession, ws_id: uuid.UUID) -> tuple[list[dict], dict]:
    """(tool definitions for the model, name → add-on tool) – only enabled add-ons contribute tools. The buy-link
    finder (privat/links.py) is offered when web search is on; the chat model itself never searches."""
    defs = [t for t in CORE_TOOLS if t["name"] != "find_buy_link" or links.enabled()]
    extra = {}
    for t in addons.tools_for(db, ws_id):
        defs.append({"name": t.name, "description": t.description, "input_schema": t.input_schema})
        extra[t.name] = t
    if (s := _suggest_tool(addons.offerable(db, ws_id))) is not None:
        defs.append(s)
    return defs, extra


def _system(db: OrmSession, ctx, about: PrivateTask | None) -> str:
    now = rules.local()
    lists = [t for t in service.list_tasks(db, ctx) if t.kind in ("list", "reminder")
             and t.status not in ("done", "declined")][:15]
    lists_txt = ("\nÅbne lister og påmindelser (id · type · titel):\n" + "\n".join(
        f"- {t.id} · {t.kind} · {t.title}" for t in lists) + "\n") if lists else ""
    about_txt = ""
    if about is not None:
        about_txt = f"\nSamtalen handler om opgaven {about.id} ({about.kind}): {about.title}\n"
        if about.kind == "list":
            items = service.items_out(db, about, ctx.user_id, sharing.member(db, about.id, ctx.user_id).role)
            about_txt += "Punkter: " + ", ".join(i["text"] for i in items) + "\n"
    on = addons.enabled_keys(db, ctx.ws_id)
    addons_txt = "\nTilføjelser slået til: " + (", ".join(sorted(on)) or "ingen") + "\n"
    return SYSTEM.format(name=ctx.user.display_name, call_part=" og opkald til virksomheder" if "ring-for-mig" in on
                         else "", now=now.strftime("%Y-%m-%dT%H:%M"), weekday=rules.WEEKDAYS[now.weekday()],
                         search=SEARCH_RULE if links.enabled() else NO_SEARCH_RULE,
                         lists=lists_txt, about=about_txt, addons=addons_txt)


def _history(db: OrmSession, ctx) -> list[dict]:
    rows = list(db.scalars(select(PrivateMessage).where(PrivateMessage.workspace_id == ctx.ws_id)
                           .order_by(PrivateMessage.created_at.desc(), PrivateMessage.id).limit(HISTORY)))
    turns: list[dict] = []
    for m in reversed(rows):
        role = "user" if m.role == "user" else "assistant"
        text = m.text or m.kind
        if turns and turns[-1]["role"] == role:
            turns[-1]["content"] += "\n" + text
        else:
            turns.append({"role": role, "content": text})
    while turns and turns[0]["role"] != "user":
        turns.pop(0)
    return turns


def run(db: OrmSession, ctx, text: str, about_task_id: uuid.UUID | None) -> list[PrivateMessage]:
    """Store the user's message, let the model act with tools, return all new messages (user's first)."""
    from app.modules.ai.provider import get_provider, tool_result_message
    from app.modules.ai.service import log_call

    about = None
    if about_task_id is not None:
        about, _m = sharing.access(db, about_task_id, ctx.user_id)
    text = (text or "").strip()[:2000]
    user_msg = service.add_message(db, ctx.ws_id, role="user", kind="text", text=text,
                                   about_task_id=about.id if about else None)
    turn = Turn(db=db, ctx=ctx, text=text, about=about)
    if about is not None and about.kind == "call" and (attached := attach_number(db, ctx, about, text)) is not None:
        db.commit()  # the user answered «skriv nummeret»: no model needed
        return [user_msg, *attached]
    db.commit()
    from app.config import get_settings

    settings = get_settings()
    provider = get_provider()
    tools, extra = tools_for(db, ctx.ws_id)
    system = _system(db, ctx, about)
    messages = _history(db, ctx)
    ask = dict(user_id=ctx.user_id, purpose="privat_chat", system=system, prompt_version=PROMPT_VERSION, revision=0,
               max_tokens=1024, tools=tools, model=settings.privat_ai_model_id, effort=settings.privat_ai_effort)
    c, _row = log_call(db, ctx.workspace, provider, messages=messages, **ask)
    rounds = 0
    errors: list[str] = []
    while c.tool_calls and rounds < MAX_TOOL_ROUNDS:
        rounds += 1
        results = []
        for call in c.tool_calls:
            kept = len(turn.out)
            try:
                with db.begin_nested():  # a failing tool undoes only its own changes
                    results.append((call.id, execute(turn, call.name, call.input or {}, extra)))
            except ApiError as e:
                del turn.out[kept:]
                errors.append(e.message)
                results.append((call.id, f"Fejl: {e.message}"))
        db.commit()
        if turn.out and not errors:
            break  # the tools already said what happened (card, question, list) – no second model turn, no wait
        messages = messages + [{"role": "assistant", "content": c.assistant_content}, tool_result_message(results)]
        c, _row = log_call(db, ctx.workspace, provider, messages=messages, **ask)
    if not turn.out:
        reply = c.text.strip() if c.stop_reason != "refusal" and c.text else ""
        turn.say("text", reply or (errors[-1] if errors else
                                   "Det kan jeg desværre ikke hjælpe med. Prøv at skrive det på en anden måde."))
    db.commit()
    return [user_msg, *turn.out]


def execute(turn: Turn, name: str, args: dict, extra: dict) -> str:
    if name in extra:
        return addons.handler(extra[name])(turn, args)
    fn = CORE_HANDLERS.get(name)
    if fn is None:
        return "Ukendt værktøj"
    return fn(turn, args)


# --------------------------------------------------------------------------- core handlers

def _parse_when(raw: str | None) -> datetime | None:
    try:
        dt = datetime.fromisoformat(str(raw or "").strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt.replace(tzinfo=rules.TZ) if dt.tzinfo is None else dt


def _items(raw) -> list[str]:
    return [t for t, _l, _n in _rich_items(raw)]


def _rich_items(raw) -> list[tuple[str, str | None, str | None]]:
    """Items as (text, link, note): plain strings, or {text, link, note} from a web search."""
    if isinstance(raw, str):
        raw = re.split(r",|\sog\s", raw)
    out: list[tuple[str, str | None, str | None]] = []
    for x in raw or []:
        if isinstance(x, dict):
            text = str(x.get("text") or "").strip()[:300]
            link = str(x.get("link") or "").strip()[:1000] or None
            note = str(x.get("note") or "").strip()[:500] or None
            if link and not link.startswith(("https://", "http://")):
                link = None
        else:
            text, link, note = str(x).strip()[:300], None, None
        if text:
            out.append((text, link, note))
    return out[:50]


def _cap(s: str) -> str:
    return s[:1].upper() + s[1:] if s else s


def _join(items: list[str]) -> str:
    low = [i.lower() for i in items]
    return low[0] if len(low) == 1 else ", ".join(low[:-1]) + " og " + low[-1]


def _created(turn: Turn, task: PrivateTask, intro: str) -> None:
    if task.status == "draft":
        turn.say("draft", "Det kræver en plan. Prøv Dialogbot Privat gratis i 14 dage – kortet trækkes først, når "
                          "prøveperioden er slut. Opgaven er gemt som udkast, til du har valgt.", task_id=task.id)
        return
    turn.say("text", intro, task_id=task.id)
    turn.say("task", task.title, task_id=task.id)


def h_create_list(turn: Turn, a: dict) -> str:
    rich = _rich_items(a.get("items"))
    items = [t for t, _l, _n in rich]
    lt = a.get("type") if a.get("type") in service.LIST_TYPES else None
    title = _cap(str(a.get("title") or "").strip()) or {"shopping": "Indkøbsliste", "wishlist": "Ønskeliste"}.get(lt or "", "Liste")
    task = service.create_digital(turn.db, turn.ctx, kind="list", title=title, items=items, list_type=lt)
    _apply_links(turn, task, rich)
    intro = f"Her er din {title.lower()}" + (f" med {_join(items)}." if items else ".")
    if a.get("find_links") and items and task.status != "draft" and links.enabled():
        found = _find_links(turn, task, [t for t, link, _n in rich if not link])
        intro += " " + _links_text(found)
    _created(turn, task, intro)
    return f"Liste oprettet (id {task.id}, status {task.status})."


def _resolve(turn: Turn, task_id, kind: str, min_role: str = "viewer") -> tuple[PrivateTask, PrivateTaskMember]:
    if task_id:
        try:
            t, m = sharing.access(turn.db, uuid.UUID(str(task_id)), turn.ctx.user_id, min_role=min_role)
        except ValueError as e:
            raise NotFound("Opgaven findes ikke") from e
        if t.kind != kind:
            raise NotFound("Opgaven findes ikke")
        return t, m
    if turn.about is not None and turn.about.kind == kind:
        return sharing.access(turn.db, turn.about.id, turn.ctx.user_id, min_role=min_role)
    for t in service.list_tasks(turn.db, turn.ctx):
        if t.kind == kind and t.status not in ("done", "declined"):
            m = sharing.member(turn.db, t.id, turn.ctx.user_id)
            if sharing.ROLE_RANK[m.role] >= sharing.ROLE_RANK[min_role]:
                return t, m
    raise NotFound("Jeg fandt ingen åben " + ("liste" if kind == "list" else "påmindelse"))


def _apply_links(turn: Turn, task: PrivateTask, rich: list[tuple[str, str | None, str | None]]) -> int:
    """Links/notes from {text, link, note} items land on the matching rows (text match, newest first)."""
    n = 0
    for text, link, note in rich:
        if not link and not note:
            continue
        row = turn.db.scalar(select(PrivateTaskItem).where(PrivateTaskItem.task_id == task.id,
                                                            func.lower(PrivateTaskItem.text) == text.lower())
                             .order_by(PrivateTaskItem.created_at.desc()).limit(1))
        if row is None:
            continue
        if link:
            row.link = link
        if note and not row.note:
            row.note = note
        n += 1
    return n


def h_add_items(turn: Turn, a: dict) -> str:
    task, m = _resolve(turn, a.get("task_id"), "list", "editor")
    rich = _rich_items(a.get("items"))
    added = service.add_items(turn.db, task, m, [t for t, _l, _n in rich])
    _apply_links(turn, task, rich)
    names = [i.text for i in added]
    with_links = sum(1 for _t, link, _n in rich if link)
    text = f"Tilføjet {_join(names)}" + (" – med link til, hvor det kan købes." if with_links else
                                        ". Det er stadig den samme liste, og en rettelse koster ingen opgave.")
    if a.get("find_links") and links.enabled():
        text += " " + _links_text(_find_links(turn, task, [t for t, link, _n in rich if not link]))
    turn.say("text", text, task_id=task.id)
    turn.say("task", task.title, task_id=task.id)
    return f"Tilføjet til {task.id}."


def _find_links(turn: Turn, task: PrivateTask, items: list[str]) -> list[links.BuyLink]:
    """Search + verify + set, for the list's rows whose text matches `items`. Each search is logged in ai_usage."""
    from app.modules.ai.provider import get_provider
    from app.modules.ai.service import fill_usage

    profile = turn.db.get(PrivateProfile, turn.ctx.ws_id)
    results = links.find_buy_links(items, profile.location_city if profile else None)
    provider = get_provider()
    out = []
    for r, completion in results:
        if completion is not None:
            row = AiUsage(workspace_id=turn.ctx.ws_id, user_id=turn.ctx.user_id, purpose="privat_link",
                          provider=provider.name, requested_model=completion.requested_model,
                          prompt_version="privat-link-v1", knowledge_revision=0)
            turn.db.add(fill_usage(row, completion))
        if r.found:
            row_item = _item_named(turn, task, r.item)
            if row_item is not None:
                row_item.link = r.url
                note = " · ".join(x for x in (r.shop, r.price) if x)
                if note and not row_item.note:
                    row_item.note = note[:500]
        out.append(r)
    turn.db.flush()
    return out


def _item_named(turn: Turn, task: PrivateTask, wanted: str) -> PrivateTaskItem | None:
    w = wanted.strip().lower()
    rows = list(turn.db.scalars(select(PrivateTaskItem).where(PrivateTaskItem.task_id == task.id)
                                .order_by(PrivateTaskItem.position, PrivateTaskItem.created_at)))
    return next((r for r in rows if r.text.lower() == w), None) or \
        next((r for r in rows if w and (w in r.text.lower() or r.text.lower() in w)), None)


def _links_text(found: list[links.BuyLink]) -> str:
    ok = [r for r in found if r.found]
    missing = [r for r in found if not r.found]
    parts = []
    if ok:
        parts.append("Købslink sat på " + _join_names([f"{r.item} ({r.shop}{' · ' + r.price if r.price else ''})" for r in ok])
                      + " – tryk på punktet for at åbne det.")
    if missing:
        parts.append("Jeg fandt ikke en butik, der sælger " + _join_names([r.item for r in missing])
                     + " lige nu – skriv forfatter, mærke eller model, så prøver jeg igen.")
    return " ".join(parts)


def _join_names(xs: list[str]) -> str:
    return xs[0] if len(xs) == 1 else ", ".join(xs[:-1]) + " og " + xs[-1]


def h_find_buy_link(turn: Turn, a: dict) -> str:
    task, m = _resolve(turn, a.get("task_id"), "list", "editor")
    service.can_add(task, m)
    wanted = [str(x).strip() for x in (a.get("items") or []) if str(x).strip()][:links.MAX_ITEMS]
    if not wanted:
        return "Angiv punktets tekst i items."
    # the row's own text is what we search for (the model may have shortened it)
    names = [(_item_named(turn, task, w).text if _item_named(turn, task, w) is not None else w) for w in wanted]
    found = _find_links(turn, task, names)
    turn.say("text", _links_text(found), task_id=task.id)
    turn.say("task", task.title, task_id=task.id)
    return "; ".join(f"{r.item}: {r.url or 'intet verificeret link'}" for r in found)


def h_set_item_link(turn: Turn, a: dict) -> str:
    task, m = _resolve(turn, a.get("task_id"), "list", "editor")
    service.can_add(task, m)
    link = str(a.get("link") or "").strip()[:1000]
    if not link.startswith(("https://", "http://")):
        return "Linket skal starte med https://. Søg efter et rigtigt link først."
    wanted = str(a.get("item") or "").strip().lower()
    rows = list(turn.db.scalars(select(PrivateTaskItem).where(PrivateTaskItem.task_id == task.id)
                                .order_by(PrivateTaskItem.position, PrivateTaskItem.created_at)))
    row = next((r for r in rows if r.text.lower() == wanted), None) or \
        next((r for r in rows if wanted and (wanted in r.text.lower() or r.text.lower() in wanted)), None)
    if row is None:
        return "Punktet findes ikke på listen: " + ", ".join(r.text for r in rows[:20])
    row.link = link
    if (note := str(a.get("note") or "").strip()[:500]):
        row.note = note
    turn.db.flush()
    turn.say("text", f"Linket er sat på «{row.text}» – tryk på punktet for at åbne det.", task_id=task.id)
    turn.say("task", task.title, task_id=task.id)
    return f"Link sat på {row.id}."


def h_create_reminder(turn: Turn, a: dict) -> str:
    when = _parse_when(a.get("remind_at"))
    if when is None or when <= rules.now():
        return "Tidspunktet mangler eller er i fortiden. Spørg brugeren hvornår."
    title = _cap(str(a.get("title") or "").strip()) or "Påmindelse"
    task = service.create_digital(turn.db, turn.ctx, kind="reminder", title=title, remind_at=when)
    _created(turn, task, f"Jeg minder dig om det {rules.lower_first(rules.when_text(when))}.")
    return f"Påmindelse oprettet (id {task.id}, status {task.status})."


def h_move_reminder(turn: Turn, a: dict) -> str:
    task, m = _resolve(turn, a.get("task_id"), "reminder", "owner")
    raw = str(a.get("remind_at") or "").strip()
    if re.fullmatch(r"\d{1,2}[:.]\d{2}", raw) and task.remind_at:  # only a new time: same day as before
        h, mi = (int(x) for x in re.split(r"[:.]", raw))
        when = rules.local(task.remind_at).replace(hour=h, minute=mi, second=0, microsecond=0)
    else:
        when = _parse_when(raw)
    if when is None or when <= rules.now():
        return "Tidspunktet mangler eller er i fortiden."
    before, after = service.move_reminder(turn.db, task, when)
    turn.say("move", f"Flyttet fra {rules.lower_first(before)} til {rules.lower_first(after)}.", task_id=task.id,
             before=before, after=after)
    return f"Flyttet til {after}."


def h_list_waiting(turn: Turn, a: dict) -> str:
    tasks = service.list_tasks(turn.db, turn.ctx)
    waiting = [t for t in tasks if t.status in ("awaiting_user", "draft")]
    biz = [t for t in tasks if t.status == "awaiting_business"]
    text = ("Intet venter på dit svar lige nu." if not waiting else "Én ting venter på dit svar:" if len(waiting) == 1
            else f"{len(waiting)} ting venter på dit svar:")
    if biz:
        text += (" Én opgave venter på svar fra en virksomhed. Du får besked, når de svarer." if len(biz) == 1
                 else f" {len(biz)} opgaver venter på svar fra en virksomhed.")
    turn.say("waiting", text, links=[str(t.id) for t in waiting])
    return text


def h_ask_clarifying(turn: Turn, a: dict) -> str:
    opts = []
    for i, o in enumerate((a.get("options") or [])[:4]):
        if isinstance(o, dict) and str(o.get("label") or "").strip():
            label = str(o["label"]).strip()[:80]
            opts.append({"id": f"o{i + 1}", "label": label, "sub": str(o.get("sub") or "")[:120], "action": "reply",
                         "text": str(o.get("text") or label)[:300]})
    turn.say("clarify", str(a.get("question") or "Hvad mener du?")[:300], options=opts or None)
    return "Spørgsmålet er stillet; vent på brugerens svar."


def h_suggest_addon(turn: Turn, a: dict) -> str:
    a_ = addons.CATALOG.get(str(a.get("key") or ""))
    if a_ is None:
        return "Ukendt tilføjelse."
    if addons.is_enabled(turn.db, turn.ctx.ws_id, a_.key):
        return "Tilføjelsen er allerede slået til."
    turn.say("addon", f"Det kræver tilføjelsen «{a_.name}». Slå den til, så kan jeg hjælpe dig med det. "
                      f"{a_.tagline}.", addon_key=a_.key)
    return "Tilføjelsen er tilbudt brugeren."


CORE_HANDLERS = {"create_list": h_create_list, "add_items": h_add_items, "set_item_link": h_set_item_link, "find_buy_link": h_find_buy_link,
                 "create_reminder": h_create_reminder,
                 "move_reminder": h_move_reminder, "list_waiting": h_list_waiting,
                 "ask_clarifying": h_ask_clarifying, "suggest_addon": h_suggest_addon}


# --------------------------------------------------------------------------- add-on tools

def _digits(s: str) -> str:
    return re.sub(r"\D", "", s or "")


def _user_wrote(turn: Turn, phone_e164: str) -> bool:
    """A number is only used if the user typed it (last messages): the model may never invent one."""
    national = _digits(phone_e164)[-8:]
    texts = [turn.text] + [m.text for m in turn.db.scalars(
        select(PrivateMessage).where(PrivateMessage.workspace_id == turn.ctx.ws_id, PrivateMessage.role == "user")
        .order_by(PrivateMessage.created_at.desc()).limit(HISTORY))]
    return any(national in _digits(t) for t in texts)


LOCATION_OPTIONS = [
    {"id": "location:geo", "label": "Brug min position", "sub": "Kun når du trykker", "action": "text",
     "text": "Tryk «Brug min position», eller skriv byen eller postnummeret."},
    {"id": "location:city", "label": "Skriv by eller postnummer", "sub": "Fx 8000 eller Aarhus C", "action": "text",
     "text": "Skriv byen eller postnummeret, så leder jeg der."},
]


def _propose(turn: Turn, *, name: str, phone: str | None, source: str, address: str = "", place_id: str | None = None,
             next_open_at: str | None = None, data: dict | None = None, require_addon: bool = True) -> str:
    """Always a proposal (never a call). A missing number is asked for in the chat; a mobile-looking number must be
    confirmed as a business when approving (confirm_business); demo numbers can never be dialled."""
    from app.modules.privat import calls, places

    data = data or {}
    e164, kind = places.classify_phone(phone)
    nxt = datetime.fromisoformat(next_open_at) if next_open_at else None
    task = calls.propose(turn.db, turn.ctx, business_name=name, phone=e164, address=address, price_text=None,
                         purpose=data.get("purpose") or "", window=data.get("window") or "", may_ask=data.get("may_ask"),
                         may_agree=data.get("may_agree"), may_not=data.get("may_not"), place_id=place_id,
                         next_open_at=nxt, phone_source=source, require_addon=require_addon)
    if e164 is None:
        text = (f"Jeg har ikke et nummer til {name}, som jeg kan ringe til. Skriv nummeret her, så bruger jeg det. "
                "Jeg ringer først, når du godkender.")
    elif nxt is not None and nxt > rules.now():
        text = (f"{name} har lukket nu. Næste åbningstid er {rules.lower_first(rules.when_text(nxt))} – godkend, så "
                "ringer jeg dér. Jeg ringer først, når du godkender.")
    else:
        text = f"Her er mit forslag til opkaldet til {name}. Jeg ringer først, når du godkender."
    if e164 is not None and kind == "mobile":
        text += " Nummeret ligner et mobilnummer – bekræft, at det er en virksomhed, når du godkender."
    turn.say("call_proposal", text, task_id=task.id)
    return f"Forslag oprettet (id {task.id}). Der er IKKE ringet; brugeren skal godkende."


def tool_propose_call(turn: Turn, a: dict) -> str:
    """Never invents a business or a number: a number the user typed, or a pick among ≤ 3 search results."""
    from app.core.errors import Conflict
    from app.modules.campaigns.service import normalize_phone
    from app.modules.privat import places

    name = str(a.get("business_name") or "").strip()[:200]
    data = {"window": str(a.get("window") or "").strip()[:200], "purpose": str(a.get("purpose") or "").strip()[:300],
            **{k: str(a[k])[:2000] for k in ("may_ask", "may_agree", "may_not") if a.get(k)}}
    if a.get("phone"):
        phone = normalize_phone(str(a["phone"]))
        if phone is None or not _user_wrote(turn, phone):
            turn.say("text", f"Hvilket nummer skal jeg ringe til{' hos ' + name if name else ''}? Skriv det, så "
                             "laver jeg et forslag, du kan godkende.")
            return "Nummeret er ikke skrevet af brugeren. Spørg efter det; opfind det aldrig."
        if not name:
            turn.say("text", "Hvad hedder virksomheden? Så laver jeg et forslag, du kan godkende.")
            return "Mangler virksomhedens navn."
        return _propose(turn, name=name, phone=phone, source="user", data=data)
    query = name or str(a.get("category") or "").strip()
    if not query:
        turn.say("text", "Hvem skal jeg ringe til? Skriv virksomhedens navn – og gerne byen.")
        return "Mangler virksomhed. Opfind den ikke."
    try:
        results = places.search(turn.db, turn.ctx, query, city=str(a.get("city") or "").strip() or None)
    except Conflict as e:
        if e.code == "needs_location":
            turn.say("clarify", "Hvor skal jeg lede?", options=LOCATION_OPTIONS)
            return "Brugeren skal give en by eller sin position."
        raise
    if not results:
        turn.say("text", f"Jeg fandt ingen «{query}» i nærheden. Skriv navn og nummer, så laver jeg et forslag.")
        return "Ingen resultater."
    opts = [{"id": f"place:{r['place_id']}"[:320], "label": r["name"], "sub": places.option_sub(r),
             "action": "call_place", "place_id": r["place_id"], "address": r["address"], "phone": r["phone_e164"],
             "source": r["source"], "next_open_at": r["next_open_at"], **data} for r in results]
    opts.append({"id": "other", "label": "En anden", "sub": "Skriv navnet og nummeret", "action": "text",
                 "text": "Skriv navnet og nummeret på virksomheden, så laver jeg et forslag."})
    google = " (data fra Google)" if results[0]["source"] == "google" else ""
    turn.say("clarify", f"Hvem mener du? Jeg fandt {len(results)} tæt på dig{google}:", options=opts)
    return "Brugeren vælger virksomhed."


def attach_number(db: OrmSession, ctx, task: PrivateTask, text: str) -> list[PrivateMessage] | None:
    """The user answers «skriv nummeret» with a message about the call task: the number goes on the proposal.
    None when the message is not such an answer (then the model handles it)."""
    from app.modules.privat import calls, places

    m = re.search(r"(\+?45)?\s*(\d{2}\s?\d{2}\s?\d{2}\s?\d{2})", text or "")
    c = calls.latest_proposed(db, task)
    if m is None or c is None or c.business_phone_e164:
        return None
    e164, kind = places.classify_phone(m.group(2))
    turn = Turn(db=db, ctx=ctx, text=text, about=task)
    if e164 is None:
        turn.say("text", "Det nummer kan jeg ikke ringe til. Skriv et dansk nummer med 8 cifre.")
        return turn.out
    c.business_phone_e164, c.phone_source = e164, "user"
    service.event(db, task, f"Nummer tilføjet: {rules.phone_display(e164)}")
    service.touch(task)
    turn.say("text", f"Tak. Jeg bruger {rules.phone_display(e164)}." + (
        " Det ligner et mobilnummer – bekræft, at det er en virksomhed, når du godkender." if kind == "mobile" else ""))
    turn.say("call_proposal", f"Her er mit forslag til opkaldet til {c.business_name}. Jeg ringer først, når du "
                              "godkender.", task_id=task.id)
    return turn.out


def tool_share_list(turn: Turn, a: dict) -> str:
    """A share_proposal card: the web makes the link only when the user taps it (nothing is ever sent by Dialogbot)."""
    task, m = _resolve(turn, a.get("task_id"), "list", "owner")
    if m.role != "owner":
        return "Kun ejeren kan dele listen."
    mode = a.get("mode") if a.get("mode") in ("group", "wishlist") else (
        "wishlist" if task.list_type == "wishlist" else "group")
    key = addons.SHARE_MODE_ADDON[mode]
    if not addons.is_enabled(turn.db, turn.ctx.ws_id, key):
        return h_suggest_addon(turn, {"key": key})
    who = str(a.get("with_name") or "").strip()[:60]
    turn.say("share_proposal", f"Skal jeg lave et invitationslink til «{task.title}»"
                               f"{', som du kan sende til ' + who if who else ''}? Der sendes intet, før du selv deler "
                               "linket.", task_id=task.id, about_task_id_override=task.id)
    return "Forslaget er vist; brugeren laver selv linket."


# --------------------------------------------------------------------------- answering a clarify message

def answer_option(db: OrmSession, ctx, message_id: uuid.UUID, option_id: str) -> list[PrivateMessage]:
    m = db.scalar(select(PrivateMessage).where(PrivateMessage.id == message_id,
                                               PrivateMessage.workspace_id == ctx.ws_id).with_for_update())
    if m is None or not m.options:
        raise NotFound("Beskeden findes ikke")
    opt = next((o for o in m.options if o.get("id") == option_id), None)
    if opt is None:
        raise NotFound("Valget findes ikke")
    if m.answered_option_id:
        return []  # answered before: a repeated tap changes nothing
    m.answered_option_id = option_id
    about = db.get(PrivateTask, m.about_task_id) if m.about_task_id else None
    act = opt.get("action")
    if act == "reply":
        db.flush()
        return run(db, ctx, opt.get("text") or opt["label"], about.id if about else None)
    user_msg = service.add_message(db, ctx.ws_id, role="user", kind="text", text=opt["label"])
    turn = Turn(db=db, ctx=ctx, text=opt["label"], about=about)
    if act == "call_place":
        addons.require(db, ctx.ws_id, "ring-for-mig")
        _propose(turn, name=opt["label"], phone=opt.get("phone"), source=opt.get("source") or "google",
                 address=opt.get("address") or "", place_id=opt.get("place_id"), next_open_at=opt.get("next_open_at"),
                 data=opt)
    elif act in ("browser_approve", "browser_decline"):
        from app.modules.browser import service as browser

        (browser.approve if act == "browser_approve" else browser.decline)(db, ctx, about.id if about else uuid.UUID(int=0))
    elif act == "expired":
        turn.say("text", "Det forslag er for gammelt. Skriv igen, hvem jeg skal ringe til.")
    elif act == "share_group":
        from app.modules.privat import groups

        r = groups.share(db, ctx, uuid.UUID(opt["task_id"]), uuid.UUID(opt["group_id"]), mode=opt.get("mode") or "group",
                         role="editor", style=opt.get("style") or "one_by_one")
        names = [x["name"] for x in r["added_in_app"]]
        n_sms = len(r["sms_queue"] or []) or len((r["sms_group"] or {}).get("recipients") or [])
        parts = []
        if names:
            parts.append(f"{', '.join(names)} har fået listen i appen.")
        if n_sms:
            parts.append(f"{n_sms} mangler en SMS fra dig – åbn listen og tryk «Send SMS».")
        turn.say("text", " ".join(parts) or "Der var ingen i gruppen at dele med.", task_id=uuid.UUID(opt["task_id"]))
    elif act == "create_group":
        from app.modules.privat import groups

        g = groups.create(db, ctx, opt.get("name") or "Gruppe", opt.get("people") or [])
        turn.say("text", f"Gruppen {g.name} er gemt. Kun du kan se den.")
    else:
        turn.say("text", opt.get("text") or "Okay.")
    db.commit()
    return [user_msg, *turn.out]


def tool_json(x) -> str:
    return json.dumps(x, ensure_ascii=False)


def tool_share_with_group(turn: Turn, a: dict) -> str:
    from app.modules.privat import groups

    task, m = _resolve(turn, a.get("task_id"), "list", "owner")
    if m.role != "owner":
        return "Kun ejeren kan dele listen."
    g = groups.find_by_name(turn.db, turn.ctx, str(a.get("group_name") or ""))
    if g is None:
        name = str(a.get("group_name") or "gruppen").strip()[:60]
        turn.say("text", f"Du har ingen gruppe, der hedder «{name}». Skriv, hvem der skal være med (navn og "
                         "nummer), så foreslår jeg gruppen.")
        return "Gruppen findes ikke; spørg hvem der skal med (create_group)."
    mode = a.get("mode") if a.get("mode") in ("group", "wishlist") else (
        "wishlist" if task.list_type == "wishlist" else "group")
    key = addons.SHARE_MODE_ADDON[mode]
    if not addons.is_enabled(turn.db, turn.ctx.ws_id, key):
        return h_suggest_addon(turn, {"key": key})
    n = len(groups.members(turn.db, g))
    base = {"action": "share_group", "task_id": str(task.id), "group_id": str(g.id), "mode": mode}
    # share_proposal: options[0] is the group; the web opens its share sheet (nothing is shared before the yes)
    turn.say("share_proposal", f"Skal jeg dele «{task.title}» med {g.name}? Dem, der har Dialogbot, kommer med med det "
                               "samme – resten får en SMS fra dig. Der sendes intet, før du siger ja.",
             task_id=task.id, about_task_id_override=task.id,
             options=[{"id": str(g.id), "label": g.name, "sub": f"{n} personer", **base, "style": "one_by_one"}])
    return "Brugeren skal sige ja, før der deles."


def tool_create_group(turn: Turn, a: dict) -> str:
    from app.modules.campaigns.service import normalize_phone

    name = str(a.get("name") or "").strip()[:100]
    people = []
    for p in (a.get("members") or [])[:50]:
        if not isinstance(p, dict) or not str(p.get("name") or "").strip():
            continue
        phone = normalize_phone(str(p.get("phone") or "")) if p.get("phone") else None
        if phone and not _user_wrote(turn, phone):
            phone = None  # never a number the user did not write
        people.append({"name": str(p["name"]).strip()[:100], "phone": phone})
    if not name:
        return "Gruppen mangler et navn."
    names = [p["name"] for p in people]
    who = (" med " + (", ".join(names[:-1]) + " og " + names[-1] if len(names) > 1 else names[0])) if names else ""
    turn.say("clarify", f"Skal jeg lave gruppen {name}{who}?", options=[
        {"id": "yes", "label": "Ja, gem gruppen", "sub": "Kun du kan se den", "action": "create_group", "name": name,
         "people": people},
        {"id": "no", "label": "Nej tak", "sub": "", "action": "text", "text": "Fint, der er ikke gemt noget."}])
    return "Brugeren skal sige ja, før gruppen gemmes."


# --------------------------------------------------------------------------- Kalender (app/modules/privat/appointments.py)

def tool_add_to_calendar(turn: Turn, a: dict) -> str:
    from app.modules.privat import appointments

    when = _parse_when(a.get("starts_at"))
    if when is None or when <= rules.now():
        return "Tidspunktet mangler eller er i fortiden. Spørg brugeren hvornår."
    title = _cap(str(a.get("title") or "").strip())[:300] or "Aftale"
    minutes = a.get("minutes")
    appt = appointments.record(turn.db, turn.ctx.ws_id, source="manual", source_ref=f"manual:{uuid.uuid4()}", title=title,
                               starts_at=when.astimezone(UTC), minutes=int(minutes) if isinstance(minutes, int | float) else None,
                               location=str(a.get("location") or "").strip()[:300])
    st = appointments.connection_status(turn.db, turn.ctx.ws_id)
    where = [n for p, n in (("google", "Google Kalender"), ("microsoft", "Outlook")) if st[p]["connected"]]
    has_feed = turn.ctx.profile.calendar_feed_token_hash is not None
    if where:
        tail = f"Den kommer i {' og '.join(where)} om et øjeblik."
    elif has_feed:
        tail = "Den kommer i din kalender via dit kalenderlink (Google kan være op til et døgn om det)."
    else:
        tail = "Forbind din kalender under Apps → Kalender, så kommer den også dér."
    turn.say("text", f"{title} {rules.lower_first(rules.when_text(appt.starts_at))} er gemt. {tail}")
    return f"Aftale gemt (id {appt.id})."


def tool_calendar_status(turn: Turn, a: dict) -> str:
    from app.modules.privat import appointments

    st = appointments.connection_status(turn.db, turn.ctx.ws_id)
    where = [n for p, n in (("google", "Google Kalender"), ("microsoft", "Outlook")) if st[p]["connected"]]
    has_feed = turn.ctx.profile.calendar_feed_token_hash is not None
    if where or has_feed:
        parts = ([f"Dine aftaler kommer i {' og '.join(where)}."] if where else []) + \
                (["Dit private kalenderlink er aktivt."] if has_feed else [])
        text = " ".join(parts) + " Du kan ændre det under Apps → Kalender."
    else:
        text = ("Åbn Apps → Kalender. Dér forbinder du Google Kalender eller Outlook med ét tryk, eller får et privat "
                "link, som iPhone og alle andre kalendere kan abonnere på. Derefter kommer dine aftaler ind af sig selv.")
    turn.say("text", text)
    return "Status vist."


# --------------------------------------------------------------------------- Fødselsdage (app/modules/privat/birthdays.py)

def tool_add_birthdays(turn: Turn, a: dict) -> str:
    from app.core.errors import ValidationFailed
    from app.modules.privat import birthdays

    saved, bad = [], []
    for it in (a.get("items") or [])[:50]:
        if not isinstance(it, dict):
            continue
        days = it.get("remind_days_before")
        try:
            b, _ = birthdays.save(turn.db, turn.ctx.ws_id, name=str(it.get("name") or ""), when=str(it.get("date") or ""),
                                  remind_days_before=int(days) if isinstance(days, int | float) else None)
            saved.append(b)
        except ValidationFailed:
            bad.append(str(it.get("name") or "?"))
    if not saved:
        return "Ingen fødselsdag kunne gemmes. Spørg efter dag og måned."
    lines = [f"{b.name}: {birthdays.date_text(b)}" for b in saved]
    days = {b.remind_days_before for b in saved}
    when = ("på dagen" if days == {0} else f"{days.pop()} dage før") if len(days) == 1 else "før hver fødselsdag"
    text = ("Gemt: " + "; ".join(lines) + f". Jeg minder dig om det {when}.")
    if bad:
        text += " Jeg kunne ikke læse datoen for " + ", ".join(bad) + " – skriv fx 14. marts."
    turn.say("text", text)
    return f"{len(saved)} gemt, {len(bad)} ikke læst."


def tool_list_birthdays(turn: Turn, a: dict) -> str:
    from app.modules.privat import birthdays

    turn.say("text", birthdays.upcoming_text(turn.db, turn.ctx.ws_id))
    return "Vist."


def tool_remove_birthday(turn: Turn, a: dict) -> str:
    from app.modules.privat import birthdays

    b = birthdays.find(turn.db, turn.ctx.ws_id, str(a.get("name") or ""))
    if b is None:
        return "Den fødselsdag findes ikke. Spørg brugeren hvem."
    name = b.name
    birthdays.remove(turn.db, b)
    turn.say("text", f"{name}s fødselsdag er fjernet.")
    return "Fjernet."


# --------------------------------------------------------------------------- Regninger (app/modules/privat/bills.py)

def tool_add_bills(turn: Turn, a: dict) -> str:
    from app.core.errors import ValidationFailed
    from app.modules.privat import bills

    saved, bad = [], []
    for it in (a.get("items") or [])[:50]:
        if not isinstance(it, dict):
            continue
        days = it.get("remind_days_before")
        try:
            b, _ = bills.save(turn.db, turn.ctx.ws_id, name=str(it.get("name") or ""), amount=it.get("amount"),
                              frequency=str(it.get("frequency") or "monthly"), due_date=it.get("due_date"),
                              due_day=it.get("due_day") if isinstance(it.get("due_day"), int) else None,
                              remind_days_before=int(days) if isinstance(days, int | float) else None)
            saved.append(b)
        except ValidationFailed as e:
            bad.append(f"{it.get('name') or '?'} ({e.message})")
    if not saved:
        return "Ingen regning kunne gemmes: " + "; ".join(bad) + ". Spørg efter datoen."
    lines = [f"{b.name}: {bills.FREQ_TEXT[b.frequency]}, næste gang {bills.date_text(b.next_due)}"
             + (f", {bills.money(b.amount_minor)}" if b.amount_minor else "") for b in saved]
    text = "Gemt: " + "; ".join(lines).rstrip(".") + ". Jeg minder dig om det inden – jeg betaler aldrig selv."
    if bad:
        text += " Ikke gemt: " + "; ".join(bad) + "."
    turn.say("text", text)
    return f"{len(saved)} gemt, {len(bad)} ikke gemt."


def tool_bills_overview(turn: Turn, a: dict) -> str:
    from app.modules.privat import bills

    turn.say("text", bills.overview_text(turn.db, turn.ctx.ws_id))
    return "Vist."


def tool_remove_bill(turn: Turn, a: dict) -> str:
    from app.modules.privat import bills

    b = bills.find(turn.db, turn.ctx.ws_id, str(a.get("name") or ""))
    if b is None:
        return "Den regning findes ikke. Spørg brugeren hvilken."
    name = b.name
    bills.remove(turn.db, b)
    turn.say("text", f"Regningen «{name}» er fjernet.")
    return "Fjernet."


# --------------------------------------------------------------------------- Pakkeliste and Madplan

def _str_list(raw) -> list[str]:
    return [str(x) for x in (raw or []) if isinstance(x, str | int | float) and str(x).strip()]


def tool_create_packing_list(turn: Turn, a: dict) -> str:
    from app.modules.privat import packing

    items = _str_list(a.get("items"))
    if not items:
        return "Pakkelisten mangler punkter."
    task = packing.create(turn.db, turn.ctx, trip=str(a.get("trip") or ""), items=items)
    _created(turn, task, f"Her er pakkelisten til {task.title.removeprefix('Pakkeliste: ')} med {len(items)} ting. "
                         "Jeg gemmer den til næste gang.")
    return f"Pakkeliste oprettet (id {task.id}, status {task.status})."


def tool_reuse_packing_list(turn: Turn, a: dict) -> str:
    from app.modules.privat import packing

    task = packing.reuse(turn.db, turn.ctx, trip=str(a.get("trip") or "").strip() or None)
    if task is None:
        return "Der er ingen tidligere pakkeliste. Lav en ny med create_packing_list."
    _created(turn, task, "Her er pakkelisten fra sidst – intet er krydset af. Ret den til, hvis noget er anderledes denne gang.")
    return f"Pakkeliste oprettet ud fra sidst (id {task.id})."


def tool_save_food_preferences(turn: Turn, a: dict) -> str:
    from app.modules.privat import meals

    people = a.get("people")
    p = meals.save_preferences(turn.db, turn.ctx.ws_id, people=int(people) if isinstance(people, int | float) else None,
                               avoid=str(a.get("avoid") or "") or None, likes=str(a.get("likes") or "") or None)
    turn.say("text", f"Gemt: {meals.preferences_text(p)}. Det bruger jeg, når jeg laver madplaner.")
    return "Gemt."


def tool_get_food_preferences(turn: Turn, a: dict) -> str:
    from app.modules.privat import meals

    return meals.preferences_text(meals.preferences(turn.db, turn.ctx.ws_id))


def tool_save_meal_plan(turn: Turn, a: dict) -> str:
    from app.modules.privat import meals

    days = [d for d in (a.get("days") or []) if isinstance(d, dict) and str(d.get("dish") or "").strip()]
    if not days:
        return "Madplanen mangler retter."
    if not re.search(r"\b(ja|jo|gem|gemme|ok|okay|gerne|fint|godt|perfekt|super|lyder godt|yes)\b", turn.text.lower()):
        return ("Ikke gemt: brugeren har ikke sagt ja endnu. Skriv forslaget (dag og ret) i en kort tekst og spørg, "
                "om den skal gemmes med indkøbsliste.")
    plan, shop = meals.save_plan(turn.db, turn.ctx, title=str(a.get("title") or "Madplan").strip(), days=days,
                                 shopping=a.get("shopping_list") is not False)
    text = f"Madplanen er gemt med {len(days)} retter."
    if shop is not None:
        text += f" Indkøbslisten har {len(meals.merge_ingredients(days))} varer – del den med husstanden, hvis I handler sammen."
    _created(turn, plan, text)
    if shop is not None:
        turn.say("task", shop.title, task_id=shop.id)
    return f"Madplan gemt (id {plan.id})" + (f", indkøbsliste {shop.id}." if shop else ".")


# --------------------------------------------------------------------------- Læge & tandlæge, Bil & syn

def _typed_phone(turn: Turn, raw) -> str | None:
    """A number the user typed themselves (never one the model made up), as E.164."""
    from app.modules.campaigns.service import normalize_phone

    phone = normalize_phone(str(raw or ""))
    return phone if phone and _user_wrote(turn, phone) else None


def tool_save_health_contact(turn: Turn, a: dict) -> str:
    from app.modules.privat import health

    kind = str(a.get("kind") or "")
    if kind not in health.KINDS:
        return "Er det lægen eller tandlægen?"
    phone = _typed_phone(turn, a.get("phone"))
    if phone is None:
        return "Nummeret er ikke skrevet af brugeren. Spørg efter det; opfind det aldrig."
    name = str(a.get("name") or "").strip() or health.KINDS[kind].capitalize()
    health.save_contact(turn.db, turn.ctx.ws_id, kind=kind, name=name, phone_e164=phone)
    turn.say("text", f"Din {health.KINDS[kind]} er gemt: {name}, {rules.phone_display(phone)}. "
                     f"Sig til, når jeg skal ringe og finde en tid – jeg ringer først, når du godkender.")
    return "Gemt."


def tool_book_health_appointment(turn: Turn, a: dict) -> str:
    from app.modules.privat import health

    kind = str(a.get("kind") or "")
    c = health.contacts(turn.db, turn.ctx.ws_id).get(kind)
    if c is None:
        return f"Der er ingen gemt {health.KINDS.get(kind, 'læge')}. Spørg efter klinikkens navn og nummer."
    data = {"purpose": str(a.get("purpose") or "").strip()[:300], "window": str(a.get("window") or "").strip()[:200],
            "may_not": "Fortæl ikke andet om mit helbred end det, der står i formålet."}
    return _propose(turn, name=c["name"], phone=c["phone"], source="user", data=data)


def tool_save_car(turn: Turn, a: dict) -> str:
    from app.core.errors import ValidationFailed
    from app.modules.privat import car

    try:
        data = car.save_car(turn.db, turn.ctx.ws_id, plate=a.get("plate") or None, inspection_due=a.get("inspection_due"),
                            service_due=a.get("service_due"),
                            tire_reminders=a.get("tire_reminders") if isinstance(a.get("tire_reminders"), bool) else None)
    except ValidationFailed as e:
        return f"Ikke gemt: {e.message}"
    turn.say("text", "Gemt. " + car.status_text(data) + " Jeg minder dig om det i god tid.")
    return "Gemt."


def tool_save_workshop(turn: Turn, a: dict) -> str:
    from app.modules.privat import car

    phone = _typed_phone(turn, a.get("phone"))
    if phone is None:
        return "Nummeret er ikke skrevet af brugeren. Spørg efter det; opfind det aldrig."
    name = str(a.get("name") or "").strip() or "Værkstedet"
    car.save_workshop(turn.db, turn.ctx.ws_id, name=name, phone_e164=phone)
    turn.say("text", f"Værkstedet er gemt: {name}, {rules.phone_display(phone)}.")
    return "Gemt."


def tool_book_workshop(turn: Turn, a: dict) -> str:
    from app.modules.privat import car

    w = car.get(turn.db, turn.ctx.ws_id).get("workshop")
    if not w:
        return "Der er intet gemt værksted. Spørg efter værkstedets navn og nummer."
    data = {"purpose": str(a.get("purpose") or "").strip()[:300], "window": str(a.get("window") or "").strip()[:200]}
    return _propose(turn, name=w["name"], phone=w["phone"], source="user", data=data)


def tool_car_status(turn: Turn, a: dict) -> str:
    from app.modules.privat import car

    turn.say("text", car.status_text(car.get(turn.db, turn.ctx.ws_id)))
    return "Vist."


# --------------------------------------------------------------------------- Pakker

def tool_track_parcel(turn: Turn, a: dict) -> str:
    from app.core.errors import ValidationFailed
    from app.modules.privat import parcels

    try:
        p = parcels.add(turn.db, turn.ctx.ws_id, number=str(a.get("number") or ""), label=str(a.get("label") or "") or None)
    except ValidationFailed as e:
        return f"Ikke fulgt: {e.message}"
    turn.say("text", f"Jeg følger pakken. {parcels.text_of(p)}. Du får besked, når den rykker sig.")
    return "Fulgt."


def tool_parcels_status(turn: Turn, a: dict) -> str:
    from app.modules.privat import parcels

    items = [p for p in parcels.parcels(turn.db, turn.ctx.ws_id)]
    turn.say("text", "\n".join(f"- {parcels.text_of(p)}" for p in items[:15]) if items else "Du følger ingen pakker.")
    return "Vist."


def tool_stop_tracking(turn: Turn, a: dict) -> str:
    from app.modules.privat import parcels

    hit = parcels.remove(turn.db, turn.ctx.ws_id, str(a.get("number") or ""))
    if hit is None:
        return "Den pakke følger brugeren ikke. Spørg hvilken."
    turn.say("text", f"Jeg følger ikke længere {hit.get('label') or hit['number']}.")
    return "Stoppet."


# --------------------------------------------------------------------------- Rejser

def tool_search_trips(turn: Turn, a: dict) -> str:
    from app.core.errors import ValidationFailed
    from app.modules.privat import travel

    try:
        result = travel.search(turn.db, turn.ctx.ws_id, a)
    except ValidationFailed as e:
        return f"Mangler: {e.message}. Spørg brugeren kort."
    text = travel.summary(result)
    if result["offers"]:
        text += " Du finder «Book» under Apps → Rejser."
    turn.say("text", text)
    return f"{len(result['offers'])} rejser vist (søgning {result['id']})."

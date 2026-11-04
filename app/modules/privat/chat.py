"""The private assistant's chat: one model turn with tools, at most a few tool rounds.

Core tools (always): create_list, add_items, create_reminder, move_reminder, list_waiting, ask_clarifying,
suggest_addon. Add-on tools (propose_call, share_list, …) come from the catalog (addons.py) and are only offered when
the add-on is on; for a switched-off add-on the model can only offer it (suggest_addon → a kind "addon" message).

Calls: the assistant NEVER invents a business or a number. For the pilot a call needs a number the user wrote
themselves, or a pick from a small fixture of fictional Aarhus businesses (FIXTURES, demo only – refused for real
dialling outside dev/test). Looking real businesses up (Google Places/CVR) is future work.
Nothing is ever dialled from the chat: propose_call only creates a proposal the user approves in /privat/calls.
"""
from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from app.core.errors import ApiError, NotFound
from app.models import PrivateMessage, PrivateTask, PrivateTaskMember
from app.modules.privat import addons, rules, service, sharing

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
CATEGORY_WORDS = {"cykelværksted": ("cykel", "cykelværksted", "cykelsmed")}

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
{lists}{about}{addons}"""


@dataclass
class Turn:
    db: OrmSession
    ctx: object
    text: str
    about: PrivateTask | None
    out: list[PrivateMessage] = field(default_factory=list)

    def say(self, kind: str, text: str, **kw) -> PrivateMessage:
        m = service.add_message(self.db, self.ctx.ws_id, kind=kind, text=text,
                                about_task_id=self.about.id if self.about else None, **kw)
        self.out.append(m)
        return m


def _obj(props: dict, required: list[str] | None = None) -> dict:
    return {"type": "object", "properties": props, "required": required or []}


CORE_TOOLS = [
    {"name": "create_list", "description": "Lav en ny liste (bruger én af månedens gratis opgaver).",
     "input_schema": _obj({"title": {"type": "string"}, "type": {"type": "string", "enum": list(service.LIST_TYPES)},
                           "items": {"type": "array", "items": {"type": "string"}}}, ["title"])},
    {"name": "add_items", "description": "Tilføj punkter til en eksisterende liste (gratis). Udelad task_id for den "
                                         "liste, samtalen handler om, eller den nyeste liste.",
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
    """(tool definitions for the model, name → add-on tool) – only enabled add-ons contribute tools."""
    defs = list(CORE_TOOLS)
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
    db.commit()
    provider = get_provider()
    tools, extra = tools_for(db, ctx.ws_id)
    system = _system(db, ctx, about)
    messages = _history(db, ctx)
    c, _row = log_call(db, ctx.workspace, provider, user_id=ctx.user_id, purpose="privat_chat", system=system,
                       messages=messages, prompt_version=PROMPT_VERSION, revision=0, max_tokens=1024, tools=tools)
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
        messages = messages + [{"role": "assistant", "content": c.assistant_content}, tool_result_message(results)]
        c, _row = log_call(db, ctx.workspace, provider, user_id=ctx.user_id, purpose="privat_chat", system=system,
                           messages=messages, prompt_version=PROMPT_VERSION, revision=0, max_tokens=1024, tools=tools)
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
    if isinstance(raw, str):
        raw = re.split(r",|\sog\s", raw)
    return [str(x).strip()[:300] for x in (raw or []) if str(x).strip()][:50]


def _cap(s: str) -> str:
    return s[:1].upper() + s[1:] if s else s


def _join(items: list[str]) -> str:
    low = [i.lower() for i in items]
    return low[0] if len(low) == 1 else ", ".join(low[:-1]) + " og " + low[-1]


def _created(turn: Turn, task: PrivateTask, intro: str) -> None:
    if task.status == "draft":
        turn.say("draft", f"Månedens {rules.FREE_LIMIT} gratis opgaver er brugt. Opgaven er gemt som udkast – "
                          "fortsæt med 1 credit, køb credits eller se et frivilligt sponsorindslag.", task_id=task.id)
        return
    turn.say("text", intro, task_id=task.id)
    turn.say("task", task.title, task_id=task.id)


def h_create_list(turn: Turn, a: dict) -> str:
    items = _items(a.get("items"))
    lt = a.get("type") if a.get("type") in service.LIST_TYPES else None
    title = _cap(str(a.get("title") or "").strip()) or {"shopping": "Indkøbsliste", "wishlist": "Ønskeliste"}.get(lt or "", "Liste")
    task = service.create_digital(turn.db, turn.ctx, kind="list", title=title, items=items, list_type=lt)
    intro = f"Her er din {title.lower()}" + (f" med {_join(items)}." if items else ".")
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


def h_add_items(turn: Turn, a: dict) -> str:
    task, m = _resolve(turn, a.get("task_id"), "list", "editor")
    added = service.add_items(turn.db, task, m, _items(a.get("items")))
    names = [i.text for i in added]
    turn.say("text", f"Tilføjet {_join(names)}. Det er stadig den samme liste, og en rettelse koster ingen opgave.",
             task_id=task.id)
    turn.say("task", task.title, task_id=task.id)
    return f"Tilføjet til {task.id}."


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


CORE_HANDLERS = {"create_list": h_create_list, "add_items": h_add_items, "create_reminder": h_create_reminder,
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


def _fixture(key: str | None) -> dict | None:
    k = (key or "").strip().lower()
    return next((f for f in FIXTURES if k in (f["id"], f["name"].lower())), None)


def _category(*words: str) -> str | None:
    low = " ".join(w.lower() for w in words if w)
    return next((c for c, ws in CATEGORY_WORDS.items() if any(w in low for w in ws)), None)


def tool_propose_call(turn: Turn, a: dict) -> str:
    from app.modules.campaigns.service import normalize_phone
    from app.modules.privat import calls

    name = str(a.get("business_name") or "").strip()[:200]
    window = str(a.get("window") or "").strip()[:200]
    purpose = str(a.get("purpose") or "").strip()[:300]
    fx = _fixture(a.get("fixture_id")) or _fixture(name)
    if fx is None and a.get("phone"):
        phone = normalize_phone(str(a["phone"]))
        if phone is None or not _user_wrote(turn, phone):
            turn.say("text", f"Hvilket nummer skal jeg ringe til{' hos ' + name if name else ''}? Skriv det, så "
                             "laver jeg et forslag, du kan godkende.")
            return "Nummeret er ikke skrevet af brugeren. Spørg efter det; opfind det aldrig."
        if not name:
            turn.say("text", "Hvad hedder virksomheden? Så laver jeg et forslag, du kan godkende.")
            return "Mangler virksomhedens navn."
        task = calls.propose(turn.db, turn.ctx, business_name=name, phone=phone, address="", price_text=None,
                             purpose=purpose, window=window, may_ask=a.get("may_ask"), may_agree=a.get("may_agree"),
                             may_not=a.get("may_not"))
        turn.say("call_proposal", f"Her er mit forslag til opkaldet til {name}. Jeg ringer først, når du godkender.",
                 task_id=task.id)
        return f"Forslag oprettet (id {task.id}). Der er IKKE ringet; brugeren skal godkende."
    if fx is not None:
        task = calls.propose(turn.db, turn.ctx, business_name=fx["name"], phone=fx["phone"], address=fx["address"],
                             price_text=fx["price"], purpose=purpose, window=window, may_ask=a.get("may_ask"),
                             may_agree=a.get("may_agree"), may_not=a.get("may_not"))
        turn.say("call_proposal", f"Her er mit forslag til opkaldet til {fx['name']}. Jeg ringer først, når du "
                                  "godkender.", task_id=task.id)
        return f"Forslag oprettet (id {task.id}). Der er IKKE ringet."
    cat = _category(str(a.get("category") or ""), name, turn.text)
    if cat:
        opts = [{"id": f["id"], "label": f["name"], "sub": f["sub"], "action": "call_fixture", "fixture_id": f["id"],
                 "window": window, "purpose": purpose} for f in FIXTURES if f["category"] == cat]
        opts.append({"id": "other", "label": "En anden", "sub": "Skriv navnet og nummeret", "action": "text",
                     "text": "Skriv navnet og nummeret på virksomheden, så laver jeg et forslag."})
        turn.say("clarify", f"Hvilket {cat} mener du? Jeg fandt to tæt på dig:", options=opts)
        return "Brugeren vælger virksomhed."
    turn.say("text", "Hvem skal jeg ringe til? Skriv virksomhedens navn og telefonnummer.")
    return "Mangler virksomhed og nummer. Opfind dem ikke."


def tool_share_list(turn: Turn, a: dict) -> str:
    task, m = _resolve(turn, a.get("task_id"), "list", "owner")
    if m.role != "owner":
        return "Kun ejeren kan dele listen."
    mode = a.get("mode") if a.get("mode") in ("group", "wishlist") else (
        "wishlist" if task.list_type == "wishlist" else "group")
    key = addons.SHARE_MODE_ADDON[mode]
    if not addons.is_enabled(turn.db, turn.ctx.ws_id, key):
        return h_suggest_addon(turn, {"key": key})
    role = a.get("role") if a.get("role") in ("editor", "viewer") else "editor"
    who = str(a.get("with_name") or "").strip()[:60]
    turn.say("clarify", f"Skal jeg lave et invitationslink til «{task.title}»{', så du kan dele den med ' + who if who else ''}? "
                        "Der bliver ikke sendt noget – du deler selv linket.",
             task_id=task.id, options=[
                 {"id": "yes", "label": "Ja, lav linket", "sub": "Du deler det selv", "action": "share",
                  "task_id": str(task.id), "mode": mode, "role": role},
                 {"id": "no", "label": "Nej tak", "sub": "", "action": "text", "text": "Fint, listen er ikke delt."}])
    return "Brugeren skal sige ja, før der laves et link."


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
    if act == "call_fixture":
        addons.require(db, ctx.ws_id, "ring-for-mig")
        tool_propose_call(turn, {"fixture_id": opt.get("fixture_id"), "window": opt.get("window"),
                                 "purpose": opt.get("purpose")})
    elif act == "share":
        from app.modules.privat import invites

        mode = opt.get("mode") or "group"
        inv, raw = invites.create(db, ctx, addon_key=addons.SHARE_MODE_ADDON[mode],
                                  resource_id=uuid.UUID(opt["task_id"]), mode=mode, role=opt.get("role") or "editor")
        o = invites.invite_out(db, inv, raw, ctx.user.display_name)
        turn.say("text", f"Her er linket – send det selv fra din telefon: {o['short_url']}\n"
                         f"Forslag til SMS: «{o['suggested_text']}»", task_id=uuid.UUID(opt["task_id"]))
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
    turn.say("clarify", f"Skal jeg dele «{task.title}» med {g.name} ({n} personer)? Dem, der har Dialogbot, får den "
                        "med det samme; de andre får en SMS, som du selv sender fra din telefon.", task_id=task.id,
             options=[{"id": "one", "label": "Ja, én ad gangen", "sub": "Personlig SMS og link til hver", **base,
                       "style": "one_by_one"},
                      {"id": "all", "label": "Ja, én samlet SMS", "sub": "Én gruppebesked", **base, "style": "group_sms"},
                      {"id": "no", "label": "Nej tak", "sub": "", "action": "text", "text": "Fint, listen er ikke delt."}])
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

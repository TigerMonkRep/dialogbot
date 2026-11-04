"""The Privat funnel: answers → the tasks and lists Peter sets up.

`plan()` is pure (used for the preview on /privat/start while the visitor answers – nothing exists yet);
`create()` makes the real rows after the SMS code, through the same code paths the chat uses:
- a postponed errand that needs a phone call → a call PROPOSAL without a number (awaiting_user, «Hvad er deres
  nummer?» exactly as chat.tool_propose_call makes it). Nothing is dialled; the user adds the number and approves.
- a postponed errand that is just a thing to do → a reminder (planned) at the chosen time tomorrow.
- the household → the standard lists (in_progress).
"""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.orm import Session as OrmSession

from app.modules.privat import rules

# key → (what the task is called, call|reminder, the business it concerns for a call)
POSTPONED: dict[str, dict] = {
    "dentist": {"title": "Bestil tid hos tandlægen", "kind": "call", "business": "tandlægen",
                "purpose": "Bestil en tid til eftersyn"},
    "bike": {"title": "Få cyklen til service", "kind": "call", "business": "cykelsmeden",
             "purpose": "Bestil tid til et cykeleftersyn"},
    "car_inspection": {"title": "Book syn af bilen", "kind": "call", "business": "synshallen",
                       "purpose": "Book en tid til syn af bilen"},
    "gift": {"title": "Køb gaven", "kind": "reminder"},
    "doctor": {"title": "Bestil tid hos lægen", "kind": "call", "business": "lægen",
               "purpose": "Bestil en tid hos lægen"},
    "hairdresser": {"title": "Bestil tid hos frisøren", "kind": "call", "business": "frisøren",
                    "purpose": "Bestil en tid til klipning"},
    "insurance": {"title": "Ring til forsikringen", "kind": "call", "business": "forsikringsselskabet",
                  "purpose": "Få styr på forsikringen"},
    "landlord": {"title": "Ring til udlejer", "kind": "call", "business": "udlejer",
                 "purpose": "Tal med udlejer om det, der mangler"},
}
HOUSEHOLD = ("alone", "couple", "kids", "parents")
LISTS: dict[str, list[dict]] = {
    "alone": [{"title": "Indkøbsliste", "type": "shopping", "items": ["Mælk", "Brød", "Kaffe"]}],
    "couple": [{"title": "Indkøbsliste", "type": "shopping", "items": ["Mælk", "Brød", "Kaffe"]}],
    "kids": [{"title": "Indkøbsliste", "type": "shopping", "items": ["Mælk", "Brød", "Frugt", "Madpakkepålæg"]},
             {"title": "Pakkeliste", "type": "todo", "items": ["Skiftetøj", "Drikkedunk", "Regntøj"]}],
    "parents": [{"title": "Indkøbsliste", "type": "shopping", "items": ["Mælk", "Brød", "Kaffe"]},
                {"title": "Fødselsdage", "type": "todo", "items": ["Mor", "Far"]}],
}
HATE_CALLS = ("health", "workshop", "municipality", "restaurant")
REMIND_AT = {"morning": 8, "lunch": 12, "evening": 19}


def plan(answers: dict) -> dict:
    """The preview: {tasks: int, lists: int, first_call: {title}|null, items: [...]} from the answers so far."""
    chosen = [k for k in (answers.get("postponed") or []) if k in POSTPONED]
    household = answers.get("household") if answers.get("household") in HOUSEHOLD else None
    tasks = [{"kind": POSTPONED[k]["kind"], "title": POSTPONED[k]["title"], "key": k} for k in chosen]
    lists = LISTS.get(household or "", [])
    first = next((t for t in tasks if t["kind"] == "call"), None)
    return {"tasks": len(tasks), "lists": len(lists), "first_call": {"title": first["title"]} if first else None,
            "items": tasks + [{"kind": "list", "title": x["title"]} for x in lists]}


def remind_time(answers: dict, now: datetime | None = None) -> datetime:
    """Tomorrow at 08, 12 or 19 Europe/Copenhagen (morning when nothing was chosen)."""
    hour = REMIND_AT.get(answers.get("remind_at") or "", 8)
    local = rules.local(now)
    return (local + timedelta(days=1)).replace(hour=hour, minute=0, second=0, microsecond=0)


def create(db: OrmSession, ctx, answers: dict) -> dict:
    """The real rows for a freshly verified account. Returns {task_ids, first_call_task_id}."""
    from app.modules.privat import chat, service

    when = remind_time(answers)
    ids: list[str] = []
    first_call = None
    for key in (k for k in (answers.get("postponed") or []) if k in POSTPONED):
        spec = POSTPONED[key]
        if spec["kind"] == "call":
            turn = chat.Turn(db=db, ctx=ctx, text="", about=None)
            chat._propose(turn, name=spec["business"], phone=None, source="user", data={"purpose": spec["purpose"]})
            task = next(m.task_id for m in turn.out if m.task_id)
            ids.append(str(task))
            first_call = first_call or str(task)
        else:
            task = service.create_digital(db, ctx, kind="reminder", title=spec["title"], remind_at=when)
            ids.append(str(task.id))
    household = answers.get("household") if answers.get("household") in HOUSEHOLD else None
    for x in LISTS.get(household or "", []):
        task = service.create_digital(db, ctx, kind="list", title=x["title"], items=x["items"], list_type=x["type"])
        ids.append(str(task.id))
    if ids:
        service.add_message(db, ctx.ws_id, kind="text",
                            text="Velkommen! Jeg har sat din dag op ud fra dine svar. Ret, flyt eller slet, som du vil – "
                                 "og skriv nummeret, når jeg skal ringe for dig.")
    return {"task_ids": ids, "first_call_task_id": first_call}

"""The Fælles udgifter app: who paid what on the trip, in the summer house or in the shared flat – and who owes whom.

A group (`private_app_data` «faelles-udgifter», `items`) is a name, the people (first names, as written) and an ordinary
list «Udgifter: <navn>» that holds the expenses, one per line: «Anna: 300 kr. – vin». Because it is a list, it can be
shared with the friends (Delte lister): they add their own lines – «Bo: 250 kr – pizza», or just «250 kr pizza» and
their own first name is used. Settling up gives the fewest transfers. Dialogbot never moves money (MobilePay has no open
API for private users): the summary says who pays whom – with the user's own MobilePay number when the user is owed and
the number is verified – and ends with Dialogbot's footer, so the friends see where it came from.
Groups from before the list (expenses kept in the JSON) still count.
"""
from __future__ import annotations

import re
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from app.core.errors import ValidationFailed
from app.models import PrivateTask, PrivateTaskItem, User
from app.modules.privat import app_kit as kit
from app.modules.privat import brand, rules, service

ADDON, PATH = "faelles-udgifter", "/privat/apps/faelles-udgifter"
MAX_GROUPS, MAX_PEOPLE = 30, 30
LINE = re.compile(r"^\s*(?:(?P<name>[A-Za-zÆØÅæøåÄÖÜäöüé][\wæøåÆØÅ'-]*)\s*[:–-]\s*)?(?P<amt>\d[\d.]*(?:,\d{1,2})?)\s*"
                  r"(?:kr\.?|,-)?\s*(?:[–-]\s*)?(?P<text>.*)$")


def _name(s: str) -> str:
    s = kit.clean(s, 40)
    return s[:1].upper() + s[1:]


def _person(group: dict, raw: str, me: str) -> str:
    n = _name(raw)
    if kit.key_of(n) in ("jeg", "mig", "mig selv"):
        n = me
    hit = next((p for p in group["people"] if kit.key_of(p) == kit.key_of(n)), None)
    if hit:
        return hit
    if len(group["people"]) >= MAX_PEOPLE:
        raise ValidationFailed("Der er for mange personer i gruppen", field_errors=[{"field": "people"}])
    group["people"].append(n)
    return n


def group_for(rows: list[dict], name: str | None) -> dict | None:
    if name:
        return kit.find(rows, name)
    return rows[0] if rows else None


def _task(db: OrmSession, g: dict) -> PrivateTask | None:
    return db.get(PrivateTask, uuid.UUID(g["task_id"])) if g.get("task_id") else None


def add_expense(db: OrmSession, ctx, *, me: str, group: str | None, paid_by: str, amount, text: str = "",
                among: list[str] | None = None, people: list[str] | None = None) -> tuple[dict, dict]:
    minor = kit.amount(amount, required=True)
    if not minor:
        raise ValidationFailed("Beløbet skal være over 0 kr.", field_errors=[{"field": "amount"}])
    rows = kit.items(db, ctx.ws_id, ADDON)
    g = group_for(rows, group)
    if g is None:
        if len(rows) >= MAX_GROUPS:
            raise ValidationFailed("Du har for mange grupper – slet en gammel først", field_errors=[{"field": "group"}])
        g = {"id": kit.new_id(), "name": kit.clean(group, 60) or "Fælles udgifter", "people": [], "expenses": []}
        rows.insert(0, g)
    _person(g, me, me)
    for p in people or []:
        _person(g, p, me)
    payer = _person(g, paid_by or me, me)
    split = [_person(g, p, me) for p in (among or [])] or None
    task = _task(db, g)
    if task is None:
        task = service.create_digital(db, ctx, kind="list", title=f"Udgifter: {g['name']}"[:300], list_type="todo")
        task.next_step = "Skriv udlæg som «Navn: 250 kr. – hvad»"
        g["task_id"] = str(task.id)
    what = kit.clean(text, 120)
    line = f"{payer}: {kit.money(minor)}{' – ' + what if what else ''}"
    note = f"Deles mellem {', '.join(split)}" if split else None
    service._add_item(db, task, line, ctx.user_id, note=note)
    db.flush()
    kit.save_items(db, ctx.ws_id, ADDON, rows)
    return g, {"payer": payer, "amount_minor": minor, "text": what, "among": split}


def _among(note: str | None, people: list[str]) -> list[str] | None:
    if not note or not note.startswith("Deles mellem "):
        return None
    wanted = [kit.key_of(x) for x in note.removeprefix("Deles mellem ").split(",")]
    return [p for p in people if kit.key_of(p) in wanted] or None


def expenses_of(db: OrmSession, g: dict) -> dict:
    """The group with all its expenses: the ones kept in the JSON plus the lines on its (shared) list."""
    g = {**g, "people": list(g.get("people", [])), "expenses": list(g.get("expenses", []))}
    task = _task(db, g)
    if task is None:
        return g
    names = {}
    for it in db.scalars(select(PrivateTaskItem).where(PrivateTaskItem.task_id == task.id)
                         .order_by(PrivateTaskItem.position, PrivateTaskItem.created_at)):
        m = LINE.match(it.text)
        minor = kit.amount(m.group("amt")) if m else None
        if not minor:
            continue                       # a line that is not an expense («husk kvitteringer») is just a note
        name = m.group("name")
        if not name and it.added_by_user_id:
            if it.added_by_user_id not in names:
                u = db.get(User, it.added_by_user_id)
                names[it.added_by_user_id] = rules.first_name(u.display_name) if u else "Ukendt"
            name = names[it.added_by_user_id]
        payer = _person(g, name or "Ukendt", name or "Ukendt")
        g["expenses"].append({"payer": payer, "amount_minor": minor, "text": m.group("text").strip(),
                              "among": _among(it.note, g["people"])})
    return g


def balances(g: dict) -> dict[str, int]:
    """+ = is owed money, - = owes. Shares are split in whole øre; the leftover øre go to the first people."""
    bal = {p: 0 for p in g["people"]}
    for e in g["expenses"]:
        among = e.get("among") or g["people"]
        share, rest = divmod(e["amount_minor"], len(among))
        bal[e["payer"]] = bal.get(e["payer"], 0) + e["amount_minor"]
        for i, p in enumerate(among):
            bal[p] = bal.get(p, 0) - share - (1 if i < rest else 0)
    return bal


def settle(g: dict) -> list[tuple[str, str, int]]:
    """The fewest transfers (debtor, creditor, øre): largest debtor pays largest creditor first."""
    bal = balances(g)
    debt = sorted([[p, -v] for p, v in bal.items() if v < 0], key=lambda x: -x[1])
    cred = sorted([[p, v] for p, v in bal.items() if v > 0], key=lambda x: -x[1])
    out, i, j = [], 0, 0
    while i < len(debt) and j < len(cred):
        n = min(debt[i][1], cred[j][1])
        out.append((debt[i][0], cred[j][0], n))
        debt[i][1] -= n
        cred[j][1] -= n
        i += debt[i][1] == 0
        j += cred[j][1] == 0
    return out


def summary_text(g: dict, *, share: bool = False, mobilepay: dict[str, str] | None = None) -> str:
    """`mobilepay`: {name: number} – only the user's own verified number, when the user is owed money."""
    total = sum(e["amount_minor"] for e in g["expenses"])
    lines = [f"{g['name']}: {kit.money(total)} i alt fordelt på {len(g['people'])} personer."]
    mp = mobilepay or {}
    lines += [f"- {a} betaler {kit.money(n)} til {b}" + (f" (MobilePay {mp[b]})" if b in mp else "")
              for a, b, n in settle(g)] or ["- I er kvit."]
    text = "\n".join(lines)
    return brand.branded(text) if share else text


def mobilepay_for(db: OrmSession, ws_id: uuid.UUID, me: str) -> dict[str, str]:
    from app.models import PrivateProfile

    p = db.get(PrivateProfile, ws_id)
    return {me: rules.phone_display(p.phone_e164)} if p is not None and p.phone_verified_at and p.phone_e164 else {}


def overview(db: OrmSession, ws_id: uuid.UUID) -> dict:
    rows = [expenses_of(db, g) for g in kit.items(db, ws_id, ADDON)]
    from app.models import PrivateProfile

    prof = db.get(PrivateProfile, ws_id)
    owner = db.get(User, prof.user_id) if prof is not None else None
    mp = mobilepay_for(db, ws_id, rules.first_name(owner.display_name)) if owner else {}
    return {"summary": (f"{len(rows)} {'gruppe' if len(rows) == 1 else 'grupper'}. Del listen «Udgifter: …», så kan de "
                        "andre selv skrive deres udlæg." if rows else
                        "Ingen fælles udgifter endnu. Sig fx «Jeg betalte 1.200 kr. for mad i sommerhuset – vi er Anna, "
                        "Bo og mig»."),
            "items": [{"id": g["id"], "text": g["name"], "sub": " · ".join(summary_text(g).split("\n")[1:4]),
                       "share_text": summary_text(g, share=True, mobilepay=mp)} for g in rows],
            "partner": None}


def remove(db: OrmSession, ws_id: uuid.UUID, item_id: str) -> bool:
    return kit.remove_item(db, ws_id, ADDON, item_id)


def is_shared(db: OrmSession, g: dict) -> bool:
    t = _task(db, g)
    return bool(t and t.share_mode)


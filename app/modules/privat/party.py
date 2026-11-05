"""The Fest & invitationer app: the party, the guest list, who comes, who brings what, and allergies.

Saved (`private_app_data` «fest», `items` = parties): title, date (and time), place, guests (name, status invited | yes |
no | maybe, what they bring, allergies/diet) and a to-bring list. Peter writes the invitation the user sends – with
Dialogbot's footer, so every guest sees where it came from. Reminders: 7 days before (who has not answered) and the
day before. Revenue: a disclosed partner link for party supplies or catering (brand.offer("fest")), if configured.
"""
from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy.orm import Session as OrmSession

from app.core.errors import ValidationFailed
from app.modules.privat import app_kit as kit
from app.modules.privat import brand

ADDON, PATH = "fest", "/privat/apps/fest"
STATUS = {"yes": "kommer", "no": "kommer ikke", "maybe": "måske", "invited": "har ikke svaret"}


def save(db: OrmSession, ws_id: uuid.UUID, *, title: str, when: str | None = None, time: str = "", place: str = "",
         guests: list[str] | None = None) -> tuple[dict, bool]:
    title = kit.clean(title, 100)
    if not title:
        raise ValidationFailed("Hvad er det for en fest?", field_errors=[{"field": "title"}])
    rows = kit.items(db, ws_id, ADDON)
    p = kit.find(rows, title, "title")
    created = p is None
    if p is None:
        p = {"id": kit.new_id(), "title": title[:1].upper() + title[1:], "guests": [], "bring": []}
        rows.insert(0, p)
    if when:
        p["date"] = kit.parse_date(when, "date")
    if time:
        p["time"] = kit.clean(time, 20)
    if place:
        p["place"] = kit.clean(place, 150)
    for g in guests or []:
        _guest(p, g)
    kit.save_items(db, ws_id, ADDON, rows[:30])
    return p, created


def _guest(p: dict, name: str) -> dict:
    n = kit.clean(name, 60)
    n = n[:1].upper() + n[1:]
    g = next((x for x in p["guests"] if kit.key_of(x["name"]) == kit.key_of(n)), None)
    if g is None:
        if len(p["guests"]) >= 200:
            raise ValidationFailed("For mange gæster", field_errors=[{"field": "guests"}])
        g = {"name": n, "status": "invited", "bring": "", "diet": ""}
        p["guests"].append(g)
    return g


def update_guest(db: OrmSession, ws_id: uuid.UUID, *, party: str | None, name: str, status: str | None = None,
                 bring: str | None = None, diet: str | None = None) -> tuple[dict, dict]:
    rows = kit.items(db, ws_id, ADDON)
    p = kit.find(rows, party, "title") if party else (rows[0] if rows else None)
    if p is None:
        raise ValidationFailed("Der er ingen fest med det navn", field_errors=[{"field": "party"}])
    g = _guest(p, name)
    if status in STATUS:
        g["status"] = status
    if bring is not None:
        g["bring"] = kit.clean(bring, 100)
    if diet is not None:
        g["diet"] = kit.clean(diet, 100)
    kit.save_items(db, ws_id, ADDON, rows)
    return p, g


def when_text(p: dict) -> str:
    if not p.get("date"):
        return ""
    return kit.date_text(p["date"]) + (f" kl. {p['time']}" if p.get("time") else "")


def status_text(p: dict) -> str:
    counts = {k: sum(1 for g in p["guests"] if g["status"] == k) for k in STATUS}
    head = f"{p['title']}{' – ' + when_text(p) if p.get('date') else ''}{', ' + p['place'] if p.get('place') else ''}."
    lines = [head, f"{counts['yes']} kommer, {counts['no']} kommer ikke, {counts['maybe']} måske, "
                   f"{counts['invited']} har ikke svaret."]
    bring = [f"{g['name']}: {g['bring']}" for g in p["guests"] if g.get("bring")]
    diet = [f"{g['name']}: {g['diet']}" for g in p["guests"] if g.get("diet")]
    if bring:
        lines.append("Medbringer – " + "; ".join(bring))
    if diet:
        lines.append("Allergier og kost – " + "; ".join(diet))
    return "\n".join(lines)


def invitation(p: dict, host: str, note: str = "") -> str:
    where = f" i {p['place']}" if p.get("place") else ""
    when = f" {when_text(p)}" if p.get("date") else ""
    extra = f"\n\n{kit.clean(note, 300)}" if note else ""
    return brand.branded(f"Du er inviteret: {p['title']}{when}{where}!{extra}\n\nSvar mig gerne, om du kommer, og om "
                         f"du har allergier eller andet, jeg skal vide.\n\nKærlig hilsen\n{host}")


def overview(db: OrmSession, ws_id: uuid.UUID) -> dict:
    rows = kit.items(db, ws_id, ADDON)
    return {"summary": f"{len(rows)} fester." if rows else
            "Ingen fester endnu. Sig fx «Lav en fest: Idas 10-års fødselsdag lørdag den 6. marts kl. 14 med Emma, Noah og Alma».",
            "items": [{"id": p["id"], "text": p["title"] + (f" · {when_text(p)}" if p.get("date") else ""),
                       "sub": status_text(p).split("\n", 1)[1] if p["guests"] else "Ingen gæster endnu"} for p in rows],
            "partner": brand.offer("fest")}


def remove(db: OrmSession, ws_id: uuid.UUID, item_id: str) -> bool:
    return kit.remove_item(db, ws_id, ADDON, item_id)


def due(data: dict, today: date) -> list[tuple[str, str]]:
    out = []
    for p in data.get("items", []):
        if not p.get("date"):
            continue
        left = (date.fromisoformat(p["date"]) - today).days
        waiting = [g["name"] for g in p["guests"] if g["status"] == "invited"]
        if 2 <= left <= 7 and waiting:
            out.append((f"week:{p['id']}:{p['date']}", f"{p['title']} er om en uge. Har ikke svaret: "
                                                       f"{', '.join(waiting[:10])}."))
        if 0 <= left <= 1:
            yes = sum(1 for g in p["guests"] if g["status"] == "yes")
            out.append((f"eve:{p['id']}:{p['date']}", f"{p['title']} er i morgen – {yes} har sagt ja."))
    return out

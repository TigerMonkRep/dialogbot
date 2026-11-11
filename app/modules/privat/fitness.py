"""The Fitness & sundhed app: the week's training, a simple log, and a nudge on the days it is planned.

Saved (`private_app_data` «fitness-og-sundhed»): a goal in the user's words («løbe 5 km i maj»), the weekly plan (day,
activity, time, minutes) and a log of workouts (date, activity, minutes). Deliberately NOT stored: weight, illness,
injuries, medicine, pulse or anything else about the body – that is health data (GDPR art. 9) and needs a legal review
first. Reminders: on a planned day (from 08:00), and on Mondays last week's tally. Booking a class, a PT or a
physiotherapist is an ordinary call proposal (app «Ring for mig»). Revenue: a disclosed partner link for gear or a
gym (brand.offer("fitness")), if configured.
"""
from __future__ import annotations

import re
import uuid
from datetime import date, timedelta

from sqlalchemy.orm import Session as OrmSession

from app.core.errors import ValidationFailed
from app.modules.privat import app_kit as kit
from app.modules.privat import appdata, brand

ADDON, PATH = "fitness-og-sundhed", "/privat/apps/fitness-og-sundhed"


def _today() -> date:
    from app.modules.privat import rules

    return rules.local().date()
DAYS = ("mandag", "tirsdag", "onsdag", "torsdag", "fredag", "lørdag", "søndag")
KEEP_LOG = 400


# Words about the body (GDPR art. 9). The promise «Gemmer aldrig vægt, sygdom … medicin» is kept HERE, on the server,
# not only in the model's prompt: a sentence that mentions one of them is never stored (PC-APP-03).
HEALTH = re.compile(
    r"\b(vej(?:er|ede|e)|vægt|kilo|\d+[.,]?\d*\s*kg|bmi|blodtryk\w*|\w*medicin\w*|pille\w*|tablet\w*|diabet\w*|"
    r"insulin|blodsukker|kolesterol|sygdom\w*|syg|diagnose\w*|gravid\w*|hjerte\w*|astma|depressi\w*|angst|"
    r"smerte\w*|skade\w*|skadet|operation\w*|opereret|allergi\w*|migræne|kræft|sclerose|gigt|puls|"
    r"tab(?:e|t)\s+mig|tage\s+på|menstruation\w*|overvægt\w*|undervægt\w*|spiseforstyrrelse\w*|stress\w*|sygemeld\w*)\b", re.I)


def without_health(text: str | None) -> str:
    """The text with every sentence (or part between commas/«og») that mentions the body removed."""
    if not text:
        return ""
    keep = []
    for sentence in re.split(r"(?<=[.!?;])\s+|\n+", text):
        if not HEALTH.search(sentence):
            keep.append(sentence)
            continue
        parts = [p for p in re.split(r",\s*|\s+(?:og|men)\s+", sentence) if p.strip() and not HEALTH.search(p)]
        if parts and len(parts) < len(re.split(r",\s*|\s+(?:og|men)\s+", sentence)):
            keep.append(", ".join(parts).strip(" .,"))
    return " ".join(x.strip() for x in keep if x.strip()).strip(" .,;")


def set_goal(db: OrmSession, ws_id: uuid.UUID, goal: str) -> dict:
    return appdata.update(db, ws_id, ADDON, goal=kit.clean(without_health(goal), 200) or None)


def plan(db: OrmSession, ws_id: uuid.UUID, workouts: list[dict], *, replace: bool = False) -> list[dict]:
    rows = [] if replace else kit.items(db, ws_id, ADDON)
    added = []
    for w in workouts[:14]:
        day = kit.key_of(str(w.get("day") or ""))
        day = next((d for d in DAYS if day.startswith(d[:3])), None)
        activity = kit.clean(without_health(str(w.get("activity") or "")), 60)
        if not day or not activity:
            raise ValidationFailed("Skriv dag og aktivitet, fx «tirsdag: løb 30 min»", field_errors=[{"field": "day"}])
        row = {"id": kit.new_id(), "day": day, "activity": activity[:1].upper() + activity[1:],
               "time": kit.clean(w.get("time"), 10), "minutes": int(w["minutes"]) if str(w.get("minutes") or "").isdigit()
               and 0 < int(w["minutes"]) <= 600 else None}
        rows = [r for r in rows if not (r["day"] == day and kit.key_of(r["activity"]) == kit.key_of(activity))]
        rows.append(row)
        added.append(row)
    rows.sort(key=lambda r: (DAYS.index(r["day"]), r.get("time") or ""))
    kit.save_items(db, ws_id, ADDON, rows[:30])
    return added


def log(db: OrmSession, ws_id: uuid.UUID, *, activity: str, minutes: int | None = None, when=None) -> dict:
    activity = kit.clean(without_health(activity), 60)
    if not activity:
        raise ValidationFailed("Hvad trænede du?", field_errors=[{"field": "activity"}])
    d = kit.parse_date(when, "date") or _today().isoformat()
    entry = {"date": d, "activity": activity[:1].upper() + activity[1:],
             "minutes": int(minutes) if isinstance(minutes, int) and 0 < minutes <= 600 else None}
    data = appdata.get(db, ws_id, ADDON)
    entries = ([entry] + list(data.get("log", [])))[:KEEP_LOG]
    appdata.put(db, ws_id, ADDON, {**data, "log": entries})
    return entry


def week_tally(data: dict, monday: date) -> tuple[int, int, int]:
    """(workouts done, minutes, workouts planned) for the week starting `monday`."""
    end = monday + timedelta(days=7)
    done = [e for e in data.get("log", []) if monday.isoformat() <= e["date"] < end.isoformat()]
    return len(done), sum(e.get("minutes") or 0 for e in done), len(data.get("items", []))


def streak(data: dict, today: date) -> int:
    """Whole weeks in a row (before this one) where every planned workout was done."""
    planned = len(data.get("items", []))
    if not planned:
        return 0
    n, monday = 0, today - timedelta(days=today.weekday() + 7)
    while n < 52 and week_tally(data, monday)[0] >= planned:
        n += 1
        monday -= timedelta(days=7)
    return n


def line(r: dict) -> str:
    bits = [f"{r['day'].capitalize()}: {r['activity']}"]
    if r.get("time"):
        bits.append(f"kl. {r['time']}")
    if r.get("minutes"):
        bits.append(f"{r['minutes']} min")
    return " ".join(bits)


def status_text(data: dict, today: date | None = None) -> str:
    today = today or _today()
    monday = today - timedelta(days=today.weekday())
    n, mins, planned = week_tally(data, monday)
    lines = [f"Mål: {data['goal']}" if data.get("goal") else "Intet mål endnu."]
    lines.append(f"Denne uge: {n} træninger{f' ({mins} min)' if mins else ''}" + (f" af {planned} planlagte." if planned else "."))
    if (s := streak(data, today)) >= 2:
        lines[-1] += f" {s} uger i træk med hele planen!"
    lines += [f"- {line(r)}" for r in data.get("items", [])]
    return "\n".join(lines)


def overview(db: OrmSession, ws_id: uuid.UUID) -> dict:
    data = appdata.get(db, ws_id, ADDON)
    rows = data.get("items", [])
    summary = status_text(data).split("\n")[:2]
    return {"summary": " ".join(summary) if (rows or data.get("goal") or data.get("log")) else
            "Ingen træning planlagt. Sig fx «Jeg vil løbe tirsdag og torsdag kl. 17 og styrketræne lørdag».",
            "items": [{"id": r["id"], "text": f"{r['day'].capitalize()}: {r['activity']}",
                       "sub": line(r).split(": ", 1)[1]} for r in rows],
            "partner": brand.offer("fitness")}


def remove(db: OrmSession, ws_id: uuid.UUID, item_id: str) -> bool:
    return kit.remove_item(db, ws_id, ADDON, item_id)


def due(data: dict, today: date) -> list[tuple[str, str]]:
    out = []
    todays = [r for r in data.get("items", []) if r["day"] == DAYS[today.weekday()]]
    logged = {kit.key_of(e["activity"]) for e in data.get("log", []) if e["date"] == today.isoformat()}
    todo = [r for r in todays if kit.key_of(r["activity"]) not in logged]
    if todo:
        out.append((f"day:{today.isoformat()}", "I dag: " + ", ".join(line(r).split(": ", 1)[1] for r in todo)
                    + ". Sig «færdig med …» bagefter, så noterer jeg det."))
    if today.weekday() == 0 and data.get("items"):
        n, mins, planned = week_tally(data, today - timedelta(days=7))
        out.append((f"week:{today.isoformat()}", f"Sidste uge: {n} af {planned} træninger"
                    f"{f', {mins} minutter' if mins else ''}. " + ("Flot!" if n >= planned else "Ny uge, nye chancer.")))
    return out

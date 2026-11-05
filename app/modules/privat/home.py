"""The Hus & vedligehold app: the small jobs a home needs every year, before they become big ones.

Saved (`private_app_data` «hus-og-vedligehold», `items`): maintenance jobs (from the list below or the user's own),
each with «every N months» and the next date. Reminder on the date; «done» moves it on by N months. A job that needs a
tradesperson goes through Håndværker & tilbud (a referral = lead revenue). Revenue: a disclosed partner link for home
products/services (brand.offer("hjem")), if configured.
"""
from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy.orm import Session as OrmSession

from app.core.errors import ValidationFailed
from app.modules.privat import app_kit as kit
from app.modules.privat import brand

ADDON, PATH = "hus-og-vedligehold", "/privat/apps/hus-og-vedligehold"


def _today() -> date:
    from app.modules.privat import rules

    return rules.local().date()
# (name, every N months, month it is best done in or None, a tradesperson to ask for – None = do it yourself)
STANDARD = (
    ("Test røgalarmerne", 3, None, None),
    ("Rens emhættens filter", 3, None, None),
    ("Rens afløb og vandlåse", 6, None, None),
    ("Skift filter i ventilationen", 6, None, None),
    ("Rens tagrenderne", 12, 11, "tagdækker"),
    ("Service på fyr eller varmepumpe", 12, 9, "VVS"),
    ("Skorstensfejning", 12, None, None),
    ("Tjek tag og fuger", 12, 4, "tømrer"),
    ("Luk for udendørs vandhaner", 12, 11, None),
)


def _next(today: date, month: int | None) -> date:
    """The first date: today, or the 1st of the job's best month – never in the past (this month = today)."""
    if month is None or month == today.month:
        return today
    d = date(today.year, month, 1)
    return d if d > today else date(today.year + 1, month, 1)


# The house profile decides which standard jobs «alle» means: no boiler service with district heating, no gutters in a flat.
NOT_FOR = {"Service på fyr eller varmepumpe": lambda p: p.get("heating") in ("fjernvarme", "elvarme"),
           "Skorstensfejning": lambda p: p.get("chimney") is False,
           "Rens tagrenderne": lambda p: p.get("home") == "lejlighed",
           "Tjek tag og fuger": lambda p: p.get("home") == "lejlighed",
           "Luk for udendørs vandhaner": lambda p: p.get("home") == "lejlighed"}
HEATING = ("fyr", "varmepumpe", "fjernvarme", "elvarme")


def save_profile(db: OrmSession, ws_id: uuid.UUID, *, home: str | None = None, heating: str | None = None,
                 chimney: bool | None = None) -> dict:
    from app.modules.privat import appdata

    data = appdata.get(db, ws_id, ADDON)
    prof = dict(data.get("profile") or {})
    if home in ("hus", "lejlighed", "rækkehus", "sommerhus"):
        prof["home"] = home
    if heating in HEATING:
        prof["heating"] = heating
    if isinstance(chimney, bool):
        prof["chimney"] = chimney
    appdata.put(db, ws_id, ADDON, {**data, "profile": prof})
    return prof


def add(db: OrmSession, ws_id: uuid.UUID, *, names: list[str] | None = None, custom: str | None = None,
        every_months: int | None = None, next_due=None, today: date | None = None) -> list[dict]:
    """Standard jobs by name (or «alle» – those that fit the house profile), or one custom job. Returns the jobs added."""
    from app.modules.privat import appdata

    today = today or _today()
    rows = kit.items(db, ws_id, ADDON)
    prof = appdata.get(db, ws_id, ADDON).get("profile") or {}
    added = []
    wanted = [kit.key_of(n) for n in names or []]
    for name, every, month, trade in STANDARD:
        fits = not NOT_FOR.get(name, lambda p: False)(prof)
        if (("alle" in wanted and fits) or any(w and w != "alle" and (w in kit.key_of(name) or kit.key_of(name) in w)
                                                for w in wanted)) and kit.find(rows, name) is None:
            added.append({"id": kit.new_id(), "name": name, "every": every, "next": _next(today, month).isoformat(),
                          **({"trade": trade} if trade else {})})
    if custom:
        name = kit.clean(custom, 100)
        if not every_months:
            raise ValidationFailed("Hvor tit skal det gøres?", field_errors=[{"field": "every_months"}])
        if kit.find(rows, name) is None:
            added.append({"id": kit.new_id(), "name": name[:1].upper() + name[1:],
                          "every": max(1, min(int(every_months), 120)),
                          "next": kit.parse_date(next_due, "next_due") or today.isoformat()})
    kit.save_items(db, ws_id, ADDON, (rows + added)[:60])
    return added


def mark_done(db: OrmSession, ws_id: uuid.UUID, name: str, today: date | None = None) -> dict | None:
    today = today or _today()
    rows = kit.items(db, ws_id, ADDON)
    job = kit.find(rows, name)
    if job is None:
        return None
    job["next"] = kit.add_months(today, job["every"]).isoformat()
    job["last"] = today.isoformat()
    kit.save_items(db, ws_id, ADDON, rows)
    return job


def line(j: dict) -> str:
    return f"{j['name']}: næste gang {kit.date_text(j['next'])} (hver {j['every']}. måned)" if j["every"] > 1 else \
        f"{j['name']}: næste gang {kit.date_text(j['next'])} (hver måned)"


def overview(db: OrmSession, ws_id: uuid.UUID) -> dict:
    rows = sorted(kit.items(db, ws_id, ADDON), key=lambda j: j["next"])
    return {"summary": f"{len(rows)} faste opgaver i hjemmet." if rows else
            "Ingen opgaver endnu. Sig «Tilføj alle de faste opgaver i huset» – eller vælg dem, I har brug for.",
            "items": [{"id": j["id"], "text": j["name"], "sub": line(j).split(": ", 1)[1]} for j in rows],
            "partner": brand.offer("hjem")}


def remove(db: OrmSession, ws_id: uuid.UUID, item_id: str) -> bool:
    return kit.remove_item(db, ws_id, ADDON, item_id)


def due(data: dict, today: date) -> list[tuple[str, str]]:
    out = []
    for j in data.get("items", []):
        if 0 <= (today - date.fromisoformat(j["next"])).days <= 7:   # on the day, or a few days late
            help_ = f" Skal jeg finde en {j['trade']} og hente tilbud?" if j.get("trade") else " Sig «færdig», når det er gjort."
            out.append((f"{j['id']}:{j['next']}", f"Tid til: {j['name']}.{help_}"))
    return out

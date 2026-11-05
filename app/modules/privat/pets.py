"""The Kæledyr app: the pets, the vet, and the dates that are easy to forget.

Saved (`private_app_data` «kaeledyr»): pets (name, kind, next vaccination, worming/flea treatment every N months from
a date, insurance renewal) and the vet's name and the number the user typed. Reminders: 14 days before a vaccination
and the insurance renewal, on the day for worming/flea treatment. Booking the vet = an ordinary call proposal (app
«Ring for mig», which this app needs) – never dialled before the user approves. Revenue: a disclosed partner link for
pet insurance (brand.offer("dyreforsikring")), if configured.
"""
from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy.orm import Session as OrmSession

from app.core.errors import ValidationFailed
from app.modules.privat import app_kit as kit
from app.modules.privat import appdata, brand

ADDON, PATH = "kaeledyr", "/privat/apps/kaeledyr"


def _today() -> date:
    from app.modules.privat import rules

    return rules.local().date()
WARN_DAYS = 14
EVERY = {"worming": "ormekur", "flea": "loppemiddel"}


def save_pet(db: OrmSession, ws_id: uuid.UUID, *, name: str, kind: str = "", vaccination_due=None,
             insurance_renews=None, worming_every_months: int | None = None, flea_every_months: int | None = None,
             last_treatment=None) -> dict:
    name = kit.clean(name, 40)
    if not name:
        raise ValidationFailed("Hvad hedder dyret?", field_errors=[{"field": "name"}])
    rows = kit.items(db, ws_id, ADDON)
    p = kit.find(rows, name)
    if p is None:
        p = {"id": kit.new_id(), "name": name[:1].upper() + name[1:], "kind": ""}
        rows.append(p)
    if kind:
        p["kind"] = kit.clean(kind, 30).lower()
    for k, v in (("vaccination_due", vaccination_due), ("insurance_renews", insurance_renews)):
        if (d := kit.parse_date(v, k)):
            p[k] = d
    start = kit.parse_date(last_treatment, "last_treatment") or _today().isoformat()
    for k, months in (("worming", worming_every_months), ("flea", flea_every_months)):
        if months:
            p[k] = {"every": max(1, min(int(months), 24)), "from": start}
    kit.save_items(db, ws_id, ADDON, rows[:20])
    return p


def save_vet(db: OrmSession, ws_id: uuid.UUID, *, name: str, phone_e164: str) -> dict:
    return appdata.update(db, ws_id, ADDON, vet={"name": kit.clean(name, 120), "phone": phone_e164})


def vet(db: OrmSession, ws_id: uuid.UUID) -> dict | None:
    return appdata.get(db, ws_id, ADDON).get("vet")


def next_treatment(t: dict, today: date) -> date:
    d = date.fromisoformat(t["from"])
    while d < today:
        d = kit.add_months(d, t["every"])
    return d


def line(p: dict, today: date | None = None) -> str:
    today = today or _today()
    bits = [p["name"] + (f" ({p['kind']})" if p.get("kind") else "")]
    if p.get("vaccination_due"):
        bits.append(f"vaccination {kit.date_text(p['vaccination_due'])}")
    for k, label in EVERY.items():
        if p.get(k):
            bits.append(f"{label} {kit.date_text(next_treatment(p[k], today).isoformat())}")
    if p.get("insurance_renews"):
        bits.append(f"forsikring fornyes {kit.date_text(p['insurance_renews'])}")
    return ", ".join(bits)


def overview(db: OrmSession, ws_id: uuid.UUID) -> dict:
    rows = kit.items(db, ws_id, ADDON)
    v = vet(db, ws_id)
    from app.modules.privat import rules

    summary = (f"{len(rows)} dyr." if rows else "Ingen dyr gemt endnu. Sig fx «Vores hund Bella skal vaccineres "
                                                "1. marts og have ormekur hver 3. måned».")
    if v:
        summary += f" Dyrlæge: {v['name']}, {rules.phone_display(v['phone'])}."
    return {"summary": summary, "items": [{"id": p["id"], "text": p["name"], "sub": line(p)} for p in rows],
            "partner": brand.offer("dyreforsikring")}


def remove(db: OrmSession, ws_id: uuid.UUID, item_id: str) -> bool:
    return kit.remove_item(db, ws_id, ADDON, item_id)


def due(data: dict, today: date) -> list[tuple[str, str]]:
    out = []
    for p in data.get("items", []):
        for k, label in (("vaccination_due", "skal vaccineres"), ("insurance_renews", "har forsikring, der fornyes")):
            if p.get(k) and 0 <= (date.fromisoformat(p[k]) - today).days <= WARN_DAYS:
                out.append((f"{k}:{p['id']}:{p[k]}", f"{p['name']} {label} {kit.date_text(p[k])}."
                            + (" Skal jeg ringe til dyrlægen og finde en tid?" if k == "vaccination_due" else "")))
        for k, label in EVERY.items():
            if p.get(k) and next_treatment(p[k], today) == today:
                out.append((f"{k}:{p['id']}:{today.isoformat()}", f"I dag skal {p['name']} have {label}."))
    return out

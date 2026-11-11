"""The Bil & syn app: the car's inspection and service dates, reminders, and calls to the workshop.

Saved (`private_app_data` «bil-og-syn»): the number plate, the next inspection (syn) and service dates as the user
gives them (no register lookup), whether to be reminded about tyres, and the workshop's name and the number the user
typed. Reminders: inspection 30 days before, service 14 days before, winter tyres on 15 October and summer tyres on
25 March – each once (`reminded`), from 08:00, by push or e-mail. Booking is an ordinary call proposal (app «Ring for
mig», which this app needs): nothing is dialled before the user approves.
"""
from __future__ import annotations

import re
import uuid
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from app.config import get_settings
from app.core.errors import ValidationFailed
from app.models import PrivateAddonEnabled, PrivateAppData, PrivateProfile, User
from app.modules.privat import addons, appdata, rules

ADDON = "bil-og-syn"
INSPECTION_DAYS, SERVICE_DAYS = 30, 14
TYRES = (("vinter", 10, 15, "Tid til vinterdæk – book skiftet, før frosten kommer."),
         ("sommer", 3, 25, "Tid til sommerdæk – book skiftet hos værkstedet."))
MONTH_NAMES = ("januar", "februar", "marts", "april", "maj", "juni", "juli", "august", "september", "oktober",
               "november", "december")


def plate_ok(plate: str) -> str | None:
    p = re.sub(r"\s+", "", plate or "").upper()
    return p if re.fullmatch(r"[A-ZÆØÅ0-9]{2,8}", p) else None


def _date(v: str | None, field: str) -> str | None:
    if not v:
        return None
    try:
        d = date.fromisoformat(str(v).strip()[:10])
    except ValueError as e:
        raise ValidationFailed("Datoen kunne ikke læses – brug fx 2027-05-14", field_errors=[{"field": field}]) from e
    return d.isoformat()


def get(db: OrmSession, ws_id: uuid.UUID) -> dict:
    return appdata.get(db, ws_id, ADDON)


def save_car(db: OrmSession, ws_id: uuid.UUID, *, plate: str | None = None, inspection_due: str | None = None,
             service_due: str | None = None, tire_reminders: bool | None = None) -> dict:
    data = get(db, ws_id)
    if plate is not None:
        p = plate_ok(plate)
        if p is None:
            raise ValidationFailed("Nummerpladen kunne ikke læses", field_errors=[{"field": "plate"}])
        data["plate"] = p
    for k, v in (("inspection_due", inspection_due), ("service_due", service_due)):
        d = _date(v, k)
        if d is not None:
            if data.get(k) != d:
                data.setdefault("reminded", {}).pop(k, None)
            data[k] = d
    if tire_reminders is not None:
        data["tire_reminders"] = bool(tire_reminders)
    return appdata.put(db, ws_id, ADDON, data)


def save_workshop(db: OrmSession, ws_id: uuid.UUID, *, name: str, phone_e164: str) -> dict:
    return appdata.update(db, ws_id, ADDON, workshop={"name": " ".join(name.split())[:200], "phone": phone_e164})


def date_text(iso: str) -> str:
    d = date.fromisoformat(iso)
    return f"{d.day}. {MONTH_NAMES[d.month - 1]} {d.year}"


def status_text(data: dict) -> str:
    if not data:
        return "Der er ikke gemt nogen bil endnu."
    parts = []
    if data.get("plate"):
        parts.append(f"Bil: {data['plate']}")
    if data.get("inspection_due"):
        parts.append(f"næste syn {date_text(data['inspection_due'])}")
    if data.get("service_due"):
        parts.append(f"service {date_text(data['service_due'])}")
    if data.get("workshop"):
        parts.append(f"værksted: {data['workshop']['name']}")
    if data.get("tire_reminders"):
        parts.append("påmindelse om dækskifte")
    return ", ".join(parts) + "."


def due_reminders(data: dict, today: date) -> list[tuple[str, str]]:
    """[(reminded-key, text)] that are due today and not sent yet."""
    out, reminded = [], data.get("reminded") or {}
    for key, days, label in (("inspection_due", INSPECTION_DAYS, "syn"), ("service_due", SERVICE_DAYS, "service")):
        if data.get(key):
            d = date.fromisoformat(data[key])
            left = (d - today).days
            if 0 <= left <= days and reminded.get(key) != data[key]:
                plate = f" ({data['plate']})" if data.get("plate") else ""
                out.append((key, f"Bilen{plate} skal til {label} {date_text(data[key])} – om {left} dage. "
                                 "Skal jeg ringe til værkstedet og finde en tid?"))
    if data.get("tire_reminders"):
        for name, month, day, text in TYRES:
            when = date(today.year, month, day)
            tag = f"tyres:{name}:{today.year}"
            if 0 <= (today - when).days <= 14 and reminded.get(tag) != "sent":
                out.append((tag, text))
    return out


def send_due(db: OrmSession, now: datetime | None = None) -> int:
    from app.modules.integrations import email_templates as tpl
    from app.modules.integrations import privat_mails
    from app.modules.privat import push

    if addons.CATALOG.get(ADDON) is None or addons.CATALOG[ADDON].live_status == "coming_soon":
        return 0
    local = rules.local(now)
    if local.hour < 8:
        return 0
    today = local.date()
    url = f"{get_settings().frontend_base_url.rstrip('/')}/privat/bil"
    rows = list(db.scalars(select(PrivateAppData).join(
        PrivateAddonEnabled, (PrivateAddonEnabled.workspace_id == PrivateAppData.workspace_id)
        & (PrivateAddonEnabled.key == ADDON)).where(PrivateAppData.app_key == ADDON)))
    n = 0
    for row in rows:
        data = dict(row.data)
        due = due_reminders(data, today)
        if not due:
            continue
        owner = db.scalar(select(User).join(PrivateProfile, PrivateProfile.user_id == User.id)
                          .where(PrivateProfile.workspace_id == row.workspace_id))
        reminded = dict(data.get("reminded") or {})
        for key, text in due:
            reminded[key] = data[key] if key in ("inspection_due", "service_due") else "sent"
            if owner is None:
                continue
            mail = privat_mails.car(text, url, owner.interface_language)
            push.notify(db, owner.id, title="Bilen", body=text, url=url, dedupe=f"car:{row.workspace_id}:{key}:{reminded[key]}",
                        email={"to_email": owner.email, "email": tpl.to_payload(mail)}, workspace_id=row.workspace_id)
            n += 1
        appdata.put(db, row.workspace_id, ADDON, {**data, "reminded": reminded})
    return n

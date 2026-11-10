"""Shared plumbing for the household apps (Abonnementer, Håndværker & tilbud, Fælles udgifter, Garanti & kvitteringer,
Fest & invitationer, Flytning, Kæledyr, Hus & vedligehold, Fitness & sundhed).

Each app is one module with `ADDON`, `PATH` (its page under /privat), `overview(db, ws_id) -> dict` and
`remove(db, ws_id, item_id) -> bool`; apps with reminders also have `due(data, today) -> [(tag, text)]`. The data lives in
`private_app_data` under the app key, as a list of items with an `id`. This module gives them: ids, dates and money,
the generic overview endpoint, and ONE reminder sender (each tag once, from 08:00, push or e-mail).
"""
from __future__ import annotations

import importlib
import re
import uuid
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from app.config import get_settings
from app.core.errors import NotFound, ValidationFailed
from app.models import PrivateAddonEnabled, PrivateAppData, PrivateProfile, User
from app.modules.privat import addons, appdata, rules

MODULES = {
    "abonnementer": "app.modules.privat.subs_app",
    "haandvaerker": "app.modules.privat.quotes",
    "faelles-udgifter": "app.modules.privat.expenses",
    "garanti": "app.modules.privat.warranty",
    "fest": "app.modules.privat.party",
    "flytning": "app.modules.privat.moving",
    "kaeledyr": "app.modules.privat.pets",
    "hus-og-vedligehold": "app.modules.privat.home",
    "fitness-og-sundhed": "app.modules.privat.fitness",
}
MONTHS = ("januar", "februar", "marts", "april", "maj", "juni", "juli", "august", "september", "oktober", "november",
          "december")


def module(key: str):
    if key not in MODULES:
        raise NotFound("Appen findes ikke")
    return importlib.import_module(MODULES[key])


def new_id() -> str:
    return uuid.uuid4().hex[:10]


def clean(s, n: int = 200) -> str:
    return " ".join(str(s or "").split())[:n]


def key_of(s: str) -> str:
    return re.sub(r"[^a-zæøå0-9]+", " ", (s or "").lower()).strip()


def parse_date(v, field: str = "date", *, required: bool = False) -> str | None:
    if not v:
        if required:
            raise ValidationFailed("Datoen mangler – skriv fx 2027-05-14", field_errors=[{"field": field}])
        return None
    try:
        return date.fromisoformat(str(v).strip()[:10]).isoformat()
    except ValueError as e:
        raise ValidationFailed("Datoen kunne ikke læses – brug fx 2027-05-14", field_errors=[{"field": field}]) from e


def date_text(iso: str | None) -> str:
    if not iso:
        return ""
    d = date.fromisoformat(iso)
    return f"{d.day}. {MONTHS[d.month - 1]} {d.year}"


def add_months(d: date, n: int) -> date:
    import calendar

    m = d.month - 1 + n
    y, m = d.year + m // 12, m % 12 + 1
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def money(minor: int | None) -> str:
    from app.modules.privat.bills import money as _m

    return _m(minor)


def amount(v, field: str = "amount", *, required: bool = False) -> int | None:
    from app.modules.privat.bills import parse_amount

    if v in (None, "") and not required:
        return None
    m = parse_amount(v)
    if m is None:
        raise ValidationFailed("Beløbet kunne ikke læses – skriv fx 129 kr.", field_errors=[{"field": field}])
    return m


def items(db: OrmSession, ws_id: uuid.UUID, key: str, name: str = "items") -> list[dict]:
    return list(appdata.get(db, ws_id, key).get(name, []))


def save_items(db: OrmSession, ws_id: uuid.UUID, key: str, rows: list[dict], name: str = "items") -> list[dict]:
    data = appdata.get(db, ws_id, key)
    appdata.put(db, ws_id, key, {**data, name: rows})
    return rows


def remove_item(db: OrmSession, ws_id: uuid.UUID, key: str, item_id: str, name: str = "items") -> bool:
    rows = items(db, ws_id, key, name)
    keep = [r for r in rows if r.get("id") != item_id]
    if len(keep) == len(rows):
        return False
    save_items(db, ws_id, key, keep, name)
    return True


def find(rows: list[dict], wanted: str, field: str = "name", *, exact: bool = False) -> dict | None:
    """The row named `wanted`. Looking something up (`exact=False`) also accepts a part of the name («Mis» → «Misser»);
    saving/creating must use `exact=True`, or a new «Mis» would overwrite «Misser» (F-PB-01)."""
    w = key_of(wanted)
    if not w:
        return None
    hit = next((r for r in rows if key_of(r.get(field, "")) == w), None)
    if hit is not None or exact:
        return hit
    return next((r for r in rows if w in key_of(r.get(field, "")) or key_of(r.get(field, "")) in w), None)


# --------------------------------------------------------------------------- reminders

def send_due(db: OrmSession, now: datetime | None = None) -> int:
    """Every household app's reminders: `due(data, today)` gives (tag, text); each tag is sent once (`reminded`)."""
    from app.modules.integrations import email_templates as tpl
    from app.modules.privat import push

    local = rules.local(now)
    if local.hour < 8:
        return 0
    today, n = local.date(), 0
    base = get_settings().frontend_base_url.rstrip("/")
    for key, path in MODULES.items():
        mod = importlib.import_module(path)
        a = addons.CATALOG.get(key)
        if not hasattr(mod, "due") or a is None or a.live_status == "coming_soon":
            continue
        rows = list(db.scalars(select(PrivateAppData).join(
            PrivateAddonEnabled, (PrivateAddonEnabled.workspace_id == PrivateAppData.workspace_id)
            & (PrivateAddonEnabled.key == key)).where(PrivateAppData.app_key == key)))
        rows = addons.running_rows(db, rows, key)  # a plan app whose plan has lapsed sends nothing (PC-ENT-02)
        for row in rows:
            data = dict(row.data)
            reminded = dict(data.get("reminded") or {})
            due = [(t, x) for t, x in mod.due(data, today) if t not in reminded]
            if not due:
                continue
            owner = db.scalar(select(User).join(PrivateProfile, PrivateProfile.user_id == User.id)
                              .where(PrivateProfile.workspace_id == row.workspace_id))
            url = f"{base}{mod.PATH}"
            for tag, text in due:
                reminded[tag] = today.isoformat()
                if owner is None:
                    continue
                mail = tpl.Email(subject=a.name, heading=text, paragraphs=[], button_label=f"Åbn {a.name}",
                                 button_url=url,
                                 footer_reason=f"Du får denne e-mail, fordi du har slået {a.name} til i Dialogbot.")
                push.notify(db, owner.id, title=a.name, body=text, url=url, dedupe=f"{key}:{row.workspace_id}:{tag}",
                            email={"to_email": owner.email, "email": tpl.to_payload(mail)}, workspace_id=row.workspace_id)
                n += 1
            # keep the newest 300 tags so the JSON does not grow forever
            appdata.put(db, row.workspace_id, key, {**data, "reminded": dict(list(reminded.items())[-300:])})
    return n

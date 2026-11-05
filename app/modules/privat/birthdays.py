"""The Fødselsdage app of Dialogbot Privat: birthdays the user tells the assistant, and a reminder once a year.

Only what the user gives is stored: a name, a day and month, and the year when they say it (then the reminder says how
old the person turns). The reminder comes `remind_days_before` days before (0 = on the day), at the earliest at 08:00
Copenhagen time, by push or – without a push subscription – e-mail; `last_reminded_for` makes it once per birthday,
also when the worker was down for a while (a missed reminder still comes, up to the day itself). 29 February is
reminded on 28 February in other years.
"""
from __future__ import annotations

import re
import uuid
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from app.config import get_settings
from app.core.errors import NotFound, ValidationFailed
from app.models import PrivateAddonEnabled, PrivateBirthday, PrivateProfile, User
from app.modules.privat import addons, rules

ADDON = "foedselsdage"
DEFAULT_DAYS = 7
REMIND_FROM_HOUR = 8
MAX_PER_ACCOUNT = 500

MONTHS = {"januar": 1, "jan": 1, "februar": 2, "feb": 2, "marts": 3, "mar": 3, "april": 4, "apr": 4, "maj": 5,
          "juni": 6, "jun": 6, "juli": 7, "jul": 7, "august": 8, "aug": 8, "september": 9, "sep": 9, "sept": 9,
          "oktober": 10, "okt": 10, "november": 11, "nov": 11, "december": 12, "dec": 12}
MONTH_NAMES = ("januar", "februar", "marts", "april", "maj", "juni", "juli", "august", "september", "oktober",
               "november", "december")
_MONTH_RX = "|".join(sorted(MONTHS, key=len, reverse=True))


# --------------------------------------------------------------------------- dates

def _valid(month: int, day: int, year: int | None) -> bool:
    try:
        date(year or 2000, month, day)   # 2000 is a leap year: 29 February is a valid birthday
    except ValueError:
        return False
    return year is None or 1900 <= year <= rules.local().year


def parse_date(text: str | None) -> tuple[int, int, int | None] | None:
    """(month, day, year or None) from «14. marts», «14/3», «14.03.1946», «1946-03-14», «03-14». None if unclear."""
    low = (text or "").strip().lower()
    if not low:
        return None
    m = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", low)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        return (mo, d, y) if _valid(mo, d, y) else None
    m = re.fullmatch(r"(?:--)?(\d{1,2})-(\d{1,2})", low)
    if m:
        mo, d = int(m.group(1)), int(m.group(2))
        return (mo, d, None) if _valid(mo, d, None) else None
    m = re.search(r"\b(\d{1,2})\s*[./]\s*(\d{1,2})(?:\s*[./-]\s*(\d{4}))?\b", low)
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3)) if m.group(3) else None
        return (mo, d, y) if _valid(mo, d, y) else None
    m = re.search(rf"\b(\d{{1,2}})\.?\s*({_MONTH_RX})\.?(?:\s+(\d{{4}}))?\b", low)
    if m:
        d, mo, y = int(m.group(1)), MONTHS[m.group(2)], int(m.group(3)) if m.group(3) else None
        return (mo, d, y) if _valid(mo, d, y) else None
    return None


def _on(year: int, month: int, day: int) -> date:
    try:
        return date(year, month, day)
    except ValueError:              # 29 February in a year that has none
        return date(year, month, day - 1)


def next_date(b: PrivateBirthday, today: date) -> date:
    d = _on(today.year, b.month, b.day)
    return d if d >= today else _on(today.year + 1, b.month, b.day)


def turns(b: PrivateBirthday, on: date) -> int | None:
    return on.year - b.year if b.year else None


def date_text(b: PrivateBirthday) -> str:
    return f"{b.day}. {MONTH_NAMES[b.month - 1]}" + (f" {b.year}" if b.year else "")


def _key(name: str) -> str:
    return " ".join(name.lower().split())[:100]


# --------------------------------------------------------------------------- storing

def enabled(db: OrmSession, ws_id: uuid.UUID) -> bool:
    return addons.is_enabled(db, ws_id, ADDON)


def all_for(db: OrmSession, ws_id: uuid.UUID) -> list[PrivateBirthday]:
    rows = list(db.scalars(select(PrivateBirthday).where(PrivateBirthday.workspace_id == ws_id)))
    today = rules.local().date()
    return sorted(rows, key=lambda b: (next_date(b, today), b.name_key))


def save(db: OrmSession, ws_id: uuid.UUID, *, name: str, when: str, remind_days_before: int | None = None
         ) -> tuple[PrivateBirthday, bool]:
    """Add the birthday, or change the date of the person already there (same name). Returns (row, created)."""
    name = " ".join((name or "").split())[:100]
    if not name:
        raise ValidationFailed("Hvem har fødselsdag?", field_errors=[{"field": "name"}])
    parsed = parse_date(when)
    if parsed is None:
        raise ValidationFailed("Datoen kunne ikke læses – skriv fx 14. marts eller 14.03.1946",
                               field_errors=[{"field": "date"}])
    month, day, year = parsed
    if remind_days_before is not None and not 0 <= remind_days_before <= 60:
        raise ValidationFailed("Vælg mellem 0 og 60 dage før", field_errors=[{"field": "remind_days_before"}])
    b = db.scalar(select(PrivateBirthday).where(PrivateBirthday.workspace_id == ws_id,
                                                PrivateBirthday.name_key == _key(name)).with_for_update())
    created = b is None
    if created:
        n = db.query(PrivateBirthday).filter_by(workspace_id=ws_id).count()
        if n >= MAX_PER_ACCOUNT:
            raise ValidationFailed(f"Du kan højst gemme {MAX_PER_ACCOUNT} fødselsdage")
        b = PrivateBirthday(workspace_id=ws_id, name=name, name_key=_key(name), month=month, day=day, year=year,
                            remind_days_before=DEFAULT_DAYS if remind_days_before is None else remind_days_before)
        db.add(b)
    else:
        if (b.month, b.day) != (month, day):
            b.last_reminded_for = None      # a new date: the next reminder is for the new one
        b.name, b.month, b.day = name, month, day
        if year is not None:
            b.year = year
        if remind_days_before is not None:
            b.remind_days_before = remind_days_before
        b.updated_at = rules.now()
    db.flush()
    return b, created


def own(db: OrmSession, ws_id: uuid.UUID, birthday_id: uuid.UUID) -> PrivateBirthday:
    b = db.get(PrivateBirthday, birthday_id)
    if b is None or b.workspace_id != ws_id:
        raise NotFound("Fødselsdagen findes ikke")
    return b


def find(db: OrmSession, ws_id: uuid.UUID, name: str) -> PrivateBirthday | None:
    return db.scalar(select(PrivateBirthday).where(PrivateBirthday.workspace_id == ws_id,
                                                   PrivateBirthday.name_key == _key(name)))


def set_days(db: OrmSession, b: PrivateBirthday, days: int) -> PrivateBirthday:
    if not 0 <= days <= 60:
        raise ValidationFailed("Vælg mellem 0 og 60 dage før", field_errors=[{"field": "remind_days_before"}])
    b.remind_days_before, b.updated_at = days, rules.now()
    db.flush()
    return b


def remove(db: OrmSession, b: PrivateBirthday) -> None:
    db.delete(b)
    db.flush()


def _when(days: int) -> str:
    return "i dag" if days == 0 else "i morgen" if days == 1 else f"om {days} dage"


def out(b: PrivateBirthday, today: date | None = None) -> dict:
    today = today or rules.local().date()
    nxt = next_date(b, today)
    return {"id": str(b.id), "name": b.name, "month": b.month, "day": b.day, "year": b.year,
            "date_text": date_text(b), "next_date": nxt.isoformat(), "days_until": (nxt - today).days,
            "turns": turns(b, nxt), "remind_days_before": b.remind_days_before}


def summary(b: PrivateBirthday, today: date | None = None) -> str:
    """«Mor fylder 80 om 7 dage (lørdag 14. marts)» / «Ole har fødselsdag i dag»."""
    today = today or rules.local().date()
    nxt = next_date(b, today)
    age = turns(b, nxt)
    what = f"fylder {age}" if age else "har fødselsdag"
    when = _when((nxt - today).days)
    day_txt = f"{rules.WEEKDAYS[nxt.weekday()]} {nxt.day}. {MONTH_NAMES[nxt.month - 1]}"
    return f"{b.name} {what} {when}" + ("" if when == "i dag" else f" ({day_txt})")


# --------------------------------------------------------------------------- reminders

def due(db: OrmSession, now: datetime | None = None) -> list[PrivateBirthday]:
    """Birthdays whose reminder is due now, in accounts that have the app on."""
    local = rules.local(now)
    if local.hour < REMIND_FROM_HOUR:
        return []
    today = local.date()
    rows = db.scalars(select(PrivateBirthday).join(
        PrivateAddonEnabled, (PrivateAddonEnabled.workspace_id == PrivateBirthday.workspace_id)
        & (PrivateAddonEnabled.key == ADDON)))
    out_ = []
    for b in rows:
        nxt = next_date(b, today)
        if (nxt - today).days <= b.remind_days_before and b.last_reminded_for != nxt:
            out_.append(b)
    return out_


def send_due(db: OrmSession, now: datetime | None = None) -> int:
    """Worker schedule: one reminder per birthday per year (push, or e-mail without a push subscription)."""
    from app.modules.integrations import email_templates as tpl
    from app.modules.privat import push

    if addons.CATALOG.get(ADDON) is None or addons.CATALOG[ADDON].status == "coming_soon":
        return 0
    today = rules.local(now).date()
    url = f"{get_settings().frontend_base_url.rstrip('/')}/privat/foedselsdage"
    n = 0
    for b in due(db, now):
        owner = db.scalar(select(User).join(PrivateProfile, PrivateProfile.user_id == User.id)
                          .where(PrivateProfile.workspace_id == b.workspace_id))
        nxt = next_date(b, today)
        b.last_reminded_for = nxt
        if owner is None:
            continue
        text = summary(b, today) + "."
        mail = tpl.Email(subject=f"Fødselsdag: {b.name}", heading=text,
                         paragraphs=["Skriv til Peter, hvis du vil have idéer til en gave eller en påmindelse om at ringe."],
                         button_label="Se fødselsdage", button_url=url,
                         footer_reason="Du får denne e-mail, fordi du har slået Fødselsdage til i Dialogbot.")
        push.notify(db, owner.id, title="Fødselsdag", body=text, url=url, dedupe=f"birthday:{b.id}:{nxt.isoformat()}",
                    email={"to_email": owner.email, "email": tpl.to_payload(mail)}, workspace_id=b.workspace_id)
        n += 1
    db.flush()
    return n


def upcoming_text(db: OrmSession, ws_id: uuid.UUID, days: int = 45) -> str:
    """For the chat: the next birthdays within `days`, or a short answer that there are none."""
    today = rules.local().date()
    soon = [b for b in all_for(db, ws_id) if (next_date(b, today) - today).days <= days]
    if not soon:
        rows = all_for(db, ws_id)
        if not rows:
            return "Du har ikke gemt nogen fødselsdage endnu."
        return "Ingen fødselsdage de næste " + str(days) + " dage. Den næste: " + summary(rows[0], today) + "."
    return "\n".join(f"- {summary(b, today)}" for b in soon[:15])

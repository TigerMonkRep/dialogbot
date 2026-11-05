"""The Regninger app of Dialogbot Privat: bills the user tells the assistant about, reminded before they are due.

Only what the user gives is stored: a name, the amount when they say it, how often it comes and when it is due next.
Dialogbot never pays anything and never sees the bank. The reminder comes `remind_days_before` days before (0 = on the
day), at the earliest at 08:00 Copenhagen time, once per due date, by push or e-mail. When a due date has passed, a
recurring bill moves on to the next one (`anchor_day` keeps «the 31st» on the last day of shorter months); a one-off
bill stays until the user removes it.
"""
from __future__ import annotations

import calendar
import re
import uuid
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from app.config import get_settings
from app.core.errors import NotFound, ValidationFailed
from app.models import PrivateAddonEnabled, PrivateBill, PrivateProfile, User
from app.modules.privat import addons, rules

ADDON = "regninger"
DEFAULT_DAYS = 3
REMIND_FROM_HOUR = 8
MAX_PER_ACCOUNT = 200
FREQUENCIES = {"monthly": 1, "quarterly": 3, "half_yearly": 6, "yearly": 12, "once": 0}
FREQ_TEXT = {"monthly": "hver måned", "quarterly": "hvert kvartal", "half_yearly": "hvert halve år",
             "yearly": "hvert år", "once": "én gang"}
MONTH_NAMES = ("januar", "februar", "marts", "april", "maj", "juni", "juli", "august", "september", "oktober",
               "november", "december")


# --------------------------------------------------------------------------- amounts and dates

def parse_amount(text: str | int | float | None) -> int | None:
    """Øre from «640 kr.», «1.250,50», «1250.5», 640. None when there is no amount."""
    if text is None or text == "":
        return None
    if isinstance(text, int | float):
        return int(round(float(text) * 100)) if text >= 0 else None
    s = str(text).lower().replace("kr.", "").replace("kr", "").replace("dkk", "").replace(" ", "").strip()
    if not re.fullmatch(r"\d{1,3}(?:\.\d{3})*(?:,\d{1,2})?|\d+(?:[.,]\d{1,2})?", s):
        return None
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"\d{1,3}(?:\.\d{3})+", s):
        s = s.replace(".", "")
    return int(round(float(s) * 100))


def money(minor: int | None) -> str:
    if minor is None:
        return ""
    kr, ore = divmod(minor, 100)
    whole = f"{kr:,}".replace(",", ".")
    return f"{whole},{ore:02d} kr." if ore else f"{whole} kr."


def _on(year: int, month: int, day: int) -> date:
    return date(year, month, min(day, calendar.monthrange(year, month)[1]))


def _add_months(d: date, months: int, anchor: int) -> date:
    m = d.month - 1 + months
    return _on(d.year + m // 12, m % 12 + 1, anchor)


def first_due(today: date, *, due_date: str | None = None, due_day: int | None = None) -> tuple[date, int]:
    """(next due date, anchor day) from an ISO date or a day of the month («den 1.»). Raises ValidationFailed."""
    if due_date:
        try:
            d = date.fromisoformat(str(due_date).strip()[:10])
        except ValueError as e:
            raise ValidationFailed("Datoen kunne ikke læses", field_errors=[{"field": "due_date"}]) from e
        if (d - today).days < -31 or (d - today).days > 400:
            raise ValidationFailed("Datoen ligger for langt væk", field_errors=[{"field": "due_date"}])
        return d, d.day
    if due_day is not None and 1 <= int(due_day) <= 31:
        day = int(due_day)
        d = _on(today.year, today.month, day)
        if d < today:
            d = _add_months(d, 1, day)
        return d, day
    raise ValidationFailed("Hvornår skal regningen betales?", field_errors=[{"field": "due_date"}])


def roll(b: PrivateBill, today: date) -> bool:
    """Move a recurring bill whose due date has passed on to the next one. True if it moved."""
    step = FREQUENCIES[b.frequency]
    if not step or b.next_due >= today:
        return False
    nxt = b.next_due
    while nxt < today:
        nxt = _add_months(nxt, step, b.anchor_day)
    b.next_due = nxt
    return True


def _key(name: str) -> str:
    return " ".join(name.lower().split())[:100]


# --------------------------------------------------------------------------- storing

def enabled(db: OrmSession, ws_id: uuid.UUID) -> bool:
    return addons.is_enabled(db, ws_id, ADDON)


def all_for(db: OrmSession, ws_id: uuid.UUID) -> list[PrivateBill]:
    today = rules.local().date()
    rows = list(db.scalars(select(PrivateBill).where(PrivateBill.workspace_id == ws_id)))
    for b in rows:
        roll(b, today)
    return sorted(rows, key=lambda b: (b.next_due, b.name_key))


def save(db: OrmSession, ws_id: uuid.UUID, *, name: str, amount=None, frequency: str = "monthly",
         due_date: str | None = None, due_day: int | None = None, remind_days_before: int | None = None
         ) -> tuple[PrivateBill, bool]:
    """Add the bill, or change the one with the same name. Returns (row, created)."""
    name = " ".join((name or "").split())[:100]
    if not name:
        raise ValidationFailed("Hvilken regning?", field_errors=[{"field": "name"}])
    if frequency not in FREQUENCIES:
        raise ValidationFailed("Ukendt hyppighed", field_errors=[{"field": "frequency"}])
    if remind_days_before is not None and not 0 <= remind_days_before <= 30:
        raise ValidationFailed("Vælg mellem 0 og 30 dage før", field_errors=[{"field": "remind_days_before"}])
    minor = parse_amount(amount)
    if amount not in (None, "") and minor is None:
        raise ValidationFailed("Beløbet kunne ikke læses – skriv fx 640 kr.", field_errors=[{"field": "amount"}])
    today = rules.local().date()
    nxt, anchor = first_due(today, due_date=due_date, due_day=due_day)
    b = db.scalar(select(PrivateBill).where(PrivateBill.workspace_id == ws_id, PrivateBill.name_key == _key(name))
                  .with_for_update())
    created = b is None
    if created:
        if db.query(PrivateBill).filter_by(workspace_id=ws_id).count() >= MAX_PER_ACCOUNT:
            raise ValidationFailed(f"Du kan højst gemme {MAX_PER_ACCOUNT} regninger")
        b = PrivateBill(workspace_id=ws_id, name=name, name_key=_key(name), amount_minor=minor, frequency=frequency,
                        anchor_day=anchor, next_due=nxt,
                        remind_days_before=DEFAULT_DAYS if remind_days_before is None else remind_days_before)
        db.add(b)
    else:
        if b.next_due != nxt:
            b.last_reminded_for = None
        b.name, b.frequency, b.anchor_day, b.next_due = name, frequency, anchor, nxt
        if minor is not None:
            b.amount_minor = minor
        if remind_days_before is not None:
            b.remind_days_before = remind_days_before
        b.updated_at = rules.now()
    roll(b, today)
    db.flush()
    return b, created


def own(db: OrmSession, ws_id: uuid.UUID, bill_id: uuid.UUID) -> PrivateBill:
    b = db.get(PrivateBill, bill_id)
    if b is None or b.workspace_id != ws_id:
        raise NotFound("Regningen findes ikke")
    return b


def find(db: OrmSession, ws_id: uuid.UUID, name: str) -> PrivateBill | None:
    return db.scalar(select(PrivateBill).where(PrivateBill.workspace_id == ws_id, PrivateBill.name_key == _key(name)))


def set_days(db: OrmSession, b: PrivateBill, days: int) -> PrivateBill:
    if not 0 <= days <= 30:
        raise ValidationFailed("Vælg mellem 0 og 30 dage før", field_errors=[{"field": "remind_days_before"}])
    b.remind_days_before, b.updated_at = days, rules.now()
    db.flush()
    return b


def remove(db: OrmSession, b: PrivateBill) -> None:
    db.delete(b)
    db.flush()


def date_text(d: date) -> str:
    return f"{rules.WEEKDAYS[d.weekday()]} {d.day}. {MONTH_NAMES[d.month - 1]}"


def out(b: PrivateBill, today: date | None = None) -> dict:
    today = today or rules.local().date()
    return {"id": str(b.id), "name": b.name, "amount_minor": b.amount_minor, "amount_text": money(b.amount_minor),
            "frequency": b.frequency, "frequency_text": FREQ_TEXT[b.frequency], "next_due": b.next_due.isoformat(),
            "due_text": date_text(b.next_due), "days_until": (b.next_due - today).days,
            "remind_days_before": b.remind_days_before}


def _in_month(b: PrivateBill, year: int, month: int) -> list[date]:
    """The due dates of the bill in that month (0 or 1)."""
    step = FREQUENCIES[b.frequency]
    d = b.next_due
    if not step:
        return [d] if (d.year, d.month) == (year, month) else []
    while (d.year, d.month) < (year, month):
        d = _add_months(d, step, b.anchor_day)
    return [d] if (d.year, d.month) == (year, month) else []


def month_overview(db: OrmSession, ws_id: uuid.UUID, today: date | None = None) -> dict:
    """This month's bills (from the next due date on): items, total of the known amounts, and how many have none."""
    today = today or rules.local().date()
    rows = [(b, d) for b in all_for(db, ws_id) for d in _in_month(b, today.year, today.month)]
    rows.sort(key=lambda x: (x[1], x[0].name_key))
    total = sum(b.amount_minor or 0 for b, _ in rows)
    return {"month": f"{MONTH_NAMES[today.month - 1]} {today.year}", "total_minor": total, "total_text": money(total) or "0 kr.",
            "without_amount": sum(1 for b, _ in rows if b.amount_minor is None),
            "items": [{**out(b, today), "due_in_month": d.isoformat()} for b, d in rows]}


def overview_text(db: OrmSession, ws_id: uuid.UUID) -> str:
    ov = month_overview(db, ws_id)
    if not ov["items"]:
        rows = all_for(db, ws_id)
        if not rows:
            return "Du har ikke gemt nogen regninger endnu."
        b = rows[0]
        return f"Ingen regninger resten af {ov['month'].split()[0]}. Den næste: {b.name} {date_text(b.next_due)}."
    lines = [f"- {i['name']}: {i['due_text']}" + (f", {i['amount_text']}" if i["amount_text"] else "") for i in ov["items"]]
    tail = f"I alt {ov['total_text']}" + (f" (+ {ov['without_amount']} uden beløb)" if ov["without_amount"] else "")
    return f"Regninger i {ov['month']}:\n" + "\n".join(lines) + f"\n{tail.rstrip('.')}."


# --------------------------------------------------------------------------- reminders

def due(db: OrmSession, now: datetime | None = None) -> list[PrivateBill]:
    local = rules.local(now)
    if local.hour < REMIND_FROM_HOUR:
        return []
    today = local.date()
    rows = list(db.scalars(select(PrivateBill).join(
        PrivateAddonEnabled, (PrivateAddonEnabled.workspace_id == PrivateBill.workspace_id)
        & (PrivateAddonEnabled.key == ADDON))))
    out_ = []
    for b in rows:
        roll(b, today)
        if 0 <= (b.next_due - today).days <= b.remind_days_before and b.last_reminded_for != b.next_due:
            out_.append(b)
    return out_


def send_due(db: OrmSession, now: datetime | None = None) -> int:
    """Worker schedule: one reminder per due date (push, or e-mail without a push subscription)."""
    from app.modules.integrations import email_templates as tpl
    from app.modules.privat import push

    if addons.CATALOG.get(ADDON) is None or addons.CATALOG[ADDON].live_status == "coming_soon":
        return 0
    today = rules.local(now).date()
    url = f"{get_settings().frontend_base_url.rstrip('/')}/privat/regninger"
    n = 0
    for b in due(db, now):
        b.last_reminded_for = b.next_due
        owner = db.scalar(select(User).join(PrivateProfile, PrivateProfile.user_id == User.id)
                          .where(PrivateProfile.workspace_id == b.workspace_id))
        if owner is None:
            continue
        days = (b.next_due - today).days
        when = "i dag" if days == 0 else "i morgen" if days == 1 else f"om {days} dage"
        text = (f"{b.name} skal betales {when} ({date_text(b.next_due)})"
                + (f": {money(b.amount_minor)}" if b.amount_minor else "")).rstrip(".") + "."
        mail = tpl.Email(subject=f"Regning: {b.name}", heading=text,
                         paragraphs=["Dialogbot betaler aldrig selv og har ikke adgang til din bank."],
                         button_label="Se regninger", button_url=url,
                         footer_reason="Du får denne e-mail, fordi du har slået Regninger til i Dialogbot.")
        push.notify(db, owner.id, title="Regning", body=text, url=url, dedupe=f"bill:{b.id}:{b.next_due.isoformat()}",
                    email={"to_email": owner.email, "email": tpl.to_payload(mail)}, workspace_id=b.workspace_id)
        n += 1
    db.flush()
    return n

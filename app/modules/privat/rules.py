"""Clock, time zone and the small rules of Dialogbot Privat. `now()` is the only clock the module reads, so tests
replace it (monkeypatch rules.now) to land inside or outside calling hours or in another month."""
from __future__ import annotations

import re
from datetime import UTC, datetime, time
from zoneinfo import ZoneInfo

from app.modules.billing import prices

TZ = ZoneInfo("Europe/Copenhagen")
FREE_LIMIT = prices.PRIVAT_FREE_TASKS_PER_MONTH
WELCOME_BONUS_MINOR = prices.PRIVAT_WELCOME_BONUS_MINOR  # Opkaldssaldo amounts in øre (DKK; markets.privat_from_dkk)
EXTRA_TASK_MINOR = prices.PRIVAT_EXTRA_TASK_MINOR
SPONSOR_PER_DAY = 2
CALL_FROM, CALL_TO = time(8, 0), time(18, 0)  # weekdays, Copenhagen time
CALLBACK_DAYS = 14
INVITE_DAYS = 30
MONTHS = ("januar", "februar", "marts", "april", "maj", "juni", "juli", "august", "september", "oktober", "november",
          "december")
WEEKDAYS = ("mandag", "tirsdag", "onsdag", "torsdag", "fredag", "lørdag", "søndag")


def now() -> datetime:
    return datetime.now(UTC)


def local(dt: datetime | None = None) -> datetime:
    return (dt or now()).astimezone(TZ)


def month_key(dt: datetime | None = None) -> str:
    return local(dt).strftime("%Y-%m")


def month_name(dt: datetime | None = None) -> str:
    return MONTHS[local(dt).month - 1]


def in_call_hours(dt: datetime | None = None) -> bool:
    t = local(dt)
    return t.weekday() < 5 and CALL_FROM <= t.time() < CALL_TO


def when_text(dt: datetime, ref: datetime | None = None) -> str:
    """"I dag kl. 15.45", "I morgen kl. 9.00", "Fredag kl. 10.00", "12. november kl. 9.00"."""
    t, r = local(dt), local(ref)
    hm = f"kl. {t.hour}.{t.minute:02d}"
    days = (t.date() - r.date()).days
    if days == 0:
        return f"I dag {hm}"
    if days == 1:
        return f"I morgen {hm}"
    if 1 < days < 7:
        return f"{WEEKDAYS[t.weekday()].capitalize()} {hm}"
    return f"{t.day}. {MONTHS[t.month - 1]} {hm}"


def lower_first(s: str) -> str:
    return s[:1].lower() + s[1:] if s else s


def phone_display(e164: str | None) -> str | None:
    """+4586123456 → "86 12 34 56"; other countries are shown as stored."""
    if not e164:
        return None
    d = re.sub(r"\D", "", e164)
    if e164.startswith("+45") and len(d) == 10:
        n = d[2:]
        return " ".join(n[i:i + 2] for i in range(0, 8, 2))
    return e164


def first_name(display_name: str | None) -> str:
    return (display_name or "").strip().split(" ")[0] or "en bruger"

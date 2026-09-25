"""Callback windows offered to a visitor, in the workspace's local time.

Fixed windows (formiddag 08–12, eftermiddag 12–16) for today and the next working day, plus
"as soon as possible". A window is offered only while at least one hour of it remains.
"""
from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

WINDOWS = {"am": (time(8), time(12), "formiddag (8–12)"), "pm": (time(12), time(16), "eftermiddag (12–16)")}
WEEKDAYS = ["mandag", "tirsdag", "onsdag", "torsdag", "fredag", "lørdag", "søndag"]


def _next_workday(d: date) -> date:
    d += timedelta(days=1)
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


def options(tz: str, now: datetime | None = None) -> list[dict]:
    z = ZoneInfo(tz)
    local = (now or datetime.now(UTC)).astimezone(z)
    out = [{"key": "asap", "label": "Hurtigst muligt"}]
    days = []
    if local.weekday() < 5:
        days.append(("today", local.date(), "I dag"))
    nxt = _next_workday(local.date())
    days.append(("next", nxt, "I morgen" if nxt == local.date() + timedelta(days=1) else WEEKDAYS[nxt.weekday()].capitalize()))
    for dkey, d, dlabel in days:
        for wkey, (_start, end, wlabel) in WINDOWS.items():
            if datetime.combine(d, end, tzinfo=z) - local < timedelta(hours=1):
                continue
            out.append({"key": f"{dkey}_{wkey}", "label": f"{dlabel} {wlabel}"})
    return out


def resolve(key: str, tz: str, now: datetime | None = None) -> tuple[datetime, datetime, str] | None:
    """Window key → (from, to, label) in UTC; None for 'asap'. Raises ValueError if not offered now."""
    offered = {o["key"]: o["label"] for o in options(tz, now)}
    if key not in offered:
        raise ValueError(key)
    if key == "asap":
        return None
    z = ZoneInfo(tz)
    local = (now or datetime.now(UTC)).astimezone(z)
    dkey, wkey = key.split("_")
    d = local.date() if dkey == "today" else _next_workday(local.date())
    start, end, _ = WINDOWS[wkey]
    frm = max(datetime.combine(d, start, tzinfo=z), local)
    return frm.astimezone(UTC), datetime.combine(d, end, tzinfo=z).astimezone(UTC), offered[key]

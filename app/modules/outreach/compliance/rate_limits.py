"""Daily sending limits: per sending inbox and per sending domain. Counted from outreach_messages, so the limit holds
across batches and processes."""
from __future__ import annotations

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session as OrmSession

from app.config import get_settings
from app.models import OutreachMessage

_COUNTED = ("queued", "sent", "dry_run")


def used(db: OrmSession, day: date) -> dict[str, int]:
    rows = db.execute(select(OutreachMessage.sender_inbox, func.count()).where(
        OutreachMessage.send_on == day, OutreachMessage.status.in_(_COUNTED),
        OutreachMessage.sender_inbox.is_not(None)).group_by(OutreachMessage.sender_inbox)).all()
    return {inbox: n for inbox, n in rows}


def pick_inbox(db: OrmSession, day: date) -> str | None:
    """The inbox with most capacity left today, or None when every inbox (or its domain) is full."""
    s = get_settings()
    inboxes = s.outreach_inboxes or (["outreach@dry-run.invalid"] if s.outreach_mode != "live" else [])
    u = used(db, day)
    per_domain: dict[str, int] = {}
    for inbox, n in u.items():
        per_domain[inbox.rsplit("@", 1)[-1]] = per_domain.get(inbox.rsplit("@", 1)[-1], 0) + n
    free = [(u.get(i, 0), i) for i in inboxes
            if u.get(i, 0) < s.outreach_daily_limit_per_inbox
            and per_domain.get(i.rsplit("@", 1)[-1], 0) < s.outreach_daily_limit_per_domain]
    return min(free)[1] if free else None


def within_limits(db: OrmSession, inbox: str, day: date) -> bool:
    """Checked again at send time (a message already counts itself, hence <=)."""
    s = get_settings()
    u = used(db, day)
    domain = inbox.rsplit("@", 1)[-1]
    return (u.get(inbox, 0) <= s.outreach_daily_limit_per_inbox
            and sum(n for i, n in u.items() if i.rsplit("@", 1)[-1] == domain) <= s.outreach_daily_limit_per_domain)

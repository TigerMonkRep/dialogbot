"""Daily reports (per local calendar day in the workspace's time zone).

- `compute` counts what happened between local midnight and midnight (DST-safe via zoneinfo).
- `generate` stores an immutable snapshot for a finished day (unique per workspace/date).
- `run_due` is called by the worker: after `send_hour_local` it snapshots yesterday for every
  workspace that has none yet and, if enabled, e-mails owners/admins once (outbox dedupe).
Money is summed in whole øre from the fee snapshots of leads approved that day.
"""
from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as OrmSession

from app.config import get_settings
from app.core.outbox import enqueue
from app.models import (
    AiUsage,
    BusinessProfile,
    Conversation,
    ConversationMessage,
    DailyReport,
    Lead,
    Membership,
    ReportSettings,
    Task,
    User,
    Workspace,
)


def tz_of(db: OrmSession, workspace_id: uuid.UUID) -> str:
    p = db.get(BusinessProfile, workspace_id)
    try:
        ZoneInfo(p.timezone if p else "Europe/Copenhagen")
        return p.timezone if p else "Europe/Copenhagen"
    except Exception:  # noqa: BLE001 - an invalid stored zone must not break reporting
        return "Europe/Copenhagen"


def day_bounds(day: date, tz: str) -> tuple[datetime, datetime]:
    z = ZoneInfo(tz)
    start = datetime.combine(day, time.min, tzinfo=z)
    end = datetime.combine(day + timedelta(days=1), time.min, tzinfo=z)
    return start.astimezone(UTC), end.astimezone(UTC)


def local_today(tz: str, now: datetime | None = None) -> date:
    return (now or datetime.now(UTC)).astimezone(ZoneInfo(tz)).date()


def settings_for(db: OrmSession, workspace_id: uuid.UUID) -> ReportSettings:
    s = db.get(ReportSettings, workspace_id)
    if s is None:
        s = ReportSettings(workspace_id=workspace_id, email_enabled=True, send_hour_local=7)
        db.add(s)
        db.flush()
    return s


def _count(db: OrmSession, model, *where) -> int:
    return db.scalar(select(func.count()).select_from(model).where(*where)) or 0


def compute(db: OrmSession, workspace_id: uuid.UUID, day: date, tz: str) -> dict:
    a, b = day_bounds(day, tz)

    def within(col):
        return (col >= a, col < b)

    conversations = _count(db, Conversation, Conversation.workspace_id == workspace_id, *within(Conversation.created_at))
    visitor_msgs = _count(db, ConversationMessage, ConversationMessage.workspace_id == workspace_id,
                          ConversationMessage.role == "visitor", *within(ConversationMessage.created_at))
    ai_rows = db.execute(
        select(AiUsage.outcome, func.count(), func.sum(AiUsage.input_tokens + AiUsage.cache_creation_input_tokens
                                                       + AiUsage.cache_read_input_tokens),
               func.sum(AiUsage.output_tokens), func.sum(AiUsage.est_cost_usd_micros))
        .where(AiUsage.workspace_id == workspace_id, *within(AiUsage.created_at)).group_by(AiUsage.outcome)
    ).all()
    ai = {"calls": 0, "ok": 0, "refused": 0, "truncated": 0, "error": 0, "input_tokens": 0, "output_tokens": 0,
          "est_cost_usd_micros": 0}
    for outcome, n, tin, tout, cost in ai_rows:
        ai["calls"] += n
        ai[outcome] = ai.get(outcome, 0) + n
        ai["input_tokens"] += int(tin or 0)
        ai["output_tokens"] += int(tout or 0)
        ai["est_cost_usd_micros"] += int(cost or 0)
    new_leads = db.scalars(select(Lead).where(Lead.workspace_id == workspace_id, *within(Lead.created_at))
                           .order_by(Lead.created_at)).all()
    approved = db.scalars(select(Lead).where(Lead.workspace_id == workspace_id, Lead.billing_status == "approved",
                                             *within(Lead.billing_decided_at))).all()
    rejected = _count(db, Lead, Lead.workspace_id == workspace_id, Lead.billing_status == "rejected",
                      *within(Lead.billing_decided_at))
    tasks_created = _count(db, Task, Task.workspace_id == workspace_id, *within(Task.created_at))
    tasks_done = _count(db, Task, Task.workspace_id == workspace_id, Task.status == "done", *within(Task.completed_at))
    overdue = _count(db, Task, Task.workspace_id == workspace_id, Task.status == "open", Task.due_at < b)
    return {
        "date": day.isoformat(), "timezone": tz,
        "conversations": {"started": conversations, "visitor_messages": visitor_msgs},
        "ai": ai,
        "leads": {
            "new": len(new_leads),
            "approved": len(approved),
            "rejected": rejected,
            "approved_fee_net_minor": sum((x.fee_snapshot or {}).get("net_minor", 0) for x in approved),
            "new_items": [{"id": str(x.id), "contact_name": x.contact_name, "need_summary": x.need_summary[:200],
                           "source": x.source} for x in new_leads[:20]],
        },
        "tasks": {"created": tasks_created, "completed": tasks_done, "open_overdue_at_end": overdue},
    }


def generate(db: OrmSession, workspace_id: uuid.UUID, day: date, now: datetime | None = None) -> DailyReport | None:
    """Store the snapshot for a finished day. Returns None if it already exists (idempotent)."""
    tz = tz_of(db, workspace_id)
    if day >= local_today(tz, now):
        raise ValueError("only finished days can be snapshotted")
    if db.scalar(select(DailyReport.id).where(DailyReport.workspace_id == workspace_id, DailyReport.report_date == day)):
        return None
    r = DailyReport(workspace_id=workspace_id, report_date=day, timezone=tz, data=compute(db, workspace_id, day, tz))
    db.add(r)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        return None
    return r


def _summary_text(ws_name: str, d: dict) -> str:
    kr = lambda m: f"{m / 100:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")  # noqa: E731
    lines = [f"Dagsrapport for {ws_name} – {d['date']}", "",
             f"Samtaler: {d['conversations']['started']} (kundebeskeder: {d['conversations']['visitor_messages']})",
             f"AI-svar: {d['ai']['ok']} ok, {d['ai']['refused']} afvist, {d['ai']['error']} fejl",
             f"Nye henvendelser: {d['leads']['new']}",
             f"Godkendte henvendelser: {d['leads']['approved']} ({kr(d['leads']['approved_fee_net_minor'])} kr. ekskl. moms)",
             f"Opgaver: {d['tasks']['created']} oprettet, {d['tasks']['completed']} løst, "
             f"{d['tasks']['open_overdue_at_end']} åbne over frist"]
    if d["leads"]["new_items"]:
        lines += ["", "Nye henvendelser:"] + [f"- {x['contact_name'] or '(uden navn)'}: {x['need_summary']}"
                                              for x in d["leads"]["new_items"]]
    return "\n".join(lines)


def run_due(db: OrmSession, now: datetime | None = None) -> int:
    """Snapshot yesterday for workspaces whose local send hour has passed; e-mail once. Returns count."""
    now = now or datetime.now(UTC)
    made = 0
    for ws in db.scalars(select(Workspace)).all():
        tz = tz_of(db, ws.id)
        local_now = now.astimezone(ZoneInfo(tz))
        s = settings_for(db, ws.id)
        if local_now.hour < s.send_hour_local:
            continue
        day = local_now.date() - timedelta(days=1)
        if day < ws.created_at.astimezone(ZoneInfo(tz)).date():
            continue  # no report for days before the workspace existed
        r = generate(db, ws.id, day, now)
        if r is None:
            continue
        made += 1
        if s.email_enabled:
            link = f"{get_settings().frontend_base_url}/app/reports?date={day.isoformat()}"
            body = _summary_text(ws.name, r.data) + f"\n\nSe rapporten: {link}"
            for user_id, email in db.execute(select(User.id, User.email).join(Membership, Membership.user_id == User.id)
                                             .where(Membership.workspace_id == ws.id,
                                                    Membership.role.in_(("owner", "admin")))):
                enqueue(db, event_type="email.daily_report", dedupe_key=f"daily_report:{ws.id}:{day}:{user_id}",
                        workspace_id=ws.id, payload={"to_email": email, "subject": f"Dagsrapport {day.isoformat()} – {ws.name}",
                                                     "body": body})
        db.commit()
    db.commit()
    return made

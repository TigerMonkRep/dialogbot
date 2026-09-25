"""Daily reports: local-day boundaries (Europe/Copenhagen incl. DST), immutable snapshots,
scheduled generation with one e-mail per owner/admin, preliminary 'today', role-based cost fields."""
from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select, update

from app.models import (
    AiUsage,
    Conversation,
    DailyReport,
    Lead,
    OutboxEvent,
    Task,
    Workspace,
)
from app.modules.reports import service


def _conv(db, ws, at):
    db.add(Conversation(workspace_id=ws, channel="webchat", visitor_token_digest="x" * 64, created_at=at, last_message_at=at))


def _backdate_workspace(db, ws):
    db.execute(update(Workspace).where(Workspace.id == ws).values(created_at=datetime(2026, 1, 1, tzinfo=UTC)))
    db.commit()


def test_local_day_boundaries_follow_workspace_timezone(two_workspaces, db):
    ws = uuid.UUID(two_workspaces["ws_a"])
    # 2026-09-24 in Copenhagen (CEST, UTC+2) runs from 22:00 UTC on the 23rd to 22:00 UTC on the 24th.
    _conv(db, ws, datetime(2026, 9, 23, 21, 59, tzinfo=UTC))  # 23:59 local on the 23rd → excluded
    _conv(db, ws, datetime(2026, 9, 23, 22, 0, tzinfo=UTC))   # 00:00 local on the 24th → included
    _conv(db, ws, datetime(2026, 9, 24, 21, 59, tzinfo=UTC))  # 23:59 local → included
    _conv(db, ws, datetime(2026, 9, 24, 22, 0, tzinfo=UTC))   # next day → excluded
    db.commit()
    d = service.compute(db, ws, date(2026, 9, 24), "Europe/Copenhagen")
    assert d["conversations"]["started"] == 2
    # a DST day is 25 hours long (2026-10-25) and still one report day
    a, b = service.day_bounds(date(2026, 10, 25), "Europe/Copenhagen")
    assert b - a == timedelta(hours=25)


def test_counts_leads_fees_tasks_and_ai(two_workspaces, db):
    ws = uuid.UUID(two_workspaces["ws_a"])
    at = datetime(2026, 9, 24, 10, 0, tzinfo=UTC)
    db.add_all([
        Lead(workspace_id=ws, source="webchat", contact_name="Henrik", need_summary="Afslibning", created_at=at),
        Lead(workspace_id=ws, source="manual", contact_name="B", created_at=at, qualification_status="qualified",
             billing_status="approved", billing_decided_at=at, fee_snapshot={"net_minor": 14900}),
        Lead(workspace_id=ws, source="manual", contact_name="C", created_at=at - timedelta(days=3),
             billing_status="rejected", billing_decided_at=at),
        Task(workspace_id=ws, title="Ring", created_at=at, status="done", completed_at=at),
        Task(workspace_id=ws, title="Over frist", created_at=at - timedelta(days=2), status="open", due_at=at),
        AiUsage(workspace_id=ws, purpose="webchat", provider="fake", requested_model="m", prompt_version="p",
                knowledge_revision=1, outcome="ok", input_tokens=100, output_tokens=20, est_cost_usd_micros=900, created_at=at),
        AiUsage(workspace_id=ws, purpose="webchat", provider="fake", requested_model="m", prompt_version="p",
                knowledge_revision=1, outcome="refused", created_at=at),
    ])
    db.commit()
    d = service.compute(db, ws, date(2026, 9, 24), "Europe/Copenhagen")
    assert d["leads"]["new"] == 2 and d["leads"]["approved"] == 1 and d["leads"]["rejected"] == 1
    assert d["leads"]["approved_fee_net_minor"] == 14900
    assert d["leads"]["new_items"][0]["contact_name"] == "Henrik"
    assert d["tasks"] == {"created": 1, "completed": 1, "open_overdue_at_end": 1}
    assert d["ai"]["ok"] == 1 and d["ai"]["refused"] == 1 and d["ai"]["input_tokens"] == 100
    assert d["ai"]["est_cost_usd_micros"] == 900


def test_scheduler_snapshots_once_and_emails_owner_once(two_workspaces, db):
    ws = uuid.UUID(two_workspaces["ws_a"])
    _backdate_workspace(db, ws)
    _backdate_workspace(db, uuid.UUID(two_workspaces["ws_b"]))
    before_send = datetime(2026, 9, 25, 4, 30, tzinfo=UTC)  # 06:30 local: too early
    assert service.run_due(db, now=before_send) == 0
    at_send = datetime(2026, 9, 25, 5, 5, tzinfo=UTC)  # 07:05 local
    assert service.run_due(db, now=at_send) == 2  # both workspaces
    assert service.run_due(db, now=at_send + timedelta(minutes=1)) == 0  # idempotent
    r = db.scalar(select(DailyReport).where(DailyReport.workspace_id == ws))
    assert r.report_date == date(2026, 9, 24) and r.timezone == "Europe/Copenhagen"
    mails = db.scalars(select(OutboxEvent).where(OutboxEvent.event_type == "email.daily_report",
                                                 OutboxEvent.workspace_id == ws)).all()
    assert len(mails) == 1 and mails[0].payload["to_email"] == "owner-a@testmail.dk"
    assert "Dagsrapport for Fjord Gulvservice ApS – 2026-09-24" in mails[0].payload["body"]


def test_email_can_be_turned_off_and_snapshot_is_immutable(api, two_workspaces, db):
    ws, tok = two_workspaces["ws_a"], two_workspaces["tok_a"]
    _backdate_workspace(db, uuid.UUID(ws))
    assert api.put(tok, f"/workspaces/{ws}/reports/settings", {"email_enabled": False, "send_hour_local": 6}).status_code == 200
    service.run_due(db, now=datetime(2026, 9, 25, 4, 10, tzinfo=UTC))  # 06:10 local ≥ 6
    assert db.scalars(select(OutboxEvent).where(OutboxEvent.event_type == "email.daily_report")).all() == []
    snap = api.get(tok, f"/workspaces/{ws}/reports/2026-09-24").json()
    assert snap["status"] == "final" and snap["conversations"]["started"] == 0
    # activity recorded later for that day does not change the stored snapshot
    _conv(db, uuid.UUID(ws), datetime(2026, 9, 24, 12, 0, tzinfo=UTC))
    db.commit()
    assert api.get(tok, f"/workspaces/{ws}/reports/2026-09-24").json()["conversations"]["started"] == 0


def test_api_today_is_preliminary_roles_and_isolation(api, two_workspaces):
    t = two_workspaces
    ws, tok = t["ws_a"], t["tok_a"]
    lst = api.get(tok, f"/workspaces/{ws}/reports").json()
    today = lst["today"]
    r = api.get(tok, f"/workspaces/{ws}/reports/{today}").json()
    assert r["status"] == "preliminary" and "est_cost_usd_micros" in r["ai"]
    tomorrow = (date.fromisoformat(today) + timedelta(days=1)).isoformat()
    assert api.get(tok, f"/workspaces/{ws}/reports/{tomorrow}").status_code == 404
    staff = api.add_member(tok, ws, "staff@testmail.dk", "staff")
    reader = api.add_member(tok, ws, "reader@testmail.dk", "reader")
    rs = api.get(staff, f"/workspaces/{ws}/reports/{today}").json()
    assert "est_cost_usd_micros" not in rs["ai"] and "approved_fee_net_minor" not in rs["leads"]
    assert api.put(staff, f"/workspaces/{ws}/reports/settings", {"email_enabled": False, "send_hour_local": 7}).status_code == 403
    assert api.get(reader, f"/workspaces/{ws}/reports").status_code == 403
    assert api.get(t["tok_b"], f"/workspaces/{ws}/reports").status_code == 404

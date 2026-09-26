"""Overview dashboard and notifications.

Notifications are derived from real records (leads, calls, tasks, conversations waiting for staff,
drafts waiting for approval, website imports) – nothing is invented or stored twice. A user's
"seen" time decides what counts as unread; each item is only shown to roles that may open it."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session as OrmSession

from app.core.auth import WorkspaceContext, get_workspace_context
from app.db import get_db
from app.models import (
    Call,
    Conversation,
    ConversationMessage,
    KnowledgeVersion,
    Lead,
    NotificationRead,
    SourceImport,
    Task,
)

router = APIRouter(prefix="/workspaces/{workspace_id}", tags=["overview"])
WINDOW = timedelta(days=14)


def _now() -> datetime:
    return datetime.now(UTC)


def _awaiting_staff(db: OrmSession, ws_id) -> list[tuple[Conversation, datetime]]:
    last = (select(ConversationMessage.conversation_id, func.max(ConversationMessage.created_at).label("at"))
            .where(ConversationMessage.workspace_id == ws_id).group_by(ConversationMessage.conversation_id).subquery())
    rows = db.execute(
        select(Conversation, ConversationMessage.role, last.c.at)
        .join(last, last.c.conversation_id == Conversation.id)
        .join(ConversationMessage, (ConversationMessage.conversation_id == Conversation.id)
              & (ConversationMessage.created_at == last.c.at))
        .where(Conversation.workspace_id == ws_id, Conversation.mode == "staff")).all()
    return [(c, at) for c, role, at in rows if role == "visitor"]


def notifications(db: OrmSession, ctx: WorkspaceContext) -> list[dict]:
    ws_id, since, now = ctx.workspace.id, _now() - WINDOW, _now()
    items: list[dict] = []
    if ctx.can("leads.read"):
        for lead in db.scalars(select(Lead).where(Lead.workspace_id == ws_id, Lead.created_at >= since)
                               .order_by(Lead.created_at.desc()).limit(20)):
            items.append({"id": f"lead:{lead.id}", "kind": "lead", "at": lead.created_at,
                          "title": f"Ny henvendelse: {lead.contact_name or lead.contact_phone or lead.contact_email or 'ukendt'}",
                          "body": lead.need_summary[:140], "href": f"/app/leads/{lead.id}"})
    if ctx.can("telephony.read"):
        for c in db.scalars(select(Call).where(Call.workspace_id == ws_id, Call.created_at >= since)
                            .order_by(Call.created_at.desc()).limit(20)):
            items.append({"id": f"call:{c.id}", "kind": "call", "at": c.created_at,
                          "title": f"Opkald fra {c.from_number or 'skjult nummer'}", "body": (c.summary or "")[:140],
                          "href": f"/app/inbox/{c.conversation_id}" if c.conversation_id else "/app/settings/telephony"})
    if ctx.can("tasks.read"):
        for t in db.scalars(select(Task).where(Task.workspace_id == ws_id, Task.status == "open",
                                               Task.due_at.is_not(None), Task.due_at <= now + timedelta(hours=2))
                            .order_by(Task.due_at).limit(20)):
            items.append({"id": f"task:{t.id}:{t.due_at.date()}", "kind": "task", "at": min(t.due_at, now),
                          "title": ("Overskredet: " if t.due_at < now else "Snart: ") + t.title, "body": "",
                          "href": "/app/tasks"})
    if ctx.can("conversations.read"):
        for c, at in _awaiting_staff(db, ws_id):
            items.append({"id": f"conv:{c.id}:{at.isoformat()}", "kind": "conversation", "at": at,
                          "title": "En kunde venter på svar i chatten", "body": "", "href": f"/app/inbox/{c.id}"})
    if ctx.can("knowledge.approve"):
        n = db.scalar(select(func.count(KnowledgeVersion.id)).where(
            KnowledgeVersion.workspace_id == ws_id, KnowledgeVersion.status.in_(("draft", "in_review")))) or 0
        latest = db.scalar(select(func.max(KnowledgeVersion.created_at)).where(
            KnowledgeVersion.workspace_id == ws_id, KnowledgeVersion.status.in_(("draft", "in_review"))))
        if n:
            items.append({"id": f"drafts:{n}:{latest.isoformat()}", "kind": "knowledge", "at": latest,
                          "title": f"{n} vidensemne{'r' if n != 1 else ''} venter på godkendelse", "body": "",
                          "href": "/app/knowledge?tab=k05"})
    if ctx.can("knowledge.read"):
        imp = db.scalar(select(SourceImport).where(SourceImport.workspace_id == ws_id, SourceImport.finished_at >= since)
                        .order_by(SourceImport.created_at.desc()).limit(1))
        if imp:
            ok = imp.status == "done"
            items.append({"id": f"import:{imp.id}", "kind": "import", "at": imp.finished_at,
                          "title": f"Hjemmesiden er læst: {len(imp.created_items)} forslag" if ok else "Importen fra hjemmesiden fejlede",
                          "body": "" if ok else (imp.error or ""), "href": "/app/knowledge?tab=k03"})
    items.sort(key=lambda i: i["at"], reverse=True)
    return items[:40]


@router.get("/notifications")
def list_notifications(ctx: WorkspaceContext = Depends(get_workspace_context), db: OrmSession = Depends(get_db)):
    read = db.get(NotificationRead, (ctx.user_id, ctx.workspace.id))
    seen = read.seen_at if read else None
    items = notifications(db, ctx)
    for i in items:
        i["unread"] = seen is None or i["at"] > seen
        i["at"] = i["at"].isoformat()
    return {"items": items, "unread": sum(1 for i in items if i["unread"]), "seen_at": seen.isoformat() if seen else None}


@router.post("/notifications/seen", status_code=204)
def mark_seen(ctx: WorkspaceContext = Depends(get_workspace_context), db: OrmSession = Depends(get_db)):
    read = db.get(NotificationRead, (ctx.user_id, ctx.workspace.id))
    if read is None:
        db.add(NotificationRead(user_id=ctx.user_id, workspace_id=ctx.workspace.id, seen_at=_now()))
    else:
        read.seen_at = _now()
    db.commit()


@router.get("/overview")
def overview(ctx: WorkspaceContext = Depends(get_workspace_context), db: OrmSession = Depends(get_db)):
    ws_id, now = ctx.workspace.id, _now()
    day = now - timedelta(days=1)
    count = lambda q: db.scalar(q) or 0  # noqa: E731
    kpis = {
        "new_leads_24h": count(select(func.count(Lead.id)).where(Lead.workspace_id == ws_id, Lead.created_at >= day)),
        "open_leads": count(select(func.count(Lead.id)).where(Lead.workspace_id == ws_id,
                                                              Lead.pipeline_status.in_(("new", "contacted")))),
        "open_tasks": count(select(func.count(Task.id)).where(Task.workspace_id == ws_id, Task.status == "open")),
        "overdue_tasks": count(select(func.count(Task.id)).where(Task.workspace_id == ws_id, Task.status == "open",
                                                                 Task.due_at < now)),
        "conversations_24h": count(select(func.count(Conversation.id)).where(Conversation.workspace_id == ws_id,
                                                                            Conversation.created_at >= day)),
        "awaiting_staff": len(_awaiting_staff(db, ws_id)),
        "calls_24h": count(select(func.count(Call.id)).where(Call.workspace_id == ws_id, Call.created_at >= day)),
        "drafts": count(select(func.count(KnowledgeVersion.id)).where(
            KnowledgeVersion.workspace_id == ws_id, KnowledgeVersion.status.in_(("draft", "in_review")))),
    }
    activity = notifications(db, ctx)[:10]
    for i in activity:
        i["at"] = i["at"].isoformat()
    return {"kpis": kpis, "activity": activity}

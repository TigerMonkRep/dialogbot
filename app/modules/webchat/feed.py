"""«Opkald og beskeder»: one row per conversation (phone and webchat) with an outcome the customer understands.

Outcome (a derived value, nothing new is stored):
- booked  – a confirmed booking was made in the conversation (or in the call that belongs to it)
- to_you  – someone has to act: a colleague has to answer in the chat, the lead is still new, or a task is open
- done    – Dialogbot handled it
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from app.models import Booking, Call, Conversation, ConversationMessage, Lead, Task

OUTCOMES = ("booked", "to_you", "done")
CHANNELS = ("phone", "webchat")


def enrich(db: OrmSession, convs: list[Conversation]) -> list[dict]:
    """Feed items for these conversations (same order). Everything is fetched in a handful of queries."""
    if not convs:
        return []
    ids = [c.id for c in convs]
    first_visitor = {cid: t for cid, t in db.execute(
        select(ConversationMessage.conversation_id, ConversationMessage.text)
        .where(ConversationMessage.conversation_id.in_(ids), ConversationMessage.role == "visitor")
        .order_by(ConversationMessage.conversation_id, ConversationMessage.created_at)).all()[::-1]}
    last_role: dict = {}
    for cid, role in db.execute(
            select(ConversationMessage.conversation_id, ConversationMessage.role)
            .where(ConversationMessage.conversation_id.in_(ids))
            .order_by(ConversationMessage.conversation_id, ConversationMessage.created_at.desc())):
        last_role.setdefault(cid, role)
    calls = {c.conversation_id: c for c in db.scalars(select(Call).where(Call.conversation_id.in_(ids)))}
    leads = {x.conversation_id: x for x in db.scalars(select(Lead).where(Lead.conversation_id.in_(ids)))}
    open_tasks = {lid for (lid,) in db.execute(
        select(Task.lead_id).where(Task.lead_id.in_([x.id for x in leads.values()] or [uuid.uuid4()]), Task.status == "open"))}
    call_ids = {c.provider_call_id: c.conversation_id for c in calls.values()}
    booked = {cid for (cid,) in db.execute(select(Booking.conversation_id).where(
        Booking.conversation_id.in_(ids), Booking.status == "confirmed"))}
    if call_ids:
        booked |= {call_ids[pc] for (pc,) in db.execute(select(Booking.provider_call_id).where(
            Booking.provider_call_id.in_(list(call_ids)), Booking.status == "confirmed")) if pc in call_ids}
    items = []
    for c in convs:
        call, lead = calls.get(c.id), leads.get(c.id)
        awaiting = c.mode == "staff" and last_role.get(c.id) == "visitor"
        pending = awaiting or (lead is not None and (lead.pipeline_status == "new" or lead.id in open_tasks))
        outcome = "booked" if c.id in booked else "to_you" if pending else "done"
        name = (lead.contact_name if lead and lead.contact_name else "") or (call.from_number if call else None) or c.origin
        if c.channel == "webchat":
            name = (lead.contact_name if lead and lead.contact_name else "") or "Webchat"
        summary = ((call.summary if call and call.summary else "") or (lead.need_summary if lead else "")
                   or first_visitor.get(c.id, ""))[:200]
        started = (call.started_at if call and call.started_at else None) or c.created_at
        items.append({
            "id": str(c.id), "channel": c.channel, "outcome": outcome, "name": name or "Ukendt nummer",
            "origin": c.origin, "summary": summary, "question": first_visitor.get(c.id, "")[:200], "started_at": started.isoformat(),
            "last_message_at": c.last_message_at.isoformat(),
            "duration_seconds": call.duration_seconds if call else None,
            "phone": (call.from_number if call else None) or (lead.contact_phone if lead else None),
            "lead_id": str(lead.id) if lead else None, "awaiting_staff": awaiting, "mode": c.mode,
        })
    return items


def conversations_between(db: OrmSession, workspace_id: uuid.UUID, a: datetime, b: datetime) -> list[Conversation]:
    return list(db.scalars(select(Conversation).where(
        Conversation.workspace_id == workspace_id, Conversation.created_at >= a, Conversation.created_at < b)))


def counts(items: list[dict]) -> dict:
    return {"all": len(items), "to_you": sum(1 for i in items if i["outcome"] == "to_you"),
            "booked": sum(1 for i in items if i["outcome"] == "booked"),
            "done": sum(1 for i in items if i["outcome"] == "done"),
            "webchat": sum(1 for i in items if i["channel"] == "webchat")}


def resolve(db: OrmSession, conv: Conversation, actor: uuid.UUID) -> dict:
    """«Marker som klaret»: complete the open tasks, mark the lead as contacted and hand a taken-over chat back."""
    lead = db.scalar(select(Lead).where(Lead.conversation_id == conv.id))
    before = {"mode": conv.mode, "pipeline": lead.pipeline_status if lead else None}
    closed_tasks = 0
    if lead is not None:
        for t in db.scalars(select(Task).where(Task.lead_id == lead.id, Task.status == "open")):
            t.status, t.completed_by = "done", actor
            t.completed_at = datetime.now(UTC)
            closed_tasks += 1
        if lead.pipeline_status == "new":
            lead.pipeline_status = "contacted"
            lead.version += 1
    if conv.mode == "staff":
        conv.mode = "ai"
    return {"before": before, "after": {"mode": conv.mode, "pipeline": lead.pipeline_status if lead else None},
            "tasks_closed": closed_tasks}

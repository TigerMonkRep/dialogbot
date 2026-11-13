"""Support tickets (H01 customer side, M06 operator queue): numbering, status rules, serializers, reply mail.

Status: open (waiting for Dialogbot) → in_progress (an operator is on it) → waiting_customer (Dialogbot replied and
waits for the customer) → resolved. A customer's reply on a waiting or resolved ticket puts it back to open; a public
operator reply sets waiting_customer unless the operator picks another status; an internal note changes nothing.

DB-016: the customer serializers read ONLY visibility='public' messages (in SQL, not by filtering afterwards) and only
the attachments of those messages; priority, assignee and internal notes are operator-only fields."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session as OrmSession

from app.config import get_settings
from app.core.errors import ApiError, NotFound
from app.core.outbox import enqueue
from app.models import Membership, SupportAttachment, SupportMessage, SupportTicket, User, Workspace
from app.modules.support import attachments as files

MAX_NEW_PER_DAY = 10  # new tickets per workspace per 24 h
MAX_MESSAGES_PER_HOUR = 30  # customer messages per ticket per hour


class TooMany(ApiError):
    status_code = 429
    code = "rate_limited"


def now() -> datetime:
    return datetime.now(UTC)


def ticket_for_customer(db: OrmSession, workspace_id: uuid.UUID, number: int, *, lock: bool = False) -> SupportTicket:
    q = select(SupportTicket).where(SupportTicket.workspace_id == workspace_id, SupportTicket.number == number)
    t = db.scalar(q.with_for_update() if lock else q)
    if t is None:
        raise NotFound("Sagen findes ikke")
    return t


def next_number(db: OrmSession, workspace_id: uuid.UUID) -> int:
    # Serialise ticket creation per workspace on the workspace row; the unique constraint is the backstop.
    db.execute(select(Workspace.id).where(Workspace.id == workspace_id).with_for_update())
    return (db.scalar(select(func.max(SupportTicket.number)).where(SupportTicket.workspace_id == workspace_id)) or 0) + 1


def check_new_ticket_rate(db: OrmSession, workspace_id: uuid.UUID) -> None:
    n = db.scalar(select(func.count()).select_from(SupportTicket).where(
        SupportTicket.workspace_id == workspace_id, SupportTicket.created_at > now() - timedelta(hours=24))) or 0
    if n >= MAX_NEW_PER_DAY:
        raise TooMany("I har oprettet mange sager i dag – skriv i en af de åbne sager i stedet")


def check_message_rate(db: OrmSession, ticket_id: uuid.UUID) -> None:
    n = db.scalar(select(func.count()).select_from(SupportMessage).where(
        SupportMessage.ticket_id == ticket_id, SupportMessage.author_kind == "customer",
        SupportMessage.created_at > now() - timedelta(hours=1))) or 0
    if n >= MAX_MESSAGES_PER_HOUR:
        raise TooMany("Mange beskeder på kort tid – vent lidt, før du skriver igen")


def add_message(db: OrmSession, t: SupportTicket, *, author: uuid.UUID | None, kind: str, visibility: str, body: str,
                uploads: list | None = None) -> SupportMessage:
    m = SupportMessage(ticket_id=t.id, workspace_id=t.workspace_id, author_user_id=author, author_kind=kind,
                       visibility=visibility, body=body)
    db.add(m)
    db.flush()
    if uploads:
        files.store(db, workspace_id=t.workspace_id, ticket_id=t.id, message_id=m.id, uploaded_by=author, files=uploads)
    t.updated_at = now()
    return m


def set_status(t: SupportTicket, status: str) -> None:
    t.status = status
    t.resolved_at = now() if status == "resolved" else None
    t.updated_at = now()


def _names(db: OrmSession, ids: set) -> dict:
    ids = {i for i in ids if i}
    if not ids:
        return {}
    return {u.id: u for u in db.scalars(select(User).where(User.id.in_(ids)))}


def _attachments_by_message(db: OrmSession, message_ids: list[uuid.UUID]) -> dict:
    out: dict = {}
    if message_ids:
        for a in db.scalars(select(SupportAttachment).where(SupportAttachment.message_id.in_(message_ids))
                            .order_by(SupportAttachment.created_at)):
            out.setdefault(a.message_id, []).append(files.out(a))
    return out


def _first_name(u: User | None) -> str:
    return ((u.display_name or "").split(" ")[0] if u else "") or ""


def customer_summary(t: SupportTicket) -> dict:
    return {"number": t.number, "subject": t.subject, "category": t.category, "status": t.status,
            "created_at": t.created_at.isoformat(), "updated_at": t.updated_at.isoformat(),
            "resolved_at": t.resolved_at.isoformat() if t.resolved_at else None}


def customer_detail(db: OrmSession, t: SupportTicket) -> dict:
    """What the customer may see: public messages and their attachments only (DB-016)."""
    msgs = list(db.scalars(select(SupportMessage).where(SupportMessage.ticket_id == t.id,
                                                        SupportMessage.visibility == "public")
                           .order_by(SupportMessage.created_at, SupportMessage.id)))
    users = _names(db, {m.author_user_id for m in msgs} | {t.created_by})
    att = _attachments_by_message(db, [m.id for m in msgs])
    creator = users.get(t.created_by)
    return customer_summary(t) | {
        "created_by": creator.display_name if creator else None,
        "messages": [{"id": str(m.id), "author_kind": m.author_kind,
                      # Operators appear by first name only, as «Dialogbot support» in the app
                      "author_name": (users[m.author_user_id].display_name if m.author_kind == "customer"
                                      else _first_name(users[m.author_user_id])) if m.author_user_id in users else "",
                      "body": m.body, "created_at": m.created_at.isoformat(), "attachments": att.get(m.id, [])}
                     for m in msgs]}


def operator_summary(t: SupportTicket, ws_name: str, users: dict) -> dict:
    a = users.get(t.assigned_to)
    c = users.get(t.created_by)
    return customer_summary(t) | {
        "id": str(t.id), "priority": t.priority, "workspace": {"id": str(t.workspace_id), "name": ws_name},
        "assigned_to": {"id": str(a.id), "name": a.display_name or a.email} if a else None,
        "created_by": {"name": c.display_name, "email": c.email} if c else None, "context_path": t.context_path}


def operator_detail(db: OrmSession, t: SupportTicket) -> dict:
    msgs = list(db.scalars(select(SupportMessage).where(SupportMessage.ticket_id == t.id)
                           .order_by(SupportMessage.created_at, SupportMessage.id)))
    users = _names(db, {m.author_user_id for m in msgs} | {t.created_by, t.assigned_to})
    att = _attachments_by_message(db, [m.id for m in msgs])
    ws = db.get(Workspace, t.workspace_id)
    operators = db.execute(select(User.id, User.display_name, User.email).where(
        User.is_platform_operator.is_(True), User.is_active.is_(True)).order_by(User.display_name)).all()
    return operator_summary(t, ws.name if ws else "", users) | {
        "messages": [{"id": str(m.id), "author_kind": m.author_kind, "visibility": m.visibility,
                      "author_name": (users[m.author_user_id].display_name or users[m.author_user_id].email)
                      if m.author_user_id in users else "", "body": m.body, "created_at": m.created_at.isoformat(),
                      "attachments": att.get(m.id, [])} for m in msgs],
        "operators": [{"id": str(i), "name": n or e} for i, n, e in operators]}


def notify_customer(db: OrmSession, t: SupportTicket, message_id: uuid.UUID) -> bool:
    """Mail the person who opened the ticket that Dialogbot replied (simulated outside production). Only while that
    person is still an active member of the workspace."""
    from app.modules.integrations import email_templates as tpl
    from app.modules.integrations.email_texts import user_language

    if not t.created_by:
        return False
    row = db.execute(select(User.email, User.is_active).join(Membership, Membership.user_id == User.id).where(
        User.id == t.created_by, Membership.workspace_id == t.workspace_id)).first()
    if row is None or not row.is_active or not row.email:
        return False
    ws = db.get(Workspace, t.workspace_id)
    link = f"{get_settings().frontend_base_url.rstrip('/')}/app/support/{t.number}"
    mail = tpl.support_reply(ws.name if ws else "", t.number, t.subject, link, user_language(db, t.created_by))
    enqueue(db, event_type="email.branded", dedupe_key=f"support-reply:{message_id}", workspace_id=t.workspace_id,
            payload={"to_email": row.email, "email": tpl.to_payload(mail)})
    return True

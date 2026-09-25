"""Leads and tasks.

- One lead per conversation (unique), created by staff or by the visitor's "Bliv kontaktet" form.
- Qualification, pipeline and billing are separate axes; billing is decided once
  (approve/reject) and never edited afterwards.
- Approval requires a qualified lead and a reception agreement; it snapshots the agreement
  version and the fee in whole øre (0 under model A).
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from app.config import get_settings
from app.core.audit import record_audit
from app.core.errors import Conflict, ValidationFailed
from app.core.outbox import enqueue
from app.models import Conversation, Lead, Membership, Task, User, Workspace
from app.modules.billing import agreements


def _now() -> datetime:
    return datetime.now(UTC)


def lead_out(lead: Lead, tasks: list[Task] | None = None) -> dict:
    d = {k: getattr(lead, k) for k in (
        "version", "source", "contact_name", "contact_email", "contact_phone", "need_summary", "qualification_status",
        "qualification_reason", "pipeline_status", "billing_status", "billing_reason", "fee_snapshot")}
    d |= {"id": str(lead.id), "conversation_id": str(lead.conversation_id) if lead.conversation_id else None,
          "callback_from": lead.callback_from.isoformat() if lead.callback_from else None,
          "callback_to": lead.callback_to.isoformat() if lead.callback_to else None,
          "agreement_id": str(lead.agreement_id) if lead.agreement_id else None,
          "billing_decided_at": lead.billing_decided_at.isoformat() if lead.billing_decided_at else None,
          "billing_decided_by": str(lead.billing_decided_by) if lead.billing_decided_by else None,
          "created_at": lead.created_at.isoformat(), "updated_at": lead.updated_at.isoformat()}
    if tasks is not None:
        d["tasks"] = [task_out(t) for t in tasks]
    return d


def task_out(t: Task) -> dict:
    return {"id": str(t.id), "lead_id": str(t.lead_id) if t.lead_id else None, "title": t.title, "status": t.status,
            "due_at": t.due_at.isoformat() if t.due_at else None,
            "assignee_user_id": str(t.assignee_user_id) if t.assignee_user_id else None,
            "created_by": str(t.created_by) if t.created_by else None, "created_at": t.created_at.isoformat(),
            "completed_at": t.completed_at.isoformat() if t.completed_at else None}


def _audit_view(lead: Lead) -> dict:
    return {k: getattr(lead, k) for k in ("contact_name", "contact_email", "contact_phone", "qualification_status",
                                          "pipeline_status", "billing_status")}


def lead_for_conversation(db: OrmSession, conversation_id: uuid.UUID) -> Lead | None:
    return db.scalar(select(Lead).where(Lead.conversation_id == conversation_id))


def create_lead(db: OrmSession, workspace_id: uuid.UUID, *, source: str, created_by: uuid.UUID | None,
                conversation: Conversation | None = None, contact_name: str = "", contact_email: str | None = None,
                contact_phone: str | None = None, need_summary: str = "", request_id: str | None = None) -> Lead:
    if conversation is not None:
        existing = lead_for_conversation(db, conversation.id)
        if existing is not None:
            raise Conflict("Der findes allerede en henvendelse for denne samtale", code="lead_exists",
                           extra={"lead_id": str(existing.id)})
    lead = Lead(workspace_id=workspace_id, source=source, conversation_id=conversation.id if conversation else None,
                contact_name=contact_name.strip(), contact_email=(contact_email or "").strip().lower() or None,
                contact_phone=(contact_phone or "").strip() or None, need_summary=need_summary.strip(),
                created_by=created_by)
    db.add(lead)
    db.flush()
    record_audit(db, workspace_id=workspace_id, actor_user_id=created_by, action="lead.created", object_type="lead",
                 object_id=lead.id, after=_audit_view(lead) | {"source": source}, request_id=request_id)
    return lead


def create_task(db: OrmSession, workspace_id: uuid.UUID, *, title: str, created_by: uuid.UUID | None,
                lead: Lead | None = None, due_at: datetime | None = None, assignee_user_id: uuid.UUID | None = None,
                request_id: str | None = None) -> Task:
    if assignee_user_id is not None:
        _require_member(db, workspace_id, assignee_user_id)
    t = Task(workspace_id=workspace_id, lead_id=lead.id if lead else None, title=title.strip()[:200],
             due_at=due_at, assignee_user_id=assignee_user_id, created_by=created_by)
    db.add(t)
    db.flush()
    record_audit(db, workspace_id=workspace_id, actor_user_id=created_by, action="task.created", object_type="task",
                 object_id=t.id, after={"title": t.title, "lead_id": str(t.lead_id) if t.lead_id else None},
                 request_id=request_id)
    return t


def _require_member(db: OrmSession, workspace_id: uuid.UUID, user_id: uuid.UUID) -> None:
    if db.scalar(select(Membership.id).where(Membership.workspace_id == workspace_id, Membership.user_id == user_id)) is None:
        raise ValidationFailed("Opgaven kan kun tildeles et medlem af arbejdsrummet",
                               field_errors=[{"field": "assignee_user_id"}])


QUALIFICATION = ("unqualified", "qualified", "disqualified")
PIPELINE = ("new", "contacted", "won", "lost")


def update_lead(db: OrmSession, lead: Lead, *, actor: uuid.UUID, expected_version: int, changes: dict,
                request_id: str | None) -> Lead:
    if expected_version != lead.version:
        raise Conflict(f"Henvendelsen er ændret af en anden (version {lead.version}). Genindlæs og prøv igen.",
                       code="version_conflict", extra={"current_version": lead.version})
    if "qualification_status" in changes and changes["qualification_status"] != lead.qualification_status \
            and lead.billing_status != "pending":
        raise Conflict("Kvalificeringen kan ikke ændres, efter at afregningen er afgjort", code="lead_billing_decided")
    before = _audit_view(lead)
    for k, v in changes.items():
        if k in ("contact_email",):
            v = (v or "").strip().lower() or None
        elif isinstance(v, str):
            v = v.strip()
        setattr(lead, k, v)
    lead.version += 1
    record_audit(db, workspace_id=lead.workspace_id, actor_user_id=actor, action="lead.updated", object_type="lead",
                 object_id=lead.id, before=before, after=_audit_view(lead), request_id=request_id)
    return lead


def decide_billing(db: OrmSession, lead: Lead, *, actor: uuid.UUID, decision: str, reason: str | None,
                   request_id: str | None) -> Lead:
    """Approve or reject a lead for billing. Decided once; the fee is snapshotted from the
    current agreement version at approval time."""
    if lead.billing_status != "pending":
        raise Conflict("Henvendelsen er allerede afgjort", code="lead_billing_decided",
                       extra={"billing_status": lead.billing_status})
    if decision == "approve":
        if lead.qualification_status != "qualified":
            raise Conflict("Kun kvalificerede henvendelser kan godkendes", code="lead_not_qualified")
        a = agreements.current(db, lead.workspace_id)
        if a is None:
            raise Conflict("Vælg en prisaftale (model A eller B), før henvendelser kan godkendes", code="no_agreement")
        lead.agreement_id = a.id
        lead.fee_snapshot = agreements.lead_fee(a).snapshot() | {"agreement_version": a.version, "model": a.model}
        lead.billing_status = "approved"
    elif decision == "reject":
        if not (reason or "").strip():
            raise ValidationFailed("Angiv en begrundelse", field_errors=[{"field": "reason"}])
        lead.billing_status = "rejected"
    else:  # pragma: no cover - guarded by the router
        raise ValidationFailed("Ukendt afgørelse")
    lead.billing_reason = (reason or "").strip() or None
    lead.billing_decided_by, lead.billing_decided_at = actor, _now()
    lead.version += 1
    record_audit(db, workspace_id=lead.workspace_id, actor_user_id=actor, action=f"lead.{decision}d",
                 object_type="lead", object_id=lead.id,
                 after={"billing_status": lead.billing_status, "fee_snapshot": lead.fee_snapshot,
                        "reason": lead.billing_reason}, request_id=request_id)
    return lead


def visitor_contact(db: OrmSession, conv: Conversation, *, name: str, email: str | None, phone: str | None,
                    note: str, window: tuple[datetime, datetime, str] | None = None) -> Lead:
    """The visitor's "Bliv kontaktet" form: create (or update) the conversation's lead, and on
    first contact a follow-up task plus an e-mail to owners and admins."""
    lead = lead_for_conversation(db, conv.id)
    if lead is None:
        from app.modules.webchat.service import messages_of

        first = next((m.text for m in messages_of(db, conv) if m.role == "visitor"), "")
        summary = note.strip() or first
        lead = create_lead(db, conv.workspace_id, source="webchat", created_by=None, conversation=conv,
                           contact_name=name, contact_email=email, contact_phone=phone, need_summary=summary)
        title = f"Kontakt {name.strip() or 'kunden'} fra webchat"
        due = _now() + timedelta(hours=24)
        if window is not None:
            lead.callback_from, lead.callback_to = window[0], window[1]
            title, due = f"Ring {name.strip() or 'kunden'} op – {window[2]}", window[0]
        create_task(db, conv.workspace_id, title=title, created_by=None, lead=lead, due_at=due)
        _notify_new_lead(db, lead)
    else:
        lead.contact_name = name.strip() or lead.contact_name
        lead.contact_email = (email or "").strip().lower() or lead.contact_email
        lead.contact_phone = (phone or "").strip() or lead.contact_phone
        if note.strip():
            lead.need_summary = note.strip()
        if window is not None:
            lead.callback_from, lead.callback_to = window[0], window[1]
        lead.version += 1
    return lead


def _notify_new_lead(db: OrmSession, lead: Lead) -> None:
    ws = db.get(Workspace, lead.workspace_id)
    recipients = db.execute(select(User.id, User.email).join(Membership, Membership.user_id == User.id)
                            .where(Membership.workspace_id == lead.workspace_id, Membership.role.in_(("owner", "admin"))))
    link = f"{get_settings().frontend_base_url}/app/leads/{lead.id}"
    for user_id, email in recipients:
        enqueue(db, event_type="email.new_lead", dedupe_key=f"new_lead:{lead.id}:{user_id}", workspace_id=lead.workspace_id,
                payload={"to_email": email, "workspace_name": ws.name if ws else "", "contact_name": lead.contact_name,
                         "need_summary": lead.need_summary[:500], "link": link})

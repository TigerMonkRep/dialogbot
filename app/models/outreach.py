"""Cold e-mail outreach for Dialogbot's own B2B sales (operator-only, global tables – no workspace_id).

`outreach_leads` – one business per e-mail address, with the compliance decision that was taken before anything else.
`outreach_messages` – the e-mail written for a lead (step 1 of a sequence), its audit and its delivery state.
`outreach_logs` – append-only trail: every compliance decision, model call (tokens), audit, send and provider event.
`outreach_suppression_list` – addresses and domains that must never be e-mailed again, across all campaigns.
`outreach_human_call_queue` – leads in markets where cold e-mail is not allowed, for a person to ring up.

The spec's table names `leads`, `suppression_list` and `human_call_queue` carry the `outreach_` prefix here because
`leads` already is the customers' own lead table (app/modules/leads).
"""
from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.identity import ts_now, uuid_pk

LEAD_STATUSES = ("new", "blocked", "held", "call_queue", "disqualified", "qualified", "low_confidence", "researched",
                 "audit_failed", "queued", "sent", "replied", "bounced", "unsubscribed", "error")
MESSAGE_STATUSES = ("draft", "rejected", "queued", "deferred", "sent", "dry_run", "cancelled", "failed")
SUPPRESSION_REASONS = ("unsubscribe", "bounce", "complaint", "manual", "objection")


class OutreachLead(Base):
    __tablename__ = "outreach_leads"
    __table_args__ = (
        CheckConstraint("status in ('" + "','".join(LEAD_STATUSES) + "')", name="ck_outreach_leads_status"),
        UniqueConstraint("email_normalized", name="uq_outreach_leads_email"),
        Index("ix_outreach_leads_status", "status", "created_at"),
        Index("ix_outreach_leads_batch", "batch"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    batch: Mapped[str] = mapped_column(String(60), nullable=False)
    company_name: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    email_normalized: Mapped[str] = mapped_column(String(320), nullable=False)
    email_domain: Mapped[str] = mapped_column(String(255), nullable=False)
    country: Mapped[str] = mapped_column(String(2), nullable=False)  # UK is stored as UK (the matrix's code)
    city: Mapped[str | None] = mapped_column(String(120))
    niche: Mapped[str | None] = mapped_column(String(40))
    website: Mapped[str | None] = mapped_column(String(300))
    phone: Mapped[str | None] = mapped_column(String(40))
    registration_number: Mapped[str | None] = mapped_column(String(40))  # CVR for DK, company number elsewhere
    # Where the address was found: published_website | directory | import | unknown, with the page it was read on.
    email_source: Mapped[str] = mapped_column(String(20), nullable=False, default="unknown")
    email_source_url: Mapped[str | None] = mapped_column(String(500))
    # Text the operator supplied with the lead (website text, review snippets) for the research agent.
    context: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="new")
    # The ComplianceEngine's decision: EMAIL | CALL_QUEUE | HOLD | BLOCK, the rule set version and the reasons.
    compliance_action: Mapped[str | None] = mapped_column(String(12))
    compliance: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    brief: Mapped[dict | None] = mapped_column(JSONB)
    confidence_score: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = ts_now()
    updated_at: Mapped[datetime] = ts_now()


class OutreachMessage(Base):
    __tablename__ = "outreach_messages"
    __table_args__ = (
        CheckConstraint("status in ('" + "','".join(MESSAGE_STATUSES) + "')", name="ck_outreach_messages_status"),
        UniqueConstraint("lead_id", "step", name="uq_outreach_messages_lead_step"),
        Index("ix_outreach_messages_status", "status", "send_on"),
        Index("ix_outreach_messages_inbox_day", "sender_inbox", "send_on"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    lead_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("outreach_leads.id", ondelete="CASCADE"), nullable=False)
    step: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    to_email: Mapped[str] = mapped_column(String(320), nullable=False)
    subject: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)       # the three lines, without the footer
    footer: Mapped[str] = mapped_column(Text, nullable=False)     # legal footer with {{unsubscribe_link}} unrendered
    word_count: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="draft")
    audit: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    sender_inbox: Mapped[str | None] = mapped_column(String(320))
    send_on: Mapped[date | None] = mapped_column(Date)
    provider: Mapped[str | None] = mapped_column(String(20))
    provider_message_id: Mapped[str | None] = mapped_column(String(200))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = ts_now()


class OutreachLog(Base):
    __tablename__ = "outreach_logs"
    __table_args__ = (Index("ix_outreach_logs_lead", "lead_id", "created_at"), Index("ix_outreach_logs_kind", "kind", "created_at"))

    id: Mapped[uuid.UUID] = uuid_pk()
    lead_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("outreach_leads.id", ondelete="SET NULL"))
    # compliance | sourcing | llm_usage | research | copy | audit | queue | dispatch | webhook | unsubscribe | call_queue
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    outcome: Mapped[str] = mapped_column(String(24), nullable=False)
    detail: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = ts_now()


class OutreachSuppression(Base):
    __tablename__ = "outreach_suppression_list"
    __table_args__ = (
        CheckConstraint("kind in ('email','domain')", name="ck_outreach_suppression_kind"),
        CheckConstraint("reason in ('" + "','".join(SUPPRESSION_REASONS) + "')", name="ck_outreach_suppression_reason"),
        UniqueConstraint("kind", "value", name="uq_outreach_suppression_value"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    kind: Mapped[str] = mapped_column(String(6), nullable=False)
    value: Mapped[str] = mapped_column(String(320), nullable=False)  # lower-cased address or domain
    reason: Mapped[str] = mapped_column(String(12), nullable=False)
    source: Mapped[str] = mapped_column(String(40), nullable=False, default="")  # link | one_click | resend | operator …
    created_at: Mapped[datetime] = ts_now()


class OutreachCallQueue(Base):
    __tablename__ = "outreach_human_call_queue"
    __table_args__ = (
        CheckConstraint("scrub_status in ('cleared','needs_review')", name="ck_outreach_call_queue_scrub"),
        CheckConstraint("status in ('open','called','not_interested','interested','removed')", name="ck_outreach_call_queue_status"),
        UniqueConstraint("lead_id", name="uq_outreach_call_queue_lead"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    lead_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("outreach_leads.id", ondelete="CASCADE"), nullable=False)
    country: Mapped[str] = mapped_column(String(2), nullable=False)
    company_name: Mapped[str] = mapped_column(String(200), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(40))
    registration_number: Mapped[str | None] = mapped_column(String(40))
    # cleared = the register says the company is not advertising-protected · needs_review = the register could not
    # be asked (no CVR access) – a person must check before ringing; such rows are left out of the default export.
    scrub_status: Mapped[str] = mapped_column(String(12), nullable=False)
    scrub: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(14), nullable=False, default="open")
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = ts_now()


class OutreachTodoMark(Base):
    """A go-live point an operator ticked by hand in the admin («juristen har godkendt», «DNS er sat op» …)."""

    __tablename__ = "outreach_todo_marks"

    key: Mapped[str] = mapped_column(String(40), primary_key=True)
    done_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    done_at: Mapped[datetime] = ts_now()

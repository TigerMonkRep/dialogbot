from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.identity import ts_now, uuid_pk

# ---------------------------------------------------------------------------
# Business profile, goals and languages (O01, O03, O04, S01)
# ---------------------------------------------------------------------------


class BusinessProfile(Base):
    __tablename__ = "business_profiles"

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), primary_key=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    legal_name: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    website_url: Mapped[str | None] = mapped_column(String(500))
    # Manual setup without URL/documents is a first-class path (O01).
    manual_setup: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    cvr: Mapped[str | None] = mapped_column(String(32))
    address_line: Mapped[str | None] = mapped_column(String(300))
    postal_code: Mapped[str | None] = mapped_column(String(16))
    city: Mapped[str | None] = mapped_column(String(120))
    country: Mapped[str] = mapped_column(String(2), nullable=False, default="DK")
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="Europe/Copenhagen")
    phone: Mapped[str | None] = mapped_column(String(40))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class WorkspaceCategory(Base):
    """Multiple categories per workspace; custom categories are allowed."""

    __tablename__ = "workspace_categories"
    __table_args__ = (UniqueConstraint("workspace_id", "slug", name="uq_workspace_categories_slug"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    slug: Mapped[str] = mapped_column(String(80), nullable=False)
    label: Mapped[str] = mapped_column(String(120), nullable=False)
    is_custom: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = ts_now()


class GoalSelection(Base):
    """Product intent and selected capabilities (O03, G02)."""

    __tablename__ = "goal_selections"
    __table_args__ = (
        CheckConstraint("product_intent in ('reception','campaigns','both')", name="ck_goal_product_intent"),
        CheckConstraint("guidance_mode in ('guided','self_managed')", name="ck_goal_guidance_mode"),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), primary_key=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    product_intent: Mapped[str] = mapped_column(String(16), nullable=False, default="reception")
    guidance_mode: Mapped[str] = mapped_column(String(16), nullable=False, default="guided")
    # Reception capabilities. Callback is part of reception; booking is optional.
    inbound_phone: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    webchat: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    callback: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    booking: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Free-form conversation goals (O03) kept as data; not interpreted by code.
    conversation_goals: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class LanguageSettings(Base):
    """Four separate language levels (O04)."""

    __tablename__ = "language_settings"

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), primary_key=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    interface_language: Mapped[str] = mapped_column(String(16), nullable=False, default="da")
    default_conversation_language: Mapped[str] = mapped_column(String(16), nullable=False, default="da")
    enabled_conversation_languages: Mapped[list] = mapped_column(JSONB, nullable=False, default=lambda: ["da"])
    report_language: Mapped[str] = mapped_column(String(16), nullable=False, default="da")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


# ---------------------------------------------------------------------------
# Knowledge (K01, K03, K04, K05, O02): items with versioned content
# ---------------------------------------------------------------------------

KNOWLEDGE_KINDS = (
    "fact",
    "service",
    "coverage_area",
    "opening_hours",
    "known_answer",
    "unknown_answer",
    "offer",
)
VERSION_STATUSES = ("draft", "in_review", "approved", "superseded", "rejected")


class KnowledgeItem(Base):
    __tablename__ = "knowledge_items"
    __table_args__ = (
        UniqueConstraint("workspace_id", "kind", "key", name="uq_knowledge_items_key"),
        CheckConstraint(
            "kind in ('fact','service','coverage_area','opening_hours','known_answer','unknown_answer','offer')",
            name="ck_knowledge_items_kind",
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    key: Mapped[str] = mapped_column(String(120), nullable=False)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = ts_now()


class KnowledgeVersion(Base):
    """A versioned content snapshot of a knowledge item.

    Exactly one version per item may be 'approved' (the active, published
    version) and at most one may be an open draft ('draft' or 'in_review').
    Both invariants are enforced by partial unique indexes.
    """

    __tablename__ = "knowledge_versions"
    __table_args__ = (
        UniqueConstraint("item_id", "version_no", name="uq_knowledge_versions_no"),
        CheckConstraint(
            "status in ('draft','in_review','approved','superseded','rejected')",
            name="ck_knowledge_versions_status",
        ),
        CheckConstraint("source_type in ('manual','import','extraction')", name="ck_knowledge_versions_source"),
        Index(
            "uq_knowledge_versions_one_approved",
            "item_id",
            unique=True,
            postgresql_where=text("status = 'approved'"),
        ),
        Index(
            "uq_knowledge_versions_one_open_draft",
            "item_id",
            unique=True,
            postgresql_where=text("status in ('draft','in_review')"),
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("knowledge_items.id", ondelete="CASCADE"), nullable=False)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    content: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    # Provenance: manual entry is also a source.
    source_type: Mapped[str] = mapped_column(String(16), nullable=False, default="manual")
    source_ref: Mapped[str | None] = mapped_column(String(300))
    # Optimistic concurrency for editing an open draft.
    edit_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = ts_now()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


# ---------------------------------------------------------------------------
# Setup plan (G01–G08): persisted task state and check results
# ---------------------------------------------------------------------------


class SetupTaskState(Base):
    """Persisted per-task state that cannot be derived: skips, assignment, notes.

    Completion is derived on the server from real domain data; it is never a
    stored boolean the client could set.
    """

    __tablename__ = "setup_task_states"
    __table_args__ = (UniqueConstraint("workspace_id", "task_key", name="uq_setup_task_states_key"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    task_key: Mapped[str] = mapped_column(String(80), nullable=False)
    skipped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    skipped_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    assigned_to: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class CheckResult(Base):
    __tablename__ = "check_results"
    __table_args__ = (
        CheckConstraint("status in ('untested','passed','failed','stale')", name="ck_check_results_status"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    check_key: Mapped[str] = mapped_column(String(80), nullable=False)
    scope: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    environment: Mapped[str] = mapped_column(String(32), nullable=False)
    # Snapshot of the configuration versions the check depended on when run.
    config_versions: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    evidence: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    run_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    run_at: Mapped[datetime] = ts_now()
    stale_reason: Mapped[str | None] = mapped_column(String(300))
    stale_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


Index("ix_check_results_workspace_key", CheckResult.workspace_id, CheckResult.check_key, CheckResult.run_at)


# ---------------------------------------------------------------------------
# Durable operations: outbox, idempotency, simulated deliveries
# ---------------------------------------------------------------------------


class OutboxEvent(Base):
    __tablename__ = "outbox_events"
    __table_args__ = (
        CheckConstraint(
            "status in ('queued','processing','done','failed','blocked')", name="ck_outbox_events_status"
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"))
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    # Deterministic per business action so a re-issued command cannot enqueue twice.
    dedupe_key: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="queued")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    next_attempt_at: Mapped[datetime] = ts_now()
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_owner: Mapped[str | None] = mapped_column(String(80))
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = ts_now()
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


Index("ix_outbox_events_pick", OutboxEvent.status, OutboxEvent.next_attempt_at)


class IdempotencyKey(Base):
    __tablename__ = "idempotency_keys"
    __table_args__ = (UniqueConstraint("scope", "key", name="uq_idempotency_scope_key"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    # scope = "<user_id>:<endpoint>" so keys cannot collide across users/endpoints
    scope: Mapped[str] = mapped_column(String(200), nullable=False)
    key: Mapped[str] = mapped_column(String(200), nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    response_status: Mapped[int] = mapped_column(Integer, nullable=False)
    response_body: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = ts_now()


class EmailDelivery(Base):
    """Record produced by the email adapter. The simulated adapter never sends.

    The unique outbox_event_id guarantees that a redelivered job cannot
    produce a second delivery record for the same business event.
    """

    __tablename__ = "email_deliveries"
    __table_args__ = (
        CheckConstraint("status in ('simulated','sent','failed')", name="ck_email_deliveries_status"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    outbox_event_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("outbox_events.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"))
    adapter: Mapped[str] = mapped_column(String(32), nullable=False)
    to_email: Mapped[str] = mapped_column(String(320), nullable=False)
    subject: Mapped[str] = mapped_column(String(300), nullable=False)
    body_text: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = ts_now()
    # Provider tracking (Resend). `status` stays the send outcome ("sent" = accepted by the provider);
    # `provider_status` is the latest delivery event from the provider webhook. It never moves backwards.
    provider_message_id: Mapped[str | None] = mapped_column(String(100), unique=True)
    provider_status: Mapped[str | None] = mapped_column(String(32))
    provider_status_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class WebhookEvent(Base):
    """Inbound provider webhook, stored once per provider event id (idempotency and audit trail).

    Only events whose signature verified are stored; the raw payload is kept for support.
    """

    __tablename__ = "webhook_events"
    __table_args__ = (UniqueConstraint("provider", "event_id", name="uq_webhook_events_provider_event"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    event_id: Mapped[str] = mapped_column(String(200), nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    # applied | ignored | unmatched — what the event did to our records.
    outcome: Mapped[str] = mapped_column(String(16), nullable=False)
    received_at: Mapped[datetime] = ts_now()


class AiUsage(Base):
    """One row per AI model call: who (workspace), what (model, prompt version, knowledge revision)
    and how much (tokens, estimated cost). Rows are append-only and never contain the prompt text."""

    __tablename__ = "ai_usage"
    __table_args__ = (Index("ix_ai_usage_workspace_created", "workspace_id", "created_at"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    # assistant_preview (more purposes arrive with webchat/telephony)
    purpose: Mapped[str] = mapped_column(String(32), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    requested_model: Mapped[str] = mapped_column(String(100), nullable=False)
    served_model: Mapped[str | None] = mapped_column(String(100))
    prompt_version: Mapped[str] = mapped_column(String(32), nullable=False)
    knowledge_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    # ok | refused | truncated | error
    outcome: Mapped[str] = mapped_column(String(16), nullable=False)
    stop_reason: Mapped[str | None] = mapped_column(String(32))
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cache_creation_input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cache_read_input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Estimate from the public list price, in millionths of a US dollar; NULL for an unpriced model.
    est_cost_usd_micros: Mapped[int | None] = mapped_column(BigInteger)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    provider_request_id: Mapped[str | None] = mapped_column(String(100))
    error_code: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = ts_now()


class WaitlistSignup(Base):
    """Early-access waitlist (P00). One row per e-mail; a repeat signup updates the answers.
    Only used to tell people when access opens; no account is created."""

    __tablename__ = "waitlist_signups"

    id: Mapped[uuid.UUID] = uuid_pk()
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True)
    industry: Mapped[str | None] = mapped_column(String(32))
    interests: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    # p00 | p01 — which page the signup came from
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    # Version of the consent text shown next to the form at signup time.
    consent_version: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = ts_now()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class WebchatSettings(Base):
    """Per-workspace web widget (W01). The widget key is public (it sits in the embed code);
    what protects the widget is the origin allowlist (CSP frame-ancestors) and rate limits."""

    __tablename__ = "webchat_settings"

    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    widget_key: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    # Exact origins ("https://www.example.dk") allowed to embed the widget.
    allowed_origins: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    greeting: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # Evidence for the "widget installed" check: last time the chat frame was opened on an allowed origin.
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_seen_origin: Mapped[str | None] = mapped_column(String(200))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class Conversation(Base):
    """A customer conversation on one channel. Visitors are anonymous; they hold an opaque token
    (only its digest is stored) that lets them continue the same conversation."""

    __tablename__ = "conversations"
    __table_args__ = (Index("ix_conversations_workspace_last", "workspace_id", "last_message_at"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    channel: Mapped[str] = mapped_column(String(16), nullable=False)  # webchat
    visitor_token_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    origin: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open")
    # ai = the assistant answers; staff = a colleague has taken over and the assistant stays silent.
    mode: Mapped[str] = mapped_column(String(8), nullable=False, default="ai", server_default="ai")
    visitor_message_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = ts_now()
    last_message_at: Mapped[datetime] = ts_now()


class ConversationMessage(Base):
    __tablename__ = "conversation_messages"
    __table_args__ = (Index("ix_conversation_messages_conv_created", "conversation_id", "created_at"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    conversation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)  # visitor | assistant | staff
    text: Mapped[str] = mapped_column(Text, nullable=False)
    author_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    ai_usage_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("ai_usage.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = ts_now()


class ReceptionAgreement(Base):
    """Versioned reception price agreement (append-only; the newest version applies).

    Model A: fixed monthly subscription, no lead fee. Model B: fee per approved lead.
    Prices are the product's list prices, snapshotted per version in whole øre."""

    __tablename__ = "reception_agreements"
    __table_args__ = (UniqueConstraint("workspace_id", "version", name="uq_reception_agreements_ws_version"),
                      CheckConstraint("model in ('A','B')", name="ck_reception_agreements_model"))

    id: Mapped[uuid.UUID] = uuid_pk()
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    model: Mapped[str] = mapped_column(String(1), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="DKK")
    monthly_net_minor: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    lead_fee_net_minor: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tax_basis_points: Mapped[int] = mapped_column(Integer, nullable=False, default=2500)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = ts_now()


class Lead(Base):
    """A person who wants something from the business. Three independent axes:
    qualification (is it a real, relevant enquiry?), pipeline (what happened next?) and
    billing (was it approved as a billable lead under an agreement version?)."""

    __tablename__ = "leads"
    __table_args__ = (
        Index("ix_leads_workspace_created", "workspace_id", "created_at"),
        UniqueConstraint("conversation_id", name="uq_leads_conversation"),
        CheckConstraint("qualification_status in ('unqualified','qualified','disqualified')", name="ck_leads_qualification"),
        CheckConstraint("pipeline_status in ('new','contacted','won','lost')", name="ck_leads_pipeline"),
        CheckConstraint("billing_status in ('pending','approved','rejected')", name="ck_leads_billing"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    source: Mapped[str] = mapped_column(String(16), nullable=False)  # webchat | manual
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("conversations.id", ondelete="SET NULL"))
    contact_name: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    contact_email: Mapped[str | None] = mapped_column(String(320))
    contact_phone: Mapped[str | None] = mapped_column(String(40))
    need_summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # Callback window the customer asked for (W03–W06), in UTC; NULL = no preference.
    callback_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    callback_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    qualification_status: Mapped[str] = mapped_column(String(16), nullable=False, default="unqualified")
    qualification_reason: Mapped[str | None] = mapped_column(String(500))
    pipeline_status: Mapped[str] = mapped_column(String(16), nullable=False, default="new")
    billing_status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    # Set once by the approve/reject decision; never edited afterwards.
    billing_decided_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    billing_decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    billing_reason: Mapped[str | None] = mapped_column(String(500))
    agreement_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("reception_agreements.id", ondelete="RESTRICT"))
    fee_snapshot: Mapped[dict | None] = mapped_column(JSONB)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = ts_now()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class Task(Base):
    __tablename__ = "tasks"
    __table_args__ = (
        Index("ix_tasks_workspace_status_due", "workspace_id", "status", "due_at"),
        CheckConstraint("status in ('open','done')", name="ck_tasks_status"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    lead_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("leads.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(8), nullable=False, default="open")
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    assignee_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))  # NULL = system
    created_at: Mapped[datetime] = ts_now()
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class ReportSettings(Base):
    __tablename__ = "report_settings"

    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), primary_key=True)
    email_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    send_hour_local: Mapped[int] = mapped_column(Integer, nullable=False, default=7)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class DailyReport(Base):
    """Snapshot of one local calendar day in the workspace's time zone. Generated once after the
    day has ended; the numbers never change afterwards (today's view is computed live instead)."""

    __tablename__ = "daily_reports"
    __table_args__ = (UniqueConstraint("workspace_id", "report_date", name="uq_daily_reports_ws_date"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    report_date: Mapped[date] = mapped_column(Date, nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    data: Mapped[dict] = mapped_column(JSONB, nullable=False)
    generated_at: Mapped[datetime] = ts_now()


class PhoneNumber(Base):
    """A phone number routed to a workspace. The number is bought/imported at the provider by the
    customer; this row only maps it (by E.164 and the provider's number id) to a workspace."""

    __tablename__ = "phone_numbers"

    id: Mapped[uuid.UUID] = uuid_pk()
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    e164: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    provider: Mapped[str] = mapped_column(String(16), nullable=False, default="vapi")
    provider_number_id: Mapped[str | None] = mapped_column(String(100), unique=True)
    label: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    greeting: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # Voice: an ElevenLabs voice id (empty = VAPI_VOICE_JSON or the provider's default voice) and model.
    voice_id: Mapped[str] = mapped_column(String(64), nullable=False, default="", server_default="")
    voice_model: Mapped[str] = mapped_column(String(40), nullable=False, default="eleven_multilingual_v2",
                                             server_default="eleven_multilingual_v2")
    # Free-text speaking style from the business (tone, "du"/"De", regional words). Never overrides facts.
    speaking_style: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    created_at: Mapped[datetime] = ts_now()


class Call(Base):
    """One phone call reported by the voice provider (end-of-call report)."""

    __tablename__ = "calls"
    __table_args__ = (Index("ix_calls_workspace_started", "workspace_id", "started_at"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    phone_number_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("phone_numbers.id", ondelete="SET NULL"))
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("conversations.id", ondelete="SET NULL"))
    provider: Mapped[str] = mapped_column(String(16), nullable=False)
    provider_call_id: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    from_number: Mapped[str | None] = mapped_column(String(40))
    to_number: Mapped[str | None] = mapped_column(String(40))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_seconds: Mapped[int | None] = mapped_column(Integer)
    ended_reason: Mapped[str | None] = mapped_column(String(100))
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # Provider-reported total cost, millionths of a USD (NULL if not reported).
    cost_usd_micros: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = ts_now()


class SourceImport(Base):
    """One run of "suggest knowledge from our website": pages fetched, suggestions created as drafts.

    Suggestions are ordinary knowledge drafts (source_type 'extraction'); nothing reaches the
    assistant before a person approves it."""

    __tablename__ = "source_imports"
    __table_args__ = (
        CheckConstraint("status in ('running','done','failed')", name="ck_source_imports_status"),
        Index("ix_source_imports_workspace_created", "workspace_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="running")
    pages: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    created_items: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    skipped: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Verified company details (description, cvr, phone, address) the owner can accept into the profile.
    profile_suggestion: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    error: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = ts_now()
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ReceptionScript(Base):
    """The receptionist's manuscript (R05), edited by owner/admin and used in every channel's prompt.

    It shapes how the assistant talks and what it asks for; it never adds facts – those come only
    from approved knowledge."""

    __tablename__ = "reception_scripts"

    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    persona_name: Mapped[str] = mapped_column(String(60), nullable=False, default="")
    address_form: Mapped[str] = mapped_column(String(8), nullable=False, default="du")
    greeting: Mapped[str] = mapped_column(Text, nullable=False, default="")
    collect: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    escalation: Mapped[str] = mapped_column(Text, nullable=False, default="")
    avoid: Mapped[str] = mapped_column(Text, nullable=False, default="")
    closing: Mapped[str] = mapped_column(Text, nullable=False, default="")
    updated_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(),
                                                 onupdate=func.now())


class NotificationRead(Base):
    """When a user last opened the notification list in a workspace. Notifications themselves are
    derived from real events (leads, calls, tasks, conversations, drafts), never stored copies."""

    __tablename__ = "notification_reads"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), primary_key=True)
    seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

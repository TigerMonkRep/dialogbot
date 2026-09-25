from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
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

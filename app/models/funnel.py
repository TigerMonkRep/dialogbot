"""Quiz-funnel drafts (app/modules/funnel): what a visitor answers on /start or /privat/start BEFORE they have an
account. A draft carries no identity until the gate (name, e-mail, mobile) and is deleted by the worker seven days
after it was created unless it was verified and attached to a user."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.identity import ts_now, uuid_pk


class FunnelDraft(Base):
    __tablename__ = "funnel_drafts"
    __table_args__ = (
        CheckConstraint("kind in ('erhverv','privat')", name="ck_funnel_drafts_kind"),
        Index("ix_funnel_drafts_expires", "expires_at"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    hook: Mapped[str | None] = mapped_column(String(80))
    industry: Mapped[str | None] = mapped_column(String(40))  # funnel key (estimates.INDUSTRIES)
    utm: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    step: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    answers: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    # Erhverv: what the Places lookup found about the company (name, address, phone, website, hours, place_id).
    company: Mapped[dict | None] = mapped_column(JSONB)
    estimate: Mapped[dict | None] = mapped_column(JSONB)
    # What was built while the visitor answered (erhverv: knowledge/voice/hours/number; privat: tasks/lists/first_call).
    build: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    place_id: Mapped[str | None] = mapped_column(String(320))
    website: Mapped[str | None] = mapped_column(String(500))
    # After the gate: {name, email, phone_e164, consent_at, consent_version, verified_at}. Nothing before it.
    gate: Mapped[dict | None] = mapped_column(JSONB)
    # The pending SMS code: only an HMAC is stored (same pattern as private_profiles); 10 minutes; 5 attempts.
    code_hash: Mapped[str | None] = mapped_column(String(64))
    code_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    code_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    code_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("workspaces.id", ondelete="SET NULL"))
    demo_call_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("demo_calls.id", ondelete="SET NULL"))
    crawl_job_ref: Mapped[str | None] = mapped_column(String(80))  # source_imports.id once the import runs
    created_at: Mapped[datetime] = ts_now()
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(),
                                                 onupdate=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

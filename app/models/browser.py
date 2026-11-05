"""Browser worker: tethered browser runs for booking on external public booking pages (docs/ADR-004-browser-worker.md).

A run belongs to ONE Privat task (and its personal workspace). `steps` and `evidence_urls` are internal: the API returns
them without selectors and with signed, short-lived evidence links (app/modules/browser/service.py).
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Float, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.identity import ts_now, uuid_pk

BROWSER_RUN_STATUSES = ("planned", "running", "awaiting_approval", "approved", "done", "failed", "fallback_phone")
BROWSER_RUN_MODES = ("playbook", "llm")


class BrowserRun(Base):
    __tablename__ = "browser_runs"
    __table_args__ = (
        CheckConstraint("status in ('planned','running','awaiting_approval','approved','done','failed','fallback_phone')",
                        name="ck_browser_runs_status"),
        CheckConstraint("mode is null or mode in ('playbook','llm')", name="ck_browser_runs_mode"),
        Index("ix_browser_runs_ws_status", "workspace_id", "status"),
        Index("ix_browser_runs_task", "task_id"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("private_tasks.id", ondelete="CASCADE"), nullable=False)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    # onlinebooq | easypractice | dinnerbooking | unknown ...
    engine: Mapped[str] = mapped_column(String(32), nullable=False, default="unknown")
    # playbook | llm: how the run is driven. Only a playbook run can be replayed after the approval TTL has expired.
    mode: Mapped[str | None] = mapped_column(String(12))
    allowed_domains: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    # {intent: book|flyt|aflys, service, preferred_windows: [{date, from, to}], contact: {name, phone, mail}}
    goal: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="planned")
    # [{n, tool, arg, result, screenshot_url, at}] – internal; the API strips refs/selectors
    steps: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    # The filled-in proposal the user approves: {service, staff, date, time, price, name ...}
    before_after: Mapped[dict | None] = mapped_column(JSONB)
    # [{kind: screenshot|video|receipt_pdf, key, name}] – STORAGE KEYS in the private bucket; signed when read
    evidence_urls: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    result: Mapped[dict | None] = mapped_column(JSONB)
    max_steps: Mapped[int] = mapped_column(Integer, nullable=False, default=25, server_default="25")
    max_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=180, server_default="180")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    awaiting_since: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(40))
    cost_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    created_at: Mapped[datetime] = ts_now()


class BusinessBookingProfile(Base):
    """Which booking engine a business uses, found once from its public website (browser_worker/engine_detect.py).
    Public information about a business, shared across workspaces; it holds no user data."""

    __tablename__ = "business_booking_profiles"
    __table_args__ = (
        Index("ix_business_booking_profiles_cvr", "cvr"),
        Index("ix_business_booking_profiles_phone", "phone_e164"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    website_host: Mapped[str] = mapped_column(String(253), nullable=False, unique=True)
    website: Mapped[str] = mapped_column(String(500), nullable=False)
    cvr: Mapped[str | None] = mapped_column(String(8))
    phone_e164: Mapped[str | None] = mapped_column(String(20))
    engine: Mapped[str] = mapped_column(String(32), nullable=False, default="unknown")
    booking_url: Mapped[str | None] = mapped_column(String(1000))
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    detected_at: Mapped[datetime] = ts_now()


class ExternalBusinessContact(Base):
    """A business that is NOT a Dialogbot customer, as far as we know: what we looked up about it once, so we do not pay for the
    same lookup twice (CVR register, Google Places). Used by the assistant's booking (A5) and by the lead loop (B).

    Public facts only. Google Places content (website, phone, opening hours) is dropped after GOOGLE_PLACES_CACHE_DAYS and only
    `place_id` is kept (Google's caching rules, see app/modules/privat/places.py). `email` exists only after an explicit yes
    (lead loop); nothing in the booking flow writes it."""

    __tablename__ = "external_business_contacts"
    __table_args__ = (
        CheckConstraint("last_outcome in ('interested','declined','skipped','not_asked')", name="ck_external_business_contacts_outcome"),
        Index("uq_external_business_contacts_cvr", "cvr", unique=True, postgresql_where="cvr is not null"),
        Index("uq_external_business_contacts_phone", "phone_e164", unique=True, postgresql_where="phone_e164 is not null"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    cvr: Mapped[str | None] = mapped_column(String(8))
    phone_e164: Mapped[str | None] = mapped_column(String(20))
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    # Only ever from Google Places (the CVR register's «website» entries are not trusted); dropped with the other Google content.
    website: Mapped[str | None] = mapped_column(String(500))
    # which booking engine the website uses (found once, browser_worker/engine_detect.py)
    booking_profile_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("business_booking_profiles.id", ondelete="SET NULL"))
    is_dialogbot_customer: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    blocklisted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    blocklist_reason: Mapped[str | None] = mapped_column(String(40))
    last_pitch_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    pitch_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    last_outcome: Mapped[str] = mapped_column(String(16), nullable=False, default="not_asked", server_default="not_asked")
    email: Mapped[str | None] = mapped_column(String(320))
    # The yes behind `email`: set together with it, only after the business said «ja, send en mail» and gave the address.
    consent_to_email: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    consent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # The lead in the sales workspace (one per business: a repeat updates it, it never makes a second)
    lead_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("leads.id", ondelete="SET NULL", name="fk_external_business_contacts_lead_id"))
    # --- lookup cache (A5) ---
    lookup_key: Mapped[str | None] = mapped_column(String(300), unique=True)   # «navn|by», normalised
    address: Mapped[str | None] = mapped_column(String(300))
    city: Mapped[str | None] = mapped_column(String(100))
    place_id: Mapped[str | None] = mapped_column(String(300))
    opening_hours: Mapped[list | None] = mapped_column(JSONB)                  # Google periods; dropped with the other Google content
    advertising_protected: Mapped[bool | None] = mapped_column()               # CVR «reklamebeskyttet»; None = the register did not say
    cvr_looked_up_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    google_looked_up_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = ts_now()

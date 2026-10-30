"""Dialogbot's internal sales channel (operator-only): companies found via Google Places, facts with sources,
profiles, personal scripts for Peter and simulated conversations.

These tables are global (no workspace_id): access goes through the `operator` dependency, never through a workspace a
client names. Calls, conversations and leads stay in the sales workspace (SALES_WORKSPACE_ID) in later phases.

Google's terms (Maps Platform): `google_place_id` may be kept permanently; every other Google field carries
`google_fetched_at` and is refreshed or cleared after GOOGLE_PLACES_CACHE_DAYS (see app/modules/sales/search.py).
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.identity import ts_now, uuid_pk


class SalesIndustry(Base):
    """An industry the operator added or changed in the admin. Overrides the same key in sales/script.INDUSTRIES."""

    __tablename__ = "sales_industries"

    key: Mapped[str] = mapped_column(String(40), primary_key=True)
    label: Mapped[str] = mapped_column(String(120), nullable=False)
    google_types: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    search_terms: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = ts_now()


class SalesSearchJob(Base):
    """One search for companies (industry × area), run by the worker in the background with progress and a budget."""

    __tablename__ = "sales_search_jobs"
    __table_args__ = (
        CheckConstraint("status in ('queued','running','paused','done','failed','cancelled')",
                        name="ck_sales_search_jobs_status"),
        CheckConstraint("source in ('google','demo','import')", name="ck_sales_search_jobs_source"),
        CheckConstraint("geo_kind in ('place','postal_codes','radius')", name="ck_sales_search_jobs_geo_kind"),
        Index("ix_sales_search_jobs_status", "status", "created_at"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    industry_keys: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    google_types: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    keywords: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    geo_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    geo: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    max_results: Mapped[int] = mapped_column(Integer, nullable=False)
    exclude_existing_customers: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    source: Mapped[str] = mapped_column(String(12), nullable=False)  # google | demo (no API key) | import
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="queued")
    # {examined, found, skipped, incomplete, duplicates, requests_used, estimated_cost_minor, reasons{}, areas_done}
    progress: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    # {estimate: {...}, requests_used, details_used, day_cap}
    budget: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    # Work list: [{area: {...}, query: {...}}] and the index of the next one, so a resumed job continues.
    plan: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    cursor: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = ts_now()
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SalesCompany(Base):
    """A company found by a search or imported. Duplicate keys: google_place_id, cvr, (domain, postal_code), phone.
    Signals that disagree mark a "possible duplicate" instead of merging."""

    __tablename__ = "sales_companies"
    __table_args__ = (
        CheckConstraint("research_status in ('found','researched','profiled','incomplete')",
                        name="ck_sales_companies_research_status"),
        CheckConstraint("source in ('google','demo','import')", name="ck_sales_companies_source"),
        Index("ix_sales_companies_domain", "domain"),
        Index("ix_sales_companies_phone", "main_phone_e164"),
        Index("ix_sales_companies_postal", "postal_code"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    source: Mapped[str] = mapped_column(String(12), nullable=False)
    google_place_id: Mapped[str | None] = mapped_column(String(300), unique=True)
    google_fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    google_types: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    google_primary_type: Mapped[str | None] = mapped_column(String(80))
    google_business_status: Mapped[str | None] = mapped_column(String(40))
    google_maps_uri: Mapped[str | None] = mapped_column(String(500))
    google_opening_hours: Mapped[list | None] = mapped_column(JSONB)
    rating: Mapped[float | None] = mapped_column(Float)
    user_rating_count: Mapped[int | None] = mapped_column(Integer)
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    cvr: Mapped[str | None] = mapped_column(String(8), unique=True)
    legal_name: Mapped[str | None] = mapped_column(String(200))
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    industry_key: Mapped[str | None] = mapped_column(String(40))
    industry_code: Mapped[str | None] = mapped_column(String(10))
    industry_text: Mapped[str | None] = mapped_column(String(200))
    address_line: Mapped[str | None] = mapped_column(String(300))
    postal_code: Mapped[str | None] = mapped_column(String(8))
    city: Mapped[str | None] = mapped_column(String(120))
    municipality_code: Mapped[str | None] = mapped_column(String(8))
    domain: Mapped[str | None] = mapped_column(String(200))
    website_url: Mapped[str | None] = mapped_column(String(500))
    main_phone_e164: Mapped[str | None] = mapped_column(String(20))
    public_email: Mapped[str | None] = mapped_column(String(320))
    cvr_status: Mapped[str | None] = mapped_column(String(80))
    advertising_protected: Mapped[bool | None] = mapped_column(Boolean)  # None = unknown, never "may be contacted"
    relevance_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    relevance_reasons: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    data_quality: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    research_status: Mapped[str] = mapped_column(String(16), nullable=False, default="found")
    researched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    research_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # set while running
    research_error: Mapped[str | None] = mapped_column(String(300))
    possible_duplicate_of: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("sales_companies.id", ondelete="SET NULL"))
    duplicate_reason: Mapped[str | None] = mapped_column(String(200))
    existing_customer_workspace_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("workspaces.id", ondelete="SET NULL"))
    last_search_job_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("sales_search_jobs.id", ondelete="SET NULL"))
    first_seen_at: Mapped[datetime] = ts_now()
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(),
                                                 onupdate=func.now())


class SalesSourceFact(Base):
    """One fact about a company with where it came from: `google_place:<id>`, a page URL or `import`/`cvr`."""

    __tablename__ = "sales_source_facts"
    __table_args__ = (
        CheckConstraint("confidence in ('high','medium','low')", name="ck_sales_source_facts_confidence"),
        Index("ix_sales_source_facts_company", "company_id", "field"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sales_companies.id", ondelete="CASCADE"), nullable=False)
    field: Mapped[str] = mapped_column(String(40), nullable=False)
    value: Mapped[str] = mapped_column(String(500), nullable=False)
    url_or_ref: Mapped[str] = mapped_column(String(500), nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    evidence: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    confidence: Mapped[str] = mapped_column(String(8), nullable=False)
    extractor_version: Mapped[str] = mapped_column(String(40), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = ts_now()


class SalesContact(Base):
    __tablename__ = "sales_contacts"
    __table_args__ = (
        CheckConstraint("status in ('unverified','verified','invalid')", name="ck_sales_contacts_status"),
        Index("ix_sales_contacts_company", "company_id"),
        Index("ix_sales_contacts_phone", "phone_e164"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sales_companies.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str | None] = mapped_column(String(200))
    role: Mapped[str | None] = mapped_column(String(120))
    phone_e164: Mapped[str | None] = mapped_column(String(20))
    email: Mapped[str | None] = mapped_column(String(320))
    source_fact_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("sales_source_facts.id", ondelete="SET NULL"))
    is_main_number: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="unverified")
    created_at: Mapped[datetime] = ts_now()


class SalesProfile(Base):
    """A versioned sales profile: at most 3 verified facts (each pointing to a source fact), at most 2 hypotheses
    (always phrased as questions) and the service Dialogbot would start with."""

    __tablename__ = "sales_profiles"
    __table_args__ = (UniqueConstraint("company_id", "version", name="uq_sales_profiles_version"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sales_companies.id", ondelete="CASCADE"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    facts: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    hypotheses: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    relevant_service: Mapped[str] = mapped_column(Text, nullable=False, default="")
    why_relevant: Mapped[str] = mapped_column(Text, nullable=False, default="")
    knowledge_revision: Mapped[int | None] = mapped_column(Integer)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = ts_now()


class SalesScript(Base):
    """A personal script for Peter (fixed JSON schema + the rendered runtime instruction), bound to the profile
    version, the knowledge revision, the offer (later phases) and the script version `peter-sales-v1`."""

    __tablename__ = "sales_scripts"
    __table_args__ = (
        UniqueConstraint("company_id", "version", name="uq_sales_scripts_version"),
        CheckConstraint("status in ('draft','approved','superseded')", name="ck_sales_scripts_status"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sales_companies.id", ondelete="CASCADE"), nullable=False)
    profile_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sales_profiles.id", ondelete="CASCADE"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    script_version: Mapped[str] = mapped_column(String(32), nullable=False)
    offer_id: Mapped[uuid.UUID | None] = mapped_column()  # FK to sales_offers arrives with phase 3
    body: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    rendered_prompt: Mapped[str] = mapped_column(Text, nullable=False, default="")
    validation: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="draft")
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    approved_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = ts_now()


class SalesSimulation(Base):
    """A simulated conversation between Peter and an AI "customer". Never a real call; always simulated=true."""

    __tablename__ = "sales_simulations"
    __table_args__ = (CheckConstraint("simulated", name="ck_sales_simulations_simulated"),
                      Index("ix_sales_simulations_company", "company_id", "created_at"))

    id: Mapped[uuid.UUID] = uuid_pk()
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sales_companies.id", ondelete="CASCADE"), nullable=False)
    script_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sales_scripts.id", ondelete="CASCADE"), nullable=False)
    persona: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    transcript: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    outcome: Mapped[str | None] = mapped_column(String(24))
    partial_accepts: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    would_call: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)  # tool calls logged, never executed
    error: Mapped[str | None] = mapped_column(String(300))
    simulated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = ts_now()


class SalesIntegrationNote(Base):
    """Operator override of the integration register: what Peter may say about a system (e.g. a booking system)."""

    __tablename__ = "sales_integration_notes"
    __table_args__ = (CheckConstraint("status in ('AKTIV','KRÆVER_OPSÆTNING','PLANLAGT','UKENDT')",
                                      name="ck_sales_integration_notes_status"),)

    system: Mapped[str] = mapped_column(String(80), primary_key=True)  # normalised name, e.g. "planway"
    label: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    note: Mapped[str] = mapped_column(Text, nullable=False, default="")
    updated_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(),
                                                 onupdate=func.now())

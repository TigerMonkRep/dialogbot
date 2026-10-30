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
    offer_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("sales_offers.id", ondelete="SET NULL"))
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


# --------------------------------------------------------------------------- phase 2: basis, policy, calls


class SalesContactBasis(Base):
    """The documented basis for contacting one person/number on one channel for one purpose. An AI call needs a
    prior request or consent (markedsføringsloven § 10 stk. 1, also for businesses); without a valid, unwithdrawn,
    unexpired row the contact policy never answers ALLOW."""

    __tablename__ = "sales_contact_basis"
    __table_args__ = (
        CheckConstraint("channel in ('ai_call','human_call','email','sms')", name="ck_sales_contact_basis_channel"),
        CheckConstraint("kind in ('request','consent')", name="ck_sales_contact_basis_kind"),
        CheckConstraint("source in ('web_form','seller','lead','import','test')", name="ck_sales_contact_basis_source"),
        Index("ix_sales_contact_basis_contact", "contact_id", "channel"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    contact_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sales_contacts.id", ondelete="CASCADE"), nullable=False)
    channel: Mapped[str] = mapped_column(String(12), nullable=False)
    purpose: Mapped[str] = mapped_column(String(200), nullable=False)
    kind: Mapped[str] = mapped_column(String(10), nullable=False)
    text_version: Mapped[str] = mapped_column(String(40), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(12), nullable=False)
    evidence_ref: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    withdrawn_reason: Mapped[str | None] = mapped_column(String(300))
    recorded_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = ts_now()


class SalesBlockList(Base):
    """Never contact this phone/domain/CVR for Dialogbot's own sales. Global across internal campaigns; reveals
    nothing between customers' workspaces (their DoNotCall lists stay their own)."""

    __tablename__ = "sales_block_list"
    __table_args__ = (
        UniqueConstraint("kind", "value", name="uq_sales_block_list_value"),
        CheckConstraint("kind in ('phone','domain','cvr')", name="ck_sales_block_list_kind"),
        CheckConstraint("source in ('call','manual','dispute')", name="ck_sales_block_list_source"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    kind: Mapped[str] = mapped_column(String(8), nullable=False)
    value: Mapped[str] = mapped_column(String(200), nullable=False)
    reason: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    source: Mapped[str] = mapped_column(String(8), nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = ts_now()


class SalesPolicyDecision(Base):
    """One evaluation of the contact policy, kept so every call (and every refusal) can be explained later."""

    __tablename__ = "sales_policy_decisions"
    __table_args__ = (
        CheckConstraint("stage in ('plan','dispatch','check')", name="ck_sales_policy_decisions_stage"),
        CheckConstraint("result in ('ALLOW','BLOCK','NEEDS_REVIEW')", name="ck_sales_policy_decisions_result"),
        Index("ix_sales_policy_decisions_contact", "contact_id", "decided_at"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    contact_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sales_contacts.id", ondelete="CASCADE"), nullable=False)
    campaign_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("campaigns.id", ondelete="CASCADE"))
    stage: Mapped[str] = mapped_column(String(10), nullable=False)
    result: Mapped[str] = mapped_column(String(14), nullable=False)
    reasons: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    evidence: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    decided_at: Mapped[datetime] = ts_now()


class SalesCallEvent(Base):
    """Provider events for an internal sales call (ringing, answered, ended, the assistant snapshot). No personal data
    beyond what the call row already holds."""

    __tablename__ = "sales_call_events"
    __table_args__ = (Index("ix_sales_call_events_call", "provider_call_id", "received_at"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    campaign_contact_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("campaign_contacts.id", ondelete="CASCADE"))
    provider_call_id: Mapped[str | None] = mapped_column(String(100))
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    received_at: Mapped[datetime] = ts_now()


class SalesQualification(Base):
    """One of Peter's five partial accepts on a real call, with the customer's own words as evidence."""

    __tablename__ = "sales_qualifications"
    __table_args__ = (
        CheckConstraint("accept_no between 1 and 5", name="ck_sales_qualifications_no"),
        CheckConstraint("result in ('JA','NEJ','BETINGET','IKKE_AFKLARET')", name="ck_sales_qualifications_result"),
        UniqueConstraint("call_id", "accept_no", name="uq_sales_qualifications_call_no"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    call_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("calls.id", ondelete="CASCADE"), nullable=False)
    accept_no: Mapped[int] = mapped_column(Integer, nullable=False)
    result: Mapped[str] = mapped_column(String(14), nullable=False)
    quote: Mapped[str | None] = mapped_column(Text)
    message_index: Mapped[int | None] = mapped_column(Integer)
    note: Mapped[str] = mapped_column(Text, nullable=False, default="")


class SalesOpenQuestion(Base):
    """A question Peter could not answer from approved knowledge. Turned into a knowledge draft by an operator."""

    __tablename__ = "sales_open_questions"
    __table_args__ = (CheckConstraint("status in ('open','answered','dismissed')", name="ck_sales_open_questions_status"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    company_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("sales_companies.id", ondelete="CASCADE"))
    call_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("calls.id", ondelete="SET NULL"))
    question: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="open")
    knowledge_item_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("knowledge_items.id", ondelete="SET NULL"))
    assignee_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = ts_now()


# --------------------------------------------------------------------------- phase 3: offers, messages, meetings


class SalesOffer(Base):
    """A written offer for one company. Amounts are copied from billing/prices.py when the offer is created – never
    free amounts. The accept link carries a random token; only its SHA-256 is stored. `sent` is not an order: the
    customer accepts on the public page, which creates the reception agreement (`agreement_id`)."""

    __tablename__ = "sales_offers"
    __table_args__ = (
        CheckConstraint("setup_kind in ('diy','specialist')", name="ck_sales_offers_setup_kind"),
        CheckConstraint("status in ('draft','sent','accepted','expired','cancelled')", name="ck_sales_offers_status"),
        CheckConstraint("sent_via is null or sent_via in ('email','sms','manual')", name="ck_sales_offers_sent_via"),
        UniqueConstraint("company_id", "version", name="uq_sales_offers_company_version"),
        Index("ix_sales_offers_status", "status", "created_at"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sales_companies.id", ondelete="CASCADE"), nullable=False)
    contact_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("sales_contacts.id", ondelete="SET NULL"))
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    package: Mapped[str] = mapped_column(String(20), nullable=False, default="reception")
    monthly_net_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    setup_kind: Mapped[str] = mapped_column(String(10), nullable=False)
    setup_net_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    campaign_call_net_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    campaign_minute_net_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    inbound_included_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    inbound_extra_minute_net_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    terms_version: Mapped[str] = mapped_column(String(40), nullable=False)
    tax_basis_points: Mapped[int] = mapped_column(Integer, nullable=False)
    valid_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="draft")
    accept_token_hash: Mapped[str | None] = mapped_column(String(64), unique=True)
    sent_via: Mapped[str | None] = mapped_column(String(8))
    sent_to: Mapped[str | None] = mapped_column(String(320))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    accepted_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    agreement_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("reception_agreements.id", ondelete="SET NULL"))
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("workspaces.id", ondelete="SET NULL"))
    first_invoice_paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = ts_now()


class SalesMessageRequest(Base):
    """A customer's request on a call ("send me the link") and what happened to it. `sent` only after the e-mail or
    SMS provider accepted it; a destination that does not match the contact waits for an operator (`requested`)."""

    __tablename__ = "sales_message_requests"
    __table_args__ = (
        CheckConstraint("kind in ('order_link','offer_summary')", name="ck_sales_message_requests_kind"),
        CheckConstraint("channel in ('email','sms')", name="ck_sales_message_requests_channel"),
        CheckConstraint("status in ('requested','sent','failed','cancelled')", name="ck_sales_message_requests_status"),
        Index("ix_sales_message_requests_status", "status", "created_at"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sales_companies.id", ondelete="CASCADE"), nullable=False)
    contact_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("sales_contacts.id", ondelete="SET NULL"))
    offer_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("sales_offers.id", ondelete="SET NULL"))
    campaign_contact_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("campaign_contacts.id", ondelete="SET NULL"))
    provider_call_id: Mapped[str | None] = mapped_column(String(100))
    kind: Mapped[str] = mapped_column(String(14), nullable=False)
    channel: Mapped[str] = mapped_column(String(6), nullable=False)
    destination: Mapped[str] = mapped_column(String(320), nullable=False)
    requested_quote: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="requested")
    outbox_event_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("outbox_events.id", ondelete="SET NULL"))
    error: Mapped[str | None] = mapped_column(String(300))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = ts_now()


class SalesMeeting(Base):
    """An intro meeting with a company, backed by a booking in the sales workspace. `confirmed` only when the booking
    was created; the booking's own status (cancelled) wins when the two disagree."""

    __tablename__ = "sales_meetings"
    __table_args__ = (
        CheckConstraint("status in ('proposed','confirmed','cancelled','held','no_show')", name="ck_sales_meetings_status"),
        Index("ix_sales_meetings_company", "company_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sales_companies.id", ondelete="CASCADE"), nullable=False)
    contact_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("sales_contacts.id", ondelete="SET NULL"))
    booking_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("bookings.id", ondelete="SET NULL"))
    campaign_contact_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("campaign_contacts.id", ondelete="SET NULL"))
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="proposed")
    calendar_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    note: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = ts_now()


# --------------------------------------------------------------------------- phase 4: audio, access log, data requests


class CallRecording(Base):
    """The audio of one internal sales call, in a private bucket. Status mirrors `calls.recording_status`."""

    __tablename__ = "call_recordings"
    __table_args__ = (
        CheckConstraint("status in ('PENDING','AVAILABLE','FAILED','NOT_RECORDED','DELETED')",
                        name="ck_call_recordings_status"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    call_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("calls.id", ondelete="CASCADE"), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(14), nullable=False, default="PENDING")
    storage_key: Mapped[str | None] = mapped_column(String(300))
    bytes: Mapped[int | None] = mapped_column(Integer)
    duration_seconds: Mapped[int | None] = mapped_column(Integer)
    content_type: Mapped[str | None] = mapped_column(String(60))
    provider_ref: Mapped[str | None] = mapped_column(String(100))
    available_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    delete_reason: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = ts_now()


class SalesMediaAccessLog(Base):
    """Every play or export of a sales call recording."""

    __tablename__ = "sales_media_access_log"
    __table_args__ = (
        CheckConstraint("kind in ('play','export')", name="ck_sales_media_access_log_kind"),
        Index("ix_sales_media_access_log_call", "call_id", "at"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    call_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("calls.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    kind: Mapped[str] = mapped_column(String(8), nullable=False)
    at: Mapped[datetime] = ts_now()


class SalesDataRequest(Base):
    """A data subject's request about Dialogbot's own sales: access, erasure or objection."""

    __tablename__ = "sales_data_requests"
    __table_args__ = (
        CheckConstraint("subject in ('phone','email','cvr')", name="ck_sales_data_requests_subject"),
        CheckConstraint("kind in ('access','erasure','objection')", name="ck_sales_data_requests_kind"),
        CheckConstraint("status in ('open','done','rejected')", name="ck_sales_data_requests_status"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    subject: Mapped[str] = mapped_column(String(8), nullable=False)
    value: Mapped[str] = mapped_column(String(320), nullable=False)
    kind: Mapped[str] = mapped_column(String(10), nullable=False)
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="open")
    handled_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    handled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    result: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = ts_now()

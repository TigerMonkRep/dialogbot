"""Dialogbot's internal sales channel: /operator/salg/* (platform operators only).

Every route needs `operator`; nothing here is scoped by a workspace the client names. With SALES_OUTBOUND_MODE=off
every route answers 501 `sales_channel_off`, except GET /operator/salg, which says what is missing.
"""
from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Literal

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session as OrmSession

from app.core.audit import record_audit
from app.core.auth import Principal
from app.core.errors import Conflict, NotFound
from app.db import get_db
from app.models import (
    SalesCompany,
    SalesMeeting,
    SalesMessageRequest,
    SalesOffer,
    SalesProfile,
    SalesScript,
    SalesSearchJob,
    SalesSimulation,
)
from app.modules.sales import channel, companies, integrations, playbook, search, simulate
from app.modules.voices.operator_router import operator

router = APIRouter(prefix="/operator/salg", tags=["sales-channel"])
log = structlog.get_logger("dialogbot.sales.channel")


def _calls_today(db: OrmSession, now: datetime) -> int:
    from zoneinfo import ZoneInfo

    from app.models import Campaign, CampaignCall

    start = now.astimezone(ZoneInfo("Europe/Copenhagen")).replace(hour=0, minute=0, second=0, microsecond=0)
    return db.scalar(select(func.count()).select_from(CampaignCall).join(Campaign, Campaign.id == CampaignCall.campaign_id)
                     .where(Campaign.kind == "internal_sales", CampaignCall.dialled_at >= start)) or 0


def research_gate(_: Principal = Depends(operator)) -> None:
    channel.require(channel.RESEARCH_MODES)


def simulation_gate(_: Principal = Depends(operator)) -> None:
    channel.require(channel.SIMULATION_MODES)


def _company(db: OrmSession, company_id: uuid.UUID) -> SalesCompany:
    c = db.get(SalesCompany, company_id)
    if c is None:
        raise NotFound("Virksomheden findes ikke")
    return c


# --------------------------------------------------------------------------- status and overview


@router.get("")
def overview(db: OrmSession = Depends(get_db), _: Principal = Depends(operator)):
    """Status (what works, what is missing) and the overview tiles. Works in every mode, also `off`."""
    now = datetime.now(UTC)
    since = now - timedelta(days=30)
    count = lambda q: db.scalar(select(func.count()).select_from(q.subquery())) or 0  # noqa: E731
    tiles = {
        "companies_new_30d": count(select(SalesCompany.id).where(SalesCompany.first_seen_at >= since)),
        "companies_total": count(select(SalesCompany.id)),
        "researched": count(select(SalesCompany.id).where(SalesCompany.research_status.in_(("researched", "profiled")))),
        "scripts_approved": count(select(SalesScript.id).where(SalesScript.status == "approved")),
        "simulations_30d": count(select(SalesSimulation.id).where(SalesSimulation.created_at >= since)),
        "searches_running": count(select(SalesSearchJob.id).where(SalesSearchJob.status.in_(("queued", "running")))),
        "calls_today": _calls_today(db, now),
        "meetings_upcoming": count(select(SalesMeeting.id).where(SalesMeeting.status == "confirmed",
                                                                 SalesMeeting.starts_at >= now)),
        "offers_open": count(select(SalesOffer.id).where(SalesOffer.status == "sent", SalesOffer.valid_until > now)),
        "orders_accepted_30d": count(select(SalesOffer.id).where(SalesOffer.accepted_at >= since)),
        "paying_customers": count(select(SalesOffer.company_id).where(SalesOffer.first_invoice_paid_at.is_not(None))
                                  .distinct()),
    }
    needs_you = []
    for j in db.scalars(select(SalesSearchJob).where(SalesSearchJob.status.in_(("paused", "failed")))
                        .order_by(SalesSearchJob.created_at.desc()).limit(10)):
        needs_you.append({"kind": "search_" + j.status, "id": str(j.id), "text": j.error or "Søgningen er stoppet"})
    for c in db.scalars(select(SalesCompany).where(SalesCompany.research_error.is_not(None))
                        .order_by(SalesCompany.updated_at.desc()).limit(10)):
        needs_you.append({"kind": "research_failed", "id": str(c.id), "text": f"{c.display_name}: {c.research_error}"})
    for s in db.scalars(select(SalesScript).where(SalesScript.status == "draft")
                        .order_by(SalesScript.created_at.desc()).limit(10)):
        c = db.get(SalesCompany, s.company_id)
        ok = (s.validation or {}).get("ok")
        needs_you.append({"kind": "script_draft", "id": str(s.company_id),
                          "text": f"{c.display_name}: manuskript v{s.version} {'klar til godkendelse' if ok else 'har valideringsfejl'}"})
    from app.models import Campaign, CampaignContact

    for cc in db.scalars(select(CampaignContact).join(Campaign, Campaign.id == CampaignContact.campaign_id)
                         .where(Campaign.kind == "internal_sales", CampaignContact.status.in_(("unknown", "failed")))
                         .order_by(CampaignContact.last_attempt_at.desc()).limit(10)):
        needs_you.append({"kind": "call_" + cc.status, "id": str(cc.id), "text": f"{cc.company}: {cc.error or cc.status}"})
    for r in db.scalars(select(SalesMessageRequest).where(SalesMessageRequest.status.in_(("requested", "failed")),
                                                          SalesMessageRequest.outbox_event_id.is_(None))
                        .order_by(SalesMessageRequest.created_at.desc()).limit(10)):
        c = db.get(SalesCompany, r.company_id)
        needs_you.append({"kind": "message_" + r.status, "id": str(r.company_id),
                          "text": f"{c.display_name}: link til {r.destination} " + (
                              "venter på, at du bekræfter adressen" if r.status == "requested" else f"fejlede ({r.error})")})
    for o in db.scalars(select(SalesOffer).where(SalesOffer.status == "sent", SalesOffer.valid_until <= now).limit(10)):
        c = db.get(SalesCompany, o.company_id)
        needs_you.append({"kind": "offer_expired", "id": str(o.company_id), "text": f"{c.display_name}: tilbud v{o.version} er udløbet"})
    for c in db.scalars(select(SalesCompany).where(SalesCompany.possible_duplicate_of.is_not(None))
                        .order_by(SalesCompany.updated_at.desc()).limit(10)):
        needs_you.append({"kind": "possible_duplicate", "id": str(c.id), "text": f"{c.display_name}: {c.duplicate_reason}"})
    definitions = {
        "companies_new_30d": "Virksomheder fundet eller importeret de seneste 30 dage (alle kilder, inkl. demo-data).",
        "companies_total": "Alle virksomheder i salgskanalen.",
        "researched": "Virksomheder, hvis hjemmeside er undersøgt (status undersøgt eller profileret).",
        "scripts_approved": "Godkendte manuskripter (gældende versioner).",
        "simulations_30d": "Simulerede samtaler de seneste 30 dage. Simulationer tæller aldrig i salgsstatistik.",
        "searches_running": "Søgninger i kø eller i gang.",
        "calls_today": "Opkald Peter har foretaget i dag i interne kampagner (også testopkald og ubesvarede).",
        "meetings_upcoming": "Bekræftede intro-møder, der ikke har fundet sted endnu.",
        "offers_open": "Sendte tilbud, der hverken er accepteret eller udløbet.",
        "orders_accepted_30d": "Tilbud accepteret på acceptsiden de seneste 30 dage (en accept er ikke en betaling).",
        "paying_customers": "Virksomheder fra salgskanalen, hvis arbejdsrum har betalt sin første faktura.",
    }
    return channel.status(db) | {"tiles": tiles, "definitions": definitions, "needs_you": needs_you,
                                 "not_built": []}


@router.get("/industries", dependencies=[Depends(research_gate)])
def list_industries(db: OrmSession = Depends(get_db)):
    return {"items": list(channel.industries(db, include_inactive=True).values()),
            "google_types": [{"type": t, "term": term} for t, term in search.TYPE_TERMS.items()]}


class IndustryIn(BaseModel):
    key: str = Field(min_length=2, max_length=40, pattern=r"^[a-z0-9_]+$")
    label: str = Field(min_length=2, max_length=120)
    google_types: list[str] = Field(default_factory=list, max_length=10)
    search_terms: list[str] = Field(default_factory=list, max_length=10)
    active: bool = True


@router.put("/industries", dependencies=[Depends(research_gate)])
def put_industry(body: IndustryIn, request: Request, db: OrmSession = Depends(get_db),
                 principal: Principal = Depends(operator)):
    from app.models import SalesIndustry

    row = db.get(SalesIndustry, body.key) or SalesIndustry(key=body.key)
    row.label = body.label.strip()
    row.google_types = [t.strip() for t in body.google_types if t.strip()][:10]
    row.search_terms = [companies.clean_text(t, 60) for t in body.search_terms if t.strip()][:10]
    row.active, row.updated_by = body.active, principal.user.id
    db.add(row)
    record_audit(db, workspace_id=None, actor_user_id=principal.user.id, action="sales.industry_saved",
                 object_type="sales_industry", object_id=body.key, after=body.model_dump(),
                 request_id=request.state.request_id)
    db.commit()
    return channel.industries(db, include_inactive=True)[body.key]


# --------------------------------------------------------------------------- search jobs


class SearchIn(BaseModel):
    industry_keys: list[str] = Field(default_factory=list, max_length=10)
    google_types: list[str] = Field(default_factory=list, max_length=10)
    keywords: list[str] = Field(default_factory=list, max_length=10)
    geo_kind: Literal["place", "postal_codes", "radius"]
    geo: dict = Field(description='{"text": "Aarhus C"} | {"postal_codes": ["8000"]} | {"lat", "lng", "km" ≤ 50}')
    max_results: int = Field(default=50, ge=1, le=1000)
    exclude_existing_customers: bool = True


@router.post("/search-jobs", status_code=status.HTTP_202_ACCEPTED, dependencies=[Depends(research_gate)])
def create_search(body: SearchIn, request: Request, dry_run: bool = Query(default=False), db: OrmSession = Depends(get_db),
                  principal: Principal = Depends(operator)):
    """Queue a search. The worker runs it; the answer carries the estimated Google usage (upper bound).
    `dry_run=true` returns the plan and estimate without saving anything (a free-text place that is not a Danish
    town or postal district is geocoded with one Places request even then)."""
    job = search.create_job(db, user_id=principal.user.id, industry_keys=body.industry_keys,
                            google_types=body.google_types, keywords=body.keywords, geo_kind=body.geo_kind, geo=body.geo,
                            max_results=body.max_results, exclude_existing_customers=body.exclude_existing_customers)
    if dry_run:
        out = search.job_out(job) | {"dry_run": True}
        db.rollback()
        return out
    record_audit(db, workspace_id=None, actor_user_id=principal.user.id, action="sales.search_created",
                 object_type="sales_search_job", object_id=job.id,
                 after={"source": job.source, "steps": len(job.plan), "max_results": job.max_results},
                 request_id=request.state.request_id)
    db.commit()
    return search.job_out(job)


@router.get("/search-jobs", dependencies=[Depends(research_gate)])
def list_searches(limit: int = Query(default=50, ge=1, le=200), db: OrmSession = Depends(get_db)):
    rows = db.scalars(select(SalesSearchJob).order_by(SalesSearchJob.created_at.desc()).limit(limit))
    return {"items": [search.job_out(j) for j in rows], "requests_today": search.requests_today(db)}


@router.get("/search-jobs/{job_id}", dependencies=[Depends(research_gate)])
def get_search(job_id: uuid.UUID, db: OrmSession = Depends(get_db)):
    return search.job_out(search.get_job(db, job_id))


@router.post("/search-jobs/{job_id}/cancel", dependencies=[Depends(research_gate)])
def cancel_search(job_id: uuid.UUID, request: Request, db: OrmSession = Depends(get_db),
                  principal: Principal = Depends(operator)):
    job = search.cancel(db, search.get_job(db, job_id))
    record_audit(db, workspace_id=None, actor_user_id=principal.user.id, action="sales.search_cancelled",
                 object_type="sales_search_job", object_id=job.id, request_id=request.state.request_id)
    db.commit()
    return search.job_out(job)


@router.post("/search-jobs/{job_id}/resume", dependencies=[Depends(research_gate)])
def resume_search(job_id: uuid.UUID, request: Request, db: OrmSession = Depends(get_db),
                  principal: Principal = Depends(operator)):
    job = search.resume(db, search.get_job(db, job_id))
    record_audit(db, workspace_id=None, actor_user_id=principal.user.id, action="sales.search_resumed",
                 object_type="sales_search_job", object_id=job.id, request_id=request.state.request_id)
    db.commit()
    return search.job_out(job)


class ImportIn(BaseModel):
    csv: str = Field(min_length=5, max_length=500_000, description="Columns: navn, cvr, hjemmeside, telefon, e-mail, postnr")
    industry_key: str | None = Field(default=None, max_length=40)


@router.post("/companies/import", status_code=status.HTTP_201_CREATED, dependencies=[Depends(research_gate)])
def import_companies(body: ImportIn, request: Request, db: OrmSession = Depends(get_db),
                     principal: Principal = Depends(operator)):
    """Fallback without Google: the operator's own list, marked `import`."""
    job = search.import_csv(db, user_id=principal.user.id, text=body.csv, industry_key=body.industry_key)
    record_audit(db, workspace_id=None, actor_user_id=principal.user.id, action="sales.companies_imported",
                 object_type="sales_search_job", object_id=job.id, after=job.progress, request_id=request.state.request_id)
    db.commit()
    return search.job_out(job)


# --------------------------------------------------------------------------- companies

SORTS = {"newest": SalesCompany.first_seen_at.desc(), "name": SalesCompany.display_name.asc(),
         "relevance": SalesCompany.relevance_score.desc(), "updated": SalesCompany.updated_at.desc()}


@router.get("/companies", dependencies=[Depends(research_gate)])
def list_companies(q: str | None = Query(default=None, max_length=100), industry: str | None = None,
                   postal: str | None = Query(default=None, max_length=8), research_status: str | None = None,
                   source: str | None = None, quality: str | None = None, search_job: uuid.UUID | None = None,
                   sort: Literal["newest", "name", "relevance", "updated"] = "newest",
                   limit: int = Query(default=50, ge=1, le=200), offset: int = Query(default=0, ge=0),
                   db: OrmSession = Depends(get_db)):
    query = select(SalesCompany)
    if q:
        like = f"%{q.strip()}%"
        query = query.where(or_(SalesCompany.display_name.ilike(like), SalesCompany.city.ilike(like),
                                SalesCompany.domain.ilike(like), SalesCompany.cvr == q.strip()))
    if industry:
        query = query.where(SalesCompany.industry_key == industry)
    if postal:
        query = query.where(SalesCompany.postal_code == postal)
    if research_status:
        query = query.where(SalesCompany.research_status == research_status)
    if source:
        query = query.where(SalesCompany.source == source)
    if search_job:
        query = query.where(SalesCompany.last_search_job_id == search_job)
    if quality == "issues":
        query = query.where(func.jsonb_array_length(SalesCompany.data_quality["issues"]) > 0)
    elif quality == "duplicates":
        query = query.where(SalesCompany.possible_duplicate_of.is_not(None))
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = db.scalars(query.order_by(SORTS[sort], SalesCompany.id).limit(limit).offset(offset))
    return {"items": [companies.out(c) for c in rows], "total": total, "limit": limit, "offset": offset}


@router.get("/companies/{company_id}", dependencies=[Depends(research_gate)])
def get_company(company_id: uuid.UUID, db: OrmSession = Depends(get_db)):
    return companies.detail(db, _company(db, company_id))


def _research_in_background(company_id: uuid.UUID, user_id: uuid.UUID) -> None:
    from app.core.errors import ApiError
    from app.db import get_session_factory
    from app.modules.sales import research

    with get_session_factory()() as db:
        c = db.get(SalesCompany, company_id)
        try:
            research.run(db, c, user_id=user_id)
        except ApiError as e:
            db.rollback()
            c = db.get(SalesCompany, company_id)
            c.research_error = e.message[:300]
            if c.research_status == "found":
                c.research_status = "incomplete"
        except Exception as e:  # noqa: BLE001 - stored for the operator, logged here
            db.rollback()
            log.warning("sales.research.failed", company_id=str(company_id), error=type(e).__name__)
            c = db.get(SalesCompany, company_id)
            c.research_error = "Uventet fejl under research. Prøv igen."
        c.research_started_at = None
        db.commit()


@router.post("/companies/{company_id}/research", status_code=status.HTTP_202_ACCEPTED,
             dependencies=[Depends(research_gate)])
def research_company(company_id: uuid.UUID, request: Request, background: BackgroundTasks,
                     db: OrmSession = Depends(get_db), principal: Principal = Depends(operator)):
    """Research the company's own website in the background (only through the safe fetcher)."""
    from app.modules.ai.provider import get_provider
    from app.modules.sales import service

    c = _company(db, company_id)
    if not c.website_url:
        raise Conflict("Virksomheden har ingen kendt hjemmeside.", code="no_website")
    get_provider()  # 501 up front when AI is not configured
    if service.sales_workspace(db) is None:
        raise Conflict("Research kræver salgsarbejdsrummet (SALES_WORKSPACE_ID).", code="sales_workspace_missing")
    now = datetime.now(UTC)
    if c.research_started_at and now - c.research_started_at < timedelta(minutes=5):
        return companies.out(c) | {"running": True}
    c.research_started_at, c.research_error = now, None
    record_audit(db, workspace_id=None, actor_user_id=principal.user.id, action="sales.research_started",
                 object_type="sales_company", object_id=c.id, after={"website": c.website_url},
                 request_id=request.state.request_id)
    db.commit()
    background.add_task(_research_in_background, c.id, principal.user.id)
    return companies.out(c) | {"running": True}


@router.post("/companies/{company_id}/profile", status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(research_gate)])
def create_profile(company_id: uuid.UUID, request: Request, db: OrmSession = Depends(get_db),
                   principal: Principal = Depends(operator)):
    p = playbook.build_profile(db, _company(db, company_id), user_id=principal.user.id,
                               request_id=request.state.request_id)
    db.commit()
    return playbook.profile_out(p)


class ScriptIn(BaseModel):
    profile_id: uuid.UUID | None = Field(default=None, description="Unset = the newest profile")


@router.post("/companies/{company_id}/scripts", status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(research_gate)])
def create_script(company_id: uuid.UUID, request: Request, body: ScriptIn | None = None,
                  db: OrmSession = Depends(get_db), principal: Principal = Depends(operator)):
    c = _company(db, company_id)
    q = select(SalesProfile).where(SalesProfile.company_id == c.id)
    q = q.where(SalesProfile.id == body.profile_id) if body and body.profile_id else q.order_by(SalesProfile.version.desc())
    p = db.scalar(q.limit(1))
    if p is None:
        raise Conflict("Byg en profil først.", code="no_profile")
    s = playbook.build_script(db, c, p, user_id=principal.user.id, request_id=request.state.request_id)
    db.commit()
    return playbook.script_out(s)


@router.post("/scripts/{script_id}/approve", dependencies=[Depends(research_gate)])
def approve_script(script_id: uuid.UUID, request: Request, db: OrmSession = Depends(get_db),
                   principal: Principal = Depends(operator)):
    s = playbook.approve(db, playbook.get_script(db, script_id), user_id=principal.user.id,
                         request_id=request.state.request_id)
    db.commit()
    return playbook.script_out(s)


class SimulateIn(BaseModel):
    script_id: uuid.UUID
    persona: str = Field(default="", max_length=500)
    max_turns: int = Field(default=12, ge=2, le=simulate.MAX_TURNS)


@router.post("/companies/{company_id}/simulate", status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(simulation_gate)])
def simulate_call(company_id: uuid.UUID, body: SimulateIn, request: Request, db: OrmSession = Depends(get_db),
                  principal: Principal = Depends(operator)):
    """A simulated conversation (no call, no tool executed). Marked simulated everywhere."""
    c = _company(db, company_id)
    sim = simulate.run(db, c, playbook.get_script(db, body.script_id), persona=body.persona, max_turns=body.max_turns,
                       user_id=principal.user.id)
    record_audit(db, workspace_id=None, actor_user_id=principal.user.id, action="sales.simulation_run",
                 object_type="sales_simulation", object_id=sim.id,
                 after={"company_id": str(c.id), "outcome": sim.outcome, "simulated": True},
                 request_id=request.state.request_id)
    db.commit()
    return simulate.out(sim)


# --------------------------------------------------------------------------- knowledge, prices, integrations


@router.get("/integrations", dependencies=[Depends(research_gate)])
def list_integrations(db: OrmSession = Depends(get_db)):
    return {"items": integrations.register(db), "statuses": list(integrations.STATUSES)}


class IntegrationNoteIn(BaseModel):
    system: str = Field(min_length=2, max_length=80)
    label: str = Field(default="", max_length=120)
    status: Literal["AKTIV", "KRÆVER_OPSÆTNING", "PLANLAGT", "UKENDT"]
    note: str = Field(default="", max_length=2000)


@router.put("/integrations", dependencies=[Depends(research_gate)])
def put_integration(body: IntegrationNoteIn, request: Request, db: OrmSession = Depends(get_db),
                    principal: Principal = Depends(operator)):
    row = integrations.set_note(db, system=body.system, label=body.label or body.system, status=body.status,
                                note=body.note, user_id=principal.user.id)
    record_audit(db, workspace_id=None, actor_user_id=principal.user.id, action="sales.integration_note_saved",
                 object_type="sales_integration_note", object_id=row.system, after=body.model_dump(),
                 request_id=request.state.request_id)
    db.commit()
    return {"items": integrations.register(db)}


@router.get("/knowledge", dependencies=[Depends(research_gate)])
def sales_knowledge(db: OrmSession = Depends(get_db)):
    """The sales workspace's approved knowledge with audience, the price list and the script versions in use."""
    from app.models import KnowledgeVersion
    from app.modules.billing import prices
    from app.modules.knowledge.service import active_knowledge
    from app.modules.sales import service

    ws = service.sales_workspace(db)
    items = active_knowledge(db, ws.id) if ws else []
    drafts = db.scalar(select(func.count()).where(KnowledgeVersion.workspace_id == ws.id,
                                                  KnowledgeVersion.status.in_(("draft", "in_review"))))if ws else 0
    scripts = db.execute(select(SalesScript.script_version, SalesScript.status, func.count())
                         .group_by(SalesScript.script_version, SalesScript.status)).all()
    return {"sales_workspace": {"id": str(ws.id), "name": ws.name, "knowledge_revision": ws.knowledge_revision} if ws else None,
            "items": [{"item_id": i["item_id"], "kind": i["kind"], "title": i["title"], "audience": i["audience"],
                       "version_no": i["version_no"]} for i in items],
            "open_drafts": drafts or 0,
            "prices": {"monthly_net_minor": prices.SUBSCRIPTION_MONTHLY_NET_MINOR,
                       "campaign_call_net_minor": prices.CAMPAIGN_CALL_NET_MINOR,
                       "campaign_minute_net_minor": prices.CAMPAIGN_MINUTE_NET_MINOR,
                       "inbound_included_minutes": prices.INBOUND_INCLUDED_MINUTES,
                       "inbound_extra_minute_net_minor": prices.INBOUND_EXTRA_MINUTE_NET_MINOR,
                       "specialist_setup_net_minor": prices.SPECIALIST_SETUP_NET_MINOR,
                       "tax_basis_points": prices.TAX_BASIS_POINTS, "terms_version": playbook.TERMS_VERSION},
            "scripts": [{"script_version": v, "status": st, "count": n} for v, st, n in scripts],
            "fallback_features": playbook.FALLBACK_FEATURES, "integrations": integrations.register(db)}


# --------------------------------------------------------------------------- phase 2: contacts, basis, policy


class ContactIn(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    role: str | None = Field(default=None, max_length=120)
    phone: str | None = Field(default=None, max_length=30)
    email: str | None = Field(default=None, max_length=320)


@router.post("/companies/{company_id}/contacts", status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(research_gate)])
def add_contact(company_id: uuid.UUID, body: ContactIn, request: Request, db: OrmSession = Depends(get_db),
                principal: Principal = Depends(operator)):
    from app.modules.sales import outbound

    c = outbound.add_contact(db, _company(db, company_id), name=body.name, role=body.role, phone=body.phone,
                             email=body.email)
    record_audit(db, workspace_id=None, actor_user_id=principal.user.id, action="sales.contact_added",
                 object_type="sales_contact", object_id=c.id, after={"company_id": str(company_id), "role": c.role},
                 request_id=request.state.request_id)
    db.commit()
    return companies.contact_out(c)


def _contact(db: OrmSession, contact_id: uuid.UUID):
    from app.models import SalesContact

    c = db.get(SalesContact, contact_id)
    if c is None:
        raise NotFound("Kontakten findes ikke")
    return c


class BasisIn(BaseModel):
    channel: Literal["ai_call", "human_call", "email", "sms"] = "ai_call"
    purpose: str = Field(min_length=3, max_length=200)
    kind: Literal["request", "consent"]
    source: Literal["web_form", "seller", "lead", "import"]
    text: str = Field(min_length=20, max_length=4000, description="The full text the contact said yes to")
    text_version: str = Field(default="operator-v1", max_length=40)
    evidence_ref: str = Field(default="", max_length=300)
    valid_until: datetime | None = None


@router.post("/contacts/{contact_id}/basis", status_code=status.HTTP_201_CREATED, dependencies=[Depends(research_gate)])
def add_basis(contact_id: uuid.UUID, body: BasisIn, request: Request, db: OrmSession = Depends(get_db),
              principal: Principal = Depends(operator)):
    """Register the documented basis for contacting this person (e.g. they asked to be called). Audited."""
    from app.modules.sales import outbound

    b = outbound.record_basis(db, _contact(db, contact_id), channel=body.channel, purpose=body.purpose, kind=body.kind,
                              source=body.source, text=body.text, text_version=body.text_version,
                              evidence_ref=body.evidence_ref, valid_until=body.valid_until, user_id=principal.user.id)
    record_audit(db, workspace_id=None, actor_user_id=principal.user.id, action="sales.basis_recorded",
                 object_type="sales_contact_basis", object_id=b.id,
                 after={"contact_id": str(contact_id), "channel": b.channel, "kind": b.kind, "source": b.source},
                 request_id=request.state.request_id)
    db.commit()
    return outbound.basis_out(b)


class WithdrawIn(BaseModel):
    reason: str = Field(min_length=2, max_length=300)


@router.post("/basis/{basis_id}/withdraw", dependencies=[Depends(research_gate)])
def withdraw_basis(basis_id: uuid.UUID, body: WithdrawIn, request: Request, db: OrmSession = Depends(get_db),
                   principal: Principal = Depends(operator)):
    from app.models import SalesContactBasis
    from app.modules.sales import outbound

    b = db.get(SalesContactBasis, basis_id)
    if b is None:
        raise NotFound("Kontaktgrundlaget findes ikke")
    outbound.withdraw_basis(db, b, body.reason)
    record_audit(db, workspace_id=None, actor_user_id=principal.user.id, action="sales.basis_withdrawn",
                 object_type="sales_contact_basis", object_id=b.id, after={"reason": body.reason},
                 request_id=request.state.request_id)
    db.commit()
    return outbound.basis_out(b)


@router.post("/contacts/{contact_id}/check", dependencies=[Depends(research_gate)])
def check_contact(contact_id: uuid.UUID, db: OrmSession = Depends(get_db)):
    """Run the contact policy now (no campaign) and store the decision."""
    from app.modules.sales import outbound, policy

    contact = _contact(db, contact_id)
    d = policy.evaluate(db, contact=contact, stage="check", script=outbound.approved_script(db, contact.company_id))
    db.commit()
    return d.out()


@router.get("/block-list", dependencies=[Depends(research_gate)])
def list_blocks(db: OrmSession = Depends(get_db)):
    from app.models import SalesBlockList
    from app.modules.sales import outbound

    rows = db.scalars(select(SalesBlockList).order_by(SalesBlockList.created_at.desc()).limit(500))
    return {"items": [outbound.block_out(b) for b in rows]}


class BlockIn(BaseModel):
    kind: Literal["phone", "domain", "cvr"]
    value: str = Field(min_length=2, max_length=200)
    reason: str = Field(default="", max_length=300)
    source: Literal["manual", "dispute"] = "manual"


@router.post("/block-list", status_code=status.HTTP_201_CREATED, dependencies=[Depends(research_gate)])
def add_block(body: BlockIn, request: Request, db: OrmSession = Depends(get_db), principal: Principal = Depends(operator)):
    from app.modules.sales import outbound

    b = outbound.block(db, kind=body.kind, value=body.value, reason=body.reason, source=body.source,
                       user_id=principal.user.id)
    record_audit(db, workspace_id=None, actor_user_id=principal.user.id, action="sales.blocked",
                 object_type="sales_block_list", object_id=b.id, after={"kind": b.kind, "source": b.source},
                 request_id=request.state.request_id)
    db.commit()
    return outbound.block_out(b)


# --------------------------------------------------------------------------- phase 2: campaigns, test calls, calls


class SalesCampaignIn(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    budget_net_minor: int | None = Field(default=None, ge=0, le=10_000_000)
    call_days: list[str] = Field(default_factory=lambda: ["mon", "tue", "wed", "thu", "fri"])
    call_from: str = Field(default="09:00", pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    call_to: str = Field(default="16:00", pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    max_attempts: int = Field(default=2, ge=1, le=5)
    recording_enabled: bool = False


@router.get("/campaigns", dependencies=[Depends(research_gate)])
def list_sales_campaigns(db: OrmSession = Depends(get_db)):
    from app.models import Campaign
    from app.modules.sales import outbound

    rows = db.scalars(select(Campaign).where(Campaign.kind == "internal_sales").order_by(Campaign.created_at.desc()))
    return {"items": [outbound.campaign_out(db, c) for c in rows]}


@router.post("/campaigns", status_code=status.HTTP_201_CREATED, dependencies=[Depends(research_gate)])
def create_sales_campaign(body: SalesCampaignIn, request: Request, db: OrmSession = Depends(get_db),
                          principal: Principal = Depends(operator)):
    from app.modules.sales import outbound

    c = outbound.create_campaign(db, name=body.name, budget_net_minor=body.budget_net_minor, call_days=body.call_days,
                                 call_from=body.call_from, call_to=body.call_to, max_attempts=body.max_attempts,
                                 user_id=principal.user.id, recording_enabled=body.recording_enabled)
    record_audit(db, workspace_id=c.workspace_id, actor_user_id=principal.user.id, action="sales.campaign_created",
                 object_type="campaign", object_id=c.id, after=body.model_dump(), request_id=request.state.request_id)
    db.commit()
    return outbound.campaign_out(db, c)


@router.get("/campaigns/{campaign_id}", dependencies=[Depends(research_gate)])
def get_sales_campaign(campaign_id: uuid.UUID, db: OrmSession = Depends(get_db)):
    from app.modules.sales import outbound

    c = outbound.get_campaign(db, campaign_id)
    p = outbound.preview(db, c)
    db.commit()  # the preview stores its plan-stage decisions
    return outbound.campaign_out(db, c) | {"preview": p}


class MembersIn(BaseModel):
    contact_ids: list[uuid.UUID] = Field(default_factory=list, max_length=500)
    company_ids: list[uuid.UUID] = Field(default_factory=list, max_length=500,
                                         description="Adds each company's main number")


@router.post("/campaigns/{campaign_id}/members", dependencies=[Depends(research_gate)])
def add_campaign_members(campaign_id: uuid.UUID, body: MembersIn, request: Request, db: OrmSession = Depends(get_db),
                         principal: Principal = Depends(operator)):
    from app.models import SalesContact
    from app.modules.sales import outbound

    c = outbound.get_campaign(db, campaign_id)
    ids = list(body.contact_ids)
    for company_id in body.company_ids:
        main = db.scalar(select(SalesContact.id).where(SalesContact.company_id == company_id,
                                                       SalesContact.is_main_number.is_(True)))
        if main:
            ids.append(main)
    out = outbound.add_members(db, c, ids)
    record_audit(db, workspace_id=c.workspace_id, actor_user_id=principal.user.id, action="sales.campaign_members",
                 object_type="campaign", object_id=c.id, after={"added": len(out["added"]), "skipped": len(out["skipped"])},
                 request_id=request.state.request_id)
    db.commit()
    return out


class StartIn(BaseModel):
    accepted_max_net_minor: int = Field(ge=0, description="The cost ceiling shown in the preview, accepted by you")


@router.post("/campaigns/{campaign_id}/start", dependencies=[Depends(research_gate)])
def start_sales_campaign(campaign_id: uuid.UUID, body: StartIn, request: Request, db: OrmSession = Depends(get_db),
                         principal: Principal = Depends(operator)):
    from app.modules.sales import outbound

    c = outbound.get_campaign(db, campaign_id)
    p = outbound.start(db, c, user_id=principal.user.id, accepted_max_net_minor=body.accepted_max_net_minor)
    record_audit(db, workspace_id=c.workspace_id, actor_user_id=principal.user.id, action="sales.campaign_started",
                 object_type="campaign", object_id=c.id, after={"preview": p["counts"],
                                                                "accepted_max_net_minor": body.accepted_max_net_minor},
                 request_id=request.state.request_id)
    db.commit()
    return outbound.campaign_out(db, c)


@router.post("/campaigns/{campaign_id}/{action}", dependencies=[Depends(research_gate)])
def control_sales_campaign(campaign_id: uuid.UUID, action: Literal["pause", "stop"], request: Request,
                           db: OrmSession = Depends(get_db), principal: Principal = Depends(operator)):
    from app.modules.sales import outbound

    c = outbound.get_campaign(db, campaign_id)
    if action == "pause":
        outbound.pause(c)
        skipped = 0
    else:
        skipped = outbound.stop(db, c)
    record_audit(db, workspace_id=c.workspace_id, actor_user_id=principal.user.id, action=f"sales.campaign_{action}",
                 object_type="campaign", object_id=c.id, after={"skipped": skipped}, request_id=request.state.request_id)
    db.commit()
    return outbound.campaign_out(db, c)


class TestCallIn(BaseModel):
    company_id: uuid.UUID
    script_id: uuid.UUID
    phone: str = Field(min_length=8, max_length=30)
    accepted_test: bool
    record: bool = False


@router.post("/test-calls", status_code=status.HTTP_201_CREATED, dependencies=[Depends(research_gate)])
def place_test_call(body: TestCallIn, request: Request, db: OrmSession = Depends(get_db),
                    principal: Principal = Depends(operator)):
    """An internal test call to a number in SALES_TEST_NUMBERS (SALES_OUTBOUND_MODE=test or live). Real telephony."""
    from app.core.errors import ValidationFailed
    from app.modules.sales import outbound

    if not body.accepted_test:
        raise ValidationFailed("Bekræft at nummeret er dit eget testnummer", field_errors=[{"field": "accepted_test"}])
    out = outbound.test_call(db, company=_company(db, body.company_id), script=playbook.get_script(db, body.script_id),
                             phone=body.phone, user_id=principal.user.id, record=body.record)
    record_audit(db, workspace_id=None, actor_user_id=principal.user.id, action="sales.test_call",
                 object_type="campaign_contact", object_id=out["campaign_contact_id"],
                 after={"status": out["status"], "company_id": str(body.company_id)}, request_id=request.state.request_id)
    db.commit()
    return out


@router.get("/calls", dependencies=[Depends(research_gate)])
def list_sales_calls(campaign_id: uuid.UUID | None = None, outcome: str | None = None, test: bool | None = None,
                     q: str | None = Query(default=None, max_length=100), limit: int = Query(default=100, ge=1, le=500),
                     db: OrmSession = Depends(get_db)):
    from app.modules.sales import outbound

    return {"items": outbound.calls(db, campaign_id=campaign_id, outcome=outcome, test=test, q=q, limit=limit)}


@router.get("/calls/{campaign_contact_id}", dependencies=[Depends(research_gate)])
def get_sales_call(campaign_contact_id: uuid.UUID, db: OrmSession = Depends(get_db)):
    from app.modules.sales import outbound

    return outbound.call_detail(db, campaign_contact_id)


class AdvertisingIn(BaseModel):
    advertising_protected: bool
    note: str = Field(min_length=5, max_length=300, description="Where it was checked, e.g. datacvr.virk.dk 30/10")


@router.post("/companies/{company_id}/advertising-check", dependencies=[Depends(research_gate)])
def advertising_check(company_id: uuid.UUID, body: AdvertisingIn, request: Request, db: OrmSession = Depends(get_db),
                      principal: Principal = Depends(operator)):
    """Record a manual check of advertising protection (when CVR system access is not set up). Audited."""
    c = _company(db, company_id)
    before = c.advertising_protected
    c.advertising_protected = body.advertising_protected
    companies.add_fact(db, c, field="advertising_protected", value="ja" if body.advertising_protected else "nej",
                       ref=f"manual:{principal.user.id}", evidence=body.note, confidence="high",
                       extractor="operator-check-v1")
    companies.compute_quality(db, c)
    record_audit(db, workspace_id=None, actor_user_id=principal.user.id, action="sales.advertising_checked",
                 object_type="sales_company", object_id=c.id, before={"advertising_protected": before},
                 after={"advertising_protected": body.advertising_protected, "note": body.note},
                 request_id=request.state.request_id)
    db.commit()
    return companies.out(c)


# --------------------------------------------------------------------------- phase 3: offers, meetings, statistics


class OfferIn(BaseModel):
    setup_kind: Literal["diy", "specialist"]
    contact_id: uuid.UUID | None = None


@router.post("/companies/{company_id}/offers", status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(research_gate)])
def create_offer(company_id: uuid.UUID, body: OfferIn, db: OrmSession = Depends(get_db),
                 principal: Principal = Depends(operator)):
    from app.modules.sales import offers

    o = offers.create(db, _company(db, company_id), setup_kind=body.setup_kind, contact_id=body.contact_id,
                      user_id=principal.user.id)
    db.commit()
    return offers.out(db, o)


def _offer(db: OrmSession, offer_id: uuid.UUID):
    from app.models import SalesOffer

    o = db.get(SalesOffer, offer_id)
    if o is None:
        raise NotFound("Tilbuddet findes ikke")
    return o


@router.get("/offers/{offer_id}", dependencies=[Depends(research_gate)])
def get_offer(offer_id: uuid.UUID, db: OrmSession = Depends(get_db)):
    from app.modules.sales import offers

    return offers.out(db, _offer(db, offer_id))


class OfferSendIn(BaseModel):
    channel: Literal["email", "sms"]
    destination: str = Field(min_length=3, max_length=320)
    kind: Literal["order_link", "offer_summary"] = "order_link"


@router.post("/offers/{offer_id}/send", dependencies=[Depends(research_gate)])
def send_offer(offer_id: uuid.UUID, body: OfferSendIn, request: Request, db: OrmSession = Depends(get_db),
               principal: Principal = Depends(operator)):
    """The operator's own choice of channel and destination (checked by them): sent at once."""
    from app.modules.sales import offers

    o = _offer(db, offer_id)
    r = offers.request_message(db, o, channel=body.channel, destination=body.destination, kind=body.kind,
                               operator_checked=True)
    record_audit(db, workspace_id=None, actor_user_id=principal.user.id, action="sales.offer_sent",
                 object_type="sales_offer", object_id=o.id, after={"channel": r.channel, "status": r.status},
                 request_id=request.state.request_id)
    db.commit()
    return offers.out(db, o)


@router.post("/offers/{offer_id}/cancel", dependencies=[Depends(research_gate)])
def cancel_offer(offer_id: uuid.UUID, db: OrmSession = Depends(get_db), principal: Principal = Depends(operator)):
    from app.modules.sales import offers

    o = _offer(db, offer_id)
    if o.status == "accepted":
        raise Conflict("Et accepteret tilbud kan ikke annulleres her.", code="offer_already_accepted")
    o.status, o.accept_token_hash = "cancelled", None
    record_audit(db, workspace_id=None, actor_user_id=principal.user.id, action="sales.offer_cancelled",
                 object_type="sales_offer", object_id=o.id)
    db.commit()
    return offers.out(db, o)


@router.post("/messages/{request_id}/send", dependencies=[Depends(research_gate)])
def send_requested_message(request_id: uuid.UUID, db: OrmSession = Depends(get_db),
                           principal: Principal = Depends(operator)):
    """A link the customer asked for on a call, to an address we did not hold: the operator has checked it."""
    from app.models import SalesMessageRequest, SalesOffer
    from app.modules.sales import offers

    r = db.get(SalesMessageRequest, request_id)
    if r is None:
        raise NotFound("Anmodningen findes ikke")
    if r.status != "requested" or r.outbox_event_id is not None:
        raise Conflict("Anmodningen er allerede behandlet.", code="message_already_handled")
    o = db.get(SalesOffer, r.offer_id)
    offers.deliver(db, o, r)
    record_audit(db, workspace_id=None, actor_user_id=principal.user.id, action="sales.message_released",
                 object_type="sales_message_request", object_id=r.id, after={"status": r.status})
    db.commit()
    return offers.message_out(r)


class MeetingIn(BaseModel):
    status: Literal["held", "no_show", "cancelled"]


@router.post("/meetings/{meeting_id}", dependencies=[Depends(research_gate)])
def update_meeting(meeting_id: uuid.UUID, body: MeetingIn, db: OrmSession = Depends(get_db),
                   principal: Principal = Depends(operator)):
    from app.models import Booking, SalesMeeting
    from app.modules.bookings import service as bookings
    from app.modules.sales import meetings

    m = db.get(SalesMeeting, meeting_id)
    if m is None:
        raise NotFound("Mødet findes ikke")
    if body.status == "cancelled" and m.booking_id:
        b = db.get(Booking, m.booking_id)
        if b is not None and b.status != "cancelled":
            bookings.cancel(db, b)
    m.status = body.status
    record_audit(db, workspace_id=None, actor_user_id=principal.user.id, action="sales.meeting_updated",
                 object_type="sales_meeting", object_id=m.id, after={"status": m.status})
    db.commit()
    return meetings.out(db, m)


@router.get("/stats", dependencies=[Depends(research_gate)])
def stats(date_from: date | None = Query(default=None, alias="from"), date_to: date | None = Query(default=None, alias="to"),
          campaign: uuid.UUID | None = None, db: OrmSession = Depends(get_db)):
    from app.modules.sales import stats as sales_stats

    today = datetime.now(UTC).date()
    d_to = date_to or today
    d_from = date_from or d_to - timedelta(days=29)
    if d_from > d_to:
        raise Conflict("Fra-datoen ligger efter til-datoen.", code="bad_range")
    return sales_stats.compute(db, d_from, d_to, campaign)


# --------------------------------------------------------------------------- phase 4: audio and data subject rights


@router.get("/calls/{campaign_contact_id}/audio", dependencies=[Depends(research_gate)])
def call_audio(campaign_contact_id: uuid.UUID, export: bool = False, db: OrmSession = Depends(get_db),
               principal: Principal = Depends(operator)):
    """A signed URL (≤ 10 min) to the recording. Playing is logged; exporting also needs `can_export_media`."""
    from app.core.errors import Forbidden
    from app.models import Call, CampaignContact
    from app.modules.sales import recordings

    if export and not principal.user.can_export_media:
        raise Forbidden("Eksport af lyd kræver særskilt rettighed.", code="export_not_allowed")
    cc = db.get(CampaignContact, campaign_contact_id)
    call = db.scalar(select(Call).where(Call.provider_call_id == cc.provider_call_id)) if cc and cc.provider_call_id else None
    if call is None or call.campaign_contact_id != cc.id:
        raise NotFound("Opkaldet findes ikke")
    out = recordings.play_url(db, call, principal.user.id, export=export)
    db.commit()
    return out


class DataRequestIn(BaseModel):
    subject: Literal["phone", "email", "cvr"]
    value: str = Field(min_length=3, max_length=320)
    kind: Literal["access", "erasure", "objection"]
    confirm: bool = False


@router.post("/data-requests", status_code=status.HTTP_201_CREATED, dependencies=[Depends(research_gate)])
def create_data_request(body: DataRequestIn, request: Request, db: OrmSession = Depends(get_db),
                        principal: Principal = Depends(operator)):
    from app.core.errors import ValidationFailed
    from app.modules.sales import privacy

    if body.kind == "erasure" and not body.confirm:
        raise ValidationFailed("Sletning kan ikke fortrydes. Bekræft den.", field_errors=[{"field": "confirm"}])
    r = privacy.handle(db, subject=body.subject, value=body.value, kind=body.kind, user_id=principal.user.id)
    record_audit(db, workspace_id=None, actor_user_id=principal.user.id, action=f"sales.data_request_{body.kind}",
                 object_type="sales_data_request", object_id=r.id, after={"subject": body.subject},
                 request_id=request.state.request_id)
    db.commit()
    return privacy.request_out(r, include_result=True)


@router.get("/data-requests", dependencies=[Depends(research_gate)])
def list_data_requests(db: OrmSession = Depends(get_db)):
    from app.models import SalesDataRequest
    from app.modules.sales import privacy

    rows = db.scalars(select(SalesDataRequest).order_by(SalesDataRequest.created_at.desc()).limit(100))
    return {"items": [privacy.request_out(r) for r in rows]}


@router.get("/data-requests/{request_id}", dependencies=[Depends(research_gate)])
def get_data_request(request_id: uuid.UUID, db: OrmSession = Depends(get_db)):
    from app.models import SalesDataRequest
    from app.modules.sales import privacy

    r = db.get(SalesDataRequest, request_id)
    if r is None:
        raise NotFound("Anmodningen findes ikke")
    return privacy.request_out(r, include_result=True)

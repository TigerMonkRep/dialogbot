"""Dialogbot's internal sales channel: /operator/salg/* (platform operators only).

Every route needs `operator`; nothing here is scoped by a workspace the client names. With SALES_OUTBOUND_MODE=off
every route answers 501 `sales_channel_off`, except GET /operator/salg, which says what is missing.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
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
from app.models import SalesCompany, SalesProfile, SalesScript, SalesSearchJob, SalesSimulation
from app.modules.sales import channel, companies, integrations, playbook, search, simulate
from app.modules.voices.operator_router import operator

router = APIRouter(prefix="/operator/salg", tags=["sales-channel"])
log = structlog.get_logger("dialogbot.sales.channel")


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
    }
    return channel.status(db) | {"tiles": tiles, "definitions": definitions, "needs_you": needs_you,
                                 "not_built": ["Kampagner", "Opkald og testopkald", "Tilbud og ordrer", "Møder",
                                               "Statistik over opkald", "Lydoptagelser"]}


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
                       "specialist_setup_net_minor": prices.SPECIALIST_SETUP_NET_MINOR,
                       "tax_basis_points": prices.TAX_BASIS_POINTS, "terms_version": playbook.TERMS_VERSION},
            "scripts": [{"script_version": v, "status": st, "count": n} for v, st, n in scripts],
            "fallback_features": playbook.FALLBACK_FEATURES, "integrations": integrations.register(db)}

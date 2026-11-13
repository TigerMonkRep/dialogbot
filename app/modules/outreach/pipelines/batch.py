"""One batch, end to end: source → (ComplianceEngine) → research → copy → audit → queue. Nothing is sent here; sending
is DispatcherAndWebhookHandler.dispatch(), a separate, deliberate step."""
from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Iterable

import structlog
from sqlalchemy import func, select
from sqlalchemy.orm import Session as OrmSession

from app.config import get_settings
from app.core.errors import NotImplementedYet
from app.models import OutreachCallQueue, OutreachLead, OutreachLog, OutreachMessage
from app.modules.outreach.agents.auditor import ComplianceAndSafetyAuditorAgent
from app.modules.outreach.agents.copywriter import OutreachCopywriterAgent
from app.modules.outreach.agents.research import PainPointResearchAgent
from app.modules.outreach.agents.sourcing import LeadSourcingAndQualificationAgent, RawLead
from app.modules.outreach.compliance import ComplianceBlocked, ComplianceEngine, LeadFacts
from app.modules.outreach.llm import OutreachAIError

log = structlog.get_logger("dialogbot.outreach.pipeline")


def require_on() -> None:
    if get_settings().outreach_mode == "off":
        raise NotImplementedYet("Outreach is switched off (OUTREACH_MODE=off)", code="outreach_off")


def ingest_batch(db: OrmSession, raws: Iterable[RawLead], *, batch: str, countries: set[str] | None = None,
                 mx_check: Callable[[str], bool | None] | None = None,
                 cvr_lookup: Callable[[str], bool | None] | None = None) -> list[OutreachLead]:
    """Step 1 (no model): every lead through the ComplianceEngine, then niche, MX and the Danish call list."""
    require_on()
    leads = LeadSourcingAndQualificationAgent(db, mx_check=mx_check, cvr_lookup=cvr_lookup).ingest(
        raws, batch=batch, countries=countries)
    db.commit()
    return leads


def process(db: OrmSession, batch: str, *, limit: int | None = None) -> dict:
    """Step 2 (Claude): research, write and audit the batch's qualified leads, `limit` at a time. The admin calls this
    one lead per request so a long batch never hangs a request; the CLI runs it to the end."""
    require_on()
    q = select(OutreachLead).where(OutreachLead.batch == batch, OutreachLead.status == "qualified").order_by(OutreachLead.created_at)
    leads = db.scalars(q.limit(limit) if limit else q).all()
    engine, research = ComplianceEngine(db), PainPointResearchAgent(db)
    writer, auditor = OutreachCopywriterAgent(db), ComplianceAndSafetyAuditorAgent(db)
    for lead in leads:
        try:
            clearance = engine.evaluate(LeadFacts(
                company_name=lead.company_name, email=lead.email_normalized, country=lead.country,
                email_source=lead.email_source, email_source_url=lead.email_source_url,
                registration_number=lead.registration_number)).clearance()
            brief = research.run(lead, clearance)
            if brief is not None:
                auditor.review(lead, writer.run(lead, brief, clearance))
        except ComplianceBlocked as e:
            lead.status = "blocked"
            db.add(OutreachLog(lead_id=lead.id, kind="compliance", outcome="BLOCK", detail={"reason": str(e)}))
        except OutreachAIError as e:
            lead.status = "error"
            db.add(OutreachLog(lead_id=lead.id, kind="research", outcome="error", detail={"error": str(e)}))
        db.commit()   # a lead at a time: a crash later in the batch never loses finished work
    remaining = db.scalar(select(func.count()).select_from(OutreachLead).where(
        OutreachLead.batch == batch, OutreachLead.status == "qualified")) or 0
    return {"processed": len(leads), "remaining": remaining}


def run_batch(db: OrmSession, raws: Iterable[RawLead], *, batch: str, countries: set[str] | None = None,
              mx_check: Callable[[str], bool | None] | None = None,
              cvr_lookup: Callable[[str], bool | None] | None = None) -> dict:
    ingest_batch(db, raws, batch=batch, countries=countries, mx_check=mx_check, cvr_lookup=cvr_lookup)
    process(db, batch)
    return report(db, batch)


def report(db: OrmSession, batch: str) -> dict:
    """Everything an operator needs to judge a batch: the decision, the brief, the e-mail and the audit per lead."""
    leads = db.scalars(select(OutreachLead).where(OutreachLead.batch == batch).order_by(OutreachLead.created_at)).all()
    ids = [x.id for x in leads]
    msgs = {m.lead_id: m for m in db.scalars(select(OutreachMessage).where(OutreachMessage.lead_id.in_(ids)))} if ids else {}
    usage = db.scalars(select(OutreachLog).where(OutreachLog.kind == "llm_usage", OutreachLog.lead_id.in_(ids))).all() if ids else []
    tokens: dict = {}
    for u in usage:
        t = tokens.setdefault(u.lead_id, {"input_tokens": 0, "output_tokens": 0, "calls": 0})
        t["input_tokens"] += u.detail.get("input_tokens", 0)
        t["output_tokens"] += u.detail.get("output_tokens", 0)
        t["calls"] += 1
    queue = {q.lead_id: q for q in db.scalars(select(OutreachCallQueue).where(OutreachCallQueue.lead_id.in_(ids)))} if ids else {}
    rendered = {d.lead_id: d.detail["rendered"] for d in db.scalars(select(OutreachLog).where(
        OutreachLog.kind == "dispatch", OutreachLog.outcome == "dry_run", OutreachLog.lead_id.in_(ids)))} if ids else {}
    rows = []
    for x in leads:
        m, q = msgs.get(x.id), queue.get(x.id)
        rows.append({
            "company": x.company_name, "email": x.email_normalized, "country": x.country, "niche": x.niche,
            "status": x.status, "compliance": x.compliance,
            "confidence": x.confidence_score, "hook": (x.brief or {}).get("personalization_hook"),
            "email_draft": None if m is None else {"status": m.status, "subject": m.subject, "body": m.body,
                                                   "footer": m.footer, "words": m.word_count, "audit": m.audit,
                                                   "sender_inbox": m.sender_inbox,
                                                   "send_on": m.send_on.isoformat() if m.send_on else None,
                                                   "rendered": rendered.get(x.id)},
            "call_queue": None if q is None else {"scrub_status": q.scrub_status, "phone": q.phone},
            "tokens": tokens.get(x.id, {"input_tokens": 0, "output_tokens": 0, "calls": 0}),
        })
    return {"batch": batch, "mode": get_settings().outreach_mode, "totals": dict(Counter(r["status"] for r in rows)),
            "tokens": {"input_tokens": sum(r["tokens"]["input_tokens"] for r in rows),
                       "output_tokens": sum(r["tokens"]["output_tokens"] for r in rows)},
            "leads": rows}

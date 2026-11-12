"""LeadSourcingAndQualificationAgent – deterministic. Takes raw business rows (CSV, or rows exported from Google Places /
Outscraper / Apify), runs the ComplianceEngine on each one FIRST, and only then spends effort on the lead: niche
filter and MX lookup for e-mail markets, the CVR scrub for the Danish call list."""
from __future__ import annotations

import csv
import io
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime

import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from app.models import OutreachCallQueue, OutreachLead, OutreachLog
from app.modules.outreach.compliance import Action, ComplianceEngine, Decision, LeadFacts
from app.modules.outreach.compliance.matrix import normalize_country
from app.modules.outreach.schemas import NICHES

log = structlog.get_logger("dialogbot.outreach.sourcing")

_NICHE_WORDS = {
    "plumber": ("plumb",), "hvac": ("hvac", "heating", "air condition", "furnace", "cooling"),
    "dentist": ("dent", "orthodont"), "med spa": ("med spa", "medspa", "medical spa", "aesthetic"),
    "auto repair": ("auto repair", "auto shop", "car repair", "mechanic", "garage", "body shop"),
    "hair salon": ("hair", "salon", "barber"),
}


@dataclass
class RawLead:
    company_name: str
    email: str
    country: str
    city: str | None = None
    niche: str | None = None
    website: str | None = None
    phone: str | None = None
    registration_number: str | None = None
    email_source: str = "unknown"
    email_source_url: str | None = None
    context: str | None = None


def normalize_niche(raw: str | None) -> str | None:
    t = (raw or "").strip().lower()
    if t in NICHES:
        return t
    return next((n for n, words in _NICHE_WORDS.items() if any(w in t for w in words)), None) if t else None


def read_csv(text: str) -> list[RawLead]:
    """Columns: company_name, email, country, city, niche, website, phone, registration_number, email_source,
    email_source_url, context. Only the first three are required."""
    fields = set(RawLead.__dataclass_fields__)
    return [RawLead(**{k: (v or "").strip() or None for k, v in row.items() if k in fields and (v or "").strip()})
            for row in csv.DictReader(io.StringIO(text)) if (row.get("email") or "").strip()]


def from_scraper_rows(rows: Iterable[dict], default_country: str | None = None) -> list[RawLead]:
    """Rows of a Google Maps export (Outscraper / Apify field names). An address found by the scraper on the business's
    own website counts as published there; the page is kept as the source."""
    out = []
    for r in rows:
        email = r.get("email_1") or r.get("email") or next(iter(r.get("emails") or []), None)
        if not email:
            continue
        site = r.get("site") or r.get("website")
        out.append(RawLead(
            company_name=r.get("name") or r.get("title") or "", email=email,
            country=r.get("country_code") or r.get("countryCode") or default_country or "",
            city=r.get("city"), niche=r.get("category") or r.get("categoryName") or r.get("type"), website=site,
            phone=r.get("phone"), email_source="published_website" if site else "directory", email_source_url=site,
            context="\n".join(str(x.get("review_text") or x.get("text") or "") for x in (r.get("reviews") or [])[:20]) or None))
    return out


def default_mx_check(domain: str) -> bool | None:
    """True/False from DNS; None when DNS could not be asked (treated as not verified)."""
    try:
        import dns.exception
        import dns.resolver

        try:
            return len(dns.resolver.resolve(domain, "MX", lifetime=5.0)) > 0
        except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer):
            return False
        except dns.exception.DNSException:
            return None
    except ImportError:
        return None


def default_cvr_lookup(cvr: str) -> bool | None:
    """reklamebeskyttet from the CVR register: True/False, or None when the register cannot be asked."""
    from app.core.errors import ApiError
    from app.modules.business import cvr as register

    try:
        return register.lookup(cvr).get("advertising_protected")
    except ApiError:
        return None


class LeadSourcingAndQualificationAgent:
    def __init__(self, db: OrmSession, *, mx_check: Callable[[str], bool | None] | None = None,
                 cvr_lookup: Callable[[str], bool | None] | None = None):
        self.db = db
        self.engine = ComplianceEngine(db)
        self.mx_check = mx_check or default_mx_check
        self.cvr_lookup = cvr_lookup or default_cvr_lookup

    def ingest(self, raws: Iterable[RawLead], *, batch: str, countries: set[str] | None = None) -> list[OutreachLead]:
        leads: list[OutreachLead] = []
        seen: set[str] = set()
        for raw in raws:
            email = (raw.email or "").strip().lower()
            country = normalize_country(raw.country)
            if countries and country not in countries:
                continue
            if not email or email in seen or self.db.scalar(select(OutreachLead.id).where(OutreachLead.email_normalized == email)):
                continue  # one lead per address, across batches
            seen.add(email)
            facts = LeadFacts(company_name=raw.company_name or "", email=email, country=country,
                              email_source=raw.email_source or "unknown", email_source_url=raw.email_source_url,
                              registration_number=raw.registration_number)
            decision = self.engine.evaluate(facts)   # before anything else
            lead = OutreachLead(
                batch=batch, company_name=(raw.company_name or "")[:200], email=raw.email.strip()[:320],
                email_normalized=email[:320], email_domain=email.rsplit("@", 1)[-1][:255], country=(country or "??")[:2],
                city=raw.city, niche=normalize_niche(raw.niche), website=raw.website, phone=raw.phone,
                registration_number=raw.registration_number, email_source=(raw.email_source or "unknown")[:20],
                email_source_url=raw.email_source_url, context=raw.context, compliance_action=str(decision.action),
                compliance=decision.out(),
                created_at=datetime.now(UTC))   # per row, so a batch keeps the order of its file
            self.db.add(lead)
            self.db.flush()
            self.db.add(OutreachLog(lead_id=lead.id, kind="compliance", outcome=str(decision.action), detail=decision.out()))
            self._route(lead, decision)
            leads.append(lead)
        self.db.flush()
        return leads

    def _route(self, lead: OutreachLead, decision: Decision) -> None:
        if decision.action is Action.BLOCK:
            lead.status = "blocked"
        elif decision.action is Action.HOLD:
            lead.status = "held"
        elif decision.action is Action.CALL_QUEUE:
            self._call_queue(lead)
        else:
            self._qualify(lead)

    def _qualify(self, lead: OutreachLead) -> None:
        if lead.niche is None:
            return self._disqualify(lead, "niche is not one of: " + ", ".join(NICHES))
        mx = self.mx_check(lead.email_domain)
        if mx is not True:
            return self._disqualify(lead, "domain has no MX record" if mx is False else "MX record could not be verified")
        lead.status = "qualified"
        self.db.add(OutreachLog(lead_id=lead.id, kind="sourcing", outcome="qualified", detail={"niche": lead.niche, "mx": True}))

    def _disqualify(self, lead: OutreachLead, reason: str) -> None:
        lead.status = "disqualified"
        self.db.add(OutreachLog(lead_id=lead.id, kind="sourcing", outcome="disqualified", detail={"reason": reason}))

    def _call_queue(self, lead: OutreachLead) -> None:
        """Denmark: the company's own reklamebeskyttelse in the CVR register decides. (The Robinson list covers
        private persons by CPR, not companies – an ApS/A/S is checked against CVR.)"""
        protected = self.cvr_lookup(lead.registration_number or "")
        if protected is True:
            lead.status = "blocked"
            lead.compliance = {**lead.compliance, "action": "BLOCK",
                               "reasons": [*lead.compliance.get("reasons", []), "reklamebeskyttet in the CVR register"]}
            lead.compliance_action = "BLOCK"
            self.db.add(OutreachLog(lead_id=lead.id, kind="call_queue", outcome="reklamebeskyttet", detail={}))
            return
        scrub = "cleared" if protected is False else "needs_review"
        lead.status = "call_queue"
        self.db.add(OutreachCallQueue(lead_id=lead.id, country=lead.country, company_name=lead.company_name,
                                      phone=lead.phone, registration_number=lead.registration_number, scrub_status=scrub,
                                      scrub={"cvr_reklamebeskyttet": protected}))
        self.db.add(OutreachLog(lead_id=lead.id, kind="call_queue", outcome=scrub, detail={}))

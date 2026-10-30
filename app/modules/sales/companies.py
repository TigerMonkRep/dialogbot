"""Companies in the sales channel: source facts, duplicates, existing customers, data quality and the API shape."""
from __future__ import annotations

import hashlib
import re
import uuid
from datetime import UTC, datetime, timedelta
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from app.models import (
    BusinessProfile,
    ReceptionAgreement,
    SalesCompany,
    SalesContact,
    SalesProfile,
    SalesScript,
    SalesSimulation,
    SalesSourceFact,
)

STALE_AFTER = timedelta(days=365)


def now() -> datetime:
    return datetime.now(UTC)


def normalize_domain(url: str | None) -> str | None:
    if not url:
        return None
    raw = url.strip()
    if "://" not in raw:
        raw = "https://" + raw
    host = (urlparse(raw).hostname or "").lower().rstrip(".")
    host = host.removeprefix("www.")
    return host or None


def clean_text(v, n: int) -> str:
    """One line, no markup characters that could pass for template syntax or instructions."""
    return re.sub(r"\s+", " ", re.sub(r"[{}\[\]<>`]", "", str(v or ""))).strip()[:n]


def add_fact(db: OrmSession, company: SalesCompany, *, field: str, value: str, ref: str, evidence: str = "",
             confidence: str = "high", extractor: str, fetched_at: datetime | None = None) -> SalesSourceFact | None:
    """Store one fact unless the same (field, value, source) is already there. Returns the (new or existing) row."""
    value = clean_text(value, 500)
    if not value:
        return None
    h = hashlib.sha256(f"{field}\x00{value}\x00{ref}".encode()).hexdigest()
    existing = db.scalar(select(SalesSourceFact).where(SalesSourceFact.company_id == company.id,
                                                       SalesSourceFact.content_hash == h))
    if existing is not None:
        existing.fetched_at = fetched_at or now()
        return existing
    f = SalesSourceFact(company_id=company.id, field=field[:40], value=value, url_or_ref=ref[:500],
                        fetched_at=fetched_at or now(), evidence=clean_text(evidence, 300), confidence=confidence,
                        extractor_version=extractor[:40], content_hash=h)
    db.add(f)
    db.flush()
    return f


def set_main_phone(db: OrmSession, company: SalesCompany, phone_e164: str, fact: SalesSourceFact | None) -> None:
    company.main_phone_e164 = phone_e164
    contact = db.scalar(select(SalesContact).where(SalesContact.company_id == company.id,
                                                   SalesContact.is_main_number.is_(True)))
    if contact is None:
        db.add(SalesContact(company_id=company.id, role="Hovednummer", phone_e164=phone_e164, is_main_number=True,
                            source_fact_id=fact.id if fact else None))
    elif contact.phone_e164 != phone_e164:
        contact.phone_e164, contact.source_fact_id, contact.status = phone_e164, fact.id if fact else None, "unverified"


def existing_customer(db: OrmSession, *, domain: str | None, cvr: str | None) -> uuid.UUID | None:
    """A workspace with an agreement whose business profile has this website domain or CVR number."""
    if not domain and not cvr:
        return None
    rows = db.execute(select(BusinessProfile.workspace_id, BusinessProfile.website_url, BusinessProfile.cvr)
                      .where(BusinessProfile.workspace_id.in_(select(ReceptionAgreement.workspace_id)))).all()
    for ws_id, url, ws_cvr in rows:
        if domain and normalize_domain(url) == domain:
            return ws_id
        if cvr and ws_cvr and re.sub(r"\D", "", ws_cvr) == cvr:
            return ws_id
    return None


def flag_duplicates(db: OrmSession, company: SalesCompany) -> None:
    """Mark — never merge — when another company shares a strong key. Same domain + other postal code = a branch."""
    company.possible_duplicate_of, company.duplicate_reason = None, None
    others = select(SalesCompany).where(SalesCompany.id != company.id)
    if company.cvr:
        other = db.scalar(others.where(SalesCompany.cvr == company.cvr).limit(1))
        if other:
            company.possible_duplicate_of, company.duplicate_reason = other.id, "Samme CVR-nummer"
            return
    if company.domain:
        same = db.scalars(others.where(SalesCompany.domain == company.domain)).all()
        for other in same:
            if other.postal_code == company.postal_code:
                company.possible_duplicate_of, company.duplicate_reason = other.id, "Samme hjemmeside og postnummer"
                return
        if same:
            company.possible_duplicate_of = same[0].id
            company.duplicate_reason = "Samme hjemmeside, anden adresse – mulig afdeling"
            return
    if company.main_phone_e164:
        other = db.scalar(others.where(SalesCompany.main_phone_e164 == company.main_phone_e164).limit(1))
        if other:
            company.possible_duplicate_of, company.duplicate_reason = other.id, "Samme telefonnummer"


def compute_quality(db: OrmSession, company: SalesCompany) -> dict:
    facts = db.scalars(select(SalesSourceFact).where(SalesSourceFact.company_id == company.id)).all()
    issues: list[str] = []
    if not company.website_url:
        issues.append("missing_website")
    if not company.main_phone_e164:
        issues.append("missing_phone")
    phones = {f.value for f in facts if f.field == "phone_e164"}
    if len(phones) > 1:
        issues.append("conflicting_phone")
    if any(f.fetched_at < now() - STALE_AFTER for f in facts):
        issues.append("stale")
    if company.advertising_protected is None:
        issues.append("advertising_protection_unknown")
    if company.google_business_status and company.google_business_status != "OPERATIONAL":
        issues.append("not_operational")
    q = {"issues": issues, "facts": len(facts), "checked_at": now().isoformat()}
    company.data_quality = q
    return q


ISSUE_TEXT = {
    "missing_website": "Ingen hjemmeside", "missing_phone": "Intet telefonnummer",
    "conflicting_phone": "Modstridende telefonnumre", "stale": "Oplysninger ældre end 12 måneder",
    "advertising_protection_unknown": "Reklamebeskyttelse ukendt", "not_operational": "Ikke i drift ifølge Google",
}


def contactable_hint(c: SalesCompany) -> dict:
    """Phase 1 cannot decide "may be called" (that is the contact policy in phase 2). It only shows what is already
    known to block. Unknown is never "yes"."""
    blockers = []
    if c.google_business_status and c.google_business_status != "OPERATIONAL":
        blockers.append("Ikke i drift")
    if c.advertising_protected is True:
        blockers.append("Reklamebeskyttet")
    if c.existing_customer_workspace_id:
        blockers.append("Eksisterende kunde")
    if not c.main_phone_e164:
        blockers.append("Intet nummer")
    return {"result": "BLOCK" if blockers else "NEEDS_REVIEW", "reasons": blockers or ["Kontaktpolitik kommer i fase 2"]}


def out(c: SalesCompany) -> dict:
    return {"id": str(c.id), "source": c.source, "display_name": c.display_name, "legal_name": c.legal_name,
            "cvr": c.cvr, "industry_key": c.industry_key, "industry_text": c.industry_text,
            "address_line": c.address_line, "postal_code": c.postal_code, "city": c.city,
            "website_url": c.website_url, "domain": c.domain, "main_phone_e164": c.main_phone_e164,
            "public_email": c.public_email, "google": {
                "place_id": c.google_place_id, "fetched_at": c.google_fetched_at.isoformat() if c.google_fetched_at else None,
                "types": c.google_types, "primary_type": c.google_primary_type,
                "business_status": c.google_business_status, "maps_uri": c.google_maps_uri,
                "opening_hours": c.google_opening_hours, "rating": c.rating, "user_rating_count": c.user_rating_count,
                "latitude": c.latitude, "longitude": c.longitude},
            "cvr_status": c.cvr_status, "advertising_protected": c.advertising_protected,
            "relevance_score": c.relevance_score, "relevance_reasons": c.relevance_reasons,
            "data_quality": c.data_quality, "research_status": c.research_status,
            "researched_at": c.researched_at.isoformat() if c.researched_at else None,
            "research_error": c.research_error,
            "research_started_at": c.research_started_at.isoformat() if c.research_started_at else None,
            "possible_duplicate_of": str(c.possible_duplicate_of) if c.possible_duplicate_of else None,
            "duplicate_reason": c.duplicate_reason,
            "existing_customer": c.existing_customer_workspace_id is not None,
            "contactable": contactable_hint(c),
            "last_search_job_id": str(c.last_search_job_id) if c.last_search_job_id else None,
            "first_seen_at": c.first_seen_at.isoformat() if c.first_seen_at else None,
            "updated_at": c.updated_at.isoformat() if c.updated_at else None}


def fact_out(f: SalesSourceFact) -> dict:
    src = "google" if f.url_or_ref.startswith("google_place:") else "import" if f.url_or_ref.startswith("import") \
        else "cvr" if f.url_or_ref.startswith("cvr:") else "website"
    return {"id": str(f.id), "field": f.field, "value": f.value, "url_or_ref": f.url_or_ref, "source": src,
            "fetched_at": f.fetched_at.isoformat(), "evidence": f.evidence, "confidence": f.confidence,
            "extractor_version": f.extractor_version}


def contact_out(c: SalesContact) -> dict:
    return {"id": str(c.id), "name": c.name, "role": c.role, "phone_e164": c.phone_e164, "email": c.email,
            "is_main_number": c.is_main_number, "status": c.status,
            "source_fact_id": str(c.source_fact_id) if c.source_fact_id else None}


def detail(db: OrmSession, c: SalesCompany) -> dict:
    from app.modules.sales import playbook, simulate

    facts = db.scalars(select(SalesSourceFact).where(SalesSourceFact.company_id == c.id)
                       .order_by(SalesSourceFact.field, SalesSourceFact.fetched_at.desc())).all()
    contacts = db.scalars(select(SalesContact).where(SalesContact.company_id == c.id)
                          .order_by(SalesContact.is_main_number.desc(), SalesContact.created_at)).all()
    profiles = db.scalars(select(SalesProfile).where(SalesProfile.company_id == c.id)
                          .order_by(SalesProfile.version.desc())).all()
    scripts = db.scalars(select(SalesScript).where(SalesScript.company_id == c.id)
                         .order_by(SalesScript.version.desc())).all()
    sims = db.scalars(select(SalesSimulation).where(SalesSimulation.company_id == c.id)
                      .order_by(SalesSimulation.created_at.desc()).limit(20)).all()
    timeline = sorted(
        [{"at": c.first_seen_at.isoformat(), "kind": "found", "text": f"Fundet ({c.source})"}]
        + ([{"at": c.researched_at.isoformat(), "kind": "researched", "text": "Hjemmeside undersøgt"}] if c.researched_at else [])
        + [{"at": p.created_at.isoformat(), "kind": "profile", "text": f"Profil v{p.version}"} for p in profiles]
        + [{"at": s.created_at.isoformat(), "kind": "script", "text": f"Manuskript v{s.version} ({s.status})"} for s in scripts]
        + [{"at": s.approved_at.isoformat(), "kind": "script_approved", "text": f"Manuskript v{s.version} godkendt"}
           for s in scripts if s.approved_at]
        + [{"at": s.created_at.isoformat(), "kind": "simulation", "text": f"Simulation: {s.outcome or 'ukendt udfald'}"}
           for s in sims],
        key=lambda e: e["at"], reverse=True)
    return out(c) | {"facts": [fact_out(f) for f in facts], "contacts": [contact_out(x) for x in contacts],
                     "profiles": [playbook.profile_out(p) for p in profiles],
                     "scripts": [playbook.script_out(s) for s in scripts],
                     "simulations": [simulate.out(s) for s in sims], "timeline": timeline,
                     "quality_text": [ISSUE_TEXT.get(i, i) for i in (c.data_quality or {}).get("issues", [])]}

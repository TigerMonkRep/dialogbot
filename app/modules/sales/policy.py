"""The contact policy for Dialogbot's own sales: may this contact be rung by Peter now? ALLOW, BLOCK or NEEDS_REVIEW.

Order (the first BLOCK wins; anything unknown makes NEEDS_REVIEW; unknown is never ALLOW):
 1. contact marked invalid, no usable number                     → BLOCK
 2. phone, domain or CVR on the sales block list                 → BLOCK
 3. number on the sales workspace's do-not-call list             → BLOCK
 4. company not operational (Google) or closed in CVR             → BLOCK
 5. existing customer                                            → BLOCK
 6. advertising protected in CVR → BLOCK; unknown                → NEEDS_REVIEW
 7. no valid basis (request/consent) for an AI call               → BLOCK (no_basis)
 8. attempts across all internal campaigns ≥ the limit            → BLOCK
 9. outside the campaign's calling window (Copenhagen time)       → BLOCK (outside_window, temporary)
10. campaign budget used up                                      → BLOCK
11. campaign not running (dispatch only)                         → BLOCK
12. script not approved                                          → NEEDS_REVIEW
13. SALES_OUTBOUND_MODE: only test/live ring; test only SALES_TEST_NUMBERS → BLOCK (mode)

The decision is stored in sales_policy_decisions every time, with the reasons and the evidence it used. It is evaluated
when a contact is planned into a campaign and again right before the provider is called (stage dispatch).
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session as OrmSession

from app.config import get_settings
from app.models import (
    Campaign,
    CampaignCall,
    CampaignContact,
    DoNotCall,
    SalesBlockList,
    SalesCompany,
    SalesContact,
    SalesContactBasis,
    SalesPolicyDecision,
    SalesScript,
)

TEMPORARY = {"outside_window", "max_concurrent"}
TEXT = {
    "invalid_contact": "Kontakten er markeret ugyldig",
    "no_phone": "Intet telefonnummer",
    "blocked_phone": "Nummeret står på Dialogbots spærreliste",
    "blocked_domain": "Domænet står på Dialogbots spærreliste",
    "blocked_cvr": "CVR-nummeret står på Dialogbots spærreliste",
    "do_not_call": "Nummeret har frabedt sig opkald",
    "closed": "Virksomheden er ikke i drift",
    "existing_customer": "Eksisterende kunde",
    "advertising_protected": "Reklamebeskyttet i CVR",
    "advertising_unknown": "Reklamebeskyttelse er ukendt (intet CVR-opslag)",
    "no_basis": "Intet gyldigt kontaktgrundlag for AI-opkald",
    "max_attempts": "Højeste antal forsøg er nået",
    "outside_window": "Uden for opkaldsvinduet",
    "budget": "Kampagnens budget er brugt",
    "campaign_not_running": "Kampagnen kører ikke",
    "script_not_approved": "Manuskriptet er ikke godkendt",
    "no_script": "Intet manuskript",
    "mode_off": "SALES_OUTBOUND_MODE tillader ikke opkald",
    "not_test_number": "I testtilstand må kun testnumre ringes op",
}


@dataclass
class Decision:
    result: str
    reasons: list[str] = field(default_factory=list)
    evidence: dict = field(default_factory=dict)
    checked_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    id: uuid.UUID | None = None

    @property
    def temporary(self) -> bool:
        return self.result == "BLOCK" and set(self.reasons) <= TEMPORARY

    def out(self) -> dict:
        return {"result": self.result, "reasons": self.reasons, "reason_text": [TEXT.get(r, r) for r in self.reasons],
                "evidence": self.evidence, "checked_at": self.checked_at.isoformat(),
                "id": str(self.id) if self.id else None}


def test_numbers() -> set[str]:
    from app.modules.campaigns.service import normalize_phone

    return {n for n in (normalize_phone(x) for x in get_settings().sales_test_numbers.split(",") if x.strip()) if n}


def valid_basis(db: OrmSession, contact: SalesContact, channel: str = "ai_call",
                now: datetime | None = None) -> SalesContactBasis | None:
    now = now or datetime.now(UTC)
    return db.scalar(select(SalesContactBasis).where(
        SalesContactBasis.contact_id == contact.id, SalesContactBasis.channel == channel,
        SalesContactBasis.withdrawn_at.is_(None), SalesContactBasis.granted_at <= now,
        or_(SalesContactBasis.valid_until.is_(None), SalesContactBasis.valid_until > now))
        .order_by(SalesContactBasis.granted_at.desc()).limit(1))


def attempts_across(db: OrmSession, contact: SalesContact) -> int:
    return db.scalar(select(func.coalesce(func.sum(CampaignContact.attempts), 0))
                     .join(Campaign, Campaign.id == CampaignContact.campaign_id)
                     .where(Campaign.kind == "internal_sales", Campaign.is_test.is_(False),
                            CampaignContact.sales_contact_id == contact.id)) or 0


def spent_net_minor(db: OrmSession, c: Campaign) -> int:
    rows = db.execute(select(func.coalesce(func.sum(CampaignCall.net_minor), 0),
                             func.coalesce(func.sum(CampaignCall.minutes_net_minor), 0))
                      .where(CampaignCall.campaign_id == c.id)).one()
    return int(rows[0]) + int(rows[1])


def evaluate(db: OrmSession, *, contact: SalesContact, campaign: Campaign | None = None, stage: str = "check",
             script: SalesScript | None = None, channel: str = "ai_call", now: datetime | None = None,
             store: bool = True) -> Decision:
    from app.modules.campaigns.service import in_window, max_cost_net_minor, started_minutes
    from app.modules.sales import service as sales

    s = get_settings()
    now = now or datetime.now(UTC)
    company = db.get(SalesCompany, contact.company_id)
    block: list[str] = []
    review: list[str] = []
    ev: dict = {"phone": contact.phone_e164, "company_id": str(company.id), "mode": s.sales_outbound_mode}

    if contact.status == "invalid":
        block.append("invalid_contact")
    if not contact.phone_e164:
        block.append("no_phone")
    keys = [("phone", contact.phone_e164), ("domain", company.domain), ("cvr", company.cvr)]
    for kind, value in keys:
        if value and db.scalar(select(SalesBlockList.id).where(SalesBlockList.kind == kind, SalesBlockList.value == value)):
            block.append(f"blocked_{kind}")
    ws = sales.sales_workspace(db)
    if ws is not None and contact.phone_e164 and db.scalar(
            select(DoNotCall.id).where(DoNotCall.workspace_id == ws.id, DoNotCall.phone == contact.phone_e164)):
        block.append("do_not_call")
    status_text = (company.cvr_status or "").lower()
    if (company.google_business_status and company.google_business_status != "OPERATIONAL") or any(
            w in status_text for w in ("ophørt", "opløst", "konkurs", "tvangsopløsning", "likvidation")):
        block.append("closed")
    if company.existing_customer_workspace_id:
        block.append("existing_customer")
    if company.advertising_protected is True:
        block.append("advertising_protected")
    elif company.advertising_protected is None and not (campaign is not None and campaign.is_test):
        review.append("advertising_unknown")  # a test call rings the operator's own number, not the company
    basis = valid_basis(db, contact, channel, now)
    if basis is None:
        block.append("no_basis")
    else:
        ev["basis"] = {"id": str(basis.id), "kind": basis.kind, "source": basis.source, "text_version": basis.text_version,
                       "granted_at": basis.granted_at.isoformat()}
    limit = s.sales_max_attempts_per_contact
    tries = attempts_across(db, contact)
    ev["attempts"] = tries
    if tries >= limit and not (campaign is not None and campaign.is_test):
        block.append("max_attempts")
    if campaign is not None:
        ev["campaign_id"] = str(campaign.id)
        from app.modules.reports.service import tz_of

        if not in_window(campaign, tz_of(db, campaign.workspace_id), now):
            block.append("outside_window")
        if campaign.budget_net_minor is not None:
            per_attempt = campaign.call_net_minor + started_minutes(campaign.max_connected_seconds) * campaign.minute_net_minor
            spent = spent_net_minor(db, campaign)
            ev["budget"] = {"limit": campaign.budget_net_minor, "spent": spent, "per_attempt": per_attempt,
                            "max_remaining": max_cost_net_minor(db, campaign)}
            if spent + per_attempt > campaign.budget_net_minor:
                block.append("budget")
        if stage == "dispatch" and campaign.status != "running":
            block.append("campaign_not_running")
    if script is None:
        review.append("no_script")
    elif script.status != "approved":
        review.append("script_not_approved")
    else:
        ev["script_id"] = str(script.id)
    mode = s.sales_outbound_mode
    if mode not in ("test", "live"):
        block.append("mode_off")
    elif mode == "test" and contact.phone_e164 not in test_numbers():
        block.append("not_test_number")
    result = "BLOCK" if block else "NEEDS_REVIEW" if review else "ALLOW"
    d = Decision(result=result, reasons=block + review, evidence=ev, checked_at=now)
    if store:
        row = SalesPolicyDecision(contact_id=contact.id, campaign_id=campaign.id if campaign else None, stage=stage,
                                  result=result, reasons=d.reasons, evidence=ev, decided_at=now)
        db.add(row)
        db.flush()
        d.id = row.id
    return d


def latest(db: OrmSession, contact_id: uuid.UUID) -> SalesPolicyDecision | None:
    return db.scalar(select(SalesPolicyDecision).where(SalesPolicyDecision.contact_id == contact_id)
                     .order_by(SalesPolicyDecision.decided_at.desc()).limit(1))


def decision_out(row: SalesPolicyDecision | None) -> dict | None:
    if row is None:
        return None
    return {"id": str(row.id), "result": row.result, "reasons": row.reasons,
            "reason_text": [TEXT.get(r, r) for r in row.reasons], "stage": row.stage,
            "campaign_id": str(row.campaign_id) if row.campaign_id else None, "decided_at": row.decided_at.isoformat()}

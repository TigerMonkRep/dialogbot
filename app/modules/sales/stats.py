"""Sales statistics (phase 3): every figure with numerator, denominator and its definition in Danish.

Test campaigns (`campaigns.is_test`, which includes every internal test call) and simulations never count. The window
is [from, to) in Copenhagen days; a figure without a window (contactable now) says so in its definition. Money is in
øre ekskl. moms; provider costs are the providers' own reported cost in USD and labelled as an estimate.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import and_, distinct, func, select
from sqlalchemy.orm import Session as OrmSession

from app.models import (
    Call,
    Campaign,
    CampaignCall,
    CampaignContact,
    SalesBlockList,
    SalesCompany,
    SalesContact,
    SalesMeeting,
    SalesOffer,
    SalesOpenQuestion,
    SalesPolicyDecision,
    SalesQualification,
)

TZ = ZoneInfo("Europe/Copenhagen")
SHORT_CALL_SECONDS = 20


def _bounds(d_from: date, d_to: date) -> tuple[datetime, datetime]:
    return datetime.combine(d_from, time(0), tzinfo=TZ), datetime.combine(d_to + timedelta(days=1), time(0), tzinfo=TZ)


def _m(key: str, label: str, numerator: int, denominator: int | None, definition: str, unit: str = "count") -> dict:
    value = numerator if denominator is None else (round(numerator / denominator, 4) if denominator else None)
    return {"key": key, "label": label, "value": value, "numerator": numerator, "denominator": denominator,
            "unit": unit, "definition": definition}


def compute(db: OrmSession, d_from: date, d_to: date, campaign_id: uuid.UUID | None = None) -> dict:
    start, end = _bounds(d_from, d_to)
    real = and_(Campaign.kind == "internal_sales", Campaign.is_test.is_(False))
    if campaign_id is not None:
        real = and_(real, Campaign.id == campaign_id)
    scalar = lambda q: db.scalar(q) or 0  # noqa: E731

    attempts_q = (select(CampaignCall).join(Campaign, Campaign.id == CampaignCall.campaign_id)
                  .where(real, CampaignCall.dialled_at >= start, CampaignCall.dialled_at < end))
    attempt_ids = attempts_q.with_only_columns(CampaignCall.provider_call_id).where(CampaignCall.provider_call_id.is_not(None))
    attempts = scalar(select(func.count()).select_from(attempts_q.subquery()))
    calls = select(Call).where(Call.provider_call_id.in_(attempt_ids))
    answered = scalar(select(func.count()).select_from(calls.where(Call.duration_seconds > 0).subquery()))
    short = scalar(select(func.count()).select_from(
        calls.where(Call.duration_seconds > 0, Call.duration_seconds < SHORT_CALL_SECONDS).subquery()))
    call_ids = calls.with_only_columns(Call.id)
    qualified = scalar(select(func.count(distinct(SalesQualification.call_id))).where(
        SalesQualification.call_id.in_(call_ids), SalesQualification.accept_no == 1, SalesQualification.result == "JA"))
    order_interest = scalar(select(func.count(distinct(SalesQualification.call_id))).where(
        SalesQualification.call_id.in_(call_ids), SalesQualification.accept_no == 5, SalesQualification.result == "JA"))
    cost_usd_micros = scalar(select(func.sum(Call.cost_usd_micros)).where(Call.provider_call_id.in_(attempt_ids)))
    failed = scalar(select(func.count()).select_from(CampaignContact).join(Campaign, Campaign.id == CampaignContact.campaign_id)
                    .where(real, CampaignContact.status.in_(("failed", "unknown")), CampaignContact.last_attempt_at >= start,
                           CampaignContact.last_attempt_at < end))

    contacted_companies = select(SalesContact.company_id).distinct().join(
        CampaignContact, CampaignContact.sales_contact_id == SalesContact.id).join(
        CampaignCall, CampaignCall.contact_id == CampaignContact.id).join(
        Campaign, Campaign.id == CampaignCall.campaign_id).where(
        real, CampaignCall.dialled_at >= start, CampaignCall.dialled_at < end)
    contacted = scalar(select(func.count()).select_from(contacted_companies.subquery()))

    found = scalar(select(func.count()).select_from(SalesCompany).where(
        SalesCompany.first_seen_at >= start, SalesCompany.first_seen_at < end))
    latest = (select(SalesPolicyDecision.contact_id, func.max(SalesPolicyDecision.decided_at).label("at"))
              .group_by(SalesPolicyDecision.contact_id).subquery())
    allow_now = scalar(select(func.count()).select_from(SalesPolicyDecision).join(
        latest, and_(latest.c.contact_id == SalesPolicyDecision.contact_id, latest.c.at == SalesPolicyDecision.decided_at))
        .where(SalesPolicyDecision.result == "ALLOW"))
    contacts_total = scalar(select(func.count()).select_from(SalesContact))

    def meetings(status: str) -> int:
        return scalar(select(func.count()).select_from(SalesMeeting).where(
            SalesMeeting.status == status, SalesMeeting.created_at >= start, SalesMeeting.created_at < end))

    offers_sent = scalar(select(func.count()).select_from(SalesOffer).where(SalesOffer.sent_at >= start, SalesOffer.sent_at < end))
    accepted = scalar(select(func.count()).select_from(SalesOffer).where(
        SalesOffer.accepted_at >= start, SalesOffer.accepted_at < end))
    paying = scalar(select(func.count(distinct(SalesOffer.company_id))).where(
        SalesOffer.first_invoice_paid_at >= start, SalesOffer.first_invoice_paid_at < end))
    mrr = scalar(select(func.sum(SalesOffer.monthly_net_minor)).where(SalesOffer.first_invoice_paid_at.is_not(None)))
    opt_outs = scalar(select(func.count()).select_from(SalesBlockList).where(
        SalesBlockList.source == "call", SalesBlockList.created_at >= start, SalesBlockList.created_at < end))
    disputes = scalar(select(func.count()).select_from(SalesBlockList).where(
        SalesBlockList.source == "dispute", SalesBlockList.created_at >= start, SalesBlockList.created_at < end))
    open_q = scalar(select(func.count()).select_from(SalesOpenQuestion).where(SalesOpenQuestion.status == "open"))

    metrics = [
        _m("companies_found", "Fundne virksomheder", found, None, "Virksomheder fundet eller importeret i perioden."),
        _m("contactable", "Kontaktbare nu", allow_now, contacts_total,
           "Kontakter, hvis seneste kontaktpolitik-afgørelse er ALLOW, ud af alle kontakter (øjebliksbillede, ikke periode)."),
        _m("answer_rate", "Svarprocent", answered, attempts,
           "Besvarede opkald (varighed > 0 s) ud af opkaldsforsøg i perioden. Testkampagner tælles ikke."),
        _m("qualified", "Kvalificerede samtaler", qualified, answered,
           "Besvarede opkald, hvor delaccept 1 (problemet er forstået) er JA, ud af besvarede opkald."),
        _m("meetings_confirmed", "Møder bekræftet", meetings("confirmed"), None, "Bookede intro-møder oprettet i perioden."),
        _m("meetings_cancelled", "Møder aflyst", meetings("cancelled"), None, "Intro-møder fra perioden, der er aflyst."),
        _m("meetings_held", "Møder afholdt", meetings("held"), None, "Intro-møder fra perioden, markeret som afholdt."),
        _m("offers_sent", "Tilbud sendt", offers_sent, None, "Tilbud, hvis link er sendt i perioden (sendt er ikke en ordre)."),
        _m("order_interest", "Ordreinteresse", order_interest, answered,
           "Besvarede opkald, hvor delaccept 5 (prisen giver mening) er JA, ud af besvarede opkald."),
        _m("orders_accepted", "Ordrer accepteret", accepted, offers_sent,
           "Tilbud accepteret på acceptsiden i perioden (ud af tilbud sendt i perioden)."),
        _m("new_paying", "Nye betalende kunder", paying, None,
           "Virksomheder, hvis arbejdsrum fik sin første betalte Stripe-faktura i perioden."),
        _m("conversion", "Konvertering", paying, contacted,
           "Nye betalende kunder i perioden ud af unikke virksomheder, der blev ringet til i perioden."),
        _m("subscription_value", "Abonnementsværdi pr. måned", mrr, None,
           "Summen af månedsprisen på accepterede og betalte tilbud (øre ekskl. moms), alle perioder.", unit="minor"),
        _m("provider_cost", "Opkaldsomkostning (estimat)", cost_usd_micros, None,
           "Leverandørernes egen rapporterede pris for opkaldene i perioden, i milliontedele USD. Et estimat.",
           unit="usd_micros"),
        _m("cost_per_customer", "Omkostning pr. ny kunde (estimat)", cost_usd_micros, paying,
           "Opkaldsomkostning (estimat) delt med nye betalende kunder. Tom, når der ingen nye kunder er.", unit="usd_micros"),
        _m("opt_outs", "Frabedelser", opt_outs, None, "Numre spærret fra et opkald i perioden."),
        _m("disputes", "Klager over kilde", disputes, None, "Spærringer med kilden 'bestridt' i perioden."),
        _m("open_questions", "Ubesvarede spørgsmål", open_q, None, "Spørgsmål Peter ikke kunne svare på, som stadig er åbne."),
        _m("short_calls", "Afbrudt under 20 s", short, answered, "Besvarede opkald under 20 sekunder ud af besvarede opkald."),
        _m("errors", "Fejlede forsøg", failed, attempts, "Kontakter med status fejlet eller uvist i perioden ud af forsøg."),
    ]
    return {"from": d_from.isoformat(), "to": d_to.isoformat(), "campaign_id": str(campaign_id) if campaign_id else None,
            "excluded": "Testkampagner, testopkald og simulationer er udeladt.", "metrics": metrics}

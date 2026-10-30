"""Retention and data subject rights for Dialogbot's own sales (phase 4).

Retention (worker, daily): recordings older than SALES_RETENTION_AUDIO_DAYS are deleted; transcripts older than
SALES_RETENTION_TRANSCRIPT_DAYS are anonymised (each line becomes "[slettet]", `transcript_status=DELETED`) and Vapi is
asked to delete its copy; summaries are cleared after SALES_RETENTION_SUMMARY_DAYS. The audit trail and the call row
(time, duration, outcome) stay. Only calls of internal sales campaigns are touched – never a customer's calls.

Requests (`sales_data_requests`): access exports everything held about a phone number, e-mail or CVR number as JSON;
erasure applies the same deletions at once and removes contacts and facts; objection adds the value to the block list.
A blocked phone number is kept on the block list – that is what makes "ring ikke igen" work.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import or_, select
from sqlalchemy.orm import Session as OrmSession

from app.config import get_settings
from app.core.errors import ValidationFailed
from app.models import (
    Call,
    CallRecording,
    Campaign,
    CampaignContact,
    ConversationMessage,
    SalesBlockList,
    SalesCompany,
    SalesContact,
    SalesContactBasis,
    SalesDataRequest,
    SalesMeeting,
    SalesMessageRequest,
    SalesOffer,
    SalesSourceFact,
)
from app.modules.sales import recordings

log = structlog.get_logger("dialogbot.sales.privacy")
DELETED_TEXT = "[slettet]"


def _sales_calls():
    return (select(Call, CampaignContact).join(CampaignContact, CampaignContact.id == Call.campaign_contact_id)
            .join(Campaign, Campaign.id == CampaignContact.campaign_id).where(Campaign.kind == "internal_sales"))


def anonymise_transcript(db: OrmSession, call: Call, cc: CampaignContact) -> None:
    if cc.conversation_id:
        for m in db.scalars(select(ConversationMessage).where(ConversationMessage.conversation_id == cc.conversation_id)):
            m.text = DELETED_TEXT
    call.transcript_status = "DELETED"


def clear_summary(call: Call, cc: CampaignContact) -> None:
    call.summary = ""
    cc.summary = ""


def run_retention(db: OrmSession, now: datetime | None = None) -> dict:
    s = get_settings()
    now = now or datetime.now(UTC)
    done = {"audio": 0, "transcripts": 0, "summaries": 0}
    for rec in db.scalars(select(CallRecording).join(Call, Call.id == CallRecording.call_id).where(
            CallRecording.status == "AVAILABLE",
            CallRecording.available_at < now - timedelta(days=s.sales_retention_audio_days))):
        if db.scalar(_sales_calls().with_only_columns(Call.id).where(Call.id == rec.call_id)):
            recordings.delete(db, rec, "retention")
            done["audio"] += 1
    for call, cc in db.execute(_sales_calls().where(
            Call.transcript_status != "DELETED", Call.started_at < now - timedelta(days=s.sales_retention_transcript_days))):
        anonymise_transcript(db, call, cc)
        recordings.delete_at_vapi(call.provider_call_id)
        done["transcripts"] += 1
    for call, cc in db.execute(_sales_calls().where(
            Call.summary != "", Call.started_at < now - timedelta(days=s.sales_retention_summary_days))):
        clear_summary(call, cc)
        done["summaries"] += 1
    db.commit()
    if any(done.values()):
        log.info("sales.retention", **done)
    return done


# --------------------------------------------------------------------------- data subject requests


def _normalise(subject: str, value: str) -> str:
    from app.modules.sales.service import danish_number

    v = (value or "").strip()
    if subject == "phone":
        out = danish_number(v)
    elif subject == "email":
        out = v.lower() if "@" in v else ""
    else:
        out = "".join(ch for ch in v if ch.isdigit())
        out = out if len(out) == 8 else ""
    if not out:
        raise ValidationFailed("Ugyldig værdi for den valgte type.", field_errors=[{"field": "value"}])
    return out


def _match(db: OrmSession, subject: str, value: str) -> tuple[list[SalesCompany], list[SalesContact], list[str]]:
    """Companies, contacts and phone numbers the subject covers."""
    if subject == "phone":
        contacts = list(db.scalars(select(SalesContact).where(SalesContact.phone_e164 == value)))
        companies = list(db.scalars(select(SalesCompany).where(SalesCompany.main_phone_e164 == value)))
        phones = [value]
    elif subject == "email":
        contacts = list(db.scalars(select(SalesContact).where(SalesContact.email == value)))
        companies = list(db.scalars(select(SalesCompany).where(SalesCompany.public_email == value)))
        phones = [c.phone_e164 for c in contacts if c.phone_e164]
    else:
        companies = list(db.scalars(select(SalesCompany).where(SalesCompany.cvr == value)))
        contacts = list(db.scalars(select(SalesContact).where(SalesContact.company_id.in_([c.id for c in companies]))))
        phones = [c.phone_e164 for c in contacts if c.phone_e164] + [c.main_phone_e164 for c in companies if c.main_phone_e164]
    return companies, contacts, sorted(set(phones))


def _calls(db: OrmSession, phones: list[str]) -> list[tuple[Call, CampaignContact]]:
    if not phones:
        return []
    return list(db.execute(_sales_calls().where(CampaignContact.phone.in_(phones))).all())


def export(db: OrmSession, subject: str, value: str) -> dict:
    companies, contacts, phones = _match(db, subject, value)
    company_ids = [c.id for c in companies] + [c.company_id for c in contacts]
    calls = _calls(db, phones)
    msgs = []
    for call, cc in calls:
        lines = (db.scalars(select(ConversationMessage).where(ConversationMessage.conversation_id == cc.conversation_id)
                            .order_by(ConversationMessage.created_at)).all() if cc.conversation_id else [])
        rec = db.scalar(select(CallRecording).where(CallRecording.call_id == call.id))
        msgs.append({"started_at": call.started_at.isoformat() if call.started_at else None,
                     "duration_seconds": call.duration_seconds, "outcome": call.outcome, "summary": call.summary,
                     "transcript": [{"role": m.role, "text": m.text} for m in lines],
                     "recording": recordings.out(rec)})
    facts = db.scalars(select(SalesSourceFact).where(SalesSourceFact.company_id.in_(company_ids))).all()
    basis = db.scalars(select(SalesContactBasis).where(SalesContactBasis.contact_id.in_([c.id for c in contacts]))).all()
    return {
        "subject": subject, "value": value, "generated_at": datetime.now(UTC).isoformat(),
        "companies": [{"name": c.display_name, "cvr": c.cvr, "address": c.address_line, "postal_code": c.postal_code,
                       "city": c.city, "website": c.website_url, "phone": c.main_phone_e164, "email": c.public_email,
                       "source": c.source, "first_seen_at": c.first_seen_at.isoformat()} for c in companies],
        "contacts": [{"name": c.name, "role": c.role, "phone": c.phone_e164, "email": c.email} for c in contacts],
        "facts": [{"field": f.field, "value": f.value, "source": f.url_or_ref, "fetched_at": f.fetched_at.isoformat()}
                  for f in facts],
        "contact_basis": [{"kind": b.kind, "source": b.source, "text": b.text, "granted_at": b.granted_at.isoformat(),
                           "withdrawn_at": b.withdrawn_at.isoformat() if b.withdrawn_at else None} for b in basis],
        "calls": msgs,
        "offers": [{"version": o.version, "status": o.status, "sent_to": o.sent_to} for o in db.scalars(
            select(SalesOffer).where(SalesOffer.company_id.in_(company_ids)))],
        "messages": [{"channel": r.channel, "destination": r.destination, "status": r.status} for r in db.scalars(
            select(SalesMessageRequest).where(or_(SalesMessageRequest.company_id.in_(company_ids),
                                                  SalesMessageRequest.destination == value)))],
        "block_list": [{"kind": b.kind, "value": b.value, "reason": b.reason} for b in db.scalars(
            select(SalesBlockList).where(SalesBlockList.value.in_([value, *phones])))],
    }


def erase(db: OrmSession, subject: str, value: str) -> dict:
    companies, contacts, phones = _match(db, subject, value)
    result = {"calls_anonymised": 0, "recordings_deleted": 0, "contacts_deleted": 0, "companies_deleted": 0,
              "messages_redacted": 0}
    for call, cc in _calls(db, phones):
        anonymise_transcript(db, call, cc)
        clear_summary(call, cc)
        cc.name = ""
        rec = db.scalar(select(CallRecording).where(CallRecording.call_id == call.id))
        if rec is not None and rec.status == "AVAILABLE":
            recordings.delete(db, rec, "erasure")
            result["recordings_deleted"] += 1
        recordings.delete_at_vapi(call.provider_call_id)
        result["calls_anonymised"] += 1
    contact_ids = [c.id for c in contacts]
    for r in db.scalars(select(SalesMessageRequest).where(or_(SalesMessageRequest.contact_id.in_(contact_ids),
                                                              SalesMessageRequest.destination == value))):
        r.destination, r.requested_quote = DELETED_TEXT, ""
        result["messages_redacted"] += 1
    for m in db.scalars(select(SalesMeeting).where(SalesMeeting.contact_id.in_(contact_ids))):
        m.note = ""
    for c in contacts:
        db.delete(c)
        result["contacts_deleted"] += 1
    if subject == "cvr":  # a company asked to be forgotten: its research goes too (the block list entry stays)
        for c in companies:
            if c.existing_customer_workspace_id is None:
                db.delete(c)
                result["companies_deleted"] += 1
    else:
        for c in companies:
            if subject == "email" and c.public_email == value:
                c.public_email = None
            for f in db.scalars(select(SalesSourceFact).where(SalesSourceFact.company_id == c.id,
                                                              SalesSourceFact.value == value)):
                db.delete(f)
    return result


def _block(db: OrmSession, subject: str, value: str, reason: str, user_id: uuid.UUID) -> list[str]:
    """Never contact again: the phone/CVR itself, or for an e-mail the phone numbers it covers."""
    from app.modules.sales import outbound

    targets = [("cvr", value)] if subject == "cvr" else [("phone", value)] if subject == "phone" else [
        ("phone", p) for p in _match(db, subject, value)[2]]
    for kind, v in targets:
        outbound.block(db, kind=kind, value=v, reason=reason, source="manual", user_id=user_id)
    return [v for _, v in targets]


def handle(db: OrmSession, *, subject: str, value: str, kind: str, user_id: uuid.UUID) -> SalesDataRequest:
    if subject not in ("phone", "email", "cvr") or kind not in ("access", "erasure", "objection"):
        raise ValidationFailed("Ugyldig anmodning.", field_errors=[{"field": "kind"}])
    v = _normalise(subject, value)
    req = SalesDataRequest(subject=subject, value=v, kind=kind, status="open")
    db.add(req)
    db.flush()
    if kind == "access":
        result = export(db, subject, v)
    elif kind == "erasure":
        blocked = _block(db, subject, v, "Sletning ønsket", user_id)  # before the contacts (and their numbers) go
        result = erase(db, subject, v) | {"blocked": blocked}
    else:
        result = {"blocked": _block(db, subject, v, "Indsigelse", user_id)}
    req.status, req.handled_by, req.handled_at, req.result = "done", user_id, datetime.now(UTC), result
    return req


def request_out(r: SalesDataRequest, *, include_result: bool = False) -> dict:
    out = {"id": str(r.id), "subject": r.subject, "value": r.value, "kind": r.kind, "status": r.status,
           "handled_at": r.handled_at.isoformat() if r.handled_at else None, "created_at": r.created_at.isoformat()}
    if include_result:
        out["result"] = r.result
    return out

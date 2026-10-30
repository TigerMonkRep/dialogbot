"""Dialogbot's own outbound sales calls: contacts and their basis, the block list, internal campaigns, Peter's
assistant for a personal script, test calls, and what happens when a call ends.

Internal campaigns reuse the campaign engine (app/modules/campaigns): window, attempts, billing rows, the dialler and
the end-of-call report. What is added for `kind="internal_sales"`:
- every contact is a sales contact with an approved script and passes the contact policy (app/modules/sales/policy)
  when planned and again right before Vapi is called – a withdrawn basis or an opt-out in between stops the call;
- the dispatch key is committed before the provider is called; a call whose creation cannot be confirmed is marked
  `unknown` and never redialled automatically;
- Peter rings with the script's rendered instruction + the sales workspace's public/customer_docs knowledge;
- after the call: outcome on the call row, partial accepts with the customer's own words, opt-out → block list.
"""
from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session as OrmSession

from app.config import get_settings
from app.core.errors import ApiError, Conflict, NotFound, ValidationFailed
from app.models import (
    Call,
    Campaign,
    CampaignContact,
    Conversation,
    ConversationMessage,
    DoNotCall,
    SalesBlockList,
    SalesCallEvent,
    SalesCompany,
    SalesContact,
    SalesContactBasis,
    SalesQualification,
    SalesScript,
    Workspace,
)
from app.modules.billing import prices
from app.modules.sales import companies, policy

log = structlog.get_logger("dialogbot.sales.outbound")
MAX_SECONDS = 600

def sales_pronunciations() -> tuple[dict, ...]:
    """Peter's own defaults (a workspace entry under Stemmer → Udtale still wins). Danes say "AI" as the Danish letters;
    the list prices are written out because Vapi's number formatters are off (they speak English) and the voice
    misread "2.495"."""
    from app.modules.billing import prices
    from app.modules.voices import danish

    amounts = (prices.SUBSCRIPTION_MONTHLY_NET_MINOR, prices.SPECIALIST_SETUP_NET_MINOR)
    return ({"term": "AI", "say": "a i"},
            *({"term": prices.kr(m), "say": danish.number(m // 100)} for m in amounts if m >= 100_000))


# Peter has no tools on a call yet (calendar, e-mail, SMS and order tools come with phase 3). Without this block the
# model improvised "I'll check the calendar" and went silent, then promised an e-mail nobody sends.
NO_TOOLS_RULES = """VÆRKTØJER I DETTE OPKALD – går forud for manuskriptet:
Du har ingen værktøjer: ingen kalender, ingen e-mail, ingen SMS og ingen ordre. Sig aldrig, at du kigger i en kalender,
tjekker ledige tider eller sender en mail, et link, en demo eller en bestilling, og lad aldrig kunden vente i stilhed.
Nævner manuskriptet opret_ordreudkast, send_bestillingslink eller et møde, så gør i stedet sådan: spørg hvilken dag og
hvilket tidsrum der passer, og om e-mail eller telefon er bedst. Gentag det kort én gang, og sig: "En kollega fra
Dialogbot vender tilbage og bekræfter det." Lov aldrig et bestemt tidspunkt, en mail eller en demo-video."""
TEST_BASIS_TEXT = ("Operatøren har bekræftet, at nummeret er operatørens eget testnummer, og at Peter fra Dialogbot "
                   "(en AI-assistent) må ringe op til det i en intern test.")
TEST_BASIS_VERSION = "sales-test-basis-v1"


def _now() -> datetime:
    return datetime.now(UTC)


def sales_ws(db: OrmSession) -> Workspace:
    from app.modules.sales import service

    ws = service.sales_workspace(db)
    if ws is None:
        raise ApiError("Kræver salgsarbejdsrummet (SALES_WORKSPACE_ID).", code="sales_workspace_missing",
                       status_code=503)
    return ws


# --------------------------------------------------------------------------- contacts and basis


def add_contact(db: OrmSession, company: SalesCompany, *, name: str | None, role: str | None, phone: str | None,
                email: str | None) -> SalesContact:
    from app.modules.campaigns.service import normalize_phone

    e164 = normalize_phone(phone) if phone else None
    if phone and not e164:
        raise ValidationFailed("Ugyldigt telefonnummer", field_errors=[{"field": "phone"}])
    if not (e164 or email):
        raise ValidationFailed("Angiv telefon eller e-mail", field_errors=[{"field": "phone"}])
    c = SalesContact(company_id=company.id, name=companies.clean_text(name, 200) or None,
                     role=companies.clean_text(role, 120) or None, phone_e164=e164, email=(email or "").strip()[:320] or None,
                     status="unverified")
    db.add(c)
    db.flush()
    return c


def record_basis(db: OrmSession, contact: SalesContact, *, channel: str, purpose: str, kind: str, source: str, text: str,
                 text_version: str, evidence_ref: str, valid_until: datetime | None, user_id: uuid.UUID | None,
                 granted_at: datetime | None = None) -> SalesContactBasis:
    if len(text.strip()) < 20:
        raise ValidationFailed("Skriv hele teksten, kontakten sagde ja til (mindst 20 tegn)",
                               field_errors=[{"field": "text"}])
    b = SalesContactBasis(contact_id=contact.id, channel=channel, purpose=purpose.strip()[:200], kind=kind,
                          text_version=text_version.strip()[:40] or "operator-v1", text=text.strip()[:4000],
                          source=source, evidence_ref=evidence_ref.strip()[:300], granted_at=granted_at or _now(),
                          valid_until=valid_until, recorded_by=user_id)
    db.add(b)
    db.flush()
    return b


def withdraw_basis(db: OrmSession, b: SalesContactBasis, reason: str) -> SalesContactBasis:
    if b.withdrawn_at is None:
        b.withdrawn_at, b.withdrawn_reason = _now(), reason.strip()[:300] or "Tilbagekaldt"
    return b


def basis_out(b: SalesContactBasis) -> dict:
    now = _now()
    return {"id": str(b.id), "contact_id": str(b.contact_id), "channel": b.channel, "purpose": b.purpose, "kind": b.kind,
            "text_version": b.text_version, "text": b.text, "source": b.source, "evidence_ref": b.evidence_ref,
            "granted_at": b.granted_at.isoformat(), "valid_until": b.valid_until.isoformat() if b.valid_until else None,
            "withdrawn_at": b.withdrawn_at.isoformat() if b.withdrawn_at else None,
            "withdrawn_reason": b.withdrawn_reason,
            "valid": b.withdrawn_at is None and (b.valid_until is None or b.valid_until > now)}


def block(db: OrmSession, *, kind: str, value: str, reason: str, source: str, user_id: uuid.UUID | None) -> SalesBlockList:
    from app.modules.campaigns.service import normalize_phone

    if kind == "phone":
        value = normalize_phone(value) or ""
    elif kind == "domain":
        value = companies.normalize_domain(value) or ""
    else:
        value = "".join(ch for ch in value if ch.isdigit())
    if not value:
        raise ValidationFailed("Ugyldig værdi", field_errors=[{"field": "value"}])
    row = db.scalar(select(SalesBlockList).where(SalesBlockList.kind == kind, SalesBlockList.value == value))
    if row is None:
        row = SalesBlockList(kind=kind, value=value, reason=reason.strip()[:300], source=source, created_by=user_id)
        db.add(row)
        db.flush()
    if kind == "phone":  # also the sales workspace's own do-not-call list, which every campaign there respects
        from app.modules.sales import service

        ws = service.sales_workspace(db)
        if ws is not None and not db.scalar(select(DoNotCall.id).where(DoNotCall.workspace_id == ws.id,
                                                                        DoNotCall.phone == value)):
            db.add(DoNotCall(workspace_id=ws.id, phone=value, source="call" if source == "call" else "manual",
                             reason=reason.strip()[:300]))
        # pending attempts for this number stop now
        for cc in db.scalars(select(CampaignContact).join(Campaign, Campaign.id == CampaignContact.campaign_id)
                             .where(Campaign.kind == "internal_sales", CampaignContact.phone == value,
                                    CampaignContact.status == "pending")):
            cc.status, cc.error = "skipped", "Spærret"
    return row


def block_out(b: SalesBlockList) -> dict:
    return {"id": str(b.id), "kind": b.kind, "value": b.value, "reason": b.reason, "source": b.source,
            "created_at": b.created_at.isoformat() if b.created_at else None}


# --------------------------------------------------------------------------- campaigns


def create_campaign(db: OrmSession, *, name: str, budget_net_minor: int | None, call_days: list[str], call_from: str,
                    call_to: str, max_attempts: int, user_id: uuid.UUID, is_test: bool = False) -> Campaign:
    from app.modules.campaigns.service import DAYS
    from app.modules.sales import service

    ws = sales_ws(db)
    number = service.caller_number(db, ws)
    if not set(call_days) <= set(DAYS) or not call_days:
        raise ValidationFailed("Ugyldige dage", field_errors=[{"field": "call_days"}])
    if not (call_from < call_to):
        raise ValidationFailed("Opkaldsvinduet skal starte før det slutter", field_errors=[{"field": "call_to"}])
    limit = get_settings().sales_max_attempts_per_contact
    c = Campaign(workspace_id=ws.id, name=name.strip()[:160], status="draft", kind="internal_sales", is_test=is_test,
                 purpose="Dialogbots eget salg: Peter ringer med et personligt manuskript pr. virksomhed.",
                 phone_number_id=number.id if number else None, call_days=call_days, call_from=call_from,
                 call_to=call_to, call_net_minor=prices.CAMPAIGN_CALL_NET_MINOR,
                 minute_net_minor=prices.CAMPAIGN_MINUTE_NET_MINOR, max_attempts=max(1, min(max_attempts, limit)),
                 max_connected_seconds=MAX_SECONDS,
                 budget_net_minor=budget_net_minor, created_by=user_id)
    db.add(c)
    db.flush()
    return c


def get_campaign(db: OrmSession, campaign_id: uuid.UUID) -> Campaign:
    c = db.get(Campaign, campaign_id)
    if c is None or c.kind != "internal_sales":
        raise NotFound("Kampagnen findes ikke")
    return c


def approved_script(db: OrmSession, company_id: uuid.UUID) -> SalesScript | None:
    return db.scalar(select(SalesScript).where(SalesScript.company_id == company_id, SalesScript.status == "approved")
                     .order_by(SalesScript.version.desc()).limit(1))


def add_members(db: OrmSession, c: Campaign, contact_ids: list[uuid.UUID]) -> dict:
    """Add sales contacts with a phone number. The policy runs at plan stage; nothing is dialled here."""
    if c.status not in ("draft", "paused"):
        raise Conflict("Kontakter kan kun tilføjes, før kampagnen startes, eller mens den er sat på pause",
                       code="campaign_not_editable")
    added, skipped = [], []
    for cid in contact_ids:
        contact = db.get(SalesContact, cid)
        if contact is None or not contact.phone_e164:
            skipped.append({"contact_id": str(cid), "reason": "no_phone"})
            continue
        if db.scalar(select(CampaignContact.id).where(CampaignContact.campaign_id == c.id,
                                                      CampaignContact.phone == contact.phone_e164)):
            skipped.append({"contact_id": str(cid), "reason": "already_member"})
            continue
        company = db.get(SalesCompany, contact.company_id)
        script = approved_script(db, company.id)
        basis = policy.valid_basis(db, contact)
        d = policy.evaluate(db, contact=contact, campaign=c, stage="plan", script=script)
        cc = CampaignContact(campaign_id=c.id, workspace_id=c.workspace_id, name=contact.name or contact.role or "",
                             company=company.display_name[:200], phone=contact.phone_e164, email=contact.email,
                             kind="business", consent_source=(basis.text[:300] if basis else ""), status="pending",
                             sales_contact_id=contact.id, sales_script_id=script.id if script else None,
                             sales_contact_basis_id=basis.id if basis else None, policy_decision_id=d.id)
        db.add(cc)
        added.append({"contact_id": str(cid), "decision": d.result})
    db.flush()
    return {"added": added, "skipped": skipped}


def preview(db: OrmSession, c: Campaign) -> dict:
    """Re-evaluate every pending member now: counts per result with reasons, and the cost ceiling."""
    from app.modules.campaigns.service import max_cost_net_minor, started_minutes

    out = {"ALLOW": 0, "BLOCK": 0, "NEEDS_REVIEW": 0}
    reasons: dict[str, int] = {}
    members = []
    for cc in db.scalars(select(CampaignContact).where(CampaignContact.campaign_id == c.id)
                         .order_by(CampaignContact.created_at)):
        contact = db.get(SalesContact, cc.sales_contact_id) if cc.sales_contact_id else None
        if contact is None:
            continue
        if cc.status == "pending":
            script = db.get(SalesScript, cc.sales_script_id) if cc.sales_script_id else approved_script(db, contact.company_id)
            if script is not None and script.status != "approved":
                script = approved_script(db, contact.company_id) or script
            cc.sales_script_id = script.id if script else None
            d = policy.evaluate(db, contact=contact, campaign=c, stage="plan", script=script)
            cc.policy_decision_id = d.id
            out[d.result] += 1
            for r in d.reasons:
                reasons[r] = reasons.get(r, 0) + 1
            decision = d.out()
        else:
            decision = policy.decision_out(policy.latest(db, contact.id))
        members.append({"campaign_contact_id": str(cc.id), "contact_id": str(contact.id), "company": cc.company,
                        "phone": cc.phone, "status": cc.status, "attempts": cc.attempts, "outcome": cc.outcome,
                        "error": cc.error, "decision": decision})
    per_attempt = c.call_net_minor + started_minutes(c.max_connected_seconds) * c.minute_net_minor
    return {"counts": out, "reasons": {k: {"count": v, "text": policy.TEXT.get(k, k)} for k, v in reasons.items()},
            "members": members, "max_cost_net_minor": max_cost_net_minor(db, c), "per_attempt_max_net_minor": per_attempt,
            "spent_net_minor": policy.spent_net_minor(db, c), "budget_net_minor": c.budget_net_minor,
            "mode": get_settings().sales_outbound_mode, "checked_at": _now().isoformat()}


def start(db: OrmSession, c: Campaign, *, user_id: uuid.UUID, accepted_max_net_minor: int) -> dict:
    from app.modules.campaigns.service import outbound_problem

    if c.status not in ("draft", "paused"):
        raise Conflict(f"Kampagnen er {c.status}", code="campaign_not_startable")
    if get_settings().sales_outbound_mode not in ("test", "live"):
        raise Conflict("Opkald kræver SALES_OUTBOUND_MODE=test eller live.", code="sales_mode_not_allowed")
    if (why := outbound_problem(db, c)) is not None:
        raise Conflict(why, code="outbound_not_ready")
    p = preview(db, c)
    if p["counts"]["ALLOW"] == 0:
        raise Conflict("Ingen kontakter må ringes op (se forhåndsvisningen).", code="nothing_allowed")
    if accepted_max_net_minor < p["max_cost_net_minor"]:
        raise Conflict("Godkend omkostningsloftet fra forhåndsvisningen.", code="preview_not_accepted",
                       extra={"max_cost_net_minor": p["max_cost_net_minor"]})
    c.status, c.started_at = "running", c.started_at or _now()
    c.legal_confirmation = {"by": str(user_id), "at": _now().isoformat(), "preview": p["counts"],
                            "accepted_max_net_minor": accepted_max_net_minor, "text_version": "sales-campaign-start-v1",
                            "text": "Operatøren har set forhåndsvisningen; kun kontakter med ALLOW ringes op, og "
                                    "politikken tjekkes igen lige før hvert opkald."}
    return p


def pause(c: Campaign) -> None:
    if c.status != "running":
        raise Conflict("Kampagnen kører ikke", code="campaign_not_running")
    c.status = "paused"


def stop(db: OrmSession, c: Campaign) -> int:
    if c.status in ("stopped", "completed"):
        raise Conflict(f"Kampagnen er allerede {c.status}", code="campaign_finished")
    c.status, c.completed_at = "stopped", _now()
    n = 0
    for cc in db.scalars(select(CampaignContact).where(CampaignContact.campaign_id == c.id,
                                                       CampaignContact.status == "pending")):
        cc.status, cc.error = "skipped", "stopped"
        n += 1
    return n


def campaign_out(db: OrmSession, c: Campaign) -> dict:
    from app.modules.campaigns.service import counts

    return {"id": str(c.id), "name": c.name, "status": c.status, "is_test": c.is_test,
            "budget_net_minor": c.budget_net_minor, "spent_net_minor": policy.spent_net_minor(db, c),
            "call_days": c.call_days, "call_from": c.call_from, "call_to": c.call_to, "max_attempts": c.max_attempts,
            "counts": counts(db, c), "legal_confirmation": c.legal_confirmation,
            "created_at": c.created_at.isoformat() if c.created_at else None,
            "started_at": c.started_at.isoformat() if c.started_at else None}


# --------------------------------------------------------------------------- dialling (called from campaigns.dispatch)


def concurrency_full(db: OrmSession) -> bool:
    n = db.scalar(select(func.count()).select_from(CampaignContact).join(Campaign, Campaign.id == CampaignContact.campaign_id)
                  .where(Campaign.kind == "internal_sales", CampaignContact.status == "calling")) or 0
    return n >= get_settings().sales_max_concurrent_calls


def gate(db: OrmSession, c: Campaign, cc: CampaignContact, now: datetime) -> bool:
    """The dispatch-stage policy check. True = may dial now. Otherwise the contact is parked with the reason."""
    contact = db.get(SalesContact, cc.sales_contact_id) if cc.sales_contact_id else None
    if contact is None:
        cc.status, cc.error = "skipped", "Ingen salgskontakt"
        return False
    script = db.get(SalesScript, cc.sales_script_id) if cc.sales_script_id else None
    d = policy.evaluate(db, contact=contact, campaign=c, stage="dispatch", script=script, now=now)
    cc.policy_decision_id = d.id
    if d.result == "ALLOW":
        basis = policy.valid_basis(db, contact, now=now)
        cc.sales_contact_basis_id = basis.id if basis else None
        return True
    text = ", ".join(policy.TEXT.get(r, r) for r in d.reasons)[:300]
    if d.temporary:
        cc.error = text  # stays pending: tried again in the window
    else:
        cc.status, cc.error = "skipped", text
    return False


def assistant_for(db: OrmSession, c: Campaign, cc: CampaignContact) -> dict:
    from app.modules.ai.service import CHANNEL_INSTRUCTIONS, build_system_prompt
    from app.modules.sales import service
    from app.modules.telephony import vapi
    from app.modules.voices import standard

    ws = db.get(Workspace, c.workspace_id)
    script = db.get(SalesScript, cc.sales_script_id)
    base, _rev = build_system_prompt(db, ws, ("public", "customer_docs"))
    who = (script.body.get("opening") or {}).get("who") or "den ansvarlige for telefonen"
    system = f"{base}\n\n{CHANNEL_INSTRUCTIONS['phone'][1]}\n\n{script.rendered_prompt}\n\n{NO_TOOLS_RULES}"
    out: dict = {
        "firstMessage": f"Hej, det er Peter, AI-assistent hos Dialogbot. Taler jeg med {who}?",
        "model": {"provider": get_settings().vapi_model_provider, "model": vapi.phone_model(get_settings()),
                  "messages": [{"role": "system", "content": system}]},
        "transcriber": vapi.transcriber_for(db, ws),
        "maxDurationSeconds": MAX_SECONDS,
        "voicemailDetection": {"provider": "vapi"},  # voicemail: hang up, no message is left
        "endCallPhrases": ["Tak for din tid", "hav en god dag"],
        "analysisPlan": vapi.ANALYSIS_PLAN,
        "stopSpeakingPlan": vapi.STOP_SPEAKING_PLAN, "startSpeakingPlan": vapi.START_SPEAKING_PLAN,
        "metadata": {"workspace_id": str(ws.id), "campaign_id": str(c.id), "campaign_contact_id": str(cc.id),
                     "sales_campaign_contact_id": str(cc.id), "script_id": str(script.id)},
    }
    if (server := vapi.server_block()) is not None:
        out["server"] = server
    out["voice"] = service.agent_voice()
    out["voice"].setdefault("chunkPlan", standard.danish_chunk_plan(db, ws.id, sales_pronunciations()))
    return out


def snapshot(db: OrmSession, cc: CampaignContact, assistant: dict) -> None:
    prompt = assistant["model"]["messages"][0]["content"]
    db.add(SalesCallEvent(campaign_contact_id=cc.id, event_type="assistant_snapshot",
                          payload={"script_id": str(cc.sales_script_id), "dispatch_key": cc.dispatch_key,
                                   "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
                                   "first_message": assistant["firstMessage"],
                                   "rendered_prompt": db.get(SalesScript, cc.sales_script_id).rendered_prompt}))


def dial(db: OrmSession, c: Campaign, cc: CampaignContact, now: datetime) -> None:
    """Dial one internal sales contact. The dispatch key and `calling` are committed BEFORE the provider is called;
    the answer is stored afterwards. A failure without an answer from the provider leaves the attempt `unknown`."""
    from app.models import CampaignCall, PhoneNumber
    from app.modules.campaigns import service as campaigns

    number = db.get(PhoneNumber, c.phone_number_id)
    assistant = assistant_for(db, c, cc)
    cc.dispatch_key = f"{cc.id}:{cc.attempts + 1}"
    cc.status, cc.last_attempt_at, cc.error = "calling", now, None
    snapshot(db, cc, assistant)
    db.commit()
    payload = {"phoneNumberId": number.provider_number_id,
               "customer": {"number": cc.phone, **({"name": cc.name[:40]} if cc.name else {})},
               "assistant": assistant,
               "metadata": {"campaign_contact_id": str(cc.id), "sales_campaign_contact_id": str(cc.id),
                            "dispatch_key": cc.dispatch_key}}
    try:
        out = campaigns.create_call(payload)
    except ApiError as e:
        cc = db.get(CampaignContact, cc.id)
        if (e.extra or {}).get("no_response"):  # no answer at all: the call may exist at Vapi
            cc.status, cc.error = "unknown", "Uvist om opkaldet blev oprettet hos Vapi – ringes ikke op igen automatisk"
        elif (e.extra or {}).get("permanent"):
            cc.status, cc.error = "failed", e.message[:300]
        else:
            cc.status, cc.error, cc.next_attempt_at = "pending", e.message[:300], now + timedelta(minutes=30)
        cc.dispatch_key = None if cc.status == "pending" else cc.dispatch_key
        db.commit()
        return
    cc = db.get(CampaignContact, cc.id)
    cc.attempts += 1
    cc.provider_call_id = str(out.get("id") or "")[:100] or None
    db.add(CampaignCall(workspace_id=c.workspace_id, campaign_id=c.id, contact_id=cc.id,
                        provider_call_id=cc.provider_call_id, dialled_at=now, net_minor=c.call_net_minor))
    db.add(SalesCallEvent(campaign_contact_id=cc.id, provider_call_id=cc.provider_call_id, event_type="created",
                          payload={"dispatch_key": cc.dispatch_key}))
    db.commit()


# --------------------------------------------------------------------------- test calls


def test_call(db: OrmSession, *, company: SalesCompany, script: SalesScript, phone: str, user_id: uuid.UUID) -> dict:
    """An internal test call to one of SALES_TEST_NUMBERS: a one-contact test campaign, dialled now if the policy
    allows. The operator's confirmation becomes a `test` basis on that number."""
    from app.modules.campaigns.service import normalize_phone, outbound_problem

    s = get_settings()
    if s.sales_outbound_mode not in ("test", "live"):
        raise Conflict("Testopkald kræver SALES_OUTBOUND_MODE=test eller live.", code="sales_mode_not_allowed")
    e164 = normalize_phone(phone)
    if not e164 or e164 not in policy.test_numbers():
        raise ValidationFailed("Nummeret står ikke i SALES_TEST_NUMBERS", field_errors=[{"field": "phone"}])
    if script.company_id != company.id or script.status != "approved":
        raise ValidationFailed("Vælg et godkendt manuskript for virksomheden", field_errors=[{"field": "script_id"}])
    contact = db.scalar(select(SalesContact).where(SalesContact.company_id == company.id,
                                                   SalesContact.phone_e164 == e164, SalesContact.role == "Testnummer"))
    if contact is None:
        contact = add_contact(db, company, name=None, role="Testnummer", phone=e164, email=None)
    if policy.valid_basis(db, contact) is None:
        record_basis(db, contact, channel="ai_call", purpose="Intern test af Dialogbots salgsopkald", kind="consent",
                     source="test", text=TEST_BASIS_TEXT, text_version=TEST_BASIS_VERSION,
                     evidence_ref=f"operator:{user_id}", valid_until=_now() + timedelta(days=30), user_id=user_id)
    c = create_campaign(db, name=f"Test: {company.display_name}"[:160], budget_net_minor=None,
                        call_days=["mon", "tue", "wed", "thu", "fri", "sat", "sun"], call_from="00:00",
                        call_to="23:59", max_attempts=1, user_id=user_id, is_test=True)
    if (why := outbound_problem(db, c)) is not None:
        raise Conflict(why, code="outbound_not_ready")
    add_members(db, c, [contact.id])
    cc = db.scalar(select(CampaignContact).where(CampaignContact.campaign_id == c.id))
    cc.sales_script_id = script.id
    c.status, c.started_at = "running", _now()
    c.legal_confirmation = {"by": str(user_id), "at": _now().isoformat(), "text_version": TEST_BASIS_VERSION,
                            "text": TEST_BASIS_TEXT}
    db.flush()
    now = _now()
    if gate(db, c, cc, now):
        dial(db, c, cc, now)
    else:
        db.commit()
    cc = db.get(CampaignContact, cc.id)
    return {"campaign_id": str(c.id), "campaign_contact_id": str(cc.id), "status": cc.status, "error": cc.error,
            "provider_call_id": cc.provider_call_id,
            "decision": policy.decision_out(policy.latest(db, contact.id))}


# --------------------------------------------------------------------------- webhooks


def on_status_update(db: OrmSession, message: dict) -> bool:
    call_id = str((message.get("call") or {}).get("id") or "")
    if not call_id:
        return False
    cc = db.scalar(select(CampaignContact).join(Campaign, Campaign.id == CampaignContact.campaign_id)
                   .where(Campaign.kind == "internal_sales", CampaignContact.provider_call_id == call_id))
    if cc is None:
        return False
    db.add(SalesCallEvent(campaign_contact_id=cc.id, provider_call_id=call_id, event_type="status-update",
                          payload={"status": str(message.get("status") or "")[:40],
                                   "ended_reason": str(message.get("endedReason") or "")[:100] or None}))
    return True


ACCEPTS_PROMPT_VERSION = "sales-accepts-v1"


def on_report(db: OrmSession, message: dict, *, call_id: str, conv: Conversation, transcript: str) -> bool:
    """After campaigns.on_report: the sales-specific part for internal campaigns. False when not ours."""
    from app.modules.ai.provider import get_provider
    from app.modules.sales import simulate

    cc = db.scalar(select(CampaignContact).where(CampaignContact.provider_call_id == call_id))
    if cc is None:
        return False
    c = db.get(Campaign, cc.campaign_id)
    if c.kind != "internal_sales":
        return False
    call = db.scalar(select(Call).where(Call.provider_call_id == call_id))
    if call is not None:
        call.direction, call.campaign_contact_id, call.script_id = "outbound", cc.id, cc.sales_script_id
        call.outcome = cc.outcome or ("no_answer" if cc.status in ("pending", "no_answer") else None)
        call.transcript_status = "AVAILABLE" if conv.visitor_message_count else "NOT_RECORDED"
    db.add(SalesCallEvent(campaign_contact_id=cc.id, provider_call_id=call_id, event_type="end-of-call-report",
                          payload={"ended_reason": str(message.get("endedReason") or "")[:100] or None,
                                   "outcome": cc.outcome}))
    if cc.outcome == "opt_out":
        block(db, kind="phone", value=cc.phone, reason=f"Frabad sig opkald i \"{c.name}\"", source="call", user_id=None)
    if call is not None and conv.visitor_message_count and cc.outcome not in (None, "no_answer"):
        msgs = db.scalars(select(ConversationMessage).where(ConversationMessage.conversation_id == conv.id)
                          .order_by(ConversationMessage.created_at)).all()
        lines = [{"speaker": "customer" if m.role == "visitor" else "peter", "text": m.text} for m in msgs]
        ws = db.get(Workspace, c.workspace_id)
        try:
            accepts, _outcome = simulate.classify_accepts(db, ws, get_provider(), lines, ws.knowledge_revision, None)
        except ApiError as e:
            log.info("sales.outbound.accepts_failed", code=e.code)
            accepts = []
        for a in accepts:
            db.add(SalesQualification(call_id=call.id, accept_no=a["no"], result=a["result"], quote=a["quote"],
                                      message_index=a["message_index"]))
    return True


# --------------------------------------------------------------------------- calls view


def calls(db: OrmSession, *, campaign_id: uuid.UUID | None = None, outcome: str | None = None, test: bool | None = None,
          q: str | None = None, limit: int = 100) -> list[dict]:
    query = (select(CampaignContact, Campaign).join(Campaign, Campaign.id == CampaignContact.campaign_id)
             .where(Campaign.kind == "internal_sales",
                    or_(CampaignContact.attempts > 0, CampaignContact.status.in_(("calling", "unknown", "failed")))))
    if campaign_id:
        query = query.where(Campaign.id == campaign_id)
    if outcome:
        query = query.where(CampaignContact.outcome == outcome)
    if test is not None:
        query = query.where(Campaign.is_test.is_(test))
    if q:
        conv_ids = select(ConversationMessage.conversation_id).where(ConversationMessage.text.ilike(f"%{q.strip()}%"))
        query = query.where(CampaignContact.conversation_id.in_(conv_ids))
    out = []
    for cc, c in db.execute(query.order_by(CampaignContact.last_attempt_at.desc().nulls_last()).limit(limit)).all():
        call = db.scalar(select(Call).where(Call.provider_call_id == cc.provider_call_id)) if cc.provider_call_id else None
        out.append({"campaign_contact_id": str(cc.id), "campaign": {"id": str(c.id), "name": c.name, "test": c.is_test},
                    "company": cc.company, "phone": cc.phone, "status": cc.status, "attempts": cc.attempts,
                    "outcome": cc.outcome, "summary": cc.summary, "error": cc.error,
                    "last_attempt_at": cc.last_attempt_at.isoformat() if cc.last_attempt_at else None,
                    "call_id": str(call.id) if call else None,
                    "duration_seconds": call.duration_seconds if call else None,
                    "ended_reason": call.ended_reason if call else None,
                    "transcript_status": call.transcript_status if call else ("PENDING" if cc.status == "calling" else None),
                    "recording_status": call.recording_status if call else "NOT_RECORDED"})
    return out


def call_detail(db: OrmSession, cc_id: uuid.UUID) -> dict:
    cc = db.get(CampaignContact, cc_id)
    c = db.get(Campaign, cc.campaign_id) if cc else None
    if cc is None or c.kind != "internal_sales":
        raise NotFound("Opkaldet findes ikke")
    call = db.scalar(select(Call).where(Call.provider_call_id == cc.provider_call_id)) if cc.provider_call_id else None
    messages = []
    if cc.conversation_id:
        msgs = db.scalars(select(ConversationMessage).where(ConversationMessage.conversation_id == cc.conversation_id)
                          .order_by(ConversationMessage.created_at)).all()
        messages = [{"index": i, "speaker": "kunde" if m.role == "visitor" else "peter", "text": m.text,
                     "time": None, "time_note": "rækkefølge – Vapi-tidsstempler gemmes ikke endnu"}
                    for i, m in enumerate(msgs)]
    events = db.scalars(select(SalesCallEvent).where(SalesCallEvent.campaign_contact_id == cc.id)
                        .order_by(SalesCallEvent.received_at)).all()
    quals = db.scalars(select(SalesQualification).where(SalesQualification.call_id == call.id)
                       .order_by(SalesQualification.accept_no)).all() if call else []
    contact = db.get(SalesContact, cc.sales_contact_id) if cc.sales_contact_id else None
    return {"campaign_contact_id": str(cc.id), "campaign": {"id": str(c.id), "name": c.name, "test": c.is_test},
            "company": cc.company, "company_id": str(contact.company_id) if contact else None, "phone": cc.phone,
            "status": cc.status, "attempts": cc.attempts, "outcome": cc.outcome, "summary": cc.summary, "error": cc.error,
            "dispatch_key": cc.dispatch_key, "provider_call_id": cc.provider_call_id,
            "call": None if call is None else {
                "id": str(call.id), "started_at": call.started_at.isoformat() if call.started_at else None,
                "ended_at": call.ended_at.isoformat() if call.ended_at else None,
                "duration_seconds": call.duration_seconds, "ended_reason": call.ended_reason, "summary": call.summary,
                "transcript_status": call.transcript_status, "recording_status": call.recording_status,
                "outcome": call.outcome},
            "messages": messages,
            "events": [{"type": e.event_type, "at": e.received_at.isoformat(),
                        "payload": {k: v for k, v in e.payload.items() if k != "rendered_prompt"}} for e in events],
            "qualifications": [{"no": q.accept_no, "result": q.result, "quote": q.quote, "message_index": q.message_index}
                               for q in quals],
            "decision": policy.decision_out(policy.latest(db, contact.id)) if contact else None}

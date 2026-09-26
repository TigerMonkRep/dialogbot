"""Outbound calling campaigns.

Rules (product and Danish law, markedsføringsloven § 10):
- A contact is either a business number (B2B calls are allowed unless the business has said no) or a
  consumer who has given prior consent – the consent source is required and stored per contact.
  We cannot check the CPR Robinson list, so consumers without documented consent are refused.
- Numbers on the workspace's do-not-call list are never called; "ring ikke igen" in a call adds the
  number to it.
- One package per contact: fixed price, at most `max_attempts` dial attempts and `max_connected_seconds`
  of connected AI time in total. The package is used (billable) when the first attempt is dialled.
- Payment never starts calls. Only an admin's explicit start command sets a campaign running, and
  the worker only dials inside the campaign's calling window in the workspace's time zone.
- The assistant always says it is a digital assistent, who it calls from, and why.
"""
from __future__ import annotations

import csv
import io
import json
import re
import uuid
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session as OrmSession

from app.config import get_settings
from app.core.errors import ApiError, NotImplementedYet, ValidationFailed
from app.models import Campaign, CampaignContact, DoNotCall, PhoneNumber, Workspace

PACKAGE_NET_MINOR = 900      # 9,00 kr. excl. VAT per contact
MAX_ATTEMPTS = 2
MAX_CONNECTED_SECONDS = 180
RETRY_AFTER = timedelta(hours=3)
STALE_CALL = timedelta(minutes=15)   # no report after this long: count the attempt as failed
MAX_IMPORT_ROWS = 5000
DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
E164 = re.compile(r"^\+[1-9]\d{7,14}$")
AI_DISCLOSURE = re.compile(r"digital assistent|ai-assistent|kunstig intelligens|\bAI\b", re.I)
NO_ANSWER_REASONS = ("customer-did-not-answer", "customer-busy", "voicemail", "twilio-failed-to-connect-call",
                     "vonage-failed-to-connect-call", "customer-did-not-give-microphone-permission")
LEGAL_TEXT_VERSION = "campaign-legal-v1"
LEGAL_CHECKLIST = (
    "Erhvervsnumre: Kontakterne er virksomheder, der ikke har frabedt sig opkald.",
    "Privatpersoner: Hver privatperson har på forhånd givet samtykke til at blive ringet op af os, og vi kan dokumentere det.",
    "Vi ringer ikke til numre på vores spærreliste, og vi respekterer et nej med det samme.",
    "Assistenten siger, at den er en digital assistent, hvem den ringer fra, og hvorfor.",
)


def _now() -> datetime:
    return datetime.now(UTC)


# --------------------------------------------------------------------------- numbers and CSV

def normalize_phone(raw: str) -> str | None:
    n = re.sub(r"[\s().\-/]", "", raw or "")
    if n.startswith("00"):
        n = "+" + n[2:]
    if re.fullmatch(r"\d{8}", n):  # Danish national number
        n = "+45" + n
    elif re.fullmatch(r"45\d{8}", n):
        n = "+" + n
    return n if E164.match(n) else None


HEADERS = {
    "name": ("navn", "name", "kontakt", "kontaktperson", "fulde navn", "fornavn"),
    "phone": ("telefon", "telefonnummer", "tlf", "tlf.", "phone", "mobil", "mobilnummer", "nummer", "number"),
    "company": ("firma", "virksomhed", "company", "firmanavn", "organisation"),
    "email": ("email", "e-mail", "mail"),
}


def parse_csv(text: str) -> list[dict]:
    """Rows as dicts with name/phone/company/email. Delimiter ; , or tab; header row optional."""
    text = (text or "").lstrip("﻿").strip()
    if not text:
        return []
    first = text.split("\n", 1)[0]
    delim = max((";", ",", "\t"), key=first.count)
    rows = [r for r in csv.reader(io.StringIO(text), delimiter=delim) if any(c.strip() for c in r)]
    if not rows:
        return []
    head = [c.strip().lower() for c in rows[0]]
    cols = {k: next((i for i, h in enumerate(head) if h in names), None) for k, names in HEADERS.items()}
    if cols["phone"] is not None:
        body = rows[1:]
    else:  # no header: the phone column is the one whose cells look like numbers
        body = rows
        width = max(len(r) for r in rows)
        scores = [sum(1 for r in rows if i < len(r) and normalize_phone(r[i])) for i in range(width)]
        cols = {"phone": max(range(width), key=scores.__getitem__) if any(scores) else None, "name": None,
                "company": None, "email": None}
        others = [i for i in range(width) if i != cols["phone"]]
        for i in others:
            if any("@" in r[i] for r in rows if i < len(r)):
                cols["email"] = i
        texts = [i for i in others if i != cols["email"]]
        cols["name"] = texts[0] if texts else None
        cols["company"] = texts[1] if len(texts) > 1 else None

    def cell(r: list[str], k: str) -> str:
        i = cols.get(k)
        return r[i].strip() if i is not None and i < len(r) else ""

    return [{k: cell(r, k) for k in ("name", "phone", "company", "email")} for r in body[:MAX_IMPORT_ROWS + 1]]


def blocked_numbers(db: OrmSession, ws_id: uuid.UUID) -> set[str]:
    return set(db.scalars(select(DoNotCall.phone).where(DoNotCall.workspace_id == ws_id)))


def import_contacts(db: OrmSession, c: Campaign, text: str, *, kind: str, consent_source: str) -> dict:
    if kind not in ("business", "consumer"):
        raise ValidationFailed("Vælg erhverv eller privat", field_errors=[{"field": "kind"}])
    consent_source = consent_source.strip()
    if kind == "consumer" and len(consent_source) < 5:
        raise ValidationFailed("Privatpersoner må kun ringes op med forudgående samtykke. Skriv hvor samtykket er givet "
                               "(fx \"tilmelding på hjemmesiden, marts 2026\").", field_errors=[{"field": "consent_source"}])
    rows = parse_csv(text)
    if not rows:
        raise ValidationFailed("Filen indeholder ingen rækker", field_errors=[{"field": "csv"}])
    if len(rows) > MAX_IMPORT_ROWS:
        raise ValidationFailed(f"Højst {MAX_IMPORT_ROWS} kontakter ad gangen", field_errors=[{"field": "csv"}])
    existing = set(db.scalars(select(CampaignContact.phone).where(CampaignContact.campaign_id == c.id)))
    blocked = blocked_numbers(db, c.workspace_id)
    added, duplicates, on_block_list, invalid = 0, 0, 0, []
    for i, r in enumerate(rows, start=1):
        phone = normalize_phone(r["phone"])
        if phone is None:
            invalid.append({"row": i, "value": r["phone"][:40], "reason": "Ugyldigt telefonnummer"})
            continue
        if phone in existing:
            duplicates += 1
            continue
        if phone in blocked:
            on_block_list += 1
            continue
        existing.add(phone)
        email = r["email"].lower() if "@" in r["email"] else None
        db.add(CampaignContact(campaign_id=c.id, workspace_id=c.workspace_id, name=r["name"][:200],
                               company=r["company"][:200], phone=phone, email=email, kind=kind,
                               consent_source=consent_source[:500] if kind == "consumer" else ""))
        added += 1
    db.flush()
    return {"added": added, "duplicates": duplicates, "blocked": on_block_list, "invalid": invalid[:50],
            "invalid_count": len(invalid)}


# --------------------------------------------------------------------------- state

def counts(db: OrmSession, c: Campaign) -> dict:
    rows = dict(db.execute(select(CampaignContact.status, func.count()).where(CampaignContact.campaign_id == c.id)
                           .group_by(CampaignContact.status)).all())
    outcomes = dict(db.execute(select(CampaignContact.outcome, func.count()).where(
        CampaignContact.campaign_id == c.id, CampaignContact.outcome.is_not(None)).group_by(CampaignContact.outcome)).all())
    used = db.scalar(select(func.count()).where(CampaignContact.campaign_id == c.id,
                                                CampaignContact.charged_at.is_not(None))) or 0
    total = sum(rows.values())
    return {"total": total, "by_status": rows, "by_outcome": outcomes, "packages_used": used,
            "open": rows.get("pending", 0) + rows.get("calling", 0)}


def max_cost_net_minor(db: OrmSession, c: Campaign) -> int:
    """The most the campaign can cost from now: one package per contact not yet charged and still callable."""
    n = db.scalar(select(func.count()).where(CampaignContact.campaign_id == c.id, CampaignContact.charged_at.is_(None),
                                             CampaignContact.status == "pending")) or 0
    return n * c.package_net_minor


def outbound_problem(db: OrmSession, c: Campaign) -> str | None:
    """Why the campaign cannot call now (None = ready). Honest about missing configuration."""
    s = get_settings()
    if not s.vapi_api_key or not s.vapi_server_secret:
        return "Udgående opkald kræver en Vapi-konto på serveren (VAPI_API_KEY og VAPI_SERVER_SECRET)."
    n = db.get(PhoneNumber, c.phone_number_id) if c.phone_number_id else None
    if n is None or n.workspace_id != c.workspace_id or not n.active:
        return "Vælg hvilket af jeres telefonnumre, der skal ringe ud."
    if not n.provider_number_id:
        return "Nummeret mangler Vapis nummer-id (Indstillinger → Telefoni)."
    return None


def in_window(c: Campaign, tz: str, now: datetime | None = None) -> bool:
    local = (now or _now()).astimezone(ZoneInfo(tz))
    if DAYS[local.weekday()] not in (c.call_days or []):
        return False
    return time.fromisoformat(c.call_from) <= local.time() < time.fromisoformat(c.call_to)


# --------------------------------------------------------------------------- the call

def opening_line(c: Campaign, ws: Workspace, contact: CampaignContact) -> str:
    who = contact.name.split(" ")[0] if contact.name else ""
    g = (c.opening.strip() or "Hej{komma}{navn}, det er den digitale assistent fra {virksomhed}. Har du et øjeblik?")
    g = g.replace("{komma}", " " if who else "").replace("{navn}", who).replace("{virksomhed}", ws.name)
    g = re.sub(r"\s+,", ",", re.sub(r"\s{2,}", " ", g)).replace("Hej ,", "Hej,").strip()
    if not AI_DISCLOSURE.search(g):
        g = f"{g} Du taler med en digital assistent fra {ws.name}."
    return g


def system_prompt(db: OrmSession, c: Campaign, ws: Workspace, contact: CampaignContact) -> str:
    from app.modules.ai.service import build_system_prompt

    base, _rev = build_system_prompt(db, ws)  # approved knowledge only; 409 without it
    qs = "\n".join(f"- {q}" for q in c.questions or [])
    who = ", ".join(x for x in (contact.name, contact.company) if x) or "kontakten"
    return f"""{base}

Du ringer UD på vegne af {ws.name} til {who}. Det er et kort opkald på højst {c.max_connected_seconds} sekunder.
Formål med opkaldet: {c.purpose or "(ikke angivet)"}
Spørg om (et spørgsmål ad gangen, spring over hvis kunden allerede har svaret):
{qs or "- Om de er interesseret"}
En interesseret kontakt er: {c.success or "en der gerne vil kontaktes af en medarbejder"}

Regler for udgående opkald:
- Du har allerede sagt, at du er en digital assistent. Lyv aldrig om at være et menneske.
- Hvis personen ikke har tid, så spørg kort, hvornår det passer bedre, og afslut.
- Hvis personen siger nej eller ikke vil ringes op igen, så undskyld forstyrrelsen, bekræft at de ikke bliver ringet op igen, og afslut straks. Pres aldrig.
- Lov aldrig priser, rabatter eller aftaler, der ikke står i den godkendte viden. En medarbejder følger op.
- Hvis det ikke er den rette person eller et forkert nummer, så undskyld og afslut.
- Tal naturligt dansk, kort og venligt. Afslut med at takke for snakken."""


def assistant_for(db: OrmSession, c: Campaign, contact: CampaignContact) -> dict:
    from app.modules.telephony import vapi

    ws = db.get(Workspace, c.workspace_id)
    number = db.get(PhoneNumber, c.phone_number_id)
    s = get_settings()
    remaining = max(30, c.max_connected_seconds - contact.connected_seconds)
    assistant: dict = {
        "firstMessage": opening_line(c, ws, contact),
        "model": {"provider": s.vapi_model_provider, "model": s.vapi_model or s.ai_model_id,
                  "messages": [{"role": "system", "content": system_prompt(db, c, ws, contact)}]},
        "transcriber": vapi._json_setting(s.vapi_transcriber_json) or dict(vapi.DEFAULT_TRANSCRIBER),
        "maxDurationSeconds": remaining,
        "voicemailDetection": {"provider": "vapi"},
        "endCallPhrases": ["Tak for snakken, hav en god dag", "Undskyld forstyrrelsen, hav en god dag"],
        "metadata": {"workspace_id": str(ws.id), "campaign_id": str(c.id), "campaign_contact_id": str(contact.id)},
    }
    if voice := vapi.voice_config(number):
        assistant["voice"] = voice
    elif (voice := vapi._json_setting(s.vapi_voice_json)) is not None:
        assistant["voice"] = voice
    return assistant


class OutboundFailed(ApiError):
    status_code = 502
    code = "outbound_failed"


def create_call(payload: dict) -> dict:
    """POST /call at Vapi. Separate function so tests can replace it."""
    import httpx

    s = get_settings()
    if not s.vapi_api_key:
        raise NotImplementedYet("VAPI_API_KEY mangler", code="outbound_not_configured")
    try:
        r = httpx.post(f"{s.vapi_api_url.rstrip('/')}/call", json=payload, timeout=20.0,
                       headers={"authorization": f"Bearer {s.vapi_api_key}"})
    except httpx.HTTPError as e:
        raise OutboundFailed("Vapi svarede ikke") from e
    if r.status_code >= 400:
        raise OutboundFailed(f"Vapi afviste opkaldet ({r.status_code}): {r.text[:200]}",
                             extra={"permanent": 400 <= r.status_code < 500 and r.status_code not in (408, 429)})
    return r.json()


def dial(db: OrmSession, c: Campaign, contact: CampaignContact, now: datetime) -> None:
    number = db.get(PhoneNumber, c.phone_number_id)
    payload = {"phoneNumberId": number.provider_number_id,
               "customer": {"number": contact.phone, **({"name": contact.name[:40]} if contact.name else {})},
               "assistant": assistant_for(db, c, contact),
               "metadata": {"campaign_contact_id": str(contact.id)}}
    contact.last_attempt_at = now
    try:
        out = create_call(payload)
    except ApiError as e:
        contact.error = e.message[:300]
        if (e.extra or {}).get("permanent"):
            contact.status, contact.outcome = "failed", None
        else:
            contact.status, contact.next_attempt_at = "pending", now + timedelta(minutes=30)
        return
    contact.attempts += 1
    contact.status, contact.error = "calling", None
    contact.provider_call_id = str(out.get("id") or "")[:100] or None
    if contact.charged_at is None:
        contact.charged_at, contact.charged_net_minor = now, c.package_net_minor


def dispatch(db: OrmSession, now: datetime | None = None, max_calls: int = 20) -> int:
    """One dialler pass: at most one call in flight per campaign, only inside the calling window."""
    from app.modules.reports.service import tz_of

    now = now or _now()
    dialled = 0
    for c in db.scalars(select(Campaign).where(Campaign.status == "running").with_for_update(skip_locked=True)).all():
        # attempts that never got a report count as failed attempts
        for st in db.scalars(select(CampaignContact).where(CampaignContact.campaign_id == c.id,
                                                           CampaignContact.status == "calling",
                                                           CampaignContact.last_attempt_at < now - STALE_CALL)):
            _after_attempt(c, st, now, answered=False)
            st.error = "Ingen opkaldsrapport fra Vapi"
        if db.scalar(select(func.count()).where(CampaignContact.campaign_id == c.id, CampaignContact.status == "calling")):
            continue
        blocked = blocked_numbers(db, c.workspace_id)
        callable_ = select(CampaignContact).where(
            CampaignContact.campaign_id == c.id, CampaignContact.status == "pending",
            (CampaignContact.next_attempt_at.is_(None)) | (CampaignContact.next_attempt_at <= now))
        if not db.scalar(select(func.count()).select_from(select(CampaignContact.id).where(
                CampaignContact.campaign_id == c.id, CampaignContact.status == "pending").subquery())):
            c.status, c.completed_at = "completed", now
            continue
        if dialled >= max_calls or outbound_problem(db, c) or not in_window(c, tz_of(db, c.workspace_id), now):
            continue
        for contact in db.scalars(callable_.order_by(CampaignContact.next_attempt_at.nulls_first(),
                                                     CampaignContact.created_at).limit(10)):
            if contact.phone in blocked:
                contact.status = "skipped"
                continue
            dial(db, c, contact, now)
            dialled += 1
            break
    db.commit()
    return dialled


def _after_attempt(c: Campaign, contact: CampaignContact, now: datetime, *, answered: bool) -> None:
    if answered:
        contact.status = "done"
        return
    if contact.attempts < c.max_attempts and contact.connected_seconds < c.max_connected_seconds:
        contact.status, contact.next_attempt_at = "pending", now + RETRY_AFTER
    else:
        contact.status, contact.outcome = "no_answer", "no_answer"


# --------------------------------------------------------------------------- report

OUTCOME_SYSTEM = """CAMPAIGN_OUTCOME
Du får udskriften af et udgående salgs-/opfølgningsopkald, som en digital assistent har foretaget for en dansk virksomhed. Vurder udfaldet:
- interested: kontakten vil gerne have et tilbud, en aftale eller at en medarbejder ringer
- callback: kontakten havde ikke tid eller bad om at blive ringet op senere, eller det er uklart
- not_interested: kontakten sagde nej tak
- opt_out: kontakten vil ikke ringes op igen / bad om at blive fjernet
Svar med ét JSON-objekt og intet andet: {"outcome": "...", "summary": "1-3 sætninger på dansk om hvad kontakten sagde og ønsker"}"""
OUTCOMES = ("interested", "callback", "not_interested", "opt_out")


def classify(db: OrmSession, ws: Workspace, transcript: str, fallback_summary: str) -> tuple[str, str]:
    from app.modules.ai.provider import get_provider
    from app.modules.ai.service import log_call

    try:
        provider = get_provider()
        comp, row = log_call(db, ws, provider, user_id=None, purpose="campaign_outcome", system=OUTCOME_SYSTEM,
                             messages=[{"role": "user", "content": transcript[:12000]}], prompt_version="campaign-outcome-v1",
                             revision=ws.knowledge_revision, max_tokens=400)
        text = comp.text
        data = json.loads(text[text.find("{"):text.rfind("}") + 1]) if "{" in text else {}
    except (ApiError, ValueError):
        data = {}
    outcome = data.get("outcome") if data.get("outcome") in OUTCOMES else "callback"
    summary = re.sub(r"\s+", " ", str(data.get("summary") or fallback_summary or "")).strip()[:1000]
    return outcome, summary


def on_report(db: OrmSession, message: dict, *, call_id: str, conv, duration: float | None, visitor_lines: int,
              transcript: str, summary: str) -> bool:
    """Apply an end-of-call report to the campaign contact it belongs to. False when it is not a campaign call."""
    from app.modules.leads import service as leads

    contact = db.scalar(select(CampaignContact).where(CampaignContact.provider_call_id == call_id).with_for_update())
    if contact is None:
        return False
    c = db.get(Campaign, contact.campaign_id)
    ws = db.get(Workspace, c.workspace_id)
    now = _now()
    reason = str(message.get("endedReason") or "")
    answered = visitor_lines > 0 and not any(reason.startswith(r) for r in NO_ANSWER_REASONS)
    contact.conversation_id = conv.id
    if answered and duration:
        contact.connected_seconds += int(duration)
    if not answered:
        _after_attempt(c, contact, now, answered=False)
        return True
    outcome, text = classify(db, ws, transcript, summary)
    contact.outcome, contact.summary = outcome, text
    _after_attempt(c, contact, now, answered=True)
    if outcome == "opt_out":
        contact.status = "opted_out"
        if not db.scalar(select(DoNotCall.id).where(DoNotCall.workspace_id == ws.id, DoNotCall.phone == contact.phone)):
            db.add(DoNotCall(workspace_id=ws.id, phone=contact.phone, source="call",
                             reason=f"Frabad sig opkald i kampagnen \"{c.name}\""[:300]))
    elif outcome in ("interested", "callback"):
        who = contact.name or contact.company or contact.phone
        lead = leads.create_lead(db, ws.id, source="campaign", created_by=None, conversation=conv, contact_name=contact.name,
                                 contact_email=contact.email, contact_phone=contact.phone,
                                 need_summary=f"Kampagne \"{c.name}\": {text}" if text else f"Kampagne \"{c.name}\"")
        leads._notify_new_lead(db, lead)
        contact.lead_id = lead.id
        leads.create_task(db, ws.id, title=(f"Følg op på {who} (interesseret)" if outcome == "interested"
                                            else f"Ring tilbage til {who}"),
                          created_by=None, lead=lead, due_at=now + timedelta(hours=4))
    return True


def contact_out(x: CampaignContact) -> dict:
    return {"id": str(x.id), "name": x.name, "company": x.company, "phone": x.phone, "email": x.email, "kind": x.kind,
            "consent_source": x.consent_source, "status": x.status, "attempts": x.attempts,
            "connected_seconds": x.connected_seconds, "outcome": x.outcome, "summary": x.summary, "error": x.error,
            "next_attempt_at": x.next_attempt_at.isoformat() if x.next_attempt_at else None,
            "lead_id": str(x.lead_id) if x.lead_id else None,
            "conversation_id": str(x.conversation_id) if x.conversation_id else None,
            "charged": x.charged_at is not None}

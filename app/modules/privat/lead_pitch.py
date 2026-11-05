"""The lead loop: ONE short, honest sentence about Dialogbot at the end of a Privat call, and a lead in the sales workspace
only when the business says yes and gives an address. docs/sales/privat-opkald-leads.md.

The rules live here, in code, and never in a prompt:
- the line is a FIXED text (PITCH_LINE), not AI-written; the assistant is told to say exactly what the tool returns, and the
  closing part of the transcript is cut away before the errand is classified, so the line can never change `confirmed_text`;
- it exists only in calls a Privat user asked for (campaign and demo calls have other assistants and never get the tool);
- it is said only when the user's errand is finished (agreed or declined), the business is not a Dialogbot customer, is not on a block
  list, was not given the line within LEAD_PITCH_COOLDOWN_DAYS, and is not «reklamebeskyttet» (unknown counts as protected);
- it never interrupts: calm business only, never when the other side hung up or the call went badly;
- no lead and no e-mail address without an explicit yes; a no puts the business on the block list and nothing else is stored.

NOT legally reviewed. Do not set LEAD_PITCH_ENABLED in production before a lawyer has confirmed it.
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timedelta

import structlog
from sqlalchemy import func, select
from sqlalchemy.orm import Session as OrmSession

from app.config import get_settings
from app.models import (
    BusinessProfile,
    ExternalBusinessContact,
    Lead,
    PhoneNumber,
    PrivateCall,
    SalesBlockList,
    TelephonySetup,
    Workspace,
)
from app.modules.privat import rules

log = structlog.get_logger("dialogbot.leadpitch")

# --- the fixed texts. Changing one is a decision (the wording is locked by tests/test_lead_pitch.py) -----------------------
PITCH_LINE = ("Tak for hjælpen. Jeg ringer på vegne af en kunde via Dialogbot – hvis I vil høre, hvad det kan gøre for jeres "
              "telefon, sender vi gerne en mail. Ellers ingen problem, hav en god dag.")
ASK_EMAIL_LINE = "Det er dejligt. Hvilken mailadresse skal vi sende den til?"
BAD_EMAIL_LINE = "Jeg fik ikke adressen helt med. Kan du sige den igen, langsomt?"
THANKS_LINE = "Tak, så sender vi en kort mail. Hav en god dag."
DECLINE_LINE = "Helt i orden. Tak for hjælpen, hav en god dag."
SKIP_LINE = "Sig ikke noget om Dialogbot. Afslut som vanligt med: Tak for hjælpen, hav en god dag."
PITCH_MARKER = "Jeg ringer på vegne af en kunde via Dialogbot"   # how the line is found again in the transcript

TOOL_PITCH, TOOL_REPLY = "end_call_pitch", "pitch_reply"
ERRAND_DONE = ("confirmed", "declined")

# Skip reasons (private_calls.pitch_skipped_reason)
R_CUSTOMER, R_BLOCKED, R_COOLDOWN = "dialogbot_customer", "blocklisted", "cooldown"
R_PROTECTED, R_PROTECTION_UNKNOWN = "advertising_protected", "advertising_unknown"
R_NOT_ANSWERED, R_COUNTERPARTY_ENDED, R_ERRAND_OPEN, R_STRESSED = "call_not_answered", "counterparty_ended", "errand_not_finished", "stressed"
R_NO_REPLY, R_HUNG_UP, R_NO_EMAIL, R_NO_PHONE = "no_reply", "hung_up_during_pitch", "no_email_given", "no_number"

PROMPT = f"""

Afslutning (kun hvis du har værktøjerne {TOOL_PITCH} og {TOOL_REPLY}):
- Dit ærinde kommer ALTID først. Aftalen skal være bekræftet af dig (du har gentaget dag og klokkeslæt), eller virksomheden har sagt nej, før du gør noget af det følgende.
- Er samtalen rolig og venlig, så kald {TOOL_PITCH} med errand_outcome (confirmed eller declined) og business_is_calm. Virker virksomheden stresset, har travlt, er utålmodig, eller er samtalen gået dårligt, så kald den med business_is_calm=false og sig ikke mere.
- Sig derefter ORDRET det, værktøjet giver dig. Ændr ingenting, tilføj ingenting, og nævn aldrig priser eller sammenligninger.
- Siger de ja til en mail: spørg efter adressen, gentag den bogstav for bogstav, og kald {TOOL_REPLY} med interested=true og email. Siger de nej: kald {TOOL_REPLY} med interested=false og sig det, værktøjet giver dig.
- Lægger de på, eller svarer de ikke: gør ikke mere. Afbryd aldrig nogen."""

_EMAIL = re.compile(r"^[A-Za-z0-9._%+\-]{1,64}@([A-Za-z0-9\-]+\.)+[A-Za-z]{2,}$")

CATEGORIES = (("frisør", ("frisør", "barber", "klip")), ("tandlæge", ("tandlæge", "tand")), ("læge og behandler", ("læge", "fysio", "kiropraktor", "massage", "behandl")),
              ("værksted", ("værksted", "cykel", "bil", "dæk", "mekaniker")), ("håndværker", ("vvs", "elektriker", "maler", "tømrer", "murer", "gulv", "blikkenslager")),
              ("restaurant og café", ("restaurant", "café", "cafe", "bord", "pizza")), ("skønhed og velvære", ("kosmetolog", "negle", "spa", "skønhed", "hudpleje")))


def category_for(purpose: str | None, business_name: str | None) -> str:
    """A coarse category for the lead («værksted»), never the user's words or name."""
    hay = f"{purpose or ''} {business_name or ''}".lower()
    for label, words in CATEGORIES:
        if any(w in hay for w in words):
            return label
    return "andet"


def valid_email(raw: str | None) -> str | None:
    e = (raw or "").strip().strip(".,;:").replace(" ", "").lower()
    return e if len(e) <= 254 and _EMAIL.match(e) else None


def _now() -> datetime:
    return rules.now()


# --------------------------------------------------------------------------- the business

def _digits8(phone: str | None) -> str | None:
    d = "".join(ch for ch in (phone or "") if ch.isdigit())
    return d[-8:] if len(d) >= 8 else None


def is_dialogbot_customer(db: OrmSession, *, cvr: str | None, phone: str | None) -> bool:
    """Is this business one of our customers? CVR and phone against the business workspaces (never a personal workspace, never the
    sales workspace itself)."""
    sales_id = get_settings().sales_workspace_id
    biz = select(Workspace.id).where(Workspace.kind == "business")
    if sales_id:
        biz = biz.where(Workspace.id != uuid.UUID(sales_id))
    ids = biz.scalar_subquery()
    if cvr and db.scalar(select(BusinessProfile.workspace_id).where(BusinessProfile.workspace_id.in_(ids), BusinessProfile.cvr == cvr).limit(1)):
        return True
    d8 = _digits8(phone)
    if not d8:
        return False
    if db.scalar(select(PhoneNumber.id).where(PhoneNumber.workspace_id.in_(ids), PhoneNumber.e164.like(f"%{d8}")).limit(1)):
        return True
    if db.scalar(select(TelephonySetup.workspace_id).where(TelephonySetup.workspace_id.in_(ids), TelephonySetup.business_number.like(f"%{d8}")).limit(1)):
        return True
    digits = func.regexp_replace(BusinessProfile.phone, "[^0-9]", "", "g")
    return db.scalar(select(BusinessProfile.workspace_id).where(BusinessProfile.workspace_id.in_(ids), digits.like(f"%{d8}")).limit(1)) is not None


def _city_of(address: str | None) -> str | None:
    m = re.search(r"\b\d{4}\s+([^,]+)$", (address or "").strip())
    return m.group(1).strip() if m else None


def ensure_contact(db: OrmSession, c: PrivateCall) -> ExternalBusinessContact:
    """The remembered row for this call's business (by phone, then place id), made if it does not exist. CVR is looked up once,
    best effort, so «reklamebeskyttet» is known; nothing about the USER is stored here."""
    row = None
    if c.business_phone_e164:
        row = db.scalar(select(ExternalBusinessContact).where(ExternalBusinessContact.phone_e164 == c.business_phone_e164))
    if row is None and c.place_id:
        row = db.scalar(select(ExternalBusinessContact).where(ExternalBusinessContact.place_id == c.place_id))
    if row is None:
        row = ExternalBusinessContact(name=c.business_name[:200], phone_e164=c.business_phone_e164, place_id=c.place_id,
                                      address=c.business_address or None, city=_city_of(c.business_address))
        db.add(row)
        db.flush()
    if row.advertising_protected is None:
        from app.modules.browser import lookup

        hit = lookup._cvr_part(row.name, row.city)
        if hit is not None:
            other = db.scalar(select(ExternalBusinessContact).where(ExternalBusinessContact.cvr == hit["cvr"],
                                                                  ExternalBusinessContact.id != row.id))
            if other is not None:       # the same company is already remembered under its CVR number: use that row
                other.phone_e164 = other.phone_e164 or row.phone_e164
                other.place_id = other.place_id or row.place_id
                db.delete(row)
                db.flush()
                row = other
            row.cvr = row.cvr or hit["cvr"]
            row.advertising_protected = hit["advertising_protected"]
            row.cvr_looked_up_at = _now()
    row.is_dialogbot_customer = is_dialogbot_customer(db, cvr=row.cvr, phone=row.phone_e164)
    db.flush()
    return row


def _on_block_list(db: OrmSession, row: ExternalBusinessContact) -> bool:
    values = [("phone", row.phone_e164), ("cvr", row.cvr)]
    return any(v and db.scalar(select(SalesBlockList.id).where(SalesBlockList.kind == k, SalesBlockList.value == v)) for k, v in values)


def eligibility(db: OrmSession, c: PrivateCall, *, now: datetime | None = None) -> tuple[bool, str | None, ExternalBusinessContact | None]:
    """May the closing line be offered in this call at all? (ok, skip reason, the remembered business.) With the flag off the
    answer is (False, None, None): nothing happens and nothing is logged."""
    s = get_settings()
    if not s.lead_pitch_enabled:
        return False, None, None
    if not c.business_phone_e164:
        return False, R_NO_PHONE, None
    now = now or _now()
    row = ensure_contact(db, c)
    if row.is_dialogbot_customer:
        return False, R_CUSTOMER, row
    if row.blocklisted or _on_block_list(db, row):
        return False, R_BLOCKED, row
    if row.last_pitch_at is not None and now - row.last_pitch_at < timedelta(days=s.lead_pitch_cooldown_days):
        return False, R_COOLDOWN, row
    if row.advertising_protected is True:
        return False, R_PROTECTED, row
    if row.advertising_protected is None:       # we could not find out: treat it as protected rather than risk a marketing call
        return False, R_PROTECTION_UNKNOWN, row
    return True, None, row


# --------------------------------------------------------------------------- the assistant: tools and prompt

def vapi_tools(db: OrmSession, c: PrivateCall) -> tuple[list[dict], str]:
    """(tools, extra system prompt) for the Privat call assistant. Empty unless the line may be offered; when the flag is on and
    the rules say no, the reason is logged on the call, so «why was nothing said» can always be answered."""
    ok, reason, _row = eligibility(db, c)
    if not ok:
        if reason is not None:
            c.pitch_outcome, c.pitch_skipped_reason = "skipped", reason
        return [], ""
    tools = [
        {"type": "function", "function": {
            "name": TOOL_PITCH,
            "description": "Kald når dit ærinde er afsluttet. Svaret er den tekst, du skal sige ordret.",
            "parameters": {"type": "object", "properties": {
                "errand_outcome": {"type": "string", "enum": ["confirmed", "declined", "open"],
                                   "description": "confirmed = aftalen er bekræftet af dig. declined = virksomheden sagde nej. open = ærindet er ikke afsluttet"},
                "business_is_calm": {"type": "boolean", "description": "false hvis virksomheden virker stresset, har travlt eller samtalen er gået dårligt"}},
                "required": ["errand_outcome", "business_is_calm"]}}},
        {"type": "function", "function": {
            "name": TOOL_REPLY,
            "description": "Virksomhedens svar på tilbuddet om en mail.",
            "parameters": {"type": "object", "properties": {
                "interested": {"type": "boolean"},
                "email": {"type": "string", "description": "Kun hvis de sagde ja og gav adressen"}},
                "required": ["interested"]}}},
    ]
    return tools, PROMPT


def private_call_for(db: OrmSession, message: dict) -> PrivateCall | None:
    """The Privat call a Vapi `tool-calls` message belongs to (by call id, then by the metadata we put on it)."""
    from app.modules.telephony.vapi import _dig

    call_id = str(_dig(message, "call", "id") or "")
    c = db.scalar(select(PrivateCall).where(PrivateCall.vapi_call_id == call_id).with_for_update()) if call_id else None
    if c is None:
        raw = _dig(message, "call", "metadata", "private_call_id") or _dig(message, "call", "assistant", "metadata", "private_call_id")
        try:
            c = db.scalar(select(PrivateCall).where(PrivateCall.id == uuid.UUID(str(raw))).with_for_update()) if raw else None
        except ValueError:
            c = None
    return c


def execute_tool(db: OrmSession, c: PrivateCall, name: str, args: dict) -> str:
    if name == TOOL_PITCH:
        return _say_line(db, c, args)
    if name == TOOL_REPLY:
        return _reply(db, c, args)
    return "Ukendt værktøj."


def _skip(c: PrivateCall, reason: str) -> str:
    c.pitch_outcome, c.pitch_skipped_reason = "skipped", reason
    return SKIP_LINE


def _say_line(db: OrmSession, c: PrivateCall, args: dict) -> str:
    if c.pitch_started_at is not None:
        return "Teksten er allerede sagt. Sig ikke mere om Dialogbot."
    if c.status != "in_progress":
        return _skip(c, R_NOT_ANSWERED)
    ok, reason, row = eligibility(db, c)          # the rules are checked AGAIN here, not only when the call was set up
    if not ok:
        return _skip(c, reason or "not_eligible") if reason else SKIP_LINE
    if args.get("errand_outcome") not in ERRAND_DONE:
        return _skip(c, R_ERRAND_OPEN)
    if args.get("business_is_calm") is not True:
        return _skip(c, R_STRESSED)
    now = _now()
    c.pitch_started_at, c.pitch_outcome, c.pitch_skipped_reason = now, None, None
    row.last_pitch_at, row.pitch_count = now, (row.pitch_count or 0) + 1       # the cooldown starts when the line is said
    return f"Sig præcis denne tekst, uden at ændre noget: «{PITCH_LINE}» Vent derefter på svar."


def _reply(db: OrmSession, c: PrivateCall, args: dict) -> str:
    if c.pitch_started_at is None:
        return "Teksten om Dialogbot er ikke sagt endnu. Sig ikke mere om det."
    row = ensure_contact(db, c)
    if args.get("interested") is False:
        c.pitch_outcome, c.pitch_skipped_reason = "declined", None
        row.last_outcome, row.blocklisted, row.blocklist_reason = "declined", True, "declined_pitch"
        from app.modules.sales import outbound

        for kind, value in (("phone", row.phone_e164), ("cvr", row.cvr)):
            if value:
                outbound.block(db, kind=kind, value=value, reason="Afviste afslutningslinjen i et Privat-opkald", source="call", user_id=None)
        return DECLINE_LINE                       # only the block list and the date are kept: no lead, no address, no follow-up
    email = valid_email(args.get("email"))
    if args.get("interested") is not True:
        return DECLINE_LINE
    if not email:
        return ASK_EMAIL_LINE if not args.get("email") else BAD_EMAIL_LINE
    c.pitch_outcome, c.pitch_skipped_reason = "interested", None
    row.last_outcome, row.email, row.consent_to_email, row.consent_at = "interested", email, True, _now()
    upsert_lead(db, c, row)
    return THANKS_LINE


# --------------------------------------------------------------------------- the report

def split_transcript(transcript: str) -> tuple[str, str]:
    """(the errand, the closing). The closing starts at the line where the fixed text was said; everything before it is what
    the errand is classified on, so the line cannot leak into `confirmed_text`."""
    lines = (transcript or "").split("\n")
    for i, ln in enumerate(lines):
        if PITCH_MARKER in ln:
            return "\n".join(lines[:i]), "\n".join(lines[i:])
    return transcript or "", ""


def excerpt(closing: str) -> str | None:
    """Only the closing, at most 500 characters."""
    text = closing.strip()
    return text[:500] or None


def finalize(db: OrmSession, c: PrivateCall, *, answered: bool, ended_reason: str, closing: str, has_transcript: bool = True) -> None:
    """At the end-of-call report: settle what the closing line came to, and put the report on the lead if there is one."""
    if not get_settings().lead_pitch_enabled:
        return
    if c.pitch_started_at is not None and has_transcript and PITCH_MARKER not in closing:
        # The assistant was handed the fixed text but the transcript does not contain it: whatever the business said yes to, it was
        # not our offer. The consent is withdrawn, the address deleted, and nothing is followed up.
        c.pitch_outcome, c.pitch_skipped_reason, c.pitch_transcript_excerpt = "skipped", "line_not_verbatim", None
        _withdraw(db, c)
        return
    if c.pitch_started_at is None and c.pitch_outcome is None:
        if not answered:
            c.pitch_outcome, c.pitch_skipped_reason = "skipped", R_NOT_ANSWERED
        elif ended_reason.startswith("customer-ended"):
            c.pitch_outcome, c.pitch_skipped_reason = "skipped", R_COUNTERPARTY_ENDED
        else:
            c.pitch_outcome, c.pitch_skipped_reason = "not_asked", "assistant_did_not_ask"
    elif c.pitch_started_at is not None and c.pitch_outcome is None:
        # the line was said but there was no usable answer
        c.pitch_outcome = "skipped"
        c.pitch_skipped_reason = R_HUNG_UP if ended_reason.startswith("customer-ended") else R_NO_REPLY
    if c.pitch_started_at is not None:
        c.pitch_transcript_excerpt = excerpt(closing)
    if c.pitch_outcome == "interested":
        row = ensure_contact(db, c)
        upsert_lead(db, c, row)
    elif c.pitch_outcome == "skipped" and c.pitch_skipped_reason in (R_NO_REPLY, R_HUNG_UP) and c.pitch_started_at is not None:
        ensure_contact(db, c).last_outcome = "skipped"


# --------------------------------------------------------------------------- the lead

def _withdraw(db: OrmSession, c: PrivateCall) -> None:
    row = ensure_contact(db, c)
    row.email, row.consent_to_email, row.consent_at, row.last_outcome = None, False, None, "skipped"
    lead = db.get(Lead, row.lead_id) if row.lead_id else None
    if lead is not None:
        from app.models import Task

        lead.contact_email = None
        lead.need_summary = (lead.need_summary + " Samtykket er trukket tilbage: afslutningslinjen blev ikke sagt ordret. Send ingen mail.")[:2000]
        for t in db.scalars(select(Task).where(Task.lead_id == lead.id, Task.status == "open", Task.title.like("Send intro-mail%"))):
            t.status, t.completed_at = "done", _now()
    db.flush()


def upsert_lead(db: OrmSession, c: PrivateCall, row: ExternalBusinessContact) -> Lead | None:
    """One lead per business in the sales workspace: a repeat updates it. Created only for a business that said yes AND gave an
    address; the user's name and errand never reach it, only a category."""
    from app.modules.leads import service as leads
    from app.modules.sales import service as sales

    ws = sales.sales_workspace(db)
    if ws is None or not row.consent_to_email or not row.email:
        return None
    engine = "ukendt"
    if row.booking_profile_id is not None:
        from app.models import BusinessBookingProfile

        engine = (db.get(BusinessBookingProfile, row.booking_profile_id).engine or "ukendt")
    text = (f"Privat-opkald · kategori: {category_for(c.purpose, c.business_name)} · bookingsystem: {engine}. "
            f"{row.name} sagde ja til en mail om Dialogbot ({rules.local(row.consent_at).date().isoformat()}). "
            f"Uddrag af afslutningen: «{(c.pitch_transcript_excerpt or 'se opkaldet')[:300]}». Foreslået næste skridt: Send intro-mail.")
    lead = db.get(Lead, row.lead_id) if row.lead_id else None
    if lead is None and row.phone_e164:
        lead = db.scalar(select(Lead).where(Lead.workspace_id == ws.id, Lead.source == "privat_call", Lead.contact_phone == row.phone_e164))
    created = lead is None
    if created:
        lead = leads.create_lead(db, ws.id, source="privat_call", created_by=None, contact_name=row.name, contact_email=row.email,
                                 contact_phone=row.phone_e164, need_summary=text)
    else:
        lead.contact_email, lead.need_summary = row.email, text
    row.lead_id = lead.id
    from app.models import Task

    open_task = db.scalar(select(Task.id).where(Task.lead_id == lead.id, Task.status == "open", Task.title.like("Send intro-mail%")))
    if open_task is None:
        leads.create_task(db, ws.id, title=f"Send intro-mail til {row.name}", created_by=None, lead=lead, due_at=_now() + timedelta(days=1))
    if created:
        leads._notify_new_lead(db, lead)
    db.flush()
    return lead

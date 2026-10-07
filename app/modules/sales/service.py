"""Demo calls: Dialogbot's own assistant rings a prospect who asked for it, so they hear the product.

Why only on request (markedsføringsloven § 10 stk. 1): a call placed and conducted by the AI is an "automatiseret
opkaldssystem", which needs the recipient's prior request – for businesses too. So there are two doors, both with
documented consent stored on the row:
- `web`: the prospect enters their number on dialogbot.dk and ticks the consent box ("Ring mig op nu").
- `seller`: a Dialogbot seller has the prospect on the phone (a person calling a business is allowed unless the
  business is advertising-protected in CVR), asks "må vores AI ringe dig op nu?", and on a yes presses the button.
  The seller is recorded and an advertising-protected CVR number is refused.

Calls come from the sales workspace (SALES_WORKSPACE_ID): its approved knowledge describes Dialogbot, its
outbound-approved number places the call, and interested prospects become leads with a task there. The same
workspace's inbound number is the public demo number. Numbers on its do-not-call list are never called, and
"ring ikke igen" adds the number to it.

Abuse limits for the public door: Danish numbers only (no premium-rate ranges), one web request per number per
24 hours, a global cap per hour, and only inside the calling hours.
"""
from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session as OrmSession

from app.config import get_settings
from app.core.errors import ApiError, Conflict, ValidationFailed
from app.models import DemoCall, DoNotCall, PhoneNumber, Workspace

TZ = ZoneInfo("Europe/Copenhagen")
MAX_SECONDS = 300
WEB_REPEAT_AFTER = timedelta(hours=24)
DK_NUMBER = re.compile(r"^\+45[2-9]\d{7}$")
PREMIUM = re.compile(r"^\+4590")  # 90xx xxxx: overtakseret
CONSENT_VERSION_WEB = "demo-call-web-v1"
CONSENT_VERSION_SELLER = "demo-call-seller-v1"
CONSENT_TEXT_WEB = ("Ja tak, Dialogbots digitale assistent må ringe mig op på dette nummer nu og vise, hvordan den "
                    "tager telefonen. Opkaldet bliver skrevet ned, og en medarbejder fra Dialogbot må kontakte mig "
                    "bagefter om det, vi talte om.")
CONSENT_TEXT_SELLER = ("Kontakten sagde ja i telefonen til, at Dialogbots digitale assistent ringer op nu og viser, "
                       "hvordan den tager telefonen.")


class DemoUnavailable(ApiError):
    status_code = 503
    code = "demo_unavailable"


class DemoRateLimited(ApiError):
    status_code = 429
    code = "demo_rate_limited"


def _now() -> datetime:
    return datetime.now(UTC)


def sales_workspace(db: OrmSession) -> Workspace | None:
    raw = get_settings().sales_workspace_id
    try:
        return db.get(Workspace, uuid.UUID(raw)) if raw else None
    except ValueError:
        return None


def _numbers(db: OrmSession, ws: Workspace) -> list[PhoneNumber]:
    return list(db.scalars(select(PhoneNumber).where(PhoneNumber.workspace_id == ws.id, PhoneNumber.active.is_(True),
                                                     PhoneNumber.status == "active")
                           .order_by(PhoneNumber.created_at)))


def caller_number(db: OrmSession, ws: Workspace) -> PhoneNumber | None:
    return next((n for n in _numbers(db, ws) if n.outbound_allowed and n.provider_number_id), None)


def demo_number(db: OrmSession) -> str | None:
    """The sales workspace's inbound number: prospects can ring it themselves (no consent question at all)."""
    ws = sales_workspace(db)
    nums = _numbers(db, ws) if ws else []
    return nums[0].e164 if nums else None


def problem(db: OrmSession) -> str | None:
    """Why demo calls cannot be placed now (None = ready). Configuration only; never secrets."""
    s = get_settings()
    ws = sales_workspace(db)
    if ws is None:
        return "SALES_WORKSPACE_ID er ikke sat"
    if not s.vapi_api_key or not s.vapi_server_secret:
        return "Udgående opkald er ikke sat op (VAPI_API_KEY/VAPI_SERVER_SECRET)"
    if caller_number(db, ws) is None:
        return "Salgsarbejdsrummet har intet aktivt nummer, der er godkendt til udgående opkald"
    from app.modules.knowledge import service as knowledge

    if not knowledge.active_knowledge(db, ws.id):
        return "Salgsarbejdsrummet har ingen godkendt viden om Dialogbot"
    return None


def hours() -> tuple[time, time]:
    s = get_settings()
    return time.fromisoformat(s.sales_call_from), time.fromisoformat(s.sales_call_to)


def in_hours(now: datetime) -> bool:
    start, end = hours()
    return start <= now.astimezone(TZ).time() < end


def info(db: OrmSession) -> dict:
    start, end = hours()
    return {"available": problem(db) is None, "demo_number": demo_number(db), "open_now": in_hours(_now()),
            "hours": {"from": start.strftime("%H:%M"), "to": end.strftime("%H:%M")},
            "consent_text": CONSENT_TEXT_WEB, "consent_version": CONSENT_VERSION_WEB}


def danish_number(raw: str) -> str:
    from app.modules.campaigns.service import normalize_phone

    n = normalize_phone(raw)
    if n is None or not DK_NUMBER.match(n) or PREMIUM.match(n):
        raise ValidationFailed("Skriv et dansk telefonnummer med 8 cifre", field_errors=[{"field": "phone"}])
    return n


def _blocked(db: OrmSession, ws: Workspace, phone: str) -> bool:
    return db.scalar(select(DoNotCall.id).where(DoNotCall.workspace_id == ws.id, DoNotCall.phone == phone)) is not None


def _global_cap(db: OrmSession, ws: Workspace, now: datetime) -> None:
    n = db.scalar(select(func.count()).where(DemoCall.workspace_id == ws.id,
                                             DemoCall.created_at > now - timedelta(hours=1))) or 0
    if n >= get_settings().sales_max_calls_per_hour:
        raise DemoRateLimited("Der er mange i kø lige nu. Prøv igen om lidt, eller ring selv til vores demonummer.")


# --------------------------------------------------------------------------- the call

def first_message(d: DemoCall) -> str:
    who = d.name.split(" ")[0] if d.name else ""
    hello = f"Hej {who}" if who else "Hej"
    if d.company:
        return (f"{hello}, det er Dialogbots digitale assistent, som du bad om at blive ringet op af. Lad os lade som om, "
                f"jeg er receptionist hos {d.company}. Du kan ringe ind som en af jeres kunder, eller spørge mig om "
                "Dialogbot. Hvad vil du helst?")
    return (f"{hello}, det er Dialogbots digitale assistent, som du bad om at blive ringet op af. Jeg kan vise, hvordan "
            "jeg ville tage telefonen for jeres virksomhed. Hvad hedder virksomheden, og hvad laver I?")


def system_prompt(db: OrmSession, ws: Workspace, d: DemoCall) -> str:
    from app.modules.ai.service import CHANNEL_INSTRUCTIONS, build_system_prompt

    base, _rev = build_system_prompt(db, ws)  # approved knowledge about Dialogbot only
    return f"""{base}

{CHANNEL_INSTRUCTIONS["phone"][1]}

Dette er et DEMO-opkald. Du ringer UD fra {ws.name}, fordi kontakten selv har bedt om det. Kontakt: {d.name or "ukendt navn"}{f", {d.company}" if d.company else ""}.
Formål: kontakten skal høre, hvordan du ville tage telefonen for deres egen virksomhed, og få svar på spørgsmål om Dialogbot.

Sådan gør du:
- Hvis kontakten vil prøve rollespillet, så vær receptionist for deres virksomhed. Spørg kort, hvad virksomheden laver, hvis du ikke ved det. Vis det, du kan: tage imod en henvendelse, spørge ind til behovet, notere navn og nummer, og love at en medarbejder ringer tilbage. Opfind aldrig priser, åbningstider eller ydelser for deres virksomhed – sig at det står i den viden, virksomheden selv godkender.
- Svar på spørgsmål om Dialogbot kun ud fra den godkendte viden ovenfor. Lov aldrig rabatter eller aftaler.
- Hvis kontakten vil i gang eller vil tale med en person, så sig at en medarbejder fra Dialogbot ringer tilbage, og spørg hvornår det passer.
- Du er en digital assistent. Lyv aldrig om at være et menneske.
- Hvis kontakten ikke vil tale mere eller ikke vil ringes op igen, så undskyld, bekræft det og afslut straks.
- Opkaldet varer højst fem minutter. Afslut med at takke for snakken."""


def assistant(db: OrmSession, ws: Workspace, d: DemoCall, number: PhoneNumber) -> dict:
    from app.modules.telephony import vapi

    s = get_settings()
    out: dict = {
        "firstMessage": first_message(d),
        "model": {"provider": s.vapi_model_provider, "model": vapi.phone_model(s),
                  "messages": [{"role": "system", "content": system_prompt(db, ws, d)}]},
        "transcriber": vapi.transcriber_for(db, ws),
        "maxDurationSeconds": MAX_SECONDS,
        "voicemailDetection": {"provider": "vapi"},
        "endCallPhrases": ["Tak for snakken, hav en god dag", "Undskyld forstyrrelsen, hav en god dag"],
        "analysisPlan": vapi.ANALYSIS_PLAN,
        "metadata": {"workspace_id": str(ws.id), "demo_call_id": str(d.id)},
    }
    from app.modules.voices import standard

    out["voice"] = standard.provider_voice(db, ws.id, number)
    return out


def place(db: OrmSession, ws: Workspace, d: DemoCall) -> None:
    """Dial now. A failure is stored on the row (the prospect is told to try again or ring the demo number)."""
    from app.modules.campaigns.service import create_call

    number = caller_number(db, ws)
    payload = {"phoneNumberId": number.provider_number_id,
               "customer": {"number": d.phone, **({"name": d.name[:40]} if d.name else {})},
               "assistant": assistant(db, ws, d, number), "metadata": {"demo_call_id": str(d.id)}}
    try:
        out = create_call(payload)
    except ApiError as e:
        d.status, d.error = "failed", e.message[:300]
        return
    d.provider_call_id = str(out.get("id") or "")[:100] or None


def request_web(db: OrmSession, *, phone: str, name: str, company: str) -> DemoCall | None:
    """The public door. Returns None when the number must not be called (do-not-call): the answer to the visitor
    is the same, so the endpoint does not reveal who has opted out."""
    now = _now()
    phone = danish_number(phone)
    if problem(db) is not None:
        raise DemoUnavailable("Demo-opkald er ikke åbnet endnu. Skriv dig på ventelisten, så hører du fra os.")
    ws = sales_workspace(db)
    if not in_hours(now):
        start, end = hours()
        raise Conflict(f"Vi ringer mellem kl. {start:%H:%M} og {end:%H:%M}. Prøv igen i det tidsrum.", code="demo_closed")
    if db.scalar(select(DemoCall.id).where(DemoCall.phone == phone, DemoCall.source == "web",
                                           DemoCall.created_at > now - WEB_REPEAT_AFTER)):
        raise DemoRateLimited("Vi har allerede ringet til dette nummer i dag. Ring selv til demonummeret, hvis du vil "
                              "prøve igen.", code="demo_already_called")
    _global_cap(db, ws, now)
    d = DemoCall(workspace_id=ws.id, source="web", phone=phone, name=name.strip()[:200], company=company.strip()[:200],
                 consent_version=CONSENT_VERSION_WEB, consent_text=CONSENT_TEXT_WEB, consented_at=now)
    db.add(d)
    if _blocked(db, ws, phone):
        d.status, d.error = "skipped", "Nummeret står på spærrelisten"
        db.flush()
        return None
    db.flush()
    place(db, ws, d)
    return d


def request_seller(db: OrmSession, *, seller_id: uuid.UUID, phone: str, name: str, company: str, cvr: str | None,
                   note: str) -> DemoCall:
    from app.modules.business import cvr as cvr_register

    now = _now()
    phone = danish_number(phone)
    if (why := problem(db)) is not None:
        raise DemoUnavailable(f"Demo-opkald kan ikke foretages: {why}")
    ws = sales_workspace(db)
    if cvr:
        cvr = "".join(ch for ch in cvr if ch.isdigit())
        if cvr_register.configured():
            if cvr_register.lookup(cvr).get("advertising_protected"):
                raise Conflict("Virksomheden er reklamebeskyttet i CVR. I må ikke ringe til den for at sælge.",
                               code="advertising_protected")
    if _blocked(db, ws, phone):
        raise Conflict("Nummeret står på spærrelisten, fordi kontakten har frabedt sig opkald.", code="do_not_call")
    _global_cap(db, ws, now)
    d = DemoCall(workspace_id=ws.id, source="seller", phone=phone, name=name.strip()[:200], company=company.strip()[:200],
                 cvr=cvr or None, consent_version=CONSENT_VERSION_SELLER, consent_text=CONSENT_TEXT_SELLER,
                 consented_at=now, seller_user_id=seller_id, note=note.strip()[:500])
    db.add(d)
    db.flush()
    place(db, ws, d)
    return d


# --------------------------------------------------------------------------- report

def on_report(db: OrmSession, message: dict, *, call_id: str, conv, visitor_lines: int, transcript: str,
              summary: str) -> bool:
    """Apply an end-of-call report to its demo call. False when it is not a demo call."""
    from app.modules.campaigns.service import NO_ANSWER_REASONS, classify
    from app.modules.leads import service as leads

    d = db.scalar(select(DemoCall).where(DemoCall.provider_call_id == call_id).with_for_update())
    if d is None:
        return False
    ws = db.get(Workspace, d.workspace_id)
    reason = str(message.get("endedReason") or "")
    d.conversation_id = conv.id
    if visitor_lines == 0 or any(reason.startswith(r) for r in NO_ANSWER_REASONS):
        d.status = "no_answer"
        return True
    outcome, text = classify(db, ws, transcript, summary)
    d.status, d.outcome, d.summary = "done", outcome, text
    if outcome == "opt_out":
        if not _blocked(db, ws, d.phone):
            db.add(DoNotCall(workspace_id=ws.id, phone=d.phone, source="call", reason="Frabad sig opkald i et demo-opkald"))
        return True
    who = " – ".join(x for x in (d.name, d.company) if x) or d.phone
    lead = leads.create_lead(db, ws.id, source="demo_call", created_by=None, conversation=conv, contact_name=d.name,
                             contact_phone=d.phone,
                             need_summary=f"Demo-opkald{f' ({d.company})' if d.company else ''}: {text or 'se samtalen'}")
    d.lead_id = lead.id
    if outcome in ("interested", "callback"):
        leads._notify_new_lead(db, lead)
        leads.create_task(db, ws.id, title=(f"Ring til {who} – vil gerne i gang" if outcome == "interested"
                                            else f"Ring tilbage til {who} efter demo"),
                          created_by=None, lead=lead, due_at=_now() + timedelta(hours=2))
    return True


def out(d: DemoCall) -> dict:
    return {"id": str(d.id), "source": d.source, "phone": d.phone, "name": d.name, "company": d.company, "cvr": d.cvr,
            "status": d.status, "outcome": d.outcome, "summary": d.summary, "error": d.error,
            "consent_version": d.consent_version, "consented_at": d.consented_at.isoformat(),
            "seller_user_id": str(d.seller_user_id) if d.seller_user_id else None, "note": d.note,
            "lead_id": str(d.lead_id) if d.lead_id else None, "created_at": d.created_at.isoformat() if d.created_at else None}

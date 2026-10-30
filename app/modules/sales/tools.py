"""Peter's tools on an internal sales call (phase 3, §8 of docs/sales/intern-salgskanal.md).

Only offered on calls of an `internal_sales` campaign. A tool call is tied to the call server-side: the campaign contact
is looked up from Vapi's call id (never from metadata or the model's arguments), and every argument is checked against
the database – Peter can neither pick a free destination nor a free amount. Every run is one `action_runs` row in the
sales workspace (connector `dialogbot_sales`), ok, refused or failed alike.

Tools that change something outside the call (`book_moede`, `send_bestillingslink`) need `bekraeftet: true`, which the
description tells Peter to set only after the customer's explicit yes.
"""
from __future__ import annotations

import time
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from app.core.errors import ApiError
from app.models import (
    ActionRun,
    BookingType,
    Campaign,
    CampaignContact,
    SalesCompany,
    SalesContact,
    SalesMeeting,
    SalesOffer,
    SalesOpenQuestion,
    Workspace,
)
from app.modules.sales import offers

CONNECTOR = "dialogbot_sales"
MEETING_TYPE = "Intro-møde"  # the booking type in the sales workspace whose name starts with this
CONFIRM = "bekraeftet"
FOLLOW_UP_HOURS = 2


def _obj(props: dict, required: list[str] | None = None) -> dict:
    return {"type": "object", "properties": props, "required": required or []}


_CONFIRM_PROP = {CONFIRM: {"type": "boolean", "description": "true kun når kunden udtrykkeligt har sagt ja"}}
SPECS: list[dict] = [
    {"name": "hent_tilbud", "description": "Hent det aktuelle tilbud til virksomheden (eller prislisten). Læs det op ordret.",
     "parameters": _obj({})},
    {"name": "ledige_moedetider", "description": "Find højst to ledige tider til et 30 minutters intro-møde. Datoer som "
                                                 "ÅÅÅÅ-MM-DD; udelad dem for de nærmeste tider.",
     "parameters": _obj({"dato_fra": {"type": "string"}, "dato_til": {"type": "string"}})},
    {"name": "book_moede", "description": "Book intro-mødet på en af de tider, ledige_moedetider gav. Kræver kundens "
                                          "udtrykkelige ja til netop den tid.",
     "parameters": _obj({"slot": {"type": "string", "description": "start fra ledige_moedetider"},
                         "navn": {"type": "string"}, "email": {"type": "string"}, **_CONFIRM_PROP},
                        ["slot", "navn", CONFIRM])},
    {"name": "opret_ordreudkast", "description": "Opret et ordreudkast fra prislisten, når kunden tydeligt har sagt ja "
                                                 "til at gå videre. Returnerer det, du skal læse op.",
     "parameters": _obj({"setup_kind": {"type": "string", "enum": ["diy", "specialist"]}}, ["setup_kind"])},
    {"name": "send_bestillingslink", "description": "Send bestillingslinket (eller et oplæg) til den destination, kunden "
                                                    "har bekræftet. Kræver kundens udtrykkelige ja.",
     "parameters": _obj({"kanal": {"type": "string", "enum": ["email", "sms"]},
                         "bekraeftet_destination": {"type": "string"},
                         "slags": {"type": "string", "enum": ["order_link", "offer_summary"]}, **_CONFIRM_PROP},
                        ["kanal", "bekraeftet_destination", CONFIRM])},
    {"name": "registrer_frabedelse", "description": "Registrér at kontakten ikke vil kontaktes med salg igen. Afslut "
                                                    "derefter samtalen høfligt.",
     "parameters": _obj({"grund": {"type": "string"}})},
    {"name": "bed_menneske_foelge_op", "description": "Bed en kollega hos Dialogbot følge op inden for to timer (spørgsmål "
                                                      "du ikke kan svare på, ukendt integration, ønske om data/sletning).",
     "parameters": _obj({"emne": {"type": "string"}}, ["emne"])},
]
STOP_RECORDING = {"name": "stop_optagelse", "description": "Kunden vil ikke optages: optagelsen slettes efter samtalen.",
                  "parameters": _obj({})}
NAMES = {s["name"] for s in SPECS} | {STOP_RECORDING["name"]}

RULES = """VÆRKTØJER I DETTE OPKALD – går forud for manuskriptet:
Du har værktøjerne hent_tilbud, ledige_moedetider, book_moede, opret_ordreudkast, send_bestillingslink,
registrer_frabedelse og bed_menneske_foelge_op. Sig "et øjeblik, jeg kigger lige" før et værktøj, og læs svaret op med
dine egne ord. Lov aldrig noget, et værktøj ikke har bekræftet: en tid er kun booket, når book_moede siger det, og et
link er kun sendt, når send_bestillingslink siger det. Siger et værktøj, at en kollega følger op, så sig det til kunden.
Bekræft altid tid og destination med kunden, før du sætter bekraeftet til true. Stil højst to tider til rådighed."""


def vapi_tools(recording: bool = False) -> list[dict]:
    return [{"type": "function", "function": s} for s in SPECS + ([STOP_RECORDING] if recording else [])]


# --------------------------------------------------------------------------- dispatch


def contact_for_call(db: OrmSession, provider_call_id: str | None) -> CampaignContact | None:
    if not provider_call_id:
        return None
    return db.scalar(select(CampaignContact).join(Campaign, Campaign.id == CampaignContact.campaign_id)
                     .where(CampaignContact.provider_call_id == provider_call_id, Campaign.kind == "internal_sales"))


def execute(db: OrmSession, cc: CampaignContact, name: str, args: dict, provider_call_id: str | None,
            now: datetime | None = None) -> str:
    """Run one tool for this call. Never raises; always one action_runs row when the sales workspace exists."""
    from app.modules.sales import service

    ws = service.sales_workspace(db)
    if ws is None:
        return "Det kan jeg ikke gøre lige nu. Sig, at en kollega fra Dialogbot vender tilbage."
    started, status, error, out = time.monotonic(), "ok", None, ""
    try:
        if name not in NAMES:
            raise _Refused("Ukendt værktøj.")
        spec = next(s for s in [*SPECS, STOP_RECORDING] if s["name"] == name)
        if CONFIRM in spec["parameters"]["properties"] and args.get(CONFIRM) is not True:
            raise _Refused("Spørg kunden og få et udtrykkeligt ja, før du gør det.")
        out = HANDLERS[name](db, ws, cc, args, provider_call_id, now or datetime.now(UTC))
    except _Refused as e:
        status, out = "refused", str(e)
    except ApiError as e:
        status, error, out = "failed", e.message[:500], f"Det lykkedes ikke: {e.message} Tilbyd at en kollega følger op."
    except Exception as e:  # noqa: BLE001 – a tool must never break the call
        status, error, out = "failed", type(e).__name__, "Det lykkedes ikke. Tilbyd at en kollega følger op."
    db.add(ActionRun(workspace_id=ws.id, conversation_id=cc.conversation_id, channel="phone", connector=CONNECTOR,
                     action=name[:60], label=out[:200], input={k: v for k, v in args.items()},
                     output={"besked": out}, status=status, error=error,
                     duration_ms=int((time.monotonic() - started) * 1000), simulated=False,
                     provider_call_id=provider_call_id))
    return out[:1500]


class _Refused(Exception):
    pass


def _company(db: OrmSession, cc: CampaignContact) -> tuple[SalesCompany, SalesContact | None]:
    contact = db.get(SalesContact, cc.sales_contact_id) if cc.sales_contact_id else None
    company = db.get(SalesCompany, contact.company_id) if contact else None
    if company is None:
        raise _Refused("Opkaldet er ikke knyttet til en virksomhed.")
    return company, contact


def _open_offer(db: OrmSession, company: SalesCompany) -> SalesOffer | None:
    o = db.scalar(select(SalesOffer).where(SalesOffer.company_id == company.id).order_by(SalesOffer.version.desc()).limit(1))
    return o if o is not None and offers.refresh_status(o).status in ("draft", "sent") else None


def _hent_tilbud(db, ws, cc, args, pcid, now) -> str:
    company, _ = _company(db, cc)
    o = _open_offer(db, company)
    if o is not None:
        return f"Tilbud version {o.version}: {offers.sentence(o)}"
    from app.modules.billing import prices

    return (f"Prislisten: Dialogbot-receptionisten til {prices.kr(prices.SUBSCRIPTION_MONTHLY_NET_MINOR)} kroner om "
            f"måneden ekskl. moms, gør-det-selv-opsætning er med i abonnementet, specialist-opsætning "
            f"{prices.kr(prices.SPECIALIST_SETUP_NET_MINOR)} kr. én gang ekskl. moms. Ingen binding.")


def _meeting_type(db: OrmSession, ws: Workspace) -> BookingType | None:
    return db.scalar(select(BookingType).where(BookingType.workspace_id == ws.id, BookingType.active,
                                               BookingType.name.startswith(MEETING_TYPE)).order_by(BookingType.created_at))


def _date(raw) -> date | None:
    try:
        return date.fromisoformat(str(raw)[:10]) if raw else None
    except ValueError:
        return None


def _slots(db: OrmSession, ws: Workspace, args: dict, now: datetime) -> list[dict]:
    from app.modules.bookings import service as bookings
    from app.modules.reports.service import tz_of

    bt = _meeting_type(db, ws)
    if bt is None:
        return []
    tz = tz_of(db, ws.id)
    lo, hi = _date(args.get("dato_fra")), _date(args.get("dato_til"))
    out = []
    for s in bookings.slots(db, ws, bt, tz, now=now, limit=500):
        d = datetime.fromisoformat(s["start"]).date()
        if (lo is None or d >= lo) and (hi is None or d <= hi):
            out.append(s)
    return out


def _ledige(db, ws, cc, args, pcid, now) -> str:
    free = _slots(db, ws, args, now)
    if not free:
        if _meeting_type(db, ws) is None:
            return ("Jeg kan ikke slå mødetider op. Spørg hvilken dag og hvilket tidsrum der passer, og kald "
                    "bed_menneske_foelge_op, så en kollega bekræfter tiden.")
        return "Der er ingen ledige tider i den periode. Foreslå en anden uge, eller at en kollega finder en tid."
    picks = [free[0]] + ([x for x in free[1:] if x["start"][:10] != free[0]["start"][:10]][:1] or free[1:2])
    return "Ledige tider (tilbyd højst disse to): " + "; ".join(f"{p['label']} (slot {p['start']})" for p in picks)


def _book(db, ws, cc, args, pcid, now) -> str:
    from app.modules.bookings import service as bookings
    from app.modules.reports.service import tz_of

    company, contact = _company(db, cc)
    bt = _meeting_type(db, ws)
    if bt is None:
        raise _Refused("Mødebooking er ikke sat op. Kald bed_menneske_foelge_op i stedet.")
    slot = str(args.get("slot") or "")
    if slot not in {s["start"] for s in _slots(db, ws, {}, now)}:
        raise _Refused("Den tid er ikke ledig længere. Kald ledige_moedetider igen.")
    email = (args.get("email") or "").strip().lower() or (contact.email if contact else None)
    b = bookings.book(db, ws, type_id=bt.id, start=slot, name=str(args.get("navn") or "")[:200],
                      phone=cc.phone, email=email or None, note=f"Intro-møde med {company.display_name} (salgsopkald)",
                      source="phone", tz=tz_of(db, ws.id))
    b.provider_call_id = pcid
    db.add(SalesMeeting(company_id=company.id, contact_id=contact.id if contact else None, booking_id=b.id,
                        campaign_contact_id=cc.id, starts_at=b.starts_at, status="confirmed"))
    return f"Mødet er booket: {bookings.label(b.starts_at, tz_of(db, ws.id))}. Gentag tiden for kunden."


def _ordreudkast(db, ws, cc, args, pcid, now) -> str:
    company, contact = _company(db, cc)
    o = _open_offer(db, company)
    kind = args.get("setup_kind")
    if o is None or o.setup_kind != kind:
        o = offers.create(db, company, setup_kind=str(kind), contact_id=contact.id if contact else None, user_id=None)
    return (f"Ordreudkast version {o.version} er klar (ikke en ordre). Læs op: {offers.sentence(o)} Spørg derefter, om "
            f"bestillingslinket skal sendes på e-mail eller SMS, og bekræft adressen.")


def _send(db, ws, cc, args, pcid, now) -> str:
    from app.modules.leads import service as leads

    company, contact = _company(db, cc)
    o = _open_offer(db, company)
    if o is None:
        o = offers.create(db, company, setup_kind="diy", contact_id=contact.id if contact else None, user_id=None)
    kind = args.get("slags") if args.get("slags") in ("order_link", "offer_summary") else "order_link"
    try:
        r = offers.request_message(db, o, channel=str(args.get("kanal")), destination=str(args.get("bekraeftet_destination")),
                                   kind=kind, campaign_contact_id=cc.id, provider_call_id=pcid)
    except ApiError as e:
        raise _Refused(f"{e.message} Bed kunden gentage eller stave den.") from e
    if r.status == "sent":
        return "Linket er sendt. Sig, at intet er bestilt, før kunden selv godkender det skriftligt."
    if r.status == "failed":
        leads.create_task(db, ws.id, title=f"Send bestillingslink til {company.display_name} ({r.destination})",
                          created_by=None, due_at=now + timedelta(hours=FOLLOW_UP_HOURS))
        return "Det kunne ikke sendes lige nu. Sig, at en kollega sender det inden for et par timer."
    if r.outbox_event_id is not None:
        return "Linket er på vej på mail. Sig, at intet er bestilt, før kunden selv godkender det skriftligt."
    leads.create_task(db, ws.id, title=f"Bekræft adresse og send bestillingslink: {company.display_name} → {r.destination}",
                      created_by=None, due_at=now + timedelta(hours=FOLLOW_UP_HOURS))
    return ("Adressen står ikke i vores oplysninger, så en kollega bekræfter den og sender linket inden for to timer. "
            "Sig det til kunden – lov ikke, at det er sendt.")


def _frabedelse(db, ws, cc, args, pcid, now) -> str:
    from app.modules.sales import outbound

    outbound.block(db, kind="phone", value=cc.phone, reason=str(args.get("grund") or "Frabedt i opkald")[:300],
                   source="call", user_id=None)
    return "Registreret: vi kontakter ikke nummeret med salg igen. Tak for tiden og afslut samtalen."


def _follow_up(db, ws, cc, args, pcid, now) -> str:
    from app.modules.leads import service as leads

    company, _ = _company(db, cc)
    topic = str(args.get("emne") or "").strip()[:500] or "Opfølgning efter salgsopkald"
    leads.create_task(db, ws.id, title=f"Salg – {company.display_name}: {topic}"[:200], created_by=None,
                      due_at=now + timedelta(hours=FOLLOW_UP_HOURS))
    db.add(SalesOpenQuestion(company_id=company.id, question=topic))
    return "En kollega hos Dialogbot følger op inden for to timer. Sig det til kunden."


def _stop_recording(db, ws, cc, args, pcid, now) -> str:
    from app.models import SalesCallEvent

    db.add(SalesCallEvent(campaign_contact_id=cc.id, provider_call_id=pcid, event_type="recording_objection", payload={}))
    return "Registreret: optagelsen bliver ikke gemt og slettes hos telefonudbyderen efter samtalen. Sig det til kunden."


HANDLERS = {"stop_optagelse": _stop_recording, "hent_tilbud": _hent_tilbud, "ledige_moedetider": _ledige, "book_moede": _book,
            "opret_ordreudkast": _ordreudkast, "send_bestillingslink": _send, "registrer_frabedelse": _frabedelse,
            "bed_menneske_foelge_op": _follow_up}


def ensure_meeting_type(db: OrmSession, ws: Workspace) -> BookingType:
    """Seed hook: the sales workspace's "Intro-møde (30 min)" booking type."""
    bt = _meeting_type(db, ws)
    if bt is None:
        bt = BookingType(workspace_id=ws.id, name=f"{MEETING_TYPE} (30 min)", duration_minutes=30,
                         description="Gennemgang af Dialogbot med en kollega.", active=True)
        db.add(bt)
        db.flush()
    return bt

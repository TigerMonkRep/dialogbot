"""SMS confirmations through Dialogbot's Twilio account (the platform's main account acts on the workspace's
sub-account, so the customer never handles a Twilio login).

The assistant can only send *templates*: fixed Danish texts filled from the workspace's approved knowledge and
profile and from facts of the conversation (the caller's number, the booking it just made). It cannot write free
text into an SMS, so nothing unapproved ever reaches a customer's phone.

Sender: Denmark allows alphanumeric sender IDs without pre-registration, and long codes support two-way SMS
(twilio.com/en-us/guidelines/dk/sms, read 30/9 2026). The default sender is the business name (≤ 11 characters);
an SMS-capable number may be configured instead. Endpoint: POST /2010-04-01/Accounts/{sid}/Messages.json.
"""
from __future__ import annotations

import re
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from app.config import get_settings
from app.models import Booking, BusinessProfile, TelephonyAccount, Workspace
from app.modules.integrations.connectors.base import (
    ActionError,
    ActionRefused,
    ActionResult,
    ActionSpec,
    ConnectorSpec,
    RunContext,
    obj,
)

TEMPLATES = ("booking", "ring_tilbage", "aabningstider", "adresse", "kontakt")
SENDER_RE = re.compile(r"^[A-Za-z0-9 ]{1,11}$|^\+[1-9]\d{7,14}$")
E164 = re.compile(r"^\+[1-9]\d{7,14}$")
MAX_SMS_CHARS = 320


def default_sender(ws: Workspace) -> str:
    """The workspace name shortened to an alphanumeric sender (letters/digits, ≤ 11), else the platform default."""
    name = re.sub(r"[^A-Za-z0-9 ]", "", ws.name).strip()
    name = re.sub(r"\s+", " ", name)[:11].strip()
    return name or get_settings().sms_default_sender


def _opening_hours_text(db: OrmSession, ws_id: uuid.UUID) -> str:
    from app.modules.bookings.service import DAYS
    from app.modules.knowledge.service import active_knowledge

    da = {"mon": "man", "tue": "tir", "wed": "ons", "thu": "tor", "fri": "fre", "sat": "lør", "sun": "søn"}
    parts = []
    for item in active_knowledge(db, ws_id):
        if item["kind"] != "opening_hours":
            continue
        for row in (item["content"] or {}).get("weekly") or []:
            days = [d for d in DAYS if d in (row.get("days") or [])]
            if days and row.get("open") and row.get("close"):
                span = f"{da[days[0]]}–{da[days[-1]]}" if len(days) > 1 else da[days[0]]
                parts.append(f"{span} {row['open']}–{row['close']}")
    return ", ".join(parts)


def render(db: OrmSession, ws: Workspace, template: str, ctx: RunContext) -> str:
    """Only approved knowledge, profile fields and conversation facts go into the text."""
    profile = db.get(BusinessProfile, ws.id)
    if template == "booking":
        q = select(Booking).where(Booking.workspace_id == ws.id, Booking.status == "confirmed")
        if ctx.conversation_id:
            q = q.where(Booking.conversation_id == ctx.conversation_id)
        elif ctx.caller_phone:
            q = q.where(Booking.contact_phone == ctx.caller_phone)
        else:
            raise ActionRefused("Der er ingen booking i denne samtale at bekræfte", code="no_booking")
        b = db.scalar(q.order_by(Booking.created_at.desc()))
        if b is None:
            raise ActionRefused("Der er ingen booking i denne samtale at bekræfte", code="no_booking")
        from app.modules.bookings.service import label

        return f"Hej {b.contact_name or ''}".strip() + f". Din tid hos {ws.name}: {b.title.split(':')[0]} {label(b.starts_at, ctx.tz)}. Vh {ws.name}"
    if template == "ring_tilbage":
        return f"Tak for din henvendelse til {ws.name}. En medarbejder ringer tilbage på dette nummer. Vh {ws.name}"
    if template == "aabningstider":
        hours = _opening_hours_text(db, ws.id)
        if not hours:
            raise ActionRefused("Virksomheden har ingen godkendte åbningstider", code="no_opening_hours")
        return f"Åbningstider hos {ws.name}: {hours}. Vh {ws.name}"
    if template == "adresse":
        addr = " ".join(x for x in ((profile.address_line, profile.postal_code, profile.city) if profile else ()) if x)
        if not addr.strip():
            raise ActionRefused("Virksomhedens adresse er ikke udfyldt", code="no_address")
        return f"{ws.name} ligger på {addr}. Vh {ws.name}"
    if template == "kontakt":
        phone = (profile.phone if profile else "") or ""
        site = (profile.website_url if profile else "") or ""
        bits = ", ".join(x for x in (f"tlf. {phone}" if phone else "", site) if x)
        if not bits:
            raise ActionRefused("Virksomhedens kontaktoplysninger er ikke udfyldt", code="no_contact")
        return f"Kontakt {ws.name}: {bits}. Vh {ws.name}"
    raise ActionRefused("Ukendt skabelon", code="unknown_template")


def send(db: OrmSession, ws: Workspace, *, sender: str, to: str, body: str, simulated: bool) -> str:
    """Send through the workspace's Twilio sub-account (main credentials act on it), or the main account."""
    if simulated:
        from app.modules.integrations.connectors.fakes import fake_send_sms

        return fake_send_sms(sender=sender, to=to, body=body, workspace_id=str(ws.id))
    from app.modules.telephony.providers import ProviderError, providers

    pv = providers()
    if pv is None:
        raise ActionError("SMS er ikke sat op hos Dialogbot", code="sms_not_configured")
    twilio = pv[0]
    acct = db.scalar(select(TelephonyAccount).where(TelephonyAccount.workspace_id == ws.id,
                                                    TelephonyAccount.provider == "twilio"))
    sid = acct.external_id if acct is not None else twilio.account_sid
    try:
        out = twilio._req("POST", f"/Accounts/{sid}/Messages.json", data={"From": sender, "To": to, "Body": body[:MAX_SMS_CHARS]})
    except ProviderError as e:
        raise ActionError(f"SMS kunne ikke sendes: {e.message}", code="provider_rejected", retryable=e.retryable) from e
    return str(out.get("sid") or "")


class SmsAdapter:
    def __init__(self, db: OrmSession, workspace_id: uuid.UUID, config: dict, simulated: bool):
        self.db, self.simulated = db, simulated
        self.ws = db.get(Workspace, workspace_id)
        self.sender = str(config.get("sender") or default_sender(self.ws))

    def test_connection(self) -> dict:
        if not SENDER_RE.match(self.sender):
            raise ActionError("Afsendernavnet skal være 1–11 bogstaver/tal eller et nummer i formatet +45…", code="bad_sender")
        return {"sender": self.sender, "templates": list(TEMPLATES)}

    def run(self, action: str, data: dict, ctx: RunContext) -> ActionResult:
        if action != "send_sms_bekraeftelse":
            raise ActionRefused("Ukendt handling", code="unknown_action")
        to = str(data.get("til") or ctx.caller_phone or "").strip()
        if not E164.match(to):
            raise ActionRefused("Der er intet gyldigt mobilnummer at sende til. Spørg kunden om nummeret (8 cifre).",
                                code="no_recipient")
        text = render(self.db, self.ws, str(data["skabelon"]), ctx)
        sid = send(self.db, self.ws, sender=self.sender, to=to, body=text, simulated=self.simulated)
        return ActionResult({"til": to, "tekst": text, "besked": f"SMS sendt til {to}: \"{text}\""},
                            label=f"SMS sendt til {to}", provider_ref=sid or None, simulated=self.simulated)


def _unavailable() -> str | None:
    from app.modules.telephony.providers import providers

    s = get_settings()
    if s.connectors_provider == "fake":
        return None
    if providers() is None:
        return "SMS kræver, at Dialogbots telefoni er sat op (TELEPHONY_PROVIDER)."
    return None


SPEC = ConnectorSpec(
    key="twilio_sms", label="SMS-bekræftelser", category="messaging", auth_kind="builtin",
    description="Assistenten kan sende en SMS med en fast skabelon: bekræftelse af en booking, \"vi ringer tilbage\", "
                "åbningstider, adresse eller kontaktoplysninger. Kun godkendt viden og samtalens oplysninger kan indgå.",
    config_schema=obj({"sender": {"type": "string", "pattern": SENDER_RE.pattern, "maxLength": 16,
                                  "description": "Afsendernavn (højst 11 bogstaver/tal) eller et nummer"}}),
    actions=(ActionSpec(
        "send_sms_bekraeftelse", "SMS sendt",
        "Send kunden en SMS med en fast skabelon: 'booking' (bekræftelse af den tid, der lige er booket), 'ring_tilbage' "
        "(vi ringer tilbage), 'aabningstider', 'adresse' eller 'kontakt'. Brug den, når kunden beder om at få det på "
        "SMS, eller efter en booking, hvis kunden siger ja til en bekræftelse.",
        obj({"skabelon": {"type": "string", "enum": list(TEMPLATES)},
             "til": {"type": "string", "description": "Mobilnummer i formatet +45XXXXXXXX; udelad for at bruge kundens eget nummer"}},
            ["skabelon"]),
        obj({"til": {"type": "string"}, "tekst": {"type": "string"}, "besked": {"type": "string"}}),
    ),),
    unavailable_reason=_unavailable,
    adapter=lambda db, ws_id, secret, config, simulated: SmsAdapter(db, ws_id, config, simulated),
    docs_url="https://www.twilio.com/docs/messaging",
)


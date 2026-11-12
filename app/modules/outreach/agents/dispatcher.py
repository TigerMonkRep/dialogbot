"""DispatcherAndWebhookHandler – hands audited e-mails to the sending provider and takes opt-outs, replies and bounces
back in.

Providers: `resend` and `smtp` are implemented. `instantly` and `smartlead` are reserved names that fail closed (their
APIs have not been wired or verified) – selecting one never pretends to send.
Every e-mail carries a signed unsubscribe link in the footer plus List-Unsubscribe / List-Unsubscribe-Post headers
(RFC 8058 one-click). An opt-out is written to the suppression list at once and cancels everything still pending.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Protocol

import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from app.config import get_settings
from app.core.errors import NotImplementedYet
from app.models import OutreachLead, OutreachLog, OutreachMessage
from app.modules.outreach import localization, suppression
from app.modules.outreach.compliance import ComplianceEngine, LeadFacts, rate_limits

log = structlog.get_logger("dialogbot.outreach.dispatch")
API_PREFIX = "/api/v1"


# --------------------------------------------------------------------------- unsubscribe links

def _sig(email: str) -> str:
    key = (get_settings().secret_key or "").encode()
    return hmac.new(key, b"outreach-unsubscribe:" + email.encode(), hashlib.sha256).hexdigest()[:40]


def unsubscribe_token(email: str) -> str:
    e = suppression.norm(email)
    return base64.urlsafe_b64encode(e.encode()).decode().rstrip("=") + "." + _sig(e)


def email_from_token(token: str) -> str | None:
    try:
        raw, sig = token.split(".", 1)
        email = base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)).decode()
    except (ValueError, UnicodeDecodeError):
        return None
    return email if hmac.compare_digest(sig, _sig(email)) else None


def unsubscribe_url(email: str) -> str:
    return f"{get_settings().public_base_url.rstrip('/')}{API_PREFIX}/unsubscribe?token={unsubscribe_token(email)}"


# --------------------------------------------------------------------------- providers

@dataclass
class Outgoing:
    from_name: str
    from_email: str
    to_email: str
    subject: str
    text: str
    headers: dict[str, str] = field(default_factory=dict)
    idempotency_key: str = ""


class Provider(Protocol):
    name: str

    def send(self, mail: Outgoing) -> str: ...


class DryRunProvider:
    """Sends nothing. The rendered e-mail is kept on the instance (and in outreach_logs) for inspection."""

    name = "dry_run"

    def __init__(self):
        self.sent: list[Outgoing] = []

    def send(self, mail: Outgoing) -> str:
        self.sent.append(mail)
        return f"dry-{uuid.uuid4().hex[:12]}"


class ResendProvider:
    name = "resend"
    endpoint = "https://api.resend.com/emails"

    def send(self, mail: Outgoing) -> str:
        import httpx

        r = httpx.post(self.endpoint, timeout=15.0,
                       headers={"Authorization": f"Bearer {get_settings().outreach_resend_api_key}",
                                "Idempotency-Key": mail.idempotency_key},
                       json={"from": f"{mail.from_name} <{mail.from_email}>", "to": [mail.to_email],
                             "subject": mail.subject, "text": mail.text, "headers": mail.headers})
        if r.status_code >= 400:
            raise RuntimeError(f"resend {r.status_code}: {r.text[:200]}")
        return str(r.json().get("id") or "")


class SmtpProvider:
    name = "smtp"

    def send(self, mail: Outgoing) -> str:
        import smtplib
        from email.message import EmailMessage
        from email.utils import formataddr, make_msgid

        s = get_settings()
        m = EmailMessage()
        m["From"], m["To"], m["Subject"] = formataddr((mail.from_name, mail.from_email)), mail.to_email, mail.subject
        m["Message-ID"] = make_msgid(domain=mail.from_email.rsplit("@", 1)[-1])
        for k, v in mail.headers.items():
            m[k] = v
        m.set_content(mail.text)
        with smtplib.SMTP(s.outreach_smtp_host, s.outreach_smtp_port, timeout=20) as smtp:
            smtp.starttls()
            if s.outreach_smtp_username:
                smtp.login(s.outreach_smtp_username, s.outreach_smtp_password or "")
            smtp.send_message(m)
        return str(m["Message-ID"])


_provider_override: Provider | None = None


def set_provider_override(p: Provider | None) -> None:
    global _provider_override
    _provider_override = p


def get_provider() -> Provider:
    s = get_settings()
    if s.outreach_mode == "off":
        raise NotImplementedYet("Outreach is switched off (OUTREACH_MODE=off)", code="outreach_off")
    if s.outreach_mode == "dry_run":
        return DryRunProvider()          # a dry run can never reach a real provider, whatever else is configured
    if _provider_override is not None:
        return _provider_override
    if s.outreach_provider == "resend":
        return ResendProvider()
    if s.outreach_provider == "smtp":
        return SmtpProvider()
    raise NotImplementedYet(f"Sending provider '{s.outreach_provider}' is not implemented; use resend or smtp",
                            code="provider_not_implemented")


def render(msg: OutreachMessage) -> Outgoing:
    s = get_settings()
    url = unsubscribe_url(msg.to_email)
    text = f"{msg.body}\n\n{msg.footer}".replace(localization.UNSUBSCRIBE_PLACEHOLDER, url)
    return Outgoing(from_name=s.outreach_sender_name, from_email=msg.sender_inbox or "", to_email=msg.to_email,
                    subject=msg.subject, text=text, idempotency_key=f"outreach-{msg.id}",
                    headers={"List-Unsubscribe": f"<{url}>", "List-Unsubscribe-Post": "List-Unsubscribe=One-Click"})


# --------------------------------------------------------------------------- the handler

class DispatcherAndWebhookHandler:
    def __init__(self, db: OrmSession):
        self.db = db
        self.s = get_settings()

    def dispatch(self, *, limit: int = 50, today: date | None = None) -> dict:
        today = today or datetime.now(UTC).date()
        provider = get_provider()
        live = self.s.outreach_mode == "live"
        engine = ComplianceEngine(self.db)
        out = {"mode": self.s.outreach_mode, "provider": provider.name, "sent": 0, "cancelled": 0, "waiting": 0, "failed": 0}
        rows = self.db.scalars(select(OutreachMessage).where(
            OutreachMessage.status == "queued", OutreachMessage.send_on <= today)
            .order_by(OutreachMessage.created_at).limit(limit).with_for_update(skip_locked=True)).all()
        for msg in rows:
            lead = self.db.get(OutreachLead, msg.lead_id)
            # The gate again, at the last moment: an opt-out or a matrix change since the audit must win.
            decision = engine.evaluate(LeadFacts(
                company_name=lead.company_name, email=msg.to_email, country=lead.country, email_source=lead.email_source,
                email_source_url=lead.email_source_url, registration_number=lead.registration_number))
            if not decision.allowed or not msg.audit.get("passed"):
                msg.status = "cancelled"
                out["cancelled"] += 1
                self._log(lead, "cancelled", {"reasons": list(decision.reasons) or ["not audited"]})
                continue
            if live and lead.country not in self.s.outreach_demo_countries:
                out["waiting"] += 1   # the demo cannot ring this country yet: the CTA would be a dead end
                self._log(lead, "waiting_demo", {"country": lead.country})
                continue
            if not rate_limits.within_limits(self.db, msg.sender_inbox or "", msg.send_on or today):
                out["waiting"] += 1
                continue
            mail = render(msg)
            try:
                ref = provider.send(mail)
            except Exception as e:  # noqa: BLE001 - one failed send must not stop the batch
                msg.status = "failed"
                out["failed"] += 1
                self._log(lead, "failed", {"error": type(e).__name__, "message": str(e)[:200]})
                continue
            msg.provider, msg.provider_message_id, msg.sent_at = provider.name, ref, datetime.now(UTC)
            msg.status = "sent" if live else "dry_run"
            if live:
                lead.status = "sent"
            out["sent"] += 1
            self._log(lead, msg.status, {"provider": provider.name, "inbox": msg.sender_inbox,
                                         **({"rendered": mail.text, "headers": mail.headers} if not live else {})})
        self.db.flush()
        return out

    def _log(self, lead: OutreachLead, outcome: str, detail: dict) -> None:
        self.db.add(OutreachLog(lead_id=lead.id, kind="dispatch", outcome=outcome, detail=detail))

    # ----- inbound: opt-outs and provider events

    def unsubscribe(self, token: str, *, source: str) -> bool:
        email = email_from_token(token)
        if not email:
            return False
        suppression.add(self.db, email, "unsubscribe", source=source)
        return True

    def handle_event(self, event: str, email: str, *, source: str) -> str:
        """reply → the sequence stops. bounce / complaint / unsubscribe → suppressed for good, sequence stops."""
        email = suppression.norm(email)
        if not email:
            return "ignored"
        if event == "reply":
            n = suppression.halt(self.db, email, "replied")
            lead_id = self.db.scalar(select(OutreachLead.id).where(OutreachLead.email_normalized == email))
            self.db.add(OutreachLog(lead_id=lead_id, kind="webhook", outcome="reply", detail={"source": source, "cancelled_messages": n}))
            return "halted"
        if event in ("bounce", "complaint", "unsubscribe"):
            suppression.add(self.db, email, event, source=source)
            return "suppressed"
        return "ignored"


RESEND_EVENTS = {"email.bounced": "bounce", "email.complained": "complaint", "email.received": "reply"}


def normalize_resend(payload: dict) -> tuple[str, str] | None:
    event = RESEND_EVENTS.get(str(payload.get("type")))
    data = payload.get("data") or {}
    if not event:
        return None
    who = data.get("from") if event == "reply" else next(iter(data.get("to") or []), None)
    if isinstance(who, str) and "<" in who:
        who = who.split("<", 1)[1].rstrip("> ")
    return (event, who) if who else None

"""Email adapters: simulated (dev/test/staging) and Resend."""
from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.errors import NotImplementedYet
from app.models import EmailDelivery


@dataclass
class OutgoingEmail:
    to_email: str
    subject: str
    body_text: str
    workspace_id: uuid.UUID | None = None
    body_html: str | None = None
    # E07: a mail in a business's name to its customer shows the business as the sender's name (the address stays
    # Dialogbot's sending address) and carries List-Unsubscribe headers (RFC 2369/8058).
    from_name: str | None = None
    headers: dict[str, str] | None = None


def _from(mail: OutgoingEmail) -> str:
    from email.utils import formataddr, parseaddr

    s = get_settings()
    if not mail.from_name:
        return s.email_from
    return formataddr((mail.from_name, parseaddr(s.email_from)[1]))


def sender_domain() -> str:
    """The domain of EMAIL_FROM – the one the Resend key must be allowed to send from."""
    from email.utils import parseaddr

    return parseaddr(get_settings().email_from)[1].rpartition("@")[2].lower()


class EmailSendError(RuntimeError):
    """The mail provider refused a message. `permanent` = the same request will be refused again until someone
    changes the configuration (key or sender domain): the worker fails the job at once instead of retrying."""

    # Start of the stored error text of a refused key/sender domain (outbox_events.last_error): read by the
    # operations screen and /health/ready.
    REJECTED_MARKER = "EmailSendError: Resend afviste"

    def __init__(self, message: str, *, status_code: int, permanent: bool):
        super().__init__(message)
        self.status_code = status_code
        self.permanent = permanent


def _resend_error(status_code: int, body: str) -> EmailSendError:
    """401/403 = the key is invalid or may not send from the sender domain: permanent, with the domain named.
    Everything else (429, 5xx, validation) keeps the plain text and the normal retries."""
    if status_code in (401, 403):
        try:
            import json

            detail = str(json.loads(body).get("message") or "")[:200]
        except Exception:  # noqa: BLE001
            detail = body[:200]
        domain = sender_domain()
        what = ("nøglen i RESEND_API_KEY er ugyldig" if status_code == 401
                else f"nøglen i RESEND_API_KEY må ikke sende fra {domain}")
        return EmailSendError(
            f"Resend afviste afsenderdomænet {domain} ({status_code}): {what}. Tjek i Resend, at domænet er "
            f"verificeret, og at nøglen har adgang til det – og at EMAIL_FROM peger på det domæne. "
            f"Prøves ikke igen automatisk. Resend: {detail}", status_code=status_code, permanent=True)
    return EmailSendError(f"resend {status_code}: {body[:300]}", status_code=status_code, permanent=False)


def sender_problem(db: Session, *, hours: int = 24) -> dict | None:
    """Is the key/sender domain being refused right now? Yes when a mail job failed on a 401/403 within `hours` and
    nothing has been sent since. Returns {domain, count, since, detail} or None. Reads the database only (a
    send-only Resend key cannot ask Resend about its own domains)."""
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import func, select

    from app.models import OutboxEvent

    since = datetime.now(UTC) - timedelta(hours=hours)
    n, first, last = db.execute(
        select(func.count(), func.min(OutboxEvent.created_at), func.max(OutboxEvent.created_at))
        .where(OutboxEvent.status == "failed", OutboxEvent.created_at > since, OutboxEvent.event_type.like("email.%"),
               OutboxEvent.last_error.like(EmailSendError.REJECTED_MARKER + "%"))).one()
    if not n:
        return None
    sent_after = db.scalar(select(func.count()).select_from(EmailDelivery)
                           .where(EmailDelivery.status == "sent", EmailDelivery.created_at > last))
    if sent_after:
        return None
    detail = db.scalar(select(OutboxEvent.last_error)
                       .where(OutboxEvent.status == "failed", OutboxEvent.created_at == last,
                              OutboxEvent.last_error.like(EmailSendError.REJECTED_MARKER + "%")).limit(1)) or ""
    return {"domain": sender_domain(), "count": n, "since": first, "detail": detail.removeprefix("EmailSendError: ")}


class SimulatedEmailAdapter:
    name = "simulated"

    def deliver(self, db: Session, outbox_event_id: uuid.UUID, mail: OutgoingEmail) -> EmailDelivery:
        rec = EmailDelivery(
            outbox_event_id=outbox_event_id,
            workspace_id=mail.workspace_id,
            adapter=self.name,
            to_email=mail.to_email,
            subject=mail.subject,
            body_text=mail.body_text,
            status="simulated",
        )
        db.add(rec)
        return rec


class ResendEmailAdapter:
    """Sends through Resend's HTTP API. Records the provider message id.

    Status semantics: "sent" means Resend accepted the message. Delivery, bounce and
    complaint arrive later as signed webhooks (app/modules/webhooks) and are stored in
    `provider_status`. A refused key or sender domain (401/403) raises a
    permanent EmailSendError: the job fails at once and is retried by an operator after the configuration is fixed.
    """

    name = "resend"
    endpoint = "https://api.resend.com/emails"

    def deliver(self, db: Session, outbox_event_id: uuid.UUID, mail: OutgoingEmail) -> EmailDelivery:
        import httpx

        s = get_settings()
        r = httpx.post(self.endpoint, timeout=15.0,
                       headers={"Authorization": f"Bearer {s.resend_api_key}", "Idempotency-Key": str(outbox_event_id)},
                       json={"from": _from(mail), "to": [mail.to_email], "subject": mail.subject, "text": mail.body_text,
                             **({"html": mail.body_html} if mail.body_html else {}),
                             **({"headers": mail.headers} if mail.headers else {})})
        if r.status_code >= 400:
            raise _resend_error(r.status_code, r.text)
        rec = EmailDelivery(outbox_event_id=outbox_event_id, workspace_id=mail.workspace_id, adapter=self.name,
                            to_email=mail.to_email, subject=mail.subject, body_text=mail.body_text,
                            status="sent", provider_message_id=r.json().get("id"))
        db.add(rec)
        return rec


def get_email_adapter():
    s = get_settings()
    if s.email_adapter == "simulated":
        return SimulatedEmailAdapter()
    if s.email_adapter == "resend":
        return ResendEmailAdapter()
    raise NotImplementedYet("Ukendt e-mailadapter")

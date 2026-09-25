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
    `provider_status`. NOT externally verified yet: no Resend account/key exists.
    """

    name = "resend"
    endpoint = "https://api.resend.com/emails"

    def deliver(self, db: Session, outbox_event_id: uuid.UUID, mail: OutgoingEmail) -> EmailDelivery:
        import httpx

        s = get_settings()
        r = httpx.post(self.endpoint, timeout=15.0,
                       headers={"Authorization": f"Bearer {s.resend_api_key}", "Idempotency-Key": str(outbox_event_id)},
                       json={"from": s.email_from, "to": [mail.to_email], "subject": mail.subject, "text": mail.body_text})
        if r.status_code >= 400:
            raise RuntimeError(f"resend {r.status_code}: {r.text[:300]}")
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

"""Email adapters. Only the simulated adapter exists in this stage."""
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


def get_email_adapter():
    s = get_settings()
    if s.email_adapter == "simulated":
        return SimulatedEmailAdapter()
    raise NotImplementedYet("Ingen produktions-e-mailadapter er implementeret")

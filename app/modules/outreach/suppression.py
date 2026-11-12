"""The suppression list: one global list across all campaigns. An address or a whole domain on it is never e-mailed."""
from __future__ import annotations

from sqlalchemy import or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session as OrmSession

from app.models import OutreachLead, OutreachLog, OutreachMessage, OutreachSuppression

# Lead status a provider event or an opt-out moves the lead to.
_LEAD_STATUS = {"unsubscribe": "unsubscribed", "complaint": "unsubscribed", "objection": "unsubscribed",
                "manual": "unsubscribed", "bounce": "bounced"}


def norm(email: str) -> str:
    return (email or "").strip().lower()


def find(db: OrmSession, email: str) -> OutreachSuppression | None:
    e = norm(email)
    domain = e.rsplit("@", 1)[-1]
    return db.scalar(select(OutreachSuppression).where(or_(
        (OutreachSuppression.kind == "email") & (OutreachSuppression.value == e),
        (OutreachSuppression.kind == "domain") & (OutreachSuppression.value == domain))).limit(1))


def halt(db: OrmSession, email: str, lead_status: str) -> int:
    """Stop the sequence for this address: every message not yet sent is cancelled. Returns how many."""
    e = norm(email)
    n = db.execute(update(OutreachMessage).where(OutreachMessage.to_email == e,
                                                 OutreachMessage.status.in_(("draft", "queued", "deferred")))
                   .values(status="cancelled")).rowcount
    db.execute(update(OutreachLead).where(OutreachLead.email_normalized == e).values(status=lead_status))
    return n


def add(db: OrmSession, value: str, reason: str, *, source: str = "", kind: str = "email") -> None:
    """Suppress now (idempotent) and halt everything still pending for the address."""
    v = norm(value)
    db.execute(insert(OutreachSuppression).values(kind=kind, value=v, reason=reason, source=source[:40])
               .on_conflict_do_nothing(constraint="uq_outreach_suppression_value"))
    cancelled = halt(db, v, _LEAD_STATUS[reason]) if kind == "email" else 0
    lead_id = db.scalar(select(OutreachLead.id).where(OutreachLead.email_normalized == v)) if kind == "email" else None
    db.add(OutreachLog(lead_id=lead_id, kind="unsubscribe" if reason == "unsubscribe" else "webhook", outcome=reason,
                       detail={"source": source, "cancelled_messages": cancelled, "kind": kind}))

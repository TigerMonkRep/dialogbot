"""Offers, the order link and acceptance (phase 3).

An offer is created from the list prices in billing/prices.py – never free amounts – and versioned per company. Its
link carries a random token; only the SHA-256 is stored and a new link replaces the old one. "Sent" is not an order:
the customer opens /tilbud/<token>, logs in or signs up, and accepts. Acceptance creates (or reuses) the customer's
workspace, a reception agreement with the offer's snapshot (`agreements.create(offer=…)`) and sends them on to card
checkout. The company only counts as a paying customer at its first paid Stripe invoice (`on_invoice_paid`).

Sending: e-mail goes through the outbox (`sales.message`; the request is `sent` only when the e-mail adapter delivered
it), SMS through the sales workspace's SMS sender (`sent` only when the provider returned a message id). A destination
that does not match what we hold for the contact or company is never sent automatically.
"""
from __future__ import annotations

import hashlib
import re
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session as OrmSession

from app.config import get_settings
from app.core.audit import record_audit
from app.core.errors import ApiError, Conflict, Forbidden, NotFound, ValidationFailed
from app.core.outbox import enqueue
from app.models import (
    Membership,
    SalesCompany,
    SalesContact,
    SalesMessageRequest,
    SalesOffer,
    User,
    Workspace,
)
from app.modules.billing import prices

VALID_DAYS = 14
PACKAGE_TEXT = {"reception": "Dialogbot-receptionisten"}
SETUP_TEXT = {"diy": "gør-det-selv-opsætning, der er med i abonnementet",
              "specialist": f"specialist-opsætning til {prices.kr(prices.SPECIALIST_SETUP_NET_MINOR)} kr. én gang ekskl. moms"}
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _now() -> datetime:
    return datetime.now(UTC)


def _hash(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def link(raw: str) -> str:
    return f"{get_settings().frontend_base_url.rstrip('/')}/tilbud/{raw}"


def create(db: OrmSession, company: SalesCompany, *, setup_kind: str, contact_id: uuid.UUID | None,
           user_id: uuid.UUID | None) -> SalesOffer:
    if setup_kind not in SETUP_TEXT:
        raise ValidationFailed("Vælg gør-det-selv eller specialist-opsætning.", field_errors=[{"field": "setup_kind"}])
    if contact_id is not None:
        contact = db.get(SalesContact, contact_id)
        if contact is None or contact.company_id != company.id:
            raise ValidationFailed("Kontakten hører ikke til virksomheden.", field_errors=[{"field": "contact_id"}])
    from app.modules.sales.playbook import TERMS_VERSION

    last = db.scalar(select(func.max(SalesOffer.version)).where(SalesOffer.company_id == company.id))
    o = SalesOffer(company_id=company.id, contact_id=contact_id, version=(last or 0) + 1, package="reception",
                   monthly_net_minor=prices.SUBSCRIPTION_MONTHLY_NET_MINOR, setup_kind=setup_kind,
                   setup_net_minor=prices.SPECIALIST_SETUP_NET_MINOR if setup_kind == "specialist" else 0,
                   campaign_call_net_minor=prices.CAMPAIGN_CALL_NET_MINOR,
                   campaign_minute_net_minor=prices.CAMPAIGN_MINUTE_NET_MINOR,
                   inbound_included_minutes=prices.INBOUND_INCLUDED_MINUTES,
                   inbound_extra_minute_net_minor=prices.INBOUND_EXTRA_MINUTE_NET_MINOR,
                   terms_version=TERMS_VERSION, tax_basis_points=prices.TAX_BASIS_POINTS,
                   valid_until=_now() + timedelta(days=VALID_DAYS), status="draft", created_by=user_id)
    db.add(o)
    db.flush()
    record_audit(db, workspace_id=None, actor_user_id=user_id, action="sales.offer_created", object_type="sales_offer",
                 object_id=o.id, after={"company_id": str(company.id), "version": o.version, "setup_kind": setup_kind})
    return o


def refresh_status(o: SalesOffer, now: datetime | None = None) -> SalesOffer:
    if o.status in ("draft", "sent") and o.valid_until <= (now or _now()):
        o.status = "expired"
    return o


def _vat(net: int, bp: int) -> int:
    return (net * bp + 5000) // 10000


def amounts(o: SalesOffer) -> dict:
    return {"monthly_net_minor": o.monthly_net_minor, "monthly_vat_minor": _vat(o.monthly_net_minor, o.tax_basis_points),
            "setup_net_minor": o.setup_net_minor, "setup_vat_minor": _vat(o.setup_net_minor, o.tax_basis_points),
            "campaign_call_net_minor": o.campaign_call_net_minor,
            "campaign_minute_net_minor": o.campaign_minute_net_minor,
            "inbound_included_minutes": o.inbound_included_minutes,
            "inbound_extra_minute_net_minor": o.inbound_extra_minute_net_minor,
            "tax_basis_points": o.tax_basis_points}


def sentence(o: SalesOffer) -> str:
    """How Peter reads the offer aloud (amounts from the row, which came from prices.py)."""
    return (f"{PACKAGE_TEXT[o.package]} til {prices.kr(o.monthly_net_minor)} kroner om måneden ekskl. moms, med "
            f"{SETUP_TEXT[o.setup_kind]}. Udgående kampagneopkald koster {prices.kr(o.campaign_call_net_minor)} kr. pr. "
            f"opkald plus {prices.kr(o.campaign_minute_net_minor)} kr. pr. påbegyndt minut, og "
            f"{o.inbound_included_minutes} indgående minutter om måneden er med. Ingen binding.")


def out(db: OrmSession, o: SalesOffer) -> dict:
    refresh_status(o)
    reqs = db.scalars(select(SalesMessageRequest).where(SalesMessageRequest.offer_id == o.id)
                      .order_by(SalesMessageRequest.created_at.desc())).all()
    return {"id": str(o.id), "company_id": str(o.company_id), "contact_id": str(o.contact_id) if o.contact_id else None,
            "version": o.version, "package": o.package, "setup_kind": o.setup_kind, "status": o.status,
            "terms_version": o.terms_version, "valid_until": o.valid_until.isoformat(), **amounts(o),
            "sent_via": o.sent_via, "sent_to": o.sent_to, "sent_at": o.sent_at.isoformat() if o.sent_at else None,
            "accepted_at": o.accepted_at.isoformat() if o.accepted_at else None,
            "workspace_id": str(o.workspace_id) if o.workspace_id else None,
            "first_invoice_paid_at": o.first_invoice_paid_at.isoformat() if o.first_invoice_paid_at else None,
            "created_at": o.created_at.isoformat(), "messages": [message_out(r) for r in reqs]}


def message_out(r: SalesMessageRequest) -> dict:
    return {"id": str(r.id), "kind": r.kind, "channel": r.channel, "destination": r.destination, "status": r.status,
            "error": r.error, "requested_quote": r.requested_quote, "created_at": r.created_at.isoformat(),
            "sent_at": r.sent_at.isoformat() if r.sent_at else None}


# --------------------------------------------------------------------------- destinations and sending


def known_destinations(db: OrmSession, company: SalesCompany, contact: SalesContact | None) -> dict[str, set[str]]:
    """What we hold for this company: the only addresses a link may go to without an operator checking it."""
    from app.modules.sales.service import danish_number

    emails = {e.strip().lower() for e in (contact.email if contact else None, company.public_email) if e}
    phones = {p for p in (contact.phone_e164 if contact else None, company.main_phone_e164) if p}
    return {"email": emails, "sms": {p for p in phones if danish_number(p)}}


def normalise(channel: str, destination: str) -> str:
    from app.modules.sales.service import danish_number

    d = (destination or "").strip()
    if channel == "email":
        d = d.lower()
        if not EMAIL_RE.match(d):
            raise ValidationFailed("Ugyldig e-mailadresse.", field_errors=[{"field": "destination"}])
        return d
    if channel == "sms":
        e164 = danish_number(d)
        if not e164:
            raise ValidationFailed("Ugyldigt dansk mobilnummer.", field_errors=[{"field": "destination"}])
        return e164
    raise ValidationFailed("Vælg e-mail eller SMS.", field_errors=[{"field": "channel"}])


def request_message(db: OrmSession, o: SalesOffer, *, channel: str, destination: str, kind: str = "order_link",
                    quote: str = "", campaign_contact_id: uuid.UUID | None = None,
                    provider_call_id: str | None = None, operator_checked: bool = False) -> SalesMessageRequest:
    """Record the request and send it when the destination is one we hold (or an operator chose it). Otherwise the
    request waits as `requested` for an operator."""
    refresh_status(o)
    if o.status not in ("draft", "sent"):
        raise Conflict(f"Tilbuddet kan ikke sendes (status: {o.status}).", code="offer_not_sendable")
    company = db.get(SalesCompany, o.company_id)
    contact = db.get(SalesContact, o.contact_id) if o.contact_id else None
    dest = normalise(channel, destination)
    r = SalesMessageRequest(company_id=company.id, contact_id=contact.id if contact else None, offer_id=o.id,
                            campaign_contact_id=campaign_contact_id, provider_call_id=provider_call_id, kind=kind,
                            channel=channel, destination=dest, requested_quote=quote[:2000], status="requested")
    db.add(r)
    db.flush()
    if operator_checked or dest in known_destinations(db, company, contact)[channel]:
        deliver(db, o, r)
    return r


def _message_text(o: SalesOffer, kind: str, url: str) -> tuple[str, str]:
    company_name = PACKAGE_TEXT[o.package]
    if kind == "offer_summary":
        subject = "Oplæg fra Dialogbot"
        body = (f"Hej,\n\nHer er oplægget, vi talte om: {sentence(o)}\n\nSe hele tilbuddet og vilkårene her:\n{url}\n\n"
                f"Tilbuddet gælder til {o.valid_until:%d.%m.%Y}.")
    else:
        subject = "Din bestilling af Dialogbot"
        body = (f"Hej,\n\nHer er bestillingen af {company_name}, som vi talte om. Du kan se priser, moms og vilkår og "
                f"godkende det hele skriftligt her:\nSe og godkend: {url}\n\nIntet er bestilt, før du selv godkender. "
                f"Linket gælder til {o.valid_until:%d.%m.%Y}.")
    return subject, body


def deliver(db: OrmSession, o: SalesOffer, r: SalesMessageRequest) -> None:
    """Send now (SMS) or queue (e-mail). A new link replaces any earlier one for the offer."""
    raw = secrets.token_urlsafe(24)
    o.accept_token_hash = _hash(raw)
    url = link(raw)
    subject, body = _message_text(o, r.kind, url)
    if r.channel == "email":
        from app.modules.integrations import email_templates as tpl

        mail = tpl.from_plain(subject, body, footer_reason="Du får denne mail, fordi du bad om den i en samtale med Dialogbot.")
        ev = enqueue(db, event_type="sales.message", dedupe_key=f"sales_message:{r.id}",
                     payload={"request_id": str(r.id), "to_email": r.destination, "email": tpl.to_payload(mail)})
        r.outbox_event_id = ev.id
        return
    from app.modules.integrations.connectors import sms
    from app.modules.integrations.connectors.base import ActionError
    from app.modules.sales import service

    ws = service.sales_workspace(db)
    if ws is None:
        r.status, r.error = "failed", "SALES_WORKSPACE_ID er ikke sat – SMS sendes fra salgsarbejdsrummet."
        return
    text = f"Dialogbot: Her er bestillingen, vi talte om. Se og godkend: {url}"
    try:
        sms.send(db, ws, sender=sms.default_sender(ws), to=r.destination, body=text,
                 simulated=get_settings().connectors_provider == "fake")
    except (ActionError, ApiError) as e:
        r.status, r.error = "failed", str(getattr(e, "message", e))[:300]
        return
    mark_sent(o, r)


def mark_sent(o: SalesOffer, r: SalesMessageRequest) -> None:
    r.status, r.sent_at, r.error = "sent", _now(), None
    if o.status == "draft":
        o.status = "sent"
    o.sent_via, o.sent_to, o.sent_at = r.channel, r.destination, r.sent_at


def handle_message(db: OrmSession, ev) -> None:
    """Worker handler for `sales.message`: deliver the e-mail, then mark the request sent."""
    from app.models import EmailDelivery
    from app.modules.integrations import email_templates as tpl
    from app.worker.runner import _send_mail

    r = db.get(SalesMessageRequest, uuid.UUID(ev.payload["request_id"]))
    if r is None or r.status == "cancelled":
        return
    _send_mail(db, ev, tpl.from_payload(ev.payload))
    d = db.scalar(select(EmailDelivery).where(EmailDelivery.outbox_event_id == ev.id))
    if d is not None and r.status != "sent":
        o = db.get(SalesOffer, r.offer_id) if r.offer_id else None
        if o is not None:
            mark_sent(o, r)
        else:
            r.status, r.sent_at = "sent", _now()
        if d.status == "simulated":
            r.error = "Simuleret: EMAIL_ADAPTER=simulated – ingen rigtig mail er sendt."


# --------------------------------------------------------------------------- public page and acceptance


def by_token(db: OrmSession, raw: str) -> SalesOffer:
    o = db.scalar(select(SalesOffer).where(SalesOffer.accept_token_hash == _hash(raw or "")))
    if o is None:
        raise NotFound("Linket er ugyldigt eller erstattet af et nyere.")
    refresh_status(o)
    return o


def public_view(db: OrmSession, o: SalesOffer) -> dict:
    company = db.get(SalesCompany, o.company_id)
    return {"company": company.display_name, "package": PACKAGE_TEXT[o.package], "setup_kind": o.setup_kind,
            "setup_text": SETUP_TEXT[o.setup_kind], "status": o.status, "valid_until": o.valid_until.isoformat(),
            "terms_version": o.terms_version, "notice": "Ingen binding – abonnementet kan opsiges til udgangen af en måned.",
            **amounts(o)}


def accept(db: OrmSession, raw: str, user: User, *, workspace_id: uuid.UUID | None, workspace_name: str | None,
           request_id: str | None = None) -> dict:
    from app.modules.billing import agreements
    from app.modules.workspaces.service import create_workspace

    o = by_token(db, raw)
    if o.status == "accepted":
        raise Conflict("Tilbuddet er allerede accepteret.", code="offer_already_accepted")
    if o.status != "sent":
        raise Conflict("Tilbuddet er udløbet eller annulleret. Bed om et nyt.", code="offer_not_open")
    if workspace_id is not None:
        m = db.scalar(select(Membership).where(Membership.workspace_id == workspace_id, Membership.user_id == user.id))
        if m is None or m.role not in ("owner", "admin"):
            raise Forbidden("Du skal være ejer eller administrator af arbejdsrummet.", code="not_workspace_admin")
        ws = db.get(Workspace, workspace_id)
    else:
        company = db.get(SalesCompany, o.company_id)
        name = (workspace_name or company.display_name).strip()[:120]
        ws = create_workspace(db, user=user, name=name, product_intent="reception", request_id=request_id)
    a = agreements.create(db, ws.id, "A", user.id, offer=o)
    o.status, o.accepted_at, o.accepted_by, o.agreement_id, o.workspace_id = "accepted", _now(), user.id, a.id, ws.id
    record_audit(db, workspace_id=ws.id, actor_user_id=user.id, action="sales.offer_accepted", object_type="sales_offer",
                 object_id=o.id, after={"agreement_version": a.version, "setup_net_minor": o.setup_net_minor},
                 request_id=request_id)
    record_audit(db, workspace_id=ws.id, actor_user_id=user.id, action="agreement.created",
                 object_type="reception_agreement", object_id=a.id, after={"version": a.version, "model": a.model},
                 request_id=request_id)
    checkout_url = None
    from app.modules.billing import stripe

    if stripe.configured():
        checkout_url = stripe.card_checkout(db, ws, user.email)
    return {"workspace_id": str(ws.id), "agreement_version": a.version, "checkout_url": checkout_url,
            "next": checkout_url or "/app/konto"}


def on_invoice_paid(db: OrmSession, workspace_id: uuid.UUID) -> None:
    """First paid Stripe invoice of a workspace that came from a sales offer: the company is now a paying customer."""
    for o in db.scalars(select(SalesOffer).where(SalesOffer.workspace_id == workspace_id, SalesOffer.status == "accepted",
                                                 SalesOffer.first_invoice_paid_at.is_(None))):
        o.first_invoice_paid_at = _now()
        company = db.get(SalesCompany, o.company_id)
        if company is not None and company.existing_customer_workspace_id is None:
            company.existing_customer_workspace_id = workspace_id

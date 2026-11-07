"""Frozen response schemas of the public API v1.

These are the contract (docs/public-openapi.json). They are built from the ORM rows by the `*_out` functions below
and never expose the models themselves: no cost fields (`cost_usd_micros`, fees), no provider ids
(`provider_call_id`, calendar event ids), no recording URLs, no billing decisions. Phone numbers and e-mails are
masked unless the key carries `contacts:read`.

Changing a field here is a contract change: add fields freely, never rename or remove one inside v1.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class V1(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Page(V1, Generic[T]):
    items: list[T]
    next_cursor: str | None = Field(default=None, description="Send som ?cursor= for næste side; null = sidste side")


# --------------------------------------------------------------------------- masking

def mask_phone(phone: str | None, reveal: bool) -> str | None:
    if phone is None or reveal:
        return phone
    digits = "".join(ch for ch in phone if ch.isdigit())
    if len(digits) <= 4:
        return "•" * max(3, len(digits))
    country = phone[:3] if phone.startswith("+") and len(digits) > 8 else ""  # "+45"
    rest = digits[len(country) - 1:] if country else digits
    return f"{country}{'•' * (len(rest) - 2)}{rest[-2:]}"  # +45••••••50


def mask_email(email: str | None, reveal: bool) -> str | None:
    if email is None or reveal:
        return email
    local, _, domain = email.partition("@")
    return f"{local[:1]}•••@{domain}" if domain else "•••"


# --------------------------------------------------------------------------- me

class MeWorkspace(V1):
    id: uuid.UUID
    name: str
    kind: str = Field(description="business | personal")


class MeKey(V1):
    id: uuid.UUID
    name: str
    prefix: str
    last4: str
    created_at: datetime
    expires_at: datetime | None
    last_used_at: datetime | None


class Me(V1):
    workspace: MeWorkspace
    key: MeKey
    scopes: list[str]


# --------------------------------------------------------------------------- calls and conversations

class Call(V1):
    id: uuid.UUID
    direction: str = Field(description="inbound | outbound")
    from_number: str | None = Field(description="E.164; maskeret uden contacts:read")
    to_number: str | None
    started_at: datetime | None
    ended_at: datetime | None
    duration_seconds: int | None
    ended_reason: str | None
    outcome: str | None = Field(description="Udgående kampagneopkald: interested | callback | not_interested | opt_out | no_answer")
    summary: str
    conversation_id: uuid.UUID | None = Field(description="Samtalen med udskriften (conversations:read)")
    created_at: datetime


def call_out(c, reveal: bool) -> Call:
    return Call(id=c.id, direction=c.direction, from_number=mask_phone(c.from_number, reveal), to_number=c.to_number,
                started_at=c.started_at, ended_at=c.ended_at, duration_seconds=c.duration_seconds,
                ended_reason=c.ended_reason, outcome=c.outcome, summary=c.summary, conversation_id=c.conversation_id,
                created_at=c.created_at)


class Conversation(V1):
    id: uuid.UUID
    channel: str = Field(description="webchat | phone")
    status: str
    mode: str = Field(description="ai | staff")
    origin: str | None = Field(description="Webchat: siden; telefon: nummeret (maskeret uden contacts:read)")
    visitor_message_count: int
    created_at: datetime
    last_message_at: datetime


def conversation_out(c, reveal: bool) -> Conversation:
    origin = mask_phone(c.origin, reveal) if c.channel == "phone" else c.origin
    return Conversation(id=c.id, channel=c.channel, status=c.status, mode=c.mode, origin=origin,
                        visitor_message_count=c.visitor_message_count, created_at=c.created_at,
                        last_message_at=c.last_message_at)


class Message(V1):
    id: uuid.UUID
    role: str = Field(description="visitor | assistant | staff")
    text: str
    created_at: datetime


def message_out(m) -> Message:
    return Message(id=m.id, role=m.role, text=m.text, created_at=m.created_at)


# --------------------------------------------------------------------------- bookings

class BookingType(V1):
    id: uuid.UUID
    name: str
    duration_minutes: int
    description: str
    active: bool
    created_at: datetime


def booking_type_out(t) -> BookingType:
    return BookingType(id=t.id, name=t.name, duration_minutes=t.duration_minutes, description=t.description,
                       active=t.active, created_at=t.created_at)


class Booking(V1):
    id: uuid.UUID
    type_id: uuid.UUID | None
    title: str
    starts_at: datetime
    ends_at: datetime
    status: str = Field(description="confirmed | cancelled")
    source: str = Field(description="webchat | phone | manual")
    contact_name: str
    contact_phone: str | None
    contact_email: str | None
    note: str
    lead_id: uuid.UUID | None
    conversation_id: uuid.UUID | None
    created_at: datetime
    cancelled_at: datetime | None


def booking_out(b, reveal: bool) -> Booking:
    return Booking(id=b.id, type_id=b.type_id, title=b.title, starts_at=b.starts_at, ends_at=b.ends_at, status=b.status,
                   source=b.source, contact_name=b.contact_name, contact_phone=mask_phone(b.contact_phone, reveal),
                   contact_email=mask_email(b.contact_email, reveal), note=b.note, lead_id=b.lead_id,
                   conversation_id=b.conversation_id, created_at=b.created_at, cancelled_at=b.cancelled_at)


# --------------------------------------------------------------------------- leads

class Lead(V1):
    id: uuid.UUID
    source: str = Field(description="webchat | phone | manual | campaign")
    contact_name: str
    contact_email: str | None
    contact_phone: str | None
    need_summary: str
    callback_from: datetime | None
    callback_to: datetime | None
    qualification_status: str = Field(description="unqualified | qualified | disqualified")
    pipeline_status: str = Field(description="new | contacted | won | lost")
    conversation_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


def lead_out(x, reveal: bool) -> Lead:
    return Lead(id=x.id, source=x.source, contact_name=x.contact_name, contact_email=mask_email(x.contact_email, reveal),
                contact_phone=mask_phone(x.contact_phone, reveal), need_summary=x.need_summary,
                callback_from=x.callback_from, callback_to=x.callback_to, qualification_status=x.qualification_status,
                pipeline_status=x.pipeline_status, conversation_id=x.conversation_id, created_at=x.created_at,
                updated_at=x.updated_at)


# --------------------------------------------------------------------------- knowledge

class KnowledgeItem(V1):
    id: uuid.UUID = Field(description="Id på den godkendte version")
    item_id: uuid.UUID
    kind: str
    title: str
    content: dict[str, Any]
    version_no: int
    approved_at: datetime | None


def knowledge_out(item, version) -> KnowledgeItem:
    return KnowledgeItem(id=version.id, item_id=item.id, kind=item.kind, title=version.title, content=version.content,
                         version_no=version.version_no, approved_at=version.approved_at)


# --------------------------------------------------------------------------- campaigns

class Campaign(V1):
    id: uuid.UUID
    name: str
    status: str = Field(description="draft | running | paused | completed | stopped")
    call_days: list[str]
    call_from: str
    call_to: str
    is_test: bool
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


def campaign_out(c) -> Campaign:
    return Campaign(id=c.id, name=c.name, status=c.status, call_days=list(c.call_days or []), call_from=c.call_from,
                    call_to=c.call_to, is_test=c.is_test, created_at=c.created_at, started_at=c.started_at,
                    completed_at=c.completed_at)


class DoNotCallEntry(V1):
    id: uuid.UUID
    phone: str
    reason: str
    source: str = Field(description="manual | call | api")
    created_at: datetime


def dnc_out(r, reveal: bool) -> DoNotCallEntry:
    return DoNotCallEntry(id=r.id, phone=mask_phone(r.phone, reveal), reason=r.reason, source=r.source,
                          created_at=r.created_at)


class DoNotCallIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    phone: str = Field(min_length=6, max_length=40, description="E.164 eller dansk 8-cifret nummer")
    reason: str = Field(default="", max_length=300)


# --------------------------------------------------------------------------- reports

class ReportCounts(V1):
    started: int = 0
    visitor_messages: int = 0


class ReportLeads(V1):
    new: int = 0
    approved: int = 0
    rejected: int = 0


class ReportTasks(V1):
    created: int = 0
    completed: int = 0
    open_overdue_at_end: int = 0


class DailyReport(V1):
    date: date
    timezone: str
    generated_at: datetime
    conversations: ReportCounts
    leads: ReportLeads
    tasks: ReportTasks


def daily_report_out(r) -> DailyReport:
    d = r.data or {}
    conv, leads, tasks = d.get("conversations") or {}, d.get("leads") or {}, d.get("tasks") or {}
    return DailyReport(date=r.report_date, timezone=r.timezone, generated_at=r.generated_at,
                       conversations=ReportCounts(started=int(conv.get("started") or 0),
                                                  visitor_messages=int(conv.get("visitor_messages") or 0)),
                       leads=ReportLeads(new=int(leads.get("new") or 0), approved=int(leads.get("approved") or 0),
                                         rejected=int(leads.get("rejected") or 0)),
                       tasks=ReportTasks(created=int(tasks.get("created") or 0), completed=int(tasks.get("completed") or 0),
                                         open_overdue_at_end=int(tasks.get("open_overdue_at_end") or 0)))


# --------------------------------------------------------------------------- webhooks

class WebhookEndpoint(V1):
    id: uuid.UUID
    url: str
    description: str
    events: list[str]
    active: bool
    created_at: datetime
    last_delivery_at: datetime | None
    last_error: str | None
    failure_count: int
    disabled_at: datetime | None
    disabled_reason: str | None


class WebhookEndpointCreated(WebhookEndpoint):
    secret: str = Field(description="Signeringshemmelighed (whsec_…). Vises kun her.")


def webhook_out(w, secret: str | None = None) -> WebhookEndpoint:
    fields = dict(id=w.id, url=w.url, description=w.description, events=list(w.events or []), active=w.active,
                  created_at=w.created_at, last_delivery_at=w.last_delivery_at, last_error=w.last_error,
                  failure_count=w.failure_count, disabled_at=w.disabled_at, disabled_reason=w.disabled_reason)
    return WebhookEndpointCreated(**fields, secret=secret) if secret is not None else WebhookEndpoint(**fields)


class WebhookEndpointIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    url: str = Field(min_length=12, max_length=500, description="Offentlig https-adresse")
    events: list[str] = Field(min_length=1, max_length=20, description="Hændelsestyper, fx call.completed")
    description: str = Field(default="", max_length=200)


class WebhookEndpointPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    events: list[str] | None = Field(default=None, min_length=1, max_length=20)
    description: str | None = Field(default=None, max_length=200)
    active: bool | None = Field(default=None, description="true genaktiverer et endpoint, der blev slået fra efter fejl")


class WebhookDelivery(V1):
    id: uuid.UUID = Field(description="Leveringens id (outbox)")
    event_id: str
    type: str
    status: str = Field(description="queued | processing | done | failed")
    attempts: int
    max_attempts: int
    next_attempt_at: datetime | None
    last_error: str | None
    created_at: datetime
    processed_at: datetime | None

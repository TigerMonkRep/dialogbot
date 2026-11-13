"""HTTP surface of the cold outreach system.

Public (no login): `/unsubscribe` (the link and the one-click POST in every e-mail) and `/webhooks/events` (provider
events: reply, bounce, complaint). Operator-only: run a batch, read its report, export the manual call list, dispatch.
"""
from __future__ import annotations

import csv
import hmac
import io
import json
import re
import uuid

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse, PlainTextResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from app.config import get_settings
from app.core.auth import Principal
from app.core.errors import Unauthenticated, ValidationFailed
from app.db import get_db
from app.models import OutreachCallQueue
from app.modules.outreach import finder, readiness, suppression
from app.modules.outreach.agents.dispatcher import DispatcherAndWebhookHandler, normalize_resend
from app.modules.outreach.agents.sourcing import RawLead, read_csv
from app.modules.outreach.pipelines import batch as pipeline
from app.modules.voices.operator_router import operator
from app.modules.webhooks import resend

public_router = APIRouter(tags=["outreach"])
operator_router = APIRouter(prefix="/operator/outreach", tags=["outreach-operator"])

_DONE = ("<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width'>"
         "<title>Unsubscribed</title><body style='font:16px system-ui;max-width:32rem;margin:15vh auto;padding:0 1rem'>"
         "<h1>You're unsubscribed</h1><p>We won't e-mail this address again.</p><p>Dialogbot</p>")


def _unsubscribe(token: str, source: str, db: OrmSession) -> HTMLResponse:
    if not DispatcherAndWebhookHandler(db).unsubscribe(token, source=source):
        raise ValidationFailed("This unsubscribe link is not valid", code="invalid_token")
    db.commit()
    return HTMLResponse(_DONE)


@public_router.get("/unsubscribe", response_class=HTMLResponse)
def unsubscribe_link(token: str = Query(max_length=1000), db: OrmSession = Depends(get_db)):
    """The opt-out link in every footer. Takes effect at once and needs nothing from the reader – no login, no form,
    no confirmation step."""
    return _unsubscribe(token, "link", db)


@public_router.post("/unsubscribe", response_class=HTMLResponse)
def unsubscribe_one_click(token: str = Query(max_length=1000), db: OrmSession = Depends(get_db)):
    """One-click opt-out for mail clients (List-Unsubscribe-Post, RFC 8058)."""
    return _unsubscribe(token, "one_click", db)


class EventIn(BaseModel):
    event: str = Field(pattern="^(reply|bounce|complaint|unsubscribe)$")
    email: str = Field(min_length=3, max_length=320)


@public_router.post("/webhooks/events")
async def provider_events(request: Request, db: OrmSession = Depends(get_db)):
    """Events from the sending provider. Resend signs with Svix (RESEND_WEBHOOK_SECRET); any other sender posts
    `{"event": "reply|bounce|complaint|unsubscribe", "email": "…"}` with the header X-Outreach-Secret."""
    s = get_settings()
    body = await request.body()
    h = request.headers
    try:
        payload = json.loads(body)
    except ValueError as e:
        raise ValidationFailed("Invalid JSON") from e
    handler = DispatcherAndWebhookHandler(db)
    if h.get("svix-id"):
        if not s.resend_webhook_secret:
            raise resend.WebhookNotConfigured("RESEND_WEBHOOK_SECRET is not set")
        resend.verify_signature(s.resend_webhook_secret, h.get("svix-id"), h.get("svix-timestamp"), h.get("svix-signature"), body)
        ev = normalize_resend(payload if isinstance(payload, dict) else {})
        result = handler.handle_event(ev[0], ev[1], source="resend") if ev else "ignored"
    else:
        if not s.outreach_webhook_secret:
            raise resend.WebhookNotConfigured("OUTREACH_WEBHOOK_SECRET is not set")
        if not hmac.compare_digest(h.get("x-outreach-secret") or "", s.outreach_webhook_secret):
            raise Unauthenticated("Invalid webhook secret", code="invalid_signature")
        e = EventIn.model_validate(payload)
        result = handler.handle_event(e.event, e.email, source=s.outreach_provider)
    db.commit()
    return {"received": True, "result": result}


# --------------------------------------------------------------------------- operator

class LeadIn(BaseModel):
    company_name: str = Field(max_length=200)
    email: str = Field(max_length=320)
    country: str = Field(max_length=20)
    city: str | None = Field(default=None, max_length=120)
    niche: str | None = Field(default=None, max_length=80)
    website: str | None = Field(default=None, max_length=300)
    phone: str | None = Field(default=None, max_length=40)
    registration_number: str | None = Field(default=None, max_length=40)
    email_source: str = Field(default="unknown", max_length=20)
    email_source_url: str | None = Field(default=None, max_length=500)
    context: str | None = Field(default=None, max_length=20000)


class BatchIn(BaseModel):
    name: str | None = Field(default=None, max_length=40, pattern=r"^[A-Za-z0-9_.-]+$")
    leads: list[LeadIn] = Field(default_factory=list, max_length=50)
    csv: str | None = Field(default=None, max_length=500_000, description="Alternative to `leads`: CSV text with a header row")
    countries: list[str] | None = Field(default=None, max_length=20)
    research: bool = Field(default=True, description="False: only check and qualify the leads now; research, copy and "
                                                     "audit are then run with POST …/batches/{name}/process")


@operator_router.post("/batches", status_code=201)
def run_batch(body: BatchIn, _: Principal = Depends(operator), db: OrmSession = Depends(get_db)):
    """Check, research, write and audit up to 50 leads. Queues audited e-mails; sends nothing."""
    raws = [RawLead(**x.model_dump()) for x in body.leads] + (read_csv(body.csv) if body.csv else [])
    if not raws or len(raws) > 50:
        raise ValidationFailed("A batch holds 1–50 leads")
    name = body.name or f"batch-{uuid.uuid4().hex[:8]}"
    countries = {c.upper() for c in body.countries} if body.countries else None
    if body.research:
        return pipeline.run_batch(db, raws, batch=name, countries=countries)
    pipeline.ingest_batch(db, raws, batch=name, countries=countries)
    return pipeline.report(db, name)


@operator_router.post("/batches/{name}/process")
def process_batch(name: str, limit: int = Query(default=1, ge=1, le=10), _: Principal = Depends(operator),
                  db: OrmSession = Depends(get_db)):
    """Research, write and audit the next `limit` qualified leads of a batch. Call until `remaining` is 0."""
    return pipeline.process(db, name, limit=limit)


@operator_router.get("/overview")
def overview(_: Principal = Depends(operator), db: OrmSession = Depends(get_db)):
    """The admin tab's data: mode, the go-live to-do list, markets, categories, key figures and the batches. Answers
    also while outreach is switched off – the to-do list is what tells the operator how to switch it on."""
    return readiness.overview(db)


class TodoIn(BaseModel):
    done: bool


@operator_router.put("/todos/{key}")
def tick_todo(key: str, body: TodoIn, p: Principal = Depends(operator), db: OrmSession = Depends(get_db)):
    """Tick (or untick) one of the manual go-live points."""
    readiness.set_mark(db, key, body.done, p.user.id)
    db.commit()
    return {"key": key, "done": body.done}


class SearchIn(BaseModel):
    country: str = Field(min_length=2, max_length=2)
    city: str = Field(min_length=2, max_length=80)
    niche: str = Field(max_length=20)
    limit: int = Field(default=10, ge=1, le=20)


@operator_router.post("/search")
def search(body: SearchIn, _: Principal = Depends(operator)):
    """Find businesses in a city and category (Google Places) with the e-mail address each publishes on its own
    website. Stores nothing; the chosen candidates are posted to /batches."""
    pipeline.require_on()
    found = finder.search(country=body.country, city=body.city.strip(), niche=body.niche, limit=body.limit)
    return {"candidates": [finder.as_dict(c) for c in found]}


@operator_router.get("/batches/{name}")
def batch_report(name: str, _: Principal = Depends(operator), db: OrmSession = Depends(get_db)):
    pipeline.require_on()
    return pipeline.report(db, name)


@operator_router.post("/dispatch")
def dispatch(limit: int = Query(default=20, ge=1, le=200), _: Principal = Depends(operator), db: OrmSession = Depends(get_db)):
    """Hand queued, audited e-mails to the provider (dry_run: render only). Never runs on a schedule."""
    out = DispatcherAndWebhookHandler(db).dispatch(limit=limit)
    db.commit()
    return out


@operator_router.get("/call-queue.csv", response_class=PlainTextResponse)
def call_queue_csv(include_needs_review: bool = False, _: Principal = Depends(operator), db: OrmSession = Depends(get_db)):
    """The manual call list (Denmark). By default only companies the CVR register cleared."""
    pipeline.require_on()
    q = select(OutreachCallQueue).where(OutreachCallQueue.status == "open").order_by(OutreachCallQueue.created_at)
    if not include_needs_review:
        q = q.where(OutreachCallQueue.scrub_status == "cleared")
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["company_name", "phone", "cvr", "country", "scrub_status", "added"])
    for r in db.scalars(q):
        # a cell starting with = + - @ would run as a formula in a spreadsheet
        w.writerow([re.sub(r"^([=+\-@])", r"'\1", str(v or "")) for v in
                    (r.company_name, r.phone, r.registration_number, r.country, r.scrub_status, r.created_at.date())])
    return PlainTextResponse(buf.getvalue(), media_type="text/csv")


class SuppressIn(BaseModel):
    value: str = Field(min_length=3, max_length=320)
    kind: str = Field(default="email", pattern="^(email|domain)$")


@operator_router.post("/suppressions", status_code=201)
def suppress(body: SuppressIn, _: Principal = Depends(operator), db: OrmSession = Depends(get_db)):
    suppression.add(db, body.value, "manual", source="operator", kind=body.kind)
    db.commit()
    return {"suppressed": body.value.strip().lower()}

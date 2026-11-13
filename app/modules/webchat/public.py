"""Public webchat endpoints used by the embed script and the chat frame (no login).

    GET  /public/webchat/loader.js                       embed script (any site; does nothing unless allowed)
    GET  /public/webchat/{key}/status                    CORS for allowed origins only
    GET  /public/webchat/{key}/frame                     chat UI; CSP frame-ancestors = allowed origins
    GET  /public/webchat/assets/{frame.js|frame.css}
    POST /public/webchat/{key}/conversations             from the frame only (Origin = API origin)
    GET  /public/webchat/{key}/conversations/{id}/messages   X-Visitor-Token
    POST /public/webchat/{key}/conversations/{id}/messages   X-Visitor-Token
    POST /public/webchat/{key}/conversations/{id}/contact/code      X-Visitor-Token  (W04: SMS code to the number)
    POST /public/webchat/{key}/conversations/{id}/contact/verify    X-Visitor-Token
    POST /public/webchat/{key}/conversations/{id}/contact             X-Visitor-Token  (a phone needs a verified code)
"""
from __future__ import annotations

import html
import json
import uuid
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session as OrmSession

from app.core.errors import Forbidden, NotFound, ValidationFailed
from app.db import get_db
from app.modules.webchat import service

router = APIRouter(prefix="/public/webchat", tags=["webchat-public"])
STATIC = Path(__file__).parent / "static"
ASSETS = {"frame.js": "application/javascript; charset=utf-8", "frame.css": "text/css; charset=utf-8"}


@lru_cache
def _asset(name: str) -> str:
    return (STATIC / name).read_text(encoding="utf-8")


def _require_frame_origin(origin: str | None) -> None:
    """Writes are only accepted from our own chat frame (the browser sets Origin; page JS cannot)."""
    if origin != service.api_origin():
        raise Forbidden("Kun tilladt fra chatvinduet", code="origin_not_allowed")


@router.get("/loader.js")
def loader():
    return Response(_asset("loader.js"), media_type="application/javascript; charset=utf-8",
                    headers={"Cache-Control": "public, max-age=300", "X-Content-Type-Options": "nosniff"})


@router.get("/assets/{name}")
def asset(name: str):
    if name not in ASSETS:
        raise NotFound("Ukendt fil")
    return Response(_asset(name), media_type=ASSETS[name],
                    headers={"Cache-Control": "public, max-age=300", "X-Content-Type-Options": "nosniff"})


@router.get("/{key}/status")
def status(key: str, request: Request, db: OrmSession = Depends(get_db)):
    origin = request.headers.get("origin")
    try:
        s = service.by_key(db, key)
    except NotFound:
        return JSONResponse({"available": False}, headers={"Cache-Control": "no-store"})
    allowed = service.origin_allowed(s, origin)
    body = {"available": allowed and not service.unavailable_reasons(db, s)}
    headers = {"Cache-Control": "no-store", "Vary": "Origin"}
    if allowed:
        headers["Access-Control-Allow-Origin"] = origin  # type: ignore[assignment]
    return JSONResponse(body, headers=headers)


def _csp(ancestors: list[str]) -> str:
    fa = " ".join(ancestors) if ancestors else "'none'"
    return ("default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; "
            f"frame-ancestors {fa}; base-uri 'none'; form-action 'none'")


@router.get("/{key}/frame", response_class=HTMLResponse)
def frame(key: str, request: Request, db: OrmSession = Depends(get_db)):
    s = service.by_key(db, key)
    ref = request.headers.get("referer")
    host_origin = None
    if ref:
        u = urlsplit(ref)
        host_origin = f"{u.scheme}://{u.netloc}" if u.scheme and u.netloc else None
    # Evidence for the "widget installed" check: a real browser iframe on an allowed origin.
    if request.headers.get("sec-fetch-dest") == "iframe" and service.origin_allowed(s, host_origin):
        service.record_seen(db, s, host_origin)  # type: ignore[arg-type]
    available = not service.unavailable_reasons(db, s)
    cfg = {"key": s.widget_key, "base": "/api/v1/public/webchat", "available": available,
           "greeting": service.greeting_text(db, s), "unavailable": service.UNAVAILABLE_TEXT,
           "maxChars": service.MAX_MESSAGE_CHARS, "hostOrigin": host_origin if service.origin_allowed(s, host_origin) else None}
    page = f"""<!doctype html>
<html lang="da"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex"><title>Chat</title>
<link rel="stylesheet" href="/api/v1/public/webchat/assets/frame.css"></head>
<body><div id="app" data-config="{html.escape(json.dumps(cfg), quote=True)}"></div>
<script src="/api/v1/public/webchat/assets/frame.js"></script></body></html>"""
    return HTMLResponse(page, headers={"Content-Security-Policy": _csp(s.allowed_origins), "Cache-Control": "no-store",
                                       "Referrer-Policy": "no-referrer", "X-Content-Type-Options": "nosniff"})


class StartIn(BaseModel):
    host_origin: str | None = Field(default=None, max_length=200)


@router.post("/{key}/conversations", status_code=201)
def start(key: str, body: StartIn, origin: str | None = Header(default=None), db: OrmSession = Depends(get_db)):
    _require_frame_origin(origin)
    s = service.by_key(db, key)
    conv, token = service.start_conversation(db, s, body.host_origin)
    return {"conversation_id": str(conv.id), "visitor_token": token, "greeting": service.greeting_text(db, s)}


class MessageIn(BaseModel):
    text: str = Field(min_length=1, max_length=service.MAX_MESSAGE_CHARS)


@router.get("/{key}/conversations/{conversation_id}/messages")
def history(key: str, conversation_id: uuid.UUID, x_visitor_token: str | None = Header(default=None),
            db: OrmSession = Depends(get_db)):
    s = service.by_key(db, key)
    conv = service.visitor_conversation(db, s, conversation_id, x_visitor_token)
    return {"messages": [service.message_out(m) for m in service.messages_of(db, conv)],
            "remaining_messages": service.MAX_VISITOR_MESSAGES - conv.visitor_message_count}


@router.post("/{key}/conversations/{conversation_id}/messages")
def send(key: str, conversation_id: uuid.UUID, body: MessageIn, origin: str | None = Header(default=None),
         x_visitor_token: str | None = Header(default=None), db: OrmSession = Depends(get_db)):
    _require_frame_origin(origin)
    s = service.by_key(db, key)
    conv = service.visitor_conversation(db, s, conversation_id, x_visitor_token)
    return service.post_visitor_message(db, s, conv, body.text)


class ContactIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=40, pattern=r"^[0-9+ ()-]{6,40}$")
    note: str = Field(default="", max_length=1000)
    window: str | None = Field(default=None, max_length=20)  # key from /callback-windows
    consent: bool


class WebchatPhoneCodeIn(BaseModel):
    phone: str = Field(min_length=6, max_length=40, pattern=r"^[0-9+ ()-]{6,40}$")


@router.post("/{key}/conversations/{conversation_id}/contact/code", status_code=202)
def phone_code(key: str, conversation_id: uuid.UUID, body: WebchatPhoneCodeIn, request: Request,
               origin: str | None = Header(default=None), x_visitor_token: str | None = Header(default=None),
               db: OrmSession = Depends(get_db)):
    """W04 step 1: a 6-digit code by SMS (the business's own text and sender) to the number the visitor typed in «Bliv
    kontaktet». 10 minutes, 5 attempts, resend after 30 s (409 `too_soon` + `retry_after`); 429 `sms_rate_limited`
    per number (all public doors), per client IP and per business."""
    from app.models import Workspace
    from app.modules.customer import service as customer
    from app.modules.privat.lookup_limits import client_ip

    _require_frame_origin(origin)
    s = service.by_key(db, key)
    conv = service.visitor_conversation(db, s, conversation_id, x_visitor_token)
    service._require_available(db, s)
    phone = customer.normalize(body.phone)
    out = customer.send_code(db, db.get(Workspace, s.workspace_id), purpose="webchat_phone", phone=phone,
                             ip=client_ip(request), conversation=conv)
    db.commit()
    return out


class WebchatPhoneVerifyIn(BaseModel):
    verification_id: str = Field(min_length=1, max_length=64)
    code: str = Field(min_length=1, max_length=12)


@router.post("/{key}/conversations/{conversation_id}/contact/verify")
def phone_verify(key: str, conversation_id: uuid.UUID, body: WebchatPhoneVerifyIn, origin: str | None = Header(default=None),
                 x_visitor_token: str | None = Header(default=None), db: OrmSession = Depends(get_db)):
    """W04 step 2: the code. 422 `code_invalid` + `attempts_left`; 409 `too_many_attempts` after 5; 409 `code_expired`
    (also for a code of another conversation or purpose)."""
    from app.modules.customer import service as customer

    _require_frame_origin(origin)
    s = service.by_key(db, key)
    conv = service.visitor_conversation(db, s, conversation_id, x_visitor_token)
    try:
        v = customer.check_code(db, purpose="webchat_phone", verification_id=body.verification_id, code=body.code,
                                conversation=conv)
    except ValidationFailed:
        db.commit()  # the attempt counts even though the request fails
        raise
    db.commit()
    return {"status": "verified", "phone_display": customer.masked(v.phone)}


@router.post("/{key}/conversations/{conversation_id}/contact")
def contact(key: str, conversation_id: uuid.UUID, body: ContactIn, origin: str | None = Header(default=None),
            x_visitor_token: str | None = Header(default=None), db: OrmSession = Depends(get_db)):
    """"Bliv kontaktet": the visitor leaves contact details; creates the conversation's lead and a follow-up task.
    A phone number is only accepted after the visitor proved it with the SMS code in this conversation (W04; 422
    `verification_required`). Returns `manage_url`: the customer's secure link to cancel the call back and set their
    preferences (W09)."""
    _require_frame_origin(origin)
    s = service.by_key(db, key)
    conv = service.visitor_conversation(db, s, conversation_id, x_visitor_token)
    if not body.consent:
        raise ValidationFailed("Sæt flueben for at give os lov til at kontakte dig", field_errors=[{"field": "consent"}])
    if not body.email and not body.phone:
        raise ValidationFailed("Angiv e-mail eller telefonnummer", field_errors=[{"field": "email"}, {"field": "phone"}])
    from app.modules.customer import service as customer
    from app.modules.leads import callback
    from app.modules.leads.service import create_task, visitor_contact
    from app.modules.reports.service import tz_of

    verified_at = None
    if body.phone:
        verified_at = customer.verified_phone(db, conv, customer.normalize(body.phone))
        if verified_at is None:
            raise ValidationFailed("Bekræft dit telefonnummer med koden fra SMS'en først", code="verification_required",
                                   field_errors=[{"field": "phone"}])

    window = None
    if body.window:
        if not body.phone:
            raise ValidationFailed("Angiv et telefonnummer, hvis du vil ringes op", field_errors=[{"field": "phone"}])
        try:
            window = callback.resolve(body.window, tz_of(db, s.workspace_id))
        except ValueError as e:
            raise ValidationFailed("Tidsrummet er ikke længere muligt – vælg et andet", field_errors=[{"field": "window"}]) from e
    lead = visitor_contact(db, conv, name=body.name, email=str(body.email) if body.email else None, phone=body.phone,
                           note=body.note, window=window)
    if verified_at is not None:
        lead.phone_verified_at = verified_at
    if lead.callback_cancelled_at is not None:  # a new request after the customer cancelled: a new call task
        lead.callback_cancelled_at = None
        create_task(db, conv.workspace_id, title=f"Ring {body.name.strip() or 'kunden'} op" + (f" – {window[2]}" if window else ""),
                    created_by=None, lead=lead, due_at=window[0] if window else None)
    url = customer.issue_link(db, purpose="callback", ws_id=conv.workspace_id, lead=lead)
    db.commit()
    return {"received": True, "manage_url": url}


@router.get("/{key}/callback-windows")
def callback_windows(key: str, db: OrmSession = Depends(get_db)):
    """Time windows the visitor can choose for a call back, in the business's local time."""
    from app.modules.leads import callback
    from app.modules.reports.service import tz_of

    s = service.by_key(db, key)
    return {"timezone": tz_of(db, s.workspace_id), "options": callback.options(tz_of(db, s.workspace_id))}

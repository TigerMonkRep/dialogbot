"""Public webchat endpoints used by the embed script and the chat frame (no login).

    GET  /public/webchat/loader.js                       embed script (any site; does nothing unless allowed)
    GET  /public/webchat/{key}/status                    CORS for allowed origins only
    GET  /public/webchat/{key}/frame                     chat UI; CSP frame-ancestors = allowed origins
    GET  /public/webchat/assets/{frame.js|frame.css}
    POST /public/webchat/{key}/conversations             from the frame only (Origin = API origin)
    GET  /public/webchat/{key}/conversations/{id}/messages   X-Visitor-Token
    POST /public/webchat/{key}/conversations/{id}/messages   X-Visitor-Token
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


@router.post("/{key}/conversations/{conversation_id}/contact")
def contact(key: str, conversation_id: uuid.UUID, body: ContactIn, origin: str | None = Header(default=None),
            x_visitor_token: str | None = Header(default=None), db: OrmSession = Depends(get_db)):
    """"Bliv kontaktet": the visitor leaves contact details; creates the conversation's lead and a follow-up task."""
    _require_frame_origin(origin)
    s = service.by_key(db, key)
    conv = service.visitor_conversation(db, s, conversation_id, x_visitor_token)
    if not body.consent:
        raise ValidationFailed("Sæt flueben for at give os lov til at kontakte dig", field_errors=[{"field": "consent"}])
    if not body.email and not body.phone:
        raise ValidationFailed("Angiv e-mail eller telefonnummer", field_errors=[{"field": "email"}, {"field": "phone"}])
    from app.modules.leads import callback
    from app.modules.leads.service import visitor_contact
    from app.modules.reports.service import tz_of

    window = None
    if body.window:
        if not body.phone:
            raise ValidationFailed("Angiv et telefonnummer, hvis du vil ringes op", field_errors=[{"field": "phone"}])
        try:
            window = callback.resolve(body.window, tz_of(db, s.workspace_id))
        except ValueError as e:
            raise ValidationFailed("Tidsrummet er ikke længere muligt – vælg et andet", field_errors=[{"field": "window"}]) from e
    visitor_contact(db, conv, name=body.name, email=str(body.email) if body.email else None, phone=body.phone,
                    note=body.note, window=window)
    db.commit()
    return {"received": True}


@router.get("/{key}/callback-windows")
def callback_windows(key: str, db: OrmSession = Depends(get_db)):
    """Time windows the visitor can choose for a call back, in the business's local time."""
    from app.modules.leads import callback
    from app.modules.reports.service import tz_of

    s = service.by_key(db, key)
    return {"timezone": tz_of(db, s.workspace_id), "options": callback.options(tz_of(db, s.workspace_id))}

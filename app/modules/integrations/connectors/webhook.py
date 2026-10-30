"""Outgoing webhooks: a generic signed webhook, and the same thing labelled for Zapier and Make.

The customer pastes the URL their Zapier "Catch Hook" / Make "Custom webhook" (or their own endpoint) gives them.
Dialogbot posts one JSON document per event and signs it (`X-Dialogbot-Signature: t=<unix>,v1=<hex hmac-sha256>`
over `<t>.<body>` with the connection's secret). Delivery goes through the outbox worker, so a receiver that is
down gets retries with backoff; after the last attempt the connection shows the error.

Events: lead.created, booking.created, booking.cancelled, action.completed, conversation.ended, test.ping.
Payload shape is flat and Zapier/Make-friendly: {"event", "id", "occurred_at", "workspace_id", "data": {...}}.

The URL must be https on the standard port and resolve to public addresses only (app/core/safe_fetch rules, in every
environment; ALLOW_PRIVATE_FETCH lets local tests reach an IP literal on this machine). Delivery goes through
safe_fetch.send: the host is resolved and checked again at send time and the connection is pinned to that address,
and redirects are not followed, so a DNS answer that changes after the connect-time check cannot reach an internal
address.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import time
from urllib.parse import urlparse

from app.modules.integrations.connectors.base import ActionError, ActionResult, ConnectorSpec, RunContext, obj

EVENTS = ("lead.created", "booking.created", "booking.cancelled", "action.completed", "conversation.ended", "test.ping")
SIGNATURE_HEADER = "X-Dialogbot-Signature"
MAX_BODY = 200_000


def url_allowed(url: str) -> bool:
    """Connect-time check. Delivery checks again and pins the address (deliver → safe_fetch.send)."""
    from app.core import safe_fetch

    if urlparse(url).scheme != "https":
        return False
    try:
        safe_fetch.resolve_checked(safe_fetch.check_url(url)[0])
    except (safe_fetch.FetchBlocked, safe_fetch.FetchFailed):
        return False
    return True


def new_secret() -> str:
    return "whsec_" + secrets.token_urlsafe(32)


def sign(secret: str, body: bytes, ts: int | None = None) -> str:
    ts = ts or int(time.time())
    mac = hmac.new(secret.encode(), f"{ts}.".encode() + body, hashlib.sha256).hexdigest()
    return f"t={ts},v1={mac}"


def verify(secret: str, body: bytes, header: str, *, tolerance_seconds: int = 300, now: int | None = None) -> bool:
    """For receivers (and our tests): constant-time check of the signature header."""
    parts = dict(p.split("=", 1) for p in header.split(",") if "=" in p)
    try:
        ts = int(parts.get("t", ""))
    except ValueError:
        return False
    if abs((now or int(time.time())) - ts) > tolerance_seconds:
        return False
    expected = hmac.new(secret.encode(), f"{ts}.".encode() + body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, parts.get("v1", ""))


def deliver(*, url: str, secret: str, body: bytes, simulated: bool) -> int:
    """POST one signed payload. Raises ActionError (retryable for 5xx/429/network) so the worker retries."""
    headers = {"content-type": "application/json", "user-agent": "Dialogbot-Webhook/1.0",
               SIGNATURE_HEADER: sign(secret, body)}
    if simulated:
        from app.modules.integrations.connectors.fakes import fake_deliver_webhook

        return fake_deliver_webhook(url=url, body=body, headers=headers)
    from app.core import safe_fetch

    if urlparse(url).scheme != "https":
        raise ActionError("Webhook-adressen er ikke tilladt (skal være en offentlig https-adresse)", code="url_not_allowed")
    try:
        r = safe_fetch.send("POST", url, content=body, headers=headers, timeout=10.0)
    except safe_fetch.FetchBlocked as e:
        raise ActionError("Webhook-adressen er ikke tilladt (skal være en offentlig https-adresse)",
                          code="url_not_allowed") from e
    except safe_fetch.FetchFailed as e:
        if e.reason == "timeout":
            raise ActionError("Modtageren svarede ikke i tide", code="provider_timeout", retryable=True) from e
        raise ActionError("Modtageren kunne ikke nås", code="provider_unavailable", retryable=True) from e
    if r.status == 410:
        raise ActionError("Modtageren har afmeldt webhooken (410)", code="gone")
    if r.status >= 400:
        raise ActionError(f"Modtageren afviste ({r.status})", code="provider_rejected",
                          retryable=r.status == 429 or r.status >= 500)
    return r.status


def payload(event: str, event_id: str, workspace_id: str, occurred_at: str, data: dict) -> bytes:
    doc = {"event": event, "id": event_id, "occurred_at": occurred_at, "workspace_id": workspace_id, "data": data}
    body = json.dumps(doc, ensure_ascii=False, default=str).encode()
    if len(body) > MAX_BODY:
        doc["data"] = {"truncated": True}
        body = json.dumps(doc, ensure_ascii=False).encode()
    return body


class WebhookAdapter:
    """Webhook sinks have no in-call actions; the only action is a test event a person triggers from the UI."""

    def __init__(self, secret: dict | None, config: dict, simulated: bool):
        self._secret = (secret or {}).get("signing_secret", "")
        self.url = str(config.get("url") or "")
        self.simulated = simulated

    def test_connection(self) -> dict:
        body = payload("test.ping", "test", "", "", {"besked": "Hej fra Dialogbot"})
        status = deliver(url=self.url, secret=self._secret, body=body, simulated=self.simulated)
        return {"http_status": status, "url": self.url}

    def run(self, action: str, data: dict, ctx: RunContext) -> ActionResult:
        raise ActionError("Webhook-connectoren udfører ingen handlinger i samtaler", code="no_actions")


CONFIG_SCHEMA = obj({"url": {"type": "string", "minLength": 12, "maxLength": 500, "format": "uri",
                             "description": "Adressen Dialogbot sender hændelser til"}}, ["url"])


def _spec(key: str, label: str, description: str, docs_url: str) -> ConnectorSpec:
    return ConnectorSpec(key=key, label=label, description=description, category="automation", auth_kind="secret",
                         events=EVENTS, config_schema=CONFIG_SCHEMA, secret_fields=(),
                         adapter=lambda db, ws_id, secret, config, simulated: WebhookAdapter(secret, config, simulated),
                         docs_url=docs_url)


WEBHOOK = _spec("webhook", "Webhook (eget system)",
                "Send hændelser (ny henvendelse, booking, udført handling, afsluttet samtale) som signeret JSON til jeres eget "
                "system. Signaturen kan tjekkes med den hemmelighed, I får ved forbindelsen.",
                "https://developer.mozilla.org/docs/Glossary/Webhook")
ZAPIER = _spec("zapier", "Zapier",
               "Indsæt adressen fra et \"Catch Hook\"-trin i Zapier, så hændelser fra Dialogbot kan starte jeres Zaps – fx "
               "oprette kunden i jeres CRM eller regnskab.",
               "https://help.zapier.com/hc/en-us/articles/8496288690317-Trigger-Zaps-from-webhooks")
MAKE = _spec("make", "Make",
             "Indsæt adressen fra et \"Custom webhook\"-modul i Make, så hændelser fra Dialogbot kan starte jeres scenarier.",
             "https://www.make.com/en/help/tools/webhooks")

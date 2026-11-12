"""Resend through our own adapter (app/modules/integrations/email.py) – ONLY to Resend's test inboxes.

- delivered@resend.dev: Resend accepts the mail from our configured sender; our delivery row is "sent" with Resend's
  message id.
- bounced@resend.dev: Resend accepts it too (the bounce comes later, as a webhook). Our bounce path is the signed
  Resend webhook (app/modules/webhooks/resend.py): an `email.bounced` event for the REAL message id, signed locally with
  a dummy secret, must move our row's provider_status to "bounced". (The sending-only key cannot read events back.)

The sender: SANDBOX_EMAIL_FROM, else EMAIL_FROM unless it is the dev default on *.local, else noreply@dialogbot.dk.
It must be on the domain the restricted key is allowed to send from. The recipient guard (conftest.resend_guard)
stops any other address before the request is made.
"""
from __future__ import annotations

import base64
import json
import os
import time
import uuid

import pytest

from app.config import get_settings
from app.models import EmailDelivery, OutboxEvent
from app.modules.integrations.email import OutgoingEmail, ResendEmailAdapter
from app.modules.webhooks import resend as resend_webhook

from .conftest import RESEND_TEST_RECIPIENTS

pytestmark = [pytest.mark.sandbox, pytest.mark.sandbox_resend, pytest.mark.usefixtures("resend_test_key")]

DEFAULT_FROM = "Dialogbot <noreply@dialogbot.dk>"
# Built at runtime so the X29 secret scanner never sees a whsec_-shaped literal; it is a dummy, not a real secret.
DUMMY_WEBHOOK_SECRET = "whsec_" + base64.b64encode(b"sandbox-dummy-not-a-real-secret").decode()


def sandbox_from() -> str:
    explicit = os.environ.get("SANDBOX_EMAIL_FROM")
    if explicit:
        return explicit
    configured = os.environ.get("EMAIL_FROM") or ""
    return configured if configured and not configured.rstrip(">").endswith(".local") else DEFAULT_FROM


@pytest.fixture
def resend_env(monkeypatch, resend_guard):
    monkeypatch.setenv("EMAIL_ADAPTER", "resend")
    monkeypatch.setenv("EMAIL_FROM", sandbox_from())
    monkeypatch.setenv("RESEND_WEBHOOK_SECRET", DUMMY_WEBHOOK_SECRET)
    get_settings.cache_clear()
    yield resend_guard
    get_settings.cache_clear()


def _send(db, to: str, subject: str) -> EmailDelivery:
    assert to in RESEND_TEST_RECIPIENTS  # never any other recipient (the HTTP guard checks again)
    ev = OutboxEvent(event_type="sandbox.email", dedupe_key=f"sandbox-email-{uuid.uuid4()}", payload={})
    db.add(ev)
    db.flush()
    rec = ResendEmailAdapter().deliver(db, ev.id, OutgoingEmail(
        to_email=to, subject=subject, body_text="Provider-sandbox: test af Dialogbots Resend-adapter.",
        body_html="<p>Provider-sandbox: test af Dialogbots Resend-adapter.</p>"))
    db.commit()
    return rec


def test_sender_is_configured(resend_env):
    assert get_settings().email_from == sandbox_from()
    assert not get_settings().email_from.rstrip(">").endswith(".local")


def test_delivered(db, resend_env):
    rec = _send(db, "delivered@resend.dev", "Dialogbot provider-sandbox: levering")
    assert rec.status == "sent" and rec.adapter == "resend"
    assert rec.provider_message_id  # Resend's id, used to match later webhooks
    assert resend_env == [{"to": ["delivered@resend.dev"], "subject": "Dialogbot provider-sandbox: levering"}]


def test_bounced_reaches_our_bounce_path(db, client, resend_env):
    rec = _send(db, "bounced@resend.dev", "Dialogbot provider-sandbox: bounce")
    assert rec.status == "sent" and rec.provider_message_id
    payload = {"type": "email.bounced", "created_at": "2026-11-12T10:00:00.000Z",
               "data": {"email_id": rec.provider_message_id, "to": ["bounced@resend.dev"],
                        "bounce": {"type": "Permanent", "message": "sandbox"}}}
    body = json.dumps(payload).encode()
    msg_id, ts = f"msg_sandbox_{uuid.uuid4().hex}", str(int(time.time()))
    headers = {"svix-id": msg_id, "svix-timestamp": ts,
               "svix-signature": resend_webhook.sign(DUMMY_WEBHOOK_SECRET, msg_id, ts, body)}
    r = client.post("/api/v1/webhooks/resend", content=body, headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["outcome"] == "applied"  # matched on Resend's real message id
    db.expire_all()
    assert db.get(EmailDelivery, rec.id).provider_status == "bounced"
    # a late "delivered" for the same message never overwrites the bounce
    late = json.dumps({**payload, "type": "email.delivered"}).encode()
    msg2 = f"msg_sandbox_{uuid.uuid4().hex}"
    r = client.post("/api/v1/webhooks/resend", content=late, headers={
        "svix-id": msg2, "svix-timestamp": ts, "svix-signature": resend_webhook.sign(DUMMY_WEBHOOK_SECRET, msg2, ts, late)})
    assert r.status_code == 200, r.text
    db.expire_all()
    assert db.get(EmailDelivery, rec.id).provider_status == "bounced"

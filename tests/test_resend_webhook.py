"""Resend delivery webhook: Svix signature, replay window, idempotency and forward-only status."""
from __future__ import annotations

import base64
import json
import time
import uuid

import pytest
from sqlalchemy import func, select

from app.config import get_settings
from app.models import EmailDelivery, OutboxEvent, WebhookEvent
from app.modules.webhooks.resend import sign

SECRET = "whsec_" + base64.b64encode(b"dialogbot-test-webhook-secret-32b").decode()
URL = "/api/v1/webhooks/resend"


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setenv("RESEND_WEBHOOK_SECRET", SECRET)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _delivery(db, provider_id: str = "re_msg_1") -> EmailDelivery:
    ev = OutboxEvent(event_type="email.send", dedupe_key=f"test:{uuid.uuid4()}", payload={}, status="done")
    db.add(ev)
    db.flush()
    rec = EmailDelivery(outbox_event_id=ev.id, adapter="resend", to_email="kunde@example.com", subject="Hej",
                        body_text="Tekst", status="sent", provider_message_id=provider_id)
    db.add(rec)
    db.commit()
    return rec


def _post(client, payload: dict, *, msg_id: str | None = None, ts: int | None = None, secret: str = SECRET, sig: str | None = None):
    body = json.dumps(payload).encode()
    msg_id = msg_id or f"msg_{uuid.uuid4().hex}"
    ts_s = str(ts if ts is not None else int(time.time()))
    headers = {"svix-id": msg_id, "svix-timestamp": ts_s, "svix-signature": sig or sign(secret, msg_id, ts_s, body),
               "content-type": "application/json"}
    return client.post(URL, content=body, headers=headers)


def _event(kind: str, email_id: str = "re_msg_1") -> dict:
    return {"type": kind, "created_at": "2026-09-25T12:00:00.000Z", "data": {"email_id": email_id, "to": ["kunde@example.com"]}}


def test_not_configured_answers_503(client, monkeypatch):
    monkeypatch.delenv("RESEND_WEBHOOK_SECRET", raising=False)
    get_settings.cache_clear()
    r = _post(client, _event("email.delivered"))
    assert r.status_code == 503
    assert r.json()["code"] == "webhook_not_configured"


def test_valid_signature_applies_delivered(client, db, configured):
    rec = _delivery(db)
    r = _post(client, _event("email.delivered"))
    assert r.status_code == 200, r.text
    assert r.json() == {"received": True, "duplicate": False, "outcome": "applied"}
    db.refresh(rec)
    assert rec.provider_status == "delivered"
    assert rec.status == "sent"  # the send outcome is never rewritten by provider events
    assert rec.provider_status_at is not None


def test_bad_signature_wrong_secret_and_missing_headers_are_rejected(client, db, configured):
    _delivery(db)
    other = "whsec_" + base64.b64encode(b"some-other-secret-value-here-000").decode()
    assert _post(client, _event("email.delivered"), secret=other).status_code == 401
    assert _post(client, _event("email.delivered"), sig="v1,AAAA").status_code == 401
    r = client.post(URL, content=b"{}", headers={"content-type": "application/json"})
    assert r.status_code == 401 and r.json()["code"] == "invalid_signature"
    assert db.scalar(select(func.count()).select_from(WebhookEvent)) == 0


def test_tampered_body_is_rejected(client, db, configured):
    _delivery(db)
    body = json.dumps(_event("email.delivered")).encode()
    ts = str(int(time.time()))
    sig = sign(SECRET, "msg_x", ts, body)
    tampered = body.replace(b"delivered", b"bounced")
    r = client.post(URL, content=tampered, headers={"svix-id": "msg_x", "svix-timestamp": ts, "svix-signature": sig})
    assert r.status_code == 401


def test_stale_or_future_timestamp_is_rejected(client, db, configured):
    _delivery(db)
    assert _post(client, _event("email.delivered"), ts=int(time.time()) - 6 * 60).status_code == 401
    assert _post(client, _event("email.delivered"), ts=int(time.time()) + 6 * 60).status_code == 401
    assert _post(client, _event("email.delivered"), ts=int(time.time()) - 4 * 60).status_code == 200


def test_redelivered_event_is_idempotent(client, db, configured):
    rec = _delivery(db)
    first = _post(client, _event("email.delivered"), msg_id="msg_same")
    again = _post(client, _event("email.delivered"), msg_id="msg_same")
    assert first.json()["duplicate"] is False
    assert again.status_code == 200 and again.json()["duplicate"] is True
    assert db.scalar(select(func.count()).select_from(WebhookEvent)) == 1
    db.refresh(rec)
    assert rec.provider_status == "delivered"


def test_status_only_moves_forward(client, db, configured):
    rec = _delivery(db)
    _post(client, _event("email.delivered"))
    _post(client, _event("email.delivery_delayed"))  # late, out of order
    db.refresh(rec)
    assert rec.provider_status == "delivered"
    _post(client, _event("email.bounced"))
    db.refresh(rec)
    assert rec.provider_status == "bounced"


def test_unknown_message_and_untracked_event_types_are_recorded_not_applied(client, db, configured):
    rec = _delivery(db)
    r1 = _post(client, _event("email.delivered", email_id="re_unknown"))
    r2 = _post(client, _event("email.opened"))
    assert r1.json()["outcome"] == "unmatched"
    assert r2.json()["outcome"] == "ignored"
    db.refresh(rec)
    assert rec.provider_status is None
    outcomes = sorted(db.scalars(select(WebhookEvent.outcome)))
    assert outcomes == ["ignored", "unmatched"]


def test_invalid_json_with_valid_signature_is_422(client, configured):
    body = b"not json"
    ts = str(int(time.time()))
    r = client.post(URL, content=body, headers={"svix-id": "m1", "svix-timestamp": ts, "svix-signature": sign(SECRET, "m1", ts, body)})
    assert r.status_code == 422


def test_signature_matches_official_svix_vector():
    """Fixed vector produced by the official `svix` library (Webhook(secret).sign), not by our own sign()."""
    from app.core.errors import Unauthenticated
    from app.modules.webhooks.resend import verify_signature

    body = b'{"type":"email.delivered","data":{"email_id":"re_msg_1"}}'
    official = "v1,rYkA/khxFeKQb+lIZ/feDHqBO2x99OvinUvN9xuruR8="
    verify_signature(SECRET, "msg_vector", "1790000000", f"v0,xx {official}", body, now=1790000000)
    with pytest.raises(Unauthenticated):
        verify_signature(SECRET, "msg_vector", "1790000001", official, body, now=1790000001)

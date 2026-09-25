"""Acceptance 9–10 plus config fail-closed and the reconciled money rules."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.models import EmailDelivery, Invitation, OutboxEvent
from app.worker import runner

# --- Acceptance 9: idempotency + worker redelivery ----------------------------------


def test_idempotency_key_replays_and_rejects_changed_payload(api, two_workspaces, db):
    t = two_workspaces
    tok, ws = t["tok_a"], t["ws_a"]
    r1 = api.invite(tok, ws, "idem@testmail.dk", "staff", key="k-1")
    r2 = api.invite(tok, ws, "idem@testmail.dk", "staff", key="k-1")
    assert r1.status_code == 201 and r2.status_code == 201 and r1.json() == r2.json()
    r3 = api.invite(tok, ws, "idem@testmail.dk", "admin", key="k-1")
    assert r3.status_code == 409 and r3.json()["code"] == "idempotency_payload_mismatch"
    assert db.scalar(select(func.count()).select_from(Invitation)) == 1
    assert db.scalar(select(func.count()).select_from(OutboxEvent).where(OutboxEvent.event_type == "email.invitation")) == 1
    # approval with the same key is idempotent too
    it = api.knowledge(tok, ws, "service", "X")
    api.submit(tok, ws, it["open_draft"]["id"])
    a1 = api.approve(tok, ws, it["open_draft"]["id"], key="ap-1")
    a2 = api.approve(tok, ws, it["open_draft"]["id"], key="ap-1")
    assert a1.status_code == a2.status_code == 200 and a1.json() == a2.json()
    assert api.get(tok, f"/workspaces/{ws}").json()["knowledge_revision"] == 1


def test_worker_outbox_retry_and_no_duplicate_delivery(api, two_workspaces, db):
    t = two_workspaces
    tok, ws = t["tok_a"], t["ws_a"]
    # verification/invitation mails already queued & drained by fixtures; add a fresh one
    api.invite(tok, ws, "worker@testmail.dk", "staff")
    ev = db.scalar(select(OutboxEvent).where(OutboxEvent.event_type == "email.invitation"))
    assert ev.status == "queued" and ev.attempts == 0
    # 1) handler failure → controlled retry with backoff, not done
    runner.FAIL_EVENT_TYPES.add("email.invitation")
    out = runner.process_once("w1")
    assert out.id == ev.id and out.status == "queued" and out.attempts == 1 and "simulated failure" in out.last_error
    assert out.next_attempt_at > datetime.now(UTC)
    assert runner.process_once("w1") is None  # backoff respected
    # 2) process interruption: lease held by a dead worker → re-pickable after lease expiry
    runner.FAIL_EVENT_TYPES.clear()
    db.expire_all()
    ev = db.get(OutboxEvent, ev.id)
    ev.next_attempt_at = datetime.now(UTC) - timedelta(seconds=1)
    db.commit()
    claimed = runner.claim_one(db, "dead-worker")
    assert claimed.id == ev.id and claimed.status == "processing"
    claimed.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)  # simulate crash after lease
    db.commit()
    out = runner.process_once("w2")
    assert out.id == ev.id and out.status == "done" and out.attempts == 3
    assert db.scalar(select(func.count()).select_from(EmailDelivery).where(EmailDelivery.outbox_event_id == ev.id)) == 1
    # 3) forced redelivery of a done event creates no second delivery
    db.expire_all()
    ev = db.get(OutboxEvent, ev.id)
    ev.status = "queued"
    ev.next_attempt_at = datetime.now(UTC) - timedelta(seconds=1)
    db.commit()
    out = runner.process_once("w3")
    assert out.status == "done"
    assert db.scalar(select(func.count()).select_from(EmailDelivery).where(EmailDelivery.outbox_event_id == ev.id)) == 1
    mails = api.get(api.user("worker@testmail.dk"), "/dev/mailbox").json()["items"]
    assert len([m for m in mails if "inviteret" in m["subject"]]) == 1


def test_failed_after_max_attempts(api, two_workspaces, db):
    t = two_workspaces
    api.invite(t["tok_a"], t["ws_a"], "fail@testmail.dk")
    ev = db.scalar(select(OutboxEvent).where(OutboxEvent.event_type == "email.invitation"))
    ev.max_attempts = 2
    db.commit()
    runner.FAIL_EVENT_TYPES.add("email.invitation")
    for _ in range(2):
        db.expire_all()
        ev = db.get(OutboxEvent, ev.id)
        ev.next_attempt_at = datetime.now(UTC) - timedelta(seconds=1)
        db.commit()
        out = runner.process_once("w")
    assert out.status == "failed" and out.attempts == 2


# --- Acceptance 10: migrations from empty + readiness -------------------------------


def test_migrations_applied_and_health(client):
    r = client.get("/health/ready")
    assert r.status_code == 200 and r.json()["status"] == "ok" and r.json()["migration"] == r.json()["expected_migration"]
    assert client.get("/health/live").json() == {"status": "ok"}
    spec = client.get("/api/v1/openapi.json").json()
    assert "/api/v1/workspaces/{workspace_id}/setup/plan" in spec["paths"]


def test_request_id_and_error_shape(client):
    r = client.get("/api/v1/workspaces", headers={"X-Request-ID": "abc-123"})
    assert r.headers["X-Request-ID"] == "abc-123"
    assert r.json() == {"code": "unauthenticated", "message": "Login påkrævet", "field_errors": [], "request_id": "abc-123"}
    r = client.post("/api/v1/auth/register", json={"email": "not-an-email", "password": "short", "display_name": ""})
    assert r.status_code == 422 and r.json()["code"] == "validation_failed" and r.json()["field_errors"]


# --- Config fails closed -----------------------------------------------------------


def test_prod_settings_fail_closed(monkeypatch):
    from app.config import Settings

    base = {"APP_ENV": "prod", "DATABASE_URL": "postgresql+psycopg://x/y", "ENABLE_DEV_TOOLS": "false",
            "EMAIL_ADAPTER": "simulated", "SECRET_KEY": "x" * 40}
    for k, v in base.items():
        monkeypatch.setenv(k, v)
    with pytest.raises(ValueError, match="EMAIL_ADAPTER=simulated is not allowed in prod"):
        Settings(_env_file=None)
    monkeypatch.setenv("EMAIL_ADAPTER", "smtp")
    with pytest.raises(ValueError, match="smtp is not implemented"):
        Settings(_env_file=None)
    monkeypatch.setenv("SECRET_KEY", "short")
    with pytest.raises(ValueError, match="SECRET_KEY"):
        Settings(_env_file=None)
    monkeypatch.setenv("APP_ENV", "dev")
    monkeypatch.setenv("EMAIL_ADAPTER", "simulated")
    monkeypatch.setenv("AUTH_PROVIDER", "external")
    with pytest.raises(ValueError, match="not implemented"):
        Settings(_env_file=None)
    monkeypatch.setenv("APP_ENV", "prod")
    monkeypatch.setenv("AUTH_PROVIDER", "local")
    monkeypatch.setenv("ENABLE_DEV_TOOLS", "true")
    monkeypatch.setenv("SECRET_KEY", "x" * 40)
    with pytest.raises(ValueError, match="ENABLE_DEV_TOOLS"):
        Settings(_env_file=None)


def test_seed_refuses_prod(monkeypatch):
    from app.config import get_settings
    from scripts import seed

    class S:  # minimal stand-in
        app_env = "prod"

    monkeypatch.setattr(seed, "get_settings", lambda: S())
    assert seed.main() == 2
    get_settings.cache_clear()


# --- Reconciled money rules (pure; not wired to endpoints) ---------------------------


def test_pricing_fixtures_model_a_and_b():
    from app.modules.billing.money import (
        CampaignPackageTerms,
        LeadBillingState,
        Money,
        ReceptionAgreement,
        calculator_total_net,
        decide_unbilled_dispute,
    )

    a = ReceptionAgreement(model="A", monthly_net_minor=149500, included_chats=500, included_ai_minutes=200)
    b = ReceptionAgreement(model="B", lead_fee_net_minor=14900)
    pkg = CampaignPackageTerms(net_minor=900, max_attempts=2, max_connected_ai_seconds_total=180)
    assert calculator_total_net(a, 14, pkg, 500) == 599500  # DB-001: leads never change model A
    assert calculator_total_net(a, 0, pkg, 500) == 599500
    assert calculator_total_net(b, 14, pkg, 500) == 658600
    m = Money("DKK", 450000, 2500)
    assert (m.tax_minor, m.gross_minor) == (112500, 562500)
    unused = Money("DKK", 180000, 2500)
    assert (unused.tax_minor, unused.gross_minor) == (45000, 225000)
    start = LeadBillingState(approved_count=14, approved_subtotal_net_minor=208600, suspended_total_net_minor=29800)
    up = decide_unbilled_dispute(start, disputed_net_minor=14900, ruling="uphold")
    assert (up.approved_count, up.approved_subtotal_net_minor, up.suspended_total_net_minor, up.excluded_net_minor,
            up.credit_note_created) == (14, 208600, 14900, 14900, False)
    rj = decide_unbilled_dispute(start, disputed_net_minor=14900, ruling="reject")
    assert (rj.approved_count, rj.approved_subtotal_net_minor, rj.suspended_total_net_minor,
            rj.next_invoice_addition_net_minor, rj.credit_note_created) == (15, 223500, 14900, 14900, False)

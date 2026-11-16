"""Mail provider errors: which ones are retried, and how a refused key/sender domain is shown.

401/403 from Resend = the key is invalid or may not send from EMAIL_FROM's domain. Retrying cannot help, so the job
fails at once with a text that names the domain; the operations screen shows it as an incident and /health/ready
carries a warning (without going unready). 429 and 5xx keep the normal retries. Resend is replaced by a fake
httpx.post: nothing leaves the process."""
from __future__ import annotations

import httpx
import pytest
from sqlalchemy import func, select

from app.config import get_settings
from app.core.outbox import enqueue
from app.models import EmailDelivery, OutboxEvent
from app.modules.health import router as health
from app.worker import runner

OPS = "/operator/admin/operations"
REFUSED = '{"message":"This API key is not authorized to send emails from dialogbot.app","statusCode":403}'


class _Resend:
    """Answers every send with the queued (status, body); counts the calls."""

    def __init__(self):
        self.answer: tuple[int, str] = (200, '{"id":"re_1"}')
        self.calls: list[dict] = []

    def post(self, url, **kw):
        self.calls.append(kw["json"])
        return httpx.Response(self.answer[0], text=self.answer[1], request=httpx.Request("POST", url))


@pytest.fixture
def resend(monkeypatch):
    monkeypatch.setenv("EMAIL_ADAPTER", "resend")
    monkeypatch.setenv("RESEND_API_KEY", "re_test_not_a_real_key")
    monkeypatch.setenv("EMAIL_FROM", "Dialogbot <noreply@dialogbot.app>")
    get_settings.cache_clear()
    fake = _Resend()
    monkeypatch.setattr(httpx, "post", fake.post)
    health._warnings_cache = None
    yield fake
    health._warnings_cache = None
    get_settings.cache_clear()


def _mail(db, key: str) -> OutboxEvent:
    ev = enqueue(db, event_type="email.branded", dedupe_key=key, workspace_id=None,
                 payload={"to_email": "kunde@testmail.dk", "subject": "Hej", "body": "Tekst"})
    db.commit()
    return ev


def _reload(db, ev: OutboxEvent) -> OutboxEvent:
    db.expire_all()
    return db.get(OutboxEvent, ev.id)


@pytest.mark.parametrize("status", [401, 403])
def test_refused_key_fails_at_once_without_retry(db, resend, status):
    resend.answer = (status, REFUSED)
    ev = _mail(db, f"refused-{status}")
    runner.drain()
    ev = _reload(db, ev)
    assert ev.status == "failed" and ev.attempts == 1 and ev.max_attempts > 1  # one call, no backoff rounds
    assert len(resend.calls) == 1
    assert ev.last_error.startswith("EmailSendError: Resend afviste afsenderdomænet dialogbot.app")
    assert "RESEND_API_KEY" in ev.last_error and "not authorized to send emails from dialogbot.app" in ev.last_error
    assert "re_test_not_a_real_key" not in ev.last_error  # the key itself never reaches the error text


@pytest.mark.parametrize("status", [429, 500, 503])
def test_rate_limit_and_server_errors_keep_retrying(db, resend, status):
    resend.answer = (status, '{"message":"try later"}')
    ev = _mail(db, f"transient-{status}")
    runner.process_once()
    ev = _reload(db, ev)
    assert ev.status == "queued" and ev.attempts == 1 and ev.last_error == f'EmailSendError: resend {status}: {{"message":"try later"}}'
    assert ev.next_attempt_at > ev.created_at  # backoff, not an immediate loop
    resend.answer = (200, '{"id":"re_ok"}')  # the provider is back: the same job is delivered
    ev.next_attempt_at = ev.created_at
    db.commit()
    runner.drain()
    assert _reload(db, ev).status == "done"
    assert db.scalar(select(EmailDelivery.provider_message_id).where(EmailDelivery.outbox_event_id == ev.id)) == "re_ok"


def test_transient_error_still_fails_after_max_attempts(db, resend):
    resend.answer = (500, "boom")
    ev = _mail(db, "transient-max")
    for _ in range(ev.max_attempts):
        ev = _reload(db, ev)
        ev.next_attempt_at = ev.created_at
        db.commit()
        runner.process_once()
    ev = _reload(db, ev)
    assert ev.status == "failed" and ev.attempts == ev.max_attempts == len(resend.calls)


def test_operations_and_health_name_the_domain_until_mail_flows_again(api, client, db, resend):
    op = api.operator()
    assert "warnings" not in client.get("/health/ready").json()
    resend.answer = (403, REFUSED)
    ev = _mail(db, "refused-shown")
    runner.drain()
    health._warnings_cache = None

    r = client.get("/health/ready")
    assert r.status_code == 200 and r.json()["status"] == "ok"  # a warning, never unready
    (w,) = r.json()["warnings"]
    assert w["code"] == "email_sender_rejected" and w["domain"] == "dialogbot.app" and w["failed"] == 1

    ops = api.get(op, OPS).json()
    (inc,) = [x for x in ops["incidents"] if x["kind"] == "email_sender"]
    assert "dialogbot.app" in inc["source"] and inc["count"] == 1 and "RESEND_API_KEY" in inc["detail"]
    (job,) = [j for j in ops["failed_jobs"] if j["id"] == str(ev.id)]
    assert job["retryable"] and "dialogbot.app" in job["error"]

    # the key is fixed in Resend: the operator's retry delivers the same job once, and the warning is gone
    resend.answer = (200, '{"id":"re_after_fix"}')
    assert api.post(op, f"{OPS}/jobs/{ev.id}/retry", {}).json()["result"] == "queued"
    runner.drain()
    assert _reload(db, ev).status == "done"
    assert db.scalar(select(func.count()).select_from(EmailDelivery).where(EmailDelivery.outbox_event_id == ev.id)) == 1
    health._warnings_cache = None
    assert "warnings" not in client.get("/health/ready").json()
    assert not [x for x in api.get(op, OPS).json()["incidents"] if x["kind"] == "email_sender"]

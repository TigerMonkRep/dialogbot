"""F-VER1112-01 rest, Fürster 13/11 («A»): code SMS go out from the worker for EVERY number, never inside the request.

- «Ring mig op nu» (/demo-call/code): a number on the do-not-call list and any other number get the same status code
  and body, and neither request touches the SMS transport; the worker then sends to the ordinary number only.
- The web chat's «Bliv kontaktet» code (W04): no SMS inside the request either, no 502 `sms_failed` when Twilio fails
  (the worker retries), and every code SMS sent is the business's own SMS usage (sms_usage, no price) – only in its
  own workspace.
- The queued event never holds the number or the code in clear text."""
from __future__ import annotations

import json
import uuid

import pytest
from sqlalchemy import select

from app.models import CustomerVerification, DemoCallVerification, DoNotCall, OutboxEvent, SmsUsage
from app.modules.integrations.connectors import sms as sms_connector
from app.modules.integrations.connectors.fakes import WORLD
from app.worker import runner
from tests.test_leads import chat, fake  # noqa: F401 – fixtures
from tests.test_sales_demo_calls import sales  # noqa: F401 – fixture
from tests.webchat_phone import last_code, request_code, submit_code


@pytest.fixture(autouse=True)
def _world():
    WORLD.reset()
    yield
    WORLD.reset()


class _Guard(list):
    """The SMS transport must not be reached while a request is being answered; `release()` lets the worker send."""

    def release(self):
        sms_connector.send = self.real


@pytest.fixture
def no_sync_sms():
    calls = _Guard()
    calls.real = sms_connector.send

    def forbidden(*a, **kw):
        calls.append(kw.get("to"))
        raise AssertionError("SMS sent inside the request")

    sms_connector.send = forbidden
    yield calls
    calls.release()


def _shape(r):
    body = r.json()
    return r.status_code, body.get("status"), body.get("resend_after"), body.get("expires_in"), sorted(body)


def test_demo_code_same_answer_for_a_do_not_call_number_and_no_sms_inside_the_request(client, sales, db, no_sync_sms):  # noqa: F811
    db.add(DoNotCall(workspace_id=uuid.UUID(sales["ws"]), phone="+4520304051", source="call"))
    db.commit()
    plain = client.post("/api/v1/demo-call/code", json={"phone": "20 30 40 50", "consent": True})
    blocked = client.post("/api/v1/demo-call/code", json={"phone": "20 30 40 51", "consent": True})
    assert _shape(plain) == _shape(blocked) == (202, "code_sent", 30, 600, ["expires_in", "phone_display", "resend_after",
                                                                          "status", "verification_id"])
    assert no_sync_sms == []  # the request never reached the transport, for either number
    evs = db.scalars(select(OutboxEvent).where(OutboxEvent.event_type == "sms.code")).all()
    assert len(evs) == 2  # the same queued work for both
    for ev in evs:
        raw = json.dumps(ev.payload)
        assert "4520304050" not in raw and "4520304051" not in raw and ev.workspace_id is None
    no_sync_sms.release()  # the worker may send now
    runner.drain()
    assert [m["to"] for m in WORLD.sms] == ["+4520304050"]  # never an SMS to the do-not-call number
    code = last_code("+4520304050")
    db.expire_all()
    for ev in evs:
        p = db.get(OutboxEvent, ev.id).payload
        assert "code" not in p and code not in json.dumps(p)  # the encrypted code is gone after the attempt
    assert sorted(db.get(OutboxEvent, ev.id).payload["outcome"] for ev in evs) == ["sent", "suppressed"]
    rows = {r.phone: r for r in db.scalars(select(DemoCallVerification))}
    guessed = client.post("/api/v1/demo-call/verify", json={"verification_id": str(rows["+4520304051"].id),
                                                             "code": code})
    assert guessed.status_code == 422  # the opt-out's code was voided: nothing matches
    usage = db.scalars(select(SmsUsage)).all()
    assert [(u.purpose, str(u.workspace_id), u.net_minor) for u in usage] == [("demo_call_code", sales["ws"], None)]


def test_webchat_code_is_sent_by_the_worker_counted_for_the_business_only(client, chat, db, no_sync_sms):  # noqa: F811
    r = request_code(client, chat["key"], chat["conv"], "20 30 40 50", send=False)
    assert r.status_code == 202 and r.json()["status"] == "code_sent", r.text
    assert no_sync_sms == [] and WORLD.sms == []
    no_sync_sms.release()
    runner.drain()
    assert [m["to"] for m in WORLD.sms] == ["+4520304050"]
    v = submit_code(client, chat["key"], chat["conv"], r.json()["verification_id"], last_code("+4520304050"))
    assert v.status_code == 200
    usage = db.scalars(select(SmsUsage)).all()
    assert [(str(u.workspace_id), u.purpose, u.segments, u.simulated, u.net_minor) for u in usage] == [
        (chat["ws_a"], "webchat_phone", 1, True, None)]
    assert db.scalar(select(SmsUsage).where(SmsUsage.workspace_id == uuid.UUID(chat["ws_b"]))) is None
    runner.drain()  # a redelivered event never sends twice
    assert len(WORLD.sms) == 1 and db.query(SmsUsage).count() == 1


def test_webchat_twilio_failure_is_202_and_retried_never_502(client, chat, db):  # noqa: F811
    from sqlalchemy import text

    runner.drain()  # the fixture's own mails first
    WORLD.fail_next.add("sms")
    r = request_code(client, chat["key"], chat["conv"], "20 30 40 50", send=False)
    assert r.status_code == 202 and r.json()["status"] == "code_sent"
    runner.drain()  # first attempt fails; the retry waits for its backoff
    assert WORLD.sms == [] and db.query(SmsUsage).count() == 0  # a failed SMS is not usage
    db.execute(text("update outbox_events set next_attempt_at = now()"))
    db.commit()
    runner.drain()
    assert [m["to"] for m in WORLD.sms] == ["+4520304050"] and db.query(SmsUsage).count() == 1


def test_an_expired_or_used_code_is_not_sent_late(client, chat, db):  # noqa: F811
    r = request_code(client, chat["key"], chat["conv"], "20 30 40 50", send=False)
    row = db.get(CustomerVerification, uuid.UUID(r.json()["verification_id"]))
    from datetime import UTC, datetime, timedelta

    row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db.commit()
    runner.drain()
    assert WORLD.sms == [] and db.query(SmsUsage).count() == 0

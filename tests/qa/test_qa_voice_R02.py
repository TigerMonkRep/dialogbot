"""QA R02 [DB-018] (voice-qa): "Existing public number, carrier, forwarding destination/rules, outgoing identity,
verification and test." DB-018: "Adapters identify environment and capabilities; provider verification gates
activation; no real launch/payment/message caused by test path."

Simulated providers only (TELEPHONY_PROVIDER=fake → providers.FakeTwilio/FakeVapi; their WORLD is the outbox). Any
attempt to reach the network during these tests fails the test."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import select

from app.db import get_session_factory
from app.models import Call, Lead, Task, TelephonySetup, TelephonyTest

from tests.test_telephony_platform import WORLD, _approve_docs, _code, _hook, _ready, _run_jobs, fake  # noqa: F401


@pytest.fixture
def no_network(monkeypatch):
    def refuse(*a, **kw):
        raise AssertionError(f"network call attempted in a test path: {a[:2]}")

    for name in ("request", "get", "post", "put", "patch", "delete", "stream"):
        monkeypatch.setattr(httpx, name, refuse)
    monkeypatch.setattr(httpx.Client, "send", refuse)
    yield


def _knowledge(api, tok, ws):
    it = api.knowledge(tok, ws, "service", "Afslibning", {"price_net_minor": 14500})
    api.submit(tok, ws, it["open_draft"]["id"])
    api.approve(tok, ws, it["open_draft"]["id"])


def _active(client, api, tok, ws, caller="+4540404040") -> str:
    """Business number verified, connected, test call passed, activated. Returns the destination number."""
    base = f"/workspaces/{ws}/telephony"
    _ready(api, tok, ws)
    assert api.post(tok, f"{base}/connect").status_code == 200
    _approve_docs(api, ws)
    _run_jobs()
    _knowledge(api, tok, ws)
    dest = api.get(tok, base).json()["destination"]["e164"]
    assert api.post(tok, f"{base}/tests", {"called_business_number": True}).status_code == 200
    a = _hook(client, {"type": "assistant-request", "call": {"id": "c-test", "customer": {"number": caller}},
                       "phoneNumber": {"number": dest}}).json()["assistant"]
    assert a["firstMessage"].startswith("Dette er et prøveopkald")
    rep = {"type": "end-of-call-report", "call": {"id": "c-test", "customer": {"number": caller}, "cost": 0.12},
           "phoneNumber": {"number": dest}, "startedAt": "2026-11-10T08:00:00Z", "endedAt": "2026-11-10T08:01:30Z",
           "analysis": {"summary": "Ejeren ringede for at teste."},
           "artifact": {"messages": [{"role": "user", "message": "Hej, det er bare en test."},
                                     {"role": "assistant", "message": "Hej, du har ringet til Fjord."}]}}
    assert _hook(client, rep).json()["outcome"] == "applied"
    assert api.get(tok, base).json()["test"]["status"] == "passed"
    r = api.post(tok, f"{base}/activate")
    assert r.status_code == 200, r.text
    return dest


# --------------------------------------------------------------------------- expected to pass

def test_r02_the_whole_setup_and_test_path_stays_in_the_simulated_adapters(client, api, two_workspaces, fake, no_network):  # noqa: F811
    t = two_workspaces
    tok, ws = t["tok_a"], t["ws_a"]
    o = api.get(tok, f"/workspaces/{ws}/telephony").json()
    assert o["status"]["platform_ready"] is True and o["status"]["code"] == "not_started"
    _active(client, api, tok, ws)
    # the only "call" placed is the verification call, and it sits in the simulated provider's outbox
    assert [c["metadata"]["purpose"] for c in WORLD.calls] == ["verification"]
    assert WORLD.calls[0]["customer"]["number"] == "+4520304050"
    assert WORLD.calls[0]["assistant"]["artifactPlan"] == {"recordingEnabled": False}
    with get_session_factory()() as db:
        s = db.scalar(select(TelephonySetup).where(TelephonySetup.workspace_id == uuid.UUID(ws)))
        t_row = db.get(TelephonyTest, s.last_test_id)
        assert t_row.simulated is True  # a test in the fake environment is labelled as such, never as a real test
        assert s.verify_code_hash is None and s.business_number_verified_by == "code_call"
    o = api.get(tok, f"/workspaces/{ws}/telephony").json()
    assert o["test"]["simulated"] is True and o["status"]["code"] == "active"


def test_r02_verification_gates_connect_and_is_rate_limited(client, api, two_workspaces, fake):  # noqa: F811
    t = two_workspaces
    tok, ws = t["tok_a"], t["ws_a"]
    base = f"/workspaces/{ws}/telephony"
    api.put(tok, f"{base}/business-number", {"e164": "+4520304050", "subscription_type": "mobile"})
    api.post(tok, f"/workspaces/{ws}/agreement", {"model": "A"})
    assert api.post(tok, f"{base}/connect").json()["code"] == "telephony_missing_info"  # unverified
    for _ in range(3):
        assert api.post(tok, f"{base}/verify").status_code == 200
    assert api.post(tok, f"{base}/verify").status_code == 429
    code = _code(ws)
    wrong = "000000" if code != "000000" else "111111"
    for _ in range(5):
        assert api.post(tok, f"{base}/verify/confirm", {"code": wrong}).status_code == 422
    assert api.post(tok, f"{base}/verify/confirm", {"code": code}).status_code == 422  # locked after 5 wrong tries
    assert api.get(tok, base).json()["verified"] is False
    # a member without telephony.manage cannot start a verification call at all
    staff = api.add_member(tok, ws, "staff-r02@testmail.dk", "staff")
    assert api.post(staff, f"{base}/verify").status_code == 403


# --------------------------------------------------------------------------- F-VQ-06: re-activation after number change

def test_r02_a_changed_business_number_must_be_verified_and_tested_before_reactivation(client, api, two_workspaces, fake):  # noqa: F811
    """Active → pause → the owner enters ANOTHER business number. The new number is unverified (verified=False) and
    has never been forwarded or tested, so activation must be refused until it is verified and a new test passes."""
    t = two_workspaces
    tok, ws = t["tok_a"], t["ws_a"]
    base = f"/workspaces/{ws}/telephony"
    _active(client, api, tok, ws)
    assert api.post(tok, f"{base}/pause").status_code == 200
    r = api.put(tok, f"{base}/business-number", {"e164": "+4529998877", "subscription_type": "mobile"})
    assert r.status_code == 200, r.text
    assert r.json()["verified"] is False and r.json()["business_number"] == "+4529998877"
    r = api.post(tok, f"{base}/activate")
    assert r.status_code == 409, (
        f"re-activated with an unverified, untested business number: {r.status_code} {r.json()['status']['code']}")


# --------------------------------------------------------------------------- F-VQ-07: the test call is a real call

def test_r02_the_test_call_creates_no_billable_minutes_and_no_lead(client, api, two_workspaces, fake):  # noqa: F811
    """DB-018: "no real launch/payment/message caused by test path". The owner's own test call ("Dette er et
    prøveopkald") must not become a lead with a "Ring tilbage" task (which fans out lead.created to the customer's
    CRM/webhooks) and must not count as billable inbound minutes."""
    from app.modules.billing.statement import inbound_minutes

    t = two_workspaces
    tok, ws = t["tok_a"], t["ws_a"]
    _active(client, api, tok, ws)
    with get_session_factory()() as db:
        call = db.scalar(select(Call).where(Call.provider_call_id == "c-test"))
        assert call is not None
        leads = db.scalars(select(Lead).where(Lead.workspace_id == uuid.UUID(ws))).all()
        tasks = db.scalars(select(Task).where(Task.workspace_id == uuid.UUID(ws))).all()
        minutes = inbound_minutes(db, uuid.UUID(ws), datetime(2026, 11, 1, tzinfo=UTC),
                                  datetime(2026, 11, 1, tzinfo=UTC) + timedelta(days=30))
    problems = []
    if leads:
        problems.append(f"{len(leads)} lead(s) from the test call: {[x.need_summary for x in leads]}")
    if tasks:
        problems.append(f"task(s): {[x.title for x in tasks]}")
    if minutes["minutes"]:
        problems.append(f"test call counted as {minutes['minutes']} billable inbound minute(s)")
    assert not problems, "; ".join(problems)

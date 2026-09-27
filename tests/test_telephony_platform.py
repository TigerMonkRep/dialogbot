"""Platform-managed telephony (simulated providers: TELEPHONY_PROVIDER=fake – no real numbers are bought).

Acceptance: a brand-new customer completes the flow without any provider login or key; two workspaces get separate
sub-accounts, numbers and routing; manipulated ids are refused; retries after timeouts never buy twice; missing
platform credentials and pending documentation give honest statuses; no secret or provider id reaches the customer;
caller ID for campaigns needs an operator's permission."""
from __future__ import annotations

import json
import uuid

import pytest

from app.config import get_settings
from app.db import get_session_factory
from app.models import TelephonyAccount, TelephonyCost, TelephonyJob
from app.modules.telephony import platform
from app.modules.telephony.providers import WORLD, FakeWorld

SECRET = "vapi-test-secret-0123456789abcdef"
BUNDLE = "BU" + "a" * 32


@pytest.fixture
def fake(monkeypatch, tmp_path):
    monkeypatch.setenv("TELEPHONY_PROVIDER", "fake")
    monkeypatch.setenv("VAPI_SERVER_SECRET", SECRET)
    monkeypatch.setenv("TELEPHONY_VERIFY_NUMBER_ID", "vapi-verify-1")
    monkeypatch.setenv("VOICE_STORAGE_DIR", str(tmp_path / "store"))
    monkeypatch.setenv("AI_PROVIDER", "fake")
    get_settings.cache_clear()
    fresh = FakeWorld()
    for k in fresh.__dataclass_fields__:
        setattr(WORLD, k, getattr(fresh, k))
    yield WORLD
    get_settings.cache_clear()


def _hook(client, message: dict):
    return client.post("/api/v1/webhooks/vapi", json={"message": message}, headers={"authorization": f"Bearer {SECRET}"})


def _code(ws: str) -> str:
    call = [c for c in WORLD.calls if (c.get("metadata") or {}).get("workspace_id") == ws][-1]
    return "".join(ch for ch in call["assistant"]["firstMessage"] if ch.isdigit())[:6]


def _ready(api, tok, ws, number="+4520304050", *, docs=True, agreement=True):
    base = f"/workspaces/{ws}/telephony"
    r = api.put(tok, f"{base}/business-number", {"e164": number, "subscription_type": "mobile",
                                                 "forwarding_mode": "busy_or_no_answer"})
    assert r.status_code == 200, r.text
    assert api.post(tok, f"{base}/verify").status_code == 200
    assert api.post(tok, f"{base}/verify/confirm", {"code": _code(ws)}).status_code == 200
    if docs:
        assert api.put(tok, f"{base}/company", {"company_name": "Test ApS", "cvr": "12345678",
                                                "address": "Østergade 1, 8000 Aarhus C"}).status_code == 200
        r = api.c.put(f"{api.base}{base}/documents", content=b"%PDF-1.4 cvr", headers=api.h(tok, **{"content-type": "application/pdf"}))
        assert r.status_code == 200, r.text
    if agreement:
        assert api.post(tok, f"/workspaces/{ws}/agreement", {"model": "A"}).status_code in (200, 201)


def _approve_docs(api, ws):
    r = api.post(api.operator(), f"/operator/telephony/workspaces/{ws}/documents/review",
                 {"status": "approved", "note": "CVR-udskrift med dansk adresse kontrolleret", "regulatory_bundle_sid": BUNDLE})
    assert r.status_code == 200, r.text


def _run_jobs():
    with get_session_factory()() as db:
        platform.run_due_jobs(db, now=platform._now() + platform.timedelta(days=1))


SECRETS_AND_IDS = ("vapi-", "ACsub", "PN0", SECRET, "fake-subaccount-token", "twilio", "webhook", "Bearer")


def _no_leaks(payload) -> None:
    text = json.dumps(payload)
    for s in SECRETS_AND_IDS:
        assert s not in text, f"{s!r} leaked to the customer"


def test_new_customer_completes_flow_without_provider_accounts(client, api, two_workspaces, fake):
    t = two_workspaces
    tok, ws = t["tok_a"], t["ws_a"]
    base = f"/workspaces/{ws}/telephony"
    o = api.get(tok, base).json()
    assert o["status"]["code"] == "not_started" and o["status"]["label"] == "Ikke sat op" and o["destination"] is None
    assert "nummer" in o["status"]["next_step"]
    api.put(tok, f"{base}/business-number", {"e164": "+45 20 30 40 50", "subscription_type": "mobile"})
    o = api.get(tok, base).json()
    assert o["status"]["code"] == "awaiting_info" and [m["key"] for m in o["status"]["missing"]][:1] == ["verify"]
    # verification: wrong code counts, right code passes
    assert api.post(tok, f"{base}/verify").status_code == 200
    assert WORLD.calls[-1]["customer"]["number"] == "+4520304050"
    assert api.post(tok, f"{base}/verify/confirm", {"code": "000000" if _code(ws) != "000000" else "111111"}).status_code == 422
    assert api.post(tok, f"{base}/verify/confirm", {"code": _code(ws)}).status_code == 200
    # connect is refused (no provisioning, no purchase) until documentation and the price agreement are in
    assert api.post(tok, f"{base}/connect").json()["code"] == "telephony_missing_info"
    assert WORLD.purchases == 0
    api.put(tok, f"{base}/company", {"company_name": "Fjord Gulvservice ApS", "cvr": "12345678", "address": "Østergade 1, 8000 Aarhus C"})
    api.c.put(f"{api.base}{base}/documents", content=b"%PDF-1.4 x", headers=api.h(tok, **{"content-type": "application/pdf"}))
    assert api.post(tok, f"{base}/connect").json()["code"] == "telephony_missing_info"  # agreement missing
    api.post(tok, f"/workspaces/{ws}/agreement", {"model": "A"})
    r = api.post(tok, f"{base}/connect")
    assert r.status_code == 200, r.text
    o = r.json()
    assert o["status"]["code"] == "provisioning" and "dokumentation" in o["status"]["next_step"]
    assert WORLD.purchases == 0  # waits for the documentation review, buys nothing yet
    _approve_docs(api, ws)
    _run_jobs()
    o = api.get(tok, base).json()
    assert o["status"]["code"] == "ready_for_test" and o["destination"]["e164"].startswith("+45")
    dest = o["destination"]["e164"]
    assert {"code": f"**61*{dest}#", "label": "Ved ubesvaret opkald"} in o["guide"]["codes"]
    _no_leaks(o)
    # before activation a real caller hears a short "not activated" message, not the assistant
    it = api.knowledge(tok, ws, "service", "Afslibning", {"price_net_minor": 14500})
    api.submit(tok, ws, it["open_draft"]["id"])
    api.approve(tok, ws, it["open_draft"]["id"])
    msg = {"type": "assistant-request", "call": {"id": "c-pre", "customer": {"number": "+4540404040"}},
           "phoneNumber": {"number": dest}}
    a = _hook(client, msg).json()["assistant"]
    assert a["metadata"].get("not_active") and "ikke aktiveret" in a["firstMessage"]
    assert api.post(tok, f"{base}/activate").json()["code"] == "telephony_test_required"
    # test call: reaches this workspace's assistant, is stored in its inbox, passes
    api.post(tok, f"{base}/tests", {"called_business_number": True})
    a = _hook(client, {**msg, "call": {"id": "c-test", "customer": {"number": "+4540404040"}}}).json()["assistant"]
    assert a["firstMessage"].startswith("Dette er et prøveopkald") and "Afslibning" in a["model"]["messages"][0]["content"]
    rep = {"type": "end-of-call-report", "call": {"id": "c-test", "customer": {"number": "+4540404040"}, "cost": 0.12},
           "phoneNumber": {"number": dest}, "startedAt": "2026-09-27T08:00:00Z", "endedAt": "2026-09-27T08:01:00Z",
           "artifact": {"messages": [{"role": "user", "message": "Hej, det er en test."}]}}
    assert _hook(client, rep).json()["outcome"] == "applied"
    o = api.get(tok, base).json()
    assert o["test"]["status"] == "passed" and o["test"]["conversation_stored"] is True
    r = api.post(tok, f"{base}/activate")
    assert r.status_code == 200 and r.json()["status"]["code"] == "active" and r.json()["status"]["label"] == "Aktiv"
    a = _hook(client, {**msg, "call": {"id": "c-live", "customer": {"number": "+4540404040"}}}).json()["assistant"]
    assert "Afslibning" in a["model"]["messages"][0]["content"] and not a["metadata"].get("not_active")
    with get_session_factory()() as db:  # internal provider cost recorded per workspace, not invoiced
        c = db.query(TelephonyCost).filter_by(workspace_id=uuid.UUID(ws), kind="call").one()
        assert c.amount_micros == 120000
    # everything the customer sees is free of provider ids and secrets
    _no_leaks(api.get(tok, f"/workspaces/{ws}/phone-numbers").json())
    _no_leaks(api.get(tok, base).json())


def test_two_workspaces_are_separated_and_foreign_ids_are_refused(client, api, two_workspaces, fake, monkeypatch):
    t = two_workspaces
    for tok, ws in ((t["tok_a"], t["ws_a"]), (t["tok_b"], t["ws_b"])):
        _ready(api, tok, ws, number="+452030405" + ("1" if ws == t["ws_a"] else "2"))
        api.post(tok, f"/workspaces/{ws}/telephony/connect")
        _approve_docs(api, ws)
    _run_jobs()
    a = api.get(t["tok_a"], f"/workspaces/{t['ws_a']}/telephony").json()["destination"]["e164"]
    b = api.get(t["tok_b"], f"/workspaces/{t['ws_b']}/telephony").json()["destination"]["e164"]
    assert a != b and WORLD.purchases == 2
    with get_session_factory()() as db:
        subs = db.query(TelephonyAccount).filter_by(kind="subaccount").all()
        assert len({s.external_id for s in subs}) == 2 and {str(s.workspace_id) for s in subs} == {t["ws_a"], t["ws_b"]}
    # the same business number cannot be claimed by B: numbers are unique per workspace destination; B can't see A
    assert api.get(t["tok_b"], f"/workspaces/{t['ws_a']}/telephony").status_code in (403, 404)
    # a webhook for A's number never produces B's assistant; foreign org is rejected
    monkeypatch.setenv("VAPI_ORG_ID", "org-dialogbot")
    get_settings.cache_clear()
    foreign = {"type": "assistant-request", "call": {"id": "x", "orgId": "org-evil"}, "phoneNumber": {"number": a}}
    assert "error" in _hook(client, foreign).json()
    # a Dialogbot number calling a Dialogbot number is a forwarding loop and is refused
    loop = {"type": "assistant-request", "call": {"id": "y", "orgId": "org-dialogbot", "customer": {"number": b}},
            "phoneNumber": {"number": a}}
    assert "løkke" in _hook(client, loop).json()["error"]
    # customers cannot reach operator endpoints or hand in provider ids
    assert api.get(t["tok_a"], "/operator/telephony").status_code == 403
    assert api.put(t["tok_a"], f"/workspaces/{t['ws_a']}/telephony/business-number",
                   {"e164": b, "subscription_type": "mobile"}).status_code == 422  # a Dialogbot number is not theirs


def test_retries_after_timeouts_never_buy_or_import_twice(client, api, two_workspaces, fake):
    t = two_workspaces
    tok, ws = t["tok_a"], t["ws_a"]
    _ready(api, tok, ws)
    _approve_docs(api, ws)
    WORLD.fail_after |= {"buy", "import", "create_subaccount"}
    api.post(tok, f"/workspaces/{ws}/telephony/connect")  # sub-account created, then a timeout
    api.post(tok, f"/workspaces/{ws}/telephony/connect")  # a second click returns the same job
    for _ in range(4):
        _run_jobs()
    o = api.get(tok, f"/workspaces/{ws}/telephony").json()
    assert o["status"]["code"] == "ready_for_test"
    assert WORLD.purchases == 1 and len(WORLD.vapi) == 1 and len(WORLD.subaccounts) == 1
    with get_session_factory()() as db:
        assert db.query(TelephonyJob).filter_by(workspace_id=uuid.UUID(ws)).count() == 1
    assert api.post(tok, f"/workspaces/{ws}/telephony/connect").json()["code"] == "telephony_already_provisioned"


def test_honest_statuses_without_platform_credentials(client, api, two_workspaces, monkeypatch):
    monkeypatch.setenv("TELEPHONY_PROVIDER", "none")
    get_settings.cache_clear()
    t = two_workspaces
    tok, ws = t["tok_a"], t["ws_a"]
    base = f"/workspaces/{ws}/telephony"
    o = api.get(tok, base).json()
    assert o["status"]["code"] == "not_started" and o["status"]["platform_ready"] is False
    api.put(tok, f"{base}/business-number", {"e164": "+4520304050", "subscription_type": "landline", "carrier": "TDC"})
    r = api.post(tok, f"{base}/verify")
    assert r.status_code == 503 and r.json()["code"] == "verify_unavailable"
    # operator verifies by hand (audited); still nothing is "active"
    op = api.operator()
    assert api.post(op, f"/operator/telephony/workspaces/{ws}/verify-manually",
                    {"note": "Kunden viste faktura fra TDC på nummeret"}).status_code == 200
    ov = api.get(op, "/operator/telephony").json()
    assert ov["configuration"]["ready"] is False and all(isinstance(v, bool | str) for v in ov["configuration"].values())
    assert SECRET not in json.dumps(ov)
    o = api.get(tok, base).json()
    assert o["status"]["code"] == "awaiting_info" and o["active"] is False and o["destination"] is None
    assert o["guide"] == {"available": False}
    get_settings.cache_clear()


def test_campaign_caller_id_needs_operator_permission(api, two_workspaces, fake, db, monkeypatch):
    from app.models import Campaign
    from app.modules.campaigns.service import outbound_problem

    monkeypatch.setenv("VAPI_API_KEY", "vapi-private-test-key")
    get_settings.cache_clear()

    t = two_workspaces
    n = api.map_number(t["ws_b"], "+4570111222", "pn_camp", activate=True, outbound=False)
    c = Campaign(workspace_id=uuid.UUID(t["ws_b"]), name="Test", phone_number_id=uuid.UUID(n["id"]),
                 package_net_minor=900, max_attempts=2, max_connected_seconds=180)
    db.add(c)
    db.flush()
    assert "ikke godkendt til udgående" in (outbound_problem(db, c) or "")
    api.c.patch(f"{api.base}/operator/telephony/numbers/{n['id']}", json={"outbound_allowed": True,
                                                                          "note": "Twilio tillader afsender for kunden"},
                headers=api.h(api.operator()))
    db.expire_all()
    assert outbound_problem(db, c) is None

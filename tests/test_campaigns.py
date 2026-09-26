"""Outbound campaigns: CSV import with the legal rules, explicit start (payment never starts calls),
the dialler (window, one call in flight, max attempts, package charged once), call outcomes → leads,
opt-out → do-not-call, and campaign packages on the monthly statement."""
from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, time, timedelta

import pytest

from app.config import get_settings
from app.core.errors import ValidationFailed
from app.models import Campaign, CampaignContact, DoNotCall, Lead, Task
from app.modules.billing.statement import statement
from app.modules.campaigns import service

SECRET = "vapi-test-secret-0123456789abcdef"
CSV = "Navn;Telefon;Firma\nMette Hansen;20 30 40 50;Hansen Byg ApS\nOle Berg;+45 21 22 23 24;Berg VVS\nForkert;123;X\nMette igen;0045 20304050;Dup\n"


def test_phone_numbers_and_csv():
    assert service.normalize_phone("20 30 40 50") == "+4520304050"
    assert service.normalize_phone("0045 2030-4050") == "+4520304050"
    assert service.normalize_phone("4520304050") == "+4520304050"
    assert service.normalize_phone("+46701234567") == "+46701234567"
    assert service.normalize_phone("123") is None
    rows = service.parse_csv(CSV)
    assert rows[0] == {"name": "Mette Hansen", "phone": "20 30 40 50", "company": "Hansen Byg ApS", "email": ""}
    headless = service.parse_csv("Jens Jensen,jens@firma.dk,22334455\nBo Bo,bo@x.dk,+4522334456")
    assert headless[0] == {"name": "Jens Jensen", "phone": "22334455", "company": "", "email": "jens@firma.dk"}


def _campaign(api, t, **extra):
    tok, ws = t["tok_a"], t["ws_a"]
    body = {"name": "Forårstilbud", "purpose": "Tilbyde gulvafslibning til foråret", "call_days": list(service.DAYS),
            "call_from": "00:00", "call_to": "23:59"} | extra
    r = api.post(tok, f"/workspaces/{ws}/campaigns", body)
    assert r.status_code == 201, r.text
    return r.json()


def test_import_rules_and_do_not_call(api, two_workspaces):
    t = two_workspaces
    tok, ws = t["tok_a"], t["ws_a"]
    c = _campaign(api, t)
    assert c["package"] == {"net_minor": 900, "max_attempts": 2, "max_connected_seconds": 180}
    assert api.post(tok, f"/workspaces/{ws}/do-not-call", {"phone": "21222324", "reason": "Bad os lade være"}).status_code == 201
    r = api.post(tok, f"/workspaces/{ws}/campaigns/{c['id']}/contacts/import", {"csv": CSV, "kind": "business"}).json()
    assert (r["added"], r["duplicates"], r["blocked"], r["invalid_count"]) == (1, 1, 1, 1)
    assert r["invalid"][0]["row"] == 3
    # consumers need documented prior consent (markedsføringsloven § 10)
    bad = api.post(tok, f"/workspaces/{ws}/campaigns/{c['id']}/contacts/import", {"csv": "Bo;22334455", "kind": "consumer"})
    assert bad.status_code == 422
    ok = api.post(tok, f"/workspaces/{ws}/campaigns/{c['id']}/contacts/import",
                  {"csv": "Bo;22334455", "kind": "consumer", "consent_source": "Tilmelding på hjemmesiden, marts 2026"}).json()
    assert ok["added"] == 1 and ok["campaign"]["max_cost"]["net_minor"] == 1800
    items = api.get(tok, f"/workspaces/{ws}/campaigns/{c['id']}/contacts").json()["items"]
    assert {x["kind"] for x in items} == {"business", "consumer"}
    # staff can read and block a number, but not create or start campaigns
    staff = api.add_member(tok, ws, "staff-camp@testmail.dk", "staff")
    assert api.get(staff, f"/workspaces/{ws}/campaigns").status_code == 200
    assert api.post(staff, f"/workspaces/{ws}/campaigns", {"name": "x"}).status_code == 403
    assert api.post(staff, f"/workspaces/{ws}/do-not-call", {"phone": "22334455"}).status_code == 201
    assert {x["status"] for x in api.get(tok, f"/workspaces/{ws}/campaigns/{c['id']}/contacts").json()["items"]} == {"pending", "skipped"}
    # other workspaces cannot see it
    assert api.get(t["tok_b"], f"/workspaces/{t['ws_b']}/campaigns/{c['id']}").status_code == 404


def _ready(api, t, monkeypatch, *, key=True):
    tok, ws = t["tok_a"], t["ws_a"]
    monkeypatch.setenv("VAPI_SERVER_SECRET", SECRET)
    monkeypatch.setenv("AI_PROVIDER", "fake")
    if key:
        monkeypatch.setenv("VAPI_API_KEY", "vapi-private-key-test")
    else:
        monkeypatch.delenv("VAPI_API_KEY", raising=False)
    get_settings.cache_clear()
    it = api.knowledge(tok, ws, "service", "Gulvafslibning", {"description": "Vi sliber trægulve."})
    api.submit(tok, ws, it["open_draft"]["id"])
    api.approve(tok, ws, it["open_draft"]["id"])
    api.post(tok, f"/workspaces/{ws}/phone-numbers", {"e164": "+4570123456", "provider_number_id": "pn_out"})


def test_start_is_explicit_and_honest(api, two_workspaces, monkeypatch):
    t = two_workspaces
    tok, ws = t["tok_a"], t["ws_a"]
    _ready(api, t, monkeypatch, key=False)
    c = _campaign(api, t)
    assert c["phone_number_id"] is not None and c["status"] == "draft"
    api.post(tok, f"/workspaces/{ws}/campaigns/{c['id']}/contacts/import", {"csv": "Mette;20304050\nOle;21222324", "kind": "business"})
    start = f"/workspaces/{ws}/campaigns/{c['id']}/start"
    body = {"expected_version": c["version"], "legal_confirmed": False, "accept_max_net_minor": 1800}
    assert api.post(tok, start, body).status_code == 422
    assert api.post(tok, start, body | {"legal_confirmed": True, "accept_max_net_minor": 900}).json()["code"] == "price_changed"
    r = api.post(tok, start, body | {"legal_confirmed": True})
    assert r.status_code == 501 and r.json()["code"] == "outbound_not_configured"
    monkeypatch.setenv("VAPI_API_KEY", "vapi-private-key-test")
    get_settings.cache_clear()
    caps = {x["key"]: x["status"] for x in api.get(tok, "/integrations/capabilities").json()["items"]}
    assert caps["telephony.outbound"] == "available"
    r = api.post(tok, start, body | {"legal_confirmed": True})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["status"] == "running" and out["legal_confirmation"]["accepted_max_net_minor"] == 1800
    assert api.put(tok, f"/workspaces/{ws}/campaigns/{c['id']}", {"name": "x", "expected_version": out["version"]}).status_code == 409
    assert api.post(tok, f"/workspaces/{ws}/campaigns/{c['id']}/pause").json()["status"] == "paused"
    get_settings.cache_clear()


def test_dialler_outcomes_and_billing(api, client, two_workspaces, db, monkeypatch):
    t = two_workspaces
    tok, ws = t["tok_a"], t["ws_a"]
    _ready(api, t, monkeypatch)
    c = _campaign(api, t, questions=["Hvor mange m²?"])
    api.post(tok, f"/workspaces/{ws}/campaigns/{c['id']}/contacts/import",
             {"csv": "Mette Hansen;20304050\nOle Berg;21222324", "kind": "business"})
    r = api.post(tok, f"/workspaces/{ws}/campaigns/{c['id']}/start",
                 {"expected_version": c["version"], "legal_confirmed": True, "accept_max_net_minor": 1800})
    assert r.status_code == 200, r.text
    calls = []

    def fake_call(payload):
        calls.append(payload)
        return {"id": f"out_{len(calls)}"}

    monkeypatch.setattr(service, "create_call", fake_call)
    now = datetime.combine(date.today(), time(8, 0), tzinfo=UTC)  # 10:00 in Copenhagen, inside the window
    clock = [now]
    monkeypatch.setattr(service, "_now", lambda: clock[0])
    assert service.dispatch(db, now) == 1
    p = calls[0]
    assert p["phoneNumberId"] == "pn_out" and p["customer"]["number"] == "+4520304050"
    assert "digital assistent" in p["assistant"]["firstMessage"] and "Mette" in p["assistant"]["firstMessage"]
    assert p["assistant"]["maxDurationSeconds"] == 180
    assert "Hvor mange m²?" in p["assistant"]["model"]["messages"][0]["content"]
    assert service.dispatch(db, now) == 0  # one call in flight per campaign
    h = {"authorization": f"Bearer {SECRET}"}

    def report(call_id, messages, reason="customer-ended-call", seconds=60):
        return client.post("/api/v1/webhooks/vapi", headers=h, json={"message": {
            "type": "end-of-call-report", "endedReason": reason, "durationSeconds": seconds,
            "call": {"id": call_id, "phoneNumberId": "pn_out", "type": "outboundPhoneCall", "customer": {"number": "+4520304050"}},
            "artifact": {"messages": messages}}}).json()

    # no answer: the package is charged once, a second attempt comes later
    assert report("out_1", [{"role": "bot", "message": "Hej Mette"}], reason="customer-did-not-answer", seconds=0)["outcome"] == "applied"
    mette = db.query(CampaignContact).filter_by(phone="+4520304050").one()
    db.refresh(mette)
    assert (mette.status, mette.attempts, mette.charged_net_minor) == ("pending", 1, 900)
    assert db.query(Lead).filter(Lead.workspace_id == uuid.UUID(ws)).count() == 0  # not the inbound "ring tilbage" lead
    assert service.dispatch(db, now) == 1 and calls[-1]["customer"]["number"] == "+4521222324"  # Ole meanwhile
    assert report("out_2", [{"role": "bot", "message": "Hej Ole"}, {"role": "user", "message": "Nej tak, ring ikke igen."}])
    assert db.query(DoNotCall).filter_by(phone="+4521222324", source="call").count() == 1
    later = now + timedelta(hours=4)
    clock[0] = later
    assert service.dispatch(db, later) == 1 and calls[-1]["customer"]["number"] == "+4520304050"
    assert report("out_3", [{"role": "bot", "message": "Hej Mette"}, {"role": "user", "message": "Ja, jeg er interesseret i et tilbud"}],
                  seconds=95)
    db.expire_all()
    mette = db.query(CampaignContact).filter_by(phone="+4520304050").one()
    assert (mette.status, mette.outcome, mette.attempts, mette.connected_seconds) == ("done", "interested", 2, 95)
    lead = db.get(Lead, mette.lead_id)
    assert lead.source == "campaign" and lead.contact_phone == "+4520304050" and "Forårstilbud" in lead.need_summary
    assert db.query(Task).filter_by(lead_id=lead.id).count() == 1
    ole = db.query(CampaignContact).filter_by(phone="+4521222324").one()
    assert (ole.status, ole.outcome) == ("opted_out", "opt_out")
    # nothing left to call: the campaign completes
    service.dispatch(db, later)
    assert db.get(Campaign, uuid.UUID(c["id"])).status == "completed"
    st = statement(db, uuid.UUID(ws), date.today(), "Europe/Copenhagen")
    camp = [x for x in st["lines"] if x["kind"] == "campaign"]
    assert camp[0]["packages"] == 2 and camp[0]["net_minor"] == 1800
    assert db.query(DoNotCall).filter_by(phone="+4521222324").one().source == "call"
    entry = api.get(tok, f"/workspaces/{ws}/do-not-call").json()["items"][0]
    assert api.delete(tok, f"/workspaces/{ws}/do-not-call/{entry['id']}").status_code == 409  # own opt-out stays
    check = api.post(tok, f"/workspaces/{ws}/setup/checks/campaign.test_call/run").json()
    assert check["status"] == "passed", check
    get_settings.cache_clear()


def test_window_and_stale_calls(api, two_workspaces, db, monkeypatch):
    t = two_workspaces
    c = Campaign(workspace_id=uuid.UUID(t["ws_a"]), name="x", call_days=["mon"], call_from="09:00", call_to="17:00",
                 package_net_minor=900, max_attempts=2, max_connected_seconds=180)
    monday_10 = datetime(2026, 9, 28, 8, 0, tzinfo=UTC)  # 10:00 in Copenhagen
    assert service.in_window(c, "Europe/Copenhagen", monday_10)
    assert not service.in_window(c, "Europe/Copenhagen", monday_10 + timedelta(hours=8))
    assert not service.in_window(c, "Europe/Copenhagen", monday_10 + timedelta(days=1))
    contact = CampaignContact(phone="+4520304050", kind="business", attempts=2, connected_seconds=0)
    service._after_attempt(c, contact, monday_10, answered=False)
    assert (contact.status, contact.outcome) == ("no_answer", "no_answer")
    with pytest.raises(ValidationFailed):
        service.import_contacts(db, c, "", kind="business", consent_source="")

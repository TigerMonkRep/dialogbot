"""QA C11 (e2e-erhverv B): final readiness and explicit launch confirmation; DB-018 (no real launch caused by a
test path, capability gates activation) and the DB-007 rule "no blind new write after timeout" applied to the
dialler.

Requirement C11: "Final readiness, frozen versions, paid order and explicit launch confirmation."
"""
from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta

from app.config import get_settings
from app.models import Campaign, CampaignCall, CampaignContact
from app.modules.campaigns import service

SECRET = "vapi-test-secret-0123456789abcdef"


def _ready(api, t, monkeypatch, *, key: bool):
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
    api.map_number(ws, "+4570123456", "pn_qa_out", outbound=True)


def _campaign(api, t, csv="Mette Hansen;20304050"):
    tok, ws = t["tok_a"], t["ws_a"]
    r = api.post(tok, f"/workspaces/{ws}/campaigns", {"name": "QA-EB kampagne", "purpose": "Tilbyde gulvafslibning",
                                                       "call_days": list(service.DAYS), "call_from": "00:00", "call_to": "23:59"})
    assert r.status_code == 201, r.text
    c = r.json()
    imp = api.post(tok, f"/workspaces/{ws}/campaigns/{c['id']}/contacts/import",
                   {"csv": csv, "kind": "business", "consent_source": "Tilmelding på hjemmesiden, marts 2026"})
    assert imp.status_code == 200, imp.text
    return imp.json()["campaign"]


def test_c11_launch_needs_explicit_confirmation_and_capability(api, two_workspaces, db, monkeypatch):
    """No automatic launch: draft stays draft until an admin confirms the legal checklist and the shown maximum,
    and an unconfigured outbound capability blocks activation (honest 501), with nothing dialled."""
    t = two_workspaces
    tok, ws = t["tok_a"], t["ws_a"]
    _ready(api, t, monkeypatch, key=False)
    c = _campaign(api, t)
    start = f"/workspaces/{ws}/campaigns/{c['id']}/start"
    body = {"expected_version": c["version"], "legal_confirmed": True, "accept_max_net_minor": c["max_cost"]["net_minor"]}
    # missing confirmation, stale version, price below the shown maximum: refused
    assert api.post(tok, start, body | {"legal_confirmed": False}).status_code == 422
    assert api.post(tok, start, body | {"expected_version": c["version"] - 1}).json()["code"] == "version_conflict"
    assert api.post(tok, start, body | {"accept_max_net_minor": c["max_cost"]["net_minor"] - 1}).json()["code"] == "price_changed"
    # DB-018: capability not available -> activation is refused honestly
    r = api.post(tok, start, body)
    assert r.status_code == 501 and r.json()["code"] == "outbound_not_configured"
    caps = {x["key"]: x["status"] for x in api.get(tok, "/integrations/capabilities").json()["items"]}
    assert caps["telephony.outbound"] == "not_implemented"
    assert api.get(tok, f"/workspaces/{ws}/campaigns/{c['id']}").json()["status"] == "draft"
    # the dialler never touches a draft campaign
    called = []
    monkeypatch.setattr(service, "create_call", lambda p: called.append(p) or {"id": "x"})
    assert service.dispatch(db, datetime.now(UTC)) == 0 and called == []
    # staff (not admin) can never start
    staff = api.add_member(tok, ws, "staff-qa-eb@testmail.dk", "staff")
    assert api.post(staff, start, body).status_code == 403
    get_settings.cache_clear()


def test_c11_confirmation_is_frozen_with_the_run(api, two_workspaces, db, monkeypatch):
    """Frozen versions: once running, the script cannot be changed; the confirmation records the accepted maximum
    and the legal text version; resuming after pause needs a new confirmation of the current version."""
    t = two_workspaces
    tok, ws = t["tok_a"], t["ws_a"]
    _ready(api, t, monkeypatch, key=True)
    c = _campaign(api, t)
    start = f"/workspaces/{ws}/campaigns/{c['id']}/start"
    r = api.post(tok, start, {"expected_version": c["version"], "legal_confirmed": True,
                              "accept_max_net_minor": c["max_cost"]["net_minor"]})
    assert r.status_code == 200, r.text
    run = r.json()
    assert run["legal_confirmation"]["text_version"] == service.LEGAL_TEXT_VERSION
    assert run["legal_confirmation"]["accepted_max_net_minor"] == c["max_cost"]["net_minor"]
    assert api.put(tok, f"/workspaces/{ws}/campaigns/{c['id']}", {"name": "ændret", "expected_version": run["version"]}).status_code == 409
    # double start is refused (no second launch)
    again = api.post(tok, start, {"expected_version": run["version"], "legal_confirmed": True,
                                  "accept_max_net_minor": run["max_cost"]["net_minor"]})
    assert again.status_code == 409
    paused = api.post(tok, f"/workspaces/{ws}/campaigns/{c['id']}/pause").json()
    assert paused["status"] == "paused"
    # resuming with the version seen before pause is refused
    stale = api.post(tok, start, {"expected_version": run["version"], "legal_confirmed": True,
                                  "accept_max_net_minor": run["max_cost"]["net_minor"]})
    assert stale.status_code == 409 and stale.json()["code"] == "version_conflict"
    get_settings.cache_clear()


def test_c11_no_blind_redial_after_provider_timeout(api, two_workspaces, db, monkeypatch):
    """DB-007 (no blind new write after timeout) for outbound calls, and the campaign promise
    'each contact is dialled at most max_attempts times' (campaigns/service.py docstring).

    When Vapi's POST /call times out, the call may well have been placed. The dialler must not treat that as
    'nothing happened' and dial again and again: the number of dial requests sent for one contact must stay
    within max_attempts (or the contact must be held for reconciliation)."""
    t = two_workspaces
    tok, ws = t["tok_a"], t["ws_a"]
    _ready(api, t, monkeypatch, key=True)
    c = _campaign(api, t)
    r = api.post(tok, f"/workspaces/{ws}/campaigns/{c['id']}/start",
                 {"expected_version": c["version"], "legal_confirmed": True, "accept_max_net_minor": c["max_cost"]["net_minor"]})
    assert r.status_code == 200, r.text
    requests = []

    def timeout(payload):
        requests.append(payload["customer"]["number"])
        raise service.OutboundFailed("Telefontjenesten svarede ikke", extra={"no_response": True})

    monkeypatch.setattr(service, "create_call", timeout)
    now = datetime.combine(date.today(), time(8, 0), tzinfo=UTC)
    for i in range(6):  # six dialler passes, 31 minutes apart (the retry delay is 30 minutes)
        service.dispatch(db, now + timedelta(minutes=31 * i))
    db.expire_all()
    contact = db.query(CampaignContact).filter_by(phone="+4520304050").one()
    camp = db.get(Campaign, contact.campaign_id)
    assert len(requests) <= camp.max_attempts, (
        f"{len(requests)} dial requests sent to the same consumer/business after provider timeouts "
        f"(max_attempts={camp.max_attempts}); attempts counter={contact.attempts}, status={contact.status}, "
        f"campaign_calls={db.query(CampaignCall).filter_by(contact_id=contact.id).count()}")
    get_settings.cache_clear()

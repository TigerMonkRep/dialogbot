"""Internal sales channel, phase 2: contact basis, contact policy, internal campaigns, dispatch, test calls, webhook."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.config import get_settings
from app.core.errors import ApiError
from app.db import get_session_factory
from app.models import (
    Call,
    Campaign,
    CampaignContact,
    DoNotCall,
    SalesBlockList,
    SalesCallEvent,
    SalesCompany,
    SalesContact,
    SalesPolicyDecision,
    SalesQualification,
)
from app.modules.campaigns import service as campaigns
from app.modules.sales import playbook, policy
from app.modules.sales.outbound import NO_TOOLS_RULES
from tests.sales_fixtures import approve_knowledge

SECRET = "vapi-test-secret-0123456789abcdef"
TEST_NUMBER = "+4520304050"
OTHER_NUMBER = "+4561626364"
BASIS = {"purpose": "Demo af Dialogbot", "kind": "request", "source": "web_form",
         "text": "Ja tak, Peter fra Dialogbot (en AI-assistent) må ringe mig op om Dialogbot.",
         "text_version": "demo-call-web-v2", "evidence_ref": "test"}


@pytest.fixture
def ring(api, salg, db, monkeypatch):
    """Sales channel in test mode with a callable number, an approved script and a fake Vapi."""
    monkeypatch.setenv("SALES_OUTBOUND_MODE", "test")
    monkeypatch.setenv("SALES_TEST_NUMBERS", f"{TEST_NUMBER}, 20 30 40 51")
    monkeypatch.setenv("VAPI_API_KEY", "vapi-private-key-test")
    monkeypatch.setenv("VAPI_SERVER_SECRET", SECRET)
    monkeypatch.setenv("SALES_MAX_ATTEMPTS_PER_CONTACT", "2")
    get_settings.cache_clear()
    approve_knowledge(api, salg["tok"], salg["ws"], "fact", "Telefonpasning", {"text": "Dialogbot tager telefonen."})
    api.map_number(salg["ws"], "+4570123456", "pn_sales", outbound=True)
    company = SalesCompany(source="demo", display_name="Salon Fiktiv", website_url="https://salon-fiktiv.invalid/",
                           domain="salon-fiktiv.invalid", postal_code="8000", city="Aarhus C", industry_key="skoenhed",
                           industry_text="Frisør & skønhed", google_business_status="OPERATIONAL",
                           advertising_protected=False)
    db.add(company)
    db.flush()
    from app.modules.sales import companies

    fact = companies.add_fact(db, company, field="service", value="Dameklip", ref="https://salon-fiktiv.invalid/",
                              evidence="Dameklip", extractor="sales-research-v1")
    companies.set_main_phone(db, company, TEST_NUMBER, fact)
    profile = playbook.build_profile(db, company, user_id=None)
    script = playbook.build_script(db, company, profile, user_id=None)
    assert script.validation["ok"], script.validation
    db.commit()
    op_user = db.scalar(select(SalesContact).where(SalesContact.company_id == company.id))
    playbook.approve(db, script, user_id=_op_id(db))
    db.commit()
    calls: list[dict] = []

    def fake_call(payload):
        # the attempt is committed as `calling` with its dispatch key BEFORE the provider is asked
        with get_session_factory()() as other:
            cc = other.get(CampaignContact, payload["metadata"]["campaign_contact_id"])
            assert cc.status == "calling" and cc.dispatch_key == payload["metadata"]["dispatch_key"]
        calls.append(payload)
        return {"id": f"sales_call_{len(calls)}"}

    monkeypatch.setattr(campaigns, "create_call", fake_call)
    yield salg | {"company": company, "script": script, "contact": op_user, "calls": calls}
    get_settings.cache_clear()


def _op_id(db):
    from app.models import User

    return db.scalar(select(User.id).where(User.email_normalized == "operator@testmail.dk"))


def _basis(api, op, contact_id, **extra):
    r = api.post(op, f"/operator/salg/contacts/{contact_id}/basis", BASIS | extra)
    assert r.status_code == 201, r.text
    return r.json()


def _campaign(api, op, **extra):
    body = {"name": "Test Aarhus frisører", "call_days": ["mon", "tue", "wed", "thu", "fri", "sat", "sun"],
            "call_from": "00:00", "call_to": "23:59"} | extra
    r = api.post(op, "/operator/salg/campaigns", body)
    assert r.status_code == 201, r.text
    return r.json()


def _report(client, call_id, messages, reason="customer-ended-call"):
    return client.post("/api/v1/webhooks/vapi", headers={"authorization": f"Bearer {SECRET}"}, json={"message": {
        "type": "end-of-call-report", "endedReason": reason, "durationSeconds": 95,
        "call": {"id": call_id, "phoneNumberId": "pn_sales", "type": "outboundPhoneCall",
                 "customer": {"number": TEST_NUMBER}},
        "artifact": {"messages": messages}}}).json()


def test_unknown_basis_is_never_allow_and_a_registered_one_is(api, ring, db):
    op, contact = ring["op"], ring["contact"]
    r = api.post(op, f"/operator/salg/contacts/{contact.id}/check").json()
    assert r["result"] == "BLOCK" and "no_basis" in r["reasons"]
    assert api.post(op, f"/operator/salg/contacts/{contact.id}/basis", BASIS | {"text": "kort"}).status_code == 422
    b = _basis(api, op, contact.id)
    assert b["valid"] and b["source"] == "web_form"
    r = api.post(op, f"/operator/salg/contacts/{contact.id}/check").json()
    assert r["result"] == "ALLOW", r
    assert db.scalar(select(SalesPolicyDecision).where(SalesPolicyDecision.contact_id == contact.id,
                                                       SalesPolicyDecision.result == "ALLOW")) is not None
    # advertising protection unknown → never ALLOW; a manual CVR check makes it known
    company = db.get(SalesCompany, ring["company"].id)
    company.advertising_protected = None
    db.commit()
    assert api.post(op, f"/operator/salg/contacts/{contact.id}/check").json()["result"] == "NEEDS_REVIEW"
    api.post(op, f"/operator/salg/companies/{company.id}/advertising-check",
             {"advertising_protected": True, "note": "datacvr.virk.dk 30/10"})
    r = api.post(op, f"/operator/salg/contacts/{contact.id}/check").json()
    assert r["result"] == "BLOCK" and "advertising_protected" in r["reasons"]


def test_test_mode_only_rings_test_numbers_and_live_rules(api, ring, db, monkeypatch):
    op, company = ring["op"], ring["company"]
    other = api.post(op, f"/operator/salg/companies/{company.id}/contacts", {"role": "Indehaver", "phone": "61 62 63 64"}).json()
    _basis(api, op, other["id"])
    r = api.post(op, f"/operator/salg/contacts/{other['id']}/check").json()
    assert r["result"] == "BLOCK" and r["reasons"] == ["not_test_number"]
    monkeypatch.setenv("SALES_OUTBOUND_MODE", "simulation")
    get_settings.cache_clear()
    assert "mode_off" in api.post(op, f"/operator/salg/contacts/{other['id']}/check").json()["reasons"]
    r = api.post(op, "/operator/salg/test-calls", {"company_id": str(company.id), "script_id": str(ring["script"].id),
                                                    "phone": TEST_NUMBER, "accepted_test": True})
    assert r.status_code == 409 and r.json()["code"] == "sales_mode_not_allowed"
    monkeypatch.setenv("SALES_OUTBOUND_MODE", "test")
    get_settings.cache_clear()
    r = api.post(op, "/operator/salg/test-calls", {"company_id": str(company.id), "script_id": str(ring["script"].id),
                                                    "phone": OTHER_NUMBER, "accepted_test": True})
    assert r.status_code == 422 and r.json()["field_errors"][0]["field"] == "phone"
    assert ring["calls"] == []


def test_internal_test_call_rings_with_peter_and_the_script(api, ring, db):
    op = ring["op"]
    r = api.post(op, "/operator/salg/test-calls", {"company_id": str(ring["company"].id),
                                                    "script_id": str(ring["script"].id), "phone": "20 30 40 51",
                                                    "accepted_test": True})
    assert r.status_code == 201, r.text
    out = r.json()
    assert out["status"] == "calling" and out["provider_call_id"] == "sales_call_1", out
    payload = ring["calls"][0]
    a = payload["assistant"]
    assert payload["customer"]["number"] == "+4520304051"
    assert a["firstMessage"].startswith("Hej, det er Peter, AI-assistent hos Dialogbot")
    system = a["model"]["messages"][0]["content"]
    assert ring["script"].rendered_prompt in system and "Dialogbot tager telefonen" in system
    assert system.endswith(NO_TOOLS_RULES)  # no promised calendar look-ups or e-mails: Peter has no tools yet
    assert a["metadata"]["script_id"] == str(ring["script"].id) and a["maxDurationSeconds"] == 600
    assert a["voice"]["voiceId"]
    said = {r["regex"]: r["value"] for r in a["voice"]["chunkPlan"]["formatPlan"]["replacements"]}
    assert said["AI"] == "a i" and said[r"2\.495"] == "to tusind fire hundrede og femoghalvfems"
    snap = db.scalar(select(SalesCallEvent).where(SalesCallEvent.event_type == "assistant_snapshot"))
    assert snap.payload["rendered_prompt"] == ring["script"].rendered_prompt
    c = db.get(Campaign, out["campaign_id"])
    assert c.kind == "internal_sales" and c.is_test
    # customers never see internal campaigns
    assert api.get(ring["tok"], f"/workspaces/{ring['ws']}/campaigns").json()["items"] == []
    assert api.get(ring["tok"], f"/workspaces/{ring['ws']}/campaigns/{c.id}").status_code == 404


def test_campaign_preview_start_and_policy_at_dispatch(api, ring, db, client):
    op, contact = ring["op"], ring["contact"]
    camp = _campaign(api, op, budget_net_minor=10_000)
    r = api.post(op, f"/operator/salg/campaigns/{camp['id']}/members", {"company_ids": [str(ring["company"].id)]}).json()
    assert r["added"][0]["decision"] == "BLOCK"  # no basis yet
    detail = api.get(op, f"/operator/salg/campaigns/{camp['id']}").json()
    assert detail["preview"]["counts"] == {"ALLOW": 0, "BLOCK": 1, "NEEDS_REVIEW": 0}
    assert detail["preview"]["reasons"]["no_basis"]["count"] == 1
    r = api.post(op, f"/operator/salg/campaigns/{camp['id']}/start", {"accepted_max_net_minor": 999_999})
    assert r.status_code == 409 and r.json()["code"] == "nothing_allowed"
    b = _basis(api, op, contact.id)
    p = api.get(op, f"/operator/salg/campaigns/{camp['id']}").json()["preview"]
    assert p["counts"]["ALLOW"] == 1 and p["max_cost_net_minor"] == 2 * (400 + 10 * 200)
    r = api.post(op, f"/operator/salg/campaigns/{camp['id']}/start", {"accepted_max_net_minor": 100})
    assert r.status_code == 409 and r.json()["code"] == "preview_not_accepted"
    assert api.post(op, f"/operator/salg/campaigns/{camp['id']}/start",
                    {"accepted_max_net_minor": p["max_cost_net_minor"]}).json()["status"] == "running"
    # the basis is withdrawn after planning but before dispatch: no call
    api.post(op, f"/operator/salg/basis/{b['id']}/withdraw", {"reason": "Kontakten trak sit ja tilbage"})
    campaigns.dispatch(db)
    assert ring["calls"] == []
    cc = db.scalar(select(CampaignContact).where(CampaignContact.campaign_id == camp["id"]))
    db.refresh(cc)
    assert cc.status == "skipped" and "kontaktgrundlag" in cc.error


def test_attempts_across_campaigns_and_budget(api, ring, db, monkeypatch):
    op, contact = ring["op"], ring["contact"]
    _basis(api, op, contact.id)
    contact_row = db.get(SalesContact, contact.id)
    for i in range(2):
        camp = _campaign(api, op, name=f"Runde {i}")
        api.post(op, f"/operator/salg/campaigns/{camp['id']}/members", {"contact_ids": [str(contact.id)]})
        cc = db.scalar(select(CampaignContact).where(CampaignContact.campaign_id == camp["id"]))
        cc.attempts = 1
        db.commit()
    d = policy.evaluate(db, contact=contact_row, stage="check", script=ring["script"], store=False)
    assert d.result == "BLOCK" and "max_attempts" in d.reasons
    # budget: a campaign whose ceiling is below one attempt never dials
    db.execute(CampaignContact.__table__.update().values(attempts=0))
    db.commit()
    camp = _campaign(api, op, name="Lille budget", budget_net_minor=100)
    api.post(op, f"/operator/salg/campaigns/{camp['id']}/members", {"contact_ids": [str(contact.id)]})
    d = policy.evaluate(db, contact=contact_row, campaign=db.get(Campaign, camp["id"]), stage="check",
                        script=ring["script"], store=False)
    assert "budget" in d.reasons


def test_existing_customer_and_block_list_block(api, ring, db):
    op, contact = ring["op"], ring["contact"]
    _basis(api, op, contact.id)
    r = api.post(op, "/operator/salg/block-list", {"kind": "domain", "value": "https://www.salon-fiktiv.invalid/x",
                                                   "reason": "Bad os lade være"})
    assert r.status_code == 201 and r.json()["value"] == "salon-fiktiv.invalid"
    assert "blocked_domain" in api.post(op, f"/operator/salg/contacts/{contact.id}/check").json()["reasons"]
    db.execute(SalesBlockList.__table__.delete())
    company = db.get(SalesCompany, ring["company"].id)
    company.existing_customer_workspace_id = ring["t"]["ws_b"]
    db.commit()
    assert "existing_customer" in api.post(op, f"/operator/salg/contacts/{contact.id}/check").json()["reasons"]


def test_no_answer_from_vapi_is_unknown_and_never_redialled(api, ring, db, monkeypatch):
    op, contact = ring["op"], ring["contact"]
    _basis(api, op, contact.id)
    camp = _campaign(api, op)
    api.post(op, f"/operator/salg/campaigns/{camp['id']}/members", {"contact_ids": [str(contact.id)]})
    p = api.get(op, f"/operator/salg/campaigns/{camp['id']}").json()["preview"]
    api.post(op, f"/operator/salg/campaigns/{camp['id']}/start", {"accepted_max_net_minor": p["max_cost_net_minor"]})
    tries = []

    def timeout(payload):
        tries.append(payload)
        raise campaigns.OutboundFailed("Telefontjenesten svarede ikke", extra={"no_response": True})

    monkeypatch.setattr(campaigns, "create_call", timeout)
    campaigns.dispatch(db)
    campaigns.dispatch(db, now=datetime.now(UTC) + timedelta(hours=4))
    assert len(tries) == 1
    cc = db.scalar(select(CampaignContact).where(CampaignContact.campaign_id == camp["id"]))
    db.refresh(cc)
    assert cc.status == "unknown" and cc.dispatch_key and "Uvist" in cc.error
    calls = api.get(op, "/operator/salg/calls").json()["items"]
    assert calls[0]["status"] == "unknown"


def test_report_stores_outcome_accepts_and_opt_out_blocks(api, ring, db, client):
    op = ring["op"]
    out = api.post(op, "/operator/salg/test-calls", {"company_id": str(ring["company"].id),
                                                      "script_id": str(ring["script"].id), "phone": TEST_NUMBER,
                                                      "accepted_test": True}).json()
    sent = client.post("/api/v1/webhooks/vapi", headers={"authorization": f"Bearer {SECRET}"},
                       json={"message": {"type": "status-update", "status": "ringing", "call": {"id": "sales_call_1"}}})
    assert sent.json()["outcome"] == "stored"
    msgs = [{"role": "bot", "message": "Hej, det er Peter, AI-assistent hos Dialogbot."},
            {"role": "user", "message": "Ja, det ville gøre en forskel."},
            {"role": "bot", "message": "Det koster 2.495 kroner om måneden ekskl. moms."},
            {"role": "user", "message": "Ring ikke igen."}]
    r = _report(client, "sales_call_1", msgs)
    assert r["duplicate"] is False, r
    assert _report(client, "sales_call_1", msgs)["duplicate"] is True
    call = db.scalar(select(Call).where(Call.provider_call_id == "sales_call_1"))
    assert call.direction == "outbound" and call.campaign_contact_id is not None and call.outcome == "opt_out"
    assert call.script_id == ring["script"].id and call.recording_status == "NOT_RECORDED"
    quals = db.scalars(select(SalesQualification).where(SalesQualification.call_id == call.id)).all()
    by_no = {q.accept_no: q for q in quals}
    assert by_no[2].result == "JA" and by_no[2].quote == "Ja, det ville gøre en forskel."
    assert by_no[5].result == "IKKE_AFKLARET" and by_no[5].quote is None  # an invented quote is not evidence
    assert db.scalar(select(SalesBlockList).where(SalesBlockList.kind == "phone", SalesBlockList.value == TEST_NUMBER))
    assert db.scalar(select(DoNotCall).where(DoNotCall.phone == TEST_NUMBER))
    detail = api.get(op, f"/operator/salg/calls/{out['campaign_contact_id']}").json()
    assert [m["speaker"] for m in detail["messages"]] == ["peter", "kunde", "peter", "kunde"]
    assert {e["type"] for e in detail["events"]} >= {"assistant_snapshot", "created", "status-update", "end-of-call-report"}
    assert detail["call"]["outcome"] == "opt_out"
    assert api.get(op, "/operator/salg/calls?q=forskel").json()["items"][0]["campaign_contact_id"] == out["campaign_contact_id"]
    # after the opt-out the number is blocked for every later test call
    again = api.post(op, "/operator/salg/test-calls", {"company_id": str(ring["company"].id),
                                                        "script_id": str(ring["script"].id), "phone": TEST_NUMBER,
                                                        "accepted_test": True}).json()
    assert again["status"] == "skipped" and len(ring["calls"]) == 1


def test_stop_skips_pending_and_routes_need_an_operator(api, ring, db):
    op, contact = ring["op"], ring["contact"]
    camp = _campaign(api, op)
    api.post(op, f"/operator/salg/campaigns/{camp['id']}/members", {"contact_ids": [str(contact.id)]})
    out = api.post(op, f"/operator/salg/campaigns/{camp['id']}/stop").json()
    assert out["status"] == "stopped"
    cc = db.scalar(select(CampaignContact).where(CampaignContact.campaign_id == camp["id"]))
    assert cc.status == "skipped" and cc.error == "stopped"
    tok = ring["tok"]
    for path in ("/operator/salg/campaigns", "/operator/salg/calls", "/operator/salg/block-list"):
        assert api.get(tok, path).status_code == 403
    assert api.post(tok, "/operator/salg/test-calls", {}).status_code == 403
    with pytest.raises(ApiError):
        from app.modules.sales import outbound

        outbound.stop(db, db.get(Campaign, camp["id"]))

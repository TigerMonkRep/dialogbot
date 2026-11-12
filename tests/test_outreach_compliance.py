"""The ComplianceEngine decides before anything else: blocked markets never reach Claude, corporate-only markets
reject webmail and sole traders, held markets wait for a lawyer, and forbidden channels are refused everywhere."""
from __future__ import annotations

import pytest
from sqlalchemy import select

from app.models import OutreachCallQueue, OutreachLead, OutreachLog, OutreachMessage
from app.modules.outreach import llm
from app.modules.outreach.compliance import Action, Clearance, ComplianceBlocked, ComplianceEngine, LeadFacts
from app.modules.outreach.schemas import LeadBrief
from tests.outreach_fixtures import env, raw, run

BLOCKED = ["DK", "DE", "NL", "AT", "IT", "CH", "BE"]


def facts(country, email="info@firma.example", company="Firma GmbH", **kw) -> LeadFacts:
    return LeadFacts(company_name=company, email=email, country=country, **kw)


@pytest.mark.parametrize("country", BLOCKED)
def test_opt_in_markets_are_blocked_and_no_clearance_exists(db, country):
    d = ComplianceEngine(db).evaluate(facts(country))
    assert d.action is Action.BLOCK and not d.allowed
    with pytest.raises(ComplianceBlocked):
        d.clearance()


@pytest.mark.parametrize("country", ["DK", "DE", "NL", "AT", "IT"])
def test_a_blocked_lead_costs_no_claude_tokens_and_gets_no_email(db, outreach, country):
    company = "Nordjysk VVS ApS" if country == "DK" else "Firma GmbH"
    rep = run(db, [raw(country, email=f"info@firma-{country.lower()}.example", company=company, registration_number="25632710")])
    assert outreach.calls == []                                   # not one request to the model
    assert db.scalars(select(OutreachMessage)).all() == []        # no e-mail was written
    assert db.scalars(select(OutreachLog).where(OutreachLog.kind == "llm_usage")).all() == []
    lead = rep["leads"][0]
    if country == "DK":
        assert lead["status"] == "call_queue" and lead["call_queue"]["scrub_status"] == "cleared"
    else:
        assert lead["status"] == "blocked" and lead["call_queue"] is None


def test_denmark_goes_to_the_manual_call_list_only_as_aps_or_as_with_a_clean_cvr(db, outreach):
    rep = run(db, [
        raw("DK", email="a@vvs.example", company="Nordjysk VVS ApS", registration_number="25632710"),
        raw("DK", email="b@smed.example", company="Hansens Smedje A/S", registration_number="10000009"),
        raw("DK", email="c@enkelt.example", company="Jens Jensen VVS", registration_number="10000017"),   # not ApS/A/S
        raw("DK", email="d@nocvr.example", company="Uden Nummer ApS"),                                   # no CVR
    ], cvr_lookup=lambda cvr: {"25632710": False, "10000009": True}.get(cvr))
    by = {x["email"]: x for x in rep["leads"]}
    assert by["a@vvs.example"]["status"] == "call_queue"
    assert by["b@smed.example"]["status"] == "blocked"            # reklamebeskyttet in the register
    assert "reklamebeskyttet" in " ".join(by["b@smed.example"]["compliance"]["reasons"])
    assert by["c@enkelt.example"]["status"] == "blocked" and by["d@nocvr.example"]["status"] == "blocked"
    assert [q.company_name for q in db.scalars(select(OutreachCallQueue))] == ["Nordjysk VVS ApS"]
    assert outreach.calls == []


def test_denmark_without_register_access_is_queued_for_review_and_left_out_of_the_export(db, outreach, api):
    run(db, [raw("DK", email="a@vvs.example", company="Nordjysk VVS ApS", registration_number="25632710")],
        cvr_lookup=lambda _c: None)
    assert db.scalars(select(OutreachCallQueue)).one().scrub_status == "needs_review"
    op = api.operator()
    assert "Nordjysk" not in api.get(op, "/operator/outreach/call-queue.csv").text
    assert "Nordjysk" in api.get(op, "/operator/outreach/call-queue.csv?include_needs_review=true").text


@pytest.mark.parametrize("email", ["dave@gmail.com", "dave@yahoo.com", "dave@hotmail.com", "dave@outlook.com"])
def test_uk_webmail_is_rejected(db, outreach, email):
    d = ComplianceEngine(db).evaluate(facts("UK", email=email, company="Dave's Plumbing Ltd"))
    assert d.action is Action.BLOCK and "webmail" in d.reasons[0]
    rep = run(db, [raw("UK", email=email, company="Dave's Plumbing Ltd")])
    assert rep["leads"][0]["status"] == "blocked" and outreach.calls == []


def test_uk_takes_corporate_subscribers_only(db):
    e = ComplianceEngine(db)
    assert e.evaluate(facts("UK", company="Dave's Mobile Mechanics")).action is Action.BLOCK       # sole trader
    assert e.evaluate(facts("UK", company="Smith & Sons")).action is Action.BLOCK                  # partnership
    for name in ("Harrow Heating Ltd", "Harrow Heating Limited", "Pennine Dental LLP", "Bristol Motors PLC", "Acme Ltd."):
        assert e.evaluate(facts("GB", company=name)).action is Action.EMAIL, name                  # GB = UK


def test_the_us_allows_webmail_and_any_business_form(db):
    assert ComplianceEngine(db).evaluate(facts("US", email="shop@gmail.com", company="Lone Star Auto")).allowed


def test_spain_and_poland_wait_for_legal_sign_off(db, outreach, monkeypatch):
    rep = run(db, [raw("ES", email="info@rivas.example", company="Fontanería Rivas SL"),
                   raw("PL", email="biuro@hydro.example", company="Hydro Sp. z o.o.")])
    assert [x["status"] for x in rep["leads"]] == ["held", "held"] and outreach.calls == []
    env(monkeypatch, OUTREACH_SIGNED_OFF_MARKETS="ES")
    e = ComplianceEngine(db)
    assert e.evaluate(facts("ES", company="Rivas SL")).allowed
    assert e.evaluate(facts("PL", company="Hydro Sp. z o.o.")).action is Action.HOLD


def test_market_specific_rules(db):
    e = ComplianceEngine(db)
    pub = dict(email_source="published_website", email_source_url="https://x.example/contact")
    assert e.evaluate(facts("CA", company="Maple HVAC Inc")).action is Action.BLOCK           # no published source
    assert e.evaluate(facts("CA", company="Maple HVAC Inc", **pub)).allowed
    assert e.evaluate(facts("AU", company="Bondi Dental Pty Ltd", email_source="directory")).action is Action.BLOCK
    assert e.evaluate(facts("AU", company="Bondi Dental Pty Ltd", **pub)).allowed
    assert e.evaluate(facts("NO", email="ola.nordmann@ror.example", company="Rør AS")).action is Action.BLOCK
    assert e.evaluate(facts("NO", email="post@ror.example", company="Rør AS")).allowed
    assert e.evaluate(facts("SE", email="anna@gmail.com", company="Rör AB")).action is Action.BLOCK
    for ok in ("SE", "FR", "IE"):
        assert e.evaluate(facts(ok, company="Firma AB")).allowed
    for unknown in ("", "XX", "BR", "FI"):
        assert e.evaluate(facts(unknown)).action is Action.BLOCK                               # unknown is never allowed


@pytest.mark.parametrize("channel", ["sms", "dm", "ai_voice", "voice", "whatsapp", "fax"])
def test_only_email_is_ever_automated(db, channel):
    assert ComplianceEngine(db).evaluate(facts("US", company="Brightwater LLC"), channel=channel).action is Action.BLOCK


def test_the_model_cannot_be_called_without_a_clearance(db, outreach):
    with pytest.raises(ComplianceBlocked):
        Clearance(email="x@y.example", country="US")              # cannot be made by hand
    for bogus in (None, object(), "US"):
        with pytest.raises(ComplianceBlocked):
            llm.structured(db, clearance=bogus, purpose="research", model="m", system="s", user="u", output=LeadBrief,
                           tool_name="submit_lead_brief", tool_description="d")
    assert outreach.calls == []


def test_every_decision_is_stored_with_its_reasons(db, outreach):
    run(db, [raw("DE", email="info@mueller.example", company="Müller GmbH")])
    lead = db.scalars(select(OutreachLead)).one()
    assert lead.compliance_action == "BLOCK" and lead.compliance["ruleset"] == "outreach-compliance-v1"
    log = db.scalars(select(OutreachLog).where(OutreachLog.kind == "compliance")).one()
    assert log.outcome == "BLOCK" and "opt-in market" in log.detail["reasons"][0]

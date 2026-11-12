"""Research → copy → audit with the Anthropic client mocked: what a passing e-mail must contain, what gets a lead or an
e-mail rejected, and that tokens are logged."""
from __future__ import annotations

import anthropic
import httpx
import pytest
from sqlalchemy import select

from app.models import OutreachLead, OutreachLog, OutreachMessage
from app.modules.outreach import llm, localization
from tests.outreach_fixtures import PAIN, env, raw, run

UK = dict(email="info@harrowheating.example", company="Harrow Heating Ltd")
GOOD = {"subject": "calls at Brightwater",
        "line1": 'One reviewer wrote: "I called three times and it went to voicemail every time."',
        "line2": "Dialogbot answers in under 2 seconds, books into Google Calendar or Microsoft 365 and sends an SMS confirmation.",
        "line3": "Try the live 90-second callback demo at https://dialogbot.app – no signup, no credit card."}


def test_us_and_uk_leads_come_out_audited_with_the_right_footer(db, outreach):
    rep = run(db, [raw("US"), raw("UK", **UK)])
    us, uk = rep["leads"]
    for lead in (us, uk):
        d = lead["email_draft"]
        assert lead["status"] == "queued" and d["status"] == "queued" and d["audit"]["passed"] is True
        assert d["audit"]["model"]["ran"] is True and d["audit"]["model"]["verdict"] == "pass"
        assert d["words"] < 90 and d["words"] == len(d["body"].split())
        assert "Dialogbot, CVR 25632710, Aarhus, Denmark" in d["footer"]
        assert d["footer"].count("{{unsubscribe_link}}") == 1 and "{{unsubscribe_link}}" not in d["body"]
        assert "https://dialogbot.app" in d["body"] and "peter" not in (d["body"] + d["subject"]).lower()
        assert len(d["body"].split("\n\n")) == 3
    assert "commercial message" in us["email_draft"]["footer"]                       # CAN-SPAM
    assert "legitimate interest" in uk["email_draft"]["footer"] and "Harrow Heating Ltd" in uk["email_draft"]["footer"]
    assert "Opt out" in uk["email_draft"]["footer"] and "on your company's website" in uk["email_draft"]["footer"]


def test_the_three_agents_use_their_own_models_and_tokens_are_logged(db, outreach, monkeypatch):
    env(monkeypatch, CLAUDE_RESEARCH_MODEL="research-m", CLAUDE_WRITER_MODEL="writer-m", CLAUDE_AUDITOR_MODEL="haiku-m")
    rep = run(db, [raw("US")])
    assert [(c["tools"][0]["name"], c["model"]) for c in outreach.calls] == [
        ("submit_lead_brief", "research-m"), ("submit_email", "writer-m"), ("submit_audit", "haiku-m")]
    assert all(c["tool_choice"] == {"type": "tool", "name": c["tools"][0]["name"]} for c in outreach.calls)
    logs = db.scalars(select(OutreachLog).where(OutreachLog.kind == "llm_usage").order_by(OutreachLog.created_at)).all()
    assert [x.detail["purpose"] for x in logs] == ["research", "copy", "audit"]
    assert all(x.detail["input_tokens"] > 0 and x.detail["output_tokens"] > 0 for x in logs)
    assert rep["tokens"]["input_tokens"] == sum(x.detail["input_tokens"] for x in logs)
    assert rep["leads"][0]["tokens"]["calls"] == 3


def test_web_search_is_offered_to_the_research_agent_only_when_enabled(db, outreach, monkeypatch):
    env(monkeypatch, OUTREACH_WEB_SEARCH="true")
    run(db, [raw("US")])
    research, writer = outreach.calls[0], outreach.calls[1]
    assert research["tools"][1]["type"].startswith("web_search") and research["tool_choice"] == {"type": "auto"}
    assert len(writer["tools"]) == 1


def test_a_generic_lead_is_rejected_below_the_confidence_threshold(db, outreach):
    rep = run(db, [raw("US", context="Family plumbing company in Austin since 2009.")])
    lead = rep["leads"][0]
    assert lead["status"] == "low_confidence" and lead["confidence"] < 0.6 and lead["email_draft"] is None
    assert [c["tools"][0]["name"] for c in outreach.calls] == ["submit_lead_brief"]   # nothing was written or audited


def test_a_review_quote_the_model_made_up_is_dropped_and_sinks_the_lead(db, outreach):
    outreach.overrides["submit_lead_brief"] = {
        "business_summary": "Plumber in Austin", "is_business": True, "call_handling": "unknown",
        "call_handling_evidence": "", "ticket_value": {"low": 150, "high": 600, "currency": "USD", "basis": "niche"},
        "review_snippets": [{"quote": "They never pick up the phone, worst service ever", "source_type": "google_review"}],
        "personalization_hook": "Reviewers say they never pick up", "confidence_score": 0.95}
    rep = run(db, [raw("US")])
    lead = db.scalars(select(OutreachLead)).one()
    assert rep["leads"][0]["status"] == "low_confidence" and lead.confidence_score == 0.4
    assert lead.brief["review_snippets"] == []
    assert db.scalars(select(OutreachMessage)).all() == []


def test_a_private_person_is_not_written_to(db, outreach):
    outreach.overrides["submit_lead_brief"] = {
        "business_summary": "A private person", "is_business": False, "call_handling": "voicemail",
        "call_handling_evidence": "voicemail", "ticket_value": {"low": 0, "high": 0, "currency": "USD", "basis": "-"},
        "review_snippets": [], "personalization_hook": "x", "confidence_score": 0.9}
    assert run(db, [raw("US")])["leads"][0]["status"] == "disqualified"
    assert len(outreach.calls) == 1


@pytest.mark.parametrize("change, issue", [
    ({"line2": GOOD["line2"] + " Peter will call you."}, "b2c: 'Peter'"),
    ({"line2": GOOD["line2"] + " Also great for private users."}, "b2c"),
    ({"line1": "Hope this finds you well! " + GOOD["line1"]}, "opener"),
    ({"line1": "My name is Sam and I run sales here."}, "opener"),
    ({"line3": GOOD["line3"] + " Or book a call with me for a 30-minute walkthrough."}, "meeting_push"),
    ({"line3": "See https://bit.ly/demo and https://dialogbot.app"}, "links"),
    ({"line3": "Reply and I will send details, no signup needed."}, "cta"),
    ({"line2": GOOD["line2"] + " It is $199/mo."}, "price"),
    ({"line2": GOOD["line2"] + " We guarantee more bookings."}, "claim"),
    ({"line2": GOOD["line2"] + " Call +1 512 555 0100 to hear it."}, "phone"),
    ({"line2": GOOD["line2"] + " Unsubscribe: {{unsubscribe_link}}"}, "footer"),
    ({"line2": "**Dialogbot** answers in under 2 seconds."}, "plain_text"),
    ({"subject": "Re: your missed calls"}, "subject"),
    ({"line2": GOOD["line2"] + " so" * 75}, "word_count"),
])
def test_the_deterministic_audit_rejects(db, outreach, change, issue):
    outreach.overrides["submit_email"] = {**GOOD, **change}
    d = run(db, [raw("US")])["leads"][0]
    assert d["status"] == "audit_failed" and d["email_draft"]["status"] == "rejected"
    assert any(i.startswith(issue) for i in d["email_draft"]["audit"]["issues"]), d["email_draft"]["audit"]["issues"]
    assert d["email_draft"]["audit"]["model"] == {"ran": False}                      # Haiku is not paid for a sure reject
    assert "submit_audit" not in [c["tools"][0]["name"] for c in outreach.calls]


def test_the_exact_copy_from_the_spec_passes(db, outreach):
    outreach.overrides["submit_email"] = {**GOOD, "line2": GOOD["line2"] + " From $349/mo."}
    assert run(db, [raw("US")])["leads"][0]["email_draft"]["audit"]["passed"] is True


def test_prices_follow_the_market(db, outreach):
    assert localization.locale_for("US").price == "$349/mo" and localization.locale_for("UK").price == "£275/mo"
    assert localization.locale_for("FR").price == "€329/mo"                           # the real EUR list price
    assert "kr" in localization.locale_for("SE").price
    outreach.overrides["submit_email"] = {**GOOD, "line2": GOOD["line2"] + " From $349/mo."}   # dollars to a UK firm
    d = run(db, [raw("UK", **UK)])["leads"][0]
    assert d["status"] == "audit_failed" and any(i.startswith("price") for i in d["email_draft"]["audit"]["issues"])


def test_a_local_number_may_only_be_mentioned_when_one_is_configured(db, outreach, monkeypatch):
    outreach.overrides["submit_email"] = {**GOOD, "line3": GOOD["line3"] + " It rings from +1 512 555 0100."}
    env(monkeypatch, OUTREACH_CALLBACK_NUMBER_US="+1 (512) 555-0100")
    assert run(db, [raw("US")])["leads"][0]["email_draft"]["audit"]["passed"] is True


def test_the_haiku_auditor_can_fail_an_email_the_rules_let_through(db, outreach):
    outreach.overrides["submit_audit"] = {"verdict": "fail", "issues": [
        {"category": "unsupported_personalization", "quote": "every time", "explanation": "Not in the evidence."}]}
    d = run(db, [raw("US")])["leads"][0]
    assert d["status"] == "audit_failed" and d["email_draft"]["audit"]["model"]["ran"] is True
    assert d["email_draft"]["audit"]["issues"][0].startswith("unsupported_personalization")


def test_daily_limits_per_inbox_defer_the_rest(db, outreach, monkeypatch):
    env(monkeypatch, OUTREACH_SENDER_INBOXES="a@send.example,b@send.example", OUTREACH_DAILY_LIMIT_PER_INBOX=1)
    rep = run(db, [raw("US", email=f"office@firm{i}.example", company=f"Firm {i} LLC") for i in range(3)])
    drafts = [x["email_draft"] for x in rep["leads"]]
    assert sorted(d["status"] for d in drafts) == ["deferred", "queued", "queued"]
    assert {d["sender_inbox"] for d in drafts if d["status"] == "queued"} == {"a@send.example", "b@send.example"}
    env(monkeypatch, OUTREACH_SENDER_INBOXES="a@send.example,b@send.example", OUTREACH_DAILY_LIMIT_PER_INBOX=5,
        OUTREACH_DAILY_LIMIT_PER_DOMAIN=2)
    from app.modules.outreach.agents.auditor import ComplianceAndSafetyAuditorAgent

    assert ComplianceAndSafetyAuditorAgent(db).queue_deferred() == 0                  # the sending domain is full too


def test_an_anthropic_outage_marks_the_lead_and_the_batch_goes_on(db, outreach):
    real = outreach.messages.create
    state = {"n": 0}

    def flaky(**kw):
        state["n"] += 1
        if state["n"] == 1:
            raise anthropic.APIConnectionError(request=httpx.Request("POST", "https://api.anthropic.com/v1/messages"))
        return real(**kw)

    outreach.messages.create = flaky
    rep = run(db, [raw("US"), raw("US", email="office@second.example", company="Second LLC")])
    assert [x["status"] for x in rep["leads"]] == ["error", "queued"]
    assert db.scalars(select(OutreachLog).where(OutreachLog.kind == "llm_usage", OutreachLog.outcome == "error")).one()


def test_an_answer_that_breaks_the_schema_gets_one_correction(db, outreach):
    real = outreach.messages.create
    seen = []

    def once_invalid(**kw):
        resp = real(**kw)
        seen.append(kw)
        if len(seen) == 1:
            resp.content[0].input = {"subject": "x"}                                  # invalid LeadBrief
        return resp

    outreach.messages.create = once_invalid
    assert run(db, [raw("US")])["leads"][0]["status"] == "queued"
    assert seen[1]["messages"][-1]["content"][0]["is_error"] is True


def test_the_real_sdk_client_is_built_with_retries(monkeypatch):
    env(monkeypatch, AI_PROVIDER="anthropic", ANTHROPIC_API_KEY="sk-ant-test", OUTREACH_AI_MAX_RETRIES=6)
    llm.set_client_override(None)
    c = llm._client()
    assert isinstance(c, anthropic.Anthropic) and c.max_retries == 6


def test_duplicates_and_other_countries_are_left_out(db, outreach):
    rep = run(db, [raw("US"), raw("US"), raw("FR", email="contact@plombier.example", company="Plombier SARL")], countries={"US"})
    assert len(rep["leads"]) == 1
    assert run(db, [raw("US")], batch="t2")["leads"] == []                             # already known from batch t1


def test_niche_and_mx_gate_the_lead_before_any_tokens(db, outreach):
    rep = run(db, [raw("US", niche="law firm"), raw("US", email="office@nomx.example", company="No MX LLC")],
              mx_check=lambda d: d != "nomx.example")
    assert [x["status"] for x in rep["leads"]] == ["disqualified", "disqualified"] and outreach.calls == []
    assert PAIN  # (fixture text used above)

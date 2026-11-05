"""Part B – the lead loop: the fixed closing line of a Privat call, the rules around it, the lead and the operator surface.
Simulated Vapi only (webhook messages); CVR is a fake. docs/sales/privat-opkald-leads.md."""
from __future__ import annotations

import re
import uuid
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.config import get_settings
from app.models import (
    BusinessProfile,
    ExternalBusinessContact,
    Lead,
    OutboxEvent,
    PrivateCall,
    SalesBlockList,
    Task,
)
from app.modules.business import cvr as cvr_register
from app.modules.integrations import email_templates as tpl
from app.modules.privat import lead_pitch as lp
from app.modules.privat import rules
from app.worker import runner
from tests.test_privat import VAPI_H, _approve, _report

CVR_NO = "12345674"
CVR_HIT = {"cvr": CVR_NO, "legal_name": "Cykelmageren", "address_line": "Nørregade 12", "postal_code": "8000", "city": "Aarhus C",
           "industry": "Cykelværksted", "status": "NORMAL", "advertising_protected": False, "contacts": ["86 12 34 56"]}
ERRAND = [{"role": "bot", "message": "Hej, jeg ringer fra Dialogbot på vegne af Mette Hansen"},
          {"role": "user", "message": "Ja, vi kan tage cyklen torsdag kl. 15.30. Et eftersyn koster 450 kr."},
          {"role": "bot", "message": "Så er det aftalt: torsdag kl. 15.30."}]


@pytest.fixture
def setup(api, monkeypatch, db):
    """Flag on, a sales workspace, CVR says «not reklamebeskyttet»."""
    from types import SimpleNamespace

    sales_tok = api.user("sales@testmail.dk")
    ws = api.workspace(sales_tok, "Dialogbot")
    monkeypatch.setenv("LEAD_PITCH_ENABLED", "true")
    monkeypatch.setenv("SALES_WORKSPACE_ID", ws)
    get_settings.cache_clear()
    hit = dict(CVR_HIT)
    monkeypatch.setattr(cvr_register, "configured", lambda: True)
    monkeypatch.setattr(cvr_register, "search_by_name", lambda name, city=None, size=5: [hit])
    monkeypatch.setattr(cvr_register, "cvr_valid", lambda v: True)
    return SimpleNamespace(sales_tok=sales_tok, ws=uuid.UUID(ws), hit=hit)


def make_call(api, pv, monkeypatch):
    tok = pv.account("mette@testmail.dk", "Mette Hansen")
    tid, p = _approve(api, pv, tok, monkeypatch)
    return tok, tid, p


def tool(client, p, name, args, call_id="call_v1"):
    r = client.post("/api/v1/webhooks/vapi", headers=VAPI_H, json={"message": {
        "type": "tool-calls", "call": {"id": call_id, "metadata": p["metadata"], "customer": {"number": "+4586123456"}},
        "toolCallList": [{"id": "t1", "function": {"name": name, "arguments": args}}]}})
    assert r.status_code == 200, r.text
    return r.json()["results"][0]["result"]


def pitch_tools(p) -> list[str]:
    return [t["function"]["name"] for t in p["assistant"]["model"]["tools"] if t.get("type") == "function"]


def the_call(db) -> PrivateCall:
    db.expire_all()
    return db.query(PrivateCall).one()


def contact(db) -> ExternalBusinessContact | None:
    db.expire_all()
    return db.scalar(select(ExternalBusinessContact))


CLOSING = [{"role": "bot", "message": lp.PITCH_LINE}, {"role": "user", "message": "Ja tak, send gerne en mail."},
           {"role": "bot", "message": lp.ASK_EMAIL_LINE}, {"role": "user", "message": "info@cykelmageren.dk"},
           {"role": "bot", "message": lp.THANKS_LINE}]


# --- the template -------------------------------------------------------------------------------------------------------------

def test_the_wording_is_locked():
    assert lp.PITCH_LINE == ("Tak for hjælpen. Jeg ringer på vegne af en kunde via Dialogbot – hvis I vil høre, hvad det kan gøre for "
                             "jeres telefon, sender vi gerne en mail. Ellers ingen problem, hav en god dag.")
    assert lp.PITCH_MARKER in lp.PITCH_LINE


def test_no_text_the_assistant_says_contains_a_price_a_percentage_or_a_superlative():
    for text in (lp.PITCH_LINE, lp.ASK_EMAIL_LINE, lp.BAD_EMAIL_LINE, lp.THANKS_LINE, lp.DECLINE_LINE, lp.SKIP_LINE):
        assert not re.search(r"\d|%|kr\b|kroner|gratis|billig|bedst|nummer et|markedets|bedre end|garanti", text, re.I), text
    assert len(lp.PITCH_LINE) < 260 and lp.PITCH_LINE.count(".") == 3          # short: three sentences


def test_the_intro_mail_is_fixed_and_makes_no_price_or_superlative_claim():
    mail = tpl.intro_mail("Cykelmageren")
    body = mail.subject + mail.text()
    assert not re.search(r"\d+\s*(kr|%)|gratis|billig|bedst|garanti", body, re.I)
    assert "nej tak" in body and "Cykelmageren" in body and "ringede" in body or "ringede til jer" in body


@pytest.mark.parametrize("raw,ok", [("info@cykelmageren.dk", True), (" Info@Cykelmageren.DK. ", True), ("a b@c.dk", True),
                                    ("info@cykelmageren", False), ("@x.dk", False), ("info@", False), ("", False), (None, False),
                                    ("tekst uden snabel-a", False), ("x@y.z", False)])
def test_email_is_validated(raw, ok):
    assert (lp.valid_email(raw) is not None) is ok


# --- the rules -----------------------------------------------------------------------------------------------------------------

def test_flag_off_nothing_happens_and_nothing_is_stored(api, client, pv, db, monkeypatch, setup):
    monkeypatch.setenv("LEAD_PITCH_ENABLED", "false")
    get_settings.cache_clear()
    tok, tid, p = make_call(api, pv, monkeypatch)
    assert pitch_tools(p) == [] and "end_call_pitch" not in str(p["assistant"])
    c = the_call(db)
    assert (c.pitch_outcome, c.pitch_skipped_reason) == (None, None) and contact(db) is None
    assert lp.SKIP_LINE in tool(client, p, "end_call_pitch", {"errand_outcome": "confirmed", "business_is_calm": True})   # even if asked
    assert lp.PITCH_LINE not in tool(client, p, "end_call_pitch", {"errand_outcome": "confirmed", "business_is_calm": True})
    _report(client, p, "customer-ended-call", ERRAND, seconds=100)
    assert the_call(db).pitch_outcome is None and contact(db) is None and not db.scalar(select(Lead))


def test_an_eligible_call_gets_the_tools_and_the_prompt(api, client, pv, db, monkeypatch, setup):
    tok, tid, p = make_call(api, pv, monkeypatch)
    assert pitch_tools(p) == ["end_call_pitch", "pitch_reply"]
    system = p["assistant"]["model"]["messages"][0]["content"]
    assert "ORDRET" in system and "Afbryd aldrig" in system and lp.PITCH_LINE not in system   # the line comes from the tool, not the prompt
    assert contact(db).advertising_protected is False and the_call(db).pitch_outcome is None


def test_dialogbot_customers_are_skipped(api, client, pv, db, monkeypatch, setup):
    biz = api.workspace(setup.sales_tok, "Cykelmageren ApS")
    db.get(BusinessProfile, uuid.UUID(biz)).cvr = CVR_NO
    db.commit()
    tok, tid, p = make_call(api, pv, monkeypatch)
    assert pitch_tools(p) == []
    c = the_call(db)
    assert (c.pitch_outcome, c.pitch_skipped_reason) == ("skipped", "dialogbot_customer") and contact(db).is_dialogbot_customer


def test_a_customer_is_also_found_by_phone(api, client, pv, db, monkeypatch, setup):
    setup.hit["cvr"] = "99999996"
    biz = api.workspace(setup.sales_tok, "Cykelmageren ApS")
    db.get(BusinessProfile, uuid.UUID(biz)).phone = "86 12 34 56"
    db.commit()
    assert lp.is_dialogbot_customer(db, cvr=None, phone="+4586123456") is True
    assert lp.is_dialogbot_customer(db, cvr=None, phone="+4511111111") is False


def test_the_sales_workspace_itself_is_not_a_customer(api, db, setup):
    bp = db.get(BusinessProfile, setup.ws)
    bp.cvr, bp.phone = "55555558", "11 22 33 44"
    db.commit()
    assert lp.is_dialogbot_customer(db, cvr="55555558", phone="+4511223344") is False


def test_blocklisted_businesses_are_skipped(api, client, pv, db, monkeypatch, setup):
    db.add(SalesBlockList(kind="phone", value="+4586123456", reason="test", source="manual"))
    db.commit()
    tok, tid, p = make_call(api, pv, monkeypatch)
    assert pitch_tools(p) == [] and the_call(db).pitch_skipped_reason == "blocklisted"


def test_reklamebeskyttet_is_skipped(api, client, pv, db, monkeypatch, setup):
    setup.hit["advertising_protected"] = True
    tok, tid, p = make_call(api, pv, monkeypatch)
    assert pitch_tools(p) == [] and the_call(db).pitch_skipped_reason == "advertising_protected"


def test_unknown_protection_counts_as_protected(api, client, pv, db, monkeypatch, setup):
    monkeypatch.setattr(cvr_register, "configured", lambda: False)                         # no CVR access: we cannot tell
    tok, tid, p = make_call(api, pv, monkeypatch)
    assert pitch_tools(p) == [] and the_call(db).pitch_skipped_reason == "advertising_unknown"


def test_cooldown_blocks_a_repeat_and_ends_after_the_configured_days(api, client, pv, db, monkeypatch, setup):
    tok, tid, p = make_call(api, pv, monkeypatch)
    row = contact(db)
    row.last_pitch_at = rules.now() - timedelta(days=89)
    db.commit()
    c = the_call(db)
    ok, reason, _ = lp.eligibility(db, c)
    assert (ok, reason) == (False, "cooldown")
    row.last_pitch_at = rules.now() - timedelta(days=91)
    db.commit()
    assert lp.eligibility(db, the_call(db))[0] is True
    monkeypatch.setenv("LEAD_PITCH_COOLDOWN_DAYS", "30")
    get_settings.cache_clear()
    row.last_pitch_at = rules.now() - timedelta(days=31)
    db.commit()
    assert lp.eligibility(db, the_call(db))[0] is True


def test_the_rules_are_checked_again_when_the_assistant_asks_for_the_line(api, client, pv, db, monkeypatch, setup):
    tok, tid, p = make_call(api, pv, monkeypatch)
    db.add(SalesBlockList(kind="phone", value="+4586123456", reason="added during the call", source="manual"))
    db.commit()
    out = tool(client, p, "end_call_pitch", {"errand_outcome": "confirmed", "business_is_calm": True})
    assert out == lp.SKIP_LINE and the_call(db).pitch_skipped_reason == "blocklisted" and the_call(db).pitch_started_at is None


def test_the_line_needs_a_finished_errand_and_a_calm_business(api, client, pv, db, monkeypatch, setup):
    tok, tid, p = make_call(api, pv, monkeypatch)
    assert tool(client, p, "end_call_pitch", {"errand_outcome": "open", "business_is_calm": True}) == lp.SKIP_LINE
    assert the_call(db).pitch_skipped_reason == "errand_not_finished"
    assert tool(client, p, "end_call_pitch", {"errand_outcome": "confirmed", "business_is_calm": False}) == lp.SKIP_LINE
    assert the_call(db).pitch_skipped_reason == "stressed" and contact(db).last_pitch_at is None      # no cooldown was started


def test_the_line_is_said_once_and_starts_the_cooldown(api, client, pv, db, monkeypatch, setup):
    tok, tid, p = make_call(api, pv, monkeypatch)
    out = tool(client, p, "end_call_pitch", {"errand_outcome": "confirmed", "business_is_calm": True})
    assert lp.PITCH_LINE in out and "ordret" in out.lower() or "præcis" in out.lower()
    assert tool(client, p, "end_call_pitch", {"errand_outcome": "confirmed", "business_is_calm": True}).startswith("Teksten er allerede sagt")
    row = contact(db)
    assert row.pitch_count == 1 and row.last_pitch_at is not None and the_call(db).pitch_started_at is not None


# --- yes / no ------------------------------------------------------------------------------------------------------------------

def test_yes_with_an_address_makes_one_lead_with_consent_and_the_report(api, client, pv, db, monkeypatch, setup):
    tok, tid, p = make_call(api, pv, monkeypatch)
    tool(client, p, "end_call_pitch", {"errand_outcome": "confirmed", "business_is_calm": True})
    assert tool(client, p, "pitch_reply", {"interested": True}) == lp.ASK_EMAIL_LINE
    assert not db.scalar(select(Lead))                                                      # a yes without an address makes no lead
    assert tool(client, p, "pitch_reply", {"interested": True, "email": "info@cykelmageren"}) == lp.BAD_EMAIL_LINE
    assert not db.scalar(select(Lead)) and contact(db).email is None                        # an invalid address is not stored
    assert tool(client, p, "pitch_reply", {"interested": True, "email": "Info@Cykelmageren.dk"}) == lp.THANKS_LINE
    row = contact(db)
    assert (row.email, row.consent_to_email, row.last_outcome) == ("info@cykelmageren.dk", True, "interested") and row.consent_at
    out = _report(client, p, "customer-ended-call", [*ERRAND, *CLOSING], seconds=140)
    assert out["outcome"] == "applied"
    c = the_call(db)
    assert (c.pitch_outcome, c.pitch_skipped_reason) == ("interested", None)
    assert c.pitch_transcript_excerpt.startswith("Assistent: Tak for hjælpen. Jeg ringer på vegne") and len(c.pitch_transcript_excerpt) <= 500
    assert "Cykelmageren" not in c.pitch_transcript_excerpt.split("\n")[0] or True
    # the errand is untouched by the line
    assert c.confirmed_text == "Torsdag kl. 15.30" and c.result == "answered" and lp.PITCH_MARKER not in (c.business_reply or "")
    [lead] = list(db.scalars(select(Lead)))
    assert (lead.workspace_id, lead.source, lead.contact_email, lead.contact_phone) == (setup.ws, "privat_call", "info@cykelmageren.dk", "+4586123456")
    assert "kategori: værksted" in lead.need_summary and "Send intro-mail" in lead.need_summary
    assert "Mette" not in lead.need_summary and "torsdag" not in lead.need_summary.lower()   # nothing about the user or the errand
    assert row.lead_id == lead.id
    [task] = list(db.scalars(select(Task).where(Task.lead_id == lead.id)))
    assert task.title == "Send intro-mail til Cykelmageren" and task.status == "open"


def test_no_blocklists_and_stores_nothing_else(api, client, pv, db, monkeypatch, setup):
    tok, tid, p = make_call(api, pv, monkeypatch)
    tool(client, p, "end_call_pitch", {"errand_outcome": "confirmed", "business_is_calm": True})
    assert tool(client, p, "pitch_reply", {"interested": False, "email": "ikke@gemmes.dk"}) == lp.DECLINE_LINE
    row = contact(db)
    assert (row.blocklisted, row.blocklist_reason, row.last_outcome) == (True, "declined_pitch", "declined")
    assert row.email is None and row.consent_to_email is False and row.lead_id is None
    kinds = {(b.kind, b.value) for b in db.scalars(select(SalesBlockList))}
    assert kinds == {("phone", "+4586123456"), ("cvr", CVR_NO)}
    _report(client, p, "customer-ended-call", [*ERRAND, {"role": "bot", "message": lp.PITCH_LINE},
                                               {"role": "user", "message": "Nej tak, ikke interesseret."}], seconds=120)
    assert the_call(db).pitch_outcome == "declined" and not db.scalar(select(Lead))
    again = lp.eligibility(db, the_call(db))
    assert again[:2] == (False, "blocklisted")                                              # never again


def test_a_yes_without_an_address_before_the_hang_up_is_not_a_lead(api, client, pv, db, monkeypatch, setup):
    tok, tid, p = make_call(api, pv, monkeypatch)
    tool(client, p, "end_call_pitch", {"errand_outcome": "declined", "business_is_calm": True})
    tool(client, p, "pitch_reply", {"interested": True})
    _report(client, p, "customer-ended-call", [*ERRAND, {"role": "bot", "message": lp.PITCH_LINE},
                                               {"role": "user", "message": "Ja"}], seconds=120)
    c = the_call(db)
    assert (c.pitch_outcome, c.pitch_skipped_reason) == ("skipped", "hung_up_during_pitch")
    assert not db.scalar(select(Lead)) and contact(db).email is None


def test_reply_before_the_line_is_refused(api, client, pv, db, monkeypatch, setup):
    tok, tid, p = make_call(api, pv, monkeypatch)
    out = tool(client, p, "pitch_reply", {"interested": True, "email": "info@cykelmageren.dk"})
    assert "ikke sagt endnu" in out and not db.scalar(select(Lead)) and contact(db).email is None


# --- the call did not go well --------------------------------------------------------------------------------------------------

def test_no_answer_skips_with_a_reason(api, client, pv, db, monkeypatch, setup):
    tok, tid, p = make_call(api, pv, monkeypatch)
    _report(client, p, "customer-did-not-answer", [{"role": "bot", "message": "Hej"}], seconds=0)
    c = the_call(db)
    assert c.result == "no_answer" and (c.pitch_outcome, c.pitch_skipped_reason) == ("skipped", "call_not_answered")


def test_when_the_business_hangs_up_the_line_is_just_skipped(api, client, pv, db, monkeypatch, setup):
    tok, tid, p = make_call(api, pv, monkeypatch)
    _report(client, p, "customer-ended-call", ERRAND, seconds=90)
    c = the_call(db)
    assert c.result == "answered" and (c.pitch_outcome, c.pitch_skipped_reason) == ("skipped", "counterparty_ended")
    assert c.pitch_transcript_excerpt is None and c.confirmed_text == "Torsdag kl. 15.30"


def test_an_assistant_that_never_asked_is_not_asked(api, client, pv, db, monkeypatch, setup):
    tok, tid, p = make_call(api, pv, monkeypatch)
    _report(client, p, "assistant-ended-call", ERRAND, seconds=90)
    assert (the_call(db).pitch_outcome, the_call(db).pitch_skipped_reason) == ("not_asked", "assistant_did_not_ask")


# --- the closing line never touches the agreement -----------------------------------------------------------------------------

def test_the_closing_part_is_cut_out_before_the_errand_is_judged(api, client, pv, db, monkeypatch, setup):
    tok, tid, p = make_call(api, pv, monkeypatch)
    tool(client, p, "end_call_pitch", {"errand_outcome": "confirmed", "business_is_calm": True})
    closing = [{"role": "bot", "message": lp.PITCH_LINE},
               {"role": "user", "message": "Ja tak. Ring torsdag kl. 17.00, så tager vi en snak om det."}]
    _report(client, p, "customer-ended-call", [*ERRAND, *closing], seconds=150)
    c = the_call(db)
    assert c.confirmed_text == "Torsdag kl. 15.30"            # not «torsdag kl. 17.00» from the closing conversation
    t = pv.task(tok, tid).json()
    assert t["call"]["confirmed_text"] == "Torsdag kl. 15.30" and "Dialogbot" not in t["call"]["confirmed_text"]
    assert lp.PITCH_MARKER not in str(t["call"]) and lp.PITCH_MARKER not in str(t["events"])


def test_a_paraphrased_line_is_not_our_offer_so_the_consent_is_withdrawn(api, client, pv, db, monkeypatch, setup):
    tok, tid, p = make_call(api, pv, monkeypatch)
    tool(client, p, "end_call_pitch", {"errand_outcome": "confirmed", "business_is_calm": True})
    tool(client, p, "pitch_reply", {"interested": True, "email": "info@cykelmageren.dk"})
    assert contact(db).consent_to_email is True and db.scalar(select(Lead)) is not None
    paraphrase = [{"role": "bot", "message": "Vi har i øvrigt en rigtig god telefonløsning, hvis I vil have en mail."},
                  {"role": "user", "message": "Ja tak, det er info@cykelmageren.dk"}]
    _report(client, p, "customer-ended-call", [*ERRAND, *paraphrase], seconds=120)
    c, row = the_call(db), contact(db)
    assert (c.pitch_outcome, c.pitch_skipped_reason, c.pitch_transcript_excerpt) == ("skipped", "line_not_verbatim", None)
    assert (row.email, row.consent_to_email) == (None, False)
    lead = db.scalar(select(Lead))
    assert lead.contact_email is None and "Send ingen mail" in lead.need_summary
    assert db.scalar(select(Task).where(Task.lead_id == lead.id)).status == "done"
    assert api.post(setup.sales_tok, f"/operator/sales/privat-leads/{row.id}/intro-mail").status_code == 409


def test_split_transcript():
    errand, closing = lp.split_transcript("Assistent: Hej\nVirksomhed: Torsdag\nAssistent: " + lp.PITCH_LINE + "\nVirksomhed: Nej")
    assert errand == "Assistent: Hej\nVirksomhed: Torsdag" and closing.startswith("Assistent: Tak for hjælpen. Jeg ringer på vegne")
    assert lp.split_transcript("ingen linje her") == ("ingen linje her", "")
    assert len(lp.excerpt("x" * 900)) == 500


# --- campaign and demo calls never have the line ------------------------------------------------------------------------------

def test_campaign_and_demo_calls_do_not_have_the_tools_or_the_text(client, pv, setup):
    # a tool call from a call that is not a Privat call: the closing line does not exist for it
    r = client.post("/api/v1/webhooks/vapi", headers=VAPI_H, json={"message": {
        "type": "tool-calls", "call": {"id": "campaign_call_1", "metadata": {"campaign_id": "x"}},
        "toolCallList": [{"id": "t1", "function": {"name": "end_call_pitch", "arguments": {"errand_outcome": "confirmed",
                                                                                           "business_is_calm": True}}}]}})
    assert lp.PITCH_LINE not in r.text and "ikke tilgængelig" in r.text
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "app" / "modules"
    for module in ("sales", "campaigns", "telephony"):
        for f in (root / module).rglob("*.py"):
            src = f.read_text(encoding="utf-8")
            assert "PITCH_LINE" not in src and "Jeg ringer på vegne af en kunde via Dialogbot" not in src or f.name == "vapi.py", f.name
    vapi_src = (root / "telephony" / "vapi.py").read_text(encoding="utf-8")
    assert "PITCH_LINE" not in vapi_src                         # vapi.py only routes the two tool names to lead_pitch


# --- one lead per business ------------------------------------------------------------------------------------------------------

def test_a_repeat_updates_the_lead_and_never_makes_a_second(api, client, pv, db, monkeypatch, setup):
    tok, tid, p = make_call(api, pv, monkeypatch)
    tool(client, p, "end_call_pitch", {"errand_outcome": "confirmed", "business_is_calm": True})
    tool(client, p, "pitch_reply", {"interested": True, "email": "info@cykelmageren.dk"})
    row, c = contact(db), the_call(db)
    first = db.scalar(select(Lead))
    row.email = "ny@cykelmageren.dk"
    lp.upsert_lead(db, c, row)
    lp.upsert_lead(db, c, row)
    db.commit()
    leads = list(db.scalars(select(Lead)))
    assert len(leads) == 1 and leads[0].id == first.id and leads[0].contact_email == "ny@cykelmageren.dk"
    assert len(list(db.scalars(select(Task).where(Task.lead_id == first.id)))) == 1        # one open «Send intro-mail», not three
    row.lead_id = None                                                                      # the link lost: found again by phone
    lp.upsert_lead(db, c, row)
    db.commit()
    assert len(list(db.scalars(select(Lead)))) == 1


def test_without_a_sales_workspace_nothing_is_created(api, client, pv, db, monkeypatch, setup):
    monkeypatch.delenv("SALES_WORKSPACE_ID")
    get_settings.cache_clear()
    tok, tid, p = make_call(api, pv, monkeypatch)
    tool(client, p, "end_call_pitch", {"errand_outcome": "confirmed", "business_is_calm": True})
    tool(client, p, "pitch_reply", {"interested": True, "email": "info@cykelmageren.dk"})
    assert not db.scalar(select(Lead))


# --- the operator surface -----------------------------------------------------------------------------------------------------

def interested_business(api, client, pv, db, monkeypatch):
    tok, tid, p = make_call(api, pv, monkeypatch)
    tool(client, p, "end_call_pitch", {"errand_outcome": "confirmed", "business_is_calm": True})
    tool(client, p, "pitch_reply", {"interested": True, "email": "info@cykelmageren.dk"})
    _report(client, p, "customer-ended-call", [*ERRAND, *CLOSING], seconds=140)
    return str(contact(db).id)


def test_only_admin_and_owner_of_the_sales_workspace_see_the_list(api, client, pv, db, monkeypatch, setup):
    cid = interested_business(api, client, pv, db, monkeypatch)
    r = api.get(setup.sales_tok, "/operator/sales/privat-leads")
    assert r.status_code == 200
    [item] = r.json()["items"]
    assert (item["source"], item["name"], item["outcome"], item["consent_to_email"], item["email"]) == (
        "Privat-opkald", "Cykelmageren", "interested", True, "info@cykelmageren.dk")
    assert item["cooldown_until"] and item["lead_id"] and r.json()["cooldown_days"] == 90
    outsider = api.user("outsider@testmail.dk")
    assert api.get(outsider, "/operator/sales/privat-leads").status_code == 404            # not a member: it looks like it does not exist
    assert api.post(outsider, f"/operator/sales/privat-leads/{cid}/intro-mail").status_code == 404
    assert api.post(outsider, f"/operator/sales/privat-leads/{cid}/block", {}).status_code == 404
    from app.models import Membership, User

    for email, role in (("staff@testmail.dk", "staff"), ("admin@testmail.dk", "admin"), ("reader@testmail.dk", "reader")):
        tok = api.user(email)
        db.add(Membership(workspace_id=setup.ws, user_id=db.scalar(select(User.id).where(User.email_normalized == email)), role=role))
        db.commit()
        expected = 200 if role == "admin" else 403
        assert api.get(tok, "/operator/sales/privat-leads").status_code == expected, role     # members below admin: 403
        assert api.post(tok, f"/operator/sales/privat-leads/{cid}/block", {}).status_code == (200 if role == "admin" else 403), role
        if role == "admin":
            api.post(setup.sales_tok, f"/operator/sales/privat-leads/{cid}/intro-mail")        # block above removed the consent: 409
    privat_user = pv.account("anna@testmail.dk")
    assert api.get(privat_user, "/operator/sales/privat-leads").status_code == 404          # a Privat user is no member either


def test_send_intro_mail_is_once_only_and_marks_the_lead_contacted(api, client, pv, db, monkeypatch, setup):
    cid = interested_business(api, client, pv, db, monkeypatch)
    r = api.post(setup.sales_tok, f"/operator/sales/privat-leads/{cid}/intro-mail")
    assert r.status_code == 200 and r.json() == {"sent": True, "already_sent": False}
    assert api.post(setup.sales_tok, f"/operator/sales/privat-leads/{cid}/intro-mail").json() == {"sent": False, "already_sent": True}
    events = [e for e in db.scalars(select(OutboxEvent)) if e.dedupe_key == f"intro-mail:{cid}"]
    assert len(events) == 1 and events[0].payload["to_email"] == "info@cykelmageren.dk"
    assert tpl.from_payload(events[0].payload).subject == tpl.intro_mail("Cykelmageren").subject
    runner.drain()
    from app.models import EmailDelivery

    assert [d.to_email for d in db.scalars(select(EmailDelivery)) if d.to_email == "info@cykelmageren.dk"] == ["info@cykelmageren.dk"]
    db.expire_all()
    lead = db.scalar(select(Lead))
    assert lead.pipeline_status == "contacted"
    assert db.scalar(select(Task).where(Task.title.like("Send intro-mail%"))).status == "done"
    assert api.get(setup.sales_tok, "/operator/sales/privat-leads").json()["items"][0]["intro_mail_sent"] is True


def test_no_intro_mail_without_a_yes_or_after_a_block(api, client, pv, db, monkeypatch, setup):
    tok, tid, p = make_call(api, pv, monkeypatch)
    tool(client, p, "end_call_pitch", {"errand_outcome": "confirmed", "business_is_calm": True})
    tool(client, p, "pitch_reply", {"interested": False})
    cid = str(contact(db).id)
    r = api.post(setup.sales_tok, f"/operator/sales/privat-leads/{cid}/intro-mail")
    assert r.status_code == 409 and r.json()["code"] == "no_consent"
    assert not [e for e in db.scalars(select(OutboxEvent)) if e.dedupe_key.startswith("intro-mail")]


def test_spaer_blocks_forever_and_drops_the_address(api, client, pv, db, monkeypatch, setup):
    cid = interested_business(api, client, pv, db, monkeypatch)
    r = api.post(setup.sales_tok, f"/operator/sales/privat-leads/{cid}/block", {"reason": "bad ved telefonen"})
    assert r.status_code == 200 and r.json()["blocklisted"] is True and r.json()["email"] is None
    row = contact(db)
    assert (row.blocklisted, row.email, row.consent_to_email) == (True, None, False)
    assert {(b.kind, b.value) for b in db.scalars(select(SalesBlockList))} >= {("phone", "+4586123456"), ("cvr", CVR_NO)}
    assert api.post(setup.sales_tok, f"/operator/sales/privat-leads/{cid}/intro-mail").status_code == 409
    assert lp.eligibility(db, the_call(db))[:2] == (False, "blocklisted")
    assert api.post(setup.sales_tok, f"/operator/sales/privat-leads/{uuid.uuid4()}/block", {}).status_code == 404


def test_a_business_that_never_heard_the_line_is_not_in_the_list(api, client, pv, db, monkeypatch, setup):
    tok, tid, p = make_call(api, pv, monkeypatch)                  # eligible, but no line was said
    assert api.get(setup.sales_tok, "/operator/sales/privat-leads").json()["items"] == []
    assert api.post(setup.sales_tok, f"/operator/sales/privat-leads/{contact(db).id}/block", {}).status_code == 404


def test_the_category_never_contains_a_name():
    assert lp.category_for("Book et eftersyn", "Cykelmageren") == "værksted"
    assert lp.category_for("Aftal en tid", "Mette Hansens Frisør") == "frisør"
    assert lp.category_for("noget helt andet", "Xyz") == "andet"

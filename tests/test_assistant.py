"""«Ændr noget»: a change in the person's words becomes a before → after card; nothing changes until «Godkend»."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.config import get_settings
from app.models import (
    AssistantProposal,
    AssistantRequest,
    AuditLog,
    BusinessProfile,
    LanguageSettings,
    OutboxEvent,
    ReceptionScript,
    ReportSettings,
    User,
    WebchatSettings,
    WorkspaceVoiceSettings,
)
from app.modules.ai import provider as ai_provider
from app.modules.ai.provider import FakeProvider
from app.modules.bookings import service as bookings
from app.modules.knowledge import service as knowledge


@pytest.fixture
def fake(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "fake")
    get_settings.cache_clear()
    ai_provider.set_provider_override(FakeProvider(get_settings()))
    yield
    ai_provider.set_provider_override(None)
    get_settings.cache_clear()


@pytest.fixture
def db_requests(db):
    def rows(ws):
        db.expire_all()
        return list(db.scalars(select(AssistantRequest).where(AssistantRequest.workspace_id == __import__("uuid").UUID(ws))))
    return rows


def _propose(api, tok, ws, text, page="/app", history=None):
    body = {"text": text, "context": page, **({"history": history} if history is not None else {})}
    r = api.post(tok, f"/workspaces/{ws}/assistant/changes", body)
    assert r.status_code == 200, r.text
    return r.json()


def _live(db, ws):
    return {i["title"]: i for i in knowledge.active_knowledge(db, ws)}


def test_hours_are_proposed_then_applied_only_after_godkend(api, two_workspaces, db, fake):
    t = two_workspaces
    out = _propose(api, t["tok_a"], t["ws_a"], "Ret åbningstider: åbningstider man-fre 8-16")
    p = out["proposal"]
    assert p["kind"] == "opening_hours" and p["before"] == "Ikke angivet" and p["after"] == "Man–fre 08–16"
    assert _live(db, t["ws_a"]) == {}                                        # nothing is live before «Godkend»
    r = api.post(t["tok_a"], f"/workspaces/{t['ws_a']}/assistant/changes/{p['id']}/apply")
    assert r.status_code == 200 and r.json()["href"] == "/app/viden"
    live = _live(db, t["ws_a"])
    assert live["Åbningstider"]["content"]["weekly"] == [{"days": ["mon", "tue", "wed", "thu", "fri"], "open": "08:00", "close": "16:00"}]
    assert api.post(t["tok_a"], f"/workspaces/{t['ws_a']}/assistant/changes/{p['id']}/apply").status_code == 409   # only once
    actions = [a.action for a in db.scalars(select(AuditLog).order_by(AuditLog.created_at))]
    assert "assistant.change_proposed" in actions and "assistant.change_applied" in actions and "knowledge.approved" in actions
    again = _propose(api, t["tok_a"], t["ws_a"], "åbningstider man-fre 8-16")   # already so: nothing to change
    assert again["proposal"] is None and "allerede" in again["reply"]


def test_a_price_change_shows_the_old_and_the_new_price_and_makes_a_new_version(api, two_workspaces, db, fake):
    t = two_workspaces
    it = api.knowledge(t["tok_a"], t["ws_a"], "service", "Gulvafslibning", {"description": "Afslibning", "price_net_minor": 14500, "unit": "m2"})
    api.submit(t["tok_a"], t["ws_a"], it["open_draft"]["id"])
    assert api.approve(t["tok_a"], t["ws_a"], it["open_draft"]["id"]).status_code == 200
    p = _propose(api, t["tok_a"], t["ws_a"], "Gulvafslibning koster 165 kr pr. m²")["proposal"]
    assert p["before"] == "145,00 kr. ekskl. moms pr. m²" and p["after"] == "165,00 kr. ekskl. moms pr. m²"
    assert _live(db, t["ws_a"])["Gulvafslibning"]["content"]["price_net_minor"] == 14500
    assert api.post(t["tok_a"], f"/workspaces/{t['ws_a']}/assistant/changes/{p['id']}/apply").status_code == 200
    now = _live(db, t["ws_a"])["Gulvafslibning"]
    assert now["content"]["price_net_minor"] == 16500 and now["content"]["description"] == "Afslibning" and now["version_no"] == 2


def test_answer_and_forbidden_topic(api, two_workspaces, db, fake):
    t = two_workspaces
    a = _propose(api, t["tok_a"], t["ws_a"], "Spørgsmål: Kommer I i weekenden? Svar: Ja, mod et tillæg.")["proposal"]
    assert a["kind"] == "known_answer" and a["after"] == "Ja, mod et tillæg."
    assert api.post(t["tok_a"], f"/workspaces/{t['ws_a']}/assistant/changes/{a['id']}/apply").status_code == 200
    f = _propose(api, t["tok_a"], t["ws_a"], "Den må aldrig tale om priser på terrasser")["proposal"]
    assert f["kind"] == "forbidden_topic"
    assert api.post(t["tok_a"], f"/workspaces/{t['ws_a']}/assistant/changes/{f['id']}/apply").status_code == 200
    live = _live(db, t["ws_a"])
    assert live["Kommer I i weekenden?"]["content"]["answer"] == "Ja, mod et tillæg."
    assert live["Priser på terrasser"]["content"] == {"rule": "Priser på terrasser"}
    again = _propose(api, t["tok_a"], t["ws_a"], "Den må aldrig tale om priser på terrasser")
    assert again["proposal"] is None and "findes allerede" in again["reply"]


def test_booking_rules_and_report_settings(api, two_workspaces, db, fake):
    t = two_workspaces
    b = _propose(api, t["tok_a"], t["ws_a"], "Sæt pausen mellem aftaler til 30 min og tidligst 48 timer frem")["proposal"]
    assert b["kind"] == "booking_rule" and "Pause 30 min" in b["after"] and "tidligst om 48 timer" in b["after"]
    assert api.post(t["tok_a"], f"/workspaces/{t['ws_a']}/assistant/changes/{b['id']}/apply").status_code == 200
    db.expire_all()
    s = bookings.settings(db, __import__("uuid").UUID(t["ws_a"]))
    assert (s.buffer_minutes, s.lead_time_hours) == (30, 48)
    r = _propose(api, t["tok_a"], t["ws_a"], "Send dagsrapporten kl. 9")["proposal"]
    assert r["after"] == "Dagsrapport kl. 09 · slået til"
    assert api.post(t["tok_a"], f"/workspaces/{t['ws_a']}/assistant/changes/{r['id']}/apply").status_code == 200
    db.expire_all()
    assert db.get(ReportSettings, __import__("uuid").UUID(t["ws_a"])).send_hour_local == 9


def test_roles_the_change_needs_are_checked_before_a_proposal_is_shown(api, two_workspaces, fake):
    t = two_workspaces
    staff = api.add_member(t["tok_a"], t["ws_a"], "staff@testmail.dk", "staff")
    reader = api.add_member(t["tok_a"], t["ws_a"], "reader@testmail.dk", "reader")
    out = _propose(api, staff, t["ws_a"], "åbningstider man-fre 8-16")
    assert out["proposal"] is None and "ejer eller administrator" in out["reply"] and out["code"] == "role_needed"
    # a reader may ask, but never gets a change proposed
    r = _propose(api, reader, t["ws_a"], "åbningstider man-fre 8-16")
    assert r["proposal"] is None and r["code"] == "role_needed"
    assert _propose(api, reader, t["ws_a"], "Hvordan viderestiller jeg?")["type"] == "answer"
    # staff may change what staff may change (business profile = profile.edit)
    assert _propose(api, staff, t["ws_a"], "Vores hjemmeside er fjordgulv.dk")["proposal"]["kind"] == "business_profile"


def test_proposals_are_private_single_use_and_expire(api, two_workspaces, db, fake):
    t = two_workspaces
    p = _propose(api, t["tok_a"], t["ws_a"], "åbningstider man-fre 8-16")["proposal"]
    # another workspace's owner can neither apply nor decline it
    assert api.post(t["tok_b"], f"/workspaces/{t['ws_b']}/assistant/changes/{p['id']}/apply").status_code == 404
    assert api.post(t["tok_a"], f"/workspaces/{t['ws_b']}/assistant/changes/{p['id']}/apply").status_code == 404
    row = db.get(AssistantProposal, __import__("uuid").UUID(p["id"]))
    row.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    db.commit()
    r = api.post(t["tok_a"], f"/workspaces/{t['ws_a']}/assistant/changes/{p['id']}/apply")
    assert r.status_code == 409 and r.json()["code"] == "assistant_proposal_expired"
    assert _live(db, t["ws_a"]) == {}
    d = _propose(api, t["tok_a"], t["ws_a"], "åbningstider man-fre 9-17")["proposal"]
    assert api.post(t["tok_a"], f"/workspaces/{t['ws_a']}/assistant/changes/{d['id']}/decline").status_code == 200
    assert api.post(t["tok_a"], f"/workspaces/{t['ws_a']}/assistant/changes/{d['id']}/apply").status_code == 409
    assert _live(db, t["ws_a"]) == {}


def test_what_it_does_not_understand_is_a_question_or_a_link_never_an_error(api, two_workspaces, monkeypatch, fake, db_requests):
    t = two_workspaces
    q = _propose(api, t["tok_a"], t["ws_a"], "Vi har lukket 31. oktober")
    assert q["proposal"] is None and "Hvilke åbningstider" in q["reply"]
    o = _propose(api, t["tok_a"], t["ws_a"], "Ret vores viderestilling til et andet nummer")
    assert o["proposal"] is None and o["link"]["href"] == "/app/indstillinger?ark=telefoni" and o["code"] == "link_only"
    z = _propose(api, t["tok_a"], t["ws_a"], "bla bla")
    assert z["proposal"] is None and z["link"]["href"] == "/app/indstillinger"
    monkeypatch.setenv("AI_PROVIDER", "none")
    get_settings.cache_clear()
    ai_provider.set_provider_override(None)
    off = _propose(api, t["tok_a"], t["ws_a"], "åbningstider man-fre 8-16")
    assert off["proposal"] is None and "genvej" in off["reply"] and off["code"] == "ai_off"
    assert db_requests(t["ws_a"]) == []                                    # nothing understood → no wish recorded


# --- conversation, guidance and wishes ------------------------------------------------------------------------------------

def _uuid(x):
    return __import__("uuid").UUID(x)


def test_a_question_gets_guidance_with_a_link_to_the_right_page_and_the_guide_and_state_are_in_the_prompt(api, two_workspaces, db, fake):
    t = two_workspaces
    out = _propose(api, t["tok_a"], t["ws_a"], "Hvordan viderestiller jeg min mobil?", page="/app/viden")
    assert out["type"] == "answer" and out["proposal"] is None and out["request"] is None
    assert out["link"] == {"key": "phone", "label": "Telefon", "href": "/app/indstillinger?ark=telefoni"}
    system = ai_provider.get_provider().last_system
    assert "2.495 kr. om måneden" in system and "**67*" in system           # the maintained guide
    assert "Fjord Gulvservice ApS" in system and "Booking:" in system       # the workspace's current state
    assert "/app/indstillinger?ark=stemmer" in system                        # the page map
    assert "Siden personen står på: /app/viden" in system
    assert "på dansk" in system
    # a link the model invents is never passed on
    bad = _propose(api, t["tok_a"], t["ws_a"], "Hvor er den ugyldige side?")
    assert bad["type"] == "answer" and bad["link"] is None


def test_the_conversation_is_sent_as_turns_and_the_reply_language_follows_the_person(api, two_workspaces, db, fake):
    t = two_workspaces
    history = [{"role": "assistant", "text": "Hej. Hvad vil du ændre?"}, {"role": "user", "text": "Vi skal have ny hilsen"},
               {"role": "assistant", "text": "Hvad skal den sige?"}]
    _propose(api, t["tok_a"], t["ws_a"], "Hilsen: Goddag, du taler med Fjord Gulv", history=history)
    msgs = ai_provider.get_provider().last_messages
    assert [m["role"] for m in msgs] == ["user", "assistant", "user"]     # starts and ends with the person
    assert msgs[0]["content"] == "Vi skal have ny hilsen" and msgs[-1]["content"] == "Hilsen: Goddag, du taler med Fjord Gulv"
    u = db.scalar(select(User).where(User.email_normalized == "owner-a@testmail.dk"))
    u.interface_language = "en"
    db.commit()
    _propose(api, t["tok_a"], t["ws_a"], "How do I forward my phone?")
    assert "på engelsk" in ai_provider.get_provider().last_system


def test_new_change_kinds_show_before_and_after_and_apply_only_after_godkend(api, two_workspaces, db, fake):
    t = two_workspaces
    ws = _uuid(t["ws_a"])
    apply = lambda p: api.post(t["tok_a"], f"/workspaces/{t['ws_a']}/assistant/changes/{p['id']}/apply")  # noqa: E731

    g = _propose(api, t["tok_a"], t["ws_a"], "Hilsenen skal være: Goddag, du har ringet til {virksomhed}.")["proposal"]
    assert g["kind"] == "greeting" and g["before"] == "Standardhilsen" and g["after"] == "Goddag, du har ringet til {virksomhed}."
    assert db.get(ReceptionScript, ws) is None                              # nothing before «Godkend»
    r = apply(g)
    assert r.status_code == 200 and r.json()["href"] == "/app/indstillinger?ark=hilsen"
    db.expire_all()
    assert db.get(ReceptionScript, ws).greeting == "Goddag, du har ringet til {virksomhed}." and db.get(ReceptionScript, ws).version == 1

    v = _propose(api, t["tok_a"], t["ws_a"], "Skift vores stemme til Peter")["proposal"]
    assert v["kind"] == "standard_voice" and (v["before"], v["after"]) == ("Camilla", "Peter")
    assert apply(v).status_code == 200
    db.expire_all()
    assert db.get(WorkspaceVoiceSettings, ws).standard_voice == "peter"

    d = _propose(api, t["tok_a"], t["ws_a"], "Den skal sige De til kunderne")["proposal"]
    assert d["kind"] == "persona" and d["after"].endswith("siger De")
    assert apply(d).status_code == 200

    w = _propose(api, t["tok_a"], t["ws_a"], "Velkomsten i webchatten skal være: Hej! Skriv dit spørgsmål her.")["proposal"]
    assert w["kind"] == "webchat_greeting" and w["before"] == "Standardvelkomst"
    assert apply(w).status_code == 200
    db.expire_all()
    assert db.get(WebchatSettings, ws).greeting == "Hej! Skriv dit spørgsmål her."

    lang = _propose(api, t["tok_a"], t["ws_a"], "Den skal også tale engelsk og tysk")["proposal"]
    assert lang["kind"] == "conversation_languages" and lang["before"] == "Standard dansk" and lang["after"] == "Standard dansk · også engelsk, tysk"
    assert apply(lang).status_code == 200
    db.expire_all()
    assert db.get(LanguageSettings, ws).enabled_conversation_languages == ["da", "en", "de"]

    web = _propose(api, t["tok_a"], t["ws_a"], "Vores hjemmeside er fjordgulv.dk")["proposal"]
    assert web["kind"] == "business_profile" and web["after"] == "Hjemmeside: https://fjordgulv.dk"
    assert apply(web).status_code == 200
    db.expire_all()
    assert db.get(BusinessProfile, ws).website_url == "https://fjordgulv.dk"

    e = _propose(api, t["tok_a"], t["ws_a"], "En medarbejder skal overtage, når kunden er vred eller nævner en skade")["proposal"]
    assert e["kind"] == "escalation" and e["before"] == "Ikke angivet"
    actions = [a.action for a in db.scalars(select(AuditLog))]
    for a in ("reception.script_updated", "voices.settings_updated", "webchat.updated", "languages.updated", "profile.updated"):
        assert a in actions
    # a value the server cannot accept is never shown as a proposal
    bad = _propose(api, t["tok_a"], t["ws_a"], "Vores telefonnummer er 12")
    assert bad["proposal"] is None


def test_admin_only_kinds_are_refused_for_staff_before_a_card_is_shown(api, two_workspaces, fake):
    t = two_workspaces
    staff = api.add_member(t["tok_a"], t["ws_a"], "staff@testmail.dk", "staff")
    for text in ("Skift vores stemme til Peter", "Hilsenen skal være: Hej", "Velkomsten i webchatten skal være: Hej"):
        out = _propose(api, staff, t["ws_a"], text)
        assert out["proposal"] is None and out["code"] == "role_needed", text


def test_what_it_cannot_do_becomes_exactly_one_wish_and_repeats_are_counted(api, two_workspaces, db, fake, db_requests):
    t = two_workspaces
    op = api.operator()
    out = _propose(api, t["tok_a"], t["ws_a"], "Ønske: webchatten skal kunne have vores egen farve", page="/app/indstillinger")
    assert out["type"] == "request" and out["proposal"] is None and out["code"] == "request_logged"
    assert "Dialogbot-teamet" in out["reply"] and out["request"]["duplicate"] is False
    rows = db_requests(t["ws_a"])
    assert len(rows) == 1
    r = rows[0]
    assert (r.text, r.page, r.category, r.status, r.times_asked) == ("Ønske: webchatten skal kunne have vores egen farve",
                                                                     "/app/indstillinger", "webchat", "new", 1)
    assert r.summary == "Ønske: webchatten skal kunne have vores egen farve"
    # the operators get one mail per new wish (outbox)
    mails = [e for e in db.scalars(select(OutboxEvent)) if e.dedupe_key.startswith("assistant_request:")]
    assert len(mails) == 1 and mails[0].payload["to_email"] == "operator@testmail.dk"
    # the same wish again (other words, same meaning) is counted, not duplicated
    again = _propose(api, t["tok_a"], t["ws_a"], "Jeg har et ønske: webchatten skal kunne have vores egen farve!")
    assert again["code"] == "request_duplicate" and again["request"]["id"] == out["request"]["id"]
    rows = db_requests(t["ws_a"])
    assert len(rows) == 1 and rows[0].times_asked == 2
    assert len([e for e in db.scalars(select(OutboxEvent)) if e.dedupe_key.startswith("assistant_request:")]) == 1
    # a different wish is a new row; another workspace's same wish is its own row
    _propose(api, t["tok_a"], t["ws_a"], "Kan I lave en integration til e-conomic?")
    _propose(api, t["tok_b"], t["ws_b"], "Ønske: webchatten skal kunne have vores egen farve")
    assert len(db_requests(t["ws_a"])) == 2 and len(db_requests(t["ws_b"])) == 1
    # a wish an operator has closed is not reopened by a repeat: it becomes a new one
    rid = out["request"]["id"]
    assert api.c.patch(f"/api/v1/operator/assistant/requests/{rid}", json={"status": "done"}, headers=api.h(op)).status_code == 200
    _propose(api, t["tok_a"], t["ws_a"], "Ønske: webchatten skal kunne have vores egen farve")
    assert len(db_requests(t["ws_a"])) == 3
    # answers and changes never create wishes
    _propose(api, t["tok_a"], t["ws_a"], "Hvordan viderestiller jeg?")
    _propose(api, t["tok_a"], t["ws_a"], "åbningstider man-fre 8-16")
    assert len(db_requests(t["ws_a"])) == 3


def test_operators_list_filter_and_update_wishes_and_nobody_else_can(api, two_workspaces, db, fake):
    t = two_workspaces
    _propose(api, t["tok_a"], t["ws_a"], "Ønske: webchatten skal kunne have vores egen farve")
    _propose(api, t["tok_b"], t["ws_b"], "Kan I lave en integration til e-conomic?")
    op = api.operator()
    base = "/api/v1/operator/assistant/requests"
    # customers (even owners) and anonymous callers are refused
    assert api.c.get(base, headers=api.h(t["tok_a"])).status_code == 403
    assert api.c.get(base).status_code == 401
    r = api.c.get(base, headers=api.h(op))
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 2 and {i["workspace_name"] for i in body["items"]} == {"Fjord Gulvservice ApS", "Havnebord Café"}
    assert body["counts"]["status"]["new"] == 2 and body["counts"]["category_open"]["webchat"] == 1
    assert body["counts"]["category_open"]["integrations"] == 1 and body["categories"]["webchat"] == "Webchat"
    item = next(i for i in body["items"] if i["category"] == "webchat")
    assert item["user"]["email"] == "owner-a@testmail.dk" and item["times_asked"] == 1
    assert api.c.get(f"{base}?category=integrations", headers=api.h(op)).json()["total"] == 1
    assert api.c.get(f"{base}?q=e-conomic", headers=api.h(op)).json()["total"] == 1
    assert api.c.get(f"{base}?status=bogus", headers=api.h(op)).status_code == 422
    # update status and note; a customer cannot
    url = f"{base}/{item['id']}"
    assert api.c.patch(url, json={"status": "planned"}, headers=api.h(t["tok_a"])).status_code == 403
    p = api.c.patch(url, json={"status": "planned", "admin_note": "Kommer i december"}, headers=api.h(op))
    assert p.status_code == 200 and p.json()["status"] == "planned" and p.json()["admin_note"] == "Kommer i december"
    assert api.c.get(f"{base}?status=planned", headers=api.h(op)).json()["total"] == 1
    assert api.c.patch(url, json={"status": "maybe"}, headers=api.h(op)).status_code == 422
    assert api.c.patch(f"{base}/{__import__('uuid').uuid4()}", json={"status": "done"}, headers=api.h(op)).status_code == 404
    audit = [a for a in db.scalars(select(AuditLog).where(AuditLog.action == "assistant.request_updated"))]
    assert len(audit) == 1 and str(audit[0].workspace_id) == t["ws_a"]


def test_the_guide_states_todays_prices_and_every_link_in_it_is_a_known_page():
    from app.modules.assistant import service
    from app.modules.billing import prices

    g = service.guide()
    for minor in (prices.SUBSCRIPTION_MONTHLY_NET_MINOR, prices.INBOUND_EXTRA_MINUTE_NET_MINOR, prices.CAMPAIGN_CALL_NET_MINOR,
                  prices.CAMPAIGN_MINUTE_NET_MINOR, prices.SPECIALIST_SETUP_NET_MINOR):
        assert f"{prices.kr(minor)} kr." in g, prices.kr(minor)
    assert f"{prices.INBOUND_INCLUDED_MINUTES} påbegyndte minutter" in g
    for path in __import__("re").findall(r"\((/[a-z0-9/]+)\)", g):
        assert path in service.PAGE_BY_HREF, path
    for k in __import__("app.modules.assistant.kinds", fromlist=["KINDS"]).KINDS.values():
        assert k.href in service.PAGE_BY_HREF, k.href

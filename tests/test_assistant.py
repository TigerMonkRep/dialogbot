"""«Ændr noget»: a change in the person's words becomes a before → after card; nothing changes until «Godkend»."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.config import get_settings
from app.models import AssistantProposal, AuditLog, ReportSettings
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


def _propose(api, tok, ws, text, page="/app"):
    r = api.post(tok, f"/workspaces/{ws}/assistant/changes", {"text": text, "context": page})
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
    assert out["proposal"] is None and "ejer eller administrator" in out["reply"]
    assert api.post(reader, f"/workspaces/{t['ws_a']}/assistant/changes", {"text": "åbningstider man-fre 8-16"}).status_code == 403


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


def test_what_it_does_not_understand_is_a_question_or_a_link_never_an_error(api, two_workspaces, monkeypatch, fake):
    t = two_workspaces
    q = _propose(api, t["tok_a"], t["ws_a"], "Vi har lukket 31. oktober")
    assert q["proposal"] is None and "Hvilke åbningstider" in q["reply"]
    o = _propose(api, t["tok_a"], t["ws_a"], "Skift vores stemme til Peter")
    assert o["proposal"] is None and o["link"]["href"] == "/app/indstillinger/telefoni"
    z = _propose(api, t["tok_a"], t["ws_a"], "bla bla")
    assert z["proposal"] is None and z["link"]["href"] == "/app/indstillinger"
    monkeypatch.setenv("AI_PROVIDER", "none")
    get_settings.cache_clear()
    ai_provider.set_provider_override(None)
    off = _propose(api, t["tok_a"], t["ws_a"], "åbningstider man-fre 8-16")
    assert off["proposal"] is None and "genvej" in off["reply"]

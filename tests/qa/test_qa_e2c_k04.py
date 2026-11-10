"""QA wave 2 (P1), e2e-erhverv instance C: K04 offers (DB-005) – the rule is >= 40 m², dated, inclusive end date.

Acceptance (implementation-backlog DB-005): "39 is ineligible; exactly 40 and 41 eligible inside dates; 1 Dec expired;
same condition in editor and assistant answer."
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.models import Workspace
from app.modules.ai.service import build_system_prompt

OFFER = {"discount_percent": 15, "condition": {"area_operator": "gte", "area_threshold_m2": 40},
         "starts_on": "2026-10-01", "ends_on_inclusive": "2026-11-30"}


def _approved_offer(api, tok, ws, content=OFFER, title="Efterårsrabat på gulvafslibning"):
    it = api.knowledge(tok, ws, "offer", title, content)
    r = api.approve(tok, ws, it["open_draft"]["id"])
    assert r.status_code == 200, r.text
    return it["id"]


@pytest.mark.parametrize("area,on,eligible", [
    (39, "2026-11-10", False), (39.99, "2026-11-10", False), (40, "2026-11-10", True), (41, "2026-11-10", True),
    (40, "2026-10-01", True), (40, "2026-11-30", True), (40, "2026-12-01", False), (40, "2026-09-30", False),
    (None, "2026-11-10", False),
])
def test_k04_eligibility_rule_gte_40_inclusive_dates(api, two_workspaces, area, on, eligible):
    t = two_workspaces
    oid = _approved_offer(api, t["tok_a"], t["ws_a"])
    q = f"?on_date={on}" + (f"&area_m2={area}" if area is not None else "")
    r = api.get(t["tok_a"], f"/workspaces/{t['ws_a']}/knowledge/offers/{oid}/eligibility{q}")
    assert r.status_code == 200, r.text
    assert r.json()["eligible"] is eligible


def test_k04_draft_is_never_evaluated_or_given_to_the_assistant(api, two_workspaces, db):
    t = two_workspaces
    tok, ws = t["tok_a"], t["ws_a"]
    staff = api.add_member(tok, ws, "staff-k04@testmail.dk", "staff")
    it = api.knowledge(staff, ws, "offer", "Kladde-rabat", OFFER | {"discount_percent": 50})
    api.submit(staff, ws, it["open_draft"]["id"])
    assert api.get(tok, f"/workspaces/{ws}/knowledge/offers/{it['id']}/eligibility?on_date=2026-11-10&area_m2=50").status_code == 404
    assert api.approve(staff, ws, it["open_draft"]["id"]).status_code == 403  # staff cannot publish an offer
    queue = api.get(tok, f"/workspaces/{ws}/knowledge/review-queue").json()
    assert [v["title"] for v in queue] == ["Kladde-rabat"]
    _approved_offer(api, tok, ws, title="Godkendt")
    prompt, _ = build_system_prompt(db, db.get(Workspace, __import__("uuid").UUID(ws)))
    assert "Kladde-rabat" not in prompt and "Godkendt" in prompt


def test_k04_validation_rejects_inverted_dates_and_bad_operator(api, two_workspaces):
    t = two_workspaces
    tok, ws = t["tok_a"], t["ws_a"]
    bad = OFFER | {"starts_on": "2026-12-01", "ends_on_inclusive": "2026-11-30"}
    r = api.post(tok, f"/workspaces/{ws}/knowledge/items", {"kind": "offer", "title": "x", "content": bad})
    assert r.status_code == 422
    r = api.post(tok, f"/workspaces/{ws}/knowledge/items", {"kind": "offer", "title": "x", "content": OFFER | {"condition": {"area_operator": "≥", "area_threshold_m2": 40}}})
    assert r.status_code == 422


def test_k04_discount_percent_is_validated(api, two_workspaces):
    """F-E2C-07: validate_content checks operator, threshold and dates but not the discount. An approved offer with
    150 % or -10 % reaches the assistant (the UI field has min=1 max=100, the API does not)."""
    t = two_workspaces
    tok, ws = t["tok_a"], t["ws_a"]
    results = {}
    for pct in (150, -10, "femten"):
        r = api.post(tok, f"/workspaces/{ws}/knowledge/items", {"kind": "offer", "title": f"x{pct}", "content": OFFER | {"discount_percent": pct}})
        results[pct] = r.status_code
    assert all(s == 422 for s in results.values()), results


def test_k04_expired_offer_is_not_given_to_the_assistant(api, two_workspaces, db):
    """F-E2C-05: DB-005 "1 Dec expired; same condition in editor and assistant answer". An offer whose
    ends_on_inclusive has passed stays in <godkendt_viden> as raw JSON, and the prompt contains no today's date, so
    the assistant cannot know the offer has expired and may promise the discount."""
    t = two_workspaces
    tok, ws = t["tok_a"], t["ws_a"]
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    _approved_offer(api, tok, ws, OFFER | {"starts_on": "2026-01-01", "ends_on_inclusive": yesterday}, title="Udløbet sommerrabat")
    _approved_offer(api, tok, ws, title="Aktiv rabat") if date.today() <= date(2026, 11, 30) else None
    prompt, _ = build_system_prompt(db, db.get(Workspace, __import__("uuid").UUID(ws)))
    has_today = date.today().isoformat() in prompt or date.today().strftime("%d.%m.%Y") in prompt
    assert "Udløbet sommerrabat" not in prompt or has_today, (
        "expired offer is in the assistant's approved knowledge and the prompt has no current date")

"""QA A06 (e2e-erhverv instans A): create the business workspace or choose an existing one; save product intent.

Krav A06: "Create the business workspace or choose an existing one; save selected product intent."
"""
from __future__ import annotations

from sqlalchemy import func, select

from app.models import GoalSelection, Membership, Workspace


def test_create_with_explicit_intent_overrides_signup_and_is_persisted(api, db):
    tok = api.user("a06@testmail.dk", intent="reception")
    ws = api.workspace(tok, "A06 Begge ApS", intent="both")
    assert api.get(tok, f"/workspaces/{ws}").json()["product_intent"] == "both"
    db.expire_all()
    assert db.get(GoalSelection, ws).product_intent == "both"
    # invalid intent and too-short name are refused without side effects
    r = api.c.post("/api/v1/workspaces", json={"name": "X ApS", "product_intent": "alt"}, headers=api.h(tok))
    assert r.status_code == 422
    r = api.c.post("/api/v1/workspaces", json={"name": "X"}, headers=api.h(tok))
    assert r.status_code == 422
    assert db.scalar(select(func.count()).select_from(Workspace)) == 1


def test_choose_existing_lists_only_own_memberships_with_role(api, two_workspaces, db):
    t = two_workspaces
    second = api.workspace(t["tok_a"], "Fjord Gulvservice ApS")  # same name → distinct slug
    lst = api.get(t["tok_a"], "/workspaces").json()
    assert [w["id"] for w in lst] == [t["ws_a"], second]
    assert all(w["role"] == "owner" for w in lst)
    assert len({w["slug"] for w in lst}) == 2
    assert t["ws_b"] not in [w["id"] for w in lst]
    # choosing a foreign workspace id is answered as "does not exist"
    assert api.get(t["tok_a"], f"/workspaces/{t['ws_b']}").status_code == 404
    assert api.get(t["tok_a"], "/workspaces/00000000-0000-0000-0000-000000000000").status_code == 404


def test_goal_intent_change_is_saved_and_isolated(api, two_workspaces, db):
    t = two_workspaces
    g = api.get(t["tok_a"], f"/workspaces/{t['ws_a']}/goals").json()
    body = {k: g[k] for k in ("guidance_mode", "inbound_phone", "webchat", "callback", "booking", "conversation_goals")}
    r = api.put(t["tok_a"], f"/workspaces/{t['ws_a']}/goals", {**body, "product_intent": "campaigns", "inbound_phone": False,
                                                               "webchat": False, "callback": False, "booking": False,
                                                               "expected_version": g["version"]})
    assert r.status_code == 200, r.text
    assert api.get(t["tok_a"], f"/workspaces/{t['ws_a']}/goals").json()["product_intent"] == "campaigns"
    # B cannot read or write A's goals
    assert api.get(t["tok_b"], f"/workspaces/{t['ws_a']}/goals").status_code == 404
    r = api.put(t["tok_b"], f"/workspaces/{t['ws_a']}/goals", {**body, "product_intent": "both", "expected_version": 99})
    assert r.status_code == 404
    assert db.scalar(select(func.count()).select_from(Membership)) == 2

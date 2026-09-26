"""Deleting knowledge: archived (kept for audit), gone from the assistant, key freed, roles enforced."""
from __future__ import annotations


def _url(ws, item_id=""):
    return f"/api/v1/workspaces/{ws}/knowledge/items" + (f"/{item_id}" if item_id else "")


def test_delete_approved_item(api, two_workspaces):
    t = two_workspaces
    tok, ws = t["tok_a"], t["ws_a"]
    it = api.knowledge(tok, ws, "service", "Afslibning", {"price_net_minor": 14500})
    api.submit(tok, ws, it["open_draft"]["id"])
    assert api.approve(tok, ws, it["open_draft"]["id"]).status_code == 200
    rev = api.get(tok, f"/workspaces/{ws}/assistant/knowledge").json()["knowledge_revision"]
    staff = api.add_member(tok, ws, "staff-del@testmail.dk", "staff")
    assert api.c.delete(_url(ws, it["id"]), headers=api.h(staff)).status_code == 403  # approved: approver only
    assert api.c.delete(_url(ws, it["id"]), headers=api.h(t["tok_b"])).status_code in (403, 404)  # other workspace
    assert api.c.delete(_url(ws, it["id"]), headers=api.h(tok)).status_code == 204
    live = api.get(tok, f"/workspaces/{ws}/assistant/knowledge").json()
    assert live["items"] == [] and live["knowledge_revision"] == rev + 1
    assert all(i["id"] != it["id"] for i in api.c.get(_url(ws), headers=api.h(tok)).json()["items"])
    assert api.knowledge(tok, ws, "service", "Afslibning", {"price_net_minor": 15000})  # title can be reused
    assert api.c.delete(_url(ws, it["id"]), headers=api.h(tok)).status_code == 204  # idempotent


def test_staff_can_delete_a_draft_only_item(api, two_workspaces):
    t = two_workspaces
    tok, ws = t["tok_a"], t["ws_a"]
    staff = api.add_member(tok, ws, "staff-del2@testmail.dk", "staff")
    it = api.knowledge(staff, ws, "fact", "Forkert forslag", {"text": "x"})
    assert api.c.delete(_url(ws, it["id"]), headers=api.h(staff)).status_code == 204
    reader = api.add_member(tok, ws, "reader-del@testmail.dk", "reader")
    it2 = api.knowledge(tok, ws, "fact", "Andet", {"text": "y"})
    assert api.c.delete(_url(ws, it2["id"]), headers=api.h(reader)).status_code == 403

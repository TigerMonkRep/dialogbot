"""Overview KPIs and notifications derived from real records; unread tracking per user; role filtering."""
from __future__ import annotations


def test_notifications_and_overview(api, two_workspaces):
    t = two_workspaces
    tok, ws = t["tok_a"], t["ws_a"]
    r = api.post(tok, f"/workspaces/{ws}/leads", {"contact_name": "Mette", "contact_phone": "+4520304050",
                                                   "need_summary": "Tilbud på afslibning"})
    assert r.status_code == 201, r.text
    api.knowledge(tok, ws, "fact", "Kladde", {"text": "x"})
    n = api.get(tok, f"/workspaces/{ws}/notifications").json()
    kinds = {i["kind"] for i in n["items"]}
    assert {"lead", "knowledge"} <= kinds and n["unread"] >= 2
    assert any("Mette" in i["title"] for i in n["items"])
    assert api.c.post(f"/api/v1/workspaces/{ws}/notifications/seen", headers=api.h(tok)).status_code == 204
    assert api.get(tok, f"/workspaces/{ws}/notifications").json()["unread"] == 0
    # a reader sees neither leads nor approval work
    reader = api.add_member(tok, ws, "reader-notif@testmail.dk", "reader")
    assert {i["kind"] for i in api.get(reader, f"/workspaces/{ws}/notifications").json()["items"]} <= {"import"}
    ov = api.get(tok, f"/workspaces/{ws}/overview").json()
    assert ov["kpis"]["new_leads_24h"] == 1 and ov["kpis"]["open_leads"] == 1 and ov["kpis"]["drafts"] == 1
    assert api.get(t["tok_b"], f"/workspaces/{t['ws_b']}/overview").json()["kpis"]["new_leads_24h"] == 0

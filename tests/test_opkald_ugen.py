"""«Opkald og beskeder» (feed with outcome, resolve) and «Ugen» (week numbers, topics)."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from app.models import Booking, Conversation, ConversationMessage, Lead, Task
from app.modules.reports import service as reports


def _conv(db, ws, channel="webchat", text="Laver I også vinduer i plast?", at=None, mode="ai", role="visitor"):
    at = at or datetime.now(UTC)
    c = Conversation(workspace_id=uuid.UUID(ws), channel=channel, visitor_token_digest="x" * 64, created_at=at,
                     last_message_at=at, mode=mode, origin="norgaard.dk" if channel == "webchat" else "+4540123456")
    db.add(c)
    db.flush()
    db.add(ConversationMessage(conversation_id=c.id, workspace_id=c.workspace_id, role="visitor", text=text, created_at=at))
    if role != "visitor":
        db.add(ConversationMessage(conversation_id=c.id, workspace_id=c.workspace_id, role=role, text="Svar", created_at=at + timedelta(seconds=2)))
    db.commit()
    return c


def test_feed_derives_the_outcome_and_filters(api, two_workspaces, db):
    t = two_workspaces
    ws = uuid.UUID(t["ws_a"])
    booked = _conv(db, t["ws_a"], "phone", "Vindue skal skiftes")
    db.add(Booking(workspace_id=ws, title="Besigtigelse", starts_at=datetime.now(UTC) + timedelta(days=2),
                   ends_at=datetime.now(UTC) + timedelta(days=2, hours=1), source="phone", conversation_id=booked.id))
    pending = _conv(db, t["ws_a"], "phone", "Pris på terrasse")
    lead = Lead(workspace_id=ws, source="manual", conversation_id=pending.id, contact_name="Anders Wulff", need_summary="Tilbud på dør")
    db.add(lead)
    db.flush()
    db.add(Task(workspace_id=ws, lead_id=lead.id, title="Ring tilbage"))
    waiting = _conv(db, t["ws_a"], "webchat", "Kan I i dag?", mode="staff")
    handled = _conv(db, t["ws_a"], "webchat", "Hvad er jeres åbningstider?", role="assistant")
    db.commit()
    r = api.get(t["tok_a"], f"/workspaces/{t['ws_a']}/conversations/feed")
    assert r.status_code == 200
    body = r.json()
    by = {i["id"]: i for i in body["items"]}
    assert by[str(booked.id)]["outcome"] == "booked"
    assert by[str(pending.id)]["outcome"] == "to_you" and by[str(pending.id)]["name"] == "Anders Wulff"
    assert by[str(waiting.id)]["outcome"] == "to_you" and by[str(waiting.id)]["awaiting_staff"]
    assert by[str(handled.id)]["outcome"] == "done"
    assert body["counts"] == {"all": 4, "to_you": 2, "booked": 1, "done": 1, "webchat": 2}
    only = api.get(t["tok_a"], f"/workspaces/{t['ws_a']}/conversations/feed?f=to_you").json()
    assert {i["id"] for i in only["items"]} == {str(pending.id), str(waiting.id)}
    found = api.get(t["tok_a"], f"/workspaces/{t['ws_a']}/conversations/feed?q=terrasse").json()
    assert [i["id"] for i in found["items"]] == [str(pending.id)]
    assert api.get(t["tok_b"], f"/workspaces/{t['ws_a']}/conversations/feed").status_code in (403, 404)   # another workspace: nothing
    assert api.get(t["tok_b"], f"/workspaces/{t['ws_b']}/conversations/feed").json()["counts"]["all"] == 0


def test_resolve_closes_tasks_and_gives_the_chat_back(api, two_workspaces, db):
    t = two_workspaces
    ws = uuid.UUID(t["ws_a"])
    c = _conv(db, t["ws_a"], "phone", "Ring mig op")
    lead = Lead(workspace_id=ws, source="manual", conversation_id=c.id, need_summary="x")
    db.add(lead)
    db.flush()
    db.add(Task(workspace_id=ws, lead_id=lead.id, title="Ring tilbage"))
    db.commit()
    r = api.post(t["tok_a"], f"/workspaces/{t['ws_a']}/conversations/{c.id}/resolve")
    assert r.status_code == 200 and r.json() == {"id": str(c.id), "outcome": "done", "tasks_closed": 1}
    db.expire_all()
    assert db.get(Lead, lead.id).pipeline_status == "contacted"
    chat = _conv(db, t["ws_a"], "webchat", "Hej", mode="staff")
    assert api.post(t["tok_a"], f"/workspaces/{t['ws_a']}/conversations/{chat.id}/resolve").json()["outcome"] == "done"
    assert api.post(t["tok_b"], f"/workspaces/{t['ws_b']}/conversations/{chat.id}/resolve").status_code == 404


def test_week_numbers_and_topics(api, two_workspaces, db):
    t = two_workspaces
    ws = uuid.UUID(t["ws_a"])
    monday = reports.week_start_of(reports.local_today("Europe/Copenhagen"))
    noon = datetime.combine(monday, datetime.min.time(), tzinfo=UTC) + timedelta(hours=11)
    for i, q in enumerate(["Hvad koster vinduer?", "Hvad koster vinduer ca.?", "Koster vinduer meget?", "Laver I vinduer i plast?"]):
        c = _conv(db, t["ws_a"], "webchat", q, at=noon + timedelta(minutes=i), role="assistant")
        if "plast" in q:
            lead = Lead(workspace_id=ws, source="webchat", conversation_id=c.id, need_summary=q)
            db.add(lead)
    db.add(Booking(workspace_id=ws, title="x", starts_at=noon + timedelta(days=3), ends_at=noon + timedelta(days=3, hours=1),
                   source="manual", created_at=noon))
    db.commit()
    w = api.get(t["tok_a"], f"/workspaces/{t['ws_a']}/reports/week").json()
    assert w["start"] == monday.isoformat() and w["answered"] == 4 and w["to_you"] == 1 and w["bookings"] == 1
    assert w["response_seconds"] == 2.0 and sum(d["answered"] + d["to_you"] for d in w["days"]) == 4 and w["campaign_calls"] == 0
    prev = api.get(t["tok_a"], f"/workspaces/{t['ws_a']}/reports/week?start={(monday - timedelta(days=7)).isoformat()}").json()
    assert prev["answered"] == 0 and prev["bookings"] == 0
    topics = api.get(t["tok_a"], f"/workspaces/{t['ws_a']}/reports/topics").json()["items"]
    assert topics[0]["count"] == 3 and topics[0]["could_answer"] is True
    assert any(x["count"] == 1 and x["could_answer"] is False for x in topics)
    assert api.get(t["tok_b"], f"/workspaces/{t['ws_b']}/reports/week").json()["answered"] == 0


def test_bookings_by_week_and_open_weekdays(api, two_workspaces, db):
    t = two_workspaces
    ws = uuid.UUID(t["ws_a"])
    monday = reports.week_start_of(reports.local_today("Europe/Copenhagen"))
    inside = datetime.combine(monday + timedelta(days=2), datetime.min.time(), tzinfo=UTC) + timedelta(hours=9)
    outside = inside + timedelta(days=7)
    for at in (inside, outside):
        db.add(Booking(workspace_id=ws, title="Besigtigelse", starts_at=at, ends_at=at + timedelta(hours=1), source="manual", contact_name="Mette"))
    db.commit()
    r = api.get(t["tok_a"], f"/workspaces/{t['ws_a']}/bookings?start={monday}&end={monday + timedelta(days=6)}").json()
    assert [b["starts_at"][:10] for b in r["items"]] == [inside.date().isoformat()]
    s = api.get(t["tok_a"], f"/workspaces/{t['ws_a']}/bookings/settings").json()
    assert s["open_weekdays"] == [] and s["opening_hours"] == {}                # no approved opening hours yet
    it = api.knowledge(t["tok_a"], t["ws_a"], "opening_hours", "Åbningstider", {"weekly": [{"days": ["mon", "tue", "fri"], "open": "08:00", "close": "16:00"}]})
    api.submit(t["tok_a"], t["ws_a"], it["open_draft"]["id"])
    assert api.approve(t["tok_a"], t["ws_a"], it["open_draft"]["id"]).status_code == 200
    s = api.get(t["tok_a"], f"/workspaces/{t['ws_a']}/bookings/settings").json()
    assert s["open_weekdays"] == [0, 1, 4] and s["opening_hours"]["fri"] == ["08:00–16:00"]

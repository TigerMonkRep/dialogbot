"""QA I01–I05 (voice-qa): the customer's «Opkald og beskeder» (v2 replaces /app/inbox, /app/leads, /app/tasks – see
docs/kundeapp-v2.md §6.6 and the 308 map in web/next.config.ts).

I01 unified list (channels, status, search, filters, assignment) · I02 conversation detail (summary, transcript, linked
enquiry, next action) · I03 structured enquiries · I04 enquiry detail with tasks · I05 follow-up tasks.
Backend through the same endpoints the pages use (conversations/feed, conversations/{id}, leads, tasks). Calls arrive as
Vapi end-of-call reports and chats through the public widget API – offline, no call, no network."""
from __future__ import annotations

import pytest
from sqlalchemy import select

from app.models import Lead, Task
from tests.test_telephony import _post, _setup, configured  # noqa: F401
from tests.test_webchat import PUB, _say, _start, fake, live  # noqa: F401


def _call(client, call_id, caller, turns, summary):
    return _post(client, {
        "type": "end-of-call-report", "endedReason": "customer-ended-call",
        "call": {"id": call_id, "phoneNumberId": "pn_123", "customer": {"number": caller},
                 "startedAt": "2026-11-10T09:00:00Z", "endedAt": "2026-11-10T09:01:30Z"},
        "analysis": {"summary": summary},
        "artifact": {"messages": [{"role": r, "message": m} for r, m in turns]}})


INFO_ONLY = [
    ("bot", "Hej, du har ringet til Fjord Gulvservice. Hvad kan jeg hjælpe med?"),
    ("user", "Hvornår har I åbent på fredag?"),
    ("bot", "Ja. Vi har åbent fra otte til fire på fredag."),
    ("user", "Super, tak. Det var bare det."),
    ("bot", "Selv tak. Hav en god dag."),
]
CALLBACK = [
    ("bot", "Hej, du har ringet til Fjord Gulvservice. Hvad kan jeg hjælpe med?"),
    ("user", "Jeg vil gerne have et tilbud på afslibning, kan I ringe mig op?"),
    ("bot", "Ja, selvfølgelig. Skal vi ringe på det nummer, du ringer fra – det, der ender på fyrre halvtreds?"),
    ("user", "Ja."),
    ("bot", "Så ringer en medarbejder tilbage. Hav en god dag."),
]


def _feed(api, tok, ws, **q):
    qs = "&".join(f"{k}={v}" for k, v in q.items())
    r = api.get(tok, f"/workspaces/{ws}/conversations/feed{'?' + qs if qs else ''}")
    assert r.status_code == 200, r.text
    return r.json()


# --------------------------------------------------------------------------- I01: one list, channels, filters, search

def test_i01_phone_and_webchat_in_one_list_with_filters_search_and_tenant_isolation(client, api, live, configured, db):  # noqa: F811
    t = live
    _setup(api, t, approve=False)  # number pn_123 → ws A (knowledge already approved by `live`)
    assert _call(client, "c_cb", "+4520304050", CALLBACK, "Kunden vil have tilbud på afslibning.").status_code == 200
    conv = _start(client, t["key"]).json()
    assert _say(client, t["key"], conv, "Laver I også trapper?").status_code == 200
    f = _feed(api, t["tok_a"], t["ws_a"])
    assert {i["channel"] for i in f["items"]} == {"phone", "webchat"}
    assert f["counts"]["all"] == 2 and f["counts"]["webchat"] == 1
    phone = next(i for i in f["items"] if i["channel"] == "phone")
    assert phone["outcome"] == "to_you" and phone["lead_id"] and phone["phone"] == "+4520304050"
    # filters and search
    assert [i["channel"] for i in _feed(api, t["tok_a"], t["ws_a"], f="webchat")["items"]] == ["webchat"]
    assert [i["id"] for i in _feed(api, t["tok_a"], t["ws_a"], q="afslibning")["items"]] == [phone["id"]]
    assert [i["id"] for i in _feed(api, t["tok_a"], t["ws_a"], q="40%2050")["items"]] in ([], [phone["id"]])
    assert _feed(api, t["tok_a"], t["ws_a"], q="trapper")["total"] == 1
    assert _feed(api, t["tok_a"], t["ws_a"], q="findes-ikke-xyz")["items"] == []
    # another workspace sees nothing, and cannot open A's conversation or lead
    assert _feed(api, t["tok_b"], t["ws_b"])["items"] == []
    assert api.get(t["tok_b"], f"/workspaces/{t['ws_b']}/conversations/{phone['id']}").status_code == 404
    assert api.get(t["tok_b"], f"/workspaces/{t['ws_a']}/conversations/feed").status_code in (403, 404)
    assert api.get(t["tok_b"], f"/workspaces/{t['ws_b']}/leads/{phone['lead_id']}").status_code == 404


@pytest.mark.xfail(strict=True, reason="F-V2-03-I01: S2 new – Hvert telefonopkald med nummervisning bliver til en henvendelse og en opgave «Ring tilbage til +45…». Det …")
def test_i01_a_call_peter_fully_answered_is_not_put_on_the_to_you_list(client, api, live, configured, db):  # noqa: F811
    """feed.py: «done – Dialogbot handled it»; kundeapp-v2 §6.6: filter «Klaret af Dialogbot». A caller asks for the
    opening hours, gets the answer, says thanks and hangs up – nobody promised a call-back. Today every phone call with a
    caller id becomes a lead + «Ring tilbage til …» task (vapi._after_report), so the call lands in «Til dig»."""
    t = live
    _setup(api, t, approve=False)
    assert _call(client, "c_info", "+4520304050", INFO_ONLY, "Kunden spurgte om åbningstider fredag.").status_code == 200
    items = _feed(api, t["tok_a"], t["ws_a"])["items"]
    tasks = db.scalars(select(Task)).all()
    assert items[0]["outcome"] == "done" and not tasks, (
        f"outcome={items[0]['outcome']!r}, tasks={[x.title for x in tasks]} – an answered question became a call-back task")


# --------------------------------------------------------------------------- I02: detail = transcript + linked enquiry + next action

def test_i02_detail_has_transcript_summary_lead_and_resolve_closes_the_follow_up(client, api, live, configured, db):  # noqa: F811
    t = live
    _setup(api, t, approve=False)
    _call(client, "c_cb2", "+4520304050", CALLBACK, "Kunden vil have tilbud på afslibning.")
    item = _feed(api, t["tok_a"], t["ws_a"])["items"][0]
    d = api.get(t["tok_a"], f"/workspaces/{t['ws_a']}/conversations/{item['id']}").json()
    roles = [m["role"] for m in d["messages"]]
    assert roles[0] == "assistant" and "visitor" in roles and "SYSTEMPROMPT" not in str(d)
    assert d["call"]["from_number"] == "+4520304050"
    assert item["summary"].startswith("Kunden vil have tilbud")
    lead = api.get(t["tok_a"], f"/workspaces/{t['ws_a']}/conversations/{item['id']}/lead").json()["lead"]
    assert lead["id"] == item["lead_id"]
    # «Marker som klaret»: the open task closes, the lead moves on, the row becomes «Klaret»; doing it twice is harmless
    r1 = api.post(t["tok_a"], f"/workspaces/{t['ws_a']}/conversations/{item['id']}/resolve")
    r2 = api.post(t["tok_a"], f"/workspaces/{t['ws_a']}/conversations/{item['id']}/resolve")
    assert r1.json()["tasks_closed"] == 1 and r2.json()["tasks_closed"] == 0 and r2.json()["outcome"] == "done"


def test_i02_reader_and_other_tenant_cannot_resolve(client, api, live, configured, db):  # noqa: F811
    t = live
    _setup(api, t, approve=False)
    _call(client, "c_cb3", "+4520304050", CALLBACK, "Tilbud")
    item = _feed(api, t["tok_a"], t["ws_a"])["items"][0]
    reader = api.add_member(t["tok_a"], t["ws_a"], "reader-i02@testmail.dk", "reader")
    assert api.post(reader, f"/workspaces/{t['ws_a']}/conversations/{item['id']}/resolve").status_code == 403
    assert api.post(t["tok_b"], f"/workspaces/{t['ws_b']}/conversations/{item['id']}/resolve").status_code == 404
    assert db.scalar(select(Task)).status == "open"


# --------------------------------------------------------------------------- I03/I04: enquiries

def test_i03_i04_enquiry_list_filters_detail_tasks_and_optimistic_edit(client, api, live, configured, db):  # noqa: F811
    t = live
    _setup(api, t, approve=False)
    _call(client, "c_cb4", "+4520304050", CALLBACK, "Tilbud på afslibning")
    tok, ws = t["tok_a"], t["ws_a"]
    leads = api.get(tok, f"/workspaces/{ws}/leads").json()
    assert leads["total"] == 1 and leads["items"][0]["source"] == "phone"
    lid = leads["items"][0]["id"]
    assert api.get(tok, f"/workspaces/{ws}/leads?pipeline=new").json()["total"] == 1
    assert api.get(tok, f"/workspaces/{ws}/leads?pipeline=won").json()["total"] == 0
    lead = api.get(tok, f"/workspaces/{ws}/leads/{lid}").json()
    assert lead["conversation_id"] and len(lead["tasks"]) == 1 and lead["tasks"][0]["title"].startswith("Ring tilbage")
    ok = api.patch(tok, f"/workspaces/{ws}/leads/{lid}", {"expected_version": lead["version"], "contact_name": "Mette Hansen"})
    assert ok.status_code == 200, ok.text
    stale = api.patch(tok, f"/workspaces/{ws}/leads/{lid}", {"expected_version": lead["version"], "contact_name": "Gammel"})
    assert stale.status_code == 409
    assert db.get(Lead, lead["id"] if False else db.scalar(select(Lead.id))).contact_name == "Mette Hansen"


# --------------------------------------------------------------------------- I05: tasks

def test_i05_tasks_due_order_assignment_completion_and_scoping(client, api, live, configured, db):  # noqa: F811
    t = live
    tok, ws = t["tok_a"], t["ws_a"]
    staff = api.add_member(tok, ws, "staff-i05@testmail.dk", "staff")
    me = api.get(staff, "/auth/me").json()["id"] if api.get(staff, "/auth/me").status_code == 200 else None
    a = api.post(tok, f"/workspaces/{ws}/tasks", {"title": "Senere", "due_at": "2026-11-20T09:00:00+01:00"}).json()
    b = api.post(tok, f"/workspaces/{ws}/tasks", {"title": "Først", "due_at": "2026-11-12T09:00:00+01:00"}).json()
    assert [x["title"] for x in api.get(tok, f"/workspaces/{ws}/tasks").json()["items"]] == ["Først", "Senere"]
    # assigning to someone outside the workspace is refused; to a member works and «mine» finds it
    outsider = api.get(t["tok_b"], "/auth/me").json()["id"]
    assert api.patch(tok, f"/workspaces/{ws}/tasks/{a['id']}", {"assignee_user_id": outsider}).status_code in (403, 404, 422)
    if me:
        assert api.patch(tok, f"/workspaces/{ws}/tasks/{a['id']}", {"assignee_user_id": me}).status_code == 200
        assert [x["id"] for x in api.get(staff, f"/workspaces/{ws}/tasks?mine=true").json()["items"]] == [a["id"]]
    # completion records who and when; reopen clears it
    done = api.patch(staff, f"/workspaces/{ws}/tasks/{b['id']}", {"status": "done"}).json()
    assert done["status"] == "done" and done["completed_at"]
    assert api.get(tok, f"/workspaces/{ws}/tasks?status=done").json()["total"] == 1
    # another workspace can neither list nor touch them
    assert api.get(t["tok_b"], f"/workspaces/{t['ws_b']}/tasks").json()["total"] == 0
    assert api.patch(t["tok_b"], f"/workspaces/{t['ws_b']}/tasks/{a['id']}", {"status": "done"}).status_code == 404
    # empty title is refused
    assert api.patch(tok, f"/workspaces/{ws}/tasks/{a['id']}", {"title": ""}).status_code == 422

"""QA X09 (e2e-privat, P0): Ønskeliste – reservationer er ALDRIG synlige for ejeren (UI testes i
web/e2e/qa/privat/X09.spec.ts; her: hvert API-svar som rå JSON, outbox/e-mail/push-indhold), og en modtager uden
abonnement kan åbne den delte ønskeliste og ellers næsten intet («Uden plan kan du se og reservere på lister, andre
deler med dig – egne opgaver, lister og opkald kræver en plan», privat.json account.freeNote).

Method for the owner: a differential snapshot. Every GET the owner's app can make is recorded before the givers act and
again after (reserve, re-reserve, pledge on a group gift, unreserve, leave) – the owner must not be able to tell
the difference, byte for byte. Then the outbox and the simulated mailbox are searched for anything about it.
"""
from __future__ import annotations

import json
import uuid

import pytest
from sqlalchemy import select

from app.models import OutboxEvent, PrivateCall, PrivateTask
from app.modules.campaigns import service as campaigns
from app.worker import runner


def _share(api, tok, tid):
    r = api.post(tok, f"/privat/tasks/{tid}/share", {"mode": "wishlist", "role": "editor"})
    assert r.status_code == 200, r.text
    return r.json()


def _item(task, text):
    return next(i for i in task["items"] if i["text"] == text)


def _setup(api, pv):
    mette = pv.account("x09-mette@testmail.dk", "Mette Hansen")  # owner, on the trial
    out = pv.say(mette, "Lav en ønskeliste med cykelhjelm og bog")
    tid = next(m["task_id"] for m in out["messages"] if m["kind"] == "task")
    r = api.post(mette, f"/privat/tasks/{tid}/wishes", {"text": "Sommerhus", "price_minor": 300000, "currency": "DKK",
                                                         "group_gift_enabled": True, "group_gift_target_minor": 300000})
    assert r.status_code == 200, r.text
    other = pv.make_list(mette, "Lav en indkøbsliste med mælk")  # NOT shared
    inv = _share(api, mette, tid)
    ole = pv.user("x09-ole@testmail.dk", "Ole Berg")      # no subscription, no private account until he accepts
    anna = pv.user("x09-anna@testmail.dk", "Anna Holm")
    for tok in (ole, anna):
        r = api.post(tok, f"/privat/invites/{inv['token']}/accept")
        assert r.status_code == 200, r.text
    return mette, ole, anna, tid, other, inv


def _owner_paths(tid):
    return ["/privat/bootstrap", "/privat/me", "/privat/day", "/privat/tasks", "/privat/tasks?shared=1",
            f"/privat/tasks/{tid}", "/privat/messages", f"/privat/messages?task_id={tid}", "/privat/ledger",
            f"/privat/tasks/{tid}/members", f"/privat/tasks/{tid}/invite-status", "/privat/subscription",
            "/privat/addons", "/privat/referrals", "/privat/groups"]


def _snapshot(api, tok, tid) -> dict[str, str]:
    out = {}
    for p in _owner_paths(tid):
        r = api.get(tok, p)
        assert r.status_code == 200, (p, r.text)
        out[p] = r.text
    return out


def _owner_rows(db, ws, email) -> list[str]:
    db.expire_all()
    rows = db.scalars(select(OutboxEvent)).all()
    return sorted(f"{e.event_type}:{e.dedupe_key}" for e in rows
                  if e.workspace_id == ws or email in json.dumps(e.payload, ensure_ascii=False))


def test_owner_learns_nothing_from_any_endpoint_outbox_or_mail(api, pv, db):
    mette, ole, anna, tid, _other, _inv = _setup(api, pv)
    ws = pv.ws(mette)
    runner.drain()
    before = _snapshot(api, mette, tid)
    rows_before = _owner_rows(db, ws, "x09-mette@testmail.dk")
    mail_before = api.c.get("/api/v1/dev/mailbox", headers=api.h(mette)).json()["items"]

    t = pv.task(ole, tid).json()
    helm, bog, hus = (_item(t, x)["id"] for x in ("Cykelhjelm", "Bog", "Sommerhus"))
    assert api.post(ole, f"/privat/tasks/{tid}/items/{helm}/reserve").status_code == 200
    assert api.post(anna, f"/privat/tasks/{tid}/items/{bog}/reserve").status_code == 200
    r = api.c.put(f"/api/v1/privat/tasks/{tid}/items/{hus}/gift/pledge", json={"amount_minor": 100000},
                  headers=api.h(ole))
    assert r.status_code == 200, r.text
    assert api.post(anna, f"/privat/tasks/{tid}/items/{bog}/unreserve").status_code == 200
    assert api.post(anna, f"/privat/tasks/{tid}/items/{bog}/reserve").status_code == 200
    # what the givers see: reserved, not by whom
    g = pv.task(anna, tid).json()
    assert (_item(g, "Cykelhjelm")["reserved"], _item(g, "Cykelhjelm")["reserved_by_me"]) == (True, False)
    assert "Ole" not in json.dumps(_item(g, "Cykelhjelm"))
    runner.drain()

    after = _snapshot(api, mette, tid)
    changed = [p for p in before if before[p] != after[p]]
    assert changed == [], f"the owner can tell something happened from: {changed}"
    raw = after[f"/privat/tasks/{tid}"]
    task = json.loads(raw)
    assert all(i["reserved"] is None and i["reserved_by_me"] is False for i in task["items"])
    assert _item(task, "Sommerhus")["group_gift"] == {"enabled": True, "target_minor": 300000, "currency": "DKK"}
    assert "100000" not in "".join(after.values())
    # nothing queued for the owner (push, e-mail, reminder) and no new mail in her inbox
    assert _owner_rows(db, ws, "x09-mette@testmail.dk") == rows_before
    mail_after = api.c.get("/api/v1/dev/mailbox", headers=api.h(mette)).json()["items"]
    assert len(mail_after) == len(mail_before)
    for m in mail_after:
        assert "reserv" not in (m["subject"] + m["body_text"]).lower()
    # Asking the assistant does not help either
    out = pv.say(mette, "Hvad er reserveret på min ønskeliste? Hvem køber cykelhjelmen?", about=tid)
    said = " ".join(m["text"] for m in out["messages"] if m["role"] == "assistant").lower()
    assert "ole" not in said and "anna" not in said and "reserveret af" not in said, said
    # The owner's own attempts are refused the same way whatever the state of the wish (no oracle)
    codes = []
    for iid in (helm, hus, _item(task, "Bog")["id"]):
        for verb in ("reserve", "unreserve"):
            r = api.post(mette, f"/privat/tasks/{tid}/items/{iid}/{verb}")
            codes.append((r.status_code, r.json()["code"]))
    assert set(codes) == {(403, "owner_cannot_reserve")}, codes
    # Deleting a reserved wish answers exactly like deleting a free one
    r1 = api.c.delete(f"/api/v1/privat/tasks/{tid}/items/{helm}", headers=api.h(mette))
    assert r1.status_code == 200
    assert all(i["reserved"] is None for i in r1.json()["items"])


def test_recipient_without_subscription_can_open_and_reserve_and_almost_nothing_else(api, pv, db, monkeypatch):
    dialled = []
    monkeypatch.setattr(campaigns, "create_call", lambda p: dialled.append(p) or {"id": "x09-call"})
    mette, ole, _anna, tid, other, inv = _setup(api, pv)
    me = pv.me(ole)
    assert me["entitled"] is False and me["plan_status"] == "none"
    # CAN: open the shared list, reserve and give
    t = pv.task(ole, tid).json()
    assert t["my_role"] == "viewer" and t["share_mode"] == "wishlist"  # «kan reservere» (F-UX-03)
    assert t["usage_text"] == "Delt med dig – koster dig ingenting"
    assert t["events"] == []  # the owner's history is not the giver's business
    helm = _item(t, "Cykelhjelm")["id"]
    assert api.post(ole, f"/privat/tasks/{tid}/items/{helm}/reserve").status_code == 200
    # CANNOT: the owner's other lists, editing the wishlist, sharing it, its design, the owner's people
    assert api.get(ole, f"/privat/tasks/{other}").status_code == 404
    assert api.get(ole, f"/privat/tasks/{uuid.uuid4()}").status_code == 404
    assert api.post(ole, f"/privat/tasks/{tid}/items", {"text": "Bil"}).json()["code"] == "owner_only"
    assert api.post(ole, f"/privat/tasks/{tid}/wishes", {"text": "Bil"}).status_code == 403
    assert api.c.patch(f"/api/v1/privat/tasks/{tid}/wishes/{helm}", json={"text": "X"}, headers=api.h(ole)).status_code == 403
    assert api.c.delete(f"/api/v1/privat/tasks/{tid}/items/{helm}", headers=api.h(ole)).status_code == 403
    assert api.post(ole, f"/privat/tasks/{tid}/share", {"mode": "wishlist"}).status_code in (403, 404)
    assert api.post(ole, f"/privat/tasks/{tid}/share/revoke").status_code == 403
    assert api.c.put(f"/api/v1/privat/tasks/{tid}/design", json={"design": None}, headers=api.h(ole)).status_code == 403
    members = api.get(ole, f"/privat/tasks/{tid}/members").json()
    assert "phone" not in json.dumps(members) and "@" not in json.dumps(members)
    assert api.get(ole, f"/privat/tasks/{tid}/invite-status").status_code in (403, 404)
    # CANNOT: own tasks go live, Shop apps, calls
    out = pv.say(ole, "Lav en liste med kaffe og te")
    assert next(m["kind"] for m in out["messages"] if m["role"] == "assistant") == "draft"
    assert api.post(ole, "/privat/addons/kalender/enable").status_code >= 400
    assert api.post(ole, "/privat/addons/foedselsdage/enable").status_code >= 400
    db.expire_all()
    ws = pv.ws(ole)
    assert db.query(PrivateTask).filter(PrivateTask.workspace_id == ws, PrivateTask.status == "in_progress").count() == 0
    # «… egne opgaver, lister og opkald kræver en plan»: no call can be approved without a plan
    pv.verify_phone(ole)
    ask = "Ring til cykelværkstedet og find en tid torsdag efter klokken tre"
    out = pv.say(ole, ask)
    assert out["messages"][-1]["kind"] == "addon"  # «Det kræver tilføjelsen Ring for mig»
    en = api.post(ole, "/privat/addons/ring-for-mig/enable")
    assert en.status_code == 409 and en.json()["code"] == "needs_plan", en.text
    db.expire_all()
    assert dialled == [] and db.query(PrivateCall).filter(PrivateCall.workspace_id == ws).count() == 0


def test_shared_link_preview_is_public_but_shows_no_wishes_or_reservations(api, pv):
    mette, ole, _anna, tid, _other, inv = _setup(api, pv)
    t = pv.task(ole, tid).json()
    api.post(ole, f"/privat/tasks/{tid}/items/{_item(t, 'Cykelhjelm')['id']}/reserve")
    for path in (f"/api/v1/privat/invites/{inv['token']}", f"/api/v1/privat/invites/by-code/{inv['short_code']}"):
        r = api.c.get(path)
        assert r.status_code == 200, r.text
        blob = r.text.lower()
        assert "cykelhjelm" not in blob and "reserv" not in blob and "ole" not in blob, blob
        assert r.json()["item_count"] == 3
    # without a login, nothing else of Privat answers
    for path in (f"/api/v1/privat/tasks/{tid}", "/api/v1/privat/bootstrap", f"/api/v1/privat/tasks/{tid}/members"):
        assert api.c.get(path).status_code == 401


@pytest.mark.xfail(strict=True, reason="F-PQ-03-X09: needs-decision – open finding (status new), not fixed in c3bed12")
def test_recipient_without_subscription_cannot_make_own_tasks_live_through_the_api(api, pv, db):
    """The web hides «Brug 3 kr. fra saldoen» and «Se et sponsorindslag» from an account without a plan (status none) and says
    «Uden plan kan du se og reservere på lister, andre deler med dig – egne opgaver, lister og opkald kræver en plan»
    (privat.json account.freeNote / plan.noteNone). The API must hold the same line, or the paywall is a UI-only gate."""
    _mette, ole, _anna, _tid, _other, _inv = _setup(api, pv)
    out = pv.say(ole, "Lav en liste med kaffe og te")
    d1 = next(m["task_id"] for m in out["messages"] if m.get("task_id"))
    out = pv.say(ole, "Lav en liste med mælk")
    d2 = next(m["task_id"] for m in out["messages"] if m.get("task_id"))
    r1 = api.post(ole, f"/privat/tasks/{d1}/activate", {"method": "balance"})
    r2 = api.post(ole, "/privat/sponsor/claim", {"task_id": d2})
    db.expire_all()
    live = db.query(PrivateTask).filter(PrivateTask.workspace_id == pv.ws(ole), PrivateTask.status != "draft").count()
    assert (r1.status_code, r2.status_code, live) == (409, 409, 0), \
        f"balance → {r1.status_code} {r1.json().get('usage_text')}; sponsor → {r2.status_code} {r2.json().get('usage_text')}"

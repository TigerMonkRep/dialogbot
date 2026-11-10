"""QA X11 (e2e-privat, P0): Opkald til virksomheder på brugerens vegne sker KUN efter eksplicit godkendelse
(POST /privat/calls/{id}/approve). Intet opkald og intet planlagt opkald i outbox uden godkendelse – heller ikke ved
dobbelt-klik, reload, svar i chatten, afvisning, nyt forsøg eller når virksomheden har lukket.

«Dialled» = what reached campaigns.create_call (the only door to Vapi, replaced here). «Queued» = outbox rows of type
privat.call_due (the worker dials those) and private_calls rows past «proposed». Both are asserted directly in the DB.
"""
from __future__ import annotations

import threading
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.models import OutboxEvent, PrivateCall
from app.modules.campaigns import service as campaigns
from app.worker import runner
from tests.test_privat_places_push import THU_9, WEEK, _periods, _pick, dial, fake_places  # noqa: F401  (fixtures)


@pytest.fixture
def dialled(monkeypatch):
    calls: list[dict] = []
    lock = threading.Lock()

    def fake(p):
        with lock:
            calls.append(p)
            return {"id": f"x11_{len(calls)}"}

    monkeypatch.setattr(campaigns, "create_call", fake)
    return calls


def _state(db):
    db.expire_all()
    return ([(c.status, c.approved_at is not None) for c in db.query(PrivateCall).order_by(PrivateCall.created_at)],
            db.query(OutboxEvent).filter(OutboxEvent.event_type == "privat.call_due").count())


def _proposal(api, pv, tok, fake_places, *, open_now=True, phone="+4586112233"):  # noqa: F811
    days = WEEK if open_now else [4]  # Wed 4 Nov 10:00 is «now»; [4] = Thursdays only → closed now
    fake_places([{"id": "fona-1", "name": "Fona", "phone": phone, "periods": _periods(days)}])
    api.c.patch("/api/v1/privat/me/location", json={"city": "Aarhus"}, headers=api.h(tok))
    _clar, msgs = _pick(api, pv, tok)
    prop = msgs[-1]
    assert prop["kind"] == "call_proposal", msgs
    return prop["task_id"]


def test_proposal_reload_and_chat_yes_never_dial(api, pv, db, fake_places, dialled):  # noqa: F811
    tok = pv.account("x11-a@testmail.dk")
    pv.verify_phone(tok)
    tid = _proposal(api, pv, tok, fake_places)
    for _ in range(3):  # reload of the task, the day and the whole app
        assert pv.task(tok, tid).json()["status"] == "awaiting_user"
        api.get(tok, "/privat/bootstrap")
        api.get(tok, "/privat/day")
    # answering in the chat is not an approval
    for text in ("Ja, ring til dem", "Godkend opkaldet", "ja", "Ring nu!"):
        pv.say(tok, text, about=tid)
    runner.drain()
    assert dialled == []
    assert _state(db) == ([("proposed", False)], 0)
    t = pv.task(tok, tid).json()
    assert t["status"] == "awaiting_user" and t["call"]["status"] == "proposed"


def test_decline_then_approve_never_dials_and_others_cannot_approve(api, pv, db, fake_places, dialled):  # noqa: F811
    mette = pv.account("x11-b@testmail.dk", "Mette Hansen")
    pv.verify_phone(mette)
    tid = _proposal(api, pv, mette, fake_places)
    # a stranger, and a member of one of Mette's shared lists, cannot approve her call
    ole = pv.account("x11-ole@testmail.dk", "Ole Berg")
    pv.verify_phone(ole, "+4520304051")
    lst = pv.make_list(mette)
    inv = api.post(mette, f"/privat/tasks/{lst}/share", {"mode": "group", "role": "editor"}).json()
    api.post(ole, f"/privat/invites/{inv['token']}/accept")
    for path in (f"/privat/calls/{tid}/approve", f"/privat/calls/{tid}/retry"):
        r = api.post(ole, path, {"share_phone": False})
        assert r.status_code == 404, r.text
    # declined: nothing, and approving afterwards (stale tab / double tap on the other button) does nothing
    assert api.post(mette, f"/privat/calls/{tid}/decline").json()["status"] == "declined"
    r = api.post(mette, f"/privat/calls/{tid}/approve", {"share_phone": False})
    assert r.status_code == 200 and r.json()["status"] == "declined"
    assert api.post(mette, f"/privat/calls/{tid}/decline").json()["status"] == "declined"
    runner.drain()
    assert dialled == [] and _state(db) == ([("declined", False)], 0)
    # «Prøv igen» gives a NEW proposal, still nothing dialled until it is approved
    t = api.post(mette, f"/privat/calls/{tid}/retry").json()
    assert t["status"] == "awaiting_user"
    runner.drain()
    assert dialled == [] and _state(db) == ([("declined", False), ("proposed", False)], 0)
    t = api.post(mette, f"/privat/calls/{tid}/approve", {"share_phone": False}).json()
    assert t["status"] == "in_progress" and len(dialled) == 1  # positive control: the approval does dial


def test_double_click_and_parallel_approvals_dial_once(api, pv, db, app, fake_places, dialled):  # noqa: F811
    tok = pv.account("x11-c@testmail.dk")
    pv.verify_phone(tok)
    tid = _proposal(api, pv, tok, fake_places)
    barrier = threading.Barrier(6)
    codes: list[int] = []

    def go(i):
        c = TestClient(app)
        headers = {"Authorization": f"Bearer {tok}"}
        if i % 2:
            headers["Idempotency-Key"] = "x11-same-key"  # the web's own retry
        barrier.wait()
        codes.append(c.post(f"/api/v1/privat/calls/{tid}/approve", json={"share_phone": False}, headers=headers).status_code)

    threads = [threading.Thread(target=go, args=(i,)) for i in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert all(c < 500 for c in codes), codes
    assert len(dialled) == 1, f"{len(dialled)} calls dialled for one approval"
    # and again, sequentially, as a user hammering the button after a reload
    for _ in range(3):
        api.post(tok, f"/privat/calls/{tid}/approve", {"share_phone": False})
    runner.drain()
    db.expire_all()
    assert len(dialled) == 1 and db.query(PrivateCall).count() == 1


def test_refused_approvals_queue_nothing(api, pv, db, fake_places, dialled):  # noqa: F811
    tok = pv.account("x11-d@testmail.dk")
    tid = _proposal(api, pv, tok, fake_places)
    r = api.post(tok, f"/privat/calls/{tid}/approve", {"share_phone": False})
    assert r.status_code == 409 and r.json()["code"] == "needs_phone"
    pv.verify_phone(tok)
    pv.clock.at = datetime(2026, 11, 4, 17, 30, tzinfo=UTC)  # 18:30 in Copenhagen
    r = api.post(tok, f"/privat/calls/{tid}/approve", {"share_phone": False})
    assert r.status_code == 409 and r.json()["code"] in ("outside_hours", "business_closed")
    runner.drain()
    assert dialled == [] and _state(db) == ([("proposed", False)], 0)


def test_mobile_number_needs_explicit_business_confirmation(api, pv, db, fake_places, dialled):  # noqa: F811
    tok = pv.account("x11-e@testmail.dk")
    pv.verify_phone(tok)
    tid = _proposal(api, pv, tok, fake_places, phone="+4520304099")
    r = api.post(tok, f"/privat/calls/{tid}/approve", {"share_phone": False})
    assert r.status_code == 409 and r.json()["code"] == "confirm_business"
    assert dialled == [] and _state(db) == ([("proposed", False)], 0)


def test_closed_business_ask_again_and_cancelled_schedule_never_dial(api, pv, db, fake_places, dialled):  # noqa: F811
    tok = pv.account("x11-f@testmail.dk")
    pv.verify_phone(tok)
    _proposal(api, pv, tok, fake_places, open_now=False)
    # the «ask again when they open» reminder is queued – it must never dial by itself
    assert _state(db) == ([("proposed", False)], 0)
    pv.clock.at = THU_9 + timedelta(minutes=1)
    db.query(OutboxEvent).update({"next_attempt_at": datetime.now(UTC)}, synchronize_session=False)
    db.commit()
    runner.drain()
    assert dialled == [] and _state(db) == ([("proposed", False)], 0)


def test_cancelled_scheduled_call_is_never_dialled(api, pv, db, fake_places, dialled):  # noqa: F811
    tok = pv.account("x11-g@testmail.dk")
    pv.verify_phone(tok)
    tid = _proposal(api, pv, tok, fake_places, open_now=False)
    # approved «ved næste åbningstid», then cancelled before it opens: the queued call_due must not dial
    t = api.post(tok, f"/privat/calls/{tid}/approve", {"share_phone": False, "at_next_open": True}).json()
    assert t["status"] == "planned" and dialled == []
    assert _state(db)[1] == 1
    assert api.post(tok, f"/privat/calls/{tid}/decline").json()["status"] == "declined"
    pv.clock.at = THU_9 + timedelta(minutes=1)
    db.query(OutboxEvent).update({"next_attempt_at": datetime.now(UTC)}, synchronize_session=False)
    db.commit()
    runner.drain()
    assert dialled == [], "a cancelled scheduled call was dialled"
    # a retry after the cancel is a fresh proposal; the old queued event still does nothing
    api.post(tok, f"/privat/calls/{tid}/retry")
    db.query(OutboxEvent).update({"next_attempt_at": datetime.now(UTC), "status": "queued"}, synchronize_session=False)
    db.commit()
    runner.drain()
    assert dialled == []
    assert [s for s, _ in _state(db)[0]] == ["declined", "proposed"]

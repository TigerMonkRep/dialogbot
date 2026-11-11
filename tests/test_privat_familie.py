"""Dialogbot Privat – Familie: the household (PC-ENT-08, «Op til 5 personer»).

The owner invites through the ordinary invitation (a link from their own phone), the invitee accepts with their own
account and gets the plan's rights (Plus apps, the household's shared 25 calls) – never anybody's data. Rights follow the
owner's subscription live: removed, left, downgraded or cancelled = gone on the next request."""
from __future__ import annotations

from datetime import timedelta

from app.models import PrivateCall, PrivateHouseholdMember, PrivateInvite
from tests.privat_fixtures import WED_10


def _familie(api, pv, email="mette@testmail.dk", name="Mette Hansen") -> str:
    tok = pv.account(email, name, trial=False)
    pv.set_plan(tok, "familie")
    return tok


def _invite(api, tok) -> dict:
    r = api.post(tok, "/privat/household/invites")
    assert r.status_code == 200, r.text
    return r.json()


def _join(api, tok, inv) -> dict:
    return api.post(tok, f"/privat/invites/{inv['token']}/accept")


def _member(api, pv, owner, email, name="Ole Berg") -> str:
    tok = pv.user(email, name)
    r = _join(api, tok, _invite(api, owner))
    assert r.status_code == 200, r.text
    return tok


def test_member_gets_the_plan_rights_and_nobodys_data(api, pv, db):
    mette = _familie(api, pv)
    inv = _invite(api, mette)
    # the SMS is sent from Mette's own phone; the preview never shows names
    assert "Familie" in inv["suggested_text"] and inv["short_code"] in inv["suggested_text"]
    pre = api.c.get(f"/api/v1/privat/invites/{inv['token']}").json()
    assert pre["title"] == "Familie" and pre["household"] == {"count": 1, "limit": 5, "active": True}
    ole = pv.user("ole@testmail.dk", "Ole Berg")
    r = _join(api, ole, inv)  # creates Ole's own private account
    assert r.status_code == 200, r.text
    assert r.json()["household"]["role"] == "member" and r.json()["household"]["owner_first_name"] == "Mette"
    sub = pv.subscription(ole)
    assert (sub["plan"], sub["status"], sub["entitled"], sub["calls_quota"], sub["people_limit"]) == \
        ("familie", "active", True, 25, 5)
    assert sub["interval"] is None  # Ole is not billed
    # a Plus app can be switched on by the member
    assert api.post(ole, "/privat/addons/foedselsdage/enable").status_code == 200
    # isolation: Mette's list is not Ole's, Ole's is not Mette's
    m_list = pv.make_list(mette, "Lav en indkøbsliste med mælk og rugbrød")
    o_list = pv.make_list(ole, "Lav en indkøbsliste med kaffe og te")
    assert pv.task(ole, m_list).status_code == 404 and pv.task(mette, o_list).status_code == 404
    assert [t["id"] for t in api.get(ole, "/privat/tasks").json()] == [o_list]
    assert [t["id"] for t in api.get(mette, "/privat/tasks").json()] == [m_list]
    assert "mælk" not in api.get(ole, "/privat/messages").text  # his own chat only
    # the owner sees first names only
    h = api.get(mette, "/privat/household").json()
    assert h["role"] == "owner" and h["count"] == 2 and h["can_invite"] is True
    assert [m["name"] for m in h["members"]] == ["Ole"] and set(h["members"][0]) == {"id", "name", "is_me"}


def test_limit_is_five_people(api, pv, db):
    mette = _familie(api, pv)
    early = _invite(api, mette)  # made while there was room
    for i in range(4):
        _member(api, pv, mette, f"m{i}@testmail.dk", f"Person{i} X")
    h = api.get(mette, "/privat/household").json()
    assert h["count"] == 5 and h["can_invite"] is False
    r = api.post(mette, "/privat/household/invites")
    assert r.status_code == 409 and r.json()["code"] == "household_full"
    sixth = pv.user("sixth@testmail.dk", "Six Th")
    r = _join(api, sixth, early)  # an older invite cannot make it six
    assert r.status_code == 409 and r.json()["code"] == "household_full"
    api.post(sixth, "/privat/account")
    assert pv.subscription(sixth)["entitled"] is False
    db.expire_all()
    assert db.query(PrivateHouseholdMember).count() == 4


def test_double_accept_same_invite(api, pv, db):
    mette = _familie(api, pv)
    inv = _invite(api, mette)
    ole = pv.user("ole@testmail.dk", "Ole Berg")
    assert _join(api, ole, inv).status_code == 200
    r = _join(api, ole, inv)
    assert r.status_code == 200 and r.json()["household"]["role"] == "member"
    db.expire_all()
    assert db.query(PrivateHouseholdMember).count() == 1
    assert db.query(PrivateInvite).filter_by(resource_type="household").one().accepted_count == 1
    # the owner cannot join their own household; a member cannot join a second one
    assert _join(api, mette, inv).json()["code"] == "own_household"
    anna = _familie(api, pv, "anna@testmail.dk", "Anna Holm")
    r = _join(api, ole, _invite(api, anna))
    assert r.status_code == 409 and r.json()["code"] == "already_in_household"
    # a member cannot invite
    r = api.post(ole, "/privat/household/invites")
    assert r.status_code == 409 and r.json()["code"] == "household_member"


def test_removed_member_loses_access_at_once_and_keeps_own_data(api, pv, db):
    mette = _familie(api, pv)
    ole = _member(api, pv, mette, "ole@testmail.dk")
    o_list = pv.make_list(ole, "Lav en indkøbsliste med kaffe og te")
    assert pv.subscription(ole)["entitled"] is True
    mid = api.get(mette, "/privat/household").json()["members"][0]["id"]
    assert api.delete(mette, f"/privat/household/members/{mid}").status_code == 204
    sub = pv.subscription(ole)
    assert (sub["plan"], sub["entitled"], sub["calls_quota"]) == ("none", False, 0)
    r = api.post(ole, "/privat/addons/madplan/enable")
    assert r.status_code == 409 and r.json()["code"] == "needs_plan"
    assert pv.task(ole, o_list).status_code == 200  # his data stays his
    assert api.get(ole, "/privat/household").json()["role"] is None
    # someone else's member id: 404
    anna = _familie(api, pv, "anna@testmail.dk", "Anna Holm")
    pia = _member(api, pv, anna, "pia@testmail.dk", "Pia Lund")
    pid = api.get(anna, "/privat/household").json()["members"][0]["id"]
    assert api.delete(mette, f"/privat/household/members/{pid}").status_code == 404
    assert pv.subscription(pia)["entitled"] is True
    # leaving
    assert api.post(pia, "/privat/household/leave").status_code == 204
    assert pv.subscription(pia)["entitled"] is False
    assert api.post(pia, "/privat/household/leave").status_code == 404


def test_downgrade_and_cancellation_end_the_members_rights(api, pv, db):
    mette = _familie(api, pv)
    ole = _member(api, pv, mette, "ole@testmail.dk")
    pv.set_plan(mette, "plus")  # downgrade in the Billing Portal
    assert pv.subscription(ole)["entitled"] is False
    h = api.get(mette, "/privat/household").json()
    assert h["active"] is False and h["can_invite"] is False and h["count"] == 2  # paused, not dissolved
    assert api.get(ole, "/privat/household").json()["active"] is False
    pv.set_plan(mette, "familie")
    assert pv.subscription(ole)["entitled"] is True  # back with Familie
    pv.set_plan(mette, "familie", status="canceled", period_days=3)
    assert pv.subscription(ole)["entitled"] is True  # paid period still runs
    pv.clock.at = WED_10 + timedelta(days=4)
    assert pv.subscription(ole)["entitled"] is False
    # an invite of a paused household cannot be accepted
    pv.clock.at = WED_10
    pv.set_plan(mette, "plus")
    r = api.post(mette, "/privat/household/invites")
    assert r.status_code == 409 and r.json()["code"] == "needs_plan"


def test_the_25_calls_are_the_households(api, pv, db):
    """Familie = 25 calls a month for the plan (Plus is 10 for one person): one quota for everybody drawing on it."""
    mette = _familie(api, pv)
    ole = _member(api, pv, mette, "ole@testmail.dk")
    from app.models import PrivateTask

    ws_m, ws_o = pv.ws(mette), pv.ws(ole)
    for i, ws in enumerate([ws_m] * 3 + [ws_o] * 2):
        t = PrivateTask(workspace_id=ws, kind="call", title="x", status="done")
        db.add(t)
        db.flush()
        db.add(PrivateCall(workspace_id=ws, task_id=t.id, business_name=f"B{i}", paid_via="plan", status="answered",
                           result="answered", approved_at=WED_10 - timedelta(minutes=i)))
    db.commit()
    assert (pv.subscription(mette)["calls_used"], pv.subscription(ole)["calls_used"]) == (5, 5)
    assert pv.subscription(ole)["calls_left"] == 20
    # out of the household: Ole's calls no longer count on Mette's quota
    mid = api.get(mette, "/privat/household").json()["members"][0]["id"]
    api.delete(mette, f"/privat/household/members/{mid}")
    assert pv.subscription(mette)["calls_used"] == 3

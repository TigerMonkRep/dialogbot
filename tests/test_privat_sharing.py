"""Dialogbot Privat: shared lists and wishlists, the generic invitation, referrals, the add-on shop and groups."""
from __future__ import annotations

import json
import uuid
from datetime import timedelta

import pytest

from app.models import CreditLedger, PrivateGroupMember, PrivateInvite, PrivateReferral
from app.modules.integrations.connectors.fakes import WORLD
from app.modules.privat import addons, invites


def _share(api, tok, tid, mode="group", role="editor") -> dict:
    r = api.post(tok, f"/privat/tasks/{tid}/share", {"mode": mode, "role": role})
    assert r.status_code == 200, r.text
    return r.json()


def _accept(api, tok, token) -> dict:
    r = api.post(tok, f"/privat/invites/{token}/accept")
    assert r.status_code == 200, r.text
    return r.json()


def _item(task, text):
    return next(i for i in task["items"] if i["text"] == text)


# --------------------------------------------------------------------------- shared lists

def test_shared_grocery(api, pv):
    mette = pv.account("mette@testmail.dk", "Mette Hansen")
    ole = pv.user("ole@testmail.dk", "Ole Berg")
    tid = pv.make_list(mette)
    inv = _share(api, mette, tid)
    t = _accept(api, ole, inv["token"])  # creates Ole's private account
    assert t["my_role"] == "editor" and t["shared"] is True and t["share_mode"] == "group"
    assert t["usage_text"] == "Delt med dig – koster dig ingenting"
    t = api.post(ole, f"/privat/tasks/{tid}/items", {"text": "Smør"}).json()
    api.post(ole, f"/privat/tasks/{tid}/items/{_item(t, 'Mælk')['id']}/toggle")
    pv.say(ole, "Tilføj kaffe", about=tid)  # the chat works on a shared list the user may edit
    t = api.post(mette, f"/privat/tasks/{tid}/items/{_item(t, 'Smør')['id']}/toggle").json()
    assert (_item(t, "Smør")["added_by_name"], _item(t, "Smør")["done_by_name"]) == ("Ole Berg", "Mette Hansen")
    assert (_item(t, "Mælk")["added_by_name"], _item(t, "Mælk")["done_by_name"]) == ("Mette Hansen", "Ole Berg")
    assert _item(t, "Kaffe")["added_by_name"] == "Ole Berg"
    assert {m["name"]: m["role"] for m in t["members"]} == {"Mette Hansen": "owner", "Ole Berg": "editor"}
    assert any(e["text"].startswith("Ole: Tilføjet: smør") for e in t["events"])
    # one task for the owner, nothing for the member
    assert pv.me(mette)["free_used"] == 1 and pv.me(ole)["free_used"] == 0
    assert [x["id"] for x in api.get(ole, "/privat/tasks?shared=1").json()] == [tid]


def _wishlist(api, pv):
    mette = pv.account("mette@testmail.dk", "Mette Hansen")
    out = pv.say(mette, "Lav en ønskeliste med cykel og bog")
    tid = next(m["task_id"] for m in out["messages"] if m["kind"] == "task")
    t = api.post(mette, f"/privat/tasks/{tid}/items", {"text": "Ur", "note": "Gerne sort", "link": "https://ur.dk/x"}).json()
    assert t["list_type"] == "wishlist"
    inv = _share(api, mette, tid, mode="wishlist")
    ole, anna = pv.user("ole@testmail.dk", "Ole Berg"), pv.user("anna@testmail.dk", "Anna Holm")
    _accept(api, ole, inv["token"])
    _accept(api, anna, inv["token"])
    return mette, ole, anna, tid


def test_wishlist_secret(api, pv):
    mette, ole, anna, tid = _wishlist(api, pv)
    before = pv.task(mette, tid).json()
    cykel = _item(before, "Cykel")["id"]
    t = api.post(ole, f"/privat/tasks/{tid}/items/{cykel}/reserve").json()
    assert _item(t, "Cykel")["reserved_by_me"] is True
    t = pv.task(anna, tid).json()
    assert (_item(t, "Cykel")["reserved"], _item(t, "Cykel")["reserved_by_me"]) == (True, False)
    assert "Ole" not in json.dumps([i for i in t["items"]])  # not WHO reserved
    r = api.post(anna, f"/privat/tasks/{tid}/items/{cykel}/reserve")
    assert r.status_code == 409 and r.json()["code"] == "already_reserved"
    assert api.post(ole, f"/privat/tasks/{tid}/items/{cykel}/toggle").json()["code"] == "use_reserve"
    assert api.post(ole, f"/privat/tasks/{tid}/items", {"text": "Bil"}).json()["code"] == "owner_only"
    assert api.post(mette, f"/privat/tasks/{tid}/items/{cykel}/reserve").json()["code"] == "owner_cannot_reserve"
    # the owner learns NOTHING – from any endpoint, the chat included
    pv.say(mette, "Tilføj sokker", about=tid)
    pv.say(mette, "Hvad venter på mig?")
    after = pv.task(mette, tid).json()
    assert after["updated_at"] == pv.task(mette, tid).json()["updated_at"]
    assert all(i["reserved"] is None and i["reserved_by_me"] is False for i in after["items"])
    for path in (f"/privat/tasks/{tid}", "/privat/tasks", "/privat/tasks?shared=1", "/privat/day", "/privat/messages",
                 f"/privat/messages?task_id={tid}", f"/privat/tasks/{tid}/members", f"/privat/tasks/{tid}/invite-status",
                 "/privat/ledger", "/privat/me"):
        blob = api.get(mette, path).text
        assert '"reserved":true' not in blob.replace(" ", "") and "reserv" not in blob.replace('"reserved"', "") \
            .replace('"reserved_by_me"', ""), path
    ev_before = [e["text"] for e in before["events"]]
    assert [e["text"] for e in after["events"]][:len(ev_before)] == ev_before
    assert not any("reserv" in e["text"].lower() for e in after["events"])
    # un-reserve: only the one who reserved
    assert api.post(anna, f"/privat/tasks/{tid}/items/{cykel}/unreserve").json()["code"] == "not_reserved_by_you"
    t = api.post(ole, f"/privat/tasks/{tid}/items/{cykel}/unreserve").json()
    assert _item(t, "Cykel")["reserved"] is False


def test_invite_revoke_expire(api, pv):
    mette = pv.account("mette@testmail.dk")
    ole = pv.user("ole@testmail.dk", "Ole Berg")
    tid = pv.make_list(mette)
    inv = _share(api, mette, tid)
    assert api.get(mette, f"/privat/invites/{inv['token']}").status_code == 200
    api.post(mette, f"/privat/tasks/{tid}/share/revoke")
    assert api.c.get(f"/api/v1/privat/invites/{inv['token']}").json()["code"] == "invite_invalid"
    assert api.c.get(f"/api/v1/privat/invites/by-code/{inv['short_code']}").status_code == 404
    assert api.post(ole, f"/privat/invites/{inv['token']}/accept").status_code == 404
    inv2 = _share(api, mette, tid)
    pv.clock.at += timedelta(days=31)
    assert api.c.get(f"/api/v1/privat/invites/{inv2['token']}").status_code == 404
    assert api.post(ole, f"/privat/invites/by-code/{inv2['short_code']}/accept").status_code == 404
    pv.clock.at -= timedelta(days=2)
    t = api.post(ole, f"/privat/invites/by-code/{inv2['short_code'].lower()}/accept").json()  # case-insensitive
    assert t["my_role"] == "editor"


def test_shared_isolation(api, pv):
    mette = pv.account("mette@testmail.dk")
    ole, eve = pv.user("ole@testmail.dk", "Ole Berg"), pv.account("eve@testmail.dk", "Eve Ude")
    tid = pv.make_list(mette)
    inv = _share(api, mette, tid, role="viewer")
    t = _accept(api, ole, inv["token"])
    item = t["items"][0]["id"]
    for method, path, body in (("get", f"/privat/tasks/{tid}", None), ("get", f"/privat/tasks/{tid}/members", None),
                               ("post", f"/privat/tasks/{tid}/items", {"text": "x"}),
                               ("post", f"/privat/tasks/{tid}/items/{item}/toggle", None),
                               ("post", f"/privat/tasks/{tid}/items/{item}/reserve", None),
                               ("get", f"/privat/tasks/{tid}/invite-status", None),
                               ("post", f"/privat/tasks/{tid}/share", {"mode": "group"})):
        r = api.get(eve, path) if method == "get" else api.post(eve, path, body)
        assert r.status_code == 404, (path, r.text)
    assert api.get(eve, "/privat/tasks").json() == []
    # a viewer reads but cannot change or share
    assert api.post(ole, f"/privat/tasks/{tid}/items", {"text": "x"}).json()["code"] == "read_only"
    assert api.post(ole, f"/privat/tasks/{tid}/share", {"mode": "group"}).status_code == 403
    assert api.get(ole, f"/privat/tasks/{tid}/invite-status").status_code == 403
    # owner pauses sharing by switching the add-on off: the member cannot open the list, data is kept
    api.post(mette, "/privat/addons/delte-lister/disable")
    assert api.get(ole, f"/privat/tasks/{tid}").json()["code"] == "sharing_paused"
    assert api.get(ole, "/privat/tasks").json() == []
    assert api.get(mette, f"/privat/tasks/{tid}").status_code == 200
    api.post(mette, "/privat/addons/delte-lister/enable")
    assert api.get(ole, f"/privat/tasks/{tid}").status_code == 200
    # removed → 404
    me = next(m for m in api.get(ole, f"/privat/tasks/{tid}/members").json() if m["is_me"])
    api.delete(mette, f"/privat/tasks/{tid}/members/{me['id']}")
    assert api.get(ole, f"/privat/tasks/{tid}").status_code == 404


def test_invite_preview_leaks_nothing(api, pv):
    mette, ole, anna, tid = _wishlist(api, pv)
    cykel = _item(pv.task(ole, tid).json(), "Cykel")["id"]
    api.post(ole, f"/privat/tasks/{tid}/items/{cykel}/reserve")
    inv = _share(api, mette, tid, mode="wishlist")
    p = api.c.get(f"/api/v1/privat/invites/{inv['token']}").json()
    assert set(p) == {"title", "owner_first_name", "list_type", "item_count", "share_mode", "inviter_first_name",
                      "resource_type", "addon_key", "cta_text"}
    assert (p["owner_first_name"], p["item_count"], p["list_type"], p["addon_key"]) == ("Mette", 3, "wishlist",
                                                                                          "oenskelister")
    blob = json.dumps(p, ensure_ascii=False).lower()
    for secret in ("cykel", "bog", "ur.dk", "sort", "ole", "anna", "reserv", "hansen", "@"):
        assert secret not in blob, secret
    assert p["cta_text"].startswith("Mette bruger Dialogbot")
    p2 = api.c.get(f"/api/v1/privat/invites/by-code/{inv['short_code']}").json()
    assert p2["title"] == p["title"]
    from app.db import get_session_factory

    with get_session_factory()() as s:
        assert s.query(PrivateInvite).filter_by(short_code=inv["short_code"]).one().opened_count == 2


def test_short_code_collision_and_suggested_text(api, pv, monkeypatch):
    mette = pv.account("mette@testmail.dk", "Mette-Marie Østergård 😀")
    tid = pv.make_list(mette)
    first = _share(api, mette, tid)
    codes = iter([first["short_code"], first["short_code"], "K7Q2M9XA"])
    monkeypatch.setattr(invites, "new_short_code", lambda: next(codes))
    second = _share(api, mette, tid)
    assert second["short_code"] == "K7Q2M9XA" and second["short_url"] == "https://dialogbot.app/i/K7Q2M9XA"
    assert set(second) >= {"invite_url", "short_url", "short_code", "suggested_text"}
    out = pv.say(mette, "Lav en ønskeliste med " + ", ".join(f"ting nummer {i}" for i in range(20)))
    wid = next(m["task_id"] for m in out["messages"] if m["kind"] == "task")
    monkeypatch.undo()
    for t, mode in ((tid, "group"), (wid, "wishlist")):
        txt = _share(api, mette, t, mode=mode)["suggested_text"]
        assert len(txt) <= 160 and all(ch in invites.GSM7 for ch in txt), txt
        assert txt.endswith("- Mette-Marie") and "dialogbot.app/i/" in txt
    assert "indkøbsliste" in _share(api, mette, tid)["suggested_text"]


# --------------------------------------------------------------------------- add-ons

def test_addon_gating(api, pv, monkeypatch):
    from app.modules.campaigns import service as campaigns

    called = []
    monkeypatch.setattr(campaigns, "create_call", lambda p: called.append(p) or {"id": "x"})
    tok = pv.account("mette@testmail.dk")
    cat = {a["key"]: a for a in api.get(tok, "/privat/addons").json()}
    assert {k: (a["status"], a["enabled"]) for k, a in cat.items()} == {
        "ring-for-mig": ("available", True), "delte-lister": ("available", True), "oenskelister": ("available", True),
        "kalender": ("coming_soon", False), "pakker": ("coming_soon", False)}
    assert api.post(tok, "/privat/addons/kalender/enable").json()["code"] == "coming_soon"
    out = pv.say(tok, "Ring til cykelværkstedet og find en tid torsdag efter klokken tre")
    clar = out["messages"][-1]
    tid = api.post(tok, f"/privat/messages/{clar['id']}/options/{clar['options'][0]['id']}").json()["messages"][-1]["task_id"]
    assert api.post(tok, "/privat/addons/ring-for-mig/disable").json()["enabled"] is False
    pv.verify_phone(tok)
    r = api.post(tok, f"/privat/calls/{tid}/approve", {"share_phone": False})
    assert r.status_code == 403 and r.json()["code"] == "addon_disabled" and r.json()["addon"] == "ring-for-mig"
    out = pv.say(tok, "Ring til cykelværkstedet")
    last = out["messages"][-1]
    assert last["kind"] == "addon" and last["addon_key"] == "ring-for-mig" and "Ring for mig" in last["text"]
    assert called == []
    # shared lists off: sharing refused, the chat offers the add-on
    api.post(tok, "/privat/addons/delte-lister/disable")
    lid = pv.make_list(tok)
    assert api.post(tok, f"/privat/tasks/{lid}/share", {"mode": "group"}).json()["code"] == "addon_disabled"
    out = pv.say(tok, "Del indkøbslisten med Anna", about=lid)
    assert out["messages"][-1]["kind"] == "addon" and out["messages"][-1]["addon_key"] == "delte-lister"
    assert api.post(tok, "/privat/addons/ring-for-mig/enable").json()["enabled"] is True


@pytest.fixture
def dummy_addon():
    yield
    addons.unregister("test-tilfoejelse")


def test_addon_catalog_extensible(api, pv, dummy_addon):
    tok = pv.account("mette@testmail.dk")
    addons.register(addons.Addon(key="test-tilfoejelse", name="Testtilføjelse", tagline="Kun til test",
                                 description="Bevis for, at ét objekt er nok.", icon="star", category="test",
                                 price_text="Gratis", permissions=("Ingen",)))
    a = next(x for x in api.get(tok, "/privat/addons").json() if x["key"] == "test-tilfoejelse")
    assert a == {"key": "test-tilfoejelse", "name": "Testtilføjelse", "tagline": "Kun til test",
                 "description": "Bevis for, at ét objekt er nok.", "icon": "star", "category": "test",
                 "price_text": "Gratis", "pricing": "free", "monthly_price_minor": None, "status": "available",
                 "permissions": ["Ingen"], "requires": [], "enabled": False, "enabled_at": None}
    assert api.post(tok, "/privat/addons/test-tilfoejelse/enable").json()["enabled"] is True


def test_new_addon_shareable_gets_invites(api, pv, db, dummy_addon):
    addons.register(addons.Addon(key="test-tilfoejelse", name="Madplan", tagline="Ugens madplan sammen",
                                 description="Test.", icon="food", category="test", price_text="Gratis",
                                 shareable=True, resource_type="madplan"))
    mette = pv.account("mette@testmail.dk")
    assert api.post(mette, "/privat/addons/test-tilfoejelse/invites", {}).json()["code"] == "addon_disabled"
    api.post(mette, "/privat/addons/test-tilfoejelse/enable")
    inv = api.post(mette, "/privat/addons/test-tilfoejelse/invites", {}).json()
    p = api.c.get(f"/api/v1/privat/invites/by-code/{inv['short_code']}").json()
    assert (p["title"], p["addon_key"], p["resource_type"]) == ("Madplan", "test-tilfoejelse", "madplan")
    nina = pv.user("nina@testmail.dk", "Nina Ny")
    assert api.post(nina, f"/privat/invites/{inv['token']}/accept").status_code == 200
    assert db.query(PrivateReferral).filter_by(addon_key="test-tilfoejelse").count() == 1


# --------------------------------------------------------------------------- referrals

def _referral_ledger(db, ws):
    db.expire_all()
    return sorted((r.amount, r.source_ref) for r in db.query(CreditLedger).filter_by(workspace_id=ws, kind="referral"))


def test_referral_once(api, pv, db):
    mette = pv.account("mette@testmail.dk")
    t1, t2 = pv.make_list(mette), pv.make_list(mette, "Lav en liste med kage")
    i1, i2 = _share(api, mette, t1), _share(api, mette, t2)
    nina = pv.user("nina@testmail.dk", "Nina Ny")
    _accept(api, nina, i1["token"])
    _accept(api, nina, i2["token"])
    _accept(api, nina, i1["token"])  # replay
    pv.make_list(nina, "Lav en liste med æg")
    pv.make_list(nina, "Lav en liste med mel")
    nid = pv.uid(nina)
    assert _referral_ledger(db, pv.ws(nina)) == [(3, f"referral:{nid}:invitee")]
    assert _referral_ledger(db, pv.ws(mette)) == [(3, f"referral:{nid}:inviter")]
    assert db.query(PrivateReferral).count() == 1
    s = api.get(mette, "/privat/referrals").json()
    assert s == {"invited": 2, "joined": 1, "activated": 1, "credits_earned": 3, "monthly_left": 9}
    from app.models import User

    assert db.get(User, nid).signup_source.startswith("invite:")


def test_referral_needs_activation(api, pv, db):
    mette = pv.account("mette@testmail.dk")
    inv = _share(api, mette, pv.make_list(mette))
    nina = pv.user("nina@testmail.dk", "Nina Ny")
    tid = inv and _accept(api, nina, inv["token"])["id"]
    api.post(nina, f"/privat/tasks/{tid}/items", {"text": "Ost"})  # editing a shared list is not an own task
    assert _referral_ledger(db, pv.ws(nina)) == [] and _referral_ledger(db, pv.ws(mette)) == []
    pv.say(nina, "Mind mig om at ringe til mor i morgen kl 10")
    assert len(_referral_ledger(db, pv.ws(nina))) == 1 and len(_referral_ledger(db, pv.ws(mette))) == 1


def test_referral_monthly_cap(api, pv, db):
    mette = pv.account("mette@testmail.dk")
    link = api.post(mette, "/privat/referrals/link").json()
    for i in range(11):
        tok = pv.user(f"ny{i}@testmail.dk", f"Ny{i} Person")
        _accept(api, tok, link["token"])
        pv.make_list(tok, f"Lav en liste med ting{i}")
        assert len(_referral_ledger(db, pv.ws(tok))) == 1  # every invitee is rewarded
    assert len(_referral_ledger(db, pv.ws(mette))) == 10
    assert api.get(mette, "/privat/referrals").json()["monthly_left"] == 0
    assert db.query(PrivateReferral).filter_by(inviter_rewarded=False).count() == 1


def test_referral_existing_user_no_reward(api, pv, db):
    ole = pv.user("ole@testmail.dk", "Ole Berg")  # exists before the invitation
    mette = pv.account("mette@testmail.dk")
    inv = _share(api, mette, pv.make_list(mette))
    _accept(api, ole, inv["token"])
    pv.make_list(ole, "Lav en liste med øl")
    _accept(api, mette, inv["token"])  # self-invite
    assert db.query(PrivateReferral).count() == 0
    assert _referral_ledger(db, pv.ws(mette)) == [] and _referral_ledger(db, pv.ws(ole)) == []


def test_growth_operator_only(api, pv):
    mette = pv.account("mette@testmail.dk")
    inv = _share(api, mette, pv.make_list(mette))
    api.c.get(f"/api/v1/privat/invites/{inv['token']}")
    nina = pv.user("nina@testmail.dk", "Nina Ny")
    _accept(api, nina, inv["token"])
    pv.make_list(nina, "Lav en liste med te")
    assert api.get(mette, "/operator/privat/growth").status_code == 403
    g = api.get(api.operator(), "/operator/privat/growth").json()
    assert (g["invites_created"], g["opened"], g["accepted"], g["new_users_from_invites"], g["activated"]) == (1, 1, 1, 1, 1)
    assert g["k_factor"] == 0.5 and g["by_addon"]["delte-lister"]["accepted"] == 1


# --------------------------------------------------------------------------- groups

def _group(api, tok, name="Familien", members=None) -> dict:
    r = api.post(tok, "/privat/groups", {"name": name, "members": members or []})
    assert r.status_code == 201, r.text
    return r.json()


def test_group_dedupe_normalise(api, pv):
    tok = pv.account("mette@testmail.dk")
    g = _group(api, tok, members=[{"name": "Anna", "phone": "20 30 40 50"}, {"name": "Anna igen", "phone": "+4520304050"}])
    r = api.post(tok, f"/privat/groups/{g['id']}/members", {"members": [{"name": "Peter", "phone": "0045 21 22 23 24"},
                                                                         {"name": "Fejl", "phone": "12"}],
                                                            "paste": "20304050\n31323334, 4531323334"}).json()
    assert r["result"]["added"] == 2 and r["result"]["duplicates"] == 2 and len(r["result"]["invalid"]) == 1
    assert sorted(m["phone_e164"] for m in r["members"]) == ["+4520304050", "+4521222324", "+4531323334"]
    api.patch = lambda t, p, j: api.c.patch(f"/api/v1{p}", json=j, headers=api.h(t))
    assert api.patch(tok, f"/privat/groups/{g['id']}", {"name": "Familie"}).json()["name"] == "Familie"


def test_group_isolation(api, pv, db):
    mette, eve = pv.account("mette@testmail.dk"), pv.account("eve@testmail.dk", "Eve Ude")
    g = _group(api, mette, members=[{"name": "Anna", "phone": "20304050"}])
    assert api.get(eve, "/privat/groups").json() == []
    for r in (api.post(eve, f"/privat/groups/{g['id']}/members", {"members": [{"name": "x", "phone": "21222324"}]}),
              api.delete(eve, f"/privat/groups/{g['id']}"), api.post(eve, f"/privat/groups/{g['id']}/join-link"),
              api.post(eve, f"/privat/tasks/{pv.make_list(eve)}/share-group",
                       {"group_id": g["id"], "mode": "group", "style": "group_sms"})):
        assert r.status_code == 404, r.text
    # deleted with the group
    assert api.delete(mette, f"/privat/groups/{g['id']}").status_code == 204
    assert db.query(PrivateGroupMember).count() == 0


def _three_users_two_known(api, pv):
    mette = pv.account("mette@testmail.dk", "Mette Hansen")
    ole = pv.account("ole@testmail.dk", "Ole Berg")
    pv.verify_phone(ole, "+4540404040")
    anna = pv.account("anna@testmail.dk", "Anna Holm")
    pv.verify_phone(anna, "+4541414141")
    g = _group(api, mette, members=[{"name": "Ole", "phone": "40404040"}, {"name": "Anna", "phone": "41414141"},
                                    {"name": "Peter", "phone": "20000001"}, {"name": "Mor", "phone": "20000002"},
                                    {"name": "Far", "phone": "20000003"}])
    return mette, ole, anna, g


def test_share_group_mixed(api, pv):
    mette, ole, anna, g = _three_users_two_known(api, pv)
    tid = pv.make_list(mette)
    out = api.post(mette, f"/privat/tasks/{tid}/share-group",
                   {"group_id": g["id"], "mode": "group", "style": "one_by_one"}).json()
    assert sorted(x["name"] for x in out["added_in_app"]) == ["Anna", "Ole"] and out["sms_group"] is None
    q = out["sms_queue"]
    assert [x["name"] for x in q] == ["Peter", "Mor", "Far"] and len({x["short_url"] for x in q}) == 3
    for x in q:
        assert x["body"].startswith(f"Hej {x['name']}!") and len(x["body"]) <= 160
        assert all(ch in invites.GSM7 for ch in x["body"])
    assert pv.task(ole, tid).json()["my_role"] == "editor"
    assert api.get(ole, "/privat/messages").json()[-1]["text"] == "Mette har delt «Indkøbsliste» med dig."
    one = api.post(mette, f"/privat/tasks/{tid}/share-group",
                   {"group_id": g["id"], "mode": "group", "style": "group_sms"}).json()
    assert one["sms_queue"] is None and one["sms_group"]["recipients"] == ["+4520000001", "+4520000002", "+4520000003"]


def test_invite_status_per_person(api, pv):
    mette, ole, anna, g = _three_users_two_known(api, pv)
    tid = pv.make_list(mette)
    q = api.post(mette, f"/privat/tasks/{tid}/share-group",
                 {"group_id": g["id"], "mode": "group", "style": "one_by_one"}).json()["sms_queue"]
    code = {x["name"]: x["short_url"].rsplit("/", 1)[1] for x in q}
    api.c.get(f"/api/v1/privat/invites/by-code/{code['Mor']}")  # Mor opened her link
    peter = pv.user("peter@testmail.dk", "Peter Lund")
    api.post(peter, f"/privat/invites/by-code/{code['Peter']}/accept")
    st = {x["name"]: x["status"] for x in api.get(mette, f"/privat/tasks/{tid}/invite-status").json()}
    assert st == {"Ole Berg": "member", "Anna Holm": "member", "Peter Lund": "member", "Mor": "opened", "Far": "invited"}
    # Peter is recognised next time
    assert next(m for m in api.get(mette, "/privat/groups").json()[0]["members"] if m["name"] == "Peter")["has_dialogbot"]


def test_group_phone_never_exposed_to_members(api, pv):
    mette, ole, anna, g = _three_users_two_known(api, pv)
    tid = pv.make_list(mette)
    api.post(mette, f"/privat/tasks/{tid}/share-group", {"group_id": g["id"], "mode": "group", "style": "one_by_one"})
    for path in (f"/privat/tasks/{tid}", f"/privat/tasks/{tid}/members", "/privat/tasks", "/privat/messages",
                 "/privat/groups", "/privat/people/suggested", "/privat/day"):
        blob = api.get(ole, path).text
        for num in ("2000000", "41414141", "40404040", "Peter", "Mor"):
            assert num not in blob, (path, num)
    assert api.get(ole, f"/privat/tasks/{tid}/invite-status").status_code == 403


def test_group_join_link(api, pv, db):
    mette = pv.account("mette@testmail.dk", "Mette Hansen")
    g = _group(api, mette, members=[{"name": "Anna", "phone": "20304050"}])
    link = api.post(mette, f"/privat/groups/{g['id']}/join-link").json()
    assert link["short_url"].startswith("https://dialogbot.app/g/") and len(link["suggested_text"]) <= 160
    assert link["suggested_text"].startswith("Tryk her for at komme med i Familien på Dialogbot")
    assert all(ch in invites.GSM7 for ch in link["suggested_text"])
    code = link["short_code"]
    p = api.c.get(f"/api/v1/privat/group-invites/by-code/{code}").json()
    assert p == {"group_name": "Familien", "owner_first_name": "Mette", "member_count": 1}  # no names or numbers
    base = f"/api/v1/privat/group-invites/by-code/{code}/join"
    # logged in: linked to the user, twice = one member
    ole = pv.user("ole@testmail.dk", "Ole Berg")
    assert api.c.post(base, json={}, headers=api.h(ole)).json() == {"joined": True, "already": False}
    assert api.c.post(base, json={}, headers=api.h(ole)).json()["already"] is True
    # without login: a number only after the SMS code
    WORLD.reset()
    r = api.c.post(base, json={"name": "Bo", "phone": "22 33 44 55"}).json()
    assert r == {"joined": False, "code_sent": True}
    sms_code = WORLD.sms[-1]["body"].split("er ")[1][:6]
    assert api.c.post(base, json={"name": "Bo", "phone": "22334455", "code": "000000" if sms_code != "000000"
                                  else "111111"}).status_code == 422
    assert api.c.post(base, json={"name": "Bo", "phone": "22334455", "code": sms_code}).json()["joined"] is True
    assert api.c.post(base, json={"name": "Bo", "phone": "+4522334455"}).json()["already"] is True
    assert api.c.post(base, json={"name": "Lise"}).json()["already"] is False
    assert api.c.post(base, json={"name": "lise"}).json()["already"] is True
    members = api.get(mette, "/privat/groups").json()[0]["members"]
    assert sorted(m["name"] for m in members) == ["Anna", "Bo", "Lise", "Ole Berg"]
    assert next(m for m in members if m["name"] == "Bo")["phone_e164"] == "+4522334455"
    assert api.c.get(f"/api/v1/privat/group-invites/by-code/{code}").json()["member_count"] == 4
    # rate limit: 50 new members per link per hour
    for i in range(47):  # different people, different addresses (the per-IP lookup limit is tested separately)
        assert api.c.post(base, json={"name": f"Person {i}"},
                          headers={"x-forwarded-for": f"10.0.1.{i}"}).status_code == 200
    r = api.c.post(base, json={"name": "En for meget"}, headers={"x-forwarded-for": "10.0.2.1"})
    assert r.status_code == 429 and r.json()["code"] == "rate_limited"
    # revoke and expiry
    api.post(mette, f"/privat/groups/{g['id']}/join-link/revoke")
    assert api.c.get(f"/api/v1/privat/group-invites/by-code/{code}").status_code == 404
    link2 = api.post(mette, f"/privat/groups/{g['id']}/join-link").json()
    pv.clock.at += timedelta(days=31)
    assert api.c.post(f"/api/v1/privat/group-invites/by-code/{link2['short_code']}/join",
                      json={"name": "Sen"}).status_code == 404
    assert uuid.UUID(g["id"])


def test_groups_and_sharing_in_chat_need_a_yes(api, pv):
    mette, ole, anna, _g = _three_users_two_known(api, pv)
    out = pv.say(mette, "Lav en gruppe Kolleger med Ole, Lars og Bente")
    clar = out["messages"][-1]
    assert clar["kind"] == "clarify" and clar["text"] == "Skal jeg lave gruppen Kolleger med Ole, Lars og Bente?"
    assert [g["name"] for g in api.get(mette, "/privat/groups").json()] == ["Familien"]  # nothing saved yet
    api.post(mette, f"/privat/messages/{clar['id']}/options/yes")
    assert [g["name"] for g in api.get(mette, "/privat/groups").json()] == ["Familien", "Kolleger"]
    lid = pv.make_list(mette)
    out = pv.say(mette, "Del indkøbslisten med familien", about=lid)
    prop = out["messages"][-1]
    group_id = api.get(mette, "/privat/groups").json()[0]["id"]
    assert prop["kind"] == "share_proposal" and prop["task_id"] == lid and prop["about_task_id"] == lid
    assert (prop["options"][0]["id"], prop["options"][0]["label"]) == (group_id, "Familien")
    assert pv.task(ole, lid).status_code == 404  # not shared before the yes
    r = api.post(mette, f"/privat/messages/{prop['id']}/options/{group_id}").json()
    assert r["messages"][-1]["text"] == "Ole, Anna har fået listen i appen. 3 mangler en SMS fra dig – åbn listen og tryk «Send SMS»."
    assert pv.task(ole, lid).status_code == 200
    # a single share link: a share_proposal card, the link is made only when the user taps it (POST /share)
    out = pv.say(mette, "Del indkøbslisten med Anna", about=lid)
    prop = out["messages"][-1]
    assert prop["kind"] == "share_proposal" and prop["options"] is None and "Anna" in prop["text"]
    assert api.post(mette, f"/privat/messages/{group_id and prop['id']}/options/x").status_code == 404


def test_public_lookups_are_rate_limited(api, pv, db):
    from app.models import PrivateLookup
    from app.modules.privat import lookup_limits

    mette = pv.account("mette@testmail.dk")
    inv = _share(api, mette, pv.make_list(mette))
    g = _group(api, mette)
    link = api.post(mette, f"/privat/groups/{g['id']}/join-link").json()
    good = [f"/api/v1/privat/invites/by-code/{inv['short_code']}", f"/api/v1/privat/invites/{inv['token']}",
            f"/api/v1/privat/group-invites/by-code/{link['short_code']}"]
    bad = ["/api/v1/privat/invites/by-code/AAAAAAAA", "/api/v1/privat/invites/nope",
           "/api/v1/privat/group-invites/by-code/BBBBBBBB"]

    def get(path, ip):
        return api.c.get(path, headers={"x-forwarded-for": ip})

    # misses are counted strictly: 10 a minute, then even a real code is refused from that address
    for i in range(10):
        assert get(bad[i % 3], "10.9.9.9").status_code == 404
    r = get(good[0], "10.9.9.9")
    assert r.status_code == 429 and r.json()["code"] == "rate_limited" and r.json()["message"].startswith("Der er prøvet")
    assert get(good[0], "10.8.8.8").status_code == 200  # another address is not affected
    pv.clock.at += timedelta(seconds=61)
    assert get(good[1], "10.9.9.9").status_code == 200  # the minute has passed
    # … and 50 a day
    for i in range(40):
        if i % 10 == 0:
            pv.clock.at += timedelta(seconds=61)
        assert get(bad[0], "10.9.9.9").status_code == 404
    pv.clock.at += timedelta(seconds=61)
    assert get(good[2], "10.9.9.9").status_code == 429
    # hits: 30 a minute
    for i in range(30):
        assert get(good[i % 3], "10.7.7.7").status_code == 200, i
    assert get(good[0], "10.7.7.7").status_code == 429
    # the IP itself is never stored
    assert "10.7.7.7" not in json.dumps([r.ip_hash for r in db.query(PrivateLookup).all()])
    # a global ceiling on misses stops enumeration spread over many addresses
    lookup_limits.GLOBAL_MISSES_PER_HOUR, old = 55, lookup_limits.GLOBAL_MISSES_PER_HOUR
    try:
        for i in range(5):
            get(bad[0], f"10.6.6.{i}")
        assert get(good[0], "10.5.5.5").status_code == 429
    finally:
        lookup_limits.GLOBAL_MISSES_PER_HOUR = old

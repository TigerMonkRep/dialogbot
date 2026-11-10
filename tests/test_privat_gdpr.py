"""Dialogbot Privat – «Dine data» (PC-ACC-02/03): «Eksportér mine data» and «Slet min konto».

Export: complete, only the caller's own (a wishlist's reservations stay secret to its owner), by worker, link by
e-mail that needs the same login and expires. Delete: retyped e-mail, the Stripe subscription is cancelled first (a
Stripe failure deletes nothing), every Privat row and file goes, others' lists release the person's reservations,
household members lose Familie, the login fails, other users are untouched, the audit row holds no personal data."""
from __future__ import annotations

import io
import json
import zipfile
from datetime import timedelta
from pathlib import Path

from app.config import get_settings
from app.models import (
    AuditLog,
    PrivateDataExport,
    PrivateHouseholdMember,
    PrivateProfile,
    PrivateTask,
    PrivateTaskItem,
    User,
    Workspace,
)
from app.modules.billing import stripe as stripe_api
from app.worker import runner
from tests.privat_fixtures import WED_10

LINK = r"eksport=([A-Za-z0-9_\-]+)"


def _share(api, tok, tid, mode):
    r = api.post(tok, f"/privat/tasks/{tid}/share", {"mode": mode, "role": "editor"})
    assert r.status_code == 200, r.text
    return r.json()


def _accept(api, tok, token):
    r = api.post(tok, f"/privat/invites/{token}/accept")
    assert r.status_code == 200, r.text
    return r.json()


def _wishlist(pv, tok, text):
    out = pv.say(tok, text)
    return next(m["task_id"] for m in out["messages"] if m["kind"] == "task")


def _item_id(api, tok, tid, text):
    return next(i["id"] for i in api.get(tok, f"/privat/tasks/{tid}").json()["items"] if i["text"].lower() == text)


def _world(api, pv):
    """Mette (Familie, a wishlist Ole reserved on, a shopping list), Ole (member of her household, his own wishlist
    Mette reserved on, his own list)."""
    mette = pv.account("mette@testmail.dk", "Mette Hansen", trial=False)
    pv.set_plan(mette, "familie")
    ole = pv.user("ole@testmail.dk", "Ole Berg")
    _accept(api, ole, api.post(mette, "/privat/household/invites").json()["token"])
    m_wish = _wishlist(pv, mette, "Lav en ønskeliste med cykel og bog")
    _accept(api, ole, _share(api, mette, m_wish, "wishlist")["token"])
    cykel = _item_id(api, mette, m_wish, "cykel")
    assert api.post(ole, f"/privat/tasks/{m_wish}/items/{cykel}/reserve").status_code == 200
    m_list = pv.make_list(mette, "Lav en indkøbsliste med mælk og rugbrød")
    o_wish = _wishlist(pv, ole, "Lav en ønskeliste med te og kaffe")
    _accept(api, mette, _share(api, ole, o_wish, "wishlist")["token"])
    te = _item_id(api, ole, o_wish, "te")
    assert api.post(mette, f"/privat/tasks/{o_wish}/items/{te}/reserve").status_code == 200
    o_list = pv.make_list(ole, "Lav en indkøbsliste med smør og ost")
    return {"mette": mette, "ole": ole, "m_wish": m_wish, "m_list": m_list, "o_wish": o_wish, "o_list": o_list,
            "cykel": cykel, "te": te}


def _export(api, tok, email) -> dict:
    r = api.post(tok, "/privat/data-export")
    assert r.status_code == 202 and r.json()["status"] == "queued", r.text
    assert api.post(tok, "/privat/data-export").json()["status"] == "queued"  # idempotent while it is made
    runner.drain()
    assert api.get(tok, "/privat/data-export").json()["status"] == "ready"
    raw = api.mailbox_link(tok, "Dine data", LINK)
    return {"raw": raw}


def _unzip(resp) -> tuple[dict, str]:
    z = zipfile.ZipFile(io.BytesIO(resp.content))
    return json.loads(z.read("data.json")), z.read("oversigt.txt").decode()


def test_export_is_complete_and_only_my_own(api, pv, db):
    w = _world(api, pv)
    mette, ole = w["mette"], w["ole"]
    raw = _export(api, mette, "mette@testmail.dk")["raw"]
    # the link needs Mette's login: Ole with Mette's link gets nothing
    assert api.get(ole, f"/privat/data-export/download?token={raw}").status_code == 404
    r = api.get(mette, f"/privat/data-export/download?token={raw}")
    assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
    data, overview = _unzip(r)
    for key in ("account", "profile", "subscription", "household", "apps", "tasks", "shared_with_me", "messages",
                "calls", "appointments", "birthdays", "bills", "credits", "invitations_sent", "referrals", "groups"):
        assert key in data, key
    assert data["account"]["email"] == "mette@testmail.dk"
    assert data["subscription"]["plan"] == "familie" and data["household"]["role"] == "owner"
    assert data["household"]["members"] == ["Ole"]
    titles = {t["id"] for t in data["tasks"]}
    assert titles == {w["m_wish"], w["m_list"]}  # never Ole's tasks
    blob = json.dumps(data, ensure_ascii=False)
    assert "smør" not in blob.lower() and "kaffe" not in blob.lower()
    # her own wishlist: who reserved stays secret – no reservation fields at all
    wish = next(t for t in data["tasks"] if t["id"] == w["m_wish"])
    assert all("reserved_by_user_id" not in i for i in wish["items"]) and str(pv.uid(ole)) not in blob
    # what she did on Ole's list: only her own reservation
    shared = data["shared_with_me"]
    assert len(shared) == 1 and shared[0]["my_items"] == [
        {"text": next(i["text"] for i in api.get(ole, f"/privat/tasks/{w['o_wish']}").json()["items"] if i["id"] == w["te"]),
         "added_by_me": False, "ticked_by_me": False, "reserved_by_me": True}]
    assert any("mælk" in (m["text"] or "").lower() for m in data["messages"])
    # no secrets
    assert "token_hash" not in blob and "phone_code_hash" not in blob and "vapi_call_id" not in blob
    assert "DIALOGBOT PRIVAT" in overview and "mælk" in overview.lower()
    # Ole's own export: his tasks, his reservation on Mette's list, none of Mette's lists
    raw_o = _export(api, ole, "ole@testmail.dk")["raw"]
    od, _ = _unzip(api.get(ole, f"/privat/data-export/download?token={raw_o}"))
    assert {t["id"] for t in od["tasks"]} == {w["o_wish"], w["o_list"]}
    assert od["household"]["role"] == "member"
    assert [i["reserved_by_me"] for i in od["shared_with_me"][0]["my_items"]] == [True]
    assert "mælk" not in json.dumps(od, ensure_ascii=False).lower()


def test_export_link_expires_and_is_rate_limited(api, pv, db):
    mette = pv.account("mette@testmail.dk", "Mette Hansen")
    raw = _export(api, mette, "mette@testmail.dk")["raw"]
    pv.clock.at = WED_10 + timedelta(days=8)
    r = api.get(mette, f"/privat/data-export/download?token={raw}")
    assert r.status_code == 404 and r.json()["code"] == "export_invalid"
    db.expire_all()
    row = db.query(PrivateDataExport).one()
    assert (row.status, row.data, row.token_hash) == ("expired", None, None)
    pv.clock.at = WED_10 + timedelta(days=9)
    for _ in range(3):
        assert api.post(mette, "/privat/data-export").status_code == 202
        runner.drain()
    r = api.post(mette, "/privat/data-export")
    assert r.status_code == 429 and r.json()["code"] == "rate_limited"


def _stripe(monkeypatch, fail=False):
    sent = []

    def fake(m, p, d=None, **k):
        sent.append((m, p))
        if fail:
            raise stripe_api.StripeFailed("Stripe svarede ikke")
        return {"id": p.rsplit("/", 1)[-1], "status": "canceled"}

    monkeypatch.setattr(stripe_api, "request", fake)
    return sent


def test_delete_account(api, pv, db, monkeypatch):
    w = _world(api, pv)
    mette, ole = w["mette"], w["ole"]
    ws, uid, ws_o = pv.ws(mette), pv.uid(mette), pv.ws(ole)
    photo = Path(get_settings().voice_storage_dir).resolve() / "privat-files" / str(ws) / "garanti" / "abc123.jpg"
    photo.parent.mkdir(parents=True, exist_ok=True)
    photo.write_bytes(b"\xff\xd8\xff test")
    sent = _stripe(monkeypatch)
    r = api.post(mette, "/privat/account/delete", {"confirm_email": "forkert@testmail.dk"})
    assert r.status_code == 422 and sent == []
    r = api.post(mette, "/privat/account/delete", {"confirm_email": " Mette@TestMail.dk "})
    assert r.status_code == 200, r.text
    assert r.json() == {"deleted": True, "login_kept": False}
    assert sent == [("DELETE", f"/subscriptions/sub_test_{ws.hex[:8]}")]
    # nothing can be fetched, and the login fails
    assert api.get(mette, "/privat/me").status_code == 401
    assert api.c.post("/api/v1/auth/login", json={"email": "mette@testmail.dk",
                                                  "password": "CorrectHorse!42"}).status_code == 401
    db.expire_all()
    assert db.get(Workspace, ws) is None and db.get(User, uid) is None
    assert db.query(PrivateTask).filter(PrivateTask.workspace_id == ws).count() == 0
    assert db.query(PrivateProfile).filter_by(user_id=uid).count() == 0
    assert not photo.exists()
    # Ole: his data is untouched, Mette's reservation on his list is released, Familie is gone, her lists are gone
    assert pv.task(ole, w["o_list"]).status_code == 200
    t = api.get(ole, f"/privat/tasks/{w['o_wish']}").json()
    assert t["items"] and db.query(PrivateTaskItem).filter_by(reserved_by_user_id=uid).count() == 0
    assert pv.task(ole, w["m_wish"]).status_code == 404
    assert db.query(PrivateHouseholdMember).count() == 0 and pv.subscription(ole)["entitled"] is False
    assert db.get(Workspace, ws_o) is not None
    # the audit row: no personal data
    a = db.query(AuditLog).filter_by(action="privat.account_deleted").one()
    blob = json.dumps(a.after) + str(a.object_id) + str(a.workspace_id) + str(a.actor_user_id)
    assert "mette" not in blob.lower() and str(uid) not in blob and str(ws) not in blob
    assert a.after["subscription_cancelled"] is True and a.after["household_members_released"] == 1


def test_stripe_failure_deletes_nothing(api, pv, db, monkeypatch):
    mette = pv.account("mette@testmail.dk", "Mette Hansen")
    tid = pv.make_list(mette)
    _stripe(monkeypatch, fail=True)
    r = api.post(mette, "/privat/account/delete", {"confirm_email": "mette@testmail.dk"})
    assert r.status_code == 502 and r.json()["code"] == "subscription_cancel_failed"
    assert pv.task(mette, tid).status_code == 200 and pv.me(mette)["entitled"] is True


def test_login_used_outside_privat_is_kept(api, pv, db, monkeypatch):
    """A login that also owns a business workspace: Privat is deleted, the login and the business stay."""
    mette = pv.account("mette@testmail.dk", "Mette Hansen")
    biz = api.workspace(mette, "Mettes Frisør ApS")
    tid = pv.make_list(mette)
    ws = pv.ws(mette)
    _stripe(monkeypatch)
    r = api.post(mette, "/privat/account/delete", {"confirm_email": "mette@testmail.dk"})
    assert r.status_code == 200 and r.json()["login_kept"] is True
    assert api.get(mette, "/privat/me").status_code == 401  # every session ended
    tok = api.login("mette@testmail.dk")
    assert api.get(tok, "/privat/me").status_code == 404  # no Privat account any more
    assert api.get(tok, f"/workspaces/{biz}").status_code == 200
    db.expire_all()
    assert db.get(Workspace, ws) is None and db.get(PrivateTask, tid) is None

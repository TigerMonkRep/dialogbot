"""QA A05 (e2e-erhverv instans A): invite acceptance – existing/new user, expired/revoked, correct workspace.

Krav A05: "Invite acceptance by an existing or new user; expired/revoked invite and correct workspace."
DB-013 acceptance: "... invite never creates subscription."
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

from app.models import BillingAccount, Invitation, Invoice, Membership, ReceptionAgreement, Workspace


def _counts(db):
    db.expire_all()
    return {m.__name__: db.scalar(select(func.count()).select_from(m))
            for m in (Workspace, BillingAccount, ReceptionAgreement, Invoice)}


def test_existing_user_with_own_workspace_joins_the_right_workspace_and_nothing_is_billed(api, two_workspaces, db):
    t = two_workspaces
    before = _counts(db)
    # owner B (already owner of workspace B) is invited into A as reader
    assert api.invite(t["tok_a"], t["ws_a"], "owner-b@testmail.dk", "reader").status_code == 201
    raw = api.invite_link(t["tok_b"])
    r = api.c.post("/api/v1/invitations/accept", json={"token": raw}, headers=api.h(t["tok_b"]))
    assert r.status_code == 200, r.text
    assert r.json()["id"] == t["ws_a"] and r.json()["role"] == "reader"
    roles = {w["id"]: w["role"] for w in api.get(t["tok_b"], "/workspaces").json()}
    assert roles == {t["ws_a"]: "reader", t["ws_b"]: "owner"}
    # The reader role is enforced in A while B is untouched
    assert api.invite(t["tok_b"], t["ws_a"], "x@testmail.dk").status_code == 403
    assert api.invite(t["tok_b"], t["ws_b"], "y@testmail.dk").status_code == 201
    # DB-013: an invite never creates a workspace, a billing account, an agreement or an invoice
    assert _counts(db) == before


def test_new_user_can_accept_before_verifying_and_lands_only_in_inviting_workspace(api, two_workspaces, db):
    t = two_workspaces
    before = _counts(db)
    assert api.invite(t["tok_a"], t["ws_a"], "ny@testmail.dk", "staff").status_code == 201
    api.register("ny@testmail.dk")
    tok = api.login("ny@testmail.dk")
    raw = api.invite_link(tok)
    r = api.c.post("/api/v1/invitations/accept", json={"token": raw}, headers=api.h(tok))
    assert r.status_code == 200 and r.json()["id"] == t["ws_a"]
    assert [w["id"] for w in api.get(tok, "/workspaces").json()] == [t["ws_a"]]
    assert api.get(tok, f"/workspaces/{t['ws_b']}").status_code == 404
    assert _counts(db) == before


def test_preview_and_accept_states_expired_revoked_used_and_unknown(api, two_workspaces, db):
    t = two_workspaces
    owner, ws = t["tok_a"], t["ws_a"]
    assert api.c.get("/api/v1/invitations/not-a-real-token-123").status_code == 404
    inv = api.invite(owner, ws, "rev@testmail.dk", "staff").json()
    tok = api.user("rev@testmail.dk")
    raw = api.invite_link(tok)
    assert api.post(owner, f"/workspaces/{ws}/invitations/{inv['id']}/revoke").status_code == 200
    assert api.c.get(f"/api/v1/invitations/{raw}").json()["status"] == "revoked"
    # revoke twice -> 409, resend of revoked -> 409
    assert api.post(owner, f"/workspaces/{ws}/invitations/{inv['id']}/revoke").status_code == 409
    assert api.post(owner, f"/workspaces/{ws}/invitations/{inv['id']}/resend").status_code == 409
    r = api.c.post("/api/v1/invitations/accept", json={"token": raw}, headers=api.h(tok))
    assert r.status_code == 409 and r.json()["code"] == "invitation_revoked"
    assert api.get(tok, "/workspaces").json() == []


def test_resend_rotates_token_old_link_dead_new_link_works(api, two_workspaces, db):
    t = two_workspaces
    owner, ws = t["tok_a"], t["ws_a"]
    inv = api.invite(owner, ws, "resend@testmail.dk", "staff").json()
    tok = api.user("resend@testmail.dk")
    first = api.invite_link(tok)
    assert api.post(owner, f"/workspaces/{ws}/invitations/{inv['id']}/resend").status_code == 200
    from app.worker import runner
    runner.drain()
    links = []
    import re
    for m in api.get(tok, "/dev/mailbox").json()["items"]:
        links += re.findall(r"invite/([A-Za-z0-9_\-]+)", m["body_text"])
    new = [x for x in links if x != first]
    assert new, "resend must mail a fresh link"
    assert api.c.get(f"/api/v1/invitations/{first}").status_code == 404
    r = api.c.post("/api/v1/invitations/accept", json={"token": new[0]}, headers=api.h(tok))
    assert r.status_code == 200 and r.json()["id"] == ws


def test_expired_invitation_can_be_reissued_and_old_one_stays_dead(api, two_workspaces, db):
    t = two_workspaces
    owner, ws = t["tok_a"], t["ws_a"]
    inv = api.invite(owner, ws, "late@testmail.dk", "staff").json()
    tok = api.user("late@testmail.dk")
    old = api.invite_link(tok)
    row = db.get(Invitation, inv["id"])
    row.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    db.commit()
    assert api.post(owner, f"/workspaces/{ws}/invitations/{inv['id']}/resend").status_code == 409
    r2 = api.invite(owner, ws, "late@testmail.dk", "staff")
    assert r2.status_code == 201 and r2.json()["id"] != inv["id"]
    r = api.c.post("/api/v1/invitations/accept", json={"token": old}, headers=api.h(tok))
    assert r.status_code == 409 and r.json()["code"] in ("invitation_expired",)


def test_list_invitations_reports_expired_pending_as_expired(api, two_workspaces, db):
    """The team page filters status == 'pending'. An invitation past expires_at is still 'pending' in the list
    response, so the UI offers «Send igen» which the backend then refuses (409)."""
    t = two_workspaces
    owner, ws = t["tok_a"], t["ws_a"]
    inv = api.invite(owner, ws, "stale@testmail.dk", "staff").json()
    row = db.get(Invitation, inv["id"])
    row.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    db.commit()
    listed = {i["id"]: i for i in api.get(owner, f"/workspaces/{ws}/invitations").json()}
    assert listed[inv["id"]]["status"] == "expired", listed[inv["id"]]


def test_removed_member_loses_access_immediately(api, two_workspaces, db):
    t = two_workspaces
    tok = api.add_member(t["tok_a"], t["ws_a"], "gone@testmail.dk", "staff")
    assert api.get(tok, f"/workspaces/{t['ws_a']}").status_code == 200
    m = next(x for x in api.get(t["tok_a"], f"/workspaces/{t['ws_a']}/members").json() if x["email"] == "gone@testmail.dk")
    assert api.delete(t["tok_a"], f"/workspaces/{t['ws_a']}/members/{m['id']}").status_code == 204
    assert api.get(tok, f"/workspaces/{t['ws_a']}").status_code == 404
    assert api.get(tok, f"/workspaces/{t['ws_a']}/members").status_code == 404
    assert api.get(tok, "/workspaces").json() == []
    assert db.scalar(select(func.count()).select_from(Membership).where(Membership.workspace_id == t["ws_a"])) == 1

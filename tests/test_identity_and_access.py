"""Acceptance 1–3: tenant isolation, role limits, invitations."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

from app.models import Invitation, Membership, Workspace


def test_register_login_verify_logout(api, client):
    api.register("anna@testmail.dk", intent="both")
    tok = api.login("anna@testmail.dk")
    me = api.get(tok, "/auth/me").json()
    assert me["email_verified"] is False and me["signup_intent"] == "both"
    # workspace creation requires verification (A03 pending state)
    r = api.post(tok, "/workspaces", {"name": "Anna ApS"})
    assert r.status_code == 403 and r.json()["code"] == "email_not_verified"
    api.verify(tok)
    assert api.get(tok, "/auth/me").json()["email_verified"] is True
    # signup intent is preserved into the workspace (A01 → A06)
    ws = api.workspace(tok, "Anna ApS")
    assert api.get(tok, f"/workspaces/{ws}").json()["product_intent"] == "both"
    # logout revokes the session
    assert api.post(tok, "/auth/logout").status_code == 204
    r = api.get(tok, "/auth/me")
    assert r.status_code == 401 and r.json()["code"] == "session_invalid"


def test_invalid_credentials_and_missing_auth(api, client):
    api.register("bob@testmail.dk")
    r = client.post("/api/v1/auth/login", json={"email": "bob@testmail.dk", "password": "wrongwrongwrong"})
    assert r.status_code == 401 and r.json()["code"] == "invalid_credentials"
    r = client.get("/api/v1/workspaces")
    assert r.status_code == 401
    assert "request_id" in r.json()


def test_password_reset_flow(api, client):
    tok = api.user("carla@testmail.dk")
    assert api.post(tok, "/auth/password/forgot", {"email": "carla@testmail.dk"}).status_code == 202
    raw = api.mailbox_link(tok, "Nulstil", r"reset\?token=([A-Za-z0-9_\-]+)")
    r = client.post("/api/v1/auth/password/reset", json={"token": raw, "password": "NewPassword!2026"})
    assert r.status_code == 200
    # old session revoked, token single-use, new password works
    assert api.get(tok, "/auth/me").status_code == 401
    r = client.post("/api/v1/auth/password/reset", json={"token": raw, "password": "Another!Password9"})
    assert r.status_code == 422 and r.json()["code"] == "token_invalid"
    api.login("carla@testmail.dk", "NewPassword!2026")


def test_tokens_never_in_api_responses(api, two_workspaces, db):
    t = two_workspaces
    r = api.invite(t["tok_a"], t["ws_a"], "new@testmail.dk")
    assert r.status_code == 201
    body = r.text
    inv = db.scalar(select(Invitation))
    assert inv.token_hash not in body and "token" not in r.json()
    lst = api.get(t["tok_a"], f"/workspaces/{t['ws_a']}/invitations").text
    assert inv.token_hash not in lst


# --- Acceptance 1: workspace isolation ------------------------------------------


def test_workspace_a_cannot_touch_workspace_b(api, two_workspaces):
    t = two_workspaces
    a, b = t["tok_a"], t["tok_b"]
    ws_b = t["ws_b"]
    # B creates data
    item = api.knowledge(b, ws_b, "service", "Bordreservation", {"x": 1})
    draft_id = item["open_draft"]["id"]
    api.submit(b, ws_b, draft_id)
    r = api.put(b, f"/workspaces/{ws_b}/profile", {"expected_version": 1, "legal_name": "Havnebord", "description": "d"})
    assert r.status_code == 200

    # A lists nothing from B and sees only its own workspace
    mine = api.get(a, "/workspaces").json()
    assert [w["id"] for w in mine] == [t["ws_a"]]
    # A cannot read B's workspace, profile, plan, members, knowledge
    for path in ("", "/profile", "/setup/plan", "/members", "/knowledge/items", "/assistant/knowledge",
                 f"/knowledge/items/{item['id']}", "/audit", "/goals", "/languages"):
        r = api.get(a, f"/workspaces/{ws_b}{path}")
        assert r.status_code == 404, (path, r.text)
    # A cannot edit or approve B's objects even with B's object ids under B's workspace
    assert api.put(a, f"/workspaces/{ws_b}/knowledge/versions/{draft_id}",
                   {"expected_edit_version": 1, "title": "hacked", "content": {}}).status_code == 404
    assert api.approve(a, ws_b, draft_id).status_code == 404
    # ... and not by presenting B's object id under A's own workspace
    assert api.approve(a, t["ws_a"], draft_id).status_code == 404
    assert api.put(a, f"/workspaces/{t['ws_a']}/knowledge/versions/{draft_id}",
                   {"expected_edit_version": 1, "title": "hacked", "content": {}}).status_code == 404
    assert api.get(a, f"/workspaces/{t['ws_a']}/knowledge/items/{item['id']}").status_code == 404
    # B's data is untouched
    v = api.get(b, f"/workspaces/{ws_b}/knowledge/items/{item['id']}").json()
    assert v["open_draft"]["title"] == "Bordreservation" and v["open_draft"]["status"] == "in_review"
    assert api.get(a, f"/workspaces/{t['ws_a']}/knowledge/items").json()["total"] == 0


# --- Acceptance 2: role limits -----------------------------------------------------


def test_staff_cannot_approve_or_change_roles(api, two_workspaces):
    t = two_workspaces
    owner, ws = t["tok_a"], t["ws_a"]
    staff = api.add_member(owner, ws, "staff@testmail.dk", "staff")
    reader = api.add_member(owner, ws, "reader@testmail.dk", "reader")
    members = api.get(owner, f"/workspaces/{ws}/members").json()
    m_reader = next(m for m in members if m["email"] == "reader@testmail.dk")

    # staff may draft and submit, but not approve
    item = api.knowledge(staff, ws, "service", "Afslibning")
    vid = item["open_draft"]["id"]
    api.submit(staff, ws, vid)
    r = api.approve(staff, ws, vid)
    assert r.status_code == 403 and r.json()["code"] == "insufficient_role"
    assert api.get(owner, f"/workspaces/{ws}/assistant/knowledge").json()["items"] == []
    # staff may not change roles, invite, or read the audit log
    r = api.put(staff, f"/workspaces/{ws}/members/{m_reader['id']}/role", {"role": "admin"})
    assert r.status_code == 403
    assert api.invite(staff, ws, "x@testmail.dk").status_code == 403
    assert api.get(staff, f"/workspaces/{ws}/audit").status_code == 403
    # reader may read but not write
    assert api.get(reader, f"/workspaces/{ws}/knowledge/items").status_code == 200
    r = api.post(reader, f"/workspaces/{ws}/knowledge/items", {"kind": "fact", "title": "x"})
    assert r.status_code == 403
    r = api.put(reader, f"/workspaces/{ws}/profile", {"expected_version": 1, "legal_name": "x", "description": "y"})
    assert r.status_code == 403
    # activation is an explicit separate command, blocked and admin-only
    assert api.post(staff, f"/workspaces/{ws}/setup/activate/reception").status_code == 403
    assert api.post(owner, f"/workspaces/{ws}/setup/activate/reception").status_code == 501


def test_admin_cannot_escalate_to_owner_and_last_owner_protected(api, two_workspaces):
    t = two_workspaces
    owner, ws = t["tok_a"], t["ws_a"]
    admin = api.add_member(owner, ws, "admin@testmail.dk", "admin")
    members = api.get(owner, f"/workspaces/{ws}/members").json()
    m_owner = next(m for m in members if m["role"] == "owner")
    m_admin = next(m for m in members if m["role"] == "admin")
    # admin cannot make anyone owner, nor demote/remove the owner
    assert api.put(admin, f"/workspaces/{ws}/members/{m_admin['id']}/role", {"role": "owner"}).status_code == 403
    assert api.put(admin, f"/workspaces/{ws}/members/{m_owner['id']}/role", {"role": "staff"}).status_code == 403
    assert api.c.delete(f"/api/v1/workspaces/{ws}/members/{m_owner['id']}", headers=api.h(admin)).status_code == 403
    # the last owner cannot demote themself or leave
    r = api.put(owner, f"/workspaces/{ws}/members/{m_owner['id']}/role", {"role": "admin"})
    assert r.status_code == 409 and r.json()["code"] == "last_owner"
    r = api.c.delete(f"/api/v1/workspaces/{ws}/members/{m_owner['id']}", headers=api.h(owner))
    assert r.status_code == 409 and r.json()["code"] == "last_owner"
    # defined handover: promote admin to owner, then the original owner may step down
    assert api.put(owner, f"/workspaces/{ws}/members/{m_admin['id']}/role", {"role": "owner"}).status_code == 200
    assert api.put(owner, f"/workspaces/{ws}/members/{m_owner['id']}/role", {"role": "admin"}).status_code == 200
    audit = api.get(admin, f"/workspaces/{ws}/audit").json()["items"]
    assert [a["action"] for a in audit][:2] == ["membership.role_changed", "membership.role_changed"]


# --- Acceptance 3: invitations ----------------------------------------------------


def test_invitation_single_use_correct_workspace_no_subscription(api, two_workspaces, db):
    t = two_workspaces
    owner, ws_a = t["tok_a"], t["ws_a"]
    ws_before = db.scalar(select(func.count()).select_from(Workspace))
    r = api.invite(owner, ws_a, "invitee@testmail.dk", "staff")
    assert r.status_code == 201
    invitee = api.user("invitee@testmail.dk")
    raw = api.invite_link(invitee)
    # public preview reveals only workspace name/role/status
    prev = api.c.get(f"/api/v1/invitations/{raw}").json()
    assert prev["workspace_name"] == "Fjord Gulvservice ApS" and prev["status"] == "pending"
    # wrong account cannot accept
    r = api.c.post("/api/v1/invitations/accept", json={"token": raw}, headers=api.h(t["tok_b"]))
    assert r.status_code == 403 and r.json()["code"] == "invitation_email_mismatch"
    r = api.c.post("/api/v1/invitations/accept", json={"token": raw}, headers=api.h(invitee))
    assert r.status_code == 200 and r.json()["id"] == ws_a and r.json()["role"] == "staff"
    # second acceptance is rejected; membership count stays 1; no new workspace
    r = api.c.post("/api/v1/invitations/accept", json={"token": raw}, headers=api.h(invitee))
    assert r.status_code == 409 and r.json()["code"] == "invitation_used"
    assert db.scalar(select(func.count()).select_from(Membership).where(Membership.workspace_id == ws_a)) == 2
    assert db.scalar(select(func.count()).select_from(Workspace)) == ws_before
    assert [w["id"] for w in api.get(invitee, "/workspaces").json()] == [ws_a]


def test_expired_and_revoked_invitations_are_rejected(api, two_workspaces, db):
    t = two_workspaces
    owner, ws = t["tok_a"], t["ws_a"]
    # revoked
    inv = api.invite(owner, ws, "rev@testmail.dk").json()
    rev_tok = api.user("rev@testmail.dk")
    raw = api.invite_link(rev_tok)
    assert api.post(owner, f"/workspaces/{ws}/invitations/{inv['id']}/revoke").json()["status"] == "revoked"
    r = api.c.post("/api/v1/invitations/accept", json={"token": raw}, headers=api.h(rev_tok))
    assert r.status_code == 409 and r.json()["code"] == "invitation_revoked"
    # expired
    inv2 = api.invite(owner, ws, "exp@testmail.dk").json()
    exp_tok = api.user("exp@testmail.dk")
    raw2 = api.invite_link(exp_tok)
    row = db.get(Invitation, inv2["id"])
    row.expires_at = datetime.now(UTC) - timedelta(hours=1)
    db.commit()
    assert api.c.get(f"/api/v1/invitations/{raw2}").json()["status"] == "expired"
    r = api.c.post("/api/v1/invitations/accept", json={"token": raw2}, headers=api.h(exp_tok))
    assert r.status_code == 409 and r.json()["code"] == "invitation_expired"
    assert api.get(exp_tok, "/workspaces").json() == []
    assert db.scalar(select(func.count()).select_from(Workspace)) == 2


def test_duplicate_invitation_returns_existing(api, two_workspaces, db):
    t = two_workspaces
    r1 = api.invite(t["tok_a"], t["ws_a"], "dup@testmail.dk")
    r2 = api.invite(t["tok_a"], t["ws_a"], "dup@testmail.dk")
    assert r1.status_code == 201 and r2.status_code == 200 and r1.json()["id"] == r2.json()["id"]
    assert db.scalar(select(func.count()).select_from(Invitation)) == 1

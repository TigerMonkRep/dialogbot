"""QA S02 (e2e-erhverv instans A): members, invites, roles, permissions, resend/revoke, remove.

Krav S02: "Members, invites, roles, permissions, resend/revoke and remove-member confirmation."
DB-013: "Two-workspace isolation tests for list/object/mutation ..."
"""
from __future__ import annotations

from sqlalchemy import func, select

from app.models import Invitation, Membership


def _member(api, tok, ws, email):
    return next(m for m in api.get(tok, f"/workspaces/{ws}/members").json() if m["email"] == email)


def test_two_workspace_isolation_for_members_and_invitations(api, two_workspaces, db):
    t = two_workspaces
    a, b, ws_a, ws_b = t["tok_a"], t["tok_b"], t["ws_a"], t["ws_b"]
    inv_b = api.invite(b, ws_b, "kun-b@testmail.dk", "staff").json()
    owner_b = _member(api, b, ws_b, "owner-b@testmail.dk")
    # list: A cannot list B's members or invitations
    assert api.get(a, f"/workspaces/{ws_b}/members").status_code == 404
    assert api.get(a, f"/workspaces/{ws_b}/invitations").status_code == 404
    # object/mutation through A's own path with B's ids: 404, nothing changes
    assert api.put(a, f"/workspaces/{ws_a}/members/{owner_b['id']}/role", {"role": "reader"}).status_code == 404
    assert api.delete(a, f"/workspaces/{ws_a}/members/{owner_b['id']}").status_code == 404
    assert api.post(a, f"/workspaces/{ws_a}/invitations/{inv_b['id']}/revoke").status_code == 404
    assert api.post(a, f"/workspaces/{ws_a}/invitations/{inv_b['id']}/resend").status_code == 404
    # mutation through B's path: 404 (not a member)
    assert api.put(a, f"/workspaces/{ws_b}/members/{owner_b['id']}/role", {"role": "reader"}).status_code == 404
    assert api.invite(a, ws_b, "evil@testmail.dk").status_code == 404
    db.expire_all()
    assert db.get(Invitation, inv_b["id"]).status == "pending"
    assert _member(api, b, ws_b, "owner-b@testmail.dk")["role"] == "owner"


def test_permission_matrix_staff_reader_admin(api, two_workspaces, db):
    t = two_workspaces
    owner, ws = t["tok_a"], t["ws_a"]
    staff = api.add_member(owner, ws, "staff@testmail.dk", "staff")
    reader = api.add_member(owner, ws, "reader@testmail.dk", "reader")
    admin = api.add_member(owner, ws, "admin@testmail.dk", "admin")
    m_reader = _member(api, owner, ws, "reader@testmail.dk")
    m_owner = _member(api, owner, ws, "owner-a@testmail.dk")
    # staff: may read members, may not invite/change/remove others
    assert api.get(staff, f"/workspaces/{ws}/members").status_code == 200
    assert api.get(staff, f"/workspaces/{ws}/invitations").status_code == 403
    assert api.invite(staff, ws, "nope@testmail.dk", "reader").status_code == 403
    assert api.put(staff, f"/workspaces/{ws}/members/{m_reader['id']}/role", {"role": "staff"}).status_code == 403
    assert api.delete(staff, f"/workspaces/{ws}/members/{m_reader['id']}").status_code == 403
    # reader: may read members only
    assert api.get(reader, f"/workspaces/{ws}/members").status_code == 200
    assert api.invite(reader, ws, "nope2@testmail.dk", "reader").status_code == 403
    # admin: may invite admin/staff/reader, never owner; cannot demote/remove owner
    assert api.invite(admin, ws, "nyadmin@testmail.dk", "admin").status_code == 201
    assert api.invite(admin, ws, "nyejer@testmail.dk", "owner").status_code == 422
    assert api.put(admin, f"/workspaces/{ws}/members/{m_reader['id']}/role", {"role": "owner"}).status_code == 403
    assert api.put(admin, f"/workspaces/{ws}/members/{m_owner['id']}/role", {"role": "reader"}).status_code == 403
    assert api.delete(admin, f"/workspaces/{ws}/members/{m_owner['id']}").status_code == 403
    assert api.delete(admin, f"/workspaces/{ws}/members/{m_reader['id']}").status_code == 204
    # unknown role
    assert api.put(owner, f"/workspaces/{ws}/members/{_member(api, owner, ws, 'staff@testmail.dk')['id']}/role",
                   {"role": "superuser"}).status_code == 422
    # staff may leave on their own; last owner may not
    me = _member(api, owner, ws, "staff@testmail.dk")
    assert api.delete(staff, f"/workspaces/{ws}/members/{me['id']}").status_code == 204
    r = api.delete(owner, f"/workspaces/{ws}/members/{m_owner['id']}")
    assert r.status_code == 409 and r.json()["code"] == "last_owner"


def test_invite_double_submit_and_existing_member(api, two_workspaces, db):
    t = two_workspaces
    owner, ws = t["tok_a"], t["ws_a"]
    r1 = api.invite(owner, ws, "dbl@testmail.dk", "staff", key="k-1")
    r2 = api.invite(owner, ws, "dbl@testmail.dk", "staff", key="k-1")
    r3 = api.invite(owner, ws, "DBL@testmail.dk", "staff", key="k-2")
    assert r1.status_code == 201 and r2.status_code == 201 and r3.status_code == 200
    assert r1.json()["id"] == r2.json()["id"] == r3.json()["id"]
    assert db.scalar(select(func.count()).select_from(Invitation)) == 1
    r = api.invite(owner, ws, "owner-a@testmail.dk", "staff")
    assert r.status_code == 409 and r.json()["code"] == "already_member"


def test_role_change_and_remove_are_audited(api, two_workspaces, db):
    t = two_workspaces
    owner, ws = t["tok_a"], t["ws_a"]
    api.add_member(owner, ws, "aud@testmail.dk", "reader")
    m = _member(api, owner, ws, "aud@testmail.dk")
    assert api.put(owner, f"/workspaces/{ws}/members/{m['id']}/role", {"role": "staff"}).status_code == 200
    assert api.delete(owner, f"/workspaces/{ws}/members/{m['id']}").status_code == 204
    actions = [a["action"] for a in api.get(owner, f"/workspaces/{ws}/audit").json()["items"]]
    assert actions[:2] == ["membership.removed", "membership.role_changed"]
    assert db.scalar(select(func.count()).select_from(Membership).where(Membership.workspace_id == ws)) == 1


def test_resend_is_audited_like_create_and_revoke(api, two_workspaces, db):
    """create_invitation and revoke_invitation write an audit row; resend_invitation (a new token is minted and a
    mail is sent) writes none."""
    t = two_workspaces
    owner, ws = t["tok_a"], t["ws_a"]
    inv = api.invite(owner, ws, "res@testmail.dk", "staff").json()
    assert api.post(owner, f"/workspaces/{ws}/invitations/{inv['id']}/resend").status_code == 200
    actions = [a["action"] for a in api.get(owner, f"/workspaces/{ws}/audit").json()["items"]]
    assert any("resen" in a for a in actions), actions

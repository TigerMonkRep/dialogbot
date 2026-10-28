"""Operator admin: read-only overview/customers/users/operations, and "se som kunde" (read-only impersonation)."""
from __future__ import annotations

from sqlalchemy import select

from app.models import AuditLog, Session, User


def _view_as(api, op, user_id, workspace_id=None):
    r = api.post(op, "/operator/admin/view-as", json={"user_id": user_id, "workspace_id": workspace_id})
    assert r.status_code == 200, r.text
    return r.json()


def _user_id(db, email):
    return str(db.scalar(select(User.id).where(User.email_normalized == email)))


def test_admin_is_for_operators_only(api, two_workspaces):
    tok = two_workspaces["tok_a"] if isinstance(two_workspaces, dict) else two_workspaces[0]
    for path in ("overview", "customers", "users", "operations"):
        assert api.get(tok, f"/operator/admin/{path}").status_code == 403


def test_overview_customers_users_and_operations_work(api, two_workspaces, db):
    op = api.operator()
    ov = api.get(op, "/operator/admin/overview").json()
    assert ov["status"] in ("green", "amber", "red") and ov["schema"]["ok"] is True
    assert ov["tiles"]["workspaces"] >= 2
    cust = api.get(op, "/operator/admin/customers?q=fjord").json()["items"]
    assert [c["name"] for c in cust] == ["Fjord Gulvservice ApS"] and cust[0]["owner_email"] == "owner-a@testmail.dk"
    detail = api.get(op, f"/operator/admin/customers/{cust[0]['id']}").json()
    assert detail["members"][0]["role"] == "owner" and "workspace" in detail["advanced"]
    assert "password_hash" not in str(detail) and "token_hash" not in str(detail)
    us = api.get(op, "/operator/admin/users?q=owner-b").json()["items"]
    assert us[0]["workspaces"][0]["name"] == "Havnebord Café"
    one = api.get(op, f"/operator/admin/users/{us[0]['id']}").json()
    assert one["user"]["password_hash"] == "<skjult>"
    assert api.get(op, "/operator/admin/operations").json()["schema"]["ok"] is True


def test_view_as_shows_exactly_the_customers_view_and_nothing_can_be_changed(api, two_workspaces, db):
    op = api.operator()
    uid = _user_id(db, "owner-a@testmail.dk")
    v = _view_as(api, op, uid)
    as_customer = v["token"]
    me = api.get(as_customer, "/auth/me").json()
    assert me["email"] == "owner-a@testmail.dk"
    wss = api.get(as_customer, "/workspaces").json()
    assert [w["name"] for w in wss] == ["Fjord Gulvservice ApS"]               # the customer's own picture, not Havnebord's
    # no writes: the HTTP method is refused …
    r = api.invite(as_customer, wss[0]["id"], "x@testmail.dk")
    assert r.status_code == 403 and r.json()["code"] == "view_as_read_only"
    # … and the database transaction is read-only even for a GET
    sess = db.scalar(select(Session).where(Session.impersonator_user_id.is_not(None)))
    assert sess is not None and sess.user_agent == "se-som-kunde"
    # an operator's real session is unchanged
    assert api.get(op, "/auth/me").json()["email"] == "operator@testmail.dk"


def test_view_as_cannot_nest_cannot_target_operators_and_needs_membership(api, two_workspaces, db):
    op = api.operator()
    uid_a = _user_id(db, "owner-a@testmail.dk")
    tok = _view_as(api, op, uid_a)["token"]
    assert api.post(tok, "/operator/admin/view-as", json={"user_id": uid_a}).status_code == 403     # not an operator
    assert api.post(op, "/operator/admin/view-as", json={"user_id": _user_id(db, "operator@testmail.dk")}).status_code == 422
    ws_b = api.get(op, "/operator/admin/customers?q=havnebord").json()["items"][0]["id"]
    assert api.post(op, "/operator/admin/view-as", json={"user_id": uid_a, "workspace_id": ws_b}).status_code == 422


def test_view_as_is_audited_start_and_end_and_logout_revokes_it(api, two_workspaces, db):
    op = api.operator()
    tok = _view_as(api, op, _user_id(db, "owner-a@testmail.dk"))["token"]
    assert api.post(tok, "/auth/logout").status_code == 204                                         # allowed: it only ends the view
    assert api.get(tok, "/auth/me").status_code == 401
    actions = [a.action for a in db.scalars(select(AuditLog).order_by(AuditLog.created_at))]
    assert "admin.view_as.start" in actions and "admin.view_as.end" in actions

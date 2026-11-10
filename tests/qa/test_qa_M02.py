"""QA M02 (e2e-erhverv instans A): operator workspace search/detail and scoped support context.

Krav M02 (route /admin/workspaces and /admin/workspaces/:id → implemented as /app/operator/admin/kunder):
"Business search, entitlements, goal-specific setup/channel/booking readiness and scoped support context."
DB-013: "... expired operator grant denied."
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.models import Session, User


def _uid(db, email):
    return str(db.scalar(select(User.id).where(User.email_normalized == email)))


def test_search_by_name_email_and_member_detail_is_operator_only(api, two_workspaces, db):
    t = two_workspaces
    op = api.operator()
    by_name = api.get(op, "/operator/admin/customers?q=havnebord").json()["items"]
    by_mail = api.get(op, "/operator/admin/customers?q=owner-b@").json()["items"]
    assert [c["id"] for c in by_name] == [t["ws_b"]] == [c["id"] for c in by_mail]
    assert by_name[0]["product_intent"] == "campaigns"
    assert api.get(op, "/operator/admin/customers?q=findes-ikke-xyz").json()["items"] == []
    assert api.get(op, f"/operator/admin/customers/{uuid.uuid4()}").status_code == 404
    # customers (even owners) never reach the operator endpoints
    for tok in (t["tok_a"], t["tok_b"]):
        assert api.get(tok, "/operator/admin/customers").status_code == 403
        assert api.get(tok, f"/operator/admin/customers/{t['ws_a']}").status_code == 403


def test_detail_exposes_no_secrets(api, two_workspaces, db):
    op = api.operator()
    d = api.get(op, f"/operator/admin/customers/{two_workspaces['ws_a']}").json()
    s = str(d)
    for bad in ("password_hash", "token_hash", "$argon2"):
        assert bad not in s


def test_view_as_session_is_scoped_to_the_chosen_workspace(api, two_workspaces, db):
    """Operator opens «Se som» for owner B *in workspace A* (B is a reader there). The resulting support session
    should only see workspace A – not the user's other workspace B."""
    t = two_workspaces
    assert api.invite(t["tok_a"], t["ws_a"], "owner-b@testmail.dk", "reader").status_code == 201
    raw = api.invite_link(t["tok_b"])
    assert api.c.post("/api/v1/invitations/accept", json={"token": raw}, headers=api.h(t["tok_b"])).status_code == 200
    op = api.operator()
    v = api.post(op, "/operator/admin/view-as", json={"user_id": _uid(db, "owner-b@testmail.dk"), "workspace_id": t["ws_a"]})
    assert v.status_code == 200, v.text
    tok = v.json()["token"]
    assert api.get(tok, f"/workspaces/{t['ws_a']}").status_code == 200
    seen = [w["id"] for w in api.get(tok, "/workspaces").json()]
    assert seen == [t["ws_a"]], f"view-as scoped to A also lists {seen}"
    assert api.get(tok, f"/workspaces/{t['ws_b']}/members").status_code == 404


def test_view_as_dies_when_operator_grant_is_revoked(api, two_workspaces, db):
    """DB-013: 'expired operator grant denied'. Revoking the operator flag (scripts/grant_operator.py revoke) must
    end the support sessions that operator opened."""
    op = api.operator()
    tok = api.post(op, "/operator/admin/view-as", json={"user_id": _uid(db, "owner-a@testmail.dk")}).json()["token"]
    assert api.get(tok, "/auth/me").status_code == 200
    u = db.scalar(select(User).where(User.email_normalized == "operator@testmail.dk"))
    u.is_platform_operator = False
    db.commit()
    assert api.get(op, "/operator/admin/customers").status_code == 403           # the operator himself: denied
    r = api.get(tok, f"/workspaces/{two_workspaces['ws_a']}/members")
    assert r.status_code == 401, f"view-as session opened by a revoked operator still works: {r.status_code}"


def test_view_as_expires_after_its_window(api, two_workspaces, db):
    op = api.operator()
    v = api.post(op, "/operator/admin/view-as", json={"user_id": _uid(db, "owner-a@testmail.dk")}).json()
    exp = datetime.fromisoformat(v["expires_at"])
    assert timedelta(minutes=55) < exp - datetime.now(UTC) <= timedelta(minutes=60)
    sess = db.scalar(select(Session).where(Session.impersonator_user_id.is_not(None)))
    sess.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db.commit()
    r = api.get(v["token"], "/auth/me")
    assert r.status_code == 401 and r.json()["code"] == "session_invalid"


def test_entitlements_and_readiness_in_detail(api, two_workspaces, db):
    """M02 asks for entitlements and goal-specific setup/channel/booking readiness on the workspace detail."""
    op = api.operator()
    d = api.get(op, f"/operator/admin/customers/{two_workspaces['ws_a']}").json()
    missing = [k for k in ("entitlements", "readiness") if k not in d]
    assert not missing, f"not implemented: {missing}; keys = {sorted(d)}"

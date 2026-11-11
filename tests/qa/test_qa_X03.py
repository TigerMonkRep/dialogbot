"""QA X03 (e2e-erhverv A, bølge 2): /start – the Erhverv quiz-funnel, backend half.

Requirement (qa/scenarios.csv X03): spørgsmål → profil opbygges i baggrunden → reveal bag navn/e-mail; lead gemmes én
gang; tilbage/genindlæs midt i.

The browser half is web/e2e/qa/erhverv-p1a/X03.spec.ts. This file proves what the browser cannot see:
- the lead (user + workspace) is created exactly once, also when verify is sent twice;
- the gate for an e-mail that already has an account (F-E2A-01): today an SMS code to ANY phone number the visitor
  types logs them in as the existing account owner – the owner's workspace and its data become readable.
"""
from __future__ import annotations

from sqlalchemy import select

from app.models import FunnelDraft, Membership, User, Workspace
from tests.test_funnel import _code, _gate, _patch, funnel  # noqa: F401  (fixture re-export)


def _erhverv_to_gate(client) -> str:
    did = client.post("/api/v1/funnel/drafts", json={"kind": "erhverv", "industry": "haandvaerker"}).json()["id"]
    _patch(client, did, 2, {"company_name": "Nørgaard Tømrer", "place_id": None})
    _patch(client, did, 3, {"missed": ["lunch"]})
    _patch(client, did, 4, {"wants": ["book"]})
    _patch(client, did, 5, {})
    return did


def test_lead_is_saved_once_even_with_double_verify(client, funnel, db):  # noqa: F811
    did = _erhverv_to_gate(client)
    assert _gate(client, did, email="x03-lead@testmail.dk", phone="20 30 40 51").status_code == 202
    code = _code()
    first = client.post(f"/api/v1/funnel/drafts/{did}/verify", json={"code": code})
    second = client.post(f"/api/v1/funnel/drafts/{did}/verify", json={"code": code})
    assert first.status_code == 200, first.text
    assert second.status_code == 409 and second.json()["code"] == "draft_verified"
    db.expire_all()
    assert db.query(User).filter_by(email_normalized="x03-lead@testmail.dk").count() == 1
    user = db.query(User).filter_by(email_normalized="x03-lead@testmail.dk").one()
    assert db.query(Membership).filter_by(user_id=user.id).count() == 1
    # a second gate on the verified draft is refused (no second SMS, no second lead)
    sent = len(funnel_sms())
    assert _gate(client, did, email="x03-lead@testmail.dk", phone="20 30 40 51").status_code == 409
    assert len(funnel_sms()) == sent


def funnel_sms():
    from app.modules.integrations.connectors.fakes import WORLD
    return list(WORLD.sms)


def test_existing_owner_email_with_strangers_phone_must_not_open_the_owners_account(client, api, funnel, db):  # noqa: F811
    """F-E2A-01. The owner of «Fjord Gulvservice ApS» (owner-a@testmail.dk, from the fixture) has never given the
    number 20 99 88 77. A stranger who only knows the owner's e-mail goes through /start, types the owner's e-mail and
    their OWN mobile, receives the code and enters it."""
    victim_ws = funnel["ws"]
    owner = db.scalar(select(User).where(User.email_normalized == "owner-a@testmail.dk"))
    assert owner is not None and owner.phone_verified_at is None
    did = _erhverv_to_gate(client)
    r = _gate(client, did, name="Fremmed", email="owner-a@testmail.dk", phone="20 99 88 77")
    assert r.status_code == 202, r.text
    out = client.post(f"/api/v1/funnel/drafts/{did}/verify", json={"code": _code()})
    # Expected: a known e-mail is not proven by a code to an unrelated number – no session on the existing account
    # (e.g. send a login link to the e-mail instead, or require the number already verified on that account).
    token = out.json().get("session_token") if out.status_code == 200 else None
    leaked = []
    if token:
        ws_ids = {w["id"] for w in api.get(token, "/workspaces").json()}
        if victim_ws in ws_ids:
            leaked.append("victim workspace listed")
        if api.get(token, f"/workspaces/{victim_ws}").status_code == 200:
            leaked.append("victim workspace readable")
        if api.get(token, "/auth/me").json().get("email", "").lower() == "owner-a@testmail.dk":
            leaked.append("session is the owner's account")
    db.expire_all()
    extra_ws = db.scalars(select(Workspace).join(Membership, Membership.workspace_id == Workspace.id)
                          .where(Membership.user_id == owner.id)).all()
    assert not leaked, f"stranger with only the owner's e-mail got: {leaked}; owner now has {len(extra_ws)} workspaces"


def test_back_and_reload_mid_flow_keeps_answers(client, funnel, db):  # noqa: F811
    did = _erhverv_to_gate(client)
    # «back» to step 2 and change the name: the draft keeps the later answers and the new name
    d = _patch(client, did, 2, {"company_name": "Nørgaard Tømrer ApS", "place_id": None})
    again = client.get(f"/api/v1/funnel/drafts/{did}").json()  # reload
    assert again["answers"]["company_name"] == "Nørgaard Tømrer ApS"
    assert again["answers"]["missed"] == ["lunch"] and again["answers"]["wants"] == ["book"]
    assert d["answers"]["wants"] == ["book"]  # going back does not wipe later answers
    assert db.get(FunnelDraft, __import__("uuid").UUID(did)).user_id is None  # nothing created before the code

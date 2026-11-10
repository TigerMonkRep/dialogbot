"""QA H01 + M06 / DB-016 (e2e-erhverv instans A).

Krav H01 (/app/help and /app/support/:ticket): "Contextual help, support request with attachments, status and thread."
Krav M06 (/admin/support): "Support queue, ticket detail, assignment and client-visible replies."
DB-016: "Customer serializers and attachments exclude internal notes; expired/wrong-purpose token denied; OTP retry
limits enforced."
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.models import AssistantRequest, AuthToken, User


def test_wrong_purpose_tokens_are_denied(api, client, db):
    tok = api.user("h01-tok@testmail.dk")
    assert api.post(tok, "/auth/password/forgot", {"email": "h01-tok@testmail.dk"}).status_code == 202
    reset_raw = api.mailbox_link(tok, "Nulstil", r"reset\?token=([A-Za-z0-9_\-]+)")
    # a password-reset token is not an e-mail verification token …
    r = client.post("/api/v1/auth/verify-email", json={"token": reset_raw})
    assert r.status_code == 422 and r.json()["code"] == "token_invalid"
    # … and still works for its own purpose afterwards (the wrong-purpose attempt did not consume it)
    r = client.post("/api/v1/auth/password/reset", json={"token": reset_raw, "password": "NewPassword!2026"})
    assert r.status_code == 200
    # an invitation token is not a reset token
    api.register("h01-ver@testmail.dk")
    t2 = api.login("h01-ver@testmail.dk")
    ver_raw = api.mailbox_link(t2, "Bekræft", r"verify-email\?token=([A-Za-z0-9_\-]+)")
    r = client.post("/api/v1/auth/password/reset", json={"token": ver_raw, "password": "NewPassword!2026"})
    assert r.status_code == 422 and r.json()["code"] == "token_invalid"


def test_expired_verification_token_is_denied(api, client, db):
    api.register("h01-exp@testmail.dk")
    t = api.login("h01-exp@testmail.dk")
    raw = api.mailbox_link(t, "Bekræft", r"verify-email\?token=([A-Za-z0-9_\-]+)")
    uid = db.scalar(select(User.id).where(User.email_normalized == "h01-exp@testmail.dk"))
    for row in db.scalars(select(AuthToken).where(AuthToken.user_id == uid)):
        row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db.commit()
    r = client.post("/api/v1/auth/verify-email", json={"token": raw})
    assert r.status_code == 422 and r.json()["code"] == "token_expired"
    assert api.get(t, "/auth/me").json()["email_verified"] is False


def test_operator_internal_note_is_not_visible_to_the_customer(api, two_workspaces, db):
    """An operator's internal note on a customer's wish (/app/operator/oensker) must stay internal. The change is
    audited on the customer's workspace with before/after, and GET /workspaces/{id}/audit (owner/admin, shown in
    «Aktivitetslog») returns before/after verbatim."""
    t = two_workspaces
    uid = db.scalar(select(User.id).where(User.email_normalized == "owner-a@testmail.dk"))
    wish = AssistantRequest(workspace_id=t["ws_a"], user_id=uid, text="Kan I sende SMS til mine kunder?",
                            summary="SMS til kunder", category="campaigns", status="new", admin_note="", times_asked=1)
    db.add(wish)
    db.commit()
    op = api.operator()
    secret = "INTERN: kunden er dårlig betaler, prioritér lavt"
    r = api.patch(op, f"/operator/assistant/requests/{wish.id}", {"status": "declined", "admin_note": secret})
    assert r.status_code == 200, r.text
    audit = api.get(t["tok_a"], f"/workspaces/{t['ws_a']}/audit")
    assert audit.status_code == 200
    assert secret not in audit.text, "operator's internal note is returned to the customer by the audit log"


@pytest.mark.xfail(strict=True, reason="H01/M06 support-ticket API: not-implemented")
def test_support_ticket_api_exists(api, two_workspaces):
    """H01/M06: support requests (with attachments, status, thread) and an operator queue."""
    t = two_workspaces
    codes = [api.get(t["tok_a"], f"/workspaces/{t['ws_a']}/support/tickets").status_code,
             api.get(api.operator(), "/operator/support/tickets").status_code]
    assert all(c == 200 for c in codes), f"not implemented: {codes}"

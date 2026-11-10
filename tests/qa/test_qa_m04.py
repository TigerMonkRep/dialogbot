"""QA M04 (e2e-erhverv B): /admin/billing – price catalogue, orders, disputes, reconciliation and authorised refund
review (DB-002, DB-004, DB-006, DB-012).

Finding: none of these operator functions exist (no price catalogue, order, dispute, credit-note or refund routes).
This test documents the absence and checks that what exists (operator customer view) is operator-only and keeps
reception and campaign data apart.
"""
from __future__ import annotations

import pytest

M04_PATHS = ("/operator/admin/billing", "/operator/admin/prices", "/operator/admin/orders", "/operator/admin/disputes",
             "/operator/admin/refunds")


@pytest.mark.xfail(strict=True, reason="M04 operator billing admin (prices, orders, disputes, refunds): needs-decision")
def test_m04_billing_admin_exists(api):
    """M04 requirement: price catalogue, orders, disputes, reconciliation and refund review for operators. Not built
    (xfail strict – turns red when built)."""
    op = api.operator()
    missing = [p for p in M04_PATHS if api.get(op, p).status_code in (404, 405)]
    assert not missing, f"not built: {missing}"


def test_m04_operator_customer_view_is_operator_only(api, two_workspaces):
    t = two_workspaces
    op = api.operator()
    # what exists is operator-only (role: owner of a workspace is not enough)
    assert api.get(t["tok_a"], f"/operator/admin/customers/{t['ws_a']}").status_code in (401, 403)
    assert api.get(t["tok_a"], "/operator/admin/customers").status_code in (401, 403)
    detail = api.get(op, f"/operator/admin/customers/{t['ws_a']}")
    assert detail.status_code == 200
    body = detail.json()
    # DB-004: reception calls and campaigns are separate lists; no dispute/credit wording without a dispute module
    assert set(body) >= {"calls", "campaigns", "invoices"}
    text = str(body).lower()
    for word in ("kreditnota", "credit note", "krediteret", "tvist", "dispute"):
        assert word not in text

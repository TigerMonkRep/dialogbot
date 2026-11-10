"""QA M04 (e2e-erhverv B): /admin/billing – price catalogue, orders, disputes, reconciliation and authorised refund
review (DB-002, DB-004, DB-006, DB-012).

Finding: none of these operator functions exist (no price catalogue, order, dispute, credit-note or refund routes).
This test documents the absence and checks that what exists (operator customer view) is operator-only and keeps
reception and campaign data apart.
"""
from __future__ import annotations


def test_m04_billing_admin_not_built_and_operator_only(api, two_workspaces):
    t = two_workspaces
    op = api.operator()
    for path in ("/operator/admin/billing", "/operator/admin/prices", "/operator/admin/orders", "/operator/admin/disputes",
                 "/operator/admin/refunds", "/admin/billing"):
        assert api.get(op, path).status_code in (404, 405), path
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

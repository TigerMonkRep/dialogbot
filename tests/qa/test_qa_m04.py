"""QA M04 (e2e-erhverv B): /admin/billing – price catalogue, orders, disputes, reconciliation and authorised refund
review (DB-002, DB-004, DB-006, DB-012).

Finding: none of these operator functions exist (no price catalogue, order, dispute, credit-note or refund routes).
This test documents the absence and checks that what exists (operator customer view) is operator-only and keeps
reception and campaign data apart.
"""
from __future__ import annotations

import pytest

M04_PATHS = ("/operator/admin/billing", "/operator/admin/prices", "/operator/admin/disputes")
# Orders and refunds belonged to campaign packages; with the minute package (2026-11-10) a refund is a complaint
# about a call that is credited (disputes) – there are no orders.
M04_NOT_IN_MODEL = ("/operator/admin/orders", "/operator/admin/refunds")


def test_m04_billing_admin_exists(api):
    """M04 with the minute package: per-customer billing overview, the price list and the complaint queue."""
    op = api.operator()
    missing = [p for p in M04_PATHS if api.get(op, p).status_code in (404, 405)]
    assert not missing, f"not built: {missing}"


@pytest.mark.xfail(strict=True, reason="M04 orders/refunds: not part of the minute-package model (refund = approved complaint)")
def test_m04_orders_and_refunds_exist(api):
    op = api.operator()
    assert not [p for p in M04_NOT_IN_MODEL if api.get(op, p).status_code in (404, 405)]


def test_m04_operator_customer_view_is_operator_only(api, two_workspaces):
    t = two_workspaces
    op = api.operator()
    # what exists is operator-only (role: owner of a workspace is not enough)
    assert api.get(t["tok_a"], f"/operator/admin/customers/{t['ws_a']}").status_code in (401, 403)
    assert api.get(t["tok_a"], "/operator/admin/customers").status_code in (401, 403)
    detail = api.get(op, f"/operator/admin/customers/{t['ws_a']}")
    assert detail.status_code == 200
    body = detail.json()
    # DB-004: reception calls and campaigns are separate lists; M04: the package snapshot and the month's usage
    assert set(body) >= {"calls", "campaigns", "invoices", "agreement", "usage"}
    text = str(body).lower()
    for word in ("kreditnota", "credit note", "krediteret"):  # nothing credited without an approved complaint
        assert word not in text

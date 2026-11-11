"""QA billing-qa · B04 – dispute detail (/app/billing/disputes/:id): reason/evidence, pending review, decision and any
invoice adjustment. DB-002 (P0): an unbilled dispute never creates a credit note; the already-invoiced branch is a
SEPARATE path. Only the pure unbilled rule exists; this file pins it and records what is missing."""
from __future__ import annotations

import pytest

from app.modules.billing.money import LeadBillingState, decide_unbilled_dispute

START = LeadBillingState(approved_count=14, approved_subtotal_net_minor=208_600, suspended_total_net_minor=29_800)


def test_b04_db002_neither_ruling_creates_a_credit_note_or_changes_money_twice():
    for ruling in ("uphold", "reject"):
        out = decide_unbilled_dispute(START, disputed_net_minor=14_900, ruling=ruling)
        assert out.credit_note_created is False
        # suspended 29.800 → 14.900 either way; nothing disappears: approved + suspended + excluded is conserved
        assert out.suspended_total_net_minor == 14_900
        assert (out.approved_subtotal_net_minor + out.suspended_total_net_minor + out.excluded_net_minor
                == START.approved_subtotal_net_minor + START.suspended_total_net_minor)
    with pytest.raises(ValueError):
        decide_unbilled_dispute(START, disputed_net_minor=14_900, ruling="credit")  # type: ignore[arg-type]


def test_b04_complaint_records_endpoint_and_the_separate_invoiced_branch_exist(app):
    """B04 with the minute package (Fürster 2026-11-10): complaints about a call are records (CallDispute), there is
    an endpoint, and an already-invoiced month takes a SEPARATE path (credit on the next invoice) – the unbilled path
    puts the minutes back in the package without a credit note. Behaviour: tests/test_billing_disputes.py."""
    from qa_sec_helpers import all_routes

    import app.models as models
    from app.modules.billing import disputes

    assert hasattr(disputes, "credit_for_invoiced_period") and hasattr(disputes, "decide")
    assert [n for n in dir(models) if "dispute" in n.lower()], "no dispute model"
    assert [p for _m, p, _r in all_routes(app) if "dispute" in p], "no dispute endpoint"

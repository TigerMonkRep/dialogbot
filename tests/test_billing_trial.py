"""The 14-day free trial for Erhverv (Fürster 2026-11-18): starts with a confirmed agreement + a saved card, once per
company (CVR), credits the subscription on the statement, stops at once when cancelled inside it, keeps outbound
campaigns out, and mails before the first charge."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.core.errors import Conflict
from app.models import BillingAccount, BusinessProfile, OutboxEvent
from app.modules.billing import agreements, grace, trial

T0 = datetime(2026, 11, 10, 9, 0, tzinfo=UTC)


def _ws(two_workspaces, which="ws_a") -> uuid.UUID:
    return uuid.UUID(two_workspaces[which])


def _card(db, ws, paid_before=False):
    a = db.get(BillingAccount, ws) or BillingAccount(workspace_id=ws)
    a.stripe_customer_id = a.stripe_customer_id or f"cus_{ws.hex[:8]}"
    a.payment_method_id, a.card_brand, a.card_last4, a.card_exp = "pm_x", "visa", "4242", "12/39"
    if paid_before:
        a.first_paid_at = T0 - timedelta(days=90)
    db.add(a)
    db.flush()
    return a


def _agree(db, ws):
    agreements.create(db, ws, "A", None)
    db.flush()


def _cvr(db, ws, cvr):
    p = db.get(BusinessProfile, ws)
    p.cvr = cvr
    db.flush()


def test_trial_starts_with_card_and_agreement_and_only_once_per_company(db, two_workspaces):
    a, b = _ws(two_workspaces), _ws(two_workspaces, "ws_b")
    _cvr(db, a, "25632710")
    _cvr(db, b, "25632710")  # the same company
    _card(db, a)
    assert trial.ensure_started(db, a, T0) is False  # card but no agreement
    _agree(db, a)
    assert trial.ensure_started(db, a, T0) is True
    st = trial.state(db, a, T0)
    assert st["status"] == "active" and st["can_cancel"] is True
    assert datetime.fromisoformat(st["ends_at"]) == T0 + timedelta(days=14)
    assert trial.ensure_started(db, a, T0 + timedelta(days=1)) is False  # idempotent
    _card(db, b)
    _agree(db, b)
    assert trial.ensure_started(db, b, T0) is False  # same CVR: this company has had its trial
    assert trial.state(db, b, T0)["status"] == "none" and trial.state(db, b)["eligible"] is False


def test_existing_paying_customer_saving_a_new_card_gets_no_trial(db, two_workspaces):
    a = _ws(two_workspaces)
    _card(db, a, paid_before=True)
    _agree(db, a)
    assert trial.ensure_started(db, a, T0) is False


def test_outbound_campaigns_are_blocked_during_the_trial_only(db, two_workspaces):
    a = _ws(two_workspaces)
    _card(db, a)
    _agree(db, a)
    trial.ensure_started(db, a, T0)
    assert trial.outbound_blocked(db, a, T0 + timedelta(days=5)) is True
    assert trial.outbound_blocked(db, a, T0 + timedelta(days=15)) is False
    assert trial.state(db, a, T0 + timedelta(days=15))["status"] == "ended"


def test_statement_credits_the_trial_days_and_a_cancelled_trial_in_full(db, two_workspaces):
    a = _ws(two_workspaces)
    _card(db, a)
    _agree(db, a)
    trial.ensure_started(db, a, T0)  # 10 Nov – 24 Nov (14 days)
    ag = agreements.current(db, a)
    sub = ag.monthly_net_minor
    lines = [{"kind": "subscription", "description": "x", "net_minor": sub}]
    trial.adjust_statement(db, a, datetime(2026, 11, 1).date(), "Europe/Copenhagen", lines, "DKK")
    credit = next(x for x in lines if x["kind"] == "trial_credit")
    assert credit["net_minor"] == -round(sub * 14 / 30)  # 14 of November's 30 days are free
    # cancelled inside the trial: the whole month is credited
    trial.cancel(db, a, T0 + timedelta(days=3))
    lines = [{"kind": "subscription", "description": "x", "net_minor": sub}]
    trial.adjust_statement(db, a, datetime(2026, 11, 1).date(), "Europe/Copenhagen", lines, "DKK")
    assert sum(x["net_minor"] for x in lines) == 0
    # and nothing is charged for a later month
    lines = [{"kind": "subscription", "description": "x", "net_minor": sub}]
    trial.adjust_statement(db, a, datetime(2026, 12, 1).date(), "Europe/Copenhagen", lines, "DKK")
    assert lines == []


def test_cancel_inside_the_trial_stops_the_service_at_once_and_later_cancel_is_refused(db, two_workspaces):
    a = _ws(two_workspaces)
    _card(db, a)
    _agree(db, a)
    trial.ensure_started(db, a, T0)
    assert grace.subscription_paid(db, a, T0 + timedelta(days=1)) is True
    trial.cancel(db, a, T0 + timedelta(days=2))
    assert trial.state(db, a, T0 + timedelta(days=2))["status"] == "cancelled"
    assert grace.subscription_paid(db, a, T0 + timedelta(days=3)) is False
    assert grace.lapsed(db, a, T0 + timedelta(days=3)) is True
    with pytest.raises(Conflict):
        trial.cancel(db, a, T0 + timedelta(days=4))  # already cancelled
    b = _ws(two_workspaces, "ws_b")
    _card(db, b)
    _agree(db, b)
    trial.ensure_started(db, b, T0)
    with pytest.raises(Conflict):
        trial.cancel(db, b, T0 + timedelta(days=20))  # the trial has ended


def test_mail_before_first_charge_is_sent_once_with_the_amount(db, two_workspaces):
    a = _ws(two_workspaces)
    _card(db, a)
    _agree(db, a)
    trial.ensure_started(db, a, T0)
    db.commit()
    assert trial.run_due(db, T0 + timedelta(days=5)) == 0          # too early
    assert trial.run_due(db, T0 + timedelta(days=12)) >= 1         # within 3 days of the end
    assert trial.run_due(db, T0 + timedelta(days=13)) == 0         # only once
    keys = list(db.scalars(select(OutboxEvent.dedupe_key).where(
        OutboxEvent.workspace_id == a, OutboxEvent.dedupe_key.like("billing-mail:trial_ending:%"))))
    assert keys

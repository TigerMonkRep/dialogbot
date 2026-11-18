"""The 14-day free trial for Erhverv (Fürster 2026-11-18).

Rules:
- It starts when the workspace has a confirmed agreement AND a saved card (`ensure_started`, called when either happens).
  The card is required, nothing is charged during the trial; the first charge is the first monthly statement that follows.
- Once per company: the key is the CVR number (or the workspace for a workspace without one) – `TrialClaim`.
- The trial covers inbound phone and webchat only. Outbound campaigns are blocked until it has ended (`outbound_blocked`),
  because they need documented consent and must not run on a free trial.
- The owner can cancel in the app while the trial runs (`cancel`): service stops at once and nothing is charged.
  After the trial the normal rule holds (cancel to the end of the month).
- The subscription line is credited for the days of the trial (`adjust_statement`); a cancelled trial is credited in full.
- A mail goes out `MAIL_BEFORE` before the trial ends with the amount and the date of the first charge (`run_due`).
"""
from __future__ import annotations

import calendar
import uuid
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from app.core.errors import Conflict
from app.models import BillingAccount, BusinessProfile, Membership, TrialClaim, User

TRIAL_DAYS = 14
MAIL_BEFORE = timedelta(days=3)


def _now() -> datetime:
    return datetime.now(UTC)


def claim_key(db: OrmSession, ws_id: uuid.UUID) -> str:
    p = db.get(BusinessProfile, ws_id)
    cvr = "".join(ch for ch in (p.cvr if p and p.cvr else "") if ch.isdigit())
    return f"cvr:{cvr}" if len(cvr) == 8 else f"ws:{ws_id}"


def ensure_started(db: OrmSession, ws_id: uuid.UUID, now: datetime | None = None) -> bool:
    """Start the trial if the workspace has a confirmed agreement and a saved card and has not had one. Idempotent."""
    from app.modules.billing.agreements import current

    now = now or _now()
    acc = db.get(BillingAccount, ws_id)
    if acc is None or acc.trial_started_at is not None or not acc.payment_method_id or acc.first_paid_at is not None:
        return False  # no card yet, already had a trial, or an existing paying customer saving a new card
    a = current(db, ws_id)
    if a is None or a.model == "B" or a.sales_offer_id is not None:  # an accepted offer has its own terms
        return False
    key = claim_key(db, ws_id)
    if db.get(TrialClaim, key) is not None:
        return False  # this company has had its trial
    db.add(TrialClaim(key=key, workspace_id=ws_id, claimed_at=now))
    acc.trial_started_at, acc.trial_ends_at = now, now + timedelta(days=TRIAL_DAYS)
    db.flush()
    return True


def state(db: OrmSession, ws_id: uuid.UUID, now: datetime | None = None) -> dict:
    now = now or _now()
    acc = db.get(BillingAccount, ws_id)
    if acc is None or acc.trial_started_at is None:
        return {"status": "none", "days": TRIAL_DAYS, "eligible": db.get(TrialClaim, claim_key(db, ws_id)) is None}
    if acc.trial_cancelled_at is not None:
        status = "cancelled"
    elif now < acc.trial_ends_at:
        status = "active"
    else:
        status = "ended"
    return {"status": status, "days": TRIAL_DAYS, "started_at": acc.trial_started_at.isoformat(),
            "ends_at": acc.trial_ends_at.isoformat(), "cancelled_at": acc.trial_cancelled_at.isoformat()
            if acc.trial_cancelled_at else None, "can_cancel": status == "active"}


def active(db: OrmSession, ws_id: uuid.UUID, now: datetime | None = None) -> bool:
    return state(db, ws_id, now)["status"] == "active"


def cancelled(db: OrmSession, ws_id: uuid.UUID) -> bool:
    acc = db.get(BillingAccount, ws_id)
    return acc is not None and acc.trial_cancelled_at is not None


def outbound_blocked(db: OrmSession, ws_id: uuid.UUID, now: datetime | None = None) -> bool:
    """Campaign calls (outbound) are not part of the free trial."""
    return active(db, ws_id, now)


def cancel(db: OrmSession, ws_id: uuid.UUID, now: datetime | None = None) -> dict:
    """The owner cancels during the trial: service stops at once, nothing is charged."""
    now = now or _now()
    st = state(db, ws_id, now)
    if st["status"] != "active":
        raise Conflict("Prøveperioden kan kun opsiges, mens den kører.", code="trial_not_active")
    acc = db.get(BillingAccount, ws_id)
    acc.trial_cancelled_at = now
    db.flush()
    return state(db, ws_id, now)


def adjust_statement(db: OrmSession, ws_id: uuid.UUID, month: date, tz: str, lines: list[dict], currency: str) -> None:
    """Credit the subscription for the trial days that fall in `month`; a cancelled trial is credited in full, and no
    subscription is charged for months after the cancellation. Mutates `lines`."""
    acc = db.get(BillingAccount, ws_id)
    if acc is None or acc.trial_started_at is None:
        return
    z = ZoneInfo(tz)
    first = month.replace(day=1)
    dim = calendar.monthrange(first.year, first.month)[1]
    last = first.replace(day=dim)
    sub = next((x for x in lines if x["kind"] == "subscription"), None)
    if sub is None or sub["net_minor"] <= 0:
        return
    if acc.trial_cancelled_at is not None and acc.trial_cancelled_at.astimezone(z).date() < first:
        lines.remove(sub)  # cancelled in the trial, in an earlier month: nothing more is charged
        return
    t0 = acc.trial_started_at.astimezone(z).date()
    t1 = acc.trial_ends_at.astimezone(z).date()  # first day after the trial counts as paid
    days = max(0, (min(t1, last + timedelta(days=1)) - max(t0, first)).days)
    if days <= 0:
        return
    credit = sub["net_minor"] if acc.trial_cancelled_at is not None else round(sub["net_minor"] * days / dim)
    if credit <= 0:
        return
    da = currency == "DKK"
    text = ("Gratis prøveperiode (14 dage)" if da else "Free trial (14 days)")
    lines.append({"kind": "trial_credit", "description": text, "net_minor": -min(credit, sub["net_minor"])})


def run_due(db: OrmSession, now: datetime | None = None) -> int:
    """The worker's check: mail the owners once, shortly before the first charge. Returns how many mails were queued."""
    from app.modules.billing import customer_mails
    from app.modules.billing.agreements import current
    from app.modules.reports.service import tz_of

    now = now or _now()
    n = 0
    for acc in db.scalars(select(BillingAccount).where(
            BillingAccount.trial_ends_at.is_not(None), BillingAccount.trial_mailed_at.is_(None),
            BillingAccount.trial_cancelled_at.is_(None))):
        if not (acc.trial_ends_at - MAIL_BEFORE <= now < acc.trial_ends_at):
            continue
        a = current(db, acc.workspace_id)
        gross = a.monthly_net_minor + a.monthly_net_minor * a.tax_basis_points // 10000 if a else 0
        day = acc.trial_ends_at.astimezone(ZoneInfo(tz_of(db, acc.workspace_id)))
        for u in db.scalars(select(User).join(Membership, Membership.user_id == User.id).where(
                Membership.workspace_id == acc.workspace_id, Membership.role == "owner")):
            customer_mails.send(db, kind="trial_ending", to_email=u.email, lang=u.interface_language, audience="erhverv",
                                dedupe=f"{acc.workspace_id}:trial:{u.id}", amount_minor=gross,
                                currency=a.currency if a else "DKK", workspace_id=acc.workspace_id, date=day)
        acc.trial_mailed_at = now
        n += 1
    db.commit()
    return n

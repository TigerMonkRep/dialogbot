"""«Betalt» and the 7 days' grace (Fürster 12/11).

Neither the website chat nor the phone goes live without a paid subscription. When a PAID subscription stops being
paid – the card expired or was removed, or a payment failed – both keep running for 7 days while the owners are mailed
to update the card: at the start, after about 3 days and the day before the stop. After 7 days the chat answers no
visitor (`subscription_required`). A subscription that was never paid gets no grace; a new card ends the grace at once.

- `strictly_paid`   the plain rule (#18): a confirmed agreement plus a usable card – or only the confirmed agreement
                    where card payment (Stripe) is not set up. «Usable» = saved, not expired, no failed payment since.
- `subscription_paid`  the gate: strictly paid, or within 7 days of having stopped being paid. Read-only, so the public
                    widget can ask it on every request; before the worker has noticed a lapse, the grace counts from now.
- `sync`            records the lapse / the recovery on the billing account and queues the grace mails. Run by the
                    worker every minute (`run_due`), after Stripe's webhooks and when a card is saved.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from app.models import BillingAccount

GRACE = timedelta(days=7)
# The three mails: at the start, after about 3 days, and the day before the stop.
MAIL_AT = (timedelta(0), timedelta(days=3), timedelta(days=6))


def _now() -> datetime:
    return datetime.now(UTC)


def _confirmed(db: OrmSession, ws_id: uuid.UUID) -> bool:
    from app.modules.billing.agreements import current

    a = current(db, ws_id)
    return a is not None and a.model != "B"


def card_expired(card_exp: str | None, now: datetime) -> bool:
    """«MM/YY» – a card is valid to the end of its month."""
    try:
        mm, yy = (card_exp or "").split("/")
        month, year = int(mm), 2000 + int(yy)
    except ValueError:
        return False
    return (year, month) < (now.year, now.month)


def strictly_paid(db: OrmSession, ws_id: uuid.UUID, now: datetime | None = None) -> bool:
    from app.modules.billing import stripe

    if not _confirmed(db, ws_id):
        return False
    if not stripe.configured():
        return True
    acc = db.get(BillingAccount, ws_id)
    return bool(acc and acc.payment_method_id and not card_expired(acc.card_exp, now or _now()) and acc.payment_failed_at is None)


def grace_ends(acc: BillingAccount | None, now: datetime) -> datetime | None:
    """When the grace ends for an account that stopped being paid (None: never paid = no grace)."""
    if acc is None or acc.first_paid_at is None:
        return None
    return (acc.unpaid_since or now) + GRACE


def subscription_paid(db: OrmSession, ws_id: uuid.UUID, now: datetime | None = None) -> bool:
    now = now or _now()
    if strictly_paid(db, ws_id, now):
        return True
    ends = grace_ends(db.get(BillingAccount, ws_id), now)
    return ends is not None and now < ends


def sync(db: OrmSession, ws_id: uuid.UUID, now: datetime | None = None) -> str:
    """Record paid / lapsed and queue the due grace mail. Returns paid | grace | stopped | never_paid."""
    now = now or _now()
    acc = db.get(BillingAccount, ws_id)
    if strictly_paid(db, ws_id, now):
        if acc is not None:
            acc.first_paid_at = acc.first_paid_at or now
            acc.unpaid_since, acc.grace_mails = None, 0
        return "paid"
    if acc is None or acc.first_paid_at is None:
        return "never_paid"
    if acc.unpaid_since is None:
        acc.unpaid_since, acc.grace_mails = now, 0
    ends = acc.unpaid_since + GRACE
    due = sum(1 for at in MAIL_AT if now >= acc.unpaid_since + at)
    if now < ends and due > acc.grace_mails:
        _mail(db, acc, stage=due - 1, ends=ends)  # only the latest due one: a late worker never sends three at once
        acc.grace_mails = due
    return "grace" if now < ends else "stopped"


def _mail(db: OrmSession, acc: BillingAccount, *, stage: int, ends: datetime) -> None:
    from app.models import Membership, User
    from app.modules.billing import customer_mails
    from app.modules.reports.service import tz_of

    last_day = (ends - timedelta(seconds=1)).astimezone(ZoneInfo(tz_of(db, acc.workspace_id)))  # «kører videre til og med <dato>»
    for u in db.scalars(select(User).join(Membership, Membership.user_id == User.id).where(
            Membership.workspace_id == acc.workspace_id, Membership.role == "owner")):
        customer_mails.send(db, kind=f"grace_{stage}", to_email=u.email, lang=u.interface_language, audience="erhverv",
                            dedupe=f"{acc.workspace_id}:{acc.unpaid_since.isoformat()}:{u.id}", amount_minor=0,
                            currency="DKK", workspace_id=acc.workspace_id, date=last_day)


def run_due(db: OrmSession, now: datetime | None = None) -> int:
    """The worker's check: every account that has been paid. Returns how many changed state or got a mail."""
    now = now or _now()
    n = 0
    for acc in db.scalars(select(BillingAccount).where(BillingAccount.first_paid_at.is_not(None))):
        before = (acc.unpaid_since, acc.grace_mails)
        sync(db, acc.workspace_id, now)
        n += (acc.unpaid_since, acc.grace_mails) != before
    # Paid accounts not yet recorded as such (a card saved before this existed, or paid without a webhook).
    for acc in db.scalars(select(BillingAccount).where(BillingAccount.first_paid_at.is_(None),
                                                       BillingAccount.payment_method_id.is_not(None))):
        if sync(db, acc.workspace_id, now) == "paid":
            n += 1
    db.commit()
    return n


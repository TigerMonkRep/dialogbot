"""Dialogbot's list prices: the one place a price is written in code.

There is ONE offer (excl. VAT) – Fürster's decision 2026-11-10 (20:28, final; the public prices are the consumption
prices of the DF offer):
- the subscription, "Fra 2.495 kr./md." (whole øre below), with a package of 300 minutes a month that inbound calls
  AND outbound campaign calls draw on together (one shared pool, used in the order the calls happen);
- INSIDE the package there is no price per call: the minutes just come out of the package;
- once the package is used up: an outbound campaign call that STARTS after that costs, by outcome, 4 kr. when the
  person answers, 1 kr. at a voicemail and 0,25 kr. when unanswered/busy (an unknown outcome is the cheapest) – plus
  2 kr. per started minute of conversation; inbound calls cost 1,50 kr. per started minute. A call that crosses the
  limit only splits its minutes (no call price);
- 5.000 kr. once for setup by Dialogbot's own specialists (tailored setup and integration with the customer's own
  systems); doing it yourself through the three-step building guide is included in the subscription.
There is no fee per approved enquiry any more and no binding. Minutes are only credited when the customer complains
about a call (no automatic credit for failed calls).

The website, the sales script, the social posts and the invoices all read these numbers (or are tested against them),
so a price changes here first. Agreements snapshot the price and the package they were made at, so an old agreement
keeps its price; months invoiced before SHARED_POOL_FROM keep the model they were invoiced under (statement.py).
"""
from __future__ import annotations

from datetime import date

SUBSCRIPTION_MONTHLY_NET_MINOR = 249_500  # 2.495 kr. per month, excl. VAT
INCLUDED_MINUTES = 300                    # the package: minutes a month, inbound and outbound together
INBOUND_INCLUDED_MINUTES = INCLUDED_MINUTES  # (name kept: offers and agreements store it under this name)
INBOUND_EXTRA_MINUTE_NET_MINOR = 150      # 1,50 kr. per started inbound minute above the package, excl. VAT
OUTBOUND_EXTRA_MINUTE_NET_MINOR = 200     # 2 kr. per started outbound (campaign) minute above the package, excl. VAT
# Price per outbound call that starts after the package is used up, by outcome (campaigns/service.outcome_class)
OUTBOUND_CALL_ANSWERED_NET_MINOR = 400    # 4 kr. – the person answered
OUTBOUND_CALL_VOICEMAIL_NET_MINOR = 100   # 1 kr. – voicemail (Vapi voicemail detection; no message is left)
OUTBOUND_CALL_NO_ANSWER_NET_MINOR = 25    # 0,25 kr. – unanswered, busy, failed to connect, or outcome unknown
SPECIALIST_SETUP_NET_MINOR = 500_000      # 5.000 kr. once, setup by our specialists, excl. VAT (self-setup is included)
TAX_BASIS_POINTS = 2500                   # 25 % Danish VAT
# First month billed with the shared package (inbound + outbound). Earlier months keep
# the model they were billed under: inbound-only package, campaign calls at 4 kr. + 2 kr./min snapshotted per call.
SHARED_POOL_FROM = date(2026, 11, 1)


def kr(minor: int) -> str:
    """Whole øre → "2.495" or "4" or "4,50" (Danish thousands separator, decimals only when needed)."""
    whole = f"{minor // 100:,}".replace(",", ".")
    return whole + (f",{minor % 100:02d}" if minor % 100 else "")

# Dialogbot Privat: a pack of credits, bought by consumers with Stripe Checkout (mode=payment). Prices incl. VAT.
PRIVAT_CREDIT_PACK_CREDITS = 10
PRIVAT_CREDIT_PACK_NET_MINOR = 2320       # 23,20 kr. excl. VAT
PRIVAT_CREDIT_PACK_GROSS_MINOR = PRIVAT_CREDIT_PACK_NET_MINOR * (10000 + TAX_BASIS_POINTS) // 10000  # 29 kr.
PRIVAT_CALL_CREDITS = 3                   # an approved call reserves 3 credits; released if nobody answers
PRIVAT_FREE_TASKS_PER_MONTH = 0  # the free tier only receives shared lists; a plan (14-day card trial) does the rest
PRIVAT_WELCOME_CREDITS = 3

# Dialogbot Privat subscriptions (app/modules/privat/subscriptions.py). Consumer prices, so INCL. 25 % VAT, in øre.
# The yearly plan is paid once a year (yearly_total); yearly_monthly is what that comes to per month (~20 % off).
# Calls are per calendar month (Europe/Copenhagen); a call nobody answers does not count. Beyond the quota the
# credit pack above is sold as "ekstra opkald" (3 credits per call).
PRIVAT_TRIAL_DAYS = 14
PRIVAT_PLANS: tuple[dict, ...] = (
    {"key": "basis", "name": "Basis", "monthly_minor": 4900, "yearly_monthly_minor": 3900, "yearly_total_minor": 46800,
     "calls": 3, "people": 1, "apps_included": False, "recommended": False},
    {"key": "plus", "name": "Plus", "monthly_minor": 9900, "yearly_monthly_minor": 7900, "yearly_total_minor": 94800,
     "calls": 10, "people": 1, "apps_included": True, "recommended": True},
    {"key": "familie", "name": "Familie", "monthly_minor": 16900, "yearly_monthly_minor": 13500,
     "yearly_total_minor": 162000, "calls": 25, "people": 5, "apps_included": True, "recommended": False},
)

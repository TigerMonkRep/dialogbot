"""Dialogbot's list prices: the one place a price is written in code.

There is ONE offer (excl. VAT):
- the subscription, "Fra 2.495 kr./md." (whole øre below);
- outbound campaign calls: 4 kr. per call that is dialled (retries included) + 2 kr. per started minute of
  conversation, so an unanswered attempt costs 4 kr. and a 3-minute conversation 10 kr. – the minutes are what cost
  us money (telephony, speech, voice and model);
- inbound calls: 300 minutes a month are included in the subscription, every started minute above that costs 1,50 kr.;
- 5.000 kr. once for setup by Dialogbot's own specialists (tailored setup and integration with the customer's own
  systems); doing it yourself through the three-step building guide is included in the subscription.
There is no fee per approved enquiry any more and no binding.

The website, the sales script, the social posts and the invoices all read these numbers (or are tested against them),
so a price changes here first. Agreements snapshot the price they were made at, so an old agreement keeps its price.
"""
from __future__ import annotations

SUBSCRIPTION_MONTHLY_NET_MINOR = 249_500  # 2.495 kr. per month, excl. VAT
CAMPAIGN_CALL_NET_MINOR = 400             # 4 kr. per outbound campaign call dialled, excl. VAT
CAMPAIGN_MINUTE_NET_MINOR = 200           # 2 kr. per started minute of conversation on a campaign call, excl. VAT
INBOUND_INCLUDED_MINUTES = 300            # inbound call minutes included in the subscription each month
INBOUND_EXTRA_MINUTE_NET_MINOR = 150      # 1,50 kr. per started inbound minute above the included ones, excl. VAT
SPECIALIST_SETUP_NET_MINOR = 500_000      # 5.000 kr. once, setup by our specialists, excl. VAT (self-setup is included)
TAX_BASIS_POINTS = 2500                   # 25 % Danish VAT


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

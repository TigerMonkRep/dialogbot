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

# Outbound call price by outcome (Fürster's decision 2026-11-10; same names and values as on
# qa/decisions-2026-11-10, where Erhverv bills them after the package). Excl. VAT. Dialogbot Privat's extra calls are
# priced from these (markets.privat_extra_call): the same net price + 25 % moms (Fürster's decision 2026-11-11).
OUTBOUND_CALL_ANSWERED_NET_MINOR = 400    # 4 kr. – the person answered
OUTBOUND_CALL_VOICEMAIL_NET_MINOR = 100   # 1 kr. – voicemail (Vapi voicemail detection; no message is left)
OUTBOUND_CALL_NO_ANSWER_NET_MINOR = 25    # 0,25 kr. – unanswered, busy or failed to connect
# Erhverv's honest maximum per contact (2 attempts answered + 3 started minutes = 14 kr. excl. VAT): the most one extra
# Privat call can cost (17,50 kr. incl. VAT) and what is reserved before it is dialled.
MAX_PER_CONTACT_ATTEMPTS = 2
MAX_PER_CONTACT_MINUTES = 3


def gross_minor(net_minor: int, rate_bp: int = TAX_BASIS_POINTS) -> int:
    """Net → incl. VAT, rounded half up to a whole øre (cent). THE rounding of Privat's consumer prices: 0,25 kr. net →
    0,3125 → 0,31 kr.; 5,90 kr → 7,375 → 7,38 kr."""
    if net_minor < 0:
        return -gross_minor(-net_minor, rate_bp)
    return (net_minor * (10000 + rate_bp) + 5000) // 10000


# Dialogbot Privat's «Opkaldssaldo» (app/modules/privat/ledger.py): a prepaid balance in kroner, in øre. INCL. VAT.
PRIVAT_TOPUPS_GROSS_MINOR = (5_000, 10_000, 20_000)  # top-ups at Stripe Checkout (mode=payment): 50, 100, 200 kr.
PRIVAT_WELCOME_BONUS_MINOR = 1_000        # 10 kr. once, when the account is created
PRIVAT_REFERRAL_BONUS_MINOR = 1_000       # 10 kr. to each, after the invitee's first paid period
PRIVAT_EXTRA_TASK_MINOR = 300             # 3 kr. for a task beyond the month's limit (or a sponsor spot)
# The old credits were converted at 1 credit = 2,90 kr. (29 kr. for 10). A website booking (browser worker) cost
# 1 credit and has no price of its own yet, so it costs the converted 2,90 kr. until Fürster decides one.
PRIVAT_CREDIT_VALUE_MINOR = 290
PRIVAT_BROWSER_BOOKING_MINOR = PRIVAT_CREDIT_VALUE_MINOR
PRIVAT_FREE_TASKS_PER_MONTH = 0  # the free tier only receives shared lists; a plan (14-day card trial) does the rest

# Dialogbot Privat subscriptions (app/modules/privat/subscriptions.py). Consumer prices, so INCL. 25 % VAT, in øre.
# The yearly plan is paid once a year (yearly_total); yearly_monthly is what that comes to per month (~20 % off).
# Calls are per calendar month (Europe/Copenhagen); a call nobody answers does not count. Beyond the quota an extra
# call is paid from the Opkaldssaldo at the outcome price above + moms (markets.privat_extra_call).
PRIVAT_TRIAL_DAYS = 14
PRIVAT_PLANS: tuple[dict, ...] = (
    {"key": "basis", "name": "Basis", "monthly_minor": 4900, "yearly_monthly_minor": 3900, "yearly_total_minor": 46800,
     "calls": 3, "people": 1, "apps_included": False, "recommended": False},
    {"key": "plus", "name": "Plus", "monthly_minor": 9900, "yearly_monthly_minor": 7900, "yearly_total_minor": 94800,
     "calls": 10, "people": 1, "apps_included": True, "recommended": True},
    {"key": "familie", "name": "Familie", "monthly_minor": 16900, "yearly_monthly_minor": 13500,
     "yearly_total_minor": 162000, "calls": 25, "people": 5, "apps_included": True, "recommended": False},
)

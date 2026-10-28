"""Dialogbot's list prices: the one place a price is written in code.

There is ONE offer (excl. VAT):
- the subscription, "Fra 2.495 kr./md." (whole øre below);
- 4 kr. per outbound call in a campaign (every call that is dialled, retries included).
- 5.000 kr. once for setup by Dialogbot's own specialists (tailored setup and integration with the customer's own
  systems); doing it yourself through the three-step building guide is included in the subscription.
There is no fee per approved enquiry any more and no binding.

The website, the sales script, the social posts and the invoices all read these numbers (or are tested against them),
so a price changes here first. Agreements snapshot the price they were made at, so an old agreement keeps its price.
"""
from __future__ import annotations

SUBSCRIPTION_MONTHLY_NET_MINOR = 249_500  # 2.495 kr. per month, excl. VAT
CAMPAIGN_CALL_NET_MINOR = 400             # 4 kr. per outbound campaign call, excl. VAT
SPECIALIST_SETUP_NET_MINOR = 500_000      # 5.000 kr. once, setup by our specialists, excl. VAT (self-setup is included)
TAX_BASIS_POINTS = 2500                   # 25 % Danish VAT


def kr(minor: int) -> str:
    """Whole øre → "2.495" or "4" or "4,50" (Danish thousands separator, decimals only when needed)."""
    whole = f"{minor // 100:,}".replace(",", ".")
    return whole + (f",{minor % 100:02d}" if minor % 100 else "")

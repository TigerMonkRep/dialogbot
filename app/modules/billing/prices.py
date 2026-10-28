"""Dialogbot's list prices: the one place a price is written in code.

There is ONE offer (excl. VAT):
- the subscription, "Fra 2.495 kr./md." (whole øre below);
- 4 kr. per outbound call in a campaign (every call that is dialled, retries included).
There is no fee per approved enquiry any more. Setup is free and takes about half an hour; there is no binding.

The website, the sales script, the social posts and the invoices all read these numbers (or are tested against them),
so a price changes here first. Agreements snapshot the price they were made at, so an old agreement keeps its price.
"""
from __future__ import annotations

SUBSCRIPTION_MONTHLY_NET_MINOR = 249_500  # 2.495 kr. per month, excl. VAT
CAMPAIGN_CALL_NET_MINOR = 400             # 4 kr. per outbound campaign call, excl. VAT
TAX_BASIS_POINTS = 2500                   # 25 % Danish VAT


def kr(minor: int) -> str:
    """Whole øre → "2.495" or "4" or "4,50" (Danish thousands separator, decimals only when needed)."""
    whole = f"{minor // 100:,}".replace(",", ".")
    return whole + (f",{minor % 100:02d}" if minor % 100 else "")

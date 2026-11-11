"""Dialogbot Privat's own look on Stripe's hosted pages.

The Stripe account is branded for Dialogbot Erhverv (blue logo). A private customer who pays for a plan or fills up
the Opkaldssaldo must not land on an Erhverv-looking page, so every Privat Checkout Session carries `branding_settings`
(orange button, warm paper, the orange logo mark and the name "Dialogbot Privat"). The parameter exists from Stripe
API version 2025-09-30.clover, so the create call is pinned to that version; the session's `url` is all we read.

If Stripe rejects the branding (an icon URL it cannot fetch, say), the session is created once more without it –
the payment matters more than the colours.
"""
from __future__ import annotations

from app.config import get_settings
from app.modules.billing import stripe as stripe_api

CHECKOUT_API_VERSION = "2025-09-30.clover"
ACCENT = "#E0521A"
PAPER = "#FFFBF5"
ICON_PATH = "/icons/privat-icon-512.png"
DISPLAY_NAME = "Dialogbot Privat"


def branding_settings() -> dict:
    base = get_settings().frontend_base_url.rstrip("/")
    out: dict = {"display_name": DISPLAY_NAME, "background_color": PAPER, "button_color": ACCENT,
                 "border_style": "pill", "font_family": "inter"}
    if base.startswith("https://"):  # Stripe fetches the icon itself; a localhost URL would never resolve
        out["icon"] = {"type": "url", "url": f"{base}{ICON_PATH}"}
    return out


def create_checkout_session(payload: dict) -> dict:
    """POST /checkout/sessions with the Privat branding; once more without it if Stripe refuses the branding."""
    try:
        return stripe_api.request("POST", "/checkout/sessions", payload | {"branding_settings": branding_settings()},
                                  version=CHECKOUT_API_VERSION)
    except stripe_api.StripeFailed as e:
        if "branding" not in str(e).lower() and "icon" not in str(e).lower() and "logo" not in str(e).lower():
            raise
        return stripe_api.request("POST", "/checkout/sessions", payload)

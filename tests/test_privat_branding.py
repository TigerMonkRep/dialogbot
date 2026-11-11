"""Dialogbot Privat's own look on Stripe Checkout: every Privat session carries branding_settings (orange, the Privat
icon, «Dialogbot Privat») on the API version that knows the parameter – and is created once more without them when
Stripe refuses the branding, so a payment never fails over a logo."""
from __future__ import annotations

from app.config import get_settings
from app.modules.billing import stripe as stripe_api
from app.modules.privat import branding


def _env(monkeypatch, base="https://dialogbot.app"):
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_x")
    monkeypatch.setenv("FRONTEND_BASE_URL", base)
    get_settings.cache_clear()


def test_subscription_and_topup_checkouts_carry_the_privat_branding(api, pv, monkeypatch):
    tok = pv.account("mette@testmail.dk", trial=False)  # no running subscription: checkout allowed (PC-SUB-07)
    _env(monkeypatch)
    sent = []

    def fake(m, p, d=None, **k):
        sent.append((p, d, k))
        return {"id": "cs_1", "url": "https://checkout.stripe.com/c/pay/cs_1"}

    monkeypatch.setattr(stripe_api, "request", fake)
    assert api.post(tok, "/privat/subscription/checkout", {"plan": "plus", "interval": "month"}).status_code == 200
    assert api.post(tok, "/privat/balance/checkout").status_code in (200, 201)
    sent = [x for x in sent if x[0] == "/checkout/sessions"]  # (the VAT tax rate is looked up first, once)
    assert len(sent) == 2
    for p, d, k in sent:
        assert p == "/checkout/sessions" and k["version"] == "2025-09-30.clover"
        b = d["branding_settings"]
        assert b["display_name"] == "Dialogbot Privat" and b["button_color"] == "#C4461A"
        assert b["background_color"] == "#FFFBF5" and b["border_style"] == "pill"
        assert b["icon"] == {"type": "url", "url": "https://dialogbot.app/icons/privat-icon-512.png"}
    assert sent[0][1]["mode"] == "subscription" and sent[1][1]["mode"] == "payment"


def test_no_icon_url_without_a_public_site(monkeypatch):
    _env(monkeypatch, base="http://localhost:3000")
    b = branding.branding_settings()
    assert "icon" not in b and b["display_name"] == "Dialogbot Privat"


def test_refused_branding_falls_back_to_a_plain_session(monkeypatch):
    _env(monkeypatch)
    sent = []

    def fake(m, p, d=None, **k):
        sent.append((d, k))
        if "branding_settings" in (d or {}):
            raise stripe_api.StripeFailed("Stripe afviste kaldet: Invalid branding_settings[icon][url]")
        return {"id": "cs_2", "url": "https://checkout.stripe.com/c/pay/cs_2"}

    monkeypatch.setattr(stripe_api, "request", fake)
    out = branding.create_checkout_session({"mode": "payment", "success_url": "https://dialogbot.app/x"})
    assert out["id"] == "cs_2" and len(sent) == 2
    assert "branding_settings" in sent[0][0] and sent[0][1] == {"version": "2025-09-30.clover"}
    assert "branding_settings" not in sent[1][0] and sent[1][1] == {}


def test_other_stripe_errors_are_not_retried(monkeypatch):
    _env(monkeypatch)
    n = 0

    def fake(m, p, d=None, **k):
        nonlocal n
        n += 1
        raise stripe_api.StripeFailed("Stripe afviste kaldet: No such price")

    monkeypatch.setattr(stripe_api, "request", fake)
    try:
        branding.create_checkout_session({"mode": "payment"})
    except stripe_api.StripeFailed:
        pass
    else:
        raise AssertionError("expected StripeFailed")
    assert n == 1

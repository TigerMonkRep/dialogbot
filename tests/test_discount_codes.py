"""Discount codes: operators make them in the admin (Erhverv, Privat or both); an Erhverv owner types one on Konto
and the statement carries a negative line for the months it covers; a Privat code is mirrored to Stripe and applied
on Checkout, and the completed session records the redemption."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.config import get_settings
from app.models import DiscountCode, DiscountRedemption, ReceptionAgreement
from app.modules.billing import discounts, prices
from app.modules.billing import stripe as stripe_api
from tests.privat_fixtures import WED_10


def _agreement(db, ws):
    db.add(ReceptionAgreement(workspace_id=ws, version=1, model="A", monthly_net_minor=prices.SUBSCRIPTION_MONTHLY_NET_MINOR,
                              lead_fee_net_minor=0, created_at=datetime(2026, 1, 1, tzinfo=UTC)))
    db.commit()


# --------------------------------------------------------------------------- admin

def test_only_operators_make_codes_and_the_terms_are_checked(api, two_workspaces):
    tok = two_workspaces["tok_a"]
    assert api.get(tok, "/operator/admin/rabatkoder").status_code == 403
    op = api.operator()
    bad = [
        {"code": "x", "audience": "erhverv", "percent_off": 10},
        {"code": "FINT", "audience": "erhverv"},
        {"code": "FINT", "audience": "erhverv", "percent_off": 10, "amount_off_minor": 100},
        {"code": "FINT", "audience": "erhverv", "percent_off": 101},
        {"code": "FINT", "audience": "erhverv", "percent_off": 10, "duration": "repeating"},
        {"code": "FINT", "audience": "alle", "percent_off": 10},
    ]
    for body in bad:
        assert api.post(op, "/operator/admin/rabatkoder", body).status_code == 422, body
    r = api.post(op, "/operator/admin/rabatkoder", {"code": "velkommen 20", "audience": "erhverv", "percent_off": 20,
                                                     "duration": "repeating", "duration_months": 3, "max_redemptions": 2,
                                                     "note": "Messen i Herning"})
    assert r.status_code == 201, r.text
    out = r.json()
    assert out["code"] == "VELKOMMEN20" and out["text"] == "20 % i 3 måneder" and out["redemptions"] == 0
    assert out["active"] is True and out["stripe"] is False and out["note"] == "Messen i Herning"
    assert api.post(op, "/operator/admin/rabatkoder", {"code": "VELKOMMEN20", "audience": "privat", "percent_off": 5}).status_code == 409
    lst = api.get(op, "/operator/admin/rabatkoder").json()
    assert [x["code"] for x in lst["items"]] == ["VELKOMMEN20"] and lst["stripe"] is False
    off = api.post(op, f"/operator/admin/rabatkoder/{out['id']}/deaktiver").json()
    assert off["active"] is False
    assert api.post(op, f"/operator/admin/rabatkoder/{uuid.uuid4()}/deaktiver").status_code == 404


# --------------------------------------------------------------------------- Erhverv

def test_erhverv_code_on_konto_becomes_a_statement_line_for_the_months_it_covers(api, two_workspaces, db, monkeypatch):
    op = api.operator()
    tok, ws = two_workspaces["tok_a"], uuid.UUID(two_workspaces["ws_a"])
    _agreement(db, ws)
    api.post(op, "/operator/admin/rabatkoder", {"code": "TREMDR", "audience": "begge", "percent_off": 50,
                                                "duration": "repeating", "duration_months": 2})
    api.post(op, "/operator/admin/rabatkoder", {"code": "KUNPRIVAT", "audience": "privat", "percent_off": 50})
    api.post(op, "/operator/admin/rabatkoder", {"code": "SLUT", "audience": "erhverv", "percent_off": 50,
                                                "ends_at": "2020-01-01T00:00:00Z"})
    base = f"/workspaces/{ws}/billing"
    assert api.get(tok, f"{base}/discount").json() == {"code": None, "can_add": True, "can_manage": True}
    for code, msg in [("FINDESIKKE", "findes ikke"), ("KUNPRIVAT", "gælder ikke her"), ("SLUT", "udløbet")]:
        r = api.put(tok, f"{base}/discount", {"code": code})
        assert r.status_code == 422 and msg in r.json()["message"], (code, r.text)
    # the other owner cannot touch workspace A's code
    assert api.put(two_workspaces["tok_b"], f"{base}/discount", {"code": "TREMDR"}).status_code in (403, 404)
    monkeypatch.setattr(discounts, "now", lambda: datetime(2026, 11, 4, 17, 0, tzinfo=UTC))
    r = api.put(tok, f"{base}/discount", {"code": "tremdr"})
    assert r.status_code == 200, r.text
    assert r.json() == {"code": "TREMDR", "text": "50 % i 2 måneder", "from_month": "2026-11", "to_month": "2026-12",
                        "can_add": False, "can_manage": True}
    assert api.put(tok, f"{base}/discount", {"code": "TREMDR"}).status_code == 409  # one code per workspace
    red = db.scalar(select(DiscountRedemption).where(DiscountRedemption.workspace_id == ws))
    red.redeemed_at = datetime(2026, 11, 4, 17, 0, tzinfo=UTC)
    db.commit()
    sub = prices.SUBSCRIPTION_MONTHLY_NET_MINOR
    for month, expect in [("2026-10", None), ("2026-11", -(sub // 2)), ("2026-12", -(sub // 2)), ("2027-01", None)]:
        st = api.get(tok, f"{base}/statement?month={month}").json()
        line = next((x for x in st["lines"] if x["kind"] == "discount_code"), None)
        if expect is None:
            assert line is None, month
            assert st["totals"]["net_minor"] == sub
        else:
            assert line["net_minor"] == expect and line["description"] == "Rabatkode TREMDR: 50 % i 2 måneder", month
            assert st["totals"]["net_minor"] == sub + expect
    # the code counts one redemption now; a cap of 1 stops the next workspace
    lst = api.get(op, "/operator/admin/rabatkoder").json()["items"]
    assert next(x for x in lst if x["code"] == "TREMDR")["redemptions"] == 1


def test_amount_codes_never_exceed_the_month_and_once_means_the_first_month(api, two_workspaces, db, monkeypatch):
    op = api.operator()
    tok, ws = two_workspaces["tok_b"], uuid.UUID(two_workspaces["ws_b"])
    _agreement(db, ws)
    api.post(op, "/operator/admin/rabatkoder", {"code": "TUSIND", "audience": "erhverv", "amount_off_minor": 100_000_00})
    monkeypatch.setattr(discounts, "now", lambda: datetime(2026, 11, 4, 17, 0, tzinfo=UTC))
    assert api.put(tok, f"/workspaces/{ws}/billing/discount", {"code": "TUSIND"}).status_code == 422  # above 10.000 kr.
    api.post(op, "/operator/admin/rabatkoder", {"code": "STOR", "audience": "erhverv", "amount_off_minor": 900_000})
    r = api.put(tok, f"/workspaces/{ws}/billing/discount", {"code": "STOR"})
    assert r.json()["text"] == "9.000,00 kr. én gang" and r.json()["to_month"] == "2026-11"
    red = db.scalar(select(DiscountRedemption).where(DiscountRedemption.workspace_id == ws))
    red.redeemed_at = datetime(2026, 11, 4, 17, 0, tzinfo=UTC)
    db.commit()
    st = api.get(tok, f"/workspaces/{ws}/billing/statement?month=2026-11").json()
    assert st["totals"]["net_minor"] == 0  # capped at the month, never below zero
    assert next(x for x in st["lines"] if x["kind"] == "discount_code")["net_minor"] == -prices.SUBSCRIPTION_MONTHLY_NET_MINOR
    assert not any(x["kind"] == "discount_code" for x in api.get(tok, f"/workspaces/{ws}/billing/statement?month=2026-12").json()["lines"])


# --------------------------------------------------------------------------- Privat

def _stripe(monkeypatch):
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_x")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_privat")
    get_settings.cache_clear()


def test_privat_code_is_mirrored_to_stripe_and_applied_on_checkout(api, pv, db, monkeypatch):
    _stripe(monkeypatch)
    sent = []

    def fake(m, p, d=None, **k):
        sent.append((m, p, d))
        if p == "/coupons":
            return {"id": "cpn_1"}
        if p == "/promotion_codes":
            return {"id": "promo_1"}
        if p.startswith("/promotion_codes/"):
            return {"id": "promo_1", "active": False}
        if p == "/checkout/sessions":
            return {"id": "cs_1", "url": "https://checkout.stripe.com/c/pay/cs_1"}
        if p.startswith("/subscriptions/"):
            return {"id": "sub_1", "status": "active", "customer": "cus_1", "cancel_at_period_end": False,
                    "items": {"data": [{"current_period_end": int((WED_10 + timedelta(days=30)).timestamp()),
                                        "price": {"recurring": {"interval": "month"}}}]},
                    "metadata": {"kind": "privat_subscription", "workspace_id": self_ws[0], "plan": "plus", "interval": "month"}}
        return {"id": "x"}

    self_ws = [""]
    monkeypatch.setattr(stripe_api, "request", fake)
    op = api.operator()
    r = api.post(op, "/operator/admin/rabatkoder", {"code": "HEJ10", "audience": "privat", "percent_off": 10,
                                                     "duration": "repeating", "duration_months": 3, "max_redemptions": 100,
                                                     "ends_at": "2027-01-01T00:00:00Z"})
    assert r.status_code == 201 and r.json()["stripe"] is True
    coupon = next(d for m, p, d in sent if p == "/coupons")
    assert coupon["percent_off"] == 10 and coupon["duration"] == "repeating" and coupon["duration_in_months"] == 3
    assert coupon["max_redemptions"] == 100 and coupon["redeem_by"] == int(datetime(2027, 1, 1, tzinfo=UTC).timestamp())
    promo = next(d for m, p, d in sent if p == "/promotion_codes")
    assert promo == {"coupon": "cpn_1", "code": "HEJ10", "active": True, "metadata": {"dialogbot_discount_code": r.json()["id"]}}
    row = db.scalar(select(DiscountCode).where(DiscountCode.code == "HEJ10"))
    assert (row.stripe_coupon_id, row.stripe_promotion_code_id) == ("cpn_1", "promo_1")

    tok = pv.account("mette@testmail.dk")
    ws = pv.ws(tok)
    self_ws[0] = str(ws)
    # without a code: Stripe's own field; with a code: the discount is fixed on the session
    api.post(tok, "/privat/subscription/checkout", {"plan": "plus", "interval": "month"})
    plain = sent[-1][2]
    assert plain["allow_promotion_codes"] is True and "discounts" not in plain
    r = api.post(tok, "/privat/subscription/checkout", {"plan": "plus", "interval": "month", "code": " hej10 "})
    assert r.status_code == 200, r.text
    with_code = sent[-1][2]
    assert with_code["discounts"] == [{"promotion_code": "promo_1"}] and "allow_promotion_codes" not in with_code
    r = api.post(tok, "/privat/subscription/checkout", {"plan": "plus", "interval": "month", "code": "FINDESIKKE"})
    assert r.status_code == 422 and "findes ikke" in r.json()["message"]
    # back from Checkout: the session's promotion code becomes the redemption (once)
    monkeypatch.setattr(stripe_api, "request", lambda m, p, d=None, **k: fake(m, p, d) if not p.startswith("/checkout/sessions/") else {
        "id": "cs_1", "mode": "subscription", "subscription": "sub_1",
        "metadata": {"kind": "privat_subscription", "workspace_id": str(ws), "plan": "plus", "interval": "month"},
        "discounts": [{"coupon": "cpn_1", "promotion_code": "promo_1"}]})
    assert api.get(tok, "/privat/subscription?session_id=cs_1").json()["plan"] == "plus"
    api.get(tok, "/privat/subscription?session_id=cs_1")
    reds = db.scalars(select(DiscountRedemption).where(DiscountRedemption.code_id == row.id)).all()
    assert len(reds) == 1 and reds[0].workspace_id == ws and reds[0].source == "privat_checkout" and reds[0].stripe_ref == "cs_1"
    assert next(x for x in api.get(op, "/operator/admin/rabatkoder").json()["items"] if x["code"] == "HEJ10")["redemptions"] == 1
    # deactivating stops it at Stripe too
    api.post(op, f"/operator/admin/rabatkoder/{row.id}/deaktiver")
    assert sent[-1][1] == "/promotion_codes/promo_1" and sent[-1][2] == {"active": False}
    assert api.post(tok, "/privat/subscription/checkout", {"plan": "plus", "interval": "month", "code": "HEJ10"}).status_code == 422

"""7 days' grace when a paid Erhverv subscription stops being paid (Fürster 12/11).

The card expired or was removed, or a payment failed: chat and phone keep running for 7 days while the owners get a
mail at the start, after about 3 days and the day before the stop; then the chat answers no visitor
(`subscription_required`). A subscription that was never paid gets no grace; a new card ends the grace at once.
Days 0, 3, 6 and 8 are checked both in the gate (`grace.subscription_paid`) and on the public widget endpoint."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.models import BillingAccount, OutboxEvent
from app.modules.billing import customer_mails, grace, stripe
from tests.test_webchat import PUB, SITE, _approve, _enable, _settings
from tests.test_webchat import fake as ai_fake  # noqa: F401

DAY = timedelta(days=1)


@pytest.fixture
def card_payment(monkeypatch):
    monkeypatch.setattr(stripe, "configured", lambda: True)


def _card(db, ws: str, exp: str = "12/39") -> BillingAccount:
    a = db.get(BillingAccount, uuid.UUID(ws)) or BillingAccount(workspace_id=uuid.UUID(ws))
    a.stripe_customer_id = a.stripe_customer_id or f"cus_{ws[:8]}"
    a.payment_method_id, a.card_brand, a.card_last4, a.card_exp = "pm_old", "visa", "4242", exp
    db.add(a)
    db.commit()
    return a


def _live(api, db, t) -> tuple[str, str, str]:
    """A paid workspace (confirmed + card) whose chat is live. Returns (token, workspace id, widget key)."""
    tok, ws = t["tok_a"], t["ws_a"]
    _approve(api, tok, ws)
    _card(db, ws)
    api.subscribe(tok, ws)  # confirming with a card on file records it as paid
    assert db.get(BillingAccount, uuid.UUID(ws)).first_paid_at is not None
    r = _enable(api, tok, ws)
    assert r.status_code == 200, r.text
    return tok, ws, r.json()["widget_key"]


def _mails(db, ws: str) -> list[str]:
    db.expire_all()
    return sorted(k.split(":")[1] for k in db.scalars(select(OutboxEvent.dedupe_key).where(
        OutboxEvent.workspace_id == uuid.UUID(ws), OutboxEvent.dedupe_key.like("billing-mail:grace_%"))))


def _visitor(client, key: str) -> bool:
    return client.get(f"{PUB}/{key}/status", headers={"origin": SITE}).json()["available"]


def _visitor_on_day(db, client, ws: str, key: str, day: float, t0: datetime | None = None) -> bool:
    """What a visitor gets `day` days into the lapse: the public endpoint asks with the real clock, so the start of the
    lapse is moved back for the request (and put back to `t0` afterwards)."""
    db.expire_all()
    a = db.get(BillingAccount, uuid.UUID(ws))
    a.unpaid_since = datetime.now(UTC) - timedelta(days=day)
    db.commit()
    seen = _visitor(client, key)
    if t0 is not None:
        db.expire_all()
        db.get(BillingAccount, uuid.UUID(ws)).unpaid_since = t0
        db.commit()
    return seen


def test_failed_payment_grace_day_0_3_6_8(api, client, db, two_workspaces, card_payment, ai_fake):  # noqa: F811
    tok, ws, key = _live(api, db, two_workspaces)
    assert _visitor(client, key) is True
    # day 0: the payment fails (Stripe invoice.payment_failed) – the grace starts, the first mail goes out
    stripe._payment_state(db, uuid.UUID(ws), failed=True)
    db.commit()
    a = db.get(BillingAccount, uuid.UUID(ws))
    t0 = a.unpaid_since
    assert t0 is not None and not grace.strictly_paid(db, a.workspace_id)
    assert grace.subscription_paid(db, a.workspace_id, t0) is True
    assert _mails(db, ws) == ["grace_0"]
    assert _visitor(client, key) is True                                     # day 0: still live
    acc = api.get(tok, f"/workspaces/{ws}/billing/account").json()["subscription"]
    assert acc["paid"] is False and acc["in_grace"] is True and acc["payment_failed"] is True
    assert datetime.fromisoformat(acc["grace_ends"]) == t0 + grace.GRACE

    # day 3: the reminder; still live
    assert grace.sync(db, a.workspace_id, t0 + 3 * DAY) == "grace"
    db.commit()
    assert _mails(db, ws) == ["grace_0", "grace_1"]
    assert _visitor_on_day(db, client, ws, key, 3, t0) is True
    # day 6: the day before the stop – the last mail; still live
    assert grace.sync(db, a.workspace_id, t0 + 6 * DAY) == "grace"
    db.commit()
    assert _mails(db, ws) == ["grace_0", "grace_1", "grace_2"]
    assert grace.subscription_paid(db, a.workspace_id, t0 + 6 * DAY) is True
    assert _visitor_on_day(db, client, ws, key, 6, t0) is True
    # running again the same day sends nothing new
    grace.sync(db, a.workspace_id, t0 + 6 * DAY + timedelta(hours=5))
    db.commit()
    assert len(_mails(db, ws)) == 3
    # day 8: stopped – the visitor gets no chat, switching on again is refused; no fourth mail
    assert grace.sync(db, a.workspace_id, t0 + 8 * DAY) == "stopped"
    db.commit()
    assert grace.subscription_paid(db, a.workspace_id, t0 + 8 * DAY) is False
    assert len(_mails(db, ws)) == 3
    assert _visitor_on_day(db, client, ws, key, 8) is False
    assert "subscription_required" in _settings(api, tok, ws)["unavailable_reasons"]
    assert client.post(f"{PUB}/{key}/conversations", json={"host_origin": SITE},
                       headers={"origin": "http://localhost:8000"}).json()["code"] == "webchat_unavailable"


def test_a_new_card_ends_the_grace(api, client, db, two_workspaces, card_payment, ai_fake, monkeypatch):  # noqa: F811
    tok, ws, key = _live(api, db, two_workspaces)
    stripe._payment_state(db, uuid.UUID(ws), failed=True)
    db.commit()
    assert _visitor_on_day(db, client, ws, key, 8) is False                  # past the grace: stopped
    # the owner saves a new card at Stripe (checkout.session.completed → save_card_from_setup_intent)
    cus = db.get(BillingAccount, uuid.UUID(ws)).stripe_customer_id
    replies = {"GET /setup_intents/seti_1": {"metadata": {"workspace_id": ws}, "payment_method": "pm_new",
                                             "status": "succeeded", "customer": cus},
               "GET /payment_methods/pm_new": {"card": {"brand": "visa", "last4": "1881", "exp_month": 4, "exp_year": 2031}}}
    monkeypatch.setattr(stripe, "request", lambda method, path, data=None, **kw: replies.get(f"{method} {path}", {}))
    assert stripe.save_card_from_setup_intent(db, "seti_1") is not None
    db.commit()
    db.expire_all()
    a = db.get(BillingAccount, uuid.UUID(ws))
    assert a.payment_method_id == "pm_new" and a.payment_failed_at is None and a.unpaid_since is None and a.grace_mails == 0
    assert _visitor(client, key) is True
    assert api.get(tok, f"/workspaces/{ws}/billing/account").json()["subscription"]["paid"] is True


def test_an_expired_card_starts_the_grace_and_a_paid_invoice_ends_a_failed_payment(api, client, db, two_workspaces,
                                                                                      card_payment, ai_fake):  # noqa: F811
    tok, ws, key = _live(api, db, two_workspaces)
    now = datetime.now(UTC)
    _card(db, ws, exp=f"{(now.month - 2) % 12 + 1:02d}/{(now.year - 1) % 100:02d}")  # last year
    assert grace.run_due(db, now) >= 1
    a = db.get(BillingAccount, uuid.UUID(ws))
    assert a.unpaid_since is not None and _mails(db, ws) == ["grace_0"]
    assert api.get(tok, f"/workspaces/{ws}/billing/account").json()["subscription"]["card_expired"] is True
    assert _visitor(client, key) is True
    # a failed payment that Stripe later collects (invoice.paid) is paid again
    _card(db, ws)
    stripe._payment_state(db, uuid.UUID(ws), failed=True)
    stripe._payment_state(db, uuid.UUID(ws), failed=False)
    db.commit()
    db.expire_all()
    assert db.get(BillingAccount, uuid.UUID(ws)).unpaid_since is None


def test_never_paid_gets_no_grace(api, client, db, two_workspaces, card_payment, ai_fake):  # noqa: F811
    tok, ws = two_workspaces["tok_a"], two_workspaces["ws_a"]
    _approve(api, tok, ws)
    api.subscribe(tok, ws)                         # confirmed, but card payment is set up and there is no card
    assert grace.sync(db, uuid.UUID(ws)) in ("never_paid",)
    _card(db, ws, exp="01/20")                     # an expired card from the start: never paid either
    assert grace.sync(db, uuid.UUID(ws)) == "never_paid"
    db.commit()
    assert grace.subscription_paid(db, uuid.UUID(ws)) is False
    assert _enable(api, tok, ws).json()["code"] == "subscription_required"
    assert _mails(db, ws) == []


def test_grace_mails_in_8_languages():
    ends = datetime(2026, 11, 19, 12, tzinfo=UTC)
    seen = set()
    for lang in ("da", "en", "de", "es", "fr", "it", "no", "sv"):
        for kind in ("grace_0", "grace_1", "grace_2"):
            m = customer_mails.build(kind, lang=lang, audience="erhverv", amount_minor=0, currency="DKK",
                                     link="https://dialogbot.app/app/konto/abonnement", date=ends)
            assert "19.11.2026" in m.subject + m.heading + " ".join(m.paragraphs), (lang, kind)
            assert "{" not in m.subject + m.heading + " ".join(m.paragraphs), (lang, kind)
            seen.add(m.subject)
    assert len(seen) == 24
    assert "Opdatér betalingskortet" in customer_mails.build("grace_0", lang="da", audience="erhverv", amount_minor=0,
                                                             currency="DKK", link="x", date=ends).subject

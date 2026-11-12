"""Neither the website chat nor the phone goes live without a paid subscription (Fürster 12/11 09:25: «Skal chatten kunne
gå live uden betalt abonnement?» – «nej»).

«Betalt» (agreements.subscription_paid, the same rule as the web's billingState): a confirmed agreement plus a card on
file – or only the confirmed agreement when card payment (Stripe) is not set up. Enforced in the backend: turning the
chat on, every public widget endpoint a visitor uses, and the phone's activation. Before that the owner may try the
chat in the app's preview (nothing stored, no visitor sees it)."""
from __future__ import annotations

import uuid

from sqlalchemy import select

from app.models import AiUsage, BillingAccount, Conversation, WebchatSettings
from app.modules.billing import stripe
from tests.qa.test_qa_voice_R02 import _knowledge, no_network  # noqa: F401
from tests.test_telephony_platform import _approve_docs, _hook, _ready, _run_jobs, fake  # noqa: F401
from tests.test_webchat import PUB, SITE, _approve, _enable, _say, _settings, _start
from tests.test_webchat import fake as ai_fake  # noqa: F401


def _card(db, ws: str) -> None:
    a = db.get(BillingAccount, uuid.UUID(ws)) or BillingAccount(workspace_id=uuid.UUID(ws))
    a.payment_method_id, a.card_brand, a.card_last4 = "pm_test_gate", "visa", "4242"
    db.add(a)
    db.commit()


def test_chat_is_not_live_for_visitors_before_the_subscription_is_paid(api, client, two_workspaces, ai_fake, db):  # noqa: F811
    t = two_workspaces
    tok, ws = t["tok_a"], t["ws_a"]
    _approve(api, tok, ws)
    # set up (domain + approved knowledge), but not paid: saved, not on
    assert _enable(api, tok, ws, enabled=False).status_code == 200
    s = _settings(api, tok, ws)
    assert s["setup_missing"] == [] and s["subscription_paid"] is False
    assert set(s["unavailable_reasons"]) == {"disabled", "subscription_required"}
    # turning it on = going live: refused, said plainly
    r = _enable(api, tok, ws)
    assert r.status_code == 409 and r.json()["code"] == "subscription_required"
    assert r.json()["message"] == "Chatten går live, når abonnementet er på plads"
    key = s["widget_key"]
    # the visitor on the customer's site gets nothing
    assert client.get(f"{PUB}/{key}/status", headers={"origin": SITE}).json() == {"available": False}
    assert _start(client, key).status_code == 409
    # the owner can try it in the preview – nothing is stored as a conversation
    p = api.post(tok, f"/workspaces/{ws}/webchat/preview", {"messages": [{"role": "user", "content": "Hvad koster afslibning?"}]})
    assert p.status_code == 200, p.text
    assert p.json()["reply"].startswith("[fake] svar på: Hvad koster afslibning?")
    assert db.scalar(select(AiUsage.purpose).where(AiUsage.workspace_id == uuid.UUID(ws))) == "webchat_preview"
    assert db.scalars(select(Conversation).where(Conversation.workspace_id == uuid.UUID(ws))).all() == []
    staff = api.add_member(tok, ws, "staff-gate@testmail.dk", "staff")
    assert api.post(staff, f"/workspaces/{ws}/webchat/preview", {"messages": [{"role": "user", "content": "hej"}]}).status_code == 403

    # paid (no Stripe here: the confirmed agreement is the payment) → it can go live and answers visitors
    api.subscribe(tok, ws)
    assert _settings(api, tok, ws)["subscription_paid"] is True
    r = _enable(api, tok, ws)
    assert r.status_code == 200, r.text
    assert r.json()["available"] is True and r.json()["unavailable_reasons"] == []
    assert client.get(f"{PUB}/{key}/status", headers={"origin": SITE}).json() == {"available": True}
    conv = _start(client, key).json()
    assert _say(client, key, conv, "Hvad koster afslibning?").json()["reply"]["text"].startswith("[fake] svar på")


def test_with_card_payment_the_card_is_part_of_paid(api, client, two_workspaces, ai_fake, db, monkeypatch):  # noqa: F811
    t = two_workspaces
    tok, ws = t["tok_a"], t["ws_a"]
    _approve(api, tok, ws)
    api.subscribe(tok, ws)
    monkeypatch.setattr(stripe, "configured", lambda: True)
    # confirmed but no card while card payment is set up: not paid
    r = _enable(api, tok, ws)
    assert r.status_code == 409 and r.json()["code"] == "subscription_required"
    _card(db, ws)
    assert _enable(api, tok, ws).status_code == 200
    key = _settings(api, tok, ws)["widget_key"]
    assert client.get(f"{PUB}/{key}/status", headers={"origin": SITE}).json() == {"available": True}


def test_a_chat_switched_on_earlier_answers_no_visitor_while_not_paid(api, client, two_workspaces, ai_fake, db):  # noqa: F811
    """A chat that was switched on before this rule (or whose payment lapsed): the public endpoints refuse visitors."""
    t = two_workspaces
    tok, ws = t["tok_a"], t["ws_a"]
    _approve(api, tok, ws)
    assert _enable(api, tok, ws, enabled=False).status_code == 200
    s = db.scalar(select(WebchatSettings).where(WebchatSettings.workspace_id == uuid.UUID(ws)))
    s.enabled = True
    db.commit()
    key = s.widget_key
    assert client.get(f"{PUB}/{key}/status", headers={"origin": SITE}).json() == {"available": False}
    frame = client.get(f"{PUB}/{key}/frame", headers={"referer": SITE + "/"})
    assert '&quot;available&quot;: false' in frame.text
    assert _start(client, key).status_code == 409
    # saving the greeting of an already-on chat is not refused (the visitors are, until it is paid)
    assert _enable(api, tok, ws, greeting="Hej fra Fjord").status_code == 200


def test_phone_activation_needs_a_paid_subscription(client, api, two_workspaces, fake, no_network, db, monkeypatch):  # noqa: F811
    t = two_workspaces
    tok, ws = t["tok_a"], t["ws_a"]
    base = f"/workspaces/{ws}/telephony"
    _ready(api, tok, ws)  # number verified + the agreement confirmed (the number can only be connected after that)
    assert api.post(tok, f"{base}/connect").status_code == 200
    _approve_docs(api, ws)
    _run_jobs()
    _knowledge(api, tok, ws)
    dest = api.get(tok, base).json()["destination"]["e164"]
    assert api.post(tok, f"{base}/tests", {"called_business_number": True}).status_code == 200
    caller = "+4540404040"
    _hook(client, {"type": "assistant-request", "call": {"id": "c-gate", "customer": {"number": caller}}, "phoneNumber": {"number": dest}})
    rep = {"type": "end-of-call-report", "call": {"id": "c-gate", "customer": {"number": caller}},
           "phoneNumber": {"number": dest}, "startedAt": "2026-11-10T08:00:00Z", "endedAt": "2026-11-10T08:01:30Z",
           "artifact": {"messages": [{"role": "user", "message": "Test."}, {"role": "assistant", "message": "Hej."}]}}
    assert _hook(client, rep).json()["outcome"] == "applied"
    assert api.get(tok, base).json()["test"]["status"] == "passed"
    # card payment set up and no card: the number does not go live
    monkeypatch.setattr(stripe, "configured", lambda: True)
    assert api.get(tok, base).json()["subscription_paid"] is False
    r = api.post(tok, f"{base}/activate")
    assert r.status_code == 409 and r.json()["code"] == "subscription_required", r.text
    assert api.get(tok, base).json()["active"] is False
    _card(db, ws)
    assert api.get(tok, base).json()["subscription_paid"] is True
    r = api.post(tok, f"{base}/activate")
    assert r.status_code == 200, r.text
    assert r.json()["active"] is True

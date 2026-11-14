"""Probe (verifier 13/11 b, F-FIX20-01 bug class): after the 7 days' grace the grace mail says «I morgen stopper chat
og telefon». Does the PHONE stop answering like the chat does?"""
import uuid
from datetime import UTC, datetime, timedelta

from app.models import BillingAccount
from app.modules.billing import grace, stripe
from tests.qa.test_qa_voice_R02 import _knowledge, no_network  # noqa: F401
from tests.test_live_gate import _card
from tests.test_telephony_platform import _approve_docs, _hook, _ready, _run_jobs, fake  # noqa: F401


def test_probe_phone_after_grace(client, api, two_workspaces, fake, no_network, db, monkeypatch):  # noqa: F811
    t = two_workspaces
    tok, ws = t["tok_a"], t["ws_a"]
    base = f"/workspaces/{ws}/telephony"
    _ready(api, tok, ws)
    assert api.post(tok, f"{base}/connect").status_code == 200
    _approve_docs(api, ws)
    _run_jobs()
    _knowledge(api, tok, ws)
    dest = api.get(tok, base).json()["destination"]["e164"]
    assert api.post(tok, f"{base}/tests", {"called_business_number": True}).status_code == 200
    _hook(client, {"type": "assistant-request", "call": {"id": "c-g", "customer": {"number": "+4540404040"}}, "phoneNumber": {"number": dest}})
    rep = {"type": "end-of-call-report", "call": {"id": "c-g", "customer": {"number": "+4540404040"}},
           "phoneNumber": {"number": dest}, "startedAt": "2026-11-10T08:00:00Z", "endedAt": "2026-11-10T08:01:30Z",
           "artifact": {"messages": [{"role": "user", "message": "Test."}, {"role": "assistant", "message": "Hej."}]}}
    _hook(client, rep)
    monkeypatch.setattr(stripe, "configured", lambda: True)
    _card(db, ws)
    assert api.post(tok, f"{base}/activate").status_code == 200
    # the card is removed; it stopped being paid 10 days ago (grace = 7 days)
    a = db.get(BillingAccount, uuid.UUID(ws))
    a.payment_method_id = None
    a.first_paid_at = datetime.now(UTC) - timedelta(days=40)
    a.unpaid_since = datetime.now(UTC) - timedelta(days=10)
    db.commit()
    print("grace.sync:", grace.sync(db, uuid.UUID(ws)), "subscription_paid:", grace.subscription_paid(db, uuid.UUID(ws)))
    db.commit()
    print("GET telephony active:", api.get(tok, base).json().get("active"), "subscription_paid:", api.get(tok, base).json().get("subscription_paid"))
    r = _hook(client, {"type": "assistant-request", "call": {"id": "c-after", "customer": {"number": "+4541414141"}},
                       "phoneNumber": {"number": dest}})
    body = r.json()
    print("assistant-request after grace:", r.status_code, "keys:", sorted(body)[:5], "error:", body.get("error"),
          "firstMessage:", (body.get("assistant") or {}).get("firstMessage", "")[:80])

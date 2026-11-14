"""F-VER1113B-03: after the 7 days' grace the phone stops answering like the chat does (grace mail 3 promises «I morgen
stopper chat og telefon»); within the grace it still answers."""
import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.models import BillingAccount
from app.modules.billing import grace, stripe
from tests.qa.test_qa_voice_R02 import _knowledge, no_network  # noqa: F401
from tests.test_live_gate import _card
from tests.test_telephony_platform import _approve_docs, _hook, _ready, _run_jobs, fake  # noqa: F401


@pytest.mark.parametrize(("days", "expect_live"), [(3, True), (10, False)])
def test_phone_stops_after_grace(client, api, two_workspaces, fake, no_network, db, monkeypatch,  # noqa: F811
                                 days, expect_live):
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
    _hook(client, {"type": "assistant-request", "call": {"id": "c-g", "customer": {"number": "+4540404040"}},
                   "phoneNumber": {"number": dest}})
    _hook(client, {"type": "end-of-call-report", "call": {"id": "c-g", "customer": {"number": "+4540404040"}},
                   "phoneNumber": {"number": dest}, "startedAt": "2026-11-10T08:00:00Z", "endedAt": "2026-11-10T08:01:30Z",
                   "artifact": {"messages": [{"role": "user", "message": "Test."}, {"role": "assistant", "message": "Hej."}]}})
    monkeypatch.setattr(stripe, "configured", lambda: True)
    _card(db, ws)
    assert api.post(tok, f"{base}/activate").status_code == 200

    a = db.get(BillingAccount, uuid.UUID(ws))
    a.payment_method_id = None  # the card is removed
    a.first_paid_at = datetime.now(UTC) - timedelta(days=40)
    a.unpaid_since = datetime.now(UTC) - timedelta(days=days)
    db.commit()
    assert grace.sync(db, uuid.UUID(ws)) == ("grace" if expect_live else "stopped")
    db.commit()

    r = _hook(client, {"type": "assistant-request", "call": {"id": f"c-after-{days}", "customer": {"number": "+4541414141"}},
                       "phoneNumber": {"number": dest}})
    assert r.status_code == 200
    meta = (r.json().get("assistant") or {}).get("metadata") or {}
    assert bool(meta.get("not_active")) is (not expect_live), r.json()

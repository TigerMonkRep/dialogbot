"""Audit 2026-11-12 · F-AUD26-02-P06: the public «Ring mig op nu» door rings any Danish number typed in, day and night.

Fürster decided 12/11 that Dialogbot's own demo calls ring at once, 24/7 (not a defect). What this file pins down is
the consequence nobody decided: the number is never proven to belong to the visitor (no SMS code, no per-client
limit), so one anonymous client can make Peter ring other people's numbers at 03:00 – up to SALES_MAX_CALLS_PER_HOUR
different numbers an hour, every hour. The consent box is ticked by the requester, not by the owner of the number.

`test_one_client_rings_many_strangers_at_night` documented the behaviour on 14edd47 (five calls at 03:00); since the
fix (Fürster 12/11: «A, SMS-kode først», app/modules/sales/verification.py) it proves the opposite: without the code
sent to each number nobody is rung, a guessed or reused token rings nobody, and one client runs into the per-IP limit
on codes. `test_unproven_numbers_are_not_rung_in_bulk_at_night` was xfail(strict) until the decision; the fix flipped it.
"""
from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from app.models import DemoCall
from tests.test_sales_demo_calls import _unproven, _web, last_code, sales  # noqa: F401 – the fixture

CPH = ZoneInfo("Europe/Copenhagen")
THU_0300 = datetime(2026, 11, 12, 3, 0, tzinfo=CPH).astimezone(UTC)
STRANGERS = ["20 30 40 51", "20 30 40 52", "20 30 40 53", "20 30 40 54", "20 30 40 55"]


def _ring_all(client, sales):  # noqa: F811
    sales["clock"][0] = THU_0300
    # the attacker types strangers' numbers and ticks the box – but never sees the SMS sent to them
    return [_unproven(client, phone=p, name="X", company="Y", consent_version="demo-call-web-v2") for p in STRANGERS]


def test_one_client_rings_many_strangers_at_night(client, sales, db):  # noqa: F811
    """Fixed: one anonymous client can no longer make Peter ring strangers at 03:00."""
    # 1. straight to the call, as before the fix: refused, nobody rung
    rs = _ring_all(client, sales)
    assert [r.status_code for r in rs] == [422] * len(STRANGERS)
    assert {r.json()["code"] for r in rs} == {"verification_required"}
    # 2. asks for codes to the strangers: SMS go to the strangers (who did not ask, and are told to ignore it) –
    #    the client never sees them, so a guessed code and a made-up token ring nobody
    sales["clock"][0] = THU_0300
    sent = [client.post("/api/v1/demo-call/code", json={"phone": p, "consent": True}) for p in STRANGERS]
    assert [r.status_code for r in sent] == [202] * len(STRANGERS)
    for r in sent:
        v = client.post("/api/v1/demo-call/verify", json={"verification_id": r.json()["verification_id"],
                                                          "code": "000000"})
        assert v.status_code == 422 and v.json()["code"] == "code_invalid"
    forged = _unproven(client, phone=STRANGERS[0], verification_token="gæt-et-token")
    assert forged.status_code == 409 and forged.json()["code"] == "verification_invalid"
    # 3. ... and the sixth number from the same client is refused before any SMS (per-IP limit)
    sixth = client.post("/api/v1/demo-call/code", json={"phone": "20 30 40 56", "consent": True})
    assert sixth.status_code == 429 and sixth.json()["code"] == "sms_rate_limited"
    # 4. a token proves one number: it cannot be spent on another, and only once
    me = "+4520304055"
    v = client.post("/api/v1/demo-call/verify", json={"verification_id": sent[-1].json()["verification_id"],
                                                      "code": last_code(me)})
    token = v.json()["verification_token"]
    other = _unproven(client, phone=STRANGERS[0], verification_token=token)
    assert other.status_code == 409 and other.json()["code"] == "verification_invalid"
    assert _unproven(client, phone=STRANGERS[-1], verification_token=token).status_code == 202
    again = _unproven(client, phone=STRANGERS[-1], verification_token=token)
    assert again.status_code == 409 and again.json()["code"] == "verification_invalid"
    assert len(sales["calls"]) == 1 and sales["calls"][0]["customer"]["number"] == me  # only the proven number
    assert db.query(DemoCall).filter(DemoCall.status == "calling").count() == 1


def test_unproven_numbers_are_not_rung_in_bulk_at_night(client, sales, db):  # noqa: F811
    _ring_all(client, sales)
    assert len(sales["calls"]) <= 1

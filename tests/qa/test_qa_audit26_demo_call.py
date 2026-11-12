"""Audit 2026-11-12 · F-AUD26-02-P06: the public «Ring mig op nu» door rings any Danish number typed in, day and night.

Fürster decided 12/11 that Dialogbot's own demo calls ring at once, 24/7 (not a defect). What this file pins down is
the consequence nobody decided: the number is never proven to belong to the visitor (no SMS code, no per-client
limit), so one anonymous client can make Peter ring other people's numbers at 03:00 – up to SALES_MAX_CALLS_PER_HOUR
different numbers an hour, every hour. The consent box is ticked by the requester, not by the owner of the number.

`test_one_client_rings_many_strangers_at_night` documents today's behaviour (it passes on 14edd47).
`test_unproven_numbers_are_not_rung_in_bulk_at_night` is the minimum any of the options in the finding must satisfy;
it is xfail(strict) until Fürster picks one, so the fix flips it.
"""
from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest

from app.models import DemoCall
from tests.test_sales_demo_calls import _web, sales  # noqa: F401 – the fixture

CPH = ZoneInfo("Europe/Copenhagen")
THU_0300 = datetime(2026, 11, 12, 3, 0, tzinfo=CPH).astimezone(UTC)
STRANGERS = ["20 30 40 51", "20 30 40 52", "20 30 40 53", "20 30 40 54", "20 30 40 55"]


def _ring_all(client, sales):  # noqa: F811
    sales["clock"][0] = THU_0300
    return [_web(client, phone=p, name="X", company="Y", consent_version="demo-call-web-v2") for p in STRANGERS]


def test_one_client_rings_many_strangers_at_night(client, sales, db):  # noqa: F811
    rs = _ring_all(client, sales)
    assert [r.status_code for r in rs] == [202] * len(STRANGERS)
    assert len(sales["calls"]) == len(STRANGERS)  # five real outbound calls at 03:00, one anonymous client
    assert db.query(DemoCall).filter(DemoCall.status == "calling").count() == len(STRANGERS)


@pytest.mark.xfail(strict=True, reason="F-AUD26-02-P06 needs-decision: no proof of number ownership on /demo-call")
def test_unproven_numbers_are_not_rung_in_bulk_at_night(client, sales, db):  # noqa: F811
    _ring_all(client, sales)
    assert len(sales["calls"]) <= 1

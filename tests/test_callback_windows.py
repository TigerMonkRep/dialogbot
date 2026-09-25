"""Callback windows: offered in local time, skip expired windows and weekends, and turn into the
lead's callback period and the task's due time."""
from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.modules.leads import callback

TZ = "Europe/Copenhagen"


def _keys(now):
    return [o["key"] for o in callback.options(TZ, now)]


def test_options_follow_local_time_and_weekdays():
    # Thursday 24 Sep 2026, 09:30 local (07:30 UTC)
    assert _keys(datetime(2026, 9, 24, 7, 30, tzinfo=UTC)) == ["asap", "today_am", "today_pm", "next_am", "next_pm"]
    # 11:30 local: less than an hour of the morning left → no "today_am"
    assert "today_am" not in _keys(datetime(2026, 9, 24, 9, 30, tzinfo=UTC))
    # Friday evening: next working day is Monday, labelled by weekday
    opts = callback.options(TZ, datetime(2026, 9, 25, 18, 0, tzinfo=UTC))
    assert [o["key"] for o in opts] == ["asap", "next_am", "next_pm"]
    assert opts[1]["label"] == "Mandag formiddag (8–12)"
    # Saturday: no "today" at all
    assert _keys(datetime(2026, 9, 26, 8, 0, tzinfo=UTC)) == ["asap", "next_am", "next_pm"]


def test_resolve_to_utc_window():
    now = datetime(2026, 9, 24, 7, 30, tzinfo=UTC)  # 09:30 CEST
    frm, to, label = callback.resolve("today_am", TZ, now)
    assert frm == now and to == datetime(2026, 9, 24, 10, 0, tzinfo=UTC) and label == "I dag formiddag (8–12)"
    frm, to, _ = callback.resolve("next_pm", TZ, now)
    assert (frm, to) == (datetime(2026, 9, 25, 10, 0, tzinfo=UTC), datetime(2026, 9, 25, 14, 0, tzinfo=UTC))
    assert callback.resolve("asap", TZ, now) is None
    with pytest.raises(ValueError):
        callback.resolve("today_am", TZ, datetime(2026, 9, 24, 10, 30, tzinfo=UTC))

"""A2: the OnlineBooq playbook against the local clone (not a real site)."""
from __future__ import annotations

import pytest

from browser_worker import playbooks
from browser_worker.errors import ApprovalRequired, RunFailed
from browser_worker.playbooks import onlinebooq
from browser_worker.playbooks.common import NoAvailability, PlaybookMiss, PlaybookUnsupported, date_pattern, parse_time
from browser_worker.session import BrowserSession

GOAL = {
    "intent": "book", "service": "Herreklip",
    "preferred_windows": [{"date": "2026-11-10", "from": "10:00", "to": "12:00"}],
    "contact": {"name": "Mette Hansen", "phone": "+4512345678", "mail": "mette@example.dk"},
}


def session(workdir, **kw):
    kw.setdefault("record_video", False)
    return BrowserSession(allowed_domains=["127.0.0.1"], workdir=workdir, **kw)


def start(site, variant="booking"):
    return f"{site.url}/{variant}/ydelse.html"


def test_registry():
    assert playbooks.get("onlinebooq") is onlinebooq
    assert playbooks.get("unknown") is None
    assert playbooks.engines() == ["onlinebooq"]


def test_prepare_reaches_filled_but_not_confirmed(site, workdir):
    with session(workdir) as s:
        prepared = onlinebooq.prepare(s, GOAL, start(site))
    ba = prepared.before_after
    assert ba["service"] == "Herreklip"
    assert ba["staff"] == "Ingen præference"
    assert ba["date"] == "tirsdag 10. november 2026"
    assert ba["time"] == "10:30"
    assert ba["price"] == "350 kr."
    assert ba["name"] == "Mette Hansen"
    assert ba["engine"] == "onlinebooq" and ba["intent"] == "book"
    assert not any("kvittering" in h for h in site.hits)  # nothing was confirmed on the site


def test_confirm_without_approval_stops_with_awaiting_approval(site, workdir):
    with session(workdir) as s:
        onlinebooq.prepare(s, GOAL, start(site))
        with pytest.raises(ApprovalRequired):
            onlinebooq.confirm(s)
        assert not any("kvittering" in h for h in site.hits)
        # the live session can still be approved and continue from the very same page
        s.approved = True
        result = onlinebooq.confirm(s)
    assert result["confirmed"] is True
    assert result["reference"] == "OB-20261110-0042"
    assert "Herreklip" in result["receipt_text"]
    assert any("kvittering" in h for h in site.hits)
    assert sum("kvittering" in h for h in site.hits) == 1  # exactly one confirming click


def test_replay_in_a_fresh_approved_session_reaches_the_same_point(site, workdir):
    """TTL expired: a new session replays the playbook to the same summary and confirms."""
    with session(workdir) as s1:
        first = onlinebooq.prepare(s1, GOAL, start(site)).before_after
    with session(workdir / "replay", approved=True) as s2:
        again = onlinebooq.prepare(s2, GOAL, start(site)).before_after
        result = onlinebooq.confirm(s2)
    assert again == first
    assert result["confirmed"] is True


def test_second_window_is_tried_when_the_first_has_no_matching_time(site, workdir):
    goal = dict(GOAL, preferred_windows=[
        {"date": "2026-11-10", "from": "15:00", "to": "17:00"},   # 10 Nov has 09:00, 10:30, 14:00 only
        {"date": "2026-11-11", "from": "09:00", "to": "09:30"},
    ])
    with session(workdir) as s:
        ba = onlinebooq.prepare(s, goal, start(site)).before_after
    assert "11. november" in ba["date"] and ba["time"] == "09:00"


def test_no_availability_carries_what_was_found(site, workdir):
    goal = dict(GOAL, preferred_windows=[{"date": "2026-11-10", "from": "18:00", "to": "20:00"}])
    with session(workdir) as s, pytest.raises(NoAvailability) as e:
        onlinebooq.prepare(s, goal, start(site))
    found = e.value.found
    assert found["times_seen"]["2026-11-10"] == ["09:00", "10:30", "14:00"]
    assert any("10. november" in d for d in found["dates_seen"])
    assert found["service"] == "Herreklip"

    goal = dict(GOAL, preferred_windows=[{"date": "2026-12-24"}])
    with session(workdir / "b") as s, pytest.raises(NoAvailability) as e:
        onlinebooq.prepare(s, goal, start(site))
    assert e.value.found["dates_seen"]


def test_unknown_service_is_a_playbook_miss_with_the_services_seen(site, workdir):
    with session(workdir) as s, pytest.raises(PlaybookMiss) as e:
        onlinebooq.prepare(s, dict(GOAL, service="Permanent"), start(site))
    assert e.value.reason == "service_not_found"
    assert any("Herreklip" in n for n in e.value.found["services"])


@pytest.mark.parametrize("intent", ["flyt", "aflys"])
def test_other_intents_are_not_automated_in_v1(site, workdir, intent):
    with session(workdir) as s, pytest.raises(PlaybookUnsupported):
        onlinebooq.prepare(s, dict(GOAL, intent=intent), start(site))


def test_a_selector_mismatch_is_fixed_in_the_config_block_only(site, workdir, monkeypatch):
    monkeypatch.setitem(onlinebooq.SELECTORS, "confirm", r"^reserver tiden$")  # a real page words it differently
    with session(workdir) as s:
        # the summary page is no longer recognised as such, so the playbook cannot finish
        with pytest.raises(PlaybookMiss):
            onlinebooq.prepare(s, GOAL, start(site))
    monkeypatch.undo()
    with session(workdir / "ok") as s:
        assert onlinebooq.prepare(s, GOAL, start(site)).before_after["service"] == "Herreklip"


def test_innocent_next_button_that_books_is_caught_by_the_safety_net(site, workdir):
    with session(workdir) as s, pytest.raises(RunFailed) as e:
        onlinebooq.prepare(s, GOAL, start(site, "booking-sneaky"))
    assert e.value.error_code == "unexpected_commit"
    assert e.value.details["screenshot_file"]


def test_date_and_time_helpers():
    rx = date_pattern("2026-11-10")
    for label in ("Tirsdag 10. november 2026", "10 Nov", "10-11-2026", "10/11/26", "2026-11-10", "10. nov"):
        assert rx.search(label), label
    for label in ("Onsdag 11. november 2026", "110. november", "10. december"):
        assert not rx.search(label), label
    assert parse_time("09:00") == (9, 0) and parse_time("9.30 - 10.00") == (9, 30) and parse_time("Herreklip") is None

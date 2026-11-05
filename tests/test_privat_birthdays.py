"""Dialogbot Privat, the Fødselsdage app: birthdays the user tells the assistant, a reminder once a year (push or
e-mail), never before 08:00, never for an account that has the app off."""
from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from app.models import OutboxEvent, PrivateBirthday
from app.modules.privat import birthdays, rules
from tests.privat_fixtures import WED_10

# WED_10 = Wednesday 4 November 2026, 10:00 in Copenhagen


@pytest.mark.parametrize("text,expected", [
    ("14. marts", (3, 14, None)),
    ("14 mar", (3, 14, None)),
    ("14.03.1946", (3, 14, 1946)),
    ("14/3", (3, 14, None)),
    ("1946-03-14", (3, 14, 1946)),
    ("03-14", (3, 14, None)),
    ("29. februar", (2, 29, None)),
    ("29.02.1947", None),            # not a leap year
    ("31. april", None),
    ("1. januar 2030", None),        # in the future
    ("i marts", None),
    ("", None),
])
def test_parse_date(text, expected):
    assert birthdays.parse_date(text) == expected


def _b(month, day, year=None, days=7):
    return PrivateBirthday(name="Mor", name_key="mor", month=month, day=day, year=year, remind_days_before=days)


def test_next_date_age_and_29_february():
    today = date(2026, 11, 4)
    assert birthdays.next_date(_b(11, 4), today) == date(2026, 11, 4)          # today
    assert birthdays.next_date(_b(11, 3), today) == date(2027, 11, 3)          # passed: next year
    assert birthdays.next_date(_b(2, 29), today) == date(2027, 2, 28)          # no 29 February in 2027
    assert birthdays.next_date(_b(2, 29), date(2027, 3, 1)) == date(2028, 2, 29)
    assert birthdays.turns(_b(3, 14, 1946), date(2027, 3, 14)) == 81
    assert birthdays.summary(_b(11, 11, 1946), today) == "Mor fylder 80 om 7 dage (onsdag 11. november)"
    assert birthdays.summary(_b(11, 4), today) == "Mor har fødselsdag i dag"
    assert birthdays.summary(_b(11, 5), today) == "Mor har fødselsdag i morgen (torsdag 5. november)"


def _enable(api, tok):
    r = api.post(tok, "/privat/addons/foedselsdage/enable")
    assert r.status_code == 200, r.text


def test_needs_a_plan_and_the_app(api, pv):
    free = pv.account("fri@testmail.dk", trial=False)
    assert api.post(free, "/privat/addons/foedselsdage/enable").json()["code"] == "needs_plan"
    tok = pv.account("mette@testmail.dk")
    r = api.get(tok, "/privat/birthdays")
    assert r.status_code == 403 and r.json()["code"] == "addon_disabled"
    out = pv.say(tok, "Mors fødselsdag er den 14. marts")
    assert any(m["kind"] == "addon" and m.get("addon_key") == "foedselsdage" for m in out["messages"]), out


def test_chat_saves_lists_and_removes(api, pv, db):
    tok = pv.account("mette@testmail.dk")
    _enable(api, tok)
    out = pv.say(tok, "Mors fødselsdag er den 14. marts og Ole har fødselsdag den 10. november – mind mig om det en uge før")
    assert out["messages"][-1]["text"] == "Gemt: Mor: 14. marts; Ole: 10. november. Jeg minder dig om det 7 dage før."
    items = api.get(tok, "/privat/birthdays").json()["items"]
    assert [(b["name"], b["date_text"], b["days_until"]) for b in items] == [("Ole", "10. november", 6), ("Mor", "14. marts", 130)]
    out = pv.say(tok, "Hvem har fødselsdag snart?")
    assert out["messages"][-1]["text"] == "- Ole har fødselsdag om 6 dage (tirsdag 10. november)"
    # the same name again changes the date, it does not add a second Mor
    pv.say(tok, "Mors fødselsdag er den 15. marts")
    assert [b["date_text"] for b in api.get(tok, "/privat/birthdays").json()["items"] if b["name"] == "Mor"] == ["15. marts"]
    out = pv.say(tok, "Slet Oles fødselsdag")
    assert out["messages"][-1]["text"] == "Oles fødselsdag er fjernet."
    assert [b["name"] for b in api.get(tok, "/privat/birthdays").json()["items"]] == ["Mor"]


def test_api_add_change_and_isolation(api, pv):
    tok = pv.account("mette@testmail.dk")
    _enable(api, tok)
    r = api.post(tok, "/privat/birthdays", {"name": "Mormor", "date": "03.03.1946", "remind_days_before": 3})
    assert r.status_code == 200 and r.json()["created"] is True and r.json()["turns"] == 81
    bid = r.json()["id"]
    assert api.post(tok, "/privat/birthdays", {"name": "Mormor", "date": "31. februar"}).status_code == 422
    r = api.patch(tok, f"/privat/birthdays/{bid}", {"remind_days_before": 0})
    assert r.status_code == 200 and r.json()["remind_days_before"] == 0
    ole = pv.account("ole@testmail.dk", name="Ole Berg")
    _enable(api, ole)
    assert api.patch(ole, f"/privat/birthdays/{bid}", {"remind_days_before": 1}).status_code == 404
    assert api.delete(ole, f"/privat/birthdays/{bid}").status_code == 404
    assert api.get(ole, "/privat/birthdays").json()["items"] == []
    assert api.delete(tok, f"/privat/birthdays/{bid}").status_code == 204


def _mails(db) -> list[OutboxEvent]:
    db.expire_all()
    return db.query(OutboxEvent).filter(OutboxEvent.dedupe_key.like("privat-notify:birthday:%")).all()


def test_reminder_once_a_year_from_eight_and_only_with_the_app(api, pv, db):
    tok = pv.account("mette@testmail.dk")
    _enable(api, tok)
    api.post(tok, "/privat/birthdays", {"name": "Ole", "date": "11. november", "remind_days_before": 7})
    api.post(tok, "/privat/birthdays", {"name": "Mor", "date": "14. marts"})
    early = datetime(2026, 11, 4, 6, 30, tzinfo=UTC)        # 07:30 in Copenhagen
    assert birthdays.send_due(db, early) == 0
    assert birthdays.send_due(db, WED_10) == 1               # Ole: in 7 days; Mor: not yet
    db.commit()
    [ev] = _mails(db)
    assert ev.payload["email"]["subject"] == "Fødselsdag: Ole"
    assert birthdays.send_due(db, WED_10) == 0               # once
    later = datetime(2026, 11, 8, 9, 0, tzinfo=UTC)
    assert birthdays.send_due(db, later) == 0                # still the same birthday
    # a missed reminder (worker down) still comes, up to the day itself
    api.post(tok, "/privat/birthdays", {"name": "Bo", "date": "5. november", "remind_days_before": 14})
    assert birthdays.send_due(db, WED_10) == 1
    next_year = datetime(2027, 11, 4, 9, 0, tzinfo=UTC)
    assert birthdays.send_due(db, next_year) == 2            # next year again: Ole (in 7 days) and Bo (tomorrow)
    # app off: nothing
    api.post(tok, "/privat/birthdays", {"name": "Eva", "date": "6. november", "remind_days_before": 3})
    assert api.post(tok, "/privat/addons/foedselsdage/disable").status_code == 200
    assert birthdays.send_due(db, WED_10) == 0


def test_the_worker_schedule_sends_and_commits(api, pv, db, monkeypatch):
    from app.worker import runner

    tok = pv.account("mette@testmail.dk")
    _enable(api, tok)
    api.post(tok, "/privat/birthdays", {"name": "Ole", "date": "8. november"})
    monkeypatch.setattr(rules, "now", lambda: WED_10)
    runner.run_schedules()
    assert len(_mails(db)) == 1
    assert db.query(PrivateBirthday).filter_by(name="Ole").one().last_reminded_for == date(2026, 11, 8)

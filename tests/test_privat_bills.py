"""Dialogbot Privat, the Regninger app: bills the user tells the assistant about, a reminder before each due date,
this month's overview. Dialogbot never pays and never sees the bank."""
from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from app.models import OutboxEvent, PrivateBill
from app.modules.privat import bills
from tests.privat_fixtures import WED_10

# WED_10 = Wednesday 4 November 2026, 10:00 in Copenhagen


@pytest.mark.parametrize("text,expected", [
    ("640 kr.", 64000), ("640", 64000), ("1.250,50 kr", 125050), ("1250.5", 125050), ("12.500", 1250000),
    (99, 9900), ("0", 0), ("gratis", None), ("-5", None), ("", None), (None, None),
])
def test_parse_amount(text, expected):
    assert bills.parse_amount(text) == expected


def test_money():
    assert bills.money(64000) == "640 kr." and bills.money(125050) == "1.250,50 kr." and bills.money(None) == ""


def _bill(freq, nxt, anchor):
    return PrivateBill(name="Husleje", name_key="husleje", frequency=freq, next_due=nxt, anchor_day=anchor,
                       remind_days_before=3)


def test_first_due_and_roll_keep_the_31st():
    today = date(2026, 11, 4)
    assert bills.first_due(today, due_day=1) == (date(2026, 12, 1), 1)
    assert bills.first_due(today, due_day=4) == (date(2026, 11, 4), 4)
    assert bills.first_due(today, due_day=31) == (date(2026, 11, 30), 31)          # November has 30 days
    assert bills.first_due(today, due_date="2027-01-15") == (date(2027, 1, 15), 15)
    b = _bill("monthly", date(2026, 1, 31), 31)
    assert bills.roll(b, date(2026, 2, 1)) and b.next_due == date(2026, 2, 28)
    assert bills.roll(b, date(2026, 3, 1)) and b.next_due == date(2026, 3, 31)     # back on the 31st
    q = _bill("quarterly", date(2026, 10, 1), 1)
    assert bills.roll(q, today) and q.next_due == date(2027, 1, 1)
    once = _bill("once", date(2026, 10, 1), 1)
    assert not bills.roll(once, today) and once.next_due == date(2026, 10, 1)       # a one-off bill stays


def _enable(api, tok):
    r = api.post(tok, "/privat/addons/regninger/enable")
    assert r.status_code == 200, r.text


def test_needs_the_app(api, pv):
    tok = pv.account("mette@testmail.dk")
    r = api.get(tok, "/privat/bills")
    assert r.status_code == 403 and r.json()["code"] == "addon_disabled"
    out = pv.say(tok, "Mind mig om regningen for Forsikring den 1. hver måned – den er 640 kr.")
    assert any(m["kind"] == "addon" and m.get("addon_key") == "regninger" for m in out["messages"]), out


def test_chat_saves_overviews_and_removes(api, pv):
    tok = pv.account("mette@testmail.dk")
    _enable(api, tok)
    out = pv.say(tok, "Mind mig om regningen for Forsikring den 1. hver måned – den er 640 kr.")
    assert out["messages"][-1]["text"] == ("Gemt: Forsikring: hver måned, næste gang tirsdag 1. december, 640 kr. "
                                           "Jeg minder dig om det inden – jeg betaler aldrig selv.")
    api.post(tok, "/privat/bills", {"name": "Husleje", "amount": "8.500", "due_day": 28})
    api.post(tok, "/privat/bills", {"name": "Tandlæge", "due_date": "2026-11-20", "frequency": "once"})
    out = pv.say(tok, "Hvilke regninger skal jeg betale?")
    assert out["messages"][-1]["text"] == ("Regninger i november 2026:\n- Tandlæge: fredag 20. november\n"
                                           "- Husleje: lørdag 28. november, 8.500 kr.\nI alt 8.500 kr. (+ 1 uden beløb).")
    body = api.get(tok, "/privat/bills").json()
    assert [b["name"] for b in body["items"]] == ["Tandlæge", "Husleje", "Forsikring"]
    assert body["month"]["total_minor"] == 850000 and body["month"]["without_amount"] == 1
    out = pv.say(tok, "Slet regningen for Husleje")
    assert out["messages"][-1]["text"] == "Regningen «Husleje» er fjernet."


def test_api_validation_and_isolation(api, pv):
    tok = pv.account("mette@testmail.dk")
    _enable(api, tok)
    assert api.post(tok, "/privat/bills", {"name": "Net"}).status_code == 422                 # no date
    assert api.post(tok, "/privat/bills", {"name": "Net", "due_day": 5, "amount": "billigt"}).status_code == 422
    r = api.post(tok, "/privat/bills", {"name": "Net", "due_day": 5, "amount": "299", "frequency": "monthly"})
    assert r.status_code == 200 and r.json()["created"] is True and r.json()["amount_text"] == "299 kr."
    bid = r.json()["id"]
    r = api.post(tok, "/privat/bills", {"name": "net", "due_day": 6})
    assert r.json()["created"] is False and r.json()["id"] == bid and r.json()["next_due"] == "2026-11-06"
    assert api.patch(tok, f"/privat/bills/{bid}", {"remind_days_before": 0}).json()["remind_days_before"] == 0
    ole = pv.account("ole@testmail.dk", name="Ole Berg")
    _enable(api, ole)
    assert api.delete(ole, f"/privat/bills/{bid}").status_code == 404
    assert api.get(ole, "/privat/bills").json()["items"] == []


def _mails(db) -> list[OutboxEvent]:
    db.expire_all()
    return db.query(OutboxEvent).filter(OutboxEvent.dedupe_key.like("privat-notify:bill:%")).all()


def test_reminder_once_per_due_date_and_moves_on(api, pv, db):
    tok = pv.account("mette@testmail.dk")
    _enable(api, tok)
    api.post(tok, "/privat/bills", {"name": "Forsikring", "due_day": 6, "amount": "640", "remind_days_before": 3})
    api.post(tok, "/privat/bills", {"name": "Husleje", "due_day": 28})
    assert bills.send_due(db, datetime(2026, 11, 4, 6, 0, tzinfo=UTC)) == 0      # 07:00: too early
    assert bills.send_due(db, WED_10) == 1                                        # Forsikring in 2 days
    db.commit()
    [ev] = _mails(db)
    assert ev.payload["email"]["subject"] == "Regning: Forsikring"
    assert "betaler aldrig selv" in str(ev.payload["email"])
    assert bills.send_due(db, WED_10) == 0                                        # once
    # after the due date the bill moves on to December, and is reminded again then
    assert bills.send_due(db, datetime(2026, 12, 3, 9, 0, tzinfo=UTC)) == 1
    db.commit()
    assert db.query(PrivateBill).filter_by(name="Forsikring").one().next_due == date(2026, 12, 6)
    assert api.post(tok, "/privat/addons/regninger/disable").status_code == 200
    assert bills.send_due(db, datetime(2026, 11, 26, 9, 0, tzinfo=UTC)) == 0      # app off: nothing


def test_overview_shows_next_month_when_this_month_is_done(api, pv):
    tok = pv.account("mette@testmail.dk")
    _enable(api, tok)
    api.post(tok, "/privat/bills", {"name": "Forsikring", "due_day": 1, "amount": "640"})
    api.post(tok, "/privat/bills", {"name": "Husleje", "due_day": 1, "amount": "8.500"})
    month = api.get(tok, "/privat/bills").json()["month"]
    assert month["month"] == "december 2026" and month["total_minor"] == 914000 and len(month["items"]) == 2
    out = pv.say(tok, "Hvilke regninger skal jeg betale?")
    text = out["messages"][-1]["text"]
    assert text.startswith("Regninger i december 2026:") and "Forsikring" in text and "Husleje" in text


"""Dialogbot Privat, the Kalender app: agreed times become appointments, which reach the user's own calendar as an
.ics file, through the secret subscription link, and in Google/Outlook (fake connectors, no real provider is called)."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from app.config import get_settings
from app.core.logging import redact_path
from app.models import OutboxEvent, PrivateAppointment, PrivateTask
from app.modules.integrations.connectors.fakes import WORLD
from app.modules.privat import appointments, rules
from app.worker import runner
from tests.privat_fixtures import WED_10
from tests.test_privat import _approve, _report

# WED_10 = Wednesday 4 November 2026, 10:00 in Copenhagen


def _local(dt: datetime | None) -> str | None:
    return rules.local(dt).strftime("%Y-%m-%d %H:%M") if dt else None


@pytest.mark.parametrize("text,expected", [
    ("Torsdag kl. 15.30", "2026-11-05 15:30"),
    ("torsdag kl 15", "2026-11-05 15:00"),
    ("onsdag kl. 14", "2026-11-04 14:00"),          # today, later
    ("onsdag kl. 9", "2026-11-11 09:00"),           # today's weekday, but the time has passed: next week
    ("i morgen kl. 8.15", "2026-11-05 08:15"),
    ("12. november kl. 9", "2026-11-12 09:00"),
    ("Tirsdag d. 10. nov. kl. 10:30", "2026-11-10 10:30"),
    ("12.11 kl. 10", "2026-11-12 10:00"),
    ("12/11/2026 14:00", "2026-11-12 14:00"),
    ("2026-12-01 14:00", "2026-12-01 14:00"),
    ("3. januar kl. 10", "2027-01-03 10:00"),       # January has passed this year: next year
    ("fredag 13.45", "2026-11-06 13:45"),
    ("kl. 15", None),                               # no day: no appointment
    ("på torsdag", None),                           # no time: no appointment
    ("31. februar kl. 10", None),
    ("1. november kl. 10", "2027-11-01 10:00"),
    ("", None),
])
def test_parse_when_reads_danish_times_against_the_day_they_were_agreed(text, expected):
    assert _local(appointments.parse_when(text, WED_10)) == expected


def test_model_time_is_used_only_when_plausible():
    assert _local(appointments.from_iso("2026-11-12T15:30", WED_10)) == "2026-11-12 15:30"
    assert appointments.from_iso("2025-11-12T15:30", WED_10) is None      # in the past
    assert appointments.from_iso("2029-11-12T15:30", WED_10) is None      # more than 400 days ahead
    assert appointments.from_iso("torsdag", WED_10) is None


def test_ics_is_valid_icalendar():
    a = PrivateAppointment(id=uuid.UUID(int=7), title="Herreklip, kort; nakke – Salon Ærø", location="Nørregade 12, 8000 Aarhus C",
                           notes="Linje 1\nLinje 2 " + "x" * 120, starts_at=datetime(2026, 11, 5, 14, 30, tzinfo=UTC),
                           ends_at=datetime(2026, 11, 5, 15, 30, tzinfo=UTC), status="confirmed", sequence=2)
    body = appointments.to_ics([a])
    assert body.startswith("BEGIN:VCALENDAR\r\nVERSION:2.0\r\n") and body.endswith("END:VCALENDAR\r\n")
    assert "\n" not in body.replace("\r\n", "")
    assert all(len(line.encode()) <= 75 for line in body.split("\r\n"))
    unfolded = body.replace("\r\n ", "")
    assert f"UID:{uuid.UUID(int=7)}@dialogbot.dk" in unfolded and "SEQUENCE:2" in unfolded
    assert "DTSTART:20261105T143000Z" in unfolded and "DTEND:20261105T153000Z" in unfolded
    assert "SUMMARY:Herreklip\\, kort\\; nakke – Salon Ærø" in unfolded
    assert "LOCATION:Nørregade 12\\, 8000 Aarhus C" in unfolded and "DESCRIPTION:Linje 1\\nLinje 2" in unfolded
    a.status = "cancelled"
    assert "STATUS:CANCELLED" in appointments.to_ics([a]) and "VALARM" not in appointments.to_ics([a])


def test_feed_token_never_reaches_the_log():
    assert redact_path("/api/v1/privat/calendar/feed/abcDEF-123_x.ics") == "/api/v1/privat/calendar/feed/***"
    assert redact_path("/api/v1/privat/calendar") == "/api/v1/privat/calendar"


def _enable(api, tok):
    r = api.post(tok, "/privat/addons/kalender/enable")
    assert r.status_code == 200, r.text


def _sync(db) -> int:
    n = 0
    while (ev := runner.process_once("w1", only_types=("privat.calendar_sync",))) is not None:
        assert ev.status == "done", ev.last_error
        n += 1
    db.expire_all()
    return n


ANSWER = [{"role": "bot", "message": "Hej, jeg ringer fra Dialogbot"},
          {"role": "user", "message": "Ja, vi kan tage cyklen torsdag kl. 15.30. Et eftersyn koster 450 kr."}]


def test_the_app_needs_a_plan_and_everything_needs_the_app(api, pv):
    free = pv.account("fri@testmail.dk", trial=False)
    r = api.post(free, "/privat/addons/kalender/enable")
    assert r.status_code == 409 and r.json()["code"] == "needs_plan"
    tok = pv.account("mette@testmail.dk")
    assert api.get(tok, "/privat/calendar").json()["enabled"] is False
    for method, path in (("post", "/privat/calendar/feed"), ("post", "/privat/calendar/connect/google"),
                         ("get", "/privat/appointments")):
        r = getattr(api, method)(tok, path)
        assert r.status_code == 403 and r.json()["code"] == "addon_disabled", path


def test_confirmed_call_lands_in_the_calendar_file_and_the_feed(api, client, pv, db, monkeypatch):
    tok = pv.account("mette@testmail.dk")
    _enable(api, tok)
    feed = api.post(tok, "/privat/calendar/feed").json()
    assert feed["url"].startswith(get_settings().public_base_url.rstrip("/")) and feed["webcal_url"].startswith("webcal://")
    token = feed["url"].rsplit("/", 1)[1].removesuffix(".ics")
    assert pv.me(tok) and token not in api.get(tok, "/privat/calendar").text   # the link is never shown again

    tid, p = _approve(api, pv, tok, monkeypatch)  # an extra call (credits) within the trial
    pv.set_plan(tok, "plus")  # Kalender needs a plan to run (PC-ENT-02/03, Fürster 2026-11-10)
    assert _report(client, p, "customer-ended-call", ANSWER, seconds=130)["outcome"] == "applied"
    msgs = api.get(tok, f"/privat/messages?task_id={tid}").json()
    assert msgs[-1]["text"] == "Opkaldet er slut. Cykelmageren har bekræftet torsdag kl. 15.30. Tiden er lagt i din kalender."
    cal = api.get(tok, "/privat/calendar").json()
    [a] = cal["appointments"]
    assert a["source"] == "call" and a["task_id"] == tid and a["title"].endswith("Cykelmageren")
    assert _local(datetime.fromisoformat(a["starts_at"])) == "2026-11-05 15:30"
    assert a["ends_at"] > a["starts_at"] and "450 kr." in a["notes"]
    task = pv.task(tok, tid).json()
    assert any(e["text"].startswith("Aftale gemt") for e in task["events"])
    assert task["appointment"] == {"id": a["id"], "when_text": a["when_text"], "ics_path": a["ics_path"]}

    ics = api.get(tok, a["ics_path"].removeprefix("/api/v1"))
    assert ics.status_code == 200 and ics.headers["content-type"].startswith("text/calendar")
    assert "DTSTART:20261105T143000Z" in ics.text and "attachment" in ics.headers["content-disposition"]

    public = client.get(f"/api/v1/privat/calendar/feed/{token}.ics")         # no login: calendar apps cannot log in
    assert public.status_code == 200 and "DTSTART:20261105T143000Z" in public.text and "METHOD" not in public.text

    # the same report again changes nothing (one appointment per errand)
    assert _report(client, p, "customer-ended-call", ANSWER, seconds=130)["duplicate"] is True
    assert db.query(PrivateAppointment).count() == 1

    # a new link replaces the old one; switching the app off closes the feed
    new = api.post(tok, "/privat/calendar/feed").json()["url"].rsplit("/", 1)[1].removesuffix(".ics")
    assert client.get(f"/api/v1/privat/calendar/feed/{token}.ics").status_code == 404
    assert client.get(f"/api/v1/privat/calendar/feed/{new}.ics").status_code == 200
    assert api.post(tok, "/privat/addons/kalender/disable").status_code == 200
    assert client.get(f"/api/v1/privat/calendar/feed/{new}.ics").status_code == 404
    assert client.get("/api/v1/privat/calendar/feed/nonsense.ics").status_code == 404


def test_other_users_cannot_reach_an_appointment(api, client, pv, db, monkeypatch):
    tok = pv.account("mette@testmail.dk")
    _enable(api, tok)
    tid, p = _approve(api, pv, tok, monkeypatch)
    pv.set_plan(tok, "plus")  # Kalender needs a plan to run (PC-ENT-02/03)
    _report(client, p, "customer-ended-call", ANSWER)
    a = api.get(tok, "/privat/appointments").json()["items"][0]
    ole = pv.account("ole@testmail.dk", name="Ole Berg")
    _enable(api, ole)
    assert api.get(ole, a["ics_path"].removeprefix("/api/v1")).status_code == 404
    assert api.delete(ole, f"/privat/appointments/{a['id']}").status_code == 404


def test_without_the_app_the_time_is_kept_but_nothing_claims_the_calendar(api, client, pv, db, monkeypatch):
    tok = pv.account("mette@testmail.dk")
    tid, p = _approve(api, pv, tok, monkeypatch)
    _report(client, p, "customer-ended-call", ANSWER)
    msgs = api.get(tok, f"/privat/messages?task_id={tid}").json()
    assert msgs[-1]["text"] == "Opkaldet er slut. Cykelmageren har bekræftet torsdag kl. 15.30."
    assert db.query(PrivateAppointment).count() == 1
    assert db.query(OutboxEvent).filter_by(event_type="privat.calendar_sync").count() == 0


def test_unclear_time_makes_no_appointment(api, client, pv, db, monkeypatch):
    tok = pv.account("mette@testmail.dk")
    _enable(api, tok)
    tid, p = _approve(api, pv, tok, monkeypatch)
    pv.set_plan(tok, "plus")  # Kalender needs a plan to run (PC-ENT-02/03)
    msgs = [{"role": "bot", "message": "Hej"}, {"role": "user", "message": "Ja, kom bare forbi torsdag kl. fem eller deromkring."}]
    monkeypatch.setattr("app.modules.privat.calls.classify",
                        lambda *a, **k: {"outcome": "confirmed", "confirmed_text": "Torsdag omkring kl. fem", "starts_at": None})
    _report(client, p, "customer-ended-call", msgs)
    assert db.query(PrivateAppointment).count() == 0
    assert pv.task(tok, tid).json()["next_step"] == "Torsdag omkring kl. fem"


def test_google_connect_sync_move_and_remove(api, client, pv, db):
    tok = pv.account("mette@testmail.dk")
    _enable(api, tok)
    assert api.get(tok, "/privat/calendar").json()["providers"]["google"] == {
        "available": True, "connected": False, "status": "not_connected", "account_label": "", "error": None}
    # an appointment from before the calendar was connected …
    pv.say(tok, "Læg tandlæge torsdag kl. 9 i min kalender")
    [a] = api.get(tok, "/privat/appointments").json()["items"]
    assert a["title"] == "Tandlæge" and _local(datetime.fromisoformat(a["starts_at"])) == "2026-11-05 09:00"
    _sync(db)
    assert not [e for e in WORLD.events.values() if e["title"] == "Tandlæge"]   # nothing connected yet

    url = api.post(tok, "/privat/calendar/connect/google").json()["url"]
    r = client.get(url.split("://", 1)[1].split("/", 1)[1] if url.startswith("http") else url, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].endswith("/privat/kalender?connected=google_calendar")
    assert api.get(tok, "/privat/calendar").json()["providers"]["google"]["connected"] is True
    # … is put there by the backfill
    assert _sync(db) >= 1
    [ev] = [e for e in WORLD.events.values() if e["title"] == "Tandlæge"]
    assert rules.local(ev["start"]).strftime("%H:%M") == "09:00"
    assert api.get(tok, "/privat/appointments").json()["items"][0]["sync"]["google_calendar"] == {"synced": True, "error": None}

    # a new appointment from the chat goes there too
    out = pv.say(tok, "Læg frisør fredag kl. 14 i min kalender")
    assert any("Google Kalender" in m["text"] for m in out["messages"])
    _sync(db)
    assert [e for e in WORLD.events.values() if e["title"] == "Frisør"]

    # removing it removes it from Google (and never cancels anything at the business)
    r = api.delete(tok, f"/privat/appointments/{a['id']}")
    assert r.status_code == 200 and r.json()["status"] == "cancelled"
    _sync(db)
    assert not [e for e in WORLD.events.values() if e["title"] == "Tandlæge"]
    assert [x["title"] for x in api.get(tok, "/privat/appointments").json()["items"]] == ["Frisør"]

    assert api.delete(tok, "/privat/calendar/connect/google").status_code == 204
    assert api.get(tok, "/privat/calendar").json()["providers"]["google"]["connected"] is False


def test_a_provider_error_is_shown_and_retried(api, client, pv, db, monkeypatch):
    from app.modules.integrations.connectors.base import ActionError

    tok = pv.account("mette@testmail.dk")
    _enable(api, tok)
    url = api.post(tok, "/privat/calendar/connect/google").json()["url"]
    client.get(url.split("://", 1)[1].split("/", 1)[1] if url.startswith("http") else url, follow_redirects=False)
    _sync(db)

    def boom(self, **kw):
        raise ActionError("Kalenderen svarede ikke i tide", code="provider_timeout", retryable=True)

    from app.modules.integrations.connectors.fakes import FakeCalendarClient

    monkeypatch.setattr(FakeCalendarClient, "create_event", boom)
    pv.say(tok, "Læg tandlæge torsdag kl. 9 i min kalender")
    ev = runner.process_once("w1", only_types=("privat.calendar_sync",))
    assert ev.status == "queued" and ev.attempts == 1 and "svarede ikke" in (ev.last_error or "")   # tried again later
    # the last attempt keeps the error on the appointment, where the app shows it
    db.query(OutboxEvent).filter_by(id=ev.id).update({"max_attempts": 2, "next_attempt_at": WED_10})
    db.commit()
    ev = runner.process_once("w1", only_types=("privat.calendar_sync",))
    assert ev.status == "done"
    db.expire_all()
    [a] = api.get(tok, "/privat/appointments").json()["items"]
    assert a["sync"]["google_calendar"] == {"synced": False, "error": "Kalenderen svarede ikke i tide"}


def test_chat_offers_the_app_then_explains_how_to_connect(api, pv):
    tok = pv.account("mette@testmail.dk")
    out = pv.say(tok, "Kan du tilføje min google kalender")
    assert any(m["kind"] == "addon" and m.get("addon_key") == "kalender" for m in out["messages"]), out
    _enable(api, tok)
    out = pv.say(tok, "Kan du tilføje min google kalender")
    assert any("Apps → Kalender" in (m.get("text") or "") for m in out["messages"]), out


def test_browser_booking_becomes_an_appointment(api, pv, db, monkeypatch):
    from app.modules.browser import service as browser

    monkeypatch.setenv("BROWSER_WORKER_ENABLED", "true")
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-service-role")
    get_settings.cache_clear()
    # The run's finished_at is the reference «Tirsdag 10. november kl. 10:30» is read against. Pin the browser clock to
    # the test clock (Wed 4 Nov) – with the wall clock the slot rolls a week on once 10:30 on 10 Nov has passed (F-VR-01).
    monkeypatch.setattr(browser, "_now", pv.clock)
    tok = pv.account("mette@testmail.dk")
    _enable(api, tok)
    api.post(tok, "/privat/calendar/feed")
    tid = uuid.UUID(pv.make_list(tok))
    task = db.get(PrivateTask, tid)
    goal = {"intent": "book", "service": "Herreklip", "business_name": "Salon Test", "business_address": "Bygade 1, 8000 Aarhus C",
            "preferred_windows": [{"date": "2026-11-10", "from": "10:00", "to": "12:00"}],
            "contact": {"name": "Mette Hansen", "phone": "+4512345678", "mail": "mette@example.dk"}}
    run = browser.start_run(db, task, goal=goal, allowed_domains=["example.dk"], engine="onlinebooq",
                            booking_url="https://example.dk/book")
    run.before_after = {"service": "Herreklip", "date": "Tirsdag 10. november", "time": "10:30", "price": "350 kr."}
    browser.finish_done(db, run, {"summary": {}, "reference": "OB-1"})
    db.commit()
    [a] = api.get(tok, "/privat/appointments").json()["items"]
    assert a["source"] == "browser" and a["title"] == "Herreklip – Salon Test" and a["location"] == "Bygade 1, 8000 Aarhus C"
    assert _local(datetime.fromisoformat(a["starts_at"])) == "2026-11-10 10:30"
    msgs = api.get(tok, f"/privat/messages?task_id={tid}").json()
    assert msgs[-1]["text"].endswith("Tiden er lagt i din kalender.")

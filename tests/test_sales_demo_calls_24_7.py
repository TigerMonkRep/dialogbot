"""Fürster 12/11: a request from dialogbot.app (/proev, the chat widget, the /start quiz) is rung at once – day and
night, every day. There are no calling hours for Dialogbot's own demo calls: nothing is queued, no consent or text
promises a call «i morgen», and no setting (the retired SALES_CALL_FROM/SALES_CALL_TO) can bring a window back. The
do-not-call list and the «nu» consent still apply. Rows queued before the decision (status `scheduled`) are rung at
the time their visitor consented to, or dropped when the worker missed it by more than 12 hours. The website chat
points to the self-service sign-up when the visitor wants to buy, sign up, know the price or get started."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.config import get_settings
from app.models import DemoCall, DoNotCall
from app.modules.ai import service as ai
from app.modules.sales import service
from tests.test_sales_demo_calls import SECRET, _web, sales  # noqa: F401 – the fixture

CPH = ZoneInfo("Europe/Copenhagen")
WED_2130 = datetime(2026, 11, 11, 21, 30, tzinfo=CPH).astimezone(UTC)
THU_0300 = datetime(2026, 11, 12, 3, 0, tzinfo=CPH).astimezone(UTC)
THU_0800 = datetime(2026, 11, 12, 8, 0, tzinfo=CPH).astimezone(UTC)
THU_0805 = datetime(2026, 11, 12, 8, 5, tzinfo=CPH).astimezone(UTC)
SUN_1400 = datetime(2026, 11, 15, 14, 0, tzinfo=CPH).astimezone(UTC)
SUN_0230 = datetime(2026, 11, 15, 2, 30, tzinfo=CPH).astimezone(UTC)
TOMORROW = ("i morgen", "08:00", "fra kl.", "hverdag", "åbner")


@pytest.mark.parametrize("now", [WED_2130, THU_0300, SUN_1400, SUN_0230], ids=["21:30", "03:00", "søndag", "søndag-nat"])
def test_rung_at_once_day_and_night_every_day(client, sales, db, now):  # noqa: F811
    sales["clock"][0] = now
    info = client.get("/api/v1/demo-call").json()
    assert info["available"] is True
    assert not {"open_now", "next_open", "hours"} & info.keys()  # no calling hours to show or to wait for
    assert info["consent_version"] == service.CONSENT_VERSION_WEB and info["consent_text"] == service.CONSENT_TEXT_WEB
    assert " nu " in info["consent_text"] and not any(w in info["consent_text"] for w in TOMORROW)
    r = _web(client, name="Mette Hansen", company="Hansen Byg ApS", consent_version=info["consent_version"])
    assert r.status_code == 202, r.text
    assert r.json() == {"status": "calling"}  # no «scheduled», no «scheduled_for»
    assert len(sales["calls"]) == 1 and sales["calls"][0]["customer"]["number"] == "+4520304050"
    d = db.query(DemoCall).one()
    assert (d.status, d.scheduled_for, d.provider_call_id) == ("calling", None, "demo_1")
    assert (d.consent_version, d.consent_text) == (service.CONSENT_VERSION_WEB, service.CONSENT_TEXT_WEB)
    assert db.query(DemoCall).filter(DemoCall.status == "scheduled").count() == 0


def test_the_retired_ring_later_consent_is_refused(client, sales, db):  # noqa: F811
    """A page loaded before the change sends the old «ring når I åbner» consent: it does not match a call now, so the
    visitor is asked to reload (the new page shows the «nu» consent) – nothing stored, nobody rung."""
    sales["clock"][0] = WED_2130
    r = _web(client, consent_version="demo-call-web-later-v1")
    assert r.status_code == 422 and r.json()["code"] == "consent_outdated"
    assert db.query(DemoCall).count() == 0 and sales["calls"] == []


def test_do_not_call_stays_secret_at_night(client, sales, db):  # noqa: F811
    db.add(DoNotCall(workspace_id=uuid.UUID(sales["ws"]), phone="+4520304050", source="call"))
    db.commit()
    sales["clock"][0] = THU_0300
    r = _web(client)
    assert r.status_code == 202 and r.json()["status"] == "code_sent"  # the same answer as everybody else
    from app.modules.integrations.connectors.fakes import WORLD

    assert WORLD.sms == [] and sales["calls"] == [] and db.query(DemoCall).count() == 0  # no SMS, nobody rung


@pytest.mark.parametrize("frm, to", [("08:00", "20:00"), ("09:00", "17:00"), ("20:00", "08:00"), ("bad", "x")])
def test_old_window_settings_change_nothing(client, sales, monkeypatch, frm, to):  # noqa: F811
    """SALES_CALL_FROM/SALES_CALL_TO may still be set on Render: they are ignored."""
    monkeypatch.setenv("SALES_CALL_FROM", frm)
    monkeypatch.setenv("SALES_CALL_TO", to)
    get_settings.cache_clear()
    sales["clock"][0] = THU_0300
    assert _web(client).json() == {"status": "calling"} and len(sales["calls"]) == 1


def _legacy(db, ws, *, phone: str, scheduled_for: datetime, created: datetime) -> DemoCall:
    """A row queued by the 11/11 version (outside 08–20, consent «når Dialogbot åbner for opkald igen»)."""
    d = DemoCall(workspace_id=uuid.UUID(ws), source="web", phone=phone, name="", company="Gammel kø ApS",
                 consent_version="demo-call-web-later-v1", consent_text="… når Dialogbot åbner for opkald igen …",
                 consented_at=created, voice_key=service.AGENT_VOICE, status="scheduled", scheduled_for=scheduled_for)
    db.add(d)
    db.commit()
    return d


def test_legacy_queued_rows_are_rung_at_their_time_or_dropped(client, sales, db):  # noqa: F811
    """Rows queued before 12/11 are handled honestly: rung at the time the visitor consented to (never earlier, so not
    at night), dropped when the worker missed that time by more than 12 hours, skipped when the number opted out."""
    ws = sales["ws"]
    waiting = _legacy(db, ws, phone="+4520304050", scheduled_for=THU_0800, created=WED_2130)
    stale = _legacy(db, ws, phone="+4521222324", scheduled_for=THU_0800 - timedelta(days=1),
                    created=WED_2130 - timedelta(days=1))
    blocked = _legacy(db, ws, phone="+4522334455", scheduled_for=THU_0800, created=WED_2130)
    db.add(DoNotCall(workspace_id=uuid.UUID(ws), phone="+4522334455", source="call"))
    db.commit()
    # 03:00: the old request is not rung out of the blue at night; the one 19 hours late is dropped
    sales["clock"][0] = THU_0300
    assert service.place_due(db) == 0 and sales["calls"] == []
    db.refresh(waiting), db.refresh(stale)
    assert waiting.status == "scheduled"
    assert (stale.status, stale.error) == ("skipped", "Køen blev ikke nået i tide")
    # 08:05: the time the visitor consented to
    sales["clock"][0] = THU_0805
    assert service.place_due(db) == 1
    db.refresh(waiting), db.refresh(blocked)
    assert (waiting.status, waiting.provider_call_id) == ("calling", "demo_1")
    assert blocked.status == "skipped" and [c["customer"]["number"] for c in sales["calls"]] == ["+4520304050"]
    assert service.place_due(db) == 0  # once only


def test_a_legacy_row_the_worker_missed_is_dropped_not_rung_late(client, sales, db):  # noqa: F811
    d = _legacy(db, sales["ws"], phone="+4520304050", scheduled_for=THU_0800, created=WED_2130)
    sales["clock"][0] = THU_0800 + timedelta(hours=12, minutes=1)  # 20:01: the worker was down all day
    assert service.place_due(db) == 0 and sales["calls"] == []
    db.refresh(d)
    assert d.status == "skipped"


def test_chat_links_to_the_sign_up(client, sales, monkeypatch):  # noqa: F811
    seen: dict = {}
    real = ai.complete_logged

    def spy(db, ws, **kw):
        seen["instructions"] = kw.get("extra_instructions", "")
        return real(db, ws, **kw)

    monkeypatch.setattr(ai, "complete_logged", spy)
    sales["clock"][0] = WED_2130  # the chat answers at night too
    for q in ("Hvad koster det?", "Jeg vil gerne købe det", "Hvordan opretter jeg mig?", "Hvordan kommer vi i gang?"):
        r = client.post("/api/v1/demo-call/chat", json={"messages": [{"role": "user", "content": q}]})
        assert r.status_code == 200, r.text
        assert r.json()["signup_url"] == service.SIGNUP_PATH == "/signup?intent=reception", q
    # Peter is told to link to the sign-up, that it is open day and night, and that a call is never a condition
    assert "/signup?intent=reception" in seen["instructions"] and "døgnet rundt" in seen["instructions"]
    assert "aldrig en betingelse" in seen["instructions"]
    # … and nothing about calling hours, weekdays or «i morgen» for his own calls
    assert not any(w in seen["instructions"].lower() for w in ("hverdag", "i morgen", "08:00", "08–20", "20:00"))
    r = client.post("/api/v1/demo-call/chat", json={"messages": [{"role": "user", "content": "Kan den tale svensk?"}]})
    assert r.json()["signup_url"] is None  # no link pushed into an answer about something else

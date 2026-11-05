"""Dialogbot Privat: the apps Pakkeliste, Madplan, Læge & tandlæge, Bil & syn and Pakker (17TRACK test double –
no real tracking service, no real call is ever made)."""
from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from app.config import get_settings
from app.models import OutboxEvent, PrivateCall
from app.modules.campaigns import service as campaigns
from app.modules.privat import car, parcels
from tests.privat_fixtures import WED_10

# WED_10 = Wednesday 4 November 2026, 10:00 in Copenhagen


def _enable(api, tok, key):
    r = api.post(tok, f"/privat/addons/{key}/enable")
    assert r.status_code == 200, r.text


def _texts(out) -> list[str]:
    return [m.get("text") or "" for m in out["messages"]]


# --------------------------------------------------------------------------- Pakkeliste

def test_packing_list_is_a_list_and_can_be_reused_unticked(api, pv, db):
    tok = pv.account("mette@testmail.dk")
    out = pv.say(tok, "Lav en pakkeliste til sommerhus med badetøj, solcreme og bøger")
    assert any(m["kind"] == "addon" and m.get("addon_key") == "pakkeliste" for m in out["messages"])
    _enable(api, tok, "pakkeliste")
    out = pv.say(tok, "Lav en pakkeliste til sommerhus med badetøj, solcreme og bøger")
    tid = next(m["task_id"] for m in out["messages"] if m["kind"] == "task")
    t = pv.task(tok, tid).json()
    assert t["title"] == "Pakkeliste: sommerhus" and [i["text"] for i in t["items"]] == ["Badetøj", "Solcreme", "Bøger"]
    first = t["items"][0]["id"]
    assert api.post(tok, f"/privat/tasks/{tid}/items/{first}/toggle").status_code == 200
    out = pv.say(tok, "Lav en pakkeliste ud fra den fra sidst")
    new = next(m["task_id"] for m in out["messages"] if m["kind"] == "task")
    t2 = pv.task(tok, new).json()
    assert new != tid and [i["text"] for i in t2["items"]] == ["Badetøj", "Solcreme", "Bøger"]
    assert not any(i["done"] for i in t2["items"])                     # nothing ticked off in the new one


# --------------------------------------------------------------------------- Madplan

def test_meal_plan_makes_the_plan_and_one_merged_shopping_list(api, pv, db):
    tok = pv.account("mette@testmail.dk")
    _enable(api, tok, "madplan")
    out = pv.say(tok, "Vi er 4 og børnene spiser ikke fisk")
    assert _texts(out)[-1] == "Gemt: 4 personer; spiser ikke: fisk. Det bruger jeg, når jeg laver madplaner."
    assert api.get(tok, "/privat/meals/preferences").json() == {"people": 4, "avoid": "fisk", "likes": ""}
    out = pv.say(tok, "Ja, gem madplanen")
    tasks = [m["task_id"] for m in out["messages"] if m["kind"] == "task"]
    assert len(tasks) == 2
    plan, shop = (pv.task(tok, t).json() for t in tasks)
    assert [i["text"] for i in plan["items"]] == ["Mandag: Lasagne", "Tirsdag: Kylling i karry"]
    assert shop["list_type"] == "shopping"
    # «Tomatsauce» and «tomatsauce» are one line
    assert [i["text"] for i in shop["items"]] == ["500 g hakket oksekød", "Lasagneplader", "Tomatsauce", "Kyllingebryst", "Ris"]


# --------------------------------------------------------------------------- Læge & tandlæge

def test_dentist_is_saved_and_booking_is_only_a_proposal(api, pv, db, monkeypatch):
    called = []
    monkeypatch.setattr(campaigns, "create_call", lambda p: called.append(p) or {"id": "x"})
    tok = pv.account("mette@testmail.dk")
    _enable(api, tok, "laege-og-tandlaege")                    # needs «Ring for mig», which comes on with it
    assert {a["key"]: a["enabled"] for a in api.get(tok, "/privat/addons").json()}["ring-for-mig"] is True
    out = pv.say(tok, "Gem min tandlæge: den hedder Tandklinikken Nord, nummer 86 12 34 56")
    assert _texts(out)[-1].startswith("Din tandlæge er gemt: Tandklinikken Nord, 86 12 34 56")
    assert api.get(tok, "/privat/health-contacts").json()["items"] == [
        {"kind": "tandlaege", "label": "tandlæge", "name": "Tandklinikken Nord", "phone_display": "86 12 34 56"}]
    out = pv.say(tok, "Book et tandeftersyn hos min tandlæge")
    assert out["messages"][-1]["kind"] == "call_proposal" and called == []      # never dialled without approval
    c = db.query(PrivateCall).one()
    assert c.business_name == "Tandklinikken Nord" and c.business_phone_e164 == "+4586123456" and c.status == "proposed"
    assert "helbred" in c.may_not
    # a number the user did not write is never saved
    out = pv.say(tok, "Gem min læge")
    assert api.get(tok, "/privat/health-contacts").json()["items"][0]["kind"] == "tandlaege"
    assert api.delete(tok, "/privat/health-contacts/tandlaege").status_code == 204
    assert api.get(tok, "/privat/health-contacts").json()["items"] == []


# --------------------------------------------------------------------------- Bil & syn

def test_car_dates_reminders_and_workshop(api, pv, db, monkeypatch):
    monkeypatch.setattr(campaigns, "create_call", lambda p: {"id": "x"})
    tok = pv.account("mette@testmail.dk")
    _enable(api, tok, "bil-og-syn")
    out = pv.say(tok, "Bilen AB 12 345 skal til syn 2026-11-20 og husk mig om dæk")
    assert "AB12345" in _texts(out)[-1] and "20. november 2026" in _texts(out)[-1]
    assert api.put(tok, "/privat/car", {"service_due": "2026-11-15"}).json()["service_due"] == "2026-11-15"
    assert api.put(tok, "/privat/car", {"inspection_due": "20/11"}).status_code == 422
    out = pv.say(tok, "Gem mit værksted: værkstedet hedder Auto Hansen, nummer 86 98 76 54")
    assert "Auto Hansen" in _texts(out)[-1]
    out = pv.say(tok, "Book syn hos værkstedet")
    assert out["messages"][-1]["kind"] == "call_proposal"
    # reminders: inspection 30 days before, service 14 days before, winter tyres from 15 October – each once
    assert car.send_due(db, WED_10) == 2                         # syn in 16 days, service in 11 days
    db.commit()
    assert car.send_due(db, WED_10) == 0
    assert car.send_due(db, datetime(2027, 10, 15, 9, 0, tzinfo=UTC)) == 1      # winter tyres next year
    db.commit()
    assert len(db.query(OutboxEvent).filter(OutboxEvent.dedupe_key.like("privat-notify:car:%")).all()) == 3


def test_due_reminders_unit():
    data = {"plate": "AB12345", "inspection_due": "2026-12-01", "tire_reminders": True, "reminded": {}}
    assert [k for k, _ in car.due_reminders(data, date(2026, 11, 4))] == ["inspection_due"]
    assert car.due_reminders(data, date(2026, 10, 1)) == []
    assert [k for k, _ in car.due_reminders({"tire_reminders": True}, date(2026, 3, 30))] == ["tyres:sommer:2026"]


# --------------------------------------------------------------------------- Pakker

def test_parcels_need_the_tracking_key(api, pv):
    tok = pv.account("mette@testmail.dk")
    cat = {a["key"]: a for a in api.get(tok, "/privat/addons").json()}
    assert cat["pakker"]["status"] == "coming_soon"
    assert api.post(tok, "/privat/addons/pakker/enable").json()["code"] == "coming_soon"


@pytest.fixture
def tracking(monkeypatch):
    monkeypatch.setenv("TRACK17_API_KEY", "fake")
    get_settings.cache_clear()
    parcels.FakeTracker.world.clear()
    parcels.FakeTracker.registered.clear()
    yield parcels.FakeTracker
    get_settings.cache_clear()


def test_parcel_tracked_and_user_told_when_it_moves(api, pv, db, tracking):
    tok = pv.account("mette@testmail.dk")
    _enable(api, tok, "pakker")
    tracking.world["00340434123456789"] = [{"status": "InfoReceived"}, {"status": "AvailableForPickup", "location": "Netto, Nørregade"},
                                         {"status": "Delivered"}]
    out = pv.say(tok, "Følg pakken med nummer 00340434123456789")
    assert _texts(out)[-1] == "Jeg følger pakken. 00340434123456789: afsenderen har meldt den. Du får besked, når den rykker sig."
    assert tracking.registered == ["00340434123456789"]
    assert parcels.poll(db, WED_10 + timedelta(minutes=30)) == 0               # not again before 2 hours
    assert parcels.poll(db, WED_10 + timedelta(hours=3)) == 1                  # ready for pickup
    db.commit()
    [ev] = db.query(OutboxEvent).filter(OutboxEvent.dedupe_key.like("privat-notify:parcel:%")).all()
    assert "klar til afhentning (Netto, Nørregade)" in str(ev.payload["email"])
    assert parcels.poll(db, WED_10 + timedelta(hours=6)) == 1                  # delivered
    db.commit()
    assert parcels.poll(db, WED_10 + timedelta(hours=9)) == 0                  # done: no more polling
    items = api.get(tok, "/privat/parcels").json()["items"]
    assert items[0]["status"] == "Delivered" and items[0]["done"] is True
    assert api.post(tok, "/privat/parcels", {"number": "x!"}).status_code == 422
    assert api.delete(tok, "/privat/parcels/00340434123456789").status_code == 204
    assert api.get(tok, "/privat/parcels").json()["items"] == []


def test_every_shop_app_is_now_available_or_waits_for_its_key(api, pv):
    tok = pv.account("mette@testmail.dk")
    cat = {a["key"]: a["status"] for a in api.get(tok, "/privat/addons").json()}
    assert {k for k, v in cat.items() if v == "coming_soon"} == {"pakker", "rejser"}   # both wait for their API key

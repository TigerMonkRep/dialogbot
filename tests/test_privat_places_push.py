"""Dialogbot Privat: finding the business (Google Places via the shared client, faked here), opening hours and the
«ved næste åbningstid» path, number rules, the search rate limit, public-lookup limits and Web Push."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.config import get_settings
from app.models import EmailDelivery, OutboxEvent, PrivateCall, PushSubscription
from app.modules.campaigns import service as campaigns
from app.modules.privat import push
from app.modules.sales import places as gp
from app.worker import runner

THU_9 = datetime(2026, 11, 5, 8, 0, tzinfo=UTC)  # Thursday 09:00 in Copenhagen


def _periods(days, open_h=9, close_h=17):
    return [{"open": {"day": d, "hour": open_h, "minute": 0}, "close": {"day": d, "hour": close_h, "minute": 0}}
            for d in days]


class FakeGooglePlaces:
    source = "google"

    def __init__(self, places: list[dict]):
        self.places = places
        self.calls: list[tuple] = []

    def search(self, *, text_query, included_type, center, radius_m, page_token=None):
        self.calls.append(("search", text_query))
        return [gp.Place(id=p["id"], name=p["name"], address=p.get("address", "Vej 1, 8000 Aarhus C"), lat=p.get("lat", 56.15),
                         lng=p.get("lng", 10.20), business_status=p.get("status", "OPERATIONAL"),
                         maps_uri=f"https://maps.google.com/?cid={p['id']}") for p in self.places], None

    def details(self, place_id):
        self.calls.append(("details", place_id))
        p = next(x for x in self.places if x["id"] == place_id)
        return gp.Details(phone_national=p.get("phone"), phone_international=p.get("phone"), rating=p.get("rating"),
                          user_rating_count=12, periods=p.get("periods"))

    def geocode(self, text):
        self.calls.append(("geocode", text))
        return (55.68, 12.57)


@pytest.fixture
def fake_places():
    holder = {}

    def use(places):
        holder["c"] = FakeGooglePlaces(places)
        gp.set_client_override(holder["c"])
        return holder["c"]

    yield use
    gp.set_client_override(None)


@pytest.fixture
def dial(monkeypatch):
    called = []
    monkeypatch.setattr(campaigns, "create_call", lambda p: called.append(p) or {"id": f"v{len(called)}"})
    return called


WEEK = [1, 2, 3, 4, 5]


def test_business_search_ranking_limit_and_location(api, pv, fake_places):
    c = fake_places([{"id": "a", "name": "Fona Bruuns", "phone": "+45 86 11 22 33", "rating": 4.5, "periods": _periods(WEEK)},
                     {"id": "x", "name": "Lukket for altid", "status": "CLOSED_PERMANENTLY"},
                     {"id": "b", "name": "Fona Strøget", "phone": "+45 33 11 22 33", "periods": _periods(WEEK)},
                     {"id": "c", "name": "Fona Odense", "phone": "+45 66 11 22 33"},
                     {"id": "d", "name": "Fona Fjerde", "phone": "+45 98 11 22 33"}])
    tok = pv.account("mette@testmail.dk")
    r = api.get(tok, "/privat/businesses/search?q=Fona")
    assert r.status_code == 409 and r.json()["code"] == "needs_location"  # Google needs to know where
    rows = api.get(tok, "/privat/businesses/search?q=Fona&city=Aarhus").json()
    assert [x["place_id"] for x in rows] == ["a", "b", "c"]  # Google's order, operational only, max 3
    assert [x for x in c.calls if x[0] == "details"] == [("details", "a"), ("details", "b"), ("details", "c")]
    a = rows[0]
    assert (a["phone_e164"], a["phone_display"], a["open_now"], a["source"], a["rating"]) == (
        "+4586112233", "+45 86 11 22 33", True, "google", 4.5)
    assert a["distance_km"] is not None and a["maps_url"].startswith("https://maps.google.com/")
    assert rows[2]["open_now"] is None  # no hours known
    # a location the user gives is remembered; nothing else is stored
    me = api.c.patch("/api/v1/privat/me/location", json={"city": "København"}, headers=api.h(tok)).json()
    assert me["location_city"] == "København"
    assert api.get(tok, "/privat/businesses/search?q=Fona").status_code == 200
    bad = api.c.patch("/api/v1/privat/me/location", json={"lat": 40.0, "lng": 2.0}, headers=api.h(tok))
    assert bad.status_code == 422


def test_search_rate_limit(api, pv, fake_places):
    fake_places([{"id": "a", "name": "Fona", "phone": "+4586112233"}])
    tok = pv.account("mette@testmail.dk")
    for _ in range(30):
        assert api.get(tok, "/privat/businesses/search?q=Fona&city=Aarhus").status_code == 200
    r = api.get(tok, "/privat/businesses/search?q=Fona&city=Aarhus")
    assert r.status_code == 429 and r.json()["code"] == "rate_limited"
    pv.clock.at += timedelta(minutes=61)
    assert api.get(tok, "/privat/businesses/search?q=Fona&city=Aarhus").status_code == 200


def _pick(api, pv, tok, text="Ring til Fona i Aarhus og spørg om de har min ordre"):
    out = pv.say(tok, text)
    clar = out["messages"][-1]
    assert clar["kind"] == "clarify", out
    assert clar["options"][0]["id"].startswith("place:")
    return clar, api.post(tok, f"/privat/messages/{clar['id']}/options/{clar['options'][0]['id']}").json()["messages"]


def test_chat_uses_search_and_asks_for_a_missing_number(api, pv, fake_places, dial):
    fake_places([{"id": "a", "name": "Fona", "phone": None, "rating": 4.5, "periods": _periods(WEEK)}])
    tok = pv.account("mette@testmail.dk")
    pv.verify_phone(tok)
    out = pv.say(tok, "Ring til Fona og spørg om min ordre")  # no location yet: the web asks «Hvor skal jeg lede?»
    assert [o["id"] for o in out["messages"][-1]["options"]] == ["location:geo", "location:city"]
    pv.api.c.patch("/api/v1/privat/me/location", json={"city": "Aarhus"}, headers=api.h(tok))
    clar, msgs = _pick(api, pv, tok)
    assert "data fra Google" in clar["text"] and clar["options"][0]["label"] == "Fona"
    assert clar["options"][0]["id"] == "place:a" and "åben nu · ★ 4,5 (12)" in clar["options"][0]["sub"]
    prop = msgs[-1]
    assert prop["kind"] == "call_proposal" and prop["text"].startswith("Jeg har ikke et nummer til Fona")
    tid = prop["task_id"]
    call = pv.task(tok, tid).json()["call"]
    assert (call["phone_e164"], call["source"], call["open_now"]) == (None, "google", True)
    r = api.post(tok, f"/privat/calls/{tid}/approve", {"window": "", "share_phone": False})
    assert r.status_code == 409 and r.json()["code"] == "needs_business_phone"
    # the user answers with the number in the chat, about the call task
    out = pv.say(tok, "Nummeret er 86 11 22 33", about=tid)
    assert [m["kind"] for m in out["messages"]] == ["text", "text", "call_proposal"]
    assert out["messages"][1]["text"] == "Tak. Jeg bruger 86 11 22 33."
    call = pv.task(tok, tid).json()["call"]
    assert (call["phone_e164"], call["source"], call["is_mobile"]) == ("+4586112233", "user", False)
    assert api.post(tok, f"/privat/calls/{tid}/approve", {"window": "", "share_phone": False}).json()["status"] == "in_progress"
    assert len(dial) == 1


def test_mobile_number_needs_confirmation(api, pv, fake_places, dial):
    fake_places([{"id": "a", "name": "Frisør Lise", "phone": "+45 20 30 40 50", "periods": _periods(WEEK)}])
    tok = pv.account("mette@testmail.dk")
    api.c.patch("/api/v1/privat/me/location", json={"city": "Aarhus"}, headers=api.h(tok))
    pv.verify_phone(tok)
    _clar, msgs = _pick(api, pv, tok, "Ring til Frisør Lise og bestil tid")
    prop = msgs[-1]
    assert prop["kind"] == "call_proposal" and "ligner et mobilnummer" in prop["text"]
    tid = prop["task_id"]
    t = pv.task(tok, tid).json()
    assert t["call"]["phone_display"] == "20 30 40 50" and t["call"]["is_mobile"] is True
    r = api.post(tok, f"/privat/calls/{tid}/approve", {"window": "", "share_phone": False})
    assert r.status_code == 409 and r.json()["code"] == "confirm_business" and dial == []
    t = api.post(tok, f"/privat/calls/{tid}/approve", {"window": "", "share_phone": False, "confirm_business": True}).json()
    assert t["status"] == "in_progress" and len(dial) == 1


def test_closed_now_schedules_for_next_opening(api, pv, db, fake_places, dial):
    fake_places([{"id": "fona-1", "name": "Fona", "phone": "+4586112233", "periods": _periods([4])}])  # Thursdays
    tok = pv.account("mette@testmail.dk")
    api.c.patch("/api/v1/privat/me/location", json={"city": "Aarhus"}, headers=api.h(tok))
    pv.verify_phone(tok)
    clar, msgs = _pick(api, pv, tok)
    assert "lukket nu" in clar["options"][0]["sub"]
    prop = msgs[-1]
    assert prop["kind"] == "call_proposal" and "har lukket nu" in prop["text"] and "i morgen kl. 9.00" in prop["text"]
    tid = prop["task_id"]
    r = api.post(tok, f"/privat/calls/{tid}/approve", {"share_phone": False})
    assert r.status_code == 409 and r.json()["code"] == "business_closed"
    assert r.json()["next_open_text"] == "I morgen kl. 9.00"
    t = api.post(tok, f"/privat/calls/{tid}/approve", {"share_phone": False, "at_next_open": True}).json()
    assert t["status"] == "planned" and t["call"]["status"] == "scheduled" and dial == []
    me = pv.me(tok)  # in the trial the scheduled call is one of the plan's calls: nothing is reserved in credits
    assert me["reserved"] == 0 and me["calls_used"] == 1 and t["usage_text"] == "Opkald 1 af 10 i Plus"
    c = db.query(PrivateCall).one()
    assert c.place_id == "fona-1" and c.scheduled_for == THU_9
    due = db.query(OutboxEvent).filter_by(event_type="privat.call_due").one()
    assert due.next_attempt_at == THU_9
    # the worker dials at the opening time – and only because the approval says so
    pv.clock.at = THU_9 + timedelta(minutes=1)
    db.query(OutboxEvent).filter(OutboxEvent.event_type.in_(("privat.call_due", "privat.call_ask"))).update(
        {"next_attempt_at": datetime.now(UTC)}, synchronize_session=False)
    db.commit()
    runner.drain()
    assert len(dial) == 1 and dial[0]["customer"]["number"] == "+4586112233"
    assert pv.task(tok, tid).json()["status"] == "in_progress"


def test_closed_proposal_is_offered_again_but_never_dialled(api, pv, db, fake_places, dial):
    fake_places([{"id": "fona-1", "name": "Fona", "phone": "+4586112233", "periods": _periods([4])}])
    tok = pv.account("mette@testmail.dk")
    api.c.patch("/api/v1/privat/me/location", json={"city": "Aarhus"}, headers=api.h(tok))
    _clar, msgs = _pick(api, pv, tok)
    tid = msgs[-1]["task_id"]
    pv.clock.at = THU_9
    db.query(OutboxEvent).filter_by(event_type="privat.call_ask").update({"next_attempt_at": datetime.now(UTC)})
    db.commit()
    runner.drain()
    last = api.get(tok, f"/privat/messages?task_id={tid}").json()[-1]
    assert last["kind"] == "call_proposal" and last["text"] == "Fona har åbent nu. Skal jeg ringe?"
    assert dial == [] and pv.task(tok, tid).json()["status"] == "awaiting_user"


def test_scheduled_call_can_be_cancelled(api, pv, fake_places, dial):
    fake_places([{"id": "fona-1", "name": "Fona", "phone": "+4586112233", "periods": _periods([4])}])
    tok = pv.account("mette@testmail.dk")
    api.c.patch("/api/v1/privat/me/location", json={"city": "Aarhus"}, headers=api.h(tok))
    pv.verify_phone(tok)
    _clar, msgs = _pick(api, pv, tok)
    tid = msgs[-1]["task_id"]
    api.post(tok, f"/privat/calls/{tid}/approve", {"share_phone": False, "at_next_open": True})
    t = api.post(tok, f"/privat/calls/{tid}/decline").json()
    assert t["status"] == "declined" and pv.me(tok)["credits"] == 3 and pv.me(tok)["reserved"] == 0


# --------------------------------------------------------------------------- web push

@pytest.fixture
def vapid(monkeypatch):
    monkeypatch.setenv("VAPID_PUBLIC_KEY", "BPUBLICKEYxxxxxxxxxxxxxxxxxxxxxxxxx")
    monkeypatch.setenv("VAPID_PRIVATE_KEY", "privatekeyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx")
    get_settings.cache_clear()
    sent: list[tuple[dict, str]] = []
    behaviour = {"raise": None}

    def fake(sub, data):
        if behaviour["raise"] is not None:
            from pywebpush import WebPushException

            raise WebPushException("push failed", response=type("R", (), {"status_code": behaviour["raise"]})())
        sent.append((sub, data))

    monkeypatch.setattr(push, "_webpush", fake)
    yield sent, behaviour
    get_settings.cache_clear()


def _sub(api, tok, endpoint="https://push.example.test/abc"):
    r = api.post(tok, "/privat/push/subscriptions", {"endpoint": endpoint,
                                                     "keys": {"p256dh": "BNcRdreALRFXTkOOUHK1EtK2wtaz5Ry4YfYCA_0QTpQtUbVlUls0VJXg7A8u-Ts1XbjhazAkj7I99e8QcYP7DkM",
                                                              "auth": "tBHItJI5svbpez7KI4CCXg"}})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _due_now(db, event_type):
    db.query(OutboxEvent).filter_by(event_type=event_type, status="queued").update({"next_attempt_at": datetime.now(UTC)})
    db.commit()


def test_push_subscribe_dedupe_and_keys(api, pv, db, vapid, monkeypatch):
    tok = pv.account("mette@testmail.dk")
    assert api.get(tok, "/privat/push/public-key").json() == {"public_key": "BPUBLICKEYxxxxxxxxxxxxxxxxxxxxxxxxx"}
    a, b = _sub(api, tok), _sub(api, tok)
    assert a == b and db.query(PushSubscription).count() == 1
    assert pv.me(tok)["push_enabled"] is True
    assert api.post(tok, "/privat/push/test").json() == {"sent": 1}
    runner.drain()
    assert vapid[0][-1][1].startswith('{"title": "Dialogbot", "body": "Det virker')
    r = api.c.request("DELETE", "/api/v1/privat/push/subscriptions", json={"endpoint": "https://push.example.test/abc"},
                      headers=api.h(tok))
    assert r.json() == {"removed": True} and pv.me(tok)["push_enabled"] is False
    monkeypatch.delenv("VAPID_PRIVATE_KEY")
    get_settings.cache_clear()
    assert api.get(tok, "/privat/push/public-key").json()["code"] == "push_not_configured"


def test_reminder_sends_push_instead_of_email(api, pv, db, vapid):
    tok = pv.account("mette@testmail.dk")
    _sub(api, tok)
    pv.say(tok, "Mind mig om at hente pakken i morgen kl 16")
    _due_now(db, "privat.reminder")
    runner.drain()
    assert len(vapid[0]) == 1 and '"body": "Hente pakken"' in vapid[0][0][1]
    assert db.query(EmailDelivery).filter(EmailDelivery.subject.like("Påmindelse%")).count() == 0


def test_push_410_removes_subscription_and_falls_back_to_email(api, pv, db, vapid):
    sent, behaviour = vapid
    tok = pv.account("mette@testmail.dk")
    _sub(api, tok)
    behaviour["raise"] = 410
    pv.say(tok, "Mind mig om at hente pakken i morgen kl 16")
    _due_now(db, "privat.reminder")
    runner.drain()
    assert db.query(PushSubscription).count() == 0 and sent == []
    assert db.query(EmailDelivery).filter(EmailDelivery.subject.like("Påmindelse%")).count() == 1


def test_email_fallback_without_subscription(api, pv, db, vapid):
    tok = pv.account("mette@testmail.dk")
    pv.say(tok, "Mind mig om at hente pakken i morgen kl 16")
    _due_now(db, "privat.reminder")
    runner.drain()
    assert vapid[0] == [] and db.query(EmailDelivery).filter(EmailDelivery.subject.like("Påmindelse%")).count() == 1


def test_push_retries_then_falls_back(api, pv, db, vapid):
    sent, behaviour = vapid
    tok = pv.account("mette@testmail.dk")
    _sub(api, tok)
    behaviour["raise"] = 500
    pv.say(tok, "Mind mig om at hente pakken i morgen kl 16")
    _due_now(db, "privat.reminder")
    runner.drain()
    ev = db.query(OutboxEvent).filter_by(event_type="push.send").one()
    assert ev.status == "queued" and ev.attempts == 1  # retried later
    for _ in range(ev.max_attempts):
        _due_now(db, "push.send")
        runner.drain()
    db.expire_all()
    assert db.query(OutboxEvent).filter_by(event_type="push.send").one().status == "done"
    assert db.query(EmailDelivery).filter(EmailDelivery.subject.like("Påmindelse%")).count() == 1
    assert db.query(PushSubscription).count() == 1  # a 5xx does not remove the subscription


def test_shared_list_push_is_batched(api, pv, db, vapid):
    mette = pv.account("mette@testmail.dk", "Mette Hansen")
    ole = pv.user("ole@testmail.dk", "Ole Berg")
    tid = pv.make_list(mette)
    inv = api.post(mette, f"/privat/tasks/{tid}/share", {"mode": "group"}).json()
    _sub(api, mette, "https://push.example.test/mette")
    api.post(ole, f"/privat/invites/{inv['token']}/accept")
    _sub(api, ole, "https://push.example.test/ole")
    for item in ("Smør", "Ost", "Kaffe"):
        api.post(ole, f"/privat/tasks/{tid}/items", {"text": item})

    def to(user_endpoint):
        sub_id = str(db.query(PushSubscription).filter_by(endpoint=user_endpoint).one().id)
        return [e for e in db.query(OutboxEvent).filter_by(event_type="push.send").all()
                if e.payload["subscription_id"] == sub_id and e.payload["tag"] == f"list-{tid}"]

    db.expire_all()
    assert len(to("https://push.example.test/mette")) == 1  # three additions within 2 minutes → one push
    assert to("https://push.example.test/ole") == []  # never to the one who did it
    pv.clock.at += timedelta(minutes=2)
    api.post(ole, f"/privat/tasks/{tid}/items", {"text": "Te"})
    db.expire_all()
    assert len(to("https://push.example.test/mette")) == 2
    # reserving on a wishlist never notifies anyone (the owner must not learn of it)
    assert db.query(OutboxEvent).filter(OutboxEvent.event_type == "push.send",
                                        OutboxEvent.payload["body"].astext.like("%reserv%")).count() == 0

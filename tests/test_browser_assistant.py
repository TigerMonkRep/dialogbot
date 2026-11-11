"""A5: how a browser booking is started from the chat. The track rules (1-4) one by one, the lookup cache, the Opkaldssaldo, «ring i stedet».
No browser, no network: CVR, Google Places and the website are fakes; the model is a script."""
from __future__ import annotations

import json
import uuid
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.config import get_settings
from app.models import (
    BrowserRun,
    CreditLedger,
    ExternalBusinessContact,
    OutboxEvent,
    PrivateCall,
    PrivateTask,
)
from app.modules.ai import provider as ai_provider
from app.modules.browser import lookup, profiles, routing, service
from app.modules.browser.events import BROWSER_EVENT_TYPES
from app.modules.business import cvr as cvr_register
from app.modules.privat import ledger, rules
from app.modules.sales import places as gp

WINDOWS = [{"date": "2026-11-10", "from": "09:00", "to": "12:00"}]
SITE_OK = '<html><body><script src="https://widget.onlinebooq.example/x.js"></script><a href="/booking">Book tid</a></body></html>'
SITE_NONE = "<html><body><p>Velkommen til Salon Test</p></body></html>"


def facts(**kw) -> routing.Facts:
    base = dict(user_said=None, intent="book", website="https://salon-test.dk", engine="onlinebooq",
                booking_url="https://booking.salon-test.dk/start", has_name_and_phone=True, concrete=True, worker_enabled=True,
                has_balance=True)
    return routing.Facts(**{**base, **kw})


@pytest.fixture(autouse=True)
def _on(monkeypatch):
    monkeypatch.setenv("BROWSER_WORKER_ENABLED", "true")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
    gp._override = None
    ai_provider.set_provider_override(None)


# --- the rules, one by one ----------------------------------------------------------------------------------------------

def test_rule_1_ring_is_the_phone_even_when_the_browser_would_work():
    d = routing.decide(facts(user_said="ring"))
    assert (d.track, d.rule, d.reason) == ("phone", 1, "user_said_ring")


def test_rule_1_skriv_is_the_browser_without_questions_when_it_can():
    assert routing.decide(facts(user_said="skriv")).track == "browser"
    d = routing.decide(facts(user_said="skriv", website=None))                     # ... and the phone, with the reason, when it cannot
    assert (d.track, d.rule, d.reason) == ("phone", 1, "no_website") and "hjemmeside" in d.say_blocker


def test_rule_2_flyt_and_aflys_are_the_phone():
    for intent in ("flyt", "aflys"):
        d = routing.decide(facts(intent=intent))                                   # everything else would allow the browser
        assert (d.track, d.rule, d.reason) == ("phone", 2, "intent_not_book")
    assert routing.decide(facts(intent="flyt", user_said="skriv")).track == "phone"


def test_rule_3_browser_when_every_condition_holds():
    d = routing.decide(facts())
    assert (d.track, d.rule, d.reason) == ("browser", 3, "ok")


@pytest.mark.parametrize("change,reason", [
    ({"website": None}, "no_website"),
    ({"engine": "unknown"}, "engine_unknown"),
    ({"engine": "planway"}, "engine_unknown"),            # known to nobody here: no playbook
    ({"booking_url": None}, "no_booking_url"),
    ({"has_name_and_phone": False}, "no_contact"),
    ({"worker_enabled": False}, "worker_disabled"),
    ({"has_balance": False}, "no_balance"),
])
def test_rule_4_everything_else_is_the_phone(change, reason):
    d = routing.decide(facts(**change))
    assert (d.track, d.rule, d.reason) == ("phone", 4, reason)


def test_an_engine_outside_BROWSER_ALLOWED_ENGINES_is_the_phone(monkeypatch):
    monkeypatch.setenv("BROWSER_ALLOWED_ENGINES", "planway")
    get_settings.cache_clear()
    assert routing.decide(facts()).reason == "engine_unknown"


def test_no_concrete_booking_means_ask_never_a_run_and_never_a_silent_phone():
    d = routing.decide(facts(concrete=False))
    assert (d.track, d.rule) == ("ask", 3)
    assert routing.decide(facts(concrete=False, user_said="skriv")).track == "ask"
    assert routing.decide(facts(concrete=False, user_said="ring")).track == "phone"    # a call needs no exact slot


# --- fakes -----------------------------------------------------------------------------------------------------------------

class Cvr:
    def __init__(self, hits):
        self.hits, self.calls = hits, 0

    def __call__(self, name, city=None, size=5):
        self.calls += 1
        return self.hits


class Places:
    source = "google"

    def __init__(self, website="https://salon-test.dk", phone="+4587654321"):
        self.calls, self.website, self.phone = 0, website, phone

    def search(self, *, text_query, included_type, center, radius_m, page_token=None):
        self.calls += 1
        return [gp.Place(id="ChIJsalon", name="Salon Test", address="Testvej 1, 8000 Aarhus C", lat=56.15, lng=10.2,
                         business_status="OPERATIONAL")], None

    def details(self, place_id):
        periods = [{"open": {"day": d, "hour": 9, "minute": 0}, "close": {"day": d, "hour": 17, "minute": 0}} for d in range(1, 6)]
        return gp.Details(website=self.website, phone_national="87 65 43 21", phone_international=self.phone, periods=periods)

    def geocode(self, text):
        return None


CVR_HIT = {"cvr": "12345674", "legal_name": "Salon Test ApS", "address_line": "Testvej 1", "postal_code": "8000", "city": "Aarhus C",
           "industry": "Frisør", "status": "NORMAL", "advertising_protected": True,
           "contacts": ["86 12 34 56", "info@salon-test.dk", "salon-test.dk"]}


@pytest.fixture
def world(monkeypatch):
    """CVR, Google Places and the website, all fake; returns the handles."""
    from types import SimpleNamespace

    c = Cvr([CVR_HIT])
    monkeypatch.setattr(cvr_register, "configured", lambda: True)
    monkeypatch.setattr(cvr_register, "search_by_name", c)
    monkeypatch.setattr(cvr_register, "cvr_valid", lambda v: True)
    p = Places()
    gp._override = p
    site = SimpleNamespace(html=SITE_OK, fetched=[])

    def fetch(url):
        site.fetched.append(url)
        return url, site.html

    monkeypatch.setattr(profiles, "default_fetch", fetch)
    return SimpleNamespace(cvr=c, places=p, site=site)


class ChatModel:
    """The chat model as a script: each step maps the conversation so far to the tool calls it makes."""

    name, model = "scripted", "claude-opus-5"

    def __init__(self, *steps):
        self.steps, self.i = list(steps), 0

    def complete(self, *, system, messages, max_tokens, tools=None, model=None, effort=None):
        from app.modules.ai.provider import Completion, ToolCall, Usage

        if self.i >= len(self.steps):
            return Completion(text="Ok.", stop_reason="end_turn", requested_model="m", served_model="m", usage=Usage(1, 1))
        calls = self.steps[self.i](messages)
        self.i += 1
        tcs = [ToolCall(id=f"t{self.i}_{k}", name=n, input=a) for k, (n, a) in enumerate(calls)]
        return Completion(text="", stop_reason="tool_use", requested_model="m", served_model="m", usage=Usage(1, 1), tool_calls=tcs,
                          assistant_content=[{"type": "tool_use", "id": t.id, "name": t.name, "input": t.input} for t in tcs])


def business_id(messages) -> str:
    last = messages[-1]["content"]
    return json.loads(next(b["content"] for b in last if b.get("type") == "tool_result"))["business_id"]


def book(pv, tok, *, name="Salon Test", city="Aarhus", **start):
    """The user asks for a booking; the model finds the business, then starts the booking."""
    args = {"intent": "book", "service": "herreklip", "preferred_windows": WINDOWS, **start}
    ai_provider.set_provider_override(ChatModel(
        lambda m: [("find_business", {"name": name, "city": city})],
        lambda m: [("start_booking", {"business_id": business_id(m), **args})]))
    return pv.say(tok, f"Book {args.get('service') or 'en tid'} hos {name} i {city}")


@pytest.fixture
def user(pv):
    tok = pv.account("mette@testmail.dk")
    pv.verify_phone(tok)
    return tok


def texts(out) -> str:
    return " | ".join(m["text"] for m in out["messages"])


def runs(db):
    db.expire_all()
    return list(db.scalars(select(BrowserRun)))


# --- through the chat ---------------------------------------------------------------------------------------------------

def test_browser_track_says_so_reserves_the_price_and_queues_the_run(api, db, pv, user, world):
    out = book(pv, user)
    assert "Jeg prøver at booke online hos Salon Test – du får et forslag at godkende" in texts(out)
    assert "ring i stedet" in texts(out)
    [run] = runs(db)
    assert run.status == "planned" and run.engine == "onlinebooq"
    task = db.get(PrivateTask, run.task_id)
    assert task.status == "in_progress" and task.kind == "call"
    assert run.goal["contact"] == {"name": "Mette Hansen", "phone": "+4520304050"}      # ONLY name + verified mobile: no e-mail
    assert run.goal["service"] == "herreklip" and run.goal["preferred_windows"] == WINDOWS
    assert set(run.allowed_domains) == {"booking.salon-test.dk", "salon-test.dk"} or "salon-test.dk" in run.allowed_domains
    [res] = [e for e in db.scalars(select(CreditLedger)) if e.source_ref == f"browser:{run.id}:reserve"]
    assert res.amount == -service.BROWSER_BOOKING_MINOR == -290 and res.currency == "DKK"  # 1 credit = 2,90 kr.
    assert len([e for e in db.scalars(select(OutboxEvent)) if e.event_type in BROWSER_EVENT_TYPES]) == 1
    call = db.scalar(select(PrivateCall).where(PrivateCall.task_id == task.id))
    assert call.status == "proposed" and call.business_name == "Salon Test"      # the hidden fallback proposal, never dialled


def test_user_says_ring_phone_track_even_though_the_browser_could(api, db, pv, user, world):
    out = book(pv, user, user_said_track="ring")
    assert "Jeg ringer til Salon Test i åbningstiden, når du har godkendt opkaldet" in texts(out)
    assert not runs(db) and any(m["kind"] == "call_proposal" for m in out["messages"])
    call = db.scalar(select(PrivateCall))
    assert call.status == "proposed" and call.business_phone_e164 == "+4586123456"        # CVR's number first


def test_user_says_skriv_browser_track(api, db, pv, user, world):
    out = book(pv, user, user_said_track="skriv")
    assert "booke online" in texts(out) and len(runs(db)) == 1


@pytest.mark.parametrize("intent", ["flyt", "aflys"])
def test_flyt_and_aflys_are_not_automated_in_v1(api, db, pv, user, world, intent):
    out = book(pv, user, intent=intent)
    assert not runs(db) and "kun booke nye tider" in texts(out) and any(m["kind"] == "call_proposal" for m in out["messages"])


def test_without_a_google_key_the_website_lookup_is_skipped_and_we_call(api, db, pv, user, world):
    gp._override = None                                                                  # no GOOGLE_PLACES_API_KEY, no fake
    out = book(pv, user)
    assert not runs(db) and "ikke fundet en hjemmeside" in texts(out)
    assert any(m["kind"] == "call_proposal" for m in out["messages"]) and world.places.calls == 0 and not world.site.fetched
    row = db.scalar(select(ExternalBusinessContact))
    assert row.website is None and row.cvr == "12345674"                                 # the CVR part was still used


def test_an_unknown_booking_engine_is_the_phone(api, db, pv, user, world):
    world.site.html = SITE_NONE
    out = book(pv, user)
    assert not runs(db) and "bookingsystem" in texts(out) and any(m["kind"] == "call_proposal" for m in out["messages"])
    assert db.scalar(select(ExternalBusinessContact)).booking_profile_id is not None     # remembered: not looked up again


def test_no_concrete_booking_asks_and_starts_nothing(api, db, pv, user, world):
    out = book(pv, user, service="", preferred_windows=[])
    assert not runs(db) and "Hvilken ydelse skal jeg booke hos Salon Test" in texts(out)
    assert db.scalar(select(PrivateTask).where(PrivateTask.kind == "call")) is None      # not even a task
    out = book(pv, user, service="herreklip", preferred_windows=[{"date": "2020-01-01"}, {"date": "i morgen"}])  # past / junk dates
    assert not runs(db)


def test_the_profile_must_have_a_verified_mobile(api, db, pv, world):
    tok = pv.account("anna@testmail.dk")                                                 # no verify_phone
    out = book(pv, tok)
    assert not runs(db) and "bekræftede mobilnummer" in texts(out)


def test_without_balance_the_phone_is_the_track(api, db, pv, user, world):
    with_db = db
    ws = pv.ws(user)
    ledger.add(with_db, ws, kind="spend", amount=-ledger.balance(with_db, ws), source_ref="test:drain", text="drain")
    with_db.commit()
    out = book(pv, user)
    assert not runs(db) and "opkaldssaldo" in texts(out) and any(m["kind"] == "call_proposal" for m in out["messages"])


def test_a_booking_that_cannot_be_planned_falls_to_the_phone_and_leaves_nothing_behind(api, db, pv, user, world, monkeypatch):
    def boom(*a, **k):
        from app.core.errors import ValidationFailed

        raise ValidationFailed("x")

    monkeypatch.setattr(service, "start_run", boom)
    out = book(pv, user)
    assert not runs(db) and any(m["kind"] == "call_proposal" for m in out["messages"])
    assert db.scalar(select(PrivateTask).where(PrivateTask.status == "in_progress")) is None


# --- the lookup cache ----------------------------------------------------------------------------------------------------

def test_a_business_is_looked_up_once(api, db, pv, user, world):
    book(pv, user, user_said_track="ring")
    assert (world.cvr.calls, world.places.calls) == (1, 1)
    book(pv, user, user_said_track="ring")
    assert (world.cvr.calls, world.places.calls) == (1, 1)                                # no second paid lookup
    [row] = list(db.scalars(select(ExternalBusinessContact)))
    assert (row.cvr, row.phone_e164, row.website, row.place_id) == ("12345674", "+4586123456", "https://salon-test.dk", "ChIJsalon")
    assert row.advertising_protected is True and row.opening_hours and row.address == "Testvej 1"


def test_the_same_business_under_another_spelling_is_one_row(api, db, pv, user, world):
    book(pv, user, user_said_track="ring")
    book(pv, user, name="Salon Test ApS", city="Århus", user_said_track="ring")
    assert len(list(db.scalars(select(ExternalBusinessContact)))) == 1                    # same CVR


def test_google_content_is_dropped_after_the_cache_days_but_place_id_and_register_facts_stay(db, pv, user, world):
    class Ctx:
        ws_id = pv.ws(user)
        profile = None

    from app.models import PrivateProfile

    Ctx.profile = db.scalar(select(PrivateProfile).where(PrivateProfile.workspace_id == Ctx.ws_id))
    lookup.find_business(db, Ctx, "Salon Test", "Aarhus")
    db.commit()
    later = rules.now() + timedelta(days=get_settings().google_places_cache_days + 1)
    assert lookup.scrub_expired(db, later) == 1
    row = db.scalar(select(ExternalBusinessContact))
    assert (row.website, row.opening_hours, row.google_looked_up_at) == (None, None, None)
    assert (row.place_id, row.cvr, row.phone_e164, row.advertising_protected) == ("ChIJsalon", "12345674", "+4586123456", True)


def test_the_website_comes_from_google_only_never_from_the_register(db, pv, user, world):
    world.places.website = None                                                           # Google has no website; CVR lists one
    from app.models import PrivateProfile

    class Ctx:
        ws_id = pv.ws(user)

    Ctx.profile = db.scalar(select(PrivateProfile).where(PrivateProfile.workspace_id == Ctx.ws_id))
    b = lookup.find_business(db, Ctx, "Salon Test", "Aarhus")
    assert b.website is None and b.phone_e164 == "+4586123456"


# --- «ring i stedet» ------------------------------------------------------------------------------------------------------

def awaiting_run(db, pv, user, world):
    book(pv, user)
    [run] = runs(db)
    assert service.cas(db, run.id, "planned", "running")
    assert service.enter_awaiting(db, run.id, {"service": "Herreklip", "date": "tirsdag 10. november 2026", "time": "10:30",
                                               "price": "350 kr.", "name": "Mette Hansen"})
    db.commit()
    return run.id, db.get(BrowserRun, run.id).task_id


def say_switch(pv, tok, tid):
    ai_provider.set_provider_override(ChatModel(lambda m: [("switch_to_phone", {})]))
    return pv.say(tok, "Ring i stedet", about=str(tid))


def test_ring_i_stedet_cancels_the_run_releases_the_reservation_and_prepares_the_call(api, db, pv, user, world):
    rid, tid = awaiting_run(db, pv, user, world)
    assert ledger.balance(db, pv.ws(user)) == 1000 - 290                                 # 10 kr. welcome - 2,90 reserved
    out = say_switch(pv, user, tid)
    db.expire_all()
    run = db.get(BrowserRun, rid)
    assert (run.status, run.error_code) == ("fallback_phone", "user_switched")
    assert "Okay, jeg ringer til Salon Test i stedet" in texts(out) and any(m["kind"] == "call_proposal" for m in out["messages"])
    assert ledger.balance(db, pv.ws(user)) == 1000                                       # the reservation is back
    task = api.get(user, f"/privat/tasks/{tid}").json()
    assert task["status"] == "awaiting_user" and task["call"]["result"] is None          # a proposal, nothing dialled
    again = say_switch(pv, user, tid)                                                    # a second «ring i stedet» changes nothing
    assert ledger.balance(db, pv.ws(user)) == 1000 and len(list(db.scalars(select(PrivateCall)))) == 1
    assert "ingen booking" in texts(again).lower()


def test_ring_i_stedet_is_refused_once_the_confirming_click_may_be_made(api, db, pv, user, world):
    rid, tid = awaiting_run(db, pv, user, world)
    assert service.cas(db, rid, "awaiting_approval", "approved") and service.cas(db, rid, "approved", "running")
    run = db.get(BrowserRun, rid)
    run.result = {"_confirming": True}
    db.commit()
    out = say_switch(pv, user, tid)
    db.expire_all()
    assert db.get(BrowserRun, rid).status == "running"
    assert "kan ikke fortrydes" in texts(out) and "Tjek hos virksomheden" in texts(out)
    assert ledger.balance(db, pv.ws(user)) == 710


# --- the Opkaldssaldo through the whole life of a run -----------------------------------------------------------------------------------

def _run(db, pv, user, world):
    book(pv, user)
    [r] = runs(db)
    assert service.cas(db, r.id, "planned", "running")
    return r.id


@pytest.mark.parametrize("finish,args,balance", [
    (service.finish_done, ({"summary": {}},), 710),                                       # spent: the reservation is the price
    (service.finish_failed, ("unexpected_commit",), 710),                                 # may have booked: spent
    (service.finish_failed, ("commit_unconfirmed",), 710),
    (service.finish_failed, ("declined",), 1000),                                         # nothing booked: released
    (service.finish_failed, ("forbidden_field",), 1000),
    (service.finish_fallback, ("captcha", {}), 1000),
])
def test_the_reservation_is_spent_or_released_exactly_once(api, db, pv, user, world, finish, args, balance):
    rid = _run(db, pv, user, world)
    assert ledger.balance(db, pv.ws(user)) == 710
    for _ in range(2):                                                                    # a repeat moves nothing twice
        finish(db, db.get(BrowserRun, rid), *args)
        db.commit()
    assert ledger.balance(db, pv.ws(user)) == balance
    assert ledger.reserved(db, pv.ws(user)) == 0                                          # no reservation is left hanging


def test_a_run_needs_the_price_on_the_balance_to_start(api, db, pv, user, world):
    from app.core.errors import Conflict

    ws = pv.ws(user)
    ledger.add(db, ws, kind="spend", amount=-(1000 - 289), source_ref="test:drain", text="drain")  # 2,89 kr. left
    db.commit()
    task = PrivateTask(workspace_id=ws, kind="call", title="x", status="awaiting_user", next_step="", paid_by="call")
    db.add(task)
    db.flush()
    with pytest.raises(Conflict) as e:
        service.start_run(db, task, goal={"intent": "book", "service": "x", "contact": {"name": "M"}},
                          allowed_domains=["salon-test.dk"], engine="onlinebooq", booking_url="https://salon-test.dk/b")
    assert e.value.code == "insufficient_balance"
    db.rollback()


def test_find_business_never_invents(api, db, pv, user, world, monkeypatch):
    monkeypatch.setattr(cvr_register, "search_by_name", Cvr([]))
    gp._override = None
    ai_provider.set_provider_override(ChatModel(lambda m: [("find_business", {"name": "Findes ikke", "city": "Aarhus"})]))
    out = pv.say(user, "Book hos Findes ikke")
    assert "kunne ikke finde" in texts(out) and not db.scalar(select(ExternalBusinessContact))
    assert uuid.UUID(str(uuid.uuid4()))

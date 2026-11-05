"""Dialogbot Privat: the household apps – Abonnementer & opsigelse, Håndværker & tilbud, Fælles udgifter, Garanti &
kvitteringer, Fest & invitationer, Flytning, Kæledyr, Hus & vedligehold, Fitness & sundhed – and the expanded Madplan.
No real call, search or partner is ever reached: the business search is replaced and no call is ever dialled."""
from __future__ import annotations

import json
from datetime import UTC, date, datetime

import pytest

from app.config import get_settings
from app.models import OutboxEvent, PrivateBusinessReferral, PrivateCall
from app.modules.campaigns import service as campaigns
from app.modules.privat import app_kit, brand, expenses, home, meals, places, subs_app, warranty
from tests.privat_fixtures import WED_10

# WED_10 = Wednesday 4 November 2026, 10:00 in Copenhagen


def _on(api, tok, key):
    r = api.post(tok, f"/privat/addons/{key}/enable")
    assert r.status_code == 200, r.text


def _last(out) -> str:
    return out["messages"][-1].get("text") or ""


@pytest.fixture(autouse=True)
def _never_dial(monkeypatch):
    called = []
    monkeypatch.setattr(campaigns, "create_call", lambda p: called.append(p) or {"id": "x"})
    yield
    assert called == []                                  # nothing in these tests is ever dialled


@pytest.fixture
def partners(monkeypatch):
    monkeypatch.setenv("PRIVAT_PARTNER_LINKS", json.dumps({
        "mobil": {"name": "Testmobil", "url": "https://partner.example/mobil", "text": "Find et billigere mobilabonnement"},
        "dagligvarer": {"name": "Testkøb", "url": "https://partner.example/mad", "text": "Bestil varerne hjem"},
        "evil": {"name": "x", "url": "https://x"}, "fest": {"name": "Http", "url": "http://not-https"}}))
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_every_app_is_in_the_shop_and_switches_on(api, pv):
    tok = pv.account("mette@testmail.dk")
    cat = {a["key"]: a for a in api.get(tok, "/privat/addons").json()}
    for key in app_kit.MODULES:
        assert cat[key]["status"] == "available", key
        _on(api, tok, key)
        body = api.get(tok, f"/privat/apps/{key}/overview").json()
        assert body["items"] == [] and body["summary"] and body["partner"] is None, key
    assert cat["fest"]["included_in"] == [] and cat["faelles-udgifter"]["included_in"] == []     # free: they spread


def test_partner_links_are_always_marked_and_only_https(partners):
    o = brand.offer("mobil")
    assert o["url"] == "https://partner.example/mobil" and "Annonce" in o["note"] and "provision" in o["note"]
    assert brand.offer("fest") is None and brand.offer("evil") is None and brand.offer(None) is None
    assert "Annonce" in brand.offer_line("dagligvarer") and brand.offer_line("hjem") == ""


# --------------------------------------------------------------------------- Abonnementer

def test_subscriptions_saved_cancelled_by_letter_and_reminded(api, pv, db, partners):
    tok = pv.account("mette@testmail.dk")
    out = pv.say(tok, "Jeg har Netflix til 139 kr. om måneden")
    assert any(m["kind"] == "addon" and m.get("addon_key") == "abonnementer" for m in out["messages"])
    _on(api, tok, "abonnementer")
    out = pv.say(tok, "Jeg har Netflix til 139 kr. om måneden og Telia til 199 kr. med binding til 2026-11-30")
    assert "338 kr. om måneden" in _last(out) and "4.056 kr. om året" in _last(out)
    body = api.get(tok, "/privat/apps/abonnementer/overview").json()
    assert [i["text"].split(",")[0] for i in body["items"]] == ["Telia", "Netflix"]
    assert body["partner"]["name"] == "Testmobil"                      # a mobile subscription → the mobile partner
    out = pv.say(tok, "Opsig Netflix")
    text = _last(out)
    assert "Opsigelse af abonnement – Netflix" in text and "Sendt med Dialogbot" in text and "Mette Hansen" in text
    # Telia: the last day to give notice (30 days before 30/11 = 31/10) has passed; nothing, then a later binding is reminded
    assert app_kit.send_due(db, WED_10) == 0
    pv.say(tok, "Jeg har Telia til 199 kr. med binding til 2026-12-10")
    assert app_kit.send_due(db, WED_10) == 1                           # last day 10/11: within 10 days
    db.commit()
    assert app_kit.send_due(db, WED_10) == 0                           # once
    [ev] = db.query(OutboxEvent).filter(OutboxEvent.dedupe_key.like("privat-notify:abonnementer:%")).all()
    assert "Sidste dag at opsige Telia" in str(ev.payload)


def test_cancel_by_call_is_a_proposal_with_a_number_the_user_typed(api, pv, db):
    tok = pv.account("mette@testmail.dk")
    _on(api, tok, "abonnementer")
    out = pv.say(tok, "Opsig Viaplay og ring til dem på 70 20 30 40")
    assert out["messages"][-1]["kind"] == "call_proposal"
    c = db.query(PrivateCall).one()
    assert c.status == "proposed" and c.business_phone_e164 == "+4570203040" and "binding" in c.may_not
    # a proposal is not a cancellation: the subscription stays active until the call is made
    assert "under opsigelse" not in api.get(tok, "/privat/apps/abonnementer/overview").json()["items"][0]["text"]


def test_subscription_unit():
    row = {"id": "a", "name": "Telia", "binding_until": "2027-03-01", "notice_days": 30, "status": "active",
           "price_minor": 120000, "period": "yearly"}
    assert subs_app.last_notice_day(row) == date(2027, 1, 30) and subs_app.monthly_minor(row) == 10000
    assert [t for t, _ in subs_app.due({"items": [row]}, date(2027, 1, 25))] == ["notice:a:2027-01-30"]


# --------------------------------------------------------------------------- Håndværker & tilbud

FOUND = [{"name": "Maler Jensen", "phone_e164": "+4586111111", "address": "Vej 1, Aarhus", "place_id": "p1", "source": "google"},
         {"name": "Farve & Co", "phone_e164": "+4586222222", "address": "Vej 2, Aarhus", "place_id": "p2", "source": "google"},
         {"name": "Uden Nummer", "phone_e164": None, "address": "Vej 3", "place_id": "p3", "source": "google"}]


def test_quotes_are_proposals_and_the_choice_is_the_lead(api, pv, db, monkeypatch):
    seen = []
    monkeypatch.setattr(places, "search", lambda db, ctx, q, city=None, **k: seen.append((q, city)) or FOUND)
    tok = pv.account("mette@testmail.dk")
    _on(api, tok, "haandvaerker")
    out = pv.say(tok, "Find 3 malere i Aarhus og hent tilbud på at male stuen")
    assert seen == [("mal", "Aarhus")] or seen[0][1] == "Aarhus"
    assert [m["kind"] for m in out["messages"]].count("call_proposal") == 2      # the one without a number is left out
    calls = db.query(PrivateCall).order_by(PrivateCall.created_at).all()
    assert all(c.status == "proposed" for c in calls)                            # nothing dialled before the yes
    assert "Få et tilbud på at male stuen" == calls[0].purpose and "Sige ja til opgaven" in calls[0].may_not
    refs = db.query(PrivateBusinessReferral).all()
    assert sorted(r.business_name for r in refs) == ["Farve & Co", "Maler Jensen"] and {r.status for r in refs} == {"asked"}
    # the replies come in (as the call report would set them) and are shown side by side
    calls[0].status, calls[0].business_reply, calls[0].business_price_text = "answered", "Kan i uge 48", "ca. 9.000 kr."
    calls[1].status = "no_answer"
    db.commit()
    text = _last(pv.say(tok, "Vis tilbuddene"))
    assert "1. Maler Jensen: Kan i uge 48 Pris: ca. 9.000 kr." in text and "2. Farve & Co: tog ikke telefonen" in text
    assert "Sig hvem du vælger" in text
    out = pv.say(tok, "Jeg vælger tilbuddet fra Maler Jensen")
    assert out["messages"][-1]["kind"] == "call_proposal"
    db.expire_all()
    by = {r.business_name: r.status for r in db.query(PrivateBusinessReferral)}
    assert by == {"Maler Jensen": "chosen", "Farve & Co": "not_chosen"}
    yes = db.query(PrivateCall).filter(PrivateCall.purpose.like("Sig ja tak%")).one()
    assert yes.business_phone_e164 == "+4586111111" and yes.status == "proposed" and "endelige aftale" in yes.may_not
    body = api.get(tok, "/privat/apps/haandvaerker/overview").json()
    assert body["partner"] is None and "Valgt: Maler Jensen" in body["items"][0]["sub"]   # never an ad next to them


# --------------------------------------------------------------------------- Fælles udgifter

def test_expenses_settle_with_fewest_transfers_and_a_branded_summary(api, pv):
    tok = pv.account("mette@testmail.dk")
    _on(api, tok, "faelles-udgifter")
    out = pv.say(tok, "Jeg betalte 1.200 kr. for mad i sommerhuset – vi er Anna, Bo og mig")
    assert "Mette betaler" not in _last(out) and "Anna betaler 400 kr. til Mette" in _last(out)
    pv.say(tok, "Anna betalte 300 kr. for vin")
    text = _last(pv.say(tok, "Hvem skylder hvem? Send opgørelsen"))
    assert "Bo betaler 500 kr. til Mette" in text and "Anna betaler 200 kr. til Mette" in text
    assert "Sendt med Dialogbot" in text
    item = api.get(tok, "/privat/apps/faelles-udgifter/overview").json()["items"][0]
    assert item["text"] == "sommerhuset" or item["text"].lower() == "sommerhuset" and "Dialogbot" in item["share_text"]


def test_settle_unit_rounds_to_the_øre():
    g = {"name": "x", "people": ["A", "B", "C"], "expenses": [{"payer": "A", "amount_minor": 1000, "among": None}]}
    assert sum(expenses.balances(g).values()) == 0
    assert expenses.settle(g) == [("B", "A", 333), ("C", "A", 333)] or sorted(n for *_, n in expenses.settle(g)) == [333, 334]


# --------------------------------------------------------------------------- Garanti & kvitteringer

def test_purchase_complaint_and_reminder(api, pv, db):
    tok = pv.account("mette@testmail.dk")
    _on(api, tok, "garanti")
    out = pv.say(tok, "Jeg købte en vaskemaskine i Elgiganten den 2024-11-20 til 4.999 kr.")
    assert "reklamationsret til 20. november 2026" in _last(out)
    text = _last(pv.say(tok, "Skriv en reklamation på vaskemaskinen – den lækker vand"))
    assert "købeloven § 83" in text and "Fejlen: Den lækker vand." in text
    assert "Sendt med Dialogbot" in text
    assert app_kit.send_due(db, WED_10) == 1                   # 16 days left of the 2 years
    db.commit()


def test_warranty_unit():
    row = {"id": "a", "name": "TV", "bought": "2026-01-10", "warranty_years": 5}
    assert warranty.reklamation_until(row) == date(2028, 1, 10) and warranty.warranty_until(row) == date(2031, 1, 10)
    assert "inden for det første år" in warranty.complaint(row, "skærmen er sort", "Mette", date(2026, 6, 1))


# --------------------------------------------------------------------------- Fest & invitationer

def test_party_guests_and_branded_invitation(api, pv, db):
    tok = pv.account("mette@testmail.dk")
    _on(api, tok, "fest")
    out = pv.say(tok, "Lav en fest: Idas fødselsdag den 2026-11-11 kl. 14 med Emma, Noah og Alma")
    assert "3 har ikke svaret" in _last(out)
    pv.say(tok, "Emma kommer til festen og tager kage med")
    pv.say(tok, "Noah kommer ikke til festen")
    text = _last(pv.say(tok, "Skriv invitationen"))
    assert text.count("Idas fødselsdag") == 1 and "11. november 2026 kl. 14" in text and "Sendt med Dialogbot" in text
    assert app_kit.send_due(db, WED_10) == 1                   # a week before: Alma has not answered
    db.commit()
    ev = db.query(OutboxEvent).filter(OutboxEvent.dedupe_key.like("privat-notify:fest:%")).one()
    assert "Alma" in str(ev.payload) and "Emma" not in str(ev.payload["email"])


# --------------------------------------------------------------------------- Flytning

def test_moving_checklist_with_dates_and_partners(api, pv, db, partners):
    tok = pv.account("mette@testmail.dk")
    _on(api, tok, "flytning")
    out = pv.say(tok, "Vi flytter til Odense den 2026-12-04")
    tid = next(m["task_id"] for m in out["messages"] if m["kind"] == "task")
    t = pv.task(tok, tid).json()
    assert t["title"] == "Flytning: Odense" and len(t["items"]) == 12
    assert t["items"][10]["text"] == "Meld flytning på borger.dk (fra flyttedagen og senest 5 dage efter) (5. december 2026)"
    assert app_kit.send_due(db, WED_10) == 2                   # 30 days before: internet, and institution/work


# --------------------------------------------------------------------------- Kæledyr

def test_pet_vet_and_reminders(api, pv, db):
    tok = pv.account("mette@testmail.dk")
    _on(api, tok, "kaeledyr")
    out = pv.say(tok, "Vores hund Bella skal vaccineres 2026-11-12 og have ormekur hver 3. måned")
    assert "vaccination 12. november 2026" in _last(out) and "ormekur 4. februar 2027" in _last(out)   # never today
    pv.say(tok, "Gem dyrlægen: Dyreklinikken Syd, nummer 86 33 44 55")
    out = pv.say(tok, "Book dyrlægen til Bella")
    assert out["messages"][-1]["kind"] == "call_proposal"
    assert db.query(PrivateCall).one().business_phone_e164 == "+4586334455"
    assert app_kit.send_due(db, WED_10) == 1                   # vaccination in 8 days


# --------------------------------------------------------------------------- Hus & vedligehold

def test_home_jobs_remind_and_roll_on(api, pv, db):
    tok = pv.account("mette@testmail.dk")
    _on(api, tok, "hus-og-vedligehold")
    out = pv.say(tok, "Tilføj alle de faste opgaver i huset")
    assert "Rens tagrenderne: næste gang 4. november 2026" in _last(out)       # its month is now: today, not the 1st
    assert app_kit.send_due(db, WED_10) >= 1
    db.commit()
    out = pv.say(tok, "Jeg har testet røgalarmerne")
    assert "Test røgalarmerne: næste gang 4. februar 2027" in _last(out)


def test_home_unit():
    assert home._next(date(2026, 11, 4), 9) == date(2027, 9, 1) and home._next(date(2026, 11, 4), 11) == date(2026, 11, 4)
    assert home._next(date(2026, 11, 4), 12) == date(2026, 12, 1)


# --------------------------------------------------------------------------- Fitness & sundhed

def test_fitness_plan_log_and_nudge(api, pv, db):
    tok = pv.account("mette@testmail.dk")
    _on(api, tok, "fitness-og-sundhed")
    out = pv.say(tok, "Jeg vil løbe onsdag og fredag kl. 17 – målet er 5 km i maj")
    assert "Mål: 5 km i maj" in _last(out) and "Onsdag: Løb kl. 17:00" in _last(out)
    assert app_kit.send_due(db, WED_10) == 1                   # today is Wednesday
    db.commit()
    out = pv.say(tok, "Færdig med løb 30 min")
    assert "Noteret: Løb, 30 min" in _last(out) and "Denne uge: 1 træninger (30 min) af 2 planlagte." in _last(out)


# --------------------------------------------------------------------------- Madplan (expanded)

def test_meal_amounts_scale_and_add_up():
    days = [{"dish": "Lasagne", "servings": 4, "ingredients": ["500 g hakket oksekød", "1 dåse tomater", "Lasagneplader"]},
            {"dish": "Chili", "servings": 4, "ingredients": ["250 g hakket oksekød", "1 ds. tomater", "2 løg"]}]
    assert meals.merge_ingredients(days) == ["750 g hakket oksekød", "2 dåser tomater", "Lasagneplader", "2 løg"]
    assert meals.merge_ingredients([{"dish": "a", "ingredients": ["2 peberfrugt", "1 tomat"]},
                                    {"dish": "b", "ingredients": ["2 peberfrugter", "2 tomater"]}]) == ["4 peberfrugter", "3 tomater"]
    assert meals.merge_ingredients(days, 8) == ["1,5 kg hakket oksekød", "4 dåser tomater", "Lasagneplader", "4 løg"]
    assert meals.dish_ingredients(days[0], 2) == ["250 g hakket oksekød", "1 dåse tomater", "Lasagneplader"]
    assert meals.parse_ingredient("2 store løg") == (2, "", "store løg") and meals.parse_ingredient("Salt") == (None, "", "Salt")


def test_meal_plan_notes_and_the_grocery_partner(api, pv, partners):
    tok = pv.account("mette@testmail.dk")
    _on(api, tok, "madplan")
    out = pv.say(tok, "Ja, gem madplanen")
    assert "Bestil varerne hjem: https://partner.example/mad" in _last(out) or any(
        "partner.example/mad" in (m.get("text") or "") for m in out["messages"])
    plan = next(m["task_id"] for m in out["messages"] if m["kind"] == "task")
    items = pv.task(tok, plan).json()["items"]
    assert items[0]["note"] == "500 g hakket oksekød, Lasagneplader, Tomatsauce"


def test_reminders_wait_until_8_and_skip_switched_off_apps(api, pv, db):
    tok = pv.account("mette@testmail.dk")
    _on(api, tok, "fitness-og-sundhed")
    pv.say(tok, "Jeg vil løbe onsdag kl. 17")
    assert app_kit.send_due(db, datetime(2026, 11, 4, 6, 0, tzinfo=UTC)) == 0      # 07:00 in Copenhagen
    api.post(tok, "/privat/addons/fitness-og-sundhed/disable")
    assert app_kit.send_due(db, WED_10) == 0
    assert api.get(tok, "/privat/apps/fitness-og-sundhed/overview").status_code == 403
    assert api.get(tok, "/privat/apps/nope/overview").status_code == 404


# --------------------------------------------------------------------------- the assistant's name

def test_the_assistant_can_be_renamed_and_the_texts_follow(api, pv):
    tok = pv.account("mette@testmail.dk")
    assert api.get(tok, "/privat/me").json()["assistant_name"] == "Peter"
    r = api.patch(tok, "/privat/me/assistant", {"name": "  ida  "})
    assert r.status_code == 200 and r.json()["assistant_name"] == "Ida"
    car = next(a for a in api.get(tok, "/privat/addons").json() if a["key"] == "bil-og-syn")
    assert "Peter" not in car["what"] + car["tagline"] + " ".join(car["steps"]) and "Ida" in car["what"]
    _on(api, tok, "abonnementer")
    assert "Fortæl Ida" in api.get(tok, "/privat/apps/abonnementer/overview").json()["summary"]
    r = api.patch(tok, "/privat/me/assistant", {"name": "Ida", "pronoun": "hun"})
    assert r.json()["assistant_pronoun"] == "hun"
    car = next(a for a in api.get(tok, "/privat/addons").json() if a["key"] == "bil-og-syn")
    assert "Han " not in car["what"] and "han " not in car["what"] and ("Hun " in car["what"] or "hun " in car["what"])
    api.patch(tok, "/privat/me/assistant", {"name": "Max"})          # no pronoun given: never a guessed gender
    assert api.get(tok, "/privat/me").json()["assistant_pronoun"] == "den"
    assert api.patch(tok, "/privat/me/assistant", {"name": "Max", "pronoun": "it"}).status_code == 422
    for bad in ("Dialogbot", "x" * 21, "Bob<script>", "Politiet"):
        assert api.patch(tok, "/privat/me/assistant", {"name": bad}).status_code == 422, bad
    assert api.patch(tok, "/privat/me/assistant", {"name": ""}).json()["assistant_name"] == "Peter"


def test_the_chat_model_is_told_its_name(db, pv, api, monkeypatch):
    from app.modules.privat import chat

    seen = []
    real = chat.SYSTEM.format
    monkeypatch.setattr(chat, "SYSTEM", type("S", (str,), {"format": lambda self, **k: seen.append(k["bot"]) or real(**k)})(chat.SYSTEM))
    tok = pv.account("mette@testmail.dk")
    api.patch(tok, "/privat/me/assistant", {"name": "Max"})
    pv.say(tok, "Lav en liste med mælk")
    assert seen and seen[-1] == "Max"


def test_operator_sees_the_lead_ledger(api, pv, db, monkeypatch):
    monkeypatch.setattr(places, "search", lambda db, ctx, q, city=None, **k: FOUND)
    tok = pv.account("mette@testmail.dk")
    _on(api, tok, "haandvaerker")
    pv.say(tok, "Find 3 malere i Aarhus og hent tilbud på at male stuen")
    pv.say(tok, "Jeg vælger tilbuddet fra Maler Jensen")
    assert api.get(tok, "/operator/privat/business-referrals").status_code == 403          # not for users
    items = api.get(api.operator(), "/operator/privat/business-referrals").json()["items"]
    assert items[0] == {**items[0], "business_name": "Maler Jensen", "asked": 1, "chosen": 1}
    assert {i["business_name"] for i in items} == {"Maler Jensen", "Farve & Co"}

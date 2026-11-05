"""Dialogbot Privat, the Rejser app (step 1): trip searches with real prices only (a provider test double here – no
travel API is ever called), the total budget, «Book» hands over to the seller; nothing is booked in Dialogbot."""
from __future__ import annotations

import pytest

from app.config import get_settings
from app.core.errors import ValidationFailed
from app.modules.privat import travel
from tests.privat_fixtures import WED_10

TODAY = WED_10.date()


def test_validation_explains_what_is_missing():
    with pytest.raises(ValidationFailed, match="Hvorfra"):
        travel.validate({"destinations": ["BCN"], "month": "2027-02"}, TODAY)
    with pytest.raises(ValidationFailed, match="Hvorhen"):
        travel.validate({"origin": "CPH", "destinations": ["CPH", "nope"], "month": "2027-02"}, TODAY)
    with pytest.raises(ValidationFailed, match="Hvornår"):
        travel.validate({"origin": "CPH", "destinations": ["BCN"]}, TODAY)
    with pytest.raises(ValidationFailed, match="inden for det næste år"):
        travel.validate({"origin": "CPH", "destinations": ["BCN"], "depart_date": "2026-01-01"}, TODAY)
    p = travel.validate({"origin": "bll", "destinations": ["bcn", "LIS", "x"], "depart_date": "2027-02-10", "nights": 7,
                         "adults": 2, "children": 2, "budget_dkk": 12000}, TODAY)
    assert p["origin"] == "BLL" and p["destinations"] == ["BCN", "LIS"] and travel._return_date(p) == "2027-02-17"


def test_the_app_waits_for_a_provider_key(api, pv):
    tok = pv.account("mette@testmail.dk")
    cat = {a["key"]: a["status"] for a in api.get(tok, "/privat/addons").json()}
    assert cat["rejser"] == "coming_soon"


@pytest.fixture
def fake_travel(monkeypatch):
    monkeypatch.setenv("TRAVELPAYOUTS_TOKEN", "fake")
    get_settings.cache_clear()
    travel.FakeProvider.prices = {}
    yield travel.FakeProvider
    get_settings.cache_clear()


def test_search_real_prices_only_cheapest_first_within_budget(api, pv, fake_travel):
    tok = pv.account("mette@testmail.dk")
    assert api.post(tok, "/privat/addons/rejser/enable").status_code == 200
    fake_travel.prices = {"BCN": [11800, 14500], "LIS": [9900], "AGP": []}
    r = api.post(tok, "/privat/trips/search", {"origin": "BLL", "destinations": ["BCN", "LIS", "AGP"], "month": "2027-02",
                                               "nights": 7, "adults": 2, "children": 2, "budget_dkk": 12000})
    assert r.status_code == 200, r.text
    body = r.json()
    assert [(o["destination"], o["total_dkk"]) for o in body["offers"]] == [("LIS", 9900), ("BCN", 11800)]
    assert body["over_budget"] == 1 and all(o["book_url"].startswith("https://") for o in body["offers"])
    assert api.get(tok, "/privat/trips/latest").json()["search"]["id"] == body["id"]
    assert api.post(tok, "/privat/trips/search", {"origin": "BLL", "destinations": ["BCN"]}).status_code == 422


def test_chat_finds_beach_trips_and_says_where_to_book(api, pv, fake_travel):
    tok = pv.account("mette@testmail.dk")
    out = pv.say(tok, "Find en strandferie fra BLL i 2027-02 til 2 voksne og 2 børn for højst 12.000 kr")
    assert any(m["kind"] == "addon" and m.get("addon_key") == "rejser" for m in out["messages"])
    api.post(tok, "/privat/addons/rejser/enable")
    fake_travel.prices = {"LIS": [9900], "AGP": [10400], "BCN": [15000]}
    out = pv.say(tok, "Find en strandferie fra BLL i 2027-02 til 2 voksne og 2 børn for højst 12.000 kr")
    text = out["messages"][-1]["text"]
    assert text.startswith("Billigste fly for 2 voksne og 2 børn inden for 12.000 kr.:")
    assert "1. BLL→LIS 10/2: 9.900 kr. i alt" in text and "BCN" not in text
    assert "kan ændre sig" in text and "Apps → Rejser" in text
    out = pv.say(tok, "Find en rejse til BCN")          # no origin, no date: asks instead of guessing
    assert "Book" not in out["messages"][-1]["text"]


def test_no_provider_price_means_no_offer(api, pv, fake_travel):
    tok = pv.account("mette@testmail.dk")
    api.post(tok, "/privat/addons/rejser/enable")
    body = api.post(tok, "/privat/trips/search", {"origin": "CPH", "destinations": ["NRT"], "month": "2027-03"}).json()
    assert body["offers"] == [] and "ingen rejser" in travel.summary(body)

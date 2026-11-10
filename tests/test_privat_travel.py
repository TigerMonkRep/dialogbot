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


def test_duffel_asks_for_the_cheapest_offers_only_never_the_whole_list(monkeypatch):
    """A Duffel offer request answered with every offer is tens of MB of JSON; parsing it took the API down (OOM).
    The provider creates the request without offers and lists only the cheapest few."""
    import httpx

    calls: list[tuple[str, str, dict | None]] = []

    def fake_post(url, json=None, headers=None, timeout=None):
        calls.append(("POST", url, json))
        return httpx.Response(201, json={"data": {"id": "orq_1"}})

    def fake_get(url, params=None, headers=None, timeout=None):
        calls.append(("GET", url, params))
        return httpx.Response(200, json={"data": [
            {"total_amount": "1234.50", "total_currency": "DKK", "owner": {"name": "Testair"},
             "slices": [{"segments": [{"departing_at": "2026-12-03T07:00:00"}]},
                        {"segments": [{"departing_at": "2026-12-10T18:00:00"}]}]}]})

    monkeypatch.setattr(httpx, "post", fake_post)
    monkeypatch.setattr(httpx, "get", fake_get)
    p = travel.validate({"origin": "CPH", "destinations": ["BCN"], "depart_date": "2026-12-03", "nights": 7,
                         "adults": 2, "children": 0}, WED_10.date())
    offers = travel.Duffel("tok").search(p, "BCN")

    assert [c[0] for c in calls] == ["POST", "GET"]
    assert "return_offers=false" in calls[0][1]
    assert calls[1][2] == {"offer_request_id": "orq_1", "limit": travel.Duffel.MAX_OFFERS, "sort": "total_amount"}
    assert len(offers) == 1 and offers[0]["airline"] == "Testair" and offers[0]["total_dkk"] == 1234
    # «Book» opens the same journey: both dates and the passengers, not only the route
    assert "returning%202026-12-10" in offers[0]["book_url"] and "for%202%20adults" in offers[0]["book_url"]


def test_flexible_dates_passengers_in_the_link_and_airline_names():
    p = travel.validate({"origin": "CPH", "destinations": ["BCN"], "depart_date": "2026-12-03", "nights": 7,
                         "adults": 2, "children": 2}, TODAY)
    assert travel._fits("2026-12-05T08:00:00+01:00", "2026-12-12", p)          # 2 days later, 7 nights
    assert not travel._fits("2026-12-09", "2026-12-16", p)                     # 6 days later
    assert not travel._fits("2026-12-03", "2026-12-20", p)                     # a much longer stay
    assert travel._with_passengers("/search/CPH0312BCN10121?t=abc", p) == "/search/CPH0312BCN101222?t=abc"
    assert travel._with_passengers("/odd/link", p) == "/odd/link"
    o = travel._offer("x", "BCN", 1000.0, "DKK", airline="FR", p=p)
    assert o["airline"] == "Ryanair" and o["total_dkk"] == 1000


def test_foreign_currency_is_converted_with_the_ecb_rate_or_not_shown(monkeypatch):
    p = travel.validate({"origin": "CPH", "destinations": ["BCN"], "month": "2027-02"}, TODAY)
    monkeypatch.setattr(travel, "_rates", lambda: {"EUR": 1.0, "DKK": 7.46, "GBP": 0.85})
    o = travel._offer("duffel", "BCN", 100.0, "GBP", p=p)
    assert o["total_dkk"] == round(100 / 0.85 * 7.46) and "omregnet fra GBP" in o["price_note"]
    monkeypatch.setattr(travel, "_rates", lambda: {})
    assert travel._offer("duffel", "BCN", 100.0, "GBP", p=p)["total_dkk"] is None    # no rate: no price, never a guess


def test_empty_destination_gets_a_danish_message(api, pv, fake_travel):
    tok = pv.account("mette@testmail.dk")
    api.post(tok, "/privat/addons/rejser/enable")
    r = api.post(tok, "/privat/trips/search", {"origin": "CPH", "destinations": [], "month": "2027-02"})
    assert r.status_code == 422 and "Hvorhen" in r.text



def test_the_same_flight_is_shown_once(api, pv, fake_travel):
    """Same route, dates, airline and price from several fares (or both providers) is one line, not four."""
    tok = pv.account("mette@testmail.dk")
    api.post(tok, "/privat/addons/rejser/enable")
    fake_travel.prices = {"LIS": [9900, 9900, 9900, 9900, 10500]}
    body = api.post(tok, "/privat/trips/search", {"origin": "BLL", "destinations": ["LIS"], "month": "2027-02"}).json()
    assert [o["total_dkk"] for o in body["offers"]] == [9900, 10500]


def test_affiliate_booking_link_is_marked_as_an_ad(monkeypatch):
    """F-PX-04 (Fürster 2026-11-10): a Travelpayouts link carries Dialogbot's affiliate marker – the offer says
    `sponsored`, so the web shows «Annonce · Dialogbot får provision» and rel="sponsored". Duffel/fake: not sponsored."""
    from datetime import datetime as _dt

    import httpx

    from app.modules.privat import travel

    class R:
        status_code = 200

        def json(self):
            return {"success": True, "data": [{"price": 700, "airline": "FR", "departure_at": "2027-03-10T07:00:00+01:00",
                                               "transfers": 0, "link": "/search/CPH1003BCN1?t=x"}]}

    monkeypatch.setattr(httpx, "get", lambda *a, **k: R())
    p = travel.validate({"origin": "CPH", "destinations": ["BCN"], "month": "2027-03"}, _dt(2026, 11, 10).date())
    o = travel.Travelpayouts("tok", "M123").search(p, "BCN")[0]
    assert o["sponsored"] is True and "marker=M123" in o["book_url"]
    assert travel._offer("duffel", "BCN", 900.0, "DKK", book_url="https://x", p=p)["sponsored"] is False
    src = open("web/src/components/privat/travel.tsx", encoding="utf-8").read()
    assert 'rel={o.sponsored ? "sponsored noopener noreferrer"' in src and 't("travel.sponsored")' in src

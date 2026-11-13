"""The admin tab's backend: the go-live to-do list, the market list, the business search and the two-step campaign
(check the leads now, research and write them one request at a time)."""
from __future__ import annotations

from types import SimpleNamespace as NS

import httpx
import pytest

from app.core import safe_fetch
from app.modules.outreach import finder
from tests.outreach_fixtures import env

BASE = "/operator/outreach"
PLACES = {"places": [
    {"displayName": {"text": "Brightwater Plumbing LLC"}, "websiteUri": "https://brightwater.example/",
     "internationalPhoneNumber": "+1 512-555-0142", "businessStatus": "OPERATIONAL",
     "addressComponents": [{"types": ["locality"], "longText": "Austin"}, {"types": ["country"], "shortText": "US"}]},
    {"displayName": {"text": "Hidden Mail Plumbing"}, "websiteUri": "https://hidden.example/", "businessStatus": "OPERATIONAL",
     "addressComponents": [{"types": ["country"], "shortText": "US"}]},
    {"displayName": {"text": "No Site Plumbing"}, "businessStatus": "OPERATIONAL",
     "addressComponents": [{"types": ["country"], "shortText": "US"}]},
    {"displayName": {"text": "Closed Plumbing"}, "websiteUri": "https://closed.example/", "businessStatus": "CLOSED_PERMANENTLY"},
    {"displayName": {"text": "Tijuana Plomeros"}, "websiteUri": "https://tj.example/", "businessStatus": "OPERATIONAL",
     "addressComponents": [{"types": ["country"], "shortText": "MX"}]},
]}
PAGES = {
    "https://brightwater.example/": '<html><title>Brightwater</title><body><p>After hours? Leave a voicemail.</p>'
                                    '<img src="logo@2x.png"><a href="/contact">Contact</a></body></html>',
    "https://brightwater.example/contact": '<body>Mail <a href="mailto:joe@gmail.com">Joe</a> or '
                                           '<a href="mailto:office@brightwater.example">the office</a></body>',
    "https://hidden.example/": "<body><p>Call us.</p></body>",
}


@pytest.fixture
def places():
    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        seen.append(json.loads(request.content))
        return httpx.Response(200, json=PLACES)

    def fetch(url, _budget):
        if url not in PAGES:
            raise safe_fetch.FetchFailed("http", "404")
        return NS(url=url, text=PAGES[url])

    finder.set_overrides(transport=httpx.MockTransport(handler), fetch=fetch)
    yield seen
    finder.set_overrides()


def todo(data: dict, key: str) -> dict:
    return next(x for x in data["todos"] if x["key"] == key)


def test_overview_answers_while_switched_off_and_says_how_to_switch_on(db, api, two_workspaces, monkeypatch):
    monkeypatch.delenv("OUTREACH_MODE", raising=False)
    assert api.get(two_workspaces["tok_a"], f"{BASE}/overview").status_code == 403
    d = api.get(api.operator(), f"{BASE}/overview").json()
    assert d["mode"] == "off" and d["ready_for_dry_run"] is False and d["ready_for_live"] is False
    assert todo(d, "mode")["done"] is False and "OUTREACH_MODE=dry_run" in todo(d, "mode")["how"]
    assert [n["key"] for n in d["niches"]] == ["plumber", "hvac", "dentist", "med spa", "auto repair", "hair salon"]
    assert d["batches"] == [] and d["stats"]["queued"] == 0


def test_the_todo_list_follows_the_configuration(db, api, outreach, monkeypatch):
    d = api.get(api.operator(), f"{BASE}/overview").json()
    assert todo(d, "mode")["done"] is True
    open_live = {x["key"] for x in d["todos"] if not x["done"] and x["needed_for"] == "live"}
    assert {"demo", "postal", "inboxes", "provider", "webhooks", "prices", "legal_review", "sending_domain",
            "dry_run_read", "live"} <= open_live
    assert "US" in todo(d, "demo")["how"] and "UK" in todo(d, "demo")["how"]
    env(monkeypatch, OUTREACH_POSTAL_ADDRESS="Testvej 1, 8000 Aarhus C, Denmark", OUTREACH_SENDER_INBOXES="a@send.example",
        OUTREACH_RESEND_API_KEY="re_x", OUTREACH_WEBHOOK_SECRET="s", OUTREACH_DEMO_CALLBACK_COUNTRIES="DK,US,UK,IE,CA,AU,SE,FR,NO")
    d = api.get(api.operator(), f"{BASE}/overview").json()
    for key in ("postal", "inboxes", "provider", "webhooks", "demo"):
        assert todo(d, key)["done"] is True, key
    assert todo(d, "prices")["done"] is False and d["ready_for_live"] is False     # USD/GBP are still not billed
    assert d["stats"]["daily_capacity"] == 30


def test_manual_points_are_ticked_by_an_operator_and_automatic_ones_cannot_be(db, api, outreach, two_workspaces):
    op = api.operator()
    assert api.put(two_workspaces["tok_a"], f"{BASE}/todos/legal_review", {"done": True}).status_code == 403
    assert api.put(op, f"{BASE}/todos/legal_review", {"done": True}).status_code == 200
    assert api.put(op, f"{BASE}/todos/legal_review", {"done": True}).status_code == 200            # idempotent
    t = todo(api.get(op, f"{BASE}/overview").json(), "legal_review")
    assert t["done"] is True and t["kind"] == "manual" and t["done_at"]
    assert api.put(op, f"{BASE}/todos/postal", {"done": True}).status_code == 422                  # only the config can
    assert api.put(op, f"{BASE}/todos/legal_review", {"done": False}).status_code == 200
    assert todo(api.get(op, f"{BASE}/overview").json(), "legal_review")["done"] is False


def test_markets_show_what_each_country_allows(db, api, outreach, monkeypatch):
    m = {x["code"]: x for x in api.get(api.operator(), f"{BASE}/overview").json()["markets"]}
    assert m["US"]["state"] == "email" and m["US"]["price"] == "$349/mo" and m["US"]["demo_available"] is False
    assert m["UK"]["state"] == "email" and "Ltd" in m["UK"]["rules"]
    assert m["DK"]["state"] == "call_list" and m["DK"]["price"] is None and m["DK"]["demo_available"] is True
    assert m["DE"]["state"] == "blocked" and m["ES"]["state"] == "hold" and m["PL"]["state"] == "hold"
    env(monkeypatch, OUTREACH_SIGNED_OFF_MARKETS="ES")
    assert {x["code"]: x for x in api.get(api.operator(), f"{BASE}/overview").json()["markets"]}["ES"]["state"] == "email"


def test_search_finds_businesses_and_the_address_each_one_publishes(db, api, outreach, places):
    r = api.post(api.operator(), f"{BASE}/search", {"country": "US", "city": "Austin", "niche": "plumber", "limit": 10})
    assert r.status_code == 200, r.text
    c = {x["company_name"]: x for x in r.json()["candidates"]}
    assert set(c) == {"Brightwater Plumbing LLC", "Hidden Mail Plumbing", "No Site Plumbing"}   # closed and foreign are dropped
    b = c["Brightwater Plumbing LLC"]
    assert b["email"] == "office@brightwater.example"                  # own domain wins over the gmail address
    assert b["email_source"] == "published_website" and b["email_source_url"] == "https://brightwater.example/contact"
    assert b["city"] == "Austin" and b["phone"] == "+1 512-555-0142" and "voicemail" in b["context"] and b["problem"] is None
    assert c["Hidden Mail Plumbing"]["email"] is None and "Ingen e-mailadresse" in c["Hidden Mail Plumbing"]["problem"]
    assert "Ingen hjemmeside" in c["No Site Plumbing"]["problem"]
    assert places == [{"textQuery": "plumber in Austin", "regionCode": "US", "languageCode": "en", "pageSize": 10}]
    assert outreach.calls == []                                        # searching costs no Claude tokens


@pytest.mark.parametrize("country", ["DE", "DK", "ES", "XX"])
def test_a_closed_market_is_never_searched(db, api, outreach, places, country):
    r = api.post(api.operator(), f"{BASE}/search", {"country": country, "city": "Hamburg", "niche": "plumber"})
    assert r.status_code == 422 and r.json()["code"] == "market_closed" and places == []


def test_search_needs_outreach_on_and_a_places_key(db, api, outreach, two_workspaces, monkeypatch):
    body = {"country": "US", "city": "Austin", "niche": "plumber"}
    assert api.post(two_workspaces["tok_a"], f"{BASE}/search", body).status_code == 403
    env(monkeypatch, GOOGLE_PLACES_API_KEY="")
    r = api.post(api.operator(), f"{BASE}/search", body)
    assert r.status_code == 501 and r.json()["code"] == "places_not_configured"
    env(monkeypatch, OUTREACH_MODE="off")
    assert api.post(api.operator(), f"{BASE}/search", body).status_code == 501
    assert api.post(api.operator(), f"{BASE}/search", {**body, "niche": "law firm"}).status_code in (422, 501)


def test_a_campaign_is_checked_first_and_then_written_one_lead_at_a_time(db, api, outreach, places, monkeypatch):
    monkeypatch.setattr("app.modules.outreach.agents.sourcing.default_mx_check", lambda _d: True)
    op = api.operator()
    found = api.post(op, f"{BASE}/search", {"country": "US", "city": "Austin", "niche": "plumber"}).json()["candidates"]
    picked = [{k: v for k, v in c.items() if k != "problem"} for c in found if c["email"]]
    picked.append({"company_name": "Second Plumbing LLC", "email": "office@second.example", "country": "US", "niche": "plumber",
                   "context": "Review: I called three times and it went to voicemail every time."})
    picked.append({"company_name": "Müller GmbH", "email": "info@mueller.example", "country": "DE", "niche": "plumber"})
    r = api.post(op, f"{BASE}/batches", {"name": "austin-plumbers", "leads": picked, "research": False})
    assert r.status_code == 201 and r.json()["totals"] == {"qualified": 2, "blocked": 1}
    assert outreach.calls == []                                        # step 1 never calls Claude
    one = api.post(op, f"{BASE}/batches/austin-plumbers/process?limit=1", {}).json()
    assert one == {"processed": 1, "remaining": 1}
    assert api.post(op, f"{BASE}/batches/austin-plumbers/process?limit=1", {}).json() == {"processed": 1, "remaining": 0}
    assert api.post(op, f"{BASE}/batches/austin-plumbers/process?limit=1", {}).json() == {"processed": 0, "remaining": 0}
    d = api.get(op, f"{BASE}/overview").json()
    b = d["batches"][0]
    assert b["name"] == "austin-plumbers" and b["leads"] == 3 and b["totals"]["blocked"] == 1
    assert sum(b["totals"].values()) == 3 and d["stats"]["leads"]["blocked"] == 1
    rep = api.get(op, f"{BASE}/batches/austin-plumbers").json()
    second = next(x for x in rep["leads"] if x["email"] == "office@second.example")
    assert second["status"] == "queued" and second["email_draft"]["audit"]["passed"] is True
    assert d["stats"]["queued"] >= 1


def test_pick_email_ignores_images_and_tracking_addresses():
    html = 'x <img src="hero@2x.png"> a@sentry.io noreply@shop.example info%40shop.example owner@shop.example'
    assert finder.pick_email(html, "www.shop.example") == "info@shop.example"
    assert finder.pick_email("nothing here", "shop.example") is None

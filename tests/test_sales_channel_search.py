"""Internal sales channel, phase 1: access, mode gate, Google Places search job, duplicates, import, Google caching."""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import select

from app.config import get_settings
from app.models import (
    AuditLog,
    BusinessProfile,
    ReceptionAgreement,
    SalesCompany,
    SalesContact,
    SalesSearchJob,
    SalesSourceFact,
)
from app.modules.sales import places, search
from tests.sales_fixtures import fixture, run_search

ROUTES = [("get", "/operator/salg/industries"), ("get", "/operator/salg/search-jobs"),
          ("post", "/operator/salg/search-jobs"), ("get", "/operator/salg/companies"),
          ("post", "/operator/salg/companies/import"), ("get", "/operator/salg/integrations"),
          ("get", "/operator/salg/knowledge"), ("put", "/operator/salg/industries"),
          ("post", "/operator/salg/companies/00000000-0000-0000-0000-000000000000/simulate")]


def _call(api, tok, method, path):
    if method == "get":
        return api.get(tok, path)
    if method == "put":
        return api.put(tok, path, {})
    return api.post(tok, path, {})


def test_only_operators_and_off_means_501(api, two_workspaces, monkeypatch):
    tok = two_workspaces["tok_a"]
    assert api.get(tok, "/operator/salg").status_code == 403
    for method, path in ROUTES:
        assert _call(api, tok, method, path).status_code == 403, path
    op = api.operator()
    monkeypatch.setenv("SALES_OUTBOUND_MODE", "off")
    get_settings.cache_clear()
    st = api.get(op, "/operator/salg")
    assert st.status_code == 200 and st.json()["mode"] == "off"
    assert any("SALES_OUTBOUND_MODE" in m for m in st.json()["missing"])
    assert "GOOGLE_PLACES_API_KEY" not in json.dumps(st.json()["limits"])
    for method, path in ROUTES:
        r = _call(api, op, method, path)
        assert r.status_code == 501 and r.json()["code"] == "sales_channel_off", path
    monkeypatch.setenv("SALES_OUTBOUND_MODE", "research")
    get_settings.cache_clear()
    r = api.post(op, "/operator/salg/companies/00000000-0000-0000-0000-000000000000/simulate",
                 {"script_id": "00000000-0000-0000-0000-000000000000"})
    assert r.status_code == 501 and r.json()["code"] == "sales_mode_not_allowed"
    get_settings.cache_clear()


def test_live_mode_and_private_fetch_fail_closed(monkeypatch):
    from app.config import Settings

    with pytest.raises(ValueError, match="SALES_OUTBOUND_MODE=live requires"):
        Settings(DATABASE_URL="postgresql://x", SALES_OUTBOUND_MODE="live")
    with pytest.raises(ValueError, match="ALLOW_PRIVATE_FETCH"):
        Settings(DATABASE_URL="postgresql://x", APP_ENV="prod", SECRET_KEY="x" * 40, EMAIL_ADAPTER="resend",
                 RESEND_API_KEY="k", ENABLE_DEV_TOOLS=False, ALLOW_PRIVATE_FETCH=True)


def test_demo_search_by_industry_and_place(api, salg, db):
    op = salg["op"]
    r = api.post(op, "/operator/salg/search-jobs", {"industry_keys": ["skoenhed"], "geo_kind": "place",
                                                    "geo": {"text": "Aarhus C"}, "max_results": 20})
    assert r.status_code == 202, r.text
    job = r.json()
    assert job["source"] == "demo" and job["status"] == "queued"
    assert job["budget"]["estimate"]["search_requests_max"] == job["steps"] * 3
    assert job["budget"]["estimate"]["cost_minor_max"] > 0
    run_search(db)
    job = api.get(op, f"/operator/salg/search-jobs/{job['id']}").json()
    assert job["status"] == "done", job
    assert job["progress"]["found"] >= 3 and job["progress"]["examined"] >= job["progress"]["found"]
    rows = api.get(op, f"/operator/salg/companies?search_job={job['id']}").json()["items"]
    assert rows and all(c["source"] == "demo" for c in rows)
    assert all(c["domain"].endswith(".invalid") for c in rows if c["domain"])
    one = api.get(op, f"/operator/salg/companies/{rows[0]['id']}").json()
    assert {f["source"] for f in one["facts"]} == {"google"}
    assert all(f["url_or_ref"].startswith("google_place:") for f in one["facts"])
    assert one["contactable"]["result"] in ("BLOCK", "NEEDS_REVIEW")  # phase 1 never says ALLOW
    assert one["contacts"][0]["is_main_number"] is True
    # a second identical search adds no duplicates
    before = db.scalar(select(SalesCompany.id).where(SalesCompany.id == rows[0]["id"]))
    r = api.post(op, "/operator/salg/search-jobs", {"industry_keys": ["skoenhed"], "geo_kind": "place",
                                                    "geo": {"text": "Aarhus C"}, "max_results": 20})
    run_search(db)
    again = api.get(op, f"/operator/salg/search-jobs/{r.json()['id']}").json()
    assert again["progress"]["found"] == 0 and again["progress"]["reasons"].get("already_known", 0) >= 3
    assert before is not None
    assert db.scalar(select(AuditLog).where(AuditLog.action == "sales.search_created")) is not None


def test_validation_of_search_input(api, salg):
    op = salg["op"]
    bad = [({"industry_keys": ["findes_ikke"], "geo_kind": "place", "geo": {"text": "Aarhus C"}}, "industry_keys"),
           ({"industry_keys": [], "geo_kind": "place", "geo": {"text": "Aarhus C"}}, "industry_keys"),
           ({"industry_keys": ["skoenhed"], "geo_kind": "postal_codes", "geo": {"postal_codes": ["0000"]}}, "geo.postal_codes"),
           ({"industry_keys": ["skoenhed"], "geo_kind": "radius", "geo": {"lat": 56.15, "lng": 10.2, "km": 80}}, "geo.km"),
           ({"industry_keys": ["skoenhed"], "geo_kind": "place", "geo": {"text": "Atlantis"}}, "geo.text"),
           ({"industry_keys": ["skoenhed"], "geo_kind": "place", "geo": {"text": "Aarhus C"}, "max_results": 900},
            "max_results")]
    for body, field in bad:
        r = api.post(op, "/operator/salg/search-jobs", body)
        assert r.status_code == 422, (body, r.text)
        assert r.json()["field_errors"][0]["field"] == field


def test_radius_is_split_into_cells_and_postal_codes_one_each():
    areas, used = search.plan_areas("radius", {"lat": 56.15, "lng": 10.2, "km": 20}, places.DemoPlaces([]))
    assert used == 0 and 1 < len(areas) <= search.MAX_GRID_CELLS and all(a["radius_m"] >= 3000 for a in areas)
    areas, _ = search.plan_areas("postal_codes", {"postal_codes": ["8000", "8200", "8000"]}, places.DemoPlaces([]))
    assert [a["postal_codes"] for a in areas] == [["8000"], ["8200"]]


class FakeGoogle:
    """httpx transport answering like Places API (New), recording what we sent."""

    def __init__(self):
        self.data = fixture("sales_places.json")
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.method == "POST" and request.url.path == "/v1/places:searchText":
            body = json.loads(request.content)
            page = self.data["search_page_2"] if body.get("pageToken") == "page-2-token" else self.data["search_page_1"]
            return httpx.Response(200, json=page)
        if request.method == "GET" and request.url.path.startswith("/v1/places/"):
            pid = request.url.path.rsplit("/", 1)[1]
            return httpx.Response(200, json=self.data["details"].get(pid, {}))
        return httpx.Response(404, json={"error": {"message": "not found"}})


@pytest.fixture
def google(salg, monkeypatch):
    monkeypatch.setenv("GOOGLE_PLACES_API_KEY", "test-places-key")
    get_settings.cache_clear()
    fake = FakeGoogle()
    places.set_client_override(places.GooglePlaces("test-places-key", transport=httpx.MockTransport(fake)))
    yield fake


def test_google_requests_match_the_documented_format(api, salg, google, db):
    op = salg["op"]
    r = api.post(op, "/operator/salg/search-jobs", {"google_types": ["hair_salon"], "geo_kind": "postal_codes",
                                                    "geo": {"postal_codes": ["8000"]}, "max_results": 50})
    assert r.status_code == 202 and r.json()["source"] == "google"
    run_search(db)
    first = google.requests[0]
    assert first.url == "https://places.googleapis.com/v1/places:searchText"
    assert first.headers["X-Goog-Api-Key"] == "test-places-key"
    mask = first.headers["X-Goog-FieldMask"]
    assert "places.id" in mask and "nextPageToken" in mask
    assert "websiteUri" not in mask and "PhoneNumber" not in mask  # Enterprise fields only via Place Details
    body = json.loads(first.content)
    assert body["includedType"] == "hair_salon" and body["strictTypeFiltering"] is True
    assert body["languageCode"] == "da" and body["regionCode"] == "DK" and body["pageSize"] == 20
    assert body["locationBias"]["circle"]["radius"] <= 50_000 and "latitude" in body["locationBias"]["circle"]["center"]
    assert body["textQuery"].startswith("frisør i 8000")
    posts = [q for q in google.requests if q.method == "POST"]
    assert "pageToken" not in json.loads(posts[0].content)
    assert json.loads(posts[1].content)["pageToken"] == "page-2-token"
    details = [q for q in google.requests if q.method == "GET"]
    assert details and all(q.headers["X-Goog-FieldMask"].startswith("websiteUri") for q in details)
    assert "places." not in details[0].headers["X-Goog-FieldMask"]
    # no details were paid for the closed company
    assert not any(q.url.path.endswith("ChIJ_test_closed") for q in details)

    by_place = {c.google_place_id: c for c in db.scalars(select(SalesCompany))}
    closed = by_place["ChIJ_test_closed"]
    assert closed.research_status == "incomplete" and closed.google_business_status == "CLOSED_PERMANENTLY"
    assert "not_operational" in closed.data_quality["issues"]
    salon = by_place["ChIJ_test_salon_1"]
    assert salon.main_phone_e164 == "+4512340001" and salon.domain == "salon-fiktiv.invalid"
    assert salon.postal_code == "8000" and salon.city == "Aarhus C" and salon.google_fetched_at is not None
    facts = {f.field: f for f in db.scalars(select(SalesSourceFact).where(SalesSourceFact.company_id == salon.id))}
    assert facts["phone_e164"].url_or_ref == "google_place:ChIJ_test_salon_1" and facts["phone_e164"].confidence == "high"
    assert "opening_hours" in facts and "website" in facts
    # same domain at another address = possible branch, not merged; namesake in another postal code stays separate
    branch = by_place["ChIJ_test_branch"]
    assert branch.possible_duplicate_of == salon.id and "afdeling" in branch.duplicate_reason
    namesake = by_place["ChIJ_test_namesake"]
    assert namesake.possible_duplicate_of is None and namesake.display_name == by_place["ChIJ_test_salon_2"].display_name
    job = db.scalar(select(SalesSearchJob))
    assert job.progress["requests_used"] == 2 and job.progress["details_used"] == 4
    assert job.progress["incomplete"] == 1 and job.progress["duplicates"] == 1


def test_errors_never_leak_the_key_and_retryable_pauses(api, salg, monkeypatch, db):
    monkeypatch.setenv("GOOGLE_PLACES_API_KEY", "secret-places-key")
    get_settings.cache_clear()
    places.set_client_override(places.GooglePlaces("secret-places-key", transport=httpx.MockTransport(
        lambda r: httpx.Response(429, json={"error": {"message": "Quota exceeded"}}))))
    job = api.post(salg["op"], "/operator/salg/search-jobs", {"google_types": ["hair_salon"], "geo_kind": "postal_codes",
                                                              "geo": {"postal_codes": ["8000"]}}).json()
    run_search(db)
    job = api.get(salg["op"], f"/operator/salg/search-jobs/{job['id']}").json()
    assert job["status"] == "paused" and "429" in job["error"] and "secret-places-key" not in json.dumps(job)
    assert api.post(salg["op"], f"/operator/salg/search-jobs/{job['id']}/resume").json()["status"] == "queued"


def test_daily_cap_pauses_and_cancel_stops_between_requests(api, salg, monkeypatch, db):
    op = salg["op"]
    monkeypatch.setenv("SALES_SEARCH_DAILY_REQUEST_CAP", "3")
    get_settings.cache_clear()
    job = api.post(op, "/operator/salg/search-jobs", {"industry_keys": ["skoenhed", "haandvaerk"], "geo_kind": "place",
                                                      "geo": {"text": "Aarhus C"}, "max_results": 200}).json()
    run_search(db)
    job = api.get(op, f"/operator/salg/search-jobs/{job['id']}").json()
    assert job["status"] == "paused" and "loft" in job["error"]
    assert search.requests_today(db) <= 3
    # cancel: a queued job is stopped before the worker takes it
    monkeypatch.setenv("SALES_SEARCH_DAILY_REQUEST_CAP", "500")
    get_settings.cache_clear()
    j2 = api.post(op, "/operator/salg/search-jobs", {"industry_keys": ["klinik"], "geo_kind": "place",
                                                     "geo": {"text": "Odense C"}}).json()
    assert api.post(op, f"/operator/salg/search-jobs/{j2['id']}/cancel").json()["status"] == "cancelled"
    calls_before = len(salg["demo"].calls)
    run_search(db)
    assert api.get(op, f"/operator/salg/search-jobs/{j2['id']}").json()["status"] == "cancelled"
    assert not any(c[1].startswith(("tandlæge", "fysioterapeut")) for c in salg["demo"].calls[calls_before:])
    assert api.post(op, f"/operator/salg/search-jobs/{j2['id']}/cancel").status_code == 409


def test_cancel_while_running_stops_at_next_request(salg, db):
    job = search.create_job(db, user_id=None, industry_keys=["skoenhed", "auto"], google_types=[], keywords=[],
                            geo_kind="place", geo={"text": "Aarhus C"}, max_results=200)
    db.commit()
    job = search.claim(db)

    class CancelAfterOne(places.DemoPlaces):
        def search(self, **kw):
            out = super().search(**kw)
            db.execute(SalesSearchJob.__table__.update().where(SalesSearchJob.id == job.id).values(status="cancelled"))
            return out

    client = CancelAfterOne()
    search.run_step(db, job, client)
    db.refresh(job)
    assert job.status == "cancelled"
    assert len([c for c in client.calls if c[0] == "search"]) == 1


def test_existing_customer_is_marked_and_skipped(api, salg, db):
    ws = salg["t"]["ws_b"]
    bp = db.get(BusinessProfile, ws) or BusinessProfile(workspace_id=ws, legal_name="Kunde")
    bp.website_url = "https://www.fiktiv-frisoer-aarhus.invalid"
    db.add(bp)
    db.add(ReceptionAgreement(workspace_id=ws, version=1, model="A", monthly_net_minor=249_500))
    db.commit()
    job = api.post(salg["op"], "/operator/salg/search-jobs", {"google_types": ["hair_salon"], "geo_kind": "place",
                                                              "geo": {"text": "Aarhus C"}}).json()
    run_search(db)
    job = api.get(salg["op"], f"/operator/salg/search-jobs/{job['id']}").json()
    rows = db.scalars(select(SalesCompany).where(SalesCompany.domain == "fiktiv-frisoer-aarhus.invalid")).all()
    assert rows and all(c.existing_customer_workspace_id is not None for c in rows)
    assert job["progress"]["reasons"].get("existing_customer") == len(rows)
    c = rows[0]
    out = api.get(salg["op"], f"/operator/salg/companies/{c.id}").json()
    assert out["existing_customer"] and "Eksisterende kunde" in out["contactable"]["reasons"]


def test_csv_import_fallback(api, salg, db):
    csv_text = ("navn;cvr;hjemmeside;telefon;e-mail;postnr\n"
                "Importeret Frisør;12345674;importeret.invalid;12 34 99 01;kontakt@importeret.invalid;8000\n"
                ";;;;;\n"
                "Anden Import;;anden.invalid;;;5000\n")
    r = api.post(salg["op"], "/operator/salg/companies/import", {"csv": csv_text, "industry_key": "skoenhed"})
    assert r.status_code == 201, r.text
    job = r.json()
    assert job["source"] == "import" and job["status"] == "done" and job["progress"]["found"] == 2
    assert job["progress"]["reasons"] == {"missing_name": 1}
    c = db.scalar(select(SalesCompany).where(SalesCompany.cvr == "12345674"))
    assert c.source == "import" and c.city == "Aarhus C" and c.main_phone_e164 == "+4512349901"
    facts = db.scalars(select(SalesSourceFact).where(SalesSourceFact.company_id == c.id)).all()
    assert {f.confidence for f in facts} == {"medium"} and all(f.url_or_ref.startswith("import:") for f in facts)
    again = api.post(salg["op"], "/operator/salg/companies/import", {"csv": csv_text}).json()
    assert again["progress"]["reasons"].get("already_known") == 1


def test_google_fields_expire_after_the_cache_window(salg, db, monkeypatch):
    c = SalesCompany(source="google", google_place_id="ChIJ_old", display_name="Gammel Salon",
                     google_fetched_at=datetime.now(UTC) - timedelta(days=31), google_types=["hair_salon"],
                     google_business_status="OPERATIONAL", rating=4.2, latitude=56.1, longitude=10.2)
    db.add(c)
    db.flush()
    from app.modules.sales import companies

    f = companies.add_fact(db, c, field="phone_e164", value="+4512340099", ref="google_place:ChIJ_old",
                           extractor="google-places-v1")
    companies.set_main_phone(db, c, "+4512340099", f)
    db.commit()
    # demo client (no key): cannot refresh -> Google fields are cleared, the place id is kept
    result = search.refresh_stale(db, client=places.DemoPlaces([]))
    assert result == {"refreshed": 0, "cleared": 1}
    db.refresh(c)
    assert c.google_place_id == "ChIJ_old" and c.rating is None and c.google_fetched_at is None and c.google_types == []
    assert db.scalar(select(SalesSourceFact).where(SalesSourceFact.company_id == c.id)) is None
    assert db.scalar(select(SalesContact).where(SalesContact.company_id == c.id)).source_fact_id is None

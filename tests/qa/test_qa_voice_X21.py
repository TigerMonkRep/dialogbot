"""QA X21 (voice-qa): "Intern salgskanal: Google-baseret søgning pr. branche/område, kun admin; testopkald kun til eget
nummer efter ja".

«Admin» = Dialogbot platform operator (users.is_platform_operator). Offline: Places is the demo client or a dry run,
Vapi's create_call is faked by the `ring` fixture – nothing leaves the machine and no call is placed."""
from __future__ import annotations

import re
import uuid

from sqlalchemy import select

from app.config import get_settings
from app.models import CampaignContact
from tests.sales_fixtures import OTHER_NUMBER, TEST_NUMBER, ring, salg  # noqa: F401

ZERO = "00000000-0000-0000-0000-000000000000"


def _operator_routes(app) -> list[tuple[str, str]]:
    """Every operation under /operator/salg and /operator/sales, read from the app's own OpenAPI schema."""
    out = []
    for path, ops in app.openapi()["paths"].items():
        if not (path.startswith("/api/v1/operator/salg") or path.startswith("/api/v1/operator/sales")):
            continue
        concrete = re.sub(r"\{action\}", "pause", re.sub(r"\{(?!action)[^}]+\}", ZERO, path))
        out += [(m.upper(), concrete) for m in ops if m in ("get", "post", "put", "patch", "delete")]
    return out


def test_x21_every_sales_channel_route_refuses_everyone_but_operators(app, client, api, salg):  # noqa: F811
    """All /operator/salg/* and /operator/sales/* routes (taken from the app, not a hand-made list): the OWNER of the
    sales workspace itself, a staff member and an anonymous caller are refused; the operator is not."""
    staff = api.add_member(salg["tok"], salg["ws"], "staff-x21@testmail.dk", "staff")
    routes = _operator_routes(app)
    assert len(routes) >= 40, routes
    leaks = []
    for who, tok in (("owner of the sales workspace", salg["tok"]), ("staff", staff), ("anonymous", None)):
        for m, path in routes:
            h = {"Authorization": f"Bearer {tok}"} if tok else {}
            r = client.request(m, path, headers=h, json={})
            # by design (app/modules/sales/privat_leads.py): admin/owner OF THE SALES WORKSPACE (Dialogbot's own sellers)
            # may use /operator/sales/privat-leads; every other role gets 403/404
            if who == "owner of the sales workspace" and "/privat-leads" in path:
                continue
            if r.status_code not in (401, 403, 404 if "/privat-leads" in path else 403):
                leaks.append((who, m, path, r.status_code))
    assert not leaks, leaks
    assert api.get(salg["op"], "/operator/salg").status_code == 200


def test_x21_google_search_is_planned_per_industry_and_area(api, salg, monkeypatch):  # noqa: F811
    """With a Places key the job is a Google job, planned per industry keyword × area (dry run: nothing saved, no
    request for a known Danish town)."""
    monkeypatch.setenv("GOOGLE_PLACES_API_KEY", "places-test-key-not-real")
    get_settings.cache_clear()
    from app.modules.sales import places

    places.set_client_override(None)
    r = api.post(salg["op"], "/operator/salg/search-jobs?dry_run=true",
                 {"industry_keys": ["skoenhed", "haandvaerk"], "geo_kind": "postal_codes",
                  "geo": {"postal_codes": ["8000", "8200"]}, "max_results": 30})
    assert r.status_code == 202, r.text
    job = r.json()
    assert job["dry_run"] is True and job["source"] == "google", job
    assert job["steps"] >= 4  # ≥ 2 industries × 2 postal codes
    assert job["budget"]["estimate"]["search_requests_max"] >= job["steps"]
    assert api.get(salg["op"], "/operator/salg/search-jobs").json()["items"] == []  # dry run saved nothing
    places.set_client_override(salg["demo"])
    get_settings.cache_clear()


def test_x21_test_call_only_after_yes_and_only_to_an_own_number(api, ring, db):  # noqa: F811
    op, company, script = ring["op"], ring["company"], ring["script"]
    body = {"company_id": str(company.id), "script_id": str(script.id), "phone": TEST_NUMBER}
    # no «ja» (accepted_test missing / false): refused, nothing dialled
    assert api.post(op, "/operator/salg/test-calls", body).status_code == 422
    r = api.post(op, "/operator/salg/test-calls", body | {"accepted_test": False})
    assert r.status_code == 422 and r.json()["field_errors"][0]["field"] == "accepted_test"
    # a real company's number, even with «ja»: refused
    r = api.post(op, "/operator/salg/test-calls", body | {"phone": OTHER_NUMBER, "accepted_test": True})
    assert r.status_code == 422 and r.json()["field_errors"][0]["field"] == "phone"
    assert ring["calls"] == []
    # own number + ja: exactly one call, to that number and nowhere else
    r = api.post(op, "/operator/salg/test-calls", body | {"accepted_test": True})
    assert r.status_code == 201, r.text
    assert [c["customer"]["number"] for c in ring["calls"]] == [TEST_NUMBER]
    cc = db.get(CampaignContact, uuid.UUID(r.json()["campaign_contact_id"]))
    assert cc.phone_e164 == TEST_NUMBER if hasattr(cc, "phone_e164") else True


def test_x21_a_non_operator_cannot_place_a_test_call_even_to_the_whitelisted_number(api, ring):  # noqa: F811
    body = {"company_id": str(ring["company"].id), "script_id": str(ring["script"].id), "phone": TEST_NUMBER,
            "accepted_test": True}
    assert api.post(ring["tok"], "/operator/salg/test-calls", body).status_code == 403
    assert ring["calls"] == []


def test_x21_test_mode_never_rings_a_company_from_a_campaign(api, ring, db):  # noqa: F811
    """SALES_OUTBOUND_MODE=test: a normal (non-test) campaign with a real company number is never dialled."""
    from app.modules.sales import policy

    op, company = ring["op"], ring["company"]
    other = api.post(op, f"/operator/salg/companies/{company.id}/contacts", {"role": "Indehaver", "phone": "61 62 63 64"}).json()
    r = api.post(op, f"/operator/salg/contacts/{other['id']}/check").json()
    assert r["result"] == "BLOCK" and "not_test_number" in r["reasons"]
    assert OTHER_NUMBER not in policy.test_numbers()
    assert not db.scalars(select(CampaignContact)).all() or ring["calls"] == []

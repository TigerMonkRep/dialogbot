"""CVR register lookup: validation, not configured, parsing of the documented fields, errors."""
from __future__ import annotations

import httpx
import pytest

from app.config import get_settings

HIT = {"_source": {"Vrvirksomhed": {"cvrNummer": 12345674, "virksomhedMetadata": {
    "nyesteNavn": {"navn": "FJORD GULVSERVICE ApS"},
    "nyesteBeliggenhedsadresse": {"vejnavn": "Havnevej", "husnummerFra": 12, "bogstavFra": "B", "postnummer": 8000,
                                  "postdistrikt": "Aarhus C"},
    "nyesteHovedbranche": {"branchekode": "433300", "branchetekst": "Gulvbelægning og tapetsering"},
    "sammensatStatus": "Normal"}}}}


@pytest.fixture
def cvr_creds(monkeypatch):
    monkeypatch.setenv("CVR_USERNAME", "test-user")
    monkeypatch.setenv("CVR_PASSWORD", "test-pass")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_lookup_requires_valid_cvr_and_credentials(api, two_workspaces, monkeypatch):
    t = two_workspaces
    monkeypatch.delenv("CVR_USERNAME", raising=False)
    get_settings.cache_clear()
    assert api.get(t["tok_a"], f"/workspaces/{t['ws_a']}/cvr/12345675").status_code == 422
    r = api.get(t["tok_a"], f"/workspaces/{t['ws_a']}/cvr/12345674")
    assert r.status_code == 501 and r.json()["code"] == "cvr_not_configured"
    caps = {c["key"]: c["status"] for c in api.get(t["tok_a"], "/integrations/capabilities").json()["items"]}
    assert caps["cvr.lookup"] == "not_implemented"


def test_lookup_parses_register_fields(api, two_workspaces, cvr_creds, monkeypatch):
    t = two_workspaces
    seen = {}

    def fake_post(url, **kw):
        seen.update(url=url, **kw)
        return httpx.Response(200, json={"hits": {"hits": [HIT]}}, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", fake_post)
    r = api.get(t["tok_a"], f"/workspaces/{t['ws_a']}/cvr/12 34 56 74")
    assert r.status_code == 200, r.text
    assert r.json() == {"cvr": "12345674", "legal_name": "FJORD GULVSERVICE ApS", "address_line": "Havnevej 12B",
                        "postal_code": "8000", "city": "Aarhus C", "industry": "Gulvbelægning og tapetsering",
                        "status": "Normal"}
    assert seen["auth"] == ("test-user", "test-pass")
    assert seen["json"]["query"] == {"term": {"Vrvirksomhed.cvrNummer": 12345674}}
    monkeypatch.setattr(httpx, "post", lambda url, **kw: httpx.Response(200, json={"hits": {"hits": []}},
                                                                         request=httpx.Request("POST", url)))
    assert api.get(t["tok_a"], f"/workspaces/{t['ws_a']}/cvr/12345674").json()["code"] == "cvr_not_found"
    monkeypatch.setattr(httpx, "post", lambda url, **kw: httpx.Response(401, request=httpx.Request("POST", url)))
    assert api.get(t["tok_a"], f"/workspaces/{t['ws_a']}/cvr/12345674").status_code == 502
    reader = api.add_member(t["tok_a"], t["ws_a"], "reader-cvr@testmail.dk", "reader")
    assert api.get(reader, f"/workspaces/{t['ws_a']}/cvr/12345674").status_code == 403

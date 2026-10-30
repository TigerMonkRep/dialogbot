"""Shared set-up for the internal sales channel tests (tests/test_sales_channel_*.py)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import select

from app.config import get_settings
from app.db import get_session_factory
from app.models import CampaignContact, SalesCompany, SalesContact
from app.modules.ai import provider as ai_provider
from app.modules.ai.provider import FakeProvider
from app.modules.campaigns import service as campaigns
from app.modules.sales import places, playbook

FIXTURES = Path(__file__).parent / "fixtures"


def fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.fixture
def salg(api, two_workspaces, monkeypatch):
    """Sales channel in simulation mode on demo Places data, fake AI, workspace A as the sales workspace."""
    t = two_workspaces
    monkeypatch.setenv("SALES_OUTBOUND_MODE", "simulation")
    monkeypatch.setenv("AI_PROVIDER", "fake")
    monkeypatch.setenv("SALES_WORKSPACE_ID", t["ws_a"])
    monkeypatch.setenv("SALES_RESEARCH_PAGE_PAUSE_SECONDS", "0")
    monkeypatch.delenv("GOOGLE_PLACES_API_KEY", raising=False)
    get_settings.cache_clear()
    fake = FakeProvider(get_settings())
    ai_provider.set_provider_override(fake)
    demo = places.DemoPlaces()
    places.set_client_override(demo)
    op = api.operator()
    yield {"op": op, "ws": t["ws_a"], "tok": t["tok_a"], "t": t, "demo": demo, "ai": fake}
    places.set_client_override(None)
    ai_provider.set_provider_override(None)
    get_settings.cache_clear()


def approve_knowledge(api, tok: str, ws: str, kind: str, title: str, content: dict, audience: str = "public") -> dict:
    r = api.c.post(f"/api/v1/workspaces/{ws}/knowledge/items", json={"kind": kind, "title": title, "content": content,
                                                                      "audience": audience}, headers=api.h(tok))
    assert r.status_code == 201, r.text
    item = r.json()
    api.submit(tok, ws, item["open_draft"]["id"])
    assert api.approve(tok, ws, item["open_draft"]["id"]).status_code == 200
    return item


def run_search(db, client=None) -> int:
    from app.modules.sales import search

    total = 0
    for _ in range(50):
        n = search.run_due(db, client=client)
        if n == 0:
            break
        total += n
    return total


# --------------------------------------------------------------------------- phase 2+: test mode with a fake Vapi

SECRET = "vapi-test-secret-0123456789abcdef"
TEST_NUMBER = "+4520304050"
OTHER_NUMBER = "+4561626364"
@pytest.fixture
def ring(api, salg, db, monkeypatch):
    """Sales channel in test mode with a callable number, an approved script and a fake Vapi."""
    monkeypatch.setenv("SALES_OUTBOUND_MODE", "test")
    monkeypatch.setenv("SALES_TEST_NUMBERS", f"{TEST_NUMBER}, 20 30 40 51")
    monkeypatch.setenv("VAPI_API_KEY", "vapi-private-key-test")
    monkeypatch.setenv("VAPI_SERVER_SECRET", SECRET)
    monkeypatch.setenv("SALES_MAX_ATTEMPTS_PER_CONTACT", "2")
    get_settings.cache_clear()
    approve_knowledge(api, salg["tok"], salg["ws"], "fact", "Telefonpasning", {"text": "Dialogbot tager telefonen."})
    api.map_number(salg["ws"], "+4570123456", "pn_sales", outbound=True)
    company = SalesCompany(source="demo", display_name="Salon Fiktiv", website_url="https://salon-fiktiv.invalid/",
                           domain="salon-fiktiv.invalid", postal_code="8000", city="Aarhus C", industry_key="skoenhed",
                           industry_text="Frisør & skønhed", google_business_status="OPERATIONAL",
                           advertising_protected=False)
    db.add(company)
    db.flush()
    from app.modules.sales import companies

    fact = companies.add_fact(db, company, field="service", value="Dameklip", ref="https://salon-fiktiv.invalid/",
                              evidence="Dameklip", extractor="sales-research-v1")
    companies.set_main_phone(db, company, TEST_NUMBER, fact)
    profile = playbook.build_profile(db, company, user_id=None)
    script = playbook.build_script(db, company, profile, user_id=None)
    assert script.validation["ok"], script.validation
    db.commit()
    op_user = db.scalar(select(SalesContact).where(SalesContact.company_id == company.id))
    playbook.approve(db, script, user_id=_op_id(db))
    db.commit()
    calls: list[dict] = []

    def fake_call(payload):
        # the attempt is committed as `calling` with its dispatch key BEFORE the provider is asked
        with get_session_factory()() as other:
            cc = other.get(CampaignContact, payload["metadata"]["campaign_contact_id"])
            assert cc.status == "calling" and cc.dispatch_key == payload["metadata"]["dispatch_key"]
        calls.append(payload)
        return {"id": f"sales_call_{len(calls)}"}

    monkeypatch.setattr(campaigns, "create_call", fake_call)
    yield salg | {"company": company, "script": script, "contact": op_user, "calls": calls}
    get_settings.cache_clear()


def _op_id(db):
    from app.models import User

    return db.scalar(select(User.id).where(User.email_normalized == "operator@testmail.dk"))

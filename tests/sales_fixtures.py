"""Shared set-up for the internal sales channel tests (tests/test_sales_channel_*.py)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.config import get_settings
from app.modules.ai import provider as ai_provider
from app.modules.ai.provider import FakeProvider
from app.modules.sales import places

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

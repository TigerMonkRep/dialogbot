"""AI suggestions in the setup guide: proposes goals/channels from the profile and knowledge, saves nothing."""
from __future__ import annotations

import pytest
from sqlalchemy import select

from app.config import get_settings
from app.models import AiUsage, GoalSelection
from app.modules.ai import provider as ai_provider
from app.modules.ai.provider import FakeProvider


@pytest.fixture
def fake_ai(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "fake")
    get_settings.cache_clear()
    ai_provider.set_provider_override(FakeProvider(get_settings()))
    yield
    ai_provider.set_provider_override(None)
    get_settings.cache_clear()


def test_goal_suggestions_use_knowledge_and_save_nothing(api, two_workspaces, fake_ai, db):
    t = two_workspaces
    tok, ws = t["tok_a"], t["ws_a"]
    api.knowledge(tok, ws, "service", "Gulvafslibning", {"price_net_minor": None})  # a draft is enough here
    before = db.get(GoalSelection, __import__("uuid").UUID(ws)).version
    r = api.post(tok, f"/workspaces/{ws}/goals/suggestions", {})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["conversation_goals"] == ["Uforpligtende tilbud på gulvafslibning"]
    assert body["channels"]["webchat"] is False  # no website on the profile yet
    assert body["channels"]["callback"] is True
    db.expire_all()
    assert db.get(GoalSelection, __import__("uuid").UUID(ws)).version == before
    assert db.scalars(select(AiUsage).where(AiUsage.purpose == "setup_suggestion")).first() is not None
    reader = api.add_member(tok, ws, "reader-goals@testmail.dk", "reader")
    assert api.post(reader, f"/workspaces/{ws}/goals/suggestions", {}).status_code == 403


def test_goal_suggestions_not_configured(api, two_workspaces, monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "none")
    get_settings.cache_clear()
    t = two_workspaces
    r = api.post(t["tok_a"], f"/workspaces/{t['ws_a']}/goals/suggestions", {})
    assert r.status_code == 501 and r.json()["code"] == "ai_not_configured"
    get_settings.cache_clear()

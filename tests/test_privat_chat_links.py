"""Privat chat: links on list items (from the model's web search), set_item_link, one model turn when the tools already
answered, and Privat's own model/effort on every call."""
from __future__ import annotations

from app.config import get_settings
from app.modules.ai import provider as ai_provider
from app.modules.privat import chat


def _list(pv, tok) -> str:
    r = pv.say(tok, "Lav en ønskeliste med Lego Technic og en bog")
    task = next(m for m in r["messages"] if m["kind"] == "task")
    return task["task_id"]


def _items(api, tok, task_id) -> list[dict]:
    return api.get(tok, f"/privat/tasks/{task_id}").json()["items"]


def test_items_with_links_and_set_item_link(api, pv):
    tok = pv.account("mette@testmail.dk")
    tid = _list(pv, tok)
    r = pv.say(tok, '!add_items {"items": [{"text": "Fodbold", "link": "https://www.sportmaster.dk/fodbold", "note": "str. 5"}, "Drage"]}', about=tid)
    assert "med link til, hvor det kan købes" in next(m for m in r["messages"] if m["role"] == "assistant" and m["kind"] == "text")["text"]
    by = {i["text"]: i for i in _items(api, tok, tid)}
    assert by["Fodbold"]["link"] == "https://www.sportmaster.dk/fodbold" and by["Fodbold"]["note"] == "str. 5"
    assert by["Drage"]["link"] is None
    # a link on an item that is already there – matched by text, case-insensitively
    r = pv.say(tok, '!set_item_link {"item": "lego technic", "link": "https://www.lego.com/da-dk/themes/technic"}', about=tid)
    assert "Linket er sat på «Lego Technic»" in next(m for m in r["messages"] if m["role"] == "assistant")["text"]
    by = {i["text"]: i for i in _items(api, tok, tid)}
    assert by["Lego Technic"]["link"] == "https://www.lego.com/da-dk/themes/technic"
    # never a made-up link: only https://
    r = pv.say(tok, '!set_item_link {"item": "en bog", "link": "saxo.com/bog"}', about=tid)
    assert by["En bog"]["link"] is None if "En bog" in by else True
    assert not any("saxo" in (m.get("text") or "") for m in r["messages"] if m["role"] == "assistant" and m["kind"] == "task")


def test_tools_that_answer_end_the_turn_without_a_second_model_call(api, pv, monkeypatch):
    tok = pv.account("mette@testmail.dk")
    calls = []
    real = ai_provider.FakeProvider.complete

    def counting(self, **kw):
        calls.append(kw.get("model"))
        return real(self, **kw)

    monkeypatch.setattr(ai_provider.FakeProvider, "complete", counting)
    monkeypatch.setenv("PRIVAT_AI_MODEL_ID", "claude-sonnet-5")
    get_settings.cache_clear()
    try:
        r = pv.say(tok, "Lav en liste med kaffe og te")
        assert [m["kind"] for m in r["messages"] if m["role"] == "assistant"][:2] == ["text", "task"]
        assert len(calls) == 1  # create_list said «Her er din liste …» itself: no follow-up turn
        assert calls == ["claude-sonnet-5"]  # Privat's own model goes on the call
    finally:
        monkeypatch.delenv("PRIVAT_AI_MODEL_ID")
        get_settings.cache_clear()


def test_web_search_only_with_the_real_provider(monkeypatch):
    get_settings.cache_clear()
    assert chat.web_search_tool("Aarhus") is None  # fake provider in tests
    monkeypatch.setenv("AI_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    get_settings.cache_clear()
    try:
        t = chat.web_search_tool("Aarhus")
        assert t == {"type": "web_search_20250305", "name": "web_search", "max_uses": 3,
                     "user_location": {"type": "approximate", "country": "DK", "timezone": "Europe/Copenhagen", "city": "Aarhus"}}
        monkeypatch.setenv("PRIVAT_WEB_SEARCH", "false")
        get_settings.cache_clear()
        assert chat.web_search_tool(None) is None
    finally:
        monkeypatch.delenv("AI_PROVIDER")
        monkeypatch.delenv("PRIVAT_WEB_SEARCH", raising=False)
        get_settings.cache_clear()

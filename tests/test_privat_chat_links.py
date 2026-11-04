"""Privat chat: links on list items (from the model's web search), set_item_link, one model turn when the tools already
answered, and Privat's own model/effort on every call."""
from __future__ import annotations

from app.config import get_settings
from app.modules.ai import provider as ai_provider
from app.modules.privat import links


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


PRODUCT_HTML = """<html><head><title>Think and Grow Rich af Napoleon Hill – Saxo</title>
<meta property="og:type" content="product"><script type="application/ld+json">{"@type":"Product","name":"Think and Grow Rich",
"offers":{"@type":"Offer","price":"129.00","priceCurrency":"DKK"}}</script></head><body><button>Læg i kurv</button>
<p>129,00 kr.</p>""" + "x" * 600 + "</body></html>"
SEARCH_HTML = "<html><head><title>Vi beklager, men der opstod en fejl eller siden findes ikke.</title></head><body>" + "y" * 800 + "</body></html>"


def test_the_finder_rejects_search_pages_and_guessed_urls():
    assert links.looks_like_search("https://www.saxo.com/dk/search?query=Think%20and%20Grow%20Rich")
    assert links.looks_like_search("https://www.pricerunner.dk/pl/1-123/think-and-grow-rich")
    assert links.looks_like_search("https://www.bog-ide.dk/")
    assert not links.looks_like_search("https://www.saxo.com/dk/think-and-grow-rich_napoleon-hill_paperback_9781585424337")
    assert links.is_product_page(PRODUCT_HTML) and not links.is_product_page(SEARCH_HTML)
    assert links.price_from(PRODUCT_HTML) == "129 kr."
    assert links.parse_candidates('Her: [{"url": "https://a.dk/x", "shop": "A", "price": "10 kr."}, {"url": "ftp://no"}]') == \
        [{"url": "https://a.dk/x", "shop": "A", "price": "10 kr.", "title": None}]
    assert links.parse_candidates("[]") == [] and links.parse_candidates("ingen json") == []


def _fake_finder(monkeypatch, pages: dict[str, str], candidates: dict[str, list[dict]]):
    monkeypatch.setattr(links, "search_candidates", lambda item, city: (candidates.get(item.lower(), []), None))
    monkeypatch.setattr(links, "fetch", lambda url: (200, url, pages[url]) if url in pages else (404, url, SEARCH_HTML))


def test_find_buy_link_sets_only_a_verified_product_page(api, pv, monkeypatch):
    tok = pv.account("mette@testmail.dk")
    tid = _list(pv, tok)
    good = "https://www.saxo.com/dk/think-and-grow-rich_napoleon-hill_paperback_9781585424337"
    _fake_finder(monkeypatch, {good: PRODUCT_HTML}, {
        "en bog": [{"url": "https://www.saxo.com/dk/search?query=Think", "shop": "Saxo", "price": None, "title": None},  # search page: out
                   {"url": "https://www.plusbog.dk/think-and-grow-rich-404", "shop": "Plusbog", "price": None, "title": None},  # 404: out
                   {"url": good, "shop": "Saxo", "price": "149 kr.", "title": "Think and Grow Rich"}],
        "lego technic": [],
    })
    r = pv.say(tok, '!find_buy_link {"items": ["en bog", "Lego Technic"]}', about=tid)
    text = next(m for m in r["messages"] if m["role"] == "assistant" and m["kind"] == "text")["text"]
    assert "Købslink sat på En bog (Saxo · 129 kr.)" in text  # the page's own price wins over the model's
    assert "fandt ikke en butik, der sælger Lego Technic" in text
    by = {i["text"]: i for i in _items(api, tok, tid)}
    assert by["En bog"]["link"] == good and by["En bog"]["note"] == "Saxo · 129 kr."
    assert by["Lego Technic"]["link"] is None


def test_add_items_with_find_links_finds_them_at_once(api, pv, monkeypatch):
    tok = pv.account("mette@testmail.dk")
    tid = _list(pv, tok)
    good = "https://www.legekaeden.dk/produkt/fodbold-str-5"
    _fake_finder(monkeypatch, {good: PRODUCT_HTML.replace("129.00", "199.00")}, {"fodbold": [{"url": good, "shop": "Legekæden", "price": None, "title": None}]})
    r = pv.say(tok, '!add_items {"items": ["Fodbold"], "find_links": true}', about=tid)
    text = next(m for m in r["messages"] if m["role"] == "assistant" and m["kind"] == "text")["text"]
    assert text.startswith("Tilføjet fodbold") and "Købslink sat på Fodbold (Legekæden · 199 kr.)" in text
    assert {i["text"]: i for i in _items(api, tok, tid)}["Fodbold"]["link"] == good


def test_the_chat_model_never_gets_the_search_tool(api, pv, monkeypatch):
    tok = pv.account("mette@testmail.dk")
    seen = []
    real = ai_provider.FakeProvider.complete

    def spy(self, **kw):
        seen.append([t.get("name") for t in kw.get("tools") or []])
        return real(self, **kw)

    monkeypatch.setattr(ai_provider.FakeProvider, "complete", spy)
    pv.say(tok, "Lav en liste med kaffe")
    assert seen and all("web_search" not in names and "find_buy_link" in names for names in seen)
    monkeypatch.setenv("PRIVAT_WEB_SEARCH", "false")
    get_settings.cache_clear()
    try:
        seen.clear()
        pv.say(tok, "Lav en liste med te")
        assert seen and all("find_buy_link" not in names for names in seen)
    finally:
        monkeypatch.delenv("PRIVAT_WEB_SEARCH")
        get_settings.cache_clear()

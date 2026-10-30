"""app/core/safe_fetch: SSRF guard with a pinned address, re-checked redirects, robots.txt, limits."""
from __future__ import annotations

import httpx
import pytest

from app.config import get_settings
from app.core import safe_fetch
from app.core.safe_fetch import Budget, FetchBlocked, FetchFailed

PUBLIC = "93.184.216.34"


@pytest.fixture(autouse=True)
def _fresh():
    safe_fetch.clear_robots_cache()
    get_settings.cache_clear()
    yield
    safe_fetch.clear_robots_cache()
    get_settings.cache_clear()


class Site:
    def __init__(self, pages: dict[str, httpx.Response] | None = None, robots: str | None = None):
        self.pages = pages or {}
        self.robots = robots
        self.seen: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.seen.append(request)
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text=self.robots) if self.robots is not None else httpx.Response(404)
        return self.pages.get(request.url.path, httpx.Response(404))


def html(body: str = "<html><body><p>Hej</p></body></html>") -> httpx.Response:
    return httpx.Response(200, headers={"content-type": "text/html; charset=utf-8"}, text=body)


def resolver(mapping: dict[str, list[str]]):
    return lambda host: mapping[host]


def test_connects_to_the_validated_address_with_host_and_sni():
    site = Site({"/": html()})
    page = safe_fetch.get("https://firma.dk/", resolver=resolver({"firma.dk": [PUBLIC]}),
                          transport=httpx.MockTransport(site))
    assert page.url == "https://firma.dk/" and "Hej" in page.text
    req = site.seen[-1]
    assert req.url.host == PUBLIC and req.headers["host"] == "firma.dk"
    assert req.extensions["sni_hostname"] == "firma.dk"
    assert req.headers["user-agent"].startswith("DialogbotResearch/1.0")


@pytest.mark.parametrize("url,reason", [
    ("file:///etc/passwd", "scheme"), ("ftp://firma.dk/", "scheme"), ("http://firma.dk:8080/", "port"),
    ("https://user:pw@firma.dk/", "credentials"), ("http://localhost/", "private_address"),
    ("http://metadata.google.internal/", "private_address"),
])
def test_static_refusals(url, reason):
    with pytest.raises(FetchBlocked) as e:
        safe_fetch.get(url, resolver=resolver({"firma.dk": [PUBLIC]}), transport=httpx.MockTransport(Site()))
    assert e.value.reason == reason


@pytest.mark.parametrize("ip", ["127.0.0.1", "10.0.0.5", "192.168.1.1", "172.16.0.1", "169.254.169.254", "100.64.0.1",
                                "::1", "fd00::1", "fe80::1", "::ffff:10.0.0.1", "0.0.0.0", "224.0.0.1"])
def test_private_addresses_are_refused_also_in_test(ip):
    with pytest.raises(FetchBlocked) as e:
        safe_fetch.get("https://firma.dk/", resolver=resolver({"firma.dk": [ip]}), transport=httpx.MockTransport(Site()))
    assert e.value.reason == "private_address"
    with pytest.raises(FetchBlocked):
        safe_fetch.get(f"http://{ip if ':' not in ip else '[' + ip + ']'}/", transport=httpx.MockTransport(Site()))


def test_any_private_answer_blocks_and_rebinding_cannot_switch_the_address():
    with pytest.raises(FetchBlocked):
        safe_fetch.get("https://firma.dk/", resolver=resolver({"firma.dk": [PUBLIC, "10.0.0.1"]}),
                       transport=httpx.MockTransport(Site({"/": html()})))
    answers = iter([[PUBLIC], ["127.0.0.1"], ["127.0.0.1"]])  # a rebinding resolver: public first, then loopback
    site = Site({"/": html()})
    safe_fetch.get("https://firma.dk/", resolver=lambda h: next(answers), transport=httpx.MockTransport(site))
    assert {r.url.host for r in site.seen} == {PUBLIC}  # robots.txt and the page both went to the checked IP


def test_redirects_are_checked_per_hop():
    site = Site({"/": httpx.Response(302, headers={"location": "http://intern.firma.dk/admin"})})
    with pytest.raises(FetchBlocked) as e:
        safe_fetch.get("https://firma.dk/", resolver=resolver({"firma.dk": [PUBLIC], "intern.firma.dk": ["10.1.2.3"]}),
                       transport=httpx.MockTransport(site))
    assert e.value.reason == "private_address"
    loop = Site({"/": httpx.Response(302, headers={"location": "/"})})
    with pytest.raises(FetchBlocked) as e:
        safe_fetch.get("https://firma.dk/", resolver=resolver({"firma.dk": [PUBLIC]}), transport=httpx.MockTransport(loop))
    assert e.value.reason == "redirects"
    ok = Site({"/": httpx.Response(301, headers={"location": "/hjem"}), "/hjem": html()})
    assert safe_fetch.get("https://firma.dk/", resolver=resolver({"firma.dk": [PUBLIC]}),
                          transport=httpx.MockTransport(ok)).url == "https://firma.dk/hjem"


def test_robots_disallow_is_respected_and_cached():
    site = Site({"/": html(), "/privat/x": html()}, robots="User-agent: DialogbotResearch\nDisallow: /privat\n")
    r = resolver({"firma.dk": [PUBLIC]})
    assert safe_fetch.get("https://firma.dk/", resolver=r, transport=httpx.MockTransport(site))
    with pytest.raises(FetchBlocked) as e:
        safe_fetch.get("https://firma.dk/privat/x", resolver=r, transport=httpx.MockTransport(site))
    assert e.value.reason == "robots"
    assert [q.url.path for q in site.seen].count("/robots.txt") == 1
    # the knowledge importer reads the owner's own site on request: robots is not applied there
    assert safe_fetch.get("https://firma.dk/privat/x", resolver=r, transport=httpx.MockTransport(site), robots=False)


def test_size_type_status_and_page_budget():
    big = Site({"/": html("<p>" + "x" * 5000 + "</p>"), "/pdf": httpx.Response(200, headers={"content-type": "application/pdf"}, content=b"%PDF"),
                "/fejl": httpx.Response(500)})
    r = resolver({"firma.dk": [PUBLIC]})
    t = httpx.MockTransport(big)
    b = Budget(max_pages=3, page_bytes=1000, timeout=5)
    page = safe_fetch.get("https://firma.dk/", budget=b, resolver=r, transport=t)
    assert page.truncated and len(page.body) == 1000
    with pytest.raises(FetchFailed) as e:
        safe_fetch.get("https://firma.dk/pdf", budget=b, resolver=r, transport=t)
    assert e.value.reason == "content_type"
    with pytest.raises(FetchFailed):
        safe_fetch.get("https://firma.dk/fejl", budget=b, resolver=r, transport=t)
    with pytest.raises(FetchBlocked) as e:
        safe_fetch.get("https://firma.dk/", budget=b, resolver=r, transport=t)
    assert e.value.reason == "budget"


def test_allow_private_fetch_is_for_local_tests_only(monkeypatch):
    monkeypatch.setenv("ALLOW_PRIVATE_FETCH", "true")
    get_settings.cache_clear()
    site = Site({"/": html()})
    assert safe_fetch.get("http://lokal.test/", resolver=resolver({"lokal.test": ["127.0.0.1"]}),
                          transport=httpx.MockTransport(site)).status == 200
    page = safe_fetch.get("http://localhost:4000/", resolver=resolver({"localhost": ["127.0.0.1"]}),
                          transport=httpx.MockTransport(site))
    assert page.status == 200 and site.seen[-1].url.port == 4000


def test_importer_and_social_links_use_the_guard(monkeypatch):
    from app.modules.knowledge import importer
    from app.modules.social import prospects

    monkeypatch.setattr(safe_fetch, "system_resolver", lambda host: ["10.0.0.9"])
    assert importer.fetch("https://firma.dk/") is None
    assert prospects.fetch_social_links("https://firma.dk/") == {}

"""A2: engine detection on the clone and on synthetic pages (no network)."""
from __future__ import annotations

from urllib.request import urlopen

from browser_worker import engine_detect as ed


def fetch_local(url):
    with urlopen(url, timeout=5) as r:  # noqa: S310 – the local clone server
        return r.geturl(), r.read().decode("utf-8")


def test_clone_front_page_is_recognised(site):
    d = ed.detect(site.url, fetch_local)
    assert d.engine == "onlinebooq" and d.confidence >= 0.9
    assert d.booking_url  # the widget script was found on the front page
    assert d.pages_checked[0].startswith(site.url)


def test_engine_link_gives_a_booking_url():
    html = '<html><body><a href="https://booking.onlinebooq.example/salon-x">Book tid</a></body></html>'
    d = ed.detect_in_html(html, "https://salon-x.dk/")
    assert (d.engine, d.confidence, d.booking_url) == ("onlinebooq", ed.CONFIDENCE_LINK, "https://booking.onlinebooq.example/salon-x")


def test_booking_page_is_followed_when_the_front_page_has_no_signature():
    pages = {
        "https://salon-x.dk/": '<a href="/bestil-tid">Bestil tid</a><a href="https://other.dk/book">Book</a><a href="/om">Om os</a>',
        "https://salon-x.dk/bestil-tid": '<iframe src="https://widget.onlinebooq.example/embed?id=1"></iframe>',
    }
    fetched = []

    def fetch(url):
        fetched.append(url)
        return url, pages[url]

    d = ed.detect("salon-x.dk", fetch)
    assert d.engine == "onlinebooq"
    assert fetched == ["https://salon-x.dk/", "https://salon-x.dk/bestil-tid"]  # never /om, never a foreign host
    assert d.booking_url == "https://salon-x.dk/bestil-tid"


def test_unknown_engine_and_fetch_budget():
    pages = {"https://x.dk/": '<a href="/book1">Book</a><a href="/book2">Booking</a><a href="/book3">Book nu</a>'}
    for i in (1, 2, 3):
        pages[f"https://x.dk/book{i}"] = f'<a href="/book{i + 1}">Book</a>'
    n = []

    def fetch(url):
        n.append(url)
        return url, pages.get(url, "")

    d = ed.detect("x.dk", fetch)
    assert d.engine == "unknown" and d.confidence == 0.0
    assert len(n) <= ed.MAX_PAGES  # front page + two booking pages at most
    assert d.booking_url == "https://x.dk/book1"  # the best lead for a human/LLM, still not an engine


def test_failing_fetch_is_not_evidence():
    def fetch(url):
        raise OSError("down")

    d = ed.detect("x.dk", fetch)
    assert d.engine == "unknown" and d.booking_url is None

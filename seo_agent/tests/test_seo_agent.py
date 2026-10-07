"""Offline-tests (ingen netværk, ingen database): python -m unittest discover -s seo_agent/tests -t ."""
from __future__ import annotations

import json
import unittest

from seo_agent import checks as C
from seo_agent.fetch import Fetcher, Response
from seo_agent.parse import parse_html
from seo_agent.psi import parse_lighthouse
from seo_agent.report import Report, diff
from seo_agent.scan import scan

GOOD = """<!doctype html><html lang="da"><head><meta charset="utf-8"><title>AI-receptionist til danske firmaer</title>
<meta name="description" content="{d}"><meta name="viewport" content="width=device-width">
<link rel="canonical" href="https://x.dk/"><meta property="og:title" content="t"><meta property="og:description" content="d">
<meta property="og:image" content="i"><meta property="og:url" content="u"><meta name="twitter:card" content="summary">
<script type="application/ld+json">{{"@type":"Organization","name":"X"}}</script></head>
<body><h1>AI-receptionist</h1><h2>Fordele</h2><img src="/a.png" alt="a" width="1" height="1">
<a href="/a">Receptionist guide</a><a href="/b">Priser</a><a href="/c">Kontakt</a> {t}</body></html>""".format(
    d="Dansk AI-receptionist der tager telefonen for jeres virksomhed døgnet rundt og booker tider.", t="receptionist " * 320)


def results_by(rs, check):
    return [r for r in rs if r.check == check]


class FakeFetcher(Fetcher):
    def __init__(self, routes: dict[str, Response]):
        super().__init__()
        self.routes = routes

    def get(self, url, *, follow=True, method="GET", accept="*/*"):
        r = self.routes.get(url)
        if r is None:
            return Response(url=url, final_url=url, status=404, headers={"content-type": "text/html"}, body=b"nope", elapsed_ms=5)
        return r


def html(url, body, **headers):
    h = {"content-type": "text/html; charset=utf-8", **headers}
    return Response(url=url, final_url=url, status=200, headers=h, body=body.encode(), elapsed_ms=50)


class ParseTests(unittest.TestCase):
    def test_extracts_core_elements(self):
        p = parse_html(GOOD, "https://x.dk/")
        self.assertEqual(p.lang, "da")
        self.assertEqual(p.h1, ["AI-receptionist"])
        self.assertEqual(p.canonical, "https://x.dk/")
        self.assertIn("Organization", p.schema_types())
        self.assertEqual(len(p.internal_links()), 3)
        self.assertGreater(len(p.words), 300)

    def test_broken_html_never_raises(self):
        parse_html("<html><head><title>x<h1>y</div></span>", "https://x.dk/")


class PageCheckTests(unittest.TestCase):
    def run_checks(self, body):
        resp = html("https://x.dk/", body)
        return C.page_checks(parse_html(body, resp.url), resp)

    def test_good_page_has_no_failures(self):
        bad = [r for r in self.run_checks(GOOD) if r.status == C.FAIL]
        self.assertEqual(bad, [])

    def test_missing_basics_fail(self):
        rs = self.run_checks("<html><body><p>hej</p><img src='/x.png'></body></html>")
        failed = {r.check for r in rs if r.status == C.FAIL}
        self.assertTrue({"title_present", "desc_present", "h1_single", "canonical_present", "img_alt", "noindex"} - {"noindex"} <= failed)
        self.assertIn("lang_attr", failed)

    def test_noindex_detected_in_meta_and_header(self):
        rs = self.run_checks(GOOD.replace("<head>", '<head><meta name="robots" content="noindex,follow">'))
        self.assertEqual(results_by(rs, "noindex")[0].status, C.FAIL)
        resp = html("https://x.dk/", GOOD, **{"x-robots-tag": "noindex"})
        rs2 = C.page_checks(parse_html(GOOD, resp.url), resp)
        self.assertEqual(results_by(rs2, "noindex")[0].status, C.FAIL)

    def test_duplicate_titles(self):
        pages = {u: parse_html(GOOD, u) for u in ("https://x.dk/a", "https://x.dk/b")}
        rs = C.cross_page_checks(pages)
        self.assertTrue(all(r.status == C.FAIL for r in results_by(rs, "title_unique")))


class SiteCheckTests(unittest.TestCase):
    def test_robots_blocking_everything_fails(self):
        resp = Response(url="u", final_url="u", status=200, headers={"content-type": "text/plain"}, body=b"User-agent: *\nDisallow: /\n")
        rs = C.robots_checks("https://x.dk", resp)
        self.assertEqual(results_by(rs, "robots_open")[0].status, C.FAIL)

    def test_robots_group_parsing(self):
        g = C._robots_groups("User-agent: Googlebot\nUser-agent: *\nDisallow: /app # privat\nAllow: /\n")
        self.assertIn(("disallow", "/app"), g["*"])
        self.assertIn(("disallow", "/app"), g["googlebot"])

    def test_sitemap_lastmod_all_now_is_flagged(self):
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        xml = "<urlset xmlns='http://www.sitemaps.org/schemas/sitemap/0.9'>" + "".join(
            f"<url><loc>https://x.dk/{i}</loc><lastmod>{now}</lastmod></url>" for i in range(4)) + "</urlset>"
        resp = Response(url="u", final_url="u", status=200, headers={"content-type": "application/xml"}, body=xml.encode())
        items, err = C.parse_sitemap(resp)
        self.assertEqual(len(items), 4)
        rs = C.sitemap_checks("https://x.dk", resp, items, err, {u: (200, 0) for u, _ in items})
        self.assertEqual(results_by(rs, "sitemap_lastmod")[0].status, C.WARN)

    def test_broken_internal_link_and_orphan(self):
        pages = {"https://x.dk/": parse_html('<a href="/dead">x</a><a href="/ok">y</a>', "https://x.dk/")}
        rs = C.link_checks(pages, {"https://x.dk/dead": 404}, set())
        self.assertEqual(results_by(rs, "broken_links")[0].status, C.FAIL)


class ScanAndReportTests(unittest.TestCase):
    def make(self):
        sitemap = ("<urlset xmlns='http://www.sitemaps.org/schemas/sitemap/0.9'><url><loc>https://x.dk/</loc></url>"
                   "<url><loc>https://x.dk/a</loc></url></urlset>")
        routes = {
            "https://x.dk/": html("https://x.dk/", GOOD, **{"content-encoding": "gzip"}),
            "https://x.dk/a": html("https://x.dk/a", GOOD.replace("AI-receptionist til", "Anden titel om")),
            "https://x.dk/robots.txt": Response(url="u", final_url="u", status=200, headers={"content-type": "text/plain"},
                                                body=b"User-agent: *\nAllow: /\nSitemap: https://x.dk/sitemap.xml"),
            "https://x.dk/sitemap.xml": Response(url="u", final_url="u", status=200, headers={"content-type": "application/xml"}, body=sitemap.encode()),
        }
        return FakeFetcher(routes)

    def test_scan_produces_report(self):
        rep = scan("https://x.dk", fetcher=self.make(), max_pages=10)
        self.assertEqual(rep.pages_scanned, 2)
        self.assertTrue(0 <= rep.score() <= 100)
        data = json.loads(rep.to_json())
        self.assertIn("sitemap_present", data["checks"])
        self.assertEqual(data["checks"]["sitemap_present"]["status"], "pass")
        self.assertEqual(data["checks"]["notfound_page"]["status"], "pass")
        md = rep.to_markdown()
        self.assertIn("Samlet score", md)
        self.assertIn("Handlingsplan", md)

    def test_diff_detects_regression_and_improvement(self):
        a = Report("https://x.dk", "t", 1, [C.Result("title_present", C.PASS, "u"), C.Result("h1_single", C.FAIL, "u")]).to_dict()
        b = Report("https://x.dk", "t", 1, [C.Result("title_present", C.FAIL, "u"), C.Result("h1_single", C.PASS, "u")]).to_dict()
        d = diff(a, b)
        self.assertEqual(d["regressions"], ["title_present"])
        self.assertEqual(d["improvements"], ["h1_single"])

    def test_unreachable_site_raises(self):
        class Dead(Fetcher):
            def get(self, url, **kw):
                return Response(url=url, final_url=url, error="boom")
        with self.assertRaises(RuntimeError):
            scan("https://x.dk", fetcher=Dead())


class PsiTests(unittest.TestCase):
    def test_lighthouse_parsing(self):
        data = {"categories": {"performance": {"score": 0.62}, "accessibility": {"score": 0.97}},
                "audits": {"largest-contentful-paint": {"numericValue": 3100}, "cumulative-layout-shift": {"numericValue": 0.02},
                           "total-blocking-time": {"numericValue": 120}}}
        rs, metrics, err = parse_lighthouse(data, "https://x.dk/")
        by = {r.check: r.status for r in rs}
        self.assertEqual((by["psi_perf"], by["psi_lcp"], by["psi_cls"], by["psi_tbt"], by["psi_a11y"]),
                         (C.WARN, C.WARN, C.PASS, C.PASS, C.PASS))
        self.assertEqual(metrics["performance"], 62)


if __name__ == "__main__":
    unittest.main()

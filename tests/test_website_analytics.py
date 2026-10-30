"""Website statistics for the operator admin: Vercel Web Analytics and Google Analytics 4, read server-side."""
from __future__ import annotations

from app.modules.analytics import service


def test_website_stats_are_for_operators_only(api, two_workspaces):
    tok = two_workspaces["tok_a"] if isinstance(two_workspaces, dict) else two_workspaces[0]
    assert api.get(tok, "/operator/analytics/website").status_code == 403


def test_unconfigured_sources_say_so_instead_of_failing(api):
    service.clear_cache()
    body = api.get(api.operator(), "/operator/analytics/website?days=7").json()
    assert body["days"] == 7
    assert body["vercel"]["configured"] is False and body["vercel"]["error"] is None
    assert body["ga"]["configured"] is False and body["ga"]["error"] is None
    assert body["vercel"]["dashboard"].startswith("https://vercel.com/")


def test_vercel_numbers_are_read_and_cached(api, monkeypatch):
    service.clear_cache()
    calls: list[str] = []

    def fake_get(path, params):
        calls.append(path)
        if path == "count":
            return {"visitors": 12, "pageviews": 40}
        by = params["by"]
        return [{by: "2026-10-29" if by == "day" else "/", "visitors": 7, "pageviews": 20},
                {by: "2026-10-30" if by == "day" else "/priser", "visitors": 5, "pageviews": 20}]

    monkeypatch.setattr(service, "vercel_get", fake_get)
    monkeypatch.setattr(service.get_settings(), "vercel_api_token", "tok")
    op = api.operator()
    body = api.get(op, "/operator/analytics/website?days=30").json()
    v = body["vercel"]
    assert v["configured"] is True and v["visitors"] == 12 and v["pageviews"] == 40
    assert [r["key"] for r in v["by_day"]] == ["2026-10-29", "2026-10-30"]
    assert v["pages"][1] == {"key": "/priser", "visitors": 5, "pageviews": 20}
    n = len(calls)
    api.get(op, "/operator/analytics/website?days=30")
    assert len(calls) == n  # second read within ten minutes comes from the cache
    service.clear_cache()

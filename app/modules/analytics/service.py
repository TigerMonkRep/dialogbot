"""Website statistics for the operator admin: Vercel Web Analytics and Google Analytics 4, read server-side.

Both halves are optional. Vercel is read with a personal API token (Settings → Tokens on vercel.com) through the
web-analytics query API; Google with a service account that is a Viewer on the GA4 property, signing its own
OAuth JWT (no Google SDK). Results are cached for ten minutes so the admin page can be refreshed freely without
spending API quota. Nothing here writes anywhere, and nothing about individual visitors is read – only counts."""
from __future__ import annotations

import json
import time
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from app.config import get_settings

CACHE_SECONDS = 600
TIMEOUT = 15.0
VERCEL_API = "https://api.vercel.com/v1/query/web-analytics/visits"
GA_TOKEN_URL = "https://oauth2.googleapis.com/token"
GA_DATA_API = "https://analyticsdata.googleapis.com/v1beta/properties"

_cache: dict[str, tuple[float, dict]] = {}


def _window(days: int) -> tuple[datetime, datetime]:
    until = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    return until - timedelta(days=days), until


def _rows(data: Any, key_names: tuple[str, ...]) -> list[dict]:
    """Vercel breaks results down as a list of {<dimension>: value, visitors, pageviews}; pick the dimension out."""
    out = []
    for row in data if isinstance(data, list) else []:
        if not isinstance(row, dict):
            continue
        key = next((row[k] for k in key_names if k in row), None)
        if key is None:
            key = next((v for k, v in row.items() if isinstance(v, str) and k not in ("visitors", "pageviews")), "")
        out.append({"key": str(key), "visitors": int(row.get("visitors") or 0), "pageviews": int(row.get("pageviews") or 0)})
    return out


# ---------------------------------------------------------------- Vercel

def vercel_get(path: str, params: dict) -> Any:
    s = get_settings()
    q = {"projectId": s.vercel_project_id, "teamId": s.vercel_team_id, **params}
    r = httpx.get(f"{VERCEL_API}/{path}", params=q, headers={"Authorization": f"Bearer {s.vercel_api_token}"}, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json().get("data")


def vercel_stats(days: int) -> dict:
    s = get_settings()
    base = {"configured": bool(s.vercel_api_token), "dashboard": "https://vercel.com/rene-simonsens-projects/dialogbot/analytics"}
    if not s.vercel_api_token:
        return {**base, "error": None}
    since, until = _window(days)
    rng = {"since": since.isoformat().replace("+00:00", "Z"), "until": until.isoformat().replace("+00:00", "Z")}
    try:
        total = vercel_get("count", rng) or {}
        by_day = _rows(vercel_get("aggregate", {**rng, "by": "day", "limit": 100}), ("day", "date", "timestamp"))
        pages = _rows(vercel_get("aggregate", {**rng, "by": "requestPath", "limit": 10}), ("requestPath", "path"))
        refs = _rows(vercel_get("aggregate", {**rng, "by": "referrerHostname", "limit": 10}), ("referrerHostname",))
        countries = _rows(vercel_get("aggregate", {**rng, "by": "country", "limit": 8}), ("country",))
        devices = _rows(vercel_get("aggregate", {**rng, "by": "deviceType", "limit": 5}), ("deviceType",))
    except httpx.HTTPError as e:
        return {**base, "error": f"Vercel svarede ikke: {e}"}
    by_day.sort(key=lambda r: r["key"])
    return {**base, "error": None, "visitors": int(total.get("visitors") or 0), "pageviews": int(total.get("pageviews") or 0),
            "by_day": by_day, "pages": pages, "referrers": refs, "countries": countries, "devices": devices}


# ---------------------------------------------------------------- Google Analytics 4

def _ga_access_token(sa: dict) -> str:
    import jwt

    now = int(time.time())
    assertion = jwt.encode(
        {"iss": sa["client_email"], "scope": "https://www.googleapis.com/auth/analytics.readonly",
         "aud": GA_TOKEN_URL, "iat": now, "exp": now + 3600},
        sa["private_key"], algorithm="RS256", headers={"kid": sa.get("private_key_id")},
    )
    r = httpx.post(GA_TOKEN_URL, data={"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", "assertion": assertion},
                   timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()["access_token"]


def ga_report(token: str, property_id: str, body: dict) -> list[dict]:
    r = httpx.post(f"{GA_DATA_API}/{property_id}:runReport", json=body, headers={"Authorization": f"Bearer {token}"}, timeout=TIMEOUT)
    r.raise_for_status()
    rows = []
    for row in r.json().get("rows") or []:
        dims = [d.get("value", "") for d in row.get("dimensionValues") or []]
        mets = [m.get("value", "0") for m in row.get("metricValues") or []]
        rows.append({"dims": dims, "metrics": mets})
    return rows


def _n(v: str) -> int:
    try:
        return int(float(v))
    except ValueError:
        return 0


def ga_stats(days: int) -> dict:
    s = get_settings()
    configured = bool(s.ga4_property_id and s.ga_service_account_json)
    base = {"configured": configured, "property_id": s.ga4_property_id,
            "dashboard": f"https://analytics.google.com/analytics/web/#/p{s.ga4_property_id}/reports/intro" if s.ga4_property_id
            else "https://analytics.google.com/"}
    if not configured:
        return {**base, "error": None}
    try:
        sa = json.loads(s.ga_service_account_json or "{}")
        token = _ga_access_token(sa)
        rng = [{"startDate": f"{days}daysAgo", "endDate": "today"}]
        pid = s.ga4_property_id or ""
        totals = ga_report(token, pid, {"dateRanges": rng, "metrics": [{"name": "activeUsers"}, {"name": "sessions"}, {"name": "screenPageViews"}]})
        by_day = ga_report(token, pid, {"dateRanges": rng, "dimensions": [{"name": "date"}], "metrics": [{"name": "activeUsers"}, {"name": "screenPageViews"}],
                                        "orderBys": [{"dimension": {"dimensionName": "date"}}]})
        pages = ga_report(token, pid, {"dateRanges": rng, "dimensions": [{"name": "pagePath"}], "metrics": [{"name": "screenPageViews"}],
                                       "orderBys": [{"metric": {"metricName": "screenPageViews"}, "desc": True}], "limit": 10})
        sources = ga_report(token, pid, {"dateRanges": rng, "dimensions": [{"name": "sessionSource"}], "metrics": [{"name": "sessions"}],
                                         "orderBys": [{"metric": {"metricName": "sessions"}, "desc": True}], "limit": 10})
    except (httpx.HTTPError, KeyError, ValueError) as e:
        return {**base, "error": f"Google Analytics svarede ikke: {e}"}
    t = totals[0]["metrics"] if totals else ["0", "0", "0"]
    return {**base, "error": None, "users": _n(t[0]), "sessions": _n(t[1]), "pageviews": _n(t[2]),
            "by_day": [{"key": f"{r['dims'][0][:4]}-{r['dims'][0][4:6]}-{r['dims'][0][6:]}", "visitors": _n(r["metrics"][0]), "pageviews": _n(r["metrics"][1])} for r in by_day],
            "pages": [{"key": r["dims"][0], "pageviews": _n(r["metrics"][0])} for r in pages],
            "sources": [{"key": r["dims"][0], "sessions": _n(r["metrics"][0])} for r in sources]}


# ---------------------------------------------------------------- combined

def website_stats(days: int) -> dict:
    key = f"website:{days}"
    hit = _cache.get(key)
    if hit and hit[0] > time.monotonic():
        return hit[1]
    out = {"days": days, "fetched_at": datetime.now(UTC).isoformat(), "vercel": vercel_stats(days), "ga": ga_stats(days)}
    _cache[key] = (time.monotonic() + CACHE_SECONDS, out)
    return out


def clear_cache() -> None:
    _cache.clear()

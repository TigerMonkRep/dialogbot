"""Valgfri Google Search Console-sektion: klik, visninger, CTR, position, top-søgninger, top-sider og indekseringsstatus.

Kun standardbiblioteket: service account-nøglen (PKCS#8-PEM) parses og bruges til at signere et RS256-JWT, som byttes
til et access token. Modulet fejler blødt – mangler GSC_SERVICE_ACCOUNT_JSON eller GSC_SITE_URL, springes det over,
og enhver fejl bliver en note i rapporten i stedet for en nedbrudt scanning.

Miljø:  GSC_SERVICE_ACCOUNT_JSON  JSON-indholdet af nøglefilen (eller en sti til den)
        GSC_SITE_URL              property i Search Console, fx https://www.dialogbot.dk/ eller sc-domain:dialogbot.dk
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

TOKEN_URL = "https://oauth2.googleapis.com/token"
SCOPE = "https://www.googleapis.com/auth/webmasters.readonly"
SEARCH_API = "https://searchconsole.googleapis.com/webmasters/v3/sites/{site}/searchAnalytics/query"
INSPECT_API = "https://searchconsole.googleapis.com/v1/urlInspection/index:inspect"
DATA_LAG_DAYS = 3        # Search Console-data er typisk 2-3 dage forsinket
DEFAULT_DAYS = 28
MAX_HISTORY = 60

# En HTTP-funktion: (url, json-body eller None, headers) -> (status, parsed json). Erstattes i tests.
Http = Callable[[str, dict | None, dict[str, str]], tuple[int, dict]]


class GscError(Exception):
    """Forståelig fejl til rapporten (ingen hemmeligheder i teksten)."""


# ---------------------------------------------------------------------------------------------------
# Konfiguration
# ---------------------------------------------------------------------------------------------------
def load_config(env: dict[str, str] | None = None) -> tuple[dict, str] | None:
    """(service account, site_url) eller None, hvis sektionen skal springes over."""
    env = os.environ if env is None else env
    raw, site = env.get("GSC_SERVICE_ACCOUNT_JSON", "").strip(), env.get("GSC_SITE_URL", "").strip()
    if not raw or not site:
        return None
    if not raw.startswith("{"):
        p = Path(raw)
        if not p.is_file():
            raise GscError("GSC_SERVICE_ACCOUNT_JSON er hverken JSON eller en sti til en fil")
        raw = p.read_text()
    try:
        sa = json.loads(raw)
    except ValueError:
        raise GscError("GSC_SERVICE_ACCOUNT_JSON er ikke gyldig JSON") from None
    for key in ("client_email", "private_key"):
        if not sa.get(key):
            raise GscError(f"service account-nøglen mangler feltet {key}")
    return sa, site


# ---------------------------------------------------------------------------------------------------
# RS256-JWT uden eksterne biblioteker
# ---------------------------------------------------------------------------------------------------
def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _der_read(data: bytes, pos: int) -> tuple[int, bytes, int]:
    """Læser ét DER-element: (tag, indhold, næste position)."""
    tag = data[pos]
    length = data[pos + 1]
    pos += 2
    if length & 0x80:
        n = length & 0x7F
        length = int.from_bytes(data[pos:pos + n], "big")
        pos += n
    return tag, data[pos:pos + length], pos + length


def _der_sequence(data: bytes) -> list[tuple[int, bytes]]:
    tag, body, _ = _der_read(data, 0)
    if tag != 0x30:
        raise GscError("private_key: forventede en DER SEQUENCE")
    items, pos = [], 0
    while pos < len(body):
        t, v, pos = _der_read(body, pos)
        items.append((t, v))
    return items


def parse_private_key(pem: str) -> tuple[int, int, int]:
    """(n, e, d) fra en PKCS#8 ('BEGIN PRIVATE KEY') eller PKCS#1 ('BEGIN RSA PRIVATE KEY') PEM-nøgle."""
    lines = [ln.strip() for ln in pem.replace("\\n", "\n").splitlines() if ln.strip() and not ln.startswith("-----")]
    try:
        der = base64.b64decode("".join(lines))
        items = _der_sequence(der)
        if len(items) == 3 and items[2][0] == 0x04:  # PKCS#8: version, algorithm, OCTET STRING(RSAPrivateKey)
            items = _der_sequence(items[2][1])
        ints = [int.from_bytes(v, "big") for t, v in items if t == 0x02]
        if len(ints) < 4:
            raise ValueError
        _version, n, e, d = ints[:4]
    except (ValueError, IndexError, GscError):
        raise GscError("private_key kunne ikke læses – er det en RSA-nøgle i PEM-format?") from None
    return n, e, d


# DigestInfo-prefix for SHA-256 (RFC 8017, 9.2 note 1)
_SHA256_PREFIX = bytes.fromhex("3031300d060960864801650304020105000420")


def rs256_sign(message: bytes, key: tuple[int, int, int]) -> bytes:
    """RSASSA-PKCS1-v1_5 med SHA-256."""
    n, _e, d = key
    k = (n.bit_length() + 7) // 8
    t = _SHA256_PREFIX + hashlib.sha256(message).digest()
    if k < len(t) + 11:
        raise GscError("RSA-nøglen er for kort")
    em = b"\x00\x01" + b"\xff" * (k - len(t) - 3) + b"\x00" + t
    return pow(int.from_bytes(em, "big"), d, n).to_bytes(k, "big")


def rs256_verify(message: bytes, signature: bytes, n: int, e: int) -> bool:
    """Kun til tests: kontrollerer en signatur med den offentlige del af nøglen."""
    k = (n.bit_length() + 7) // 8
    em = pow(int.from_bytes(signature, "big"), e, n).to_bytes(k, "big")
    t = _SHA256_PREFIX + hashlib.sha256(message).digest()
    return em == b"\x00\x01" + b"\xff" * (k - len(t) - 3) + b"\x00" + t


def make_jwt(sa: dict, now: int | None = None, scope: str = SCOPE) -> str:
    now = int(time.time()) if now is None else now
    header = {"alg": "RS256", "typ": "JWT", **({"kid": sa["private_key_id"]} if sa.get("private_key_id") else {})}
    claims = {"iss": sa["client_email"], "scope": scope, "aud": sa.get("token_uri") or TOKEN_URL, "iat": now, "exp": now + 3600}
    signing_input = f"{_b64url(json.dumps(header, separators=(',', ':')).encode())}.{_b64url(json.dumps(claims, separators=(',', ':')).encode())}"
    sig = rs256_sign(signing_input.encode(), parse_private_key(sa["private_key"]))
    return f"{signing_input}.{_b64url(sig)}"


# ---------------------------------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------------------------------
def http_json(url: str, body: dict | None, headers: dict[str, str], timeout: float = 30) -> tuple[int, dict]:
    """POST (JSON) eller GET. Fejlsvar returneres som (status, {"error": ...}) – ingen exceptions for 4xx/5xx."""
    data = None
    hdrs = {"Accept": "application/json", **headers}
    if body is not None:
        data = json.dumps(body).encode()
        hdrs["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=hdrs, method="POST" if body is not None else "GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode() or "{}")
    except urllib.error.HTTPError as exc:
        try:
            payload = json.loads(exc.read().decode() or "{}")
        except ValueError:
            payload = {}
        return exc.code, payload
    except Exception as exc:  # netværk, TLS, timeout
        raise GscError(f"netværksfejl mod Google: {type(exc).__name__}") from None


def _post_form(url: str, fields: dict[str, str], timeout: float = 30) -> tuple[int, dict]:
    data = "&".join(f"{quote(k, safe='')}={quote(v, safe='')}" for k, v in fields.items()).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/x-www-form-urlencoded"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode() or "{}")
    except urllib.error.HTTPError as exc:
        try:
            return exc.code, json.loads(exc.read().decode() or "{}")
        except ValueError:
            return exc.code, {}
    except Exception as exc:
        raise GscError(f"netværksfejl mod Google: {type(exc).__name__}") from None


def fetch_token(sa: dict, post_form: Callable[[str, dict[str, str]], tuple[int, dict]] = _post_form) -> str:
    status, payload = post_form(sa.get("token_uri") or TOKEN_URL,
                                {"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", "assertion": make_jwt(sa)})
    if status != 200 or not payload.get("access_token"):
        why = payload.get("error_description") or payload.get("error") or f"HTTP {status}"
        raise GscError(f"kunne ikke få et access token ({why}) – er service account-nøglen gyldig?")
    return payload["access_token"]


def _explain(status: int, payload: dict, site: str) -> str:
    msg = (payload.get("error") or {}).get("message", "") if isinstance(payload.get("error"), dict) else str(payload.get("error", ""))
    if status == 403:
        return (f"adgang nægtet (403) til {site} – er service account-mailen tilføjet som bruger på property'en, "
                "og er «Google Search Console API» aktiveret i Google Cloud-projektet?")
    if status == 404:
        return f"property'en {site} findes ikke (404) – GSC_SITE_URL skal matche præcis, fx «https://www.dialogbot.dk/» eller «sc-domain:dialogbot.dk»"
    if status == 429:
        return "Search Console-kvoten er opbrugt (429) – prøv igen i morgen eller sænk antallet af URL-inspektioner"
    return f"Search Console svarede HTTP {status}" + (f": {msg}" if msg else "")


# ---------------------------------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------------------------------
def period(today: date | None = None, days: int = DEFAULT_DAYS) -> tuple[str, str]:
    today = today or datetime.now(timezone.utc).date()
    end = today - timedelta(days=DATA_LAG_DAYS)
    return (end - timedelta(days=days - 1)).isoformat(), end.isoformat()


def _rows(payload: dict) -> list[dict]:
    out = []
    for row in payload.get("rows", []):
        out.append({"key": (row.get("keys") or [""])[0], "clicks": row.get("clicks", 0), "impressions": row.get("impressions", 0),
                    "ctr": round(row.get("ctr", 0) * 100, 1), "position": round(row.get("position", 0), 1)})
    return out


def search_analytics(http: Http, token: str, site: str, start: str, end: str, dimension: str | None, limit: int = 20) -> dict:
    body: dict = {"startDate": start, "endDate": end, "rowLimit": limit, "dataState": "final"}
    if dimension:
        body["dimensions"] = [dimension]
    status, payload = http(SEARCH_API.format(site=quote(site, safe="")), body, {"Authorization": f"Bearer {token}"})
    if status != 200:
        raise GscError(_explain(status, payload, site))
    return payload


def inspect_url(http: Http, token: str, site: str, url: str) -> dict:
    status, payload = http(INSPECT_API, {"inspectionUrl": url, "siteUrl": site, "languageCode": "da"}, {"Authorization": f"Bearer {token}"})
    if status != 200:
        raise GscError(_explain(status, payload, site))
    idx = (payload.get("inspectionResult") or {}).get("indexStatusResult") or {}
    return {"url": url, "verdict": idx.get("verdict", "VERDICT_UNSPECIFIED"), "coverage": idx.get("coverageState", ""),
            "robots": idx.get("robotsTxtState", ""), "indexing": idx.get("indexingState", ""),
            "last_crawl": (idx.get("lastCrawlTime") or "")[:10], "canonical_google": idx.get("googleCanonical", "")}


def collect(sa: dict, site: str, sitemap_urls: list[str], http: Http = http_json, token: str | None = None,
            today: date | None = None, max_inspect: int = 20) -> dict:
    """Henter alt til rapportens Search Console-sektion. Fejl i én del stopper ikke de andre (se 'errors')."""
    start, end = period(today)
    out: dict = {"site": site, "period": {"start": start, "end": end}, "totals": {}, "queries": [], "pages": [],
                 "indexing": {"inspected": 0, "indexed": 0, "not_indexed": 0, "items": []}, "errors": []}
    try:
        token = token or fetch_token(sa)
    except GscError as exc:
        out["errors"].append(str(exc))
        return out
    try:
        total = _rows(search_analytics(http, token, site, start, end, None, 1))
        out["totals"] = total[0] if total else {"clicks": 0, "impressions": 0, "ctr": 0.0, "position": 0.0}
        out["totals"].pop("key", None)
        out["queries"] = _rows(search_analytics(http, token, site, start, end, "query"))
        out["pages"] = _rows(search_analytics(http, token, site, start, end, "page"))
    except GscError as exc:
        out["errors"].append(f"søgeanalyse: {exc}")
    for url in sitemap_urls[:max_inspect]:
        try:
            item = inspect_url(http, token, site, url)
        except GscError as exc:
            out["errors"].append(f"URL-inspektion: {exc}")
            break
        out["indexing"]["items"].append(item)
        out["indexing"]["inspected"] += 1
        out["indexing"]["indexed" if item["verdict"] == "PASS" else "not_indexed"] += 1
    return out


# ---------------------------------------------------------------------------------------------------
# Historik og rapport
# ---------------------------------------------------------------------------------------------------
def update_history(path: Path, data: dict, scanned_at: str) -> list[dict]:
    """Gemmer periodens nøgletal i en lille JSON-liste (én linje pr. scanning) og returnerer hele historikken."""
    history: list[dict] = []
    if path.is_file():
        try:
            history = json.loads(path.read_text())
        except ValueError:
            history = []
    if data.get("totals"):
        entry = {"scanned_at": scanned_at, **data["period"], **{k: data["totals"].get(k) for k in ("clicks", "impressions", "ctr", "position")},
                 "indexed": data["indexing"]["indexed"], "inspected": data["indexing"]["inspected"]}
        history = [h for h in history if h.get("scanned_at") != scanned_at] + [entry]
        history = history[-MAX_HISTORY:]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(history, ensure_ascii=False, indent=1))
    return history


def _delta(cur: float | None, prev: float | None, suffix: str = "", better_low: bool = False) -> str:
    if cur is None or prev is None:
        return ""
    d = cur - prev
    if abs(d) < 0.05:
        return " (=)"
    arrow = ("▼" if better_low else "▲") if d > 0 else ("▲" if better_low else "▼")
    return f" ({arrow} {d:+.1f}{suffix})" if isinstance(cur, float) or isinstance(prev, float) else f" ({arrow} {d:+d}{suffix})"


def markdown_section(data: dict | None, history: list[dict] | None = None) -> list[str]:
    if not data:
        return []
    L = ["", "## Google Search Console", ""]
    p = data.get("period", {})
    L.append(f"Property `{data.get('site')}` · {p.get('start')} – {p.get('end')} (28 dage, Google-data er ca. 3 dage forsinket)")
    for err in data.get("errors", []):
        L.append(f"> ⚠️ {err}")
    t = data.get("totals") or {}
    if t:
        prev = None
        for h in (history or [])[:-1][::-1]:
            if h.get("end") != p.get("end"):
                prev = h
                break
        L += ["", "| Klik | Visninger | CTR | Gns. position |", "|---|---|---|---|",
              f"| {t.get('clicks', 0)}{_delta(t.get('clicks'), prev and prev.get('clicks'))} "
              f"| {t.get('impressions', 0)}{_delta(t.get('impressions'), prev and prev.get('impressions'))} "
              f"| {t.get('ctr', 0)} %{_delta(t.get('ctr'), prev and prev.get('ctr'), ' pp')} "
              f"| {t.get('position', 0)}{_delta(t.get('position'), prev and prev.get('position'), '', better_low=True)} |"]
        if prev:
            L.append(f"(ændring i forhold til scanningen {prev.get('scanned_at', '')[:10]}, perioden {prev.get('start')} – {prev.get('end')})")
        if not data.get("queries") and not data.get("pages"):
            L.append("Ingen søgninger registreret i perioden endnu – sitet er nyt, eller Google har ikke data endnu.")
    for title, rows in (("Vigtigste søgeforespørgsler", data.get("queries", [])), ("Vigtigste sider", data.get("pages", []))):
        if rows:
            L += ["", f"### {title} (top {len(rows)})", "", "| # | " + ("Forespørgsel" if "søge" in title else "Side") + " | Klik | Visninger | CTR | Position |", "|---|---|---|---|---|---|"]
            for i, r in enumerate(rows, 1):
                L.append(f"| {i} | {r['key']} | {r['clicks']} | {r['impressions']} | {r['ctr']} % | {r['position']} |")
    idx = data.get("indexing") or {}
    if idx.get("inspected"):
        L += ["", f"### Indeksering ({idx['indexed']} af {idx['inspected']} inspicerede sitemap-sider er indekseret)", ""]
        bad = [i for i in idx["items"] if i["verdict"] != "PASS"]
        for i in bad:
            L.append(f"- ❌ `{i['url']}` – {i['coverage'] or i['verdict']}" + (f" · robots: {i['robots']}" if i.get("robots") not in ("", "ALLOWED") else "")
                     + (f" · Google vælger canonical {i['canonical_google']}" if i.get("canonical_google") and i["canonical_google"] != i["url"] else ""))
        if not bad:
            L.append("- ✅ Alle inspicerede sider er indekseret.")
        crawled = [i["last_crawl"] for i in idx["items"] if i.get("last_crawl")]
        if crawled:
            L.append(f"- Seneste crawl: {max(crawled)}")
    if history and len(history) > 1:
        L += ["", "### Udvikling", "", "| Scanning | Periode | Klik | Visninger | CTR | Position |", "|---|---|---|---|---|---|"]
        for h in history[-8:]:
            L.append(f"| {h.get('scanned_at', '')[:10]} | {h.get('start')} – {h.get('end')} | {h.get('clicks')} | {h.get('impressions')} | {h.get('ctr')} % | {h.get('position')} |")
    return L

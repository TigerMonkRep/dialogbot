"""Valgfri Core Web Vitals via Googles PageSpeed Insights API (Lighthouse + CrUX-feltdata). Gratis; API-nøgle undgår 429."""
from __future__ import annotations

import json
from urllib.parse import quote

from .checks import FAIL, PASS, WARN, Result
from .fetch import Fetcher

API = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"
STRATEGIES = ("mobile", "desktop")

# Tærskler (god, acceptabel) pr. måling – Googles egne grænser for Core Web Vitals.
LAB_THRESHOLDS = {"lcp": (2500, 4000), "cls": (0.1, 0.25), "tbt": (200, 600)}
FIELD_METRICS = {  # CrUX-nøgle → (id-suffix, etiket, god, acceptabel, format)
    "LARGEST_CONTENTFUL_PAINT_MS": ("lcp", "LCP", 2500, 4000, "{:.0f} ms"),
    "INTERACTION_TO_NEXT_PAINT": ("inp", "INP", 200, 500, "{:.0f} ms"),
    "CUMULATIVE_LAYOUT_SHIFT_SCORE": ("cls", "CLS", 0.1, 0.25, "{:.2f}"),
}


def explain_error(status: int | None, error: str | None, has_key: bool) -> str:
    """Forståelig note til rapporten, når PageSpeed ikke kunne hentes."""
    if status == 429:
        return ("PageSpeed Insights: kvoten er opbrugt (HTTP 429). " +
                ("Prøv igen senere – nøglen har en daglig grænse i Google Cloud Console." if has_key
                 else "Uden API-nøgle deles kvoten med alle; opret en gratis nøgle og sæt PSI_API_KEY."))
    if status == 403:
        return ("PageSpeed Insights: adgang nægtet (HTTP 403). " +
                ("Tjek at PSI_API_KEY er gyldig, og at «PageSpeed Insights API» er aktiveret i Google Cloud-projektet."
                 if has_key else "Google afviser anonyme kald lige nu – sæt PSI_API_KEY."))
    if status == 400:
        return "PageSpeed Insights: Google kunne ikke analysere siden (HTTP 400) – svarer den 200 for Googles crawler?"
    if status == 500 or status == 503:
        return f"PageSpeed Insights: Googles tjeneste fejlede midlertidigt (HTTP {status}) – prøv igen senere."
    return f"PageSpeed Insights kunne ikke hentes: {('HTTP ' + str(status)) if status else error}"


def run_psi(fetcher: Fetcher, url: str, key: str | None = None, strategy: str = "mobile") -> tuple[list[Result], dict, list[str]]:
    """Kører PSI for `strategy` ('mobile', 'desktop' eller 'both'). (resultater, nøgletal pr. strategi, noter).
    Fejl er ikke fatale – scanningen fortsætter uden PSI."""
    wanted = STRATEGIES if strategy == "both" else (strategy,)
    results: list[Result] = []
    metrics: dict = {}
    notes: list[str] = []
    for strat in wanted:
        rs, m, err = _run_one(fetcher, url, key, strat)
        results += rs
        if m:
            metrics[strat] = m
        if err:
            notes.append(err)
    return results, metrics, notes


def _run_one(fetcher: Fetcher, url: str, key: str | None, strategy: str) -> tuple[list[Result], dict, str | None]:
    q = f"{API}?url={quote(url, safe='')}&strategy={strategy}&category=performance&category=accessibility"
    if key:
        q += f"&key={quote(key)}"
    resp = Fetcher(timeout=90).get(q) if fetcher.timeout < 90 else fetcher.get(q)
    if not resp.ok:
        return [], {}, explain_error(resp.status or None, resp.error, bool(key)).replace("PageSpeed Insights", f"PageSpeed Insights ({strategy})", 1)
    try:
        data = json.loads(resp.text)
    except ValueError:
        return [], {}, f"PageSpeed Insights ({strategy}) gav et uventet svar"
    if "lighthouseResult" not in data:
        return [], {}, f"PageSpeed Insights ({strategy}) gav et uventet svar"
    results, metrics, _ = parse_lighthouse(data["lighthouseResult"], url, strategy)
    field = parse_field_data(data.get("loadingExperience"), url, strategy)
    if field:
        results += field[0]
        metrics["field"] = field[1]
    return results, metrics, None


def _grade(val: float | None, good: float, ok: float) -> str | None:
    if val is None:
        return None
    return PASS if val <= good else WARN if val <= ok else FAIL


def parse_lighthouse(data: dict, url: str, strategy: str = "mobile") -> tuple[list[Result], dict, None]:
    """Lab-data (Lighthouse). Tjek-id'er for desktop får suffikset _desktop, så begge kan stå i samme rapport."""
    cats, audits = data.get("categories", {}), data.get("audits", {})
    perf = round((cats.get("performance", {}).get("score") or 0) * 100)
    a11y = round((cats.get("accessibility", {}).get("score") or 0) * 100)
    lcp = audits.get("largest-contentful-paint", {}).get("numericValue")
    cls = audits.get("cumulative-layout-shift", {}).get("numericValue")
    tbt = audits.get("total-blocking-time", {}).get("numericValue")
    sfx = "" if strategy == "mobile" else f"_{strategy}"

    out: list[Result] = []
    st = PASS if perf >= 90 else WARN if perf >= 50 else FAIL
    out.append(Result(f"psi_perf{sfx}", st, url, f"score {perf}/100 ({strategy})"))
    for cid, val, fmt in (("psi_lcp", lcp, "LCP {:.0f} ms"), ("psi_cls", cls, "CLS {:.3f}"), ("psi_tbt", tbt, "TBT {:.0f} ms")):
        good, ok = LAB_THRESHOLDS[cid.split("_")[1]]
        status = _grade(val, good, ok)
        if status:
            out.append(Result(f"{cid}{sfx}", status, url, fmt.format(val)))
    out.append(Result(f"psi_a11y{sfx}", PASS if a11y >= 90 else WARN if a11y >= 70 else FAIL, url, f"score {a11y}/100"))
    return out, {"performance": perf, "accessibility": a11y, "lcp_ms": lcp, "cls": cls, "tbt_ms": tbt}, None


def parse_field_data(loading: dict | None, url: str, strategy: str = "mobile") -> tuple[list[Result], dict] | None:
    """CrUX-feltdata (rigtige brugere de sidste 28 dage). Google leverer det kun, når sitet har nok trafik."""
    if not loading or not loading.get("metrics"):
        return None
    sfx = "" if strategy == "mobile" else f"_{strategy}"
    out: list[Result] = []
    summary: dict = {"overall": loading.get("overall_category"), "origin_fallback": bool(loading.get("origin_fallback"))}
    for key, (mid, label, good, ok, fmt) in FIELD_METRICS.items():
        m = loading["metrics"].get(key)
        if not m or m.get("percentile") is None:
            continue
        val = m["percentile"] / (100 if mid == "cls" else 1)  # CrUX leverer CLS × 100
        summary[mid] = val
        out.append(Result(f"crux_{mid}{sfx}", _grade(val, good, ok) or PASS, url, f"{label} {fmt.format(val)} (75. percentil, feltdata)"))
    return out, summary

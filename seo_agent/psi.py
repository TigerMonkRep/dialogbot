"""Valgfri Core Web Vitals via Googles PageSpeed Insights API (Lighthouse). Gratis; API-nøgle undgår 429."""
from __future__ import annotations

import json
from urllib.parse import quote

from .checks import FAIL, PASS, WARN, Result
from .fetch import Fetcher

API = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"


def run_psi(fetcher: Fetcher, url: str, key: str | None = None, strategy: str = "mobile") -> tuple[list[Result], dict, str | None]:
    """(resultater, nøgletal, fejl). Fejl er ikke fatale – scanningen fortsætter uden PSI."""
    q = f"{API}?url={quote(url, safe='')}&strategy={strategy}&category=performance&category=accessibility"
    if key:
        q += f"&key={quote(key)}"
    resp = Fetcher(timeout=90).get(q) if fetcher.timeout < 90 else fetcher.get(q)
    if not resp.ok:
        why = "kvoten er brugt (429) – sæt PSI_API_KEY" if resp.status == 429 else f"HTTP {resp.status or resp.error}"
        return [], {}, f"PageSpeed Insights kunne ikke hentes: {why}"
    try:
        data = json.loads(resp.text)["lighthouseResult"]
    except (ValueError, KeyError):
        return [], {}, "PageSpeed Insights gav et uventet svar"
    return parse_lighthouse(data, url)


def parse_lighthouse(data: dict, url: str) -> tuple[list[Result], dict, None]:
    cats, audits = data.get("categories", {}), data.get("audits", {})
    perf = round((cats.get("performance", {}).get("score") or 0) * 100)
    a11y = round((cats.get("accessibility", {}).get("score") or 0) * 100)
    lcp = audits.get("largest-contentful-paint", {}).get("numericValue")
    cls = audits.get("cumulative-layout-shift", {}).get("numericValue")
    tbt = audits.get("total-blocking-time", {}).get("numericValue")

    def grade(val: float | None, good: float, ok: float, fmt: str) -> tuple[str, str]:
        if val is None:
            return "", ""
        return (PASS if val <= good else WARN if val <= ok else FAIL), fmt.format(val)

    out: list[Result] = []
    st = PASS if perf >= 90 else WARN if perf >= 50 else FAIL
    out.append(Result("psi_perf", st, url, f"score {perf}/100 (mobil)"))
    for cid, val, good, ok, fmt in (("psi_lcp", lcp, 2500, 4000, "LCP {:.0f} ms"), ("psi_cls", cls, 0.1, 0.25, "CLS {:.3f}"),
                                    ("psi_tbt", tbt, 200, 600, "TBT {:.0f} ms")):
        status, detail = grade(val, good, ok, fmt)
        if status:
            out.append(Result(cid, status, url, detail))
    out.append(Result("psi_a11y", PASS if a11y >= 90 else WARN if a11y >= 70 else FAIL, url, f"score {a11y}/100"))
    return out, {"performance": perf, "accessibility": a11y, "lcp_ms": lcp, "cls": cls, "tbt_ms": tbt}, None

"""Scoring, prioritering, markdown/JSON-rapport og sammenligning med forrige scanning."""
from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from urllib.parse import urlparse

from .catalog import CATALOG, CATEGORIES
from .checks import FAIL, INFO, PASS, WARN, Result

POINTS = {PASS: 1.0, WARN: 0.5, FAIL: 0.0}
RANK = {PASS: 0, INFO: 0, WARN: 1, FAIL: 2}
PRIORITY = [(6.0, "Kritisk"), (3.0, "Høj"), (1.5, "Medium"), (0.0, "Lav")]


def priority_of(weight: int, points: float) -> str:
    impact = weight * (1 - points)
    return next(label for threshold, label in PRIORITY if impact >= threshold)


@dataclass
class Report:
    site: str
    scanned_at: str
    pages_scanned: int
    results: list[Result]
    notes: list[str] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)
    page_list: list[str] = field(default_factory=list)

    # --- aggregering --------------------------------------------------------------------------
    def checks(self) -> dict[str, dict]:
        by: dict[str, list[Result]] = defaultdict(list)
        for r in self.results:
            if r.check in CATALOG and r.status in POINTS:
                by[r.check].append(r)
        out = {}
        for cid, rs in by.items():
            info = CATALOG[cid]
            points = sum(POINTS[r.status] for r in rs) / len(rs)
            worst = max((r.status for r in rs), key=lambda s: RANK[s])
            out[cid] = {
                "status": worst, "points": round(points, 3), "weight": info.weight, "category": info.category,
                "priority": priority_of(info.weight, points) if worst != PASS else None,
                "checked": len(rs), "failing": sum(r.status != PASS for r in rs),
                "affected": [{"url": r.url, "detail": r.detail} for r in rs if r.status != PASS],
            }
        return out

    def category_scores(self) -> dict[str, int]:
        agg = self.checks()
        scores = {}
        for cat in CATEGORIES:
            items = [v for v in agg.values() if v["category"] == cat]
            if items:
                scores[cat] = round(100 * sum(v["weight"] * v["points"] for v in items) / sum(v["weight"] for v in items))
        return scores

    def score(self) -> int:
        agg = self.checks()
        total = sum(v["weight"] for v in agg.values())
        return round(100 * sum(v["weight"] * v["points"] for v in agg.values()) / total) if total else 0

    def issues(self) -> list[tuple[str, dict]]:
        agg = self.checks()
        bad = [(cid, v) for cid, v in agg.items() if v["status"] != PASS]
        return sorted(bad, key=lambda kv: (-(kv[1]["weight"] * (1 - kv[1]["points"])), kv[0]))

    # --- output -------------------------------------------------------------------------------
    def to_dict(self) -> dict:
        return {"site": self.site, "scanned_at": self.scanned_at, "pages_scanned": self.pages_scanned, "score": self.score(),
                "categories": self.category_scores(), "checks": self.checks(), "notes": self.notes,
                "metrics": self.metrics, "pages": self.page_list}

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    def to_markdown(self, previous: dict | None = None) -> str:
        agg = self.checks()
        score = self.score()
        L = [f"# SEO-rapport – {urlparse(self.site).netloc}", "",
             f"**Samlet score: {score}/100** {_bar(score)}  ·  {self.pages_scanned} sider scannet  ·  {self.scanned_at}", ""]
        if previous:
            L += _diff_lines(previous, self.to_dict())
        for n in self.notes:
            L.append(f"> ⚠️ {n}")
        if self.metrics:
            m = self.metrics
            L += ["", f"Lighthouse (mobil): ydeevne **{m.get('performance')}**, tilgængelighed **{m.get('accessibility')}**"
                  f" · LCP {_n(m.get('lcp_ms'), 0)} ms · CLS {_n(m.get('cls'), 3)} · TBT {_n(m.get('tbt_ms'), 0)} ms"]
        L += ["", "## Score pr. kategori", "", "| Kategori | Score |", "|---|---|"]
        L += [f"| {c} | {s} {_bar(s)} |" for c, s in self.category_scores().items()]
        issues = self.issues()
        L += ["", f"## Handlingsplan ({len(issues)} punkter, vigtigste først)", ""]
        if not issues:
            L.append("Ingen åbne punkter. 🎉")
        for i, (cid, v) in enumerate(issues, 1):
            info = CATALOG[cid]
            icon = {"Kritisk": "🔴", "Høj": "🟠", "Medium": "🟡"}.get(v["priority"], "⚪")
            L += [f"### {i}. {icon} {info.title} — *{v['priority']}* · {info.category}", "",
                  f"- **Hvorfor:** {info.why}", f"- **Sådan retter du det:** {info.fix}",
                  f"- **Omfang:** {v['failing']} af {v['checked']} tjekket"]
            for a in v["affected"][:5]:
                path = urlparse(a["url"]).path or "/"
                L.append(f"  - `{path}` {('– ' + a['detail']) if a['detail'] else ''}".rstrip())
            if len(v["affected"]) > 5:
                L.append(f"  - … og {len(v['affected']) - 5} flere")
            L.append("")
        passed = sorted(CATALOG[c].title for c, v in agg.items() if v["status"] == PASS)
        L += [f"## Bestået ({len(passed)})", ""] + [f"- ✅ {t}" for t in passed]
        return "\n".join(L) + "\n"


def _bar(score: int) -> str:
    filled = round(score / 10)
    return "█" * filled + "░" * (10 - filled)


def _n(v, d: int) -> str:
    return "–" if v is None else f"{v:.{d}f}"


def diff(previous: dict, current: dict) -> dict:
    prev, cur = previous.get("checks", {}), current.get("checks", {})
    regress, improved, new = [], [], []
    for cid, v in cur.items():
        old = prev.get(cid)
        if old is None:
            if v["status"] != PASS:
                new.append(cid)
        elif RANK[v["status"]] > RANK[old["status"]] or (v["status"] == old["status"] != PASS and v["points"] < old["points"] - 0.05):
            regress.append(cid)
        elif RANK[v["status"]] < RANK[old["status"]] or (v["status"] == old["status"] != PASS and v["points"] > old["points"] + 0.05):
            improved.append(cid)
    return {"score_delta": current["score"] - previous.get("score", 0), "regressions": regress + new, "improvements": improved}


def _diff_lines(previous: dict, current: dict) -> list[str]:
    d = diff(previous, current)
    arrow = "▲" if d["score_delta"] > 0 else "▼" if d["score_delta"] < 0 else "="
    out = [f"**Siden sidst ({previous.get('scanned_at', '?')[:10]}):** {arrow} {d['score_delta']:+d} point"]
    if d["regressions"]:
        out.append("- 🔻 Forværret: " + ", ".join(CATALOG[c].title for c in d["regressions"] if c in CATALOG))
    if d["improvements"]:
        out.append("- 🔺 Forbedret: " + ", ".join(CATALOG[c].title for c in d["improvements"] if c in CATALOG))
    return out + [""]

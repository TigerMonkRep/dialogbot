"""Build the audit's traceability matrix and findings register from the QA team's own files (one system, not two).

    python -m scripts.qa_audit_register docs/qa/<run-id>

Reads qa/scenarios.csv (Erhverv + cross-cutting), qa/privat/scenarios.csv (Privat) and qa/findings/F-*.md (front
matter) and writes <out>/traceability.csv and <out>/findings-register.csv. Scenario statuses are mapped to the audit
result words (PASS, FAIL, BLOCKED, NOT TESTED, NOT APPLICABLE) exactly as .claude/agents/qa-lead.md says. Nothing is
upgraded: «pass-delvist» and «flaky» are FAIL, «todo» is NOT TESTED, a «fixed» finding is still open until verifier
closes it.
"""
from __future__ import annotations

import csv
import glob
import os
import re
import sys

RESULT = {"pass": "PASS", "fail": "FAIL", "blocked": "BLOCKED", "todo": "NOT TESTED", "running": "NOT TESTED",
          "flaky": "FAIL", "pass-delvist": "FAIL", "not-implemented": "FAIL"}
RISK = {"P0": "high", "P1": "medium", "P2": "low"}
CLOSED = {"closed", "wont-fix", "cannot-reproduce", "duplicate"}


def front(path: str) -> dict:
    txt = open(path, encoding="utf-8").read()
    m = re.match(r"---\n(.*?)\n---", txt, re.S)
    meta = {}
    for line in (m.group(1).splitlines() if m else []):
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip()
    short = re.search(r"## Kort\n+(.+)", txt)
    meta["kort"] = short.group(1).strip() if short else ""
    return meta


def findings() -> list[dict]:
    out = []
    for p in sorted(glob.glob("qa/findings/F-*.md")):
        m = front(p)
        sev, st = m.get("severity", ""), m.get("status", "").split()[0] if m.get("status") else ""
        open_ = st not in CLOSED
        out.append({
            "id": m.get("id") or os.path.basename(p)[:-3], "scenario": m.get("scenario", ""), "severity": sev,
            "status": st,
            "launch_blocker": "yes" if open_ and sev in ("S0", "S1") else ("decision" if st == "needs-decision" else "no"),
            "owner": m.get("owner_fix", ""), "summary": m.get("kort", "")[:300], "file": p,
            "retest": "closed by verifier" if st == "closed" else ("awaiting verifier" if st == "fixed" else ""),
        })
    return out


def main(out_dir: str) -> None:
    os.makedirs(out_dir, exist_ok=True)
    fs = findings()
    by_scn: dict[str, list[str]] = {}
    for f in fs:
        if f["status"] not in CLOSED:
            by_scn.setdefault(f["scenario"], []).append(f["id"])
    rows = []
    for src, audience in (("qa/scenarios.csv", "erhverv/fælles"), ("qa/privat/scenarios.csv", "privat")):
        for r in csv.DictReader(open(src, encoding="utf-8")):
            st = (r.get("status") or "todo").strip()
            rows.append({
                "requirement_id": r["id"], "capability": r.get("area", ""), "user_role": r.get("persona") or audience,
                "expected_behaviour": (r.get("acceptance") or r.get("scenario") or "")[:400],
                "source": r.get("source", ""), "risk": RISK.get(r.get("priority", ""), ""), "priority": r.get("priority", ""),
                "implementation_location": r.get("route") or r.get("route_or_endpoint") or "",
                "test_ids": r.get("evidence", "")[:300], "environment": "lokal/CI (fake providers)",
                "result": RESULT.get(st, "NOT TESTED"), "scenario_status": st,
                "evidence": r.get("evidence", "")[:300], "open_findings": " ".join(by_scn.get(r["id"], [])),
            })
    with open(os.path.join(out_dir, "traceability.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    with open(os.path.join(out_dir, "findings-register.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(fs[0]))
        w.writeheader()
        w.writerows(fs)
    from collections import Counter
    print("scenarios:", Counter((r["priority"], r["result"]) for r in rows))
    print("findings open S0/S1:", [f["id"] for f in fs if f["launch_blocker"] == "yes"])
    print("needs-decision:", [f["id"] for f in fs if f["status"] == "needs-decision"])


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "docs/qa/latest")

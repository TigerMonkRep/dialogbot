"""Dry run of the cold outreach pipeline: check, research, write and audit a CSV of leads – and send nothing.

    python -m scripts.outreach_dry_run app/modules/outreach/data/sample_leads.csv --countries US,UK
    python -m scripts.outreach_dry_run leads.csv --countries US,UK --fake-ai --skip-mx   # offline, no API key

Needs DATABASE_URL (a migrated database). Uses Claude through ANTHROPIC_API_KEY unless --fake-ai is given. This script
forces OUTREACH_MODE=dry_run, so it cannot send whatever the environment says. The full report (every decision, brief,
e-mail and audit) is written as JSON; a summary is printed.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("csv", type=Path)
    ap.add_argument("--countries", default="US,UK", help="comma-separated country codes to take from the file")
    ap.add_argument("--batch", default=None)
    ap.add_argument("--fake-ai", action="store_true", help="deterministic stand-in for Claude (no key, no tokens)")
    ap.add_argument("--skip-mx", action="store_true", help="do not look up MX records (offline machines)")
    ap.add_argument("--render", action="store_true", help="also run the dispatcher in dry-run to render the final e-mails")
    ap.add_argument("--out", type=Path, default=None, help="where to write the JSON report")
    a = ap.parse_args(argv)

    os.environ["OUTREACH_MODE"] = "dry_run"
    if a.fake_ai:
        os.environ["AI_PROVIDER"] = "fake"
    elif os.environ.get("ANTHROPIC_API_KEY"):
        os.environ.setdefault("AI_PROVIDER", "anthropic")

    import logging

    import structlog

    structlog.configure(wrapper_class=structlog.make_filtering_bound_logger(logging.WARNING))  # keep the output readable
    from app.config import get_settings
    from app.db import get_session_factory
    from app.modules.outreach.agents.dispatcher import DispatcherAndWebhookHandler
    from app.modules.outreach.agents.sourcing import read_csv
    from app.modules.outreach.pipelines import batch as pipeline

    get_settings.cache_clear()
    batch = a.batch or "dryrun-" + datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    raws = read_csv(a.csv.read_text(encoding="utf-8"))
    with get_session_factory()() as db:
        rep = pipeline.run_batch(db, raws, batch=batch, countries={c.strip().upper() for c in a.countries.split(",") if c.strip()},
                                 mx_check=(lambda _d: True) if a.skip_mx else None)
        if a.render:
            rep["dispatch"] = DispatcherAndWebhookHandler(db).dispatch(limit=500)
            db.commit()
            rep["leads"] = pipeline.report(db, batch)["leads"]
    out = a.out or Path(f"outreach-{batch}.json")
    out.write_text(json.dumps(rep, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    print(f"batch {batch} · mode {rep['mode']} · {len(rep['leads'])} leads · tokens in/out "
          f"{rep['tokens']['input_tokens']}/{rep['tokens']['output_tokens']}")
    print("totals:", ", ".join(f"{k}={v}" for k, v in sorted(rep["totals"].items())))
    for r in rep["leads"]:
        print(f"\n[{r['status']:<14}] {r['country']} · {r['company']} <{r['email']}>")
        if r["status"] in ("blocked", "held", "call_queue"):
            print("   ", "; ".join(r["compliance"].get("reasons", [])))
        d = r["email_draft"]
        if d:
            print(f"    confidence {r['confidence']} · {d['words']} words · audit {'PASSED' if d['audit'].get('passed') else 'FAILED'}")
            for i in d["audit"].get("issues", []):
                print("    ✗", i)
            print("    Subject:", d["subject"])
            print("    " + (d["body"] + "\n\n" + d["footer"]).replace("\n", "\n    "))
    print(f"\nreport: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

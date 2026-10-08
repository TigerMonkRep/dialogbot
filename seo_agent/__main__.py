"""CLI: python -m seo_agent [url] [--psi] [--max-pages N] [--fail-under SCORE] [--fail-on-regression]"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

from .report import diff
from .scan import scan

DEFAULT_URL = "https://www.dialogbot.dk"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="seo_agent", description="SEO-agent: scanner et website som WooRank og laver en prioriteret handlingsplan.")
    ap.add_argument("url", nargs="?", default=DEFAULT_URL)
    ap.add_argument("--max-pages", type=int, default=60, help="maks. antal sider der crawles (standard 60)")
    ap.add_argument("--psi", action="store_true", help="hent også Core Web Vitals fra Google PageSpeed Insights (env PSI_API_KEY anbefales)")
    ap.add_argument("--psi-strategy", choices=["mobile", "desktop", "both"], default="mobile", help="mål mobil, desktop eller begge (standard mobil)")
    ap.add_argument("--out", default="var/seo", help="mappe til rapporter og historik (standard var/seo)")
    ap.add_argument("--baseline", help="sammenlign med denne tidligere JSON-rapport i stedet for seneste lokale scanning")
    ap.add_argument("--json", action="store_true", help="skriv JSON til stdout i stedet for markdown")
    ap.add_argument("--no-save", action="store_true", help="gem ikke rapport/historik")
    ap.add_argument("--fail-under", type=int, help="exit-kode 1 hvis samlet score er lavere")
    ap.add_argument("--fail-on-regression", action="store_true", help="exit-kode 1 hvis noget er blevet dårligere siden sidst")
    args = ap.parse_args(argv)

    report = scan(args.url, max_pages=args.max_pages, psi=args.psi, psi_key=os.environ.get("PSI_API_KEY"), psi_strategy=args.psi_strategy)
    host = urlparse(report.site).netloc.replace(":", "_")
    folder = Path(args.out) / host
    latest = folder / "latest.json"
    previous = None
    src = Path(args.baseline) if args.baseline else latest
    if src.is_file():
        try:
            previous = json.loads(src.read_text())
        except ValueError:
            previous = None

    md = report.to_markdown(previous)
    print(report.to_json() if args.json else md)
    if not args.no_save:
        folder.mkdir(parents=True, exist_ok=True)
        stamp = report.scanned_at.replace(":", "").replace("-", "")[:15]
        (folder / f"{stamp}.json").write_text(report.to_json())
        latest.write_text(report.to_json())
        (folder / "latest.md").write_text(md)

    code = 0
    if args.fail_under is not None and report.score() < args.fail_under:
        print(f"Score {report.score()} er under grænsen {args.fail_under}", file=sys.stderr)
        code = 1
    if args.fail_on_regression and previous and diff(previous, report.to_dict())["regressions"]:
        print("Der er regressioner siden sidste scanning", file=sys.stderr)
        code = 1
    return code


if __name__ == "__main__":
    raise SystemExit(main())

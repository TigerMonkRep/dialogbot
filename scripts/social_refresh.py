"""Rebuild social drafts in the current design – the same code the worker runs by itself (service.refresh_stale_drafts).

    python -m scripts.social_refresh                              # dry run: lists what would change
    python -m scripts.social_refresh --apply                      # rebuild drafts made with an older DESIGN_VERSION
    python -m scripts.social_refresh --apply --force --from 2026-10-28 --to 2026-10-31 --platform tiktok

Rows are updated IN PLACE (the unique platform + slot_date stays, no duplicates), go back to `draft`, and the old
text is written to the audit log. Nothing is approved or published. Back up first when running against production:
    create table dialogbot.social_posts_bak_<date> as select * from dialogbot.social_posts;
"""
from __future__ import annotations

import argparse
from datetime import date

from app.db import get_session_factory
from app.modules.social import service


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="make the change (default: dry run)")
    ap.add_argument("--force", action="store_true", help="also rows that are already in the current design")
    ap.add_argument("--from", dest="start", type=date.fromisoformat)
    ap.add_argument("--to", dest="end", type=date.fromisoformat)
    ap.add_argument("--platform", action="append", choices=["facebook", "instagram", "tiktok"])
    a = ap.parse_args(argv)
    days = (a.start or date.min, a.end or date.max) if (a.start or a.end) else None
    with get_session_factory()() as db:
        rows = service.refresh_stale_drafts(db, force=a.force, platforms=a.platform, days=days, dry_run=not a.apply)
    for r in rows:
        print(f"{r['slot_date']} {r['platform']:<9} {r['topic']:<24} v{r['from_version']} {r['old_status']:<9} → draft kl. {r['new_slot'][-5:]}")
    print(f"{len(rows)} opslag {'opdateret' if a.apply else 'ville blive opdateret (dry run, brug --apply)'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

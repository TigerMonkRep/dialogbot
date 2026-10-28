"""Deploy check: does the running API's database sit on the Alembic head of this checkout?

    python scripts/check_live_schema.py https://<api-host> [--wait-minutes 20]

Uses only the standard library (reads the revision files, calls /health/ready), so CI needs no install step.
Exit 0 when equal, 1 when not (after retrying – a rolling deploy takes minutes)."""
from __future__ import annotations

import json
import re
import sys
import time
import urllib.request
from pathlib import Path

VERSIONS = Path(__file__).resolve().parent.parent / "alembic" / "versions"


def code_head() -> str:
    revs, downs = set(), set()
    for f in VERSIONS.glob("*.py"):
        text = f.read_text()
        if m := re.search(r"^revision(?::\s*str)?\s*=\s*['\"]([0-9a-f]+)['\"]", text, re.M):
            revs.add(m.group(1))
        if m := re.search(r"^down_revision(?::[^=]*)?\s*=\s*['\"]([0-9a-f]+)['\"]", text, re.M):
            downs.add(m.group(1))
    heads = revs - downs
    if len(heads) != 1:
        sys.exit(f"expected exactly one Alembic head in the code, found: {sorted(heads)}")
    return heads.pop()


def live_head(base: str) -> str:
    try:
        with urllib.request.urlopen(base.rstrip("/") + "/health/ready", timeout=20) as r:  # noqa: S310
            body = json.load(r)
    except urllib.error.HTTPError as e:  # 503 while migrations are pending still carries the body
        body = json.load(e)
    except Exception as e:  # noqa: BLE001
        return f"unreachable ({type(e).__name__})"
    return str(body.get("migration", ""))


def main() -> int:
    base = sys.argv[1]
    minutes = int(sys.argv[sys.argv.index("--wait-minutes") + 1]) if "--wait-minutes" in sys.argv else 0
    expected = code_head()
    deadline = time.time() + minutes * 60
    while True:
        found = live_head(base)
        print(f"live database: {found}   code: {expected}", flush=True)
        if found == expected:
            print("OK: the live schema is at the head of this commit")
            return 0
        if time.time() >= deadline:
            print("::error::the live database is not at this commit's Alembic head – the pre-deploy migration did not "
                  "run or failed (check the Render deploy log and MIGRATION_DATABASE_URL)")
            return 1
        time.sleep(30)


if __name__ == "__main__":
    sys.exit(main())

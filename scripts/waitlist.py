"""Waitlist administration (run in the API service shell, e.g. Render → Shell).

    python -m scripts.waitlist export            # CSV to stdout
    python -m scripts.waitlist delete <e-mail>   # erase one person (GDPR request)

There is deliberately no web endpoint: the list is not tied to a workspace, and
no platform-admin role exists yet.
"""
from __future__ import annotations

import csv
import sys

from sqlalchemy import delete, select

from app.db import get_session_factory
from app.models import WaitlistSignup

FIELDS = ("email", "industry", "interests", "source", "consent_version", "created_at", "updated_at")


def export(out=sys.stdout) -> int:
    with get_session_factory()() as db:
        rows = db.scalars(select(WaitlistSignup).order_by(WaitlistSignup.created_at)).all()
        w = csv.writer(out)
        w.writerow(FIELDS)
        for r in rows:
            w.writerow([r.email, r.industry or "", " ".join(r.interests), r.source, r.consent_version,
                        r.created_at.isoformat(), r.updated_at.isoformat()])
    return len(rows)


def erase(email: str) -> int:
    with get_session_factory()() as db:
        n = db.execute(delete(WaitlistSignup).where(WaitlistSignup.email == email.strip().lower())).rowcount
        db.commit()
    return n


def main(argv: list[str]) -> int:
    if argv[:1] == ["export"]:
        n = export()
        print(f"{n} tilmeldinger", file=sys.stderr)
        return 0
    if len(argv) == 2 and argv[0] == "delete":
        n = erase(argv[1])
        print("slettet" if n else "ikke fundet", file=sys.stderr)
        return 0 if n else 1
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

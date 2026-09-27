"""Grant or revoke the platform-operator role (reviews voice rights, publishes platform voices).

Run in the API service shell (Render → Shell), never from a browser:

    python -m scripts.grant_operator grant  <e-mail>
    python -m scripts.grant_operator revoke <e-mail>
    python -m scripts.grant_operator list

Every change is written to the audit log.
"""
from __future__ import annotations

import sys

from sqlalchemy import select

from app.core.audit import record_audit
from app.db import get_session_factory
from app.models import User


def main(argv: list[str]) -> int:
    if len(argv) < 2 or argv[1] not in ("grant", "revoke", "list") or (argv[1] != "list" and len(argv) != 3):
        print(__doc__)
        return 2
    with get_session_factory()() as db:
        if argv[1] == "list":
            for u in db.scalars(select(User).where(User.is_platform_operator.is_(True))):
                print(u.email)
            return 0
        u = db.scalar(select(User).where(User.email_normalized == argv[2].strip().lower()))
        if u is None:
            print("Ingen bruger med den e-mail", file=sys.stderr)
            return 1
        u.is_platform_operator = argv[1] == "grant"
        record_audit(db, workspace_id=None, actor_user_id=None, action=f"operator.{argv[1]}", object_type="user",
                     object_id=u.id, after={"is_platform_operator": u.is_platform_operator, "via": "cli"})
        db.commit()
        print(f"{u.email}: is_platform_operator={u.is_platform_operator}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

"""Dialogbot Privat context and the return address (`next`) of account links (QA F-JP-01..05, F-JP-10).

One mechanism for every account mail and page (sign-up, verify, resend, forgot/reset, login):
- a person is in the Privat context when the sign-up said so (signup_intent "privat"), when the link they came from
  returns to a Privat route, or when the account is Privat only (a personal workspace or a Privat sign-up, and no
  business workspace);
- the return address travels IN the link (`&for=privat&next=…`), so it also works when the mail opens another
  browser – never only in localStorage;
- `next` is accepted only as a relative path under /privat, /g/ or /i/ (no open redirect, no way into Erhverv).
The web has the same rule in web/src/lib/privat-next.ts.
"""
from __future__ import annotations

import re
from urllib.parse import quote

from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from app.models import Membership, PrivateProfile, User, Workspace

PRIVAT_INTENT = "privat"  # a Dialogbot Privat sign-up: Privat mails and links (F-PK-04); never a product intent
PRIVAT_HOME = "/privat/dag"
ERHVERV_HOME = "/app"
MAX_NEXT = 512
# /privat (alone, or followed by / ? #), /g/<code>, /i/<code>; then only URL characters – no spaces, no backslash
_NEXT = re.compile(r"^/(?:privat(?=$|[/?#])|g/|i/)[A-Za-z0-9\-._~/?#\[\]@!$&'()*+,;=%:]*$")


def safe_next(value: object) -> str | None:
    """`value` when it is a safe Privat return address, else None (dropped quietly – a bad `next` never fails a
    sign-up). "//host", "/\\host", ".." and control characters are refused."""
    if not isinstance(value, str) or not value or len(value) > MAX_NEXT:
        return None
    if "//" in value or ".." in value or not _NEXT.match(value) or re.search(r"%(2e|2f|5c)", value, re.I):
        return None
    return value


def next_kind(next_: str | None) -> str:
    """What the person is on their way to (web: privatKind in web/src/lib/privat-next.ts):
    "trial" – the landing page or a plan: the verify mail may say «prøveperiode»;
    "list" – a shared list, wishlist or group (/privat/invitation/, /i/, /g/): a free account, no trial promised
    (F-JP-05); "other" – somewhere else in Privat: neutral words."""
    if next_ is None or next_ == "/privat" or next_.startswith(("/privat/konto", "/privat?")):
        return "trial"
    if next_.startswith(("/privat/invitation/", "/i/", "/g/")):
        return "list"
    return "other"


def has_business(db: OrmSession, user_id) -> bool:
    return db.scalar(select(Membership.id).join(Workspace, Workspace.id == Membership.workspace_id).where(
        Membership.user_id == user_id, Workspace.kind == "business", Workspace.status != "closed").limit(1)) is not None


def is_privat_user(db: OrmSession, user: User) -> bool:
    """Privat only: a personal workspace or a Privat sign-up, and no business workspace."""
    if has_business(db, user.id):
        return False
    if user.signup_intent == PRIVAT_INTENT:
        return True
    return db.scalar(select(PrivateProfile.workspace_id).where(PrivateProfile.user_id == user.id)) is not None


def home(db: OrmSession, user: User) -> str:
    """Where a login without `next` lands: /privat/dag for a Privat-only account – never /app → /opsaetning/1."""
    return PRIVAT_HOME if is_privat_user(db, user) else ERHVERV_HOME


def link_suffix(*, privat: bool, next_: str | None) -> str:
    """The query added to an account link: `&for=privat` and the URL-encoded `next`."""
    if not privat:
        return ""
    return "&for=privat" + (f"&next={quote(next_, safe='')}" if next_ else "")

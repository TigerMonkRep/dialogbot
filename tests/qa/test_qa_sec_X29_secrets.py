"""X29 (P0) - secrets: none in git-tracked files, none in the built web bundle (web/.next), none in logs/error output.

Findings are printed masked (first 6 chars + length) - a full key is never printed.
Run: source /home/claude/qa-env.sh && export TEST_DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/qa_sec \
     DATABASE_URL=$TEST_DATABASE_URL && pytest -p no:cacheprovider tests/qa/test_qa_sec_X29_secrets.py
"""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
PATTERNS = {
    "stripe_secret": r"\b(?:sk|rk)_(?:live|test)_[0-9A-Za-z]{10,}",
    "stripe_whsec": r"\bwhsec_[0-9A-Za-z]{16,}",
    "slack": r"\bxox[abprs]-[0-9A-Za-z-]{10,}",
    "aws_access_key": r"\bAKIA[0-9A-Z]{16}\b",
    "private_key": r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
    "jwt_signed": r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{16,}",
    "twilio_sid": r"\b(?:AC|SK)[0-9a-f]{32}\b",
    "resend": r"\bre_[A-Za-z0-9]{8,}_[A-Za-z0-9]{12,}",
    "anthropic": r"\bsk-ant-[A-Za-z0-9_-]{20,}",
    "openai": r"\bsk-(?:proj-)?[A-Za-z0-9]{32,}",
    "google_api": r"\bAIza[0-9A-Za-z_-]{35}\b",
    "elevenlabs": r"\bsk_[0-9a-f]{40,}\b",
    "github": r"\b(?:ghp_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{40,})",
    "db_url_with_password": r"postgres(?:ql)?(?:\+\w+)?://[^:/\s\"']+:[^@\s\"'$]{6,}@(?!localhost|127\.0\.0\.1|db:|postgres:)[^\s\"']+",
}
RX = {k: re.compile(v) for k, v in PATTERNS.items()}


def _mask(s: str) -> str:
    return f"{s[:6]}…({len(s)} tegn)"


def _scan(files) -> list[str]:
    hits = []
    for p in files:
        try:
            if os.path.getsize(p) > 30_000_000:
                continue
            data = Path(p).read_bytes().decode("utf-8", "ignore")
        except OSError:
            continue
        for name, rx in RX.items():
            for m in rx.finditer(data):
                hits.append(f"{name}: {os.path.relpath(p, ROOT)}:{data.count(chr(10), 0, m.start()) + 1} {_mask(m.group(0))}")
    return hits


def test_no_secrets_in_git_tracked_files():
    files = [ROOT / f for f in subprocess.check_output(["git", "ls-files"], cwd=ROOT, text=True).splitlines() if f]
    hits = _scan([f for f in files if f.is_file()])
    assert not hits, "secret-like values in tracked files:\n" + "\n".join(hits)
    tracked = subprocess.check_output(["git", "ls-files"], cwd=ROOT, text=True).splitlines()
    env_files = [f for f in tracked if re.search(r"(^|/)\.env(\.|$)", f) and not f.endswith(".example")]
    assert not env_files, f"tracked env files: {env_files}"


def test_no_secrets_in_web_build_output():
    nxt = ROOT / "web" / ".next"
    if not nxt.is_dir():
        pytest.skip("web/.next not built")
    files = [Path(d) / f for d, _, fs in os.walk(nxt) for f in fs]
    hits = _scan(files)
    assert not hits, "secret-like values in web/.next:\n" + "\n".join(hits)
    # server-only env values must never reach the client bundle (checked by value, printed by name only)
    leaked = []
    for name in ("PREVIEW_COOKIE_SECRET", "PREVIEW_ACCESS_CODES", "CREDENTIALS_KEY", "VAPI_SERVER_SECRET", "SEED_DEMO_PASSWORD",
                 "STRIPE_SECRET_KEY", "ANTHROPIC_API_KEY", "RESEND_API_KEY"):
        v = os.environ.get(name)
        if not v or len(v) < 8:
            continue
        for f in (nxt / "static").rglob("*"):
            if f.is_file() and v.encode() in f.read_bytes():
                leaked.append(f"{name} in {f.relative_to(ROOT)}")
    assert not leaked, leaked


def test_db_errors_do_not_write_password_hashes_or_pii_to_logs(app):
    """A database error's text (which uvicorn/Render log as the traceback) must not carry the bound parameters.
    Seen in /home/claude/api.log during this QA run: POST /auth/register with a too-long interface_language
    (RegisterIn has no max_length; users.interface_language is varchar(16)) -> 500, and the logged DataError held
    the argon2 password hash and the e-mail. Proven here both through the route and on the engine directly.

    The engine probe binds the secret as a parameter of a statement that fails for an unrelated reason (division by
    zero), so the only way the value can reach the error text is SQLAlchemy's "[parameters: …]" dump. A value that
    Postgres itself echoes in its own message is a separate question (see the xfail test below)."""
    import sqlalchemy as sa

    from app.db import get_engine

    c = TestClient(app, raise_server_exceptions=True)
    texts = []
    try:
        r = c.post("/api/v1/auth/register", json={"email": "qasec-logleak@testmail.dk", "password": "CorrectHorse!42",
                                                  "display_name": "QA", "interface_language": "x" * 40})
        assert r.status_code < 500, r.text
    except Exception as e:  # noqa: BLE001
        texts.append(("route", str(e)))
    try:
        with get_engine().connect() as conn:
            conn.execute(sa.text("select cast(:secret as text), 1 / 0"), {"secret": "QASEC-SECRET-PARAM-VALUE"})
    except Exception as e:  # noqa: BLE001
        texts.append(("engine", str(e)))
    leaks = [w for w, t in texts if "$argon2" in t or "qasec-logleak@testmail.dk" in t or "QASEC-SECRET-PARAM-VALUE" in t]
    assert not leaks, (f"exception text that ends in the server log carries bound parameters ({leaks}); "
                       "set hide_parameters=True on create_engine in app/db.py:26 and cap RegisterIn.interface_language")
    assert [w for w, _ in texts] == ["engine"], [w for w, _ in texts]  # probe must fail; the route must not 500


@pytest.mark.xfail(strict=True, reason="F-SQ-02-X29/F-VR-02-X29: needs-decision – Postgres echoes an offending value in "
                   "its own error message (e.g. invalid input syntax, unique-violation DETAIL); hide_parameters cannot "
                   "remove it and the worker logs f'{exc}' (app/worker/runner.py). Scrubbing server messages is a decision.")
def test_postgres_echoed_values_do_not_reach_exception_text(app):
    import sqlalchemy as sa

    from app.db import get_engine

    text = ""
    try:
        with get_engine().connect() as conn:
            conn.execute(sa.text("select cast(:secret as integer)"), {"secret": "QASEC-SECRET-PARAM-VALUE"})
    except Exception as e:  # noqa: BLE001
        text = str(e)
    assert text, "probe did not fail"
    assert "QASEC-SECRET-PARAM-VALUE" not in text, "Postgres' own error message echoes the bound value"

"""X20 (P0) - operator areas (admin, social dashboard, sales channel, support access M02 «se som kunde», audit M07)
are reachable only by a Dialogbot operator (users.is_platform_operator - granted by scripts/grant_operator.py, e.g.
rene@fyrster.dk). Covers the API for every operator route (enumerated from the app, so new ones are included
automatically), the escalation paths a normal user could try, and - when the local stack runs - the UI by direct URL.

Run: source /home/claude/qa-env.sh && export TEST_DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/qa_sec \
     DATABASE_URL=$TEST_DATABASE_URL && pytest -p no:cacheprovider tests/qa/test_qa_sec_X20.py
"""
from __future__ import annotations

import os
import re
import uuid
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from qa_sec_helpers import all_routes, body_for, dep_names, fill, path_params, request_schema

from app.db import get_session_factory
from app.main import create_app
from app.models import User
from app.worker import runner

EVIDENCE = Path(__file__).resolve().parents[2] / "qa" / "evidence" / "X20"
OPERATOR_EMAIL = "rene@fyrster.dk"
_APP = create_app()
_SPEC = _APP.openapi()
OPERATOR_DEPS = {"operator", "sales_admin", "research_gate", "simulation_gate"}
_ALL = all_routes(_APP)
# /dev/* is dev/test-only (its own test below proves it is not mounted in staging/prod), so it is not part of the matrix.
OPERATOR_ROUTES = [(m, p) for m, p, r in _ALL if ((dep_names(r) & OPERATOR_DEPS) or "/operator/" in p) and not p.startswith("/api/v1/dev/")]
ROUTE = {(m, p): r for m, p, r in _ALL}


def _ids(rs):
    return [f"{m} {p}" for m, p in rs]


def test_every_operator_path_has_an_operator_guard():
    """Static: any route under /operator/ resolves an operator dependency (a route that forgets it is caught here)."""
    missing = [f"{m} {p}" for m, p in OPERATOR_ROUTES if not (dep_names(ROUTE[(m, p)]) & OPERATOR_DEPS)]
    assert not missing, f"/operator routes without operator guard: {missing}"
    assert len(OPERATOR_ROUTES) > 100


@pytest.fixture
def cast(api, client, pv):
    """Every kind of normal user: owner/admin/staff/reader of a business workspace, an unverified user, a Privat
    user, a read-only «se som kunde» session - and one real operator (rene@fyrster.dk) as positive control."""
    owner = api.user("qasec-x20-owner@testmail.dk")
    ws = api.workspace(owner, "QASEC X20 ApS")
    toks = {"owner": owner}
    for role in ("admin", "staff", "reader"):
        toks[role] = api.add_member(owner, ws, f"qasec-x20-{role}@testmail.dk", role)
    api.register("qasec-x20-unverified@testmail.dk")
    toks["unverified"] = api.login("qasec-x20-unverified@testmail.dk")
    toks["privat"] = pv.account("qasec-x20-privat@testmail.dk")
    op = api.user(OPERATOR_EMAIL)
    with get_session_factory()() as db:
        db.query(User).filter_by(email_normalized=OPERATOR_EMAIL).one().is_platform_operator = True
        db.commit()
        owner_id = db.query(User).filter_by(email_normalized="qasec-x20-owner@testmail.dk").one().id
    r = api.post(op, "/operator/admin/view-as", {"user_id": str(owner_id), "workspace_id": ws})
    assert r.status_code == 200, r.text
    toks["view_as_customer"] = r.json()["token"]
    return {"toks": toks, "op": op, "ws": ws, "owner_id": str(owner_id)}


def _probe(client, method, path, token, ws):
    vals = {p: (ws if p in ("workspace_id", "ws_id") else str(uuid.uuid4())) for p in path_params(path)}
    body = body_for(_SPEC, request_schema(_SPEC, method, path), str(uuid.uuid4()), ws) if method in ("POST", "PUT", "PATCH") else None
    h = {"Idempotency-Key": uuid.uuid4().hex}
    if token:
        h["Authorization"] = f"Bearer {token}"
    return client.request(method, fill(path, vals), json=body, headers=h)


def test_operator_routes_refuse_every_non_operator(app, cast):
    c = TestClient(app, raise_server_exceptions=False)
    bad, rows = [], []
    for m, p in OPERATOR_ROUTES:
        for who, tok in [("anonymous", None), *cast["toks"].items()]:
            r = _probe(c, m, p, tok, cast["ws"])
            rows.append(f"{who:17} {r.status_code} {m} {p}")
            if r.status_code not in (401, 403, 404):
                bad.append(f"{who}: {m} {p} -> {r.status_code} {r.text[:160]}")
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / "operator-route-matrix.txt").write_text("\n".join(rows))
    assert not bad, "non-operators reached operator routes:\n" + "\n".join(bad)


def test_operator_positive_control(app, cast):
    """The operator is let through (no 401/403 operator_only) on the read routes of each operator area."""
    c = TestClient(app, raise_server_exceptions=False)
    for path in ("/api/v1/operator/admin/overview", "/api/v1/operator/admin/customers", "/api/v1/operator/admin/users",
                 "/api/v1/operator/social/dashboard", "/api/v1/operator/voices", "/api/v1/operator/telephony"):
        r = c.get(path, headers={"Authorization": f"Bearer {cast['op']}"})
        assert r.status_code == 200, (path, r.status_code, r.text[:200])


def test_operator_flag_cannot_be_self_assigned(api, client):
    """Mass assignment: the flag is ignored on register and on PATCH /auth/me."""
    r = client.post("/api/v1/auth/register", json={"email": "qasec-x20-mass@testmail.dk", "password": "CorrectHorse!42",
                                                   "display_name": "M", "is_platform_operator": True})
    assert r.status_code == 201 and r.json()["is_platform_operator"] is False
    tok = api.login("qasec-x20-mass@testmail.dk")
    r = api.patch(tok, "/auth/me", {"is_platform_operator": True, "email": OPERATOR_EMAIL, "display_name": "M2"})
    assert r.status_code == 200 and r.json()["is_platform_operator"] is False and r.json()["email"] != OPERATOR_EMAIL


def test_operator_email_lookalikes_do_not_inherit_the_role(api, client):
    """The role is a flag on one user row, never derived from the e-mail: case variants of the operator's address
    are the same account (409/same user), and look-alike addresses are plain users."""
    api.user(OPERATOR_EMAIL)
    with get_session_factory()() as db:
        db.query(User).filter_by(email_normalized=OPERATOR_EMAIL).one().is_platform_operator = True
        db.commit()
    for variant in ("RENE@FYRSTER.DK", "Rene@Fyrster.dk", " rene@fyrster.dk"):
        r = client.post("/api/v1/auth/register", json={"email": variant, "password": "CorrectHorse!42", "display_name": "X"})
        assert r.status_code in (409, 422, 400, 201), r.text
        if r.status_code == 201:  # anti-enumeration answer: must not have created a second account
            with get_session_factory()() as db:
                assert db.query(User).filter(User.email_normalized == OPERATOR_EMAIL).count() == 1
    for lookalike in ("rene@fyrster.dk.evil.example", "rene+op@fyrster.dk", "rené@fyrster.dk"):
        r = client.post("/api/v1/auth/register", json={"email": lookalike, "password": "CorrectHorse!42", "display_name": "X"})
        if r.status_code == 201:
            assert r.json()["is_platform_operator"] is False
            tok = api.login(lookalike)
            assert api.get(tok, "/operator/admin/overview").status_code == 403


def test_view_as_cannot_target_an_operator_or_be_nested(api, cast):
    api.user("qasec-x20-op2@testmail.dk")
    with get_session_factory()() as db:
        u = db.query(User).filter_by(email_normalized="qasec-x20-op2@testmail.dk").one()
        u.is_platform_operator = True
        db.commit()
        uid = str(u.id)
    assert api.post(cast["op"], "/operator/admin/view-as", {"user_id": uid}).status_code == 422
    # the read-only customer session cannot write and cannot start another view
    va = cast["toks"]["view_as_customer"]
    assert api.post(va, "/operator/admin/view-as", {"user_id": cast["owner_id"]}).status_code == 403
    assert api.put(va, f"/workspaces/{cast['ws']}/profile", {"expected_version": 1, "legal_name": "x"}).status_code == 403
    assert api.get(va, "/privat/me").status_code in (403, 404)


def test_dev_operator_self_grant_is_not_mounted_outside_dev(monkeypatch):
    """POST /dev/operator/self makes ANY logged-in user an operator. It must only exist in dev/test."""
    from app.config import Settings, get_settings

    monkeypatch.setenv("APP_ENV", "prod")
    monkeypatch.setenv("ENABLE_DEV_TOOLS", "true")
    monkeypatch.setenv("SECRET_KEY", "x" * 40)
    with pytest.raises(ValueError):  # pydantic ValidationError
        Settings()
    monkeypatch.setenv("ENABLE_DEV_TOOLS", "false")
    monkeypatch.setenv("APP_ENV", "test")
    get_settings.cache_clear()
    paths = {p for _, p, _ in all_routes(create_app())}
    get_settings.cache_clear()
    assert "/api/v1/dev/operator/self" not in paths and "/api/v1/dev/mailbox" not in paths
    render = (Path(__file__).resolve().parents[2] / "infra" / "render.yaml").read_text()
    assert re.findall(r"ENABLE_DEV_TOOLS\s*\n\s*value:\s*\"?(\w+)", render) and all(
        v == "false" for v in re.findall(r"ENABLE_DEV_TOOLS\s*\n\s*value:\s*\"?(\w+)", render))


def test_dev_mailbox_wildcard_email_reads_operator_mail_and_takes_over(api, client):
    """Where dev tools are on (local, CI, the QA API behind Vercel previews), GET /dev/mailbox matches mail with
    `to_email ILIKE <caller's e-mail>`. '_' and '%' are legal in an e-mail's local part, so a user registered as
    `ren_@fyrster.dk` (or `%@fyrster.dk`) reads rene@fyrster.dk's mail - incl. a password-reset link - and becomes
    the operator. Expected: the mailbox only returns mail addressed exactly to the caller (app/modules/devtools/router.py:23)."""
    api.user(OPERATOR_EMAIL)
    with get_session_factory()() as db:
        db.query(User).filter_by(email_normalized=OPERATOR_EMAIL).one().is_platform_operator = True
        db.commit()
    attacker = api.user("ren_@fyrster.dk")
    assert client.post("/api/v1/auth/password/forgot", json={"email": OPERATOR_EMAIL}).status_code == 202
    runner.drain()
    items = api.get(attacker, "/dev/mailbox").json()["items"]
    foreign = [m for m in items if m["to"].lower() != "ren_@fyrster.dk"]
    took_over = False
    for m in foreign:
        hit = re.search(r"password/reset\?token=([A-Za-z0-9_\-]+)", m["body_text"])
        if hit and client.post("/api/v1/auth/password/reset",
                               json={"token": hit.group(1), "password": "Attacker-Owned-2026"}).status_code == 200:
            tok = api.login(OPERATOR_EMAIL, "Attacker-Owned-2026")
            took_over = api.get(tok, "/operator/admin/overview").status_code == 200
    if foreign:  # pytest.fail, not assert: the mails hold tokens and must not be echoed by assertion rewriting
        pytest.fail(f"ren_@fyrster.dk read {len(foreign)} mail(s) addressed to {OPERATOR_EMAIL} "
                    f"(subjects: {sorted({m['subject'] for m in foreign})})"
                    f"{' and took over the operator account' if took_over else ''}")


# --------------------------------------------------------------------------- UI (live local stack, read-only use)
WEB = os.environ.get("BASE_URL", "http://localhost:3000")
API = os.environ.get("API_BASE_URL", "http://localhost:8000")
_OPDIR = Path(__file__).resolve().parents[2] / "web/src/app/app/(admin)/operator"
UI_PAGES = sorted("/app/operator" + ("" if p.parent == _OPDIR else "/" + str(p.parent.relative_to(_OPDIR)))
                  for p in _OPDIR.rglob("page.tsx"))
OPERATOR_DATA = re.compile(r"Kræver opmærksomhed|Se som|Miljø:|Følgere|Ventende opslag|Stemmerettigheder|privat-leads", re.I)


def _live() -> bool:
    try:
        return httpx.get(f"{API}/health/live", timeout=2).status_code == 200 and httpx.get(WEB, timeout=5).status_code < 500
    except httpx.HTTPError:
        return False


def _stack_user(c: httpx.Client, email: str) -> str:
    pw = "Qa-Sec-X20-Password-2026"
    assert c.post(f"{API}/api/v1/auth/register", json={"email": email, "password": pw, "display_name": "QA X20"}).status_code == 201
    tok = c.post(f"{API}/api/v1/auth/login", json={"email": email, "password": pw}).json()["access_token"]
    h = {"Authorization": f"Bearer {tok}"}
    for _ in range(30):
        mails = c.get(f"{API}/api/v1/dev/mailbox", headers=h).json()["items"]
        m = next((re.search(r"verify-email\?token=([\w-]+)", x["body_text"]) for x in mails if x["to"] == email), None)
        if m:
            assert c.post(f"{API}/api/v1/auth/verify-email", json={"token": m.group(1)}).status_code == 200
            return tok
        import time
        time.sleep(1)
    raise AssertionError("no verification mail")


@pytest.mark.skipif(not _live(), reason="local stack (API :8000, web :3000) not running")
def test_ui_operator_pages_by_direct_url_show_no_operator_data():
    """Owner/admin/staff/reader of a fresh workspace open every /app/operator/** page by direct URL: they get the
    «kun for Dialogbot-operatører» notice (or a redirect), never operator data. Uses unique users; writes nothing
    but its own users/workspace on the shared stack."""
    tag = uuid.uuid4().hex[:8]
    out, bad = [], []
    with httpx.Client(timeout=30) as c:
        owner = _stack_user(c, f"qasec-x20-ui-owner-{tag}@example.com")
        ws = c.post(f"{API}/api/v1/workspaces", json={"name": f"QASEC X20 UI {tag}"}, headers={"Authorization": f"Bearer {owner}"}).json()["id"]
        users = {"owner": owner}
        for role in ("admin", "staff", "reader"):
            email = f"qasec-x20-ui-{role}-{tag}@example.com"
            assert c.post(f"{API}/api/v1/workspaces/{ws}/invitations", json={"email": email, "role": role},
                          headers={"Authorization": f"Bearer {owner}"}).status_code == 201
            t = _stack_user(c, email)
            for _ in range(30):
                mails = c.get(f"{API}/api/v1/dev/mailbox", headers={"Authorization": f"Bearer {t}"}).json()["items"]
                m = next((re.search(r"invite/([\w-]+)", x["body_text"]) for x in mails if "inviteret" in x["subject"]), None)
                if m:
                    break
                import time
                time.sleep(1)
            assert c.post(f"{API}/api/v1/invitations/accept", json={"token": m.group(1)}, headers={"Authorization": f"Bearer {t}"}).status_code == 200
            users[role] = t
        users["no_workspace_user"] = _stack_user(c, f"qasec-x20-ui-solo-{tag}@example.com")
        for who, tok in users.items():
            cookies = {"db_session": tok, "db_ws": ws if who != "no_workspace_user" else "", "db_setup_later": "1"}
            for page in UI_PAGES:
                url = WEB + re.sub(r"\[[a-z_]+\]", str(uuid.uuid4()), page)
                r = c.get(url, cookies=cookies, follow_redirects=False)
                note = "kun for Dialogbot-operatører" in r.text or "du er ikke operatør" in r.text
                out.append(f"{who:18} {r.status_code} notice={note} {page}")
                if r.status_code == 200 and (OPERATOR_DATA.search(r.text.split("</header>")[-1]) and not note):
                    bad.append(f"{who} {page}: operator content without notice")
                if r.status_code == 200 and not note and r.status_code not in (301, 302, 303, 307, 308, 404):
                    bad.append(f"{who} {page}: 200 without the operator-only notice")
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / "ui-direct-url-matrix.txt").write_text("\n".join(out))
    assert not bad, "\n".join(bad)


@pytest.mark.xfail(strict=True, reason="F-SQ-03-X20/M07 operator audit with access reasons: not-implemented")
def test_m07_operator_audit_and_view_as_access_reason_exist():
    """M07: «Operator actions, access reasons and filtered audit history» (/admin/audit). M02: «scoped support
    context». Not built: no operator audit route and POST /operator/admin/view-as takes no reason (xfail strict –
    turns red when built)."""
    audit = [p for m, p, _r in _ALL if m == "GET" and "/operator/" in p and "audit" in p]
    assert audit, "no operator audit route"
    from app.modules.admin.router import ViewAsIn

    props = set(ViewAsIn.model_fields)
    assert props & {"reason", "access_reason", "begrundelse"}, f"view-as takes no access reason: {sorted(props)}"

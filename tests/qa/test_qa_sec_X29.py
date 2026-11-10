"""X29 (P0) - tenant isolation: a systematic IDOR sweep over EVERY route the API serves.

How it works (and why it keeps covering new routes on its own):
- Routes are enumerated from the app itself (`qa_sec_helpers.all_routes`) at collection time, so a route added
  tomorrow becomes a new parametrised case without anyone touching this file.
- Four tenants are built once for the module: business workspaces A and B (two owners) and two Dialogbot Privat
  users P1 and P2. `RowFactory` inserts one row in EVERY workspace-scoped table for each tenant, with a marker
  string (QASEC-AAA… / QASEC-P1…) in its text columns. So B has a real object id of every kind that A owns.
- B then calls every route with A's ids in the path, in the query and in the body (all uuid fields), P2 does the
  same with P1's ids against /privat, and B's public-API key is aimed at A. A response that contains A's marker
  (or one of A's ids that B did not send) is a cross-tenant read. At the end every row A/P1 owns is compared to a
  snapshot taken before the sweep: any change is a cross-tenant write or delete.

Run: source /home/claude/qa-env.sh && export TEST_DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/qa_sec \
     DATABASE_URL=$TEST_DATABASE_URL && pytest -p no:cacheprovider tests/qa/test_qa_sec_X29.py
"""
from __future__ import annotations

import json
import socket
import uuid
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from qa_sec_helpers import RowFactory, all_routes, body_for, dep_names, fill, path_params, request_schema, snapshot
from sqlalchemy import text

from app.db import Base, get_engine, get_session_factory
from app.main import create_app
from app.models import PrivateProfile, User
from tests.conftest import Api
from tests.privat_fixtures import Clock, Pv

EVIDENCE = Path(__file__).resolve().parents[2] / "qa" / "evidence" / "X29"
MARK = {"A": "QASEC-AAA", "B": "QASEC-BBB", "P1": "QASEC-P1P1", "P2": "QASEC-P2P2"}
OK_DENIED = {401, 403, 404}

# ----------------------------------------------------------------------------------------- route classification
_APP = create_app()
_ROUTES = all_routes(_APP)
WS_PREFIX = "/api/v1/workspaces/{workspace_id}"
# The one dev route that changes who the caller is (grants operator). Never part of a tenant sweep.
EXCLUDE = {("POST", "/api/v1/dev/operator/self")}
# /privat routes that are deliberately not bound to the caller's private context: a token/code IS the credential.
PRIVAT_TOKEN_ROUTES = {
    "/api/v1/privat/account", "/api/v1/privat/invites/by-code/{code}/accept", "/api/v1/privat/invites/{token}/accept",
    "/api/v1/privat/invites/by-code/{code}", "/api/v1/privat/invites/{token}", "/api/v1/privat/group-invites/by-code/{code}",
    "/api/v1/privat/group-invites/by-code/{code}/join", "/api/v1/privat/calendar/feed/{token}.ics", "/api/v1/privat/dev-files",
}
OPERATOR_DEPS = {"operator", "sales_admin", "research_gate", "simulation_gate"}


def _cls(method, path, route):
    deps = dep_names(route)
    if (method, path) in EXCLUDE:
        return "excluded"
    if path.startswith(WS_PREFIX) or path == "/api/v1/workspaces":
        return "workspace"
    if path.startswith("/v1/"):
        return "public_api"
    if deps & OPERATOR_DEPS:
        return "operator"  # covered by test_qa_sec_X20.py
    if "private_ctx" in deps:
        return "privat"
    if "get_current_principal" in deps or "optional_principal" in deps:
        return "user"
    return "anonymous"


CLASSES = {(m, p): _cls(m, p, r) for m, p, r in _ROUTES}
WS_ROUTES = [(m, p) for m, p, _ in _ROUTES if CLASSES[(m, p)] == "workspace" and p != "/api/v1/workspaces"]
PRIVAT_ROUTES = [(m, p) for m, p, _ in _ROUTES if CLASSES[(m, p)] == "privat"]
USER_ROUTES = [(m, p) for m, p, _ in _ROUTES if CLASSES[(m, p)] in ("user", "anonymous") and path_params(p)]
V1_ROUTES = [(m, p) for m, p, _ in _ROUTES if CLASSES[(m, p)] == "public_api" and "{workspace_id}" in p]
ROUTE_OBJ = {(m, p): r for m, p, r in _ROUTES}
_SPEC = _APP.openapi()


def _ids(routes):
    return [f"{m} {p}" for m, p in routes]


# ----------------------------------------------------------------------------------------- the world
@pytest.fixture(autouse=True)
def _fresh_public_api_limiter():
    from app.modules.public_api import ratelimit

    ratelimit.LIMITER = ratelimit.TokenBucketLimiter(read_per_minute=100000, write_per_minute=100000)
    yield
    ratelimit.LIMITER = None


@pytest.fixture(autouse=True)
def clean_tables():
    """Overrides the per-test TRUNCATE in tests/conftest.py: the world is built once per module (see `world`)."""
    yield


def _truncate():
    tables = [t.name for t in reversed(Base.metadata.sorted_tables)]
    with get_engine().begin() as conn:
        conn.execute(text("TRUNCATE " + ", ".join(tables) + " RESTART IDENTITY CASCADE"))


_REAL_CONNECT = socket.socket.connect


def _local_only(self, address):
    host = address[0] if isinstance(address, tuple) else address
    if isinstance(host, str) and host not in ("127.0.0.1", "::1", "localhost") and not host.startswith("/"):
        raise ConnectionRefusedError(f"QA sweep: outbound network blocked ({host})")
    return _REAL_CONNECT(self, address)


@pytest.fixture(scope="module")
def world(app):
    from app.config import get_settings

    mp = pytest.MonkeyPatch()
    for k, v in {"AI_PROVIDER": "fake", "TTS_ENGINE": "fake", "TELEPHONY_PROVIDER": "fake", "CONNECTORS_PROVIDER": "fake",
                 "SOCIAL_PROVIDER": "fake", "EMAIL_ADAPTER": "simulated", "PRIVAT_ENABLED": "true",
                 "PRIVAT_ALLOWED_EMAILS": "", "VAPI_SERVER_SECRET": "qa-sec-vapi-secret", "VAPI_API_KEY": "qa-sec-fake",
                 "PRIVAT_POOL_NUMBERS": "+4589870000=pn_pool"}.items():
        mp.setenv(k, v)
    mp.setattr(socket.socket, "connect", _local_only)  # belt and braces: no request may leave the machine
    get_settings.cache_clear()
    _truncate()
    client = TestClient(app, raise_server_exceptions=False)
    api = Api(client)
    tok_a = api.user("qasec-owner-a@testmail.dk")
    ws_a = api.workspace(tok_a, f"{MARK['A']} Fjord Gulvservice")
    tok_b = api.user("qasec-owner-b@testmail.dk")
    ws_b = api.workspace(tok_b, f"{MARK['B']} Havnebord")
    pv = Pv(api, Clock(datetime.now(UTC)))
    tok_p1 = pv.account("qasec-privat-1@testmail.dk", name=f"{MARK['P1']} Mette")
    tok_p2 = pv.account("qasec-privat-2@testmail.dk", name=f"{MARK['P2']} Lars")
    # real-flow objects too (not only generic rows)
    from app.modules.privat import addons

    with get_session_factory()() as db:  # every add-on on for both Privat users, so add-on gates don't hide the lookup
        for tok in (tok_p1, tok_p2):
            ws_p = pv.ws(tok)
            for key in list(addons.CATALOG):
                try:
                    with db.begin_nested():
                        addons.enable(db, ws_p, key)
                except Exception:  # noqa: BLE001 - coming soon / not in plan
                    pass
        db.commit()
    ka = api.knowledge(tok_a, ws_a, "service", f"{MARK['A']} hemmelig ydelse", {"unit": "m2", "description": MARK["A"]})
    kb = api.knowledge(tok_b, ws_b, "service", f"{MARK['B']} ydelse", {"unit": "m2"})
    from app.modules.public_api import scopes

    key_a = api.post(tok_a, f"/workspaces/{ws_a}/api-keys", {"name": f"{MARK['A']} CRM", "scopes": list(scopes.BUSINESS_SCOPES)})
    key_b = api.post(tok_b, f"/workspaces/{ws_b}/api-keys", {"name": f"{MARK['B']} CRM", "scopes": list(scopes.BUSINESS_SCOPES)})
    assert key_a.status_code == 201 and key_b.status_code == 201, (key_a.text, key_b.text)

    with get_session_factory()() as db:
        uid = {e: db.query(User).filter_by(email_normalized=e).one().id for e in (
            "qasec-owner-a@testmail.dk", "qasec-owner-b@testmail.dk", "qasec-privat-1@testmail.dk", "qasec-privat-2@testmail.dk")}
        ws_p1 = db.query(PrivateProfile).filter_by(user_id=uid["qasec-privat-1@testmail.dk"]).one().workspace_id
        ws_p2 = db.query(PrivateProfile).filter_by(user_id=uid["qasec-privat-2@testmail.dk"]).one().workspace_id
        fa = RowFactory(db, uuid.UUID(ws_a), uid["qasec-owner-a@testmail.dk"], MARK["A"]).make_all()
        fb = RowFactory(db, uuid.UUID(ws_b), uid["qasec-owner-b@testmail.dk"], MARK["B"]).make_all()
        f1 = RowFactory(db, ws_p1, uid["qasec-privat-1@testmail.dk"], MARK["P1"]).make_all()
        f2 = RowFactory(db, ws_p2, uid["qasec-privat-2@testmail.dk"], MARK["P2"]).make_all()
        ids_a = {**fa.object_ids(), "knowledge_items(api)": ka["item"]["id"] if "item" in ka else ka.get("id"),
                 "api_keys(api)": key_a.json()["id"]}
        ids_b = {**fb.object_ids(), "knowledge_items(api)": kb["item"]["id"] if "item" in kb else kb.get("id")}
        snap_before = {"A": snapshot(db, uuid.UUID(ws_a)), "P1": snapshot(db, ws_p1)}
    w = dict(api=api, c=client, tok_a=tok_a, tok_b=tok_b, tok_p1=tok_p1, tok_p2=tok_p2, ws_a=ws_a, ws_b=ws_b,
             ws_p1=str(ws_p1), ws_p2=str(ws_p2), ids_a={k: v for k, v in ids_a.items() if v},
             ids_b={k: v for k, v in ids_b.items() if v}, ids_p1=f1.object_ids(), ids_p2=f2.object_ids(),
             key_a=key_a.json()["key"], key_b=key_b.json()["key"], snap=snap_before, results=defaultdict(list),
             factory_errors={"A": fa.errors, "P1": f1.errors})
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / "factory-coverage.json").write_text(json.dumps(
        {"rows_made_A": sorted(fa.ids), "rows_made_P1": sorted(f1.ids), "not_made_A": fa.errors, "not_made_P1": f1.errors},
        indent=1, ensure_ascii=False))
    yield w
    (EVIDENCE / "sweep-results.json").write_text(json.dumps(w["results"], indent=1, ensure_ascii=False, default=str))
    mp.undo()
    get_settings.cache_clear()
    _truncate()


# ----------------------------------------------------------------------------------------- probing
def _foreign_values(ids: dict[str, str]) -> list[str]:
    return list(dict.fromkeys(ids.values()))


def _call(w, method, path, token, *, foreign_id, foreign_ws, path_values, headers=None):
    url = fill(path, path_values)
    q = {}
    op = (_SPEC.get("paths", {}).get(path) or {}).get(method.lower()) or {}
    for prm in op.get("parameters", []):
        if prm.get("in") != "query":
            continue
        n = prm["name"]
        if n == "workspace_id":
            q[n] = foreign_ws
        elif n.endswith("_id") or n.endswith("_ids"):
            q[n] = foreign_id
        elif prm.get("required"):
            q[n] = body_for(_SPEC, prm.get("schema"), foreign_id, foreign_ws)
    body = body_for(_SPEC, request_schema(_SPEC, method, path), foreign_id, foreign_ws) if method in ("POST", "PUT", "PATCH") else None
    h = {"Authorization": f"Bearer {token}", "Idempotency-Key": uuid.uuid4().hex, "x-requested-with": "dialogbot", **(headers or {})}
    return w["c"].request(method, url, params=q, json=body, headers=h)


def _leak(resp_text: str, marker: str, other_ids: set[str], sent: set[str]) -> str | None:
    if marker in resp_text:
        return f"marker {marker}"
    for i in other_ids - sent:
        if i in resp_text:
            return f"foreign id {i}"
    return None


def _record(w, key, method, path, status, leak, sent, resp=None):
    row = {"route": f"{method} {path}", "status": status, "leak": leak, "sent": sent}
    if resp is not None and status in (422, 500):
        row["detail"] = resp.text[:200]
    w["results"][key].append(row)


def _object_params(path):
    return [p for p in path_params(path) if p not in ("workspace_id",)]


def _own_value(own_ids: dict[str, str], param: str) -> str:
    """Best guess at the caller's OWN object for a sibling path param (so nested routes reach the child lookup)."""
    stem = param.removesuffix("_id")
    for t, i in own_ids.items():
        if t.rstrip("s").endswith(stem) or t.startswith(stem):
            return i
    return str(uuid.uuid4())


# ----------------------------------------------------------------------------------------- tests
def test_route_inventory_and_static_guards():
    """Every /workspaces/{workspace_id}/** route resolves membership (get_workspace_context); every /privat route
    is bound to the caller's own private context unless it is a token route on the reviewed allow-list."""
    unguarded = [f"{m} {p}" for m, p in WS_ROUTES if "get_workspace_context" not in dep_names(ROUTE_OBJ[(m, p)])]
    privat_unbound = sorted({p for m, p, _ in _ROUTES if p.startswith("/api/v1/privat") and CLASSES[(m, p)] != "privat"
                             and CLASSES[(m, p)] != "operator"} - PRIVAT_TOKEN_ROUTES)
    counts = defaultdict(int)
    for v in CLASSES.values():
        counts[v] += 1
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / "route-inventory.json").write_text(json.dumps(
        {"counts": counts, "routes": [{"route": f"{m} {p}", "class": CLASSES[(m, p)]} for m, p, _ in _ROUTES]},
        indent=1, ensure_ascii=False))
    assert not unguarded, f"workspace routes without membership check: {unguarded}"
    assert not privat_unbound, f"/privat routes not bound to private_ctx and not reviewed: {privat_unbound}"
    assert len(WS_ROUTES) > 100 and len(PRIVAT_ROUTES) > 50, "route discovery broke"


def test_factory_covered_every_table(world):
    """Coverage of the generic object factory (informational; tables it cannot build are listed in evidence)."""
    made = len(world["ids_a"])
    assert made >= 40, f"factory made too few A objects ({made}); errors: {world['factory_errors']['A']}"


@pytest.mark.parametrize("method,path", WS_ROUTES, ids=_ids(WS_ROUTES))
def test_ws_swap_other_tenant_workspace_is_404(world, method, path):
    """B (owner of B) – and Privat users – call A's workspace id: never anything but 401/403/404, never A's data."""
    w = world
    sent = {w["ws_a"]}
    for who, tok, target in (("B->A", w["tok_b"], w["ws_a"]), ("P2->A", w["tok_p2"], w["ws_a"]),
                             ("P1->own personal ws", w["tok_p1"], w["ws_p1"])):
        a_id = next(iter(w["ids_a"].values()))
        vals = {"workspace_id": target, **{p: a_id for p in _object_params(path)}}
        r = _call(w, method, path, tok, foreign_id=a_id, foreign_ws=target, path_values=vals)
        leak = _leak(r.text, MARK["A"] if target == w["ws_a"] else MARK["P1"], set(w["ids_a"].values()), sent | {a_id})
        _record(w, "ws_swap", method, path, r.status_code, leak, who)
        assert leak is None, f"{who}: {method} {path} -> {r.status_code} leaked {leak}: {r.text[:300]}"
        assert r.status_code in OK_DENIED, f"{who}: {method} {path} -> {r.status_code} (expected 404): {r.text[:300]}"


@pytest.mark.parametrize("method,path", WS_ROUTES, ids=_ids(WS_ROUTES))
def test_object_swap_in_own_workspace(world, method, path):
    """B, in its OWN workspace, sends every one of A's object ids in path / query / body. Must never see A's data.
    (Writes are proven harmless by test_zz_victims_untouched.)"""
    w = world
    params = _object_params(path)
    foreign = _foreign_values(w["ids_a"])
    probes = foreign if (params or method != "GET") else [foreign[0]]
    for fid in probes:
        variants = [{p: fid for p in params}] if params else [{}]
        if len(params) > 1:  # nested: own parent + foreign child, and foreign parent + own child
            for i, _p in enumerate(params):
                variants.append({q: (fid if j == i else _own_value(w["ids_b"], q)) for j, q in enumerate(params)})
        for v in variants:
            r = _call(w, method, path, w["tok_b"], foreign_id=fid, foreign_ws=w["ws_a"],
                      path_values={"workspace_id": w["ws_b"], **v})
            leak = _leak(r.text, MARK["A"], set(w["ids_a"].values()), {fid, w["ws_a"]})
            _record(w, "object_swap", method, path, r.status_code, leak, fid, r)
            assert leak is None, f"B got A's data: {method} {fill(path, v)} id={fid} -> {r.status_code} {leak}: {r.text[:400]}"


@pytest.mark.parametrize("method,path", PRIVAT_ROUTES, ids=_ids(PRIVAT_ROUTES))
def test_privat_object_swap(world, method, path):
    """P2 sends every one of P1's object ids (path/query/body) to every /privat route."""
    w = world
    params = _object_params(path)
    foreign = _foreign_values(w["ids_p1"])
    probes = foreign if (params or method != "GET") else [foreign[0]]
    for fid in probes:
        r = _call(w, method, path, w["tok_p2"], foreign_id=fid, foreign_ws=w["ws_p1"],
                  path_values={p: fid for p in params})
        leak = _leak(r.text, MARK["P1"], set(w["ids_p1"].values()), {fid, w["ws_p1"]})
        _record(w, "privat_swap", method, path, r.status_code, leak, fid, r)
        assert leak is None, f"P2 got P1's data: {method} {path} id={fid} -> {r.status_code} {leak}: {r.text[:400]}"


@pytest.mark.parametrize("method,path", USER_ROUTES, ids=_ids(USER_ROUTES))
def test_other_id_routes_with_foreign_ids(world, method, path):
    """Non-workspace routes that take an id/token in the path (ambassador, funnel drafts, invitations, push,
    public webchat…): B with A's ids, P2 with P1's ids."""
    w = world
    params = _object_params(path)
    for tok, ids, mark, ws in ((w["tok_b"], w["ids_a"], MARK["A"], w["ws_a"]), (w["tok_p2"], w["ids_p1"], MARK["P1"], w["ws_p1"])):
        for fid in _foreign_values(ids):
            r = _call(w, method, path, tok, foreign_id=fid, foreign_ws=ws, path_values={p: fid for p in params})
            leak = _leak(r.text, mark, set(ids.values()), {fid, ws})
            _record(w, "user_routes", method, path, r.status_code, leak, fid)
            assert leak is None, f"{method} {path} id={fid} -> {r.status_code} leaked {leak}: {r.text[:400]}"


@pytest.mark.parametrize("method,path", V1_ROUTES, ids=_ids(V1_ROUTES))
def test_public_api_key_of_b_cannot_reach_a(world, method, path):
    """Public API v1: B's key against A's workspace -> 404; B's key on B's workspace with A's object ids -> never A's data."""
    w = world
    params = _object_params(path)
    for fid in _foreign_values(w["ids_a"]):
        vals = {p: fid for p in params}
        r = _call(w, method, path, w["key_b"], foreign_id=fid, foreign_ws=w["ws_a"], path_values={"workspace_id": w["ws_a"], **vals})
        _record(w, "v1_ws_swap", method, path, r.status_code, None, fid)
        assert r.status_code in OK_DENIED and MARK["A"] not in r.text, f"key B -> A: {method} {path} {r.status_code} {r.text[:300]}"
        if not params and method == "GET":
            break
    for fid in _foreign_values(w["ids_a"]):
        r = _call(w, method, path, w["key_b"], foreign_id=fid, foreign_ws=w["ws_a"],
                  path_values={"workspace_id": w["ws_b"], **{p: fid for p in params}})
        leak = _leak(r.text, MARK["A"], set(w["ids_a"].values()), {fid, w["ws_a"]})
        _record(w, "v1_object_swap", method, path, r.status_code, leak, fid)
        assert leak is None, f"key B got A's data: {method} {path} id={fid} -> {r.status_code}: {r.text[:300]}"
    # a Privat user's personal workspace is not reachable with a business key either
    r = _call(w, method, path, w["key_b"], foreign_id=str(uuid.uuid4()), foreign_ws=w["ws_p1"],
              path_values={"workspace_id": w["ws_p1"], **{p: str(uuid.uuid4()) for p in params}})
    assert r.status_code in OK_DENIED and MARK["P1"] not in r.text


def test_public_api_session_token_and_key_confusion(world):
    w, c = world, world["c"]
    assert c.get("/v1/me", headers={"Authorization": f"Bearer {w['tok_a']}"}).status_code == 401   # session ≠ key
    me = c.get("/v1/me", headers={"Authorization": f"Bearer {w['key_b']}"})
    assert me.status_code == 200 and MARK["A"] not in me.text
    # an API key is not a session for the internal API
    assert c.get(f"/api/v1/workspaces/{w['ws_b']}", headers={"Authorization": f"Bearer {w['key_b']}"}).status_code == 401


def test_zz_victims_untouched(world):
    """Runs last: every row A and P1 own is byte-for-byte what it was before B/P2 threw their ids at every route."""
    w = world
    with get_session_factory()() as db:
        after = {"A": snapshot(db, uuid.UUID(w["ws_a"])), "P1": snapshot(db, uuid.UUID(w["ws_p1"]))}
    changed = {who: sorted(t for t in after[who] if after[who][t] != w["snap"][who].get(t)) for who in after}
    # ... and nothing the attackers own now points at the victim's objects (a foreign id accepted into a body)
    victim_ids = set(w["ids_a"].values()) | set(w["ids_p1"].values()) | {w["ws_a"], w["ws_p1"]}
    links = []
    with get_session_factory()() as db:
        for t in Base.metadata.sorted_tables:
            if "workspace_id" not in t.c:
                continue
            for ws in (w["ws_b"], w["ws_p2"]):
                for row in db.execute(sa.select(t).where(t.c.workspace_id == uuid.UUID(ws))).mappings():
                    for k, v in row.items():
                        if k != "workspace_id" and str(v) in victim_ids:
                            links.append(f"{t.name}.{k} (attacker {ws[:8]}) -> victim id {v}")
    (EVIDENCE / "victim-diff.json").write_text(json.dumps({"changed": changed, "cross_links": links}, indent=1))
    assert not changed["A"] and not changed["P1"], f"tables of the victim tenant changed during the sweep: {changed}"
    assert not links, f"attacker rows reference the victim's objects: {links}"

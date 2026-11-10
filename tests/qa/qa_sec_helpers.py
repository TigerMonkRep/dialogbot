"""Shared helpers for the security-privacy QA sweeps (tests/qa/test_qa_sec_*.py).

- `all_routes(app)`: every APIRoute the app serves, with its full path (works with FastAPI's nested
  `_IncludedRouter` wrappers and mounted sub-apps such as the public API at /v1).
- `dep_names(route)`: names of every dependency in the route's dependency tree (used to classify routes).
- `RowFactory`: inserts one generic row per workspace-scoped table for a workspace, so the IDOR sweep has a
  real object id of *every* kind to throw at other tenants' routes - automatically, also for tables added later.
- `body_for(schema, ...)`: a minimal body valid against a route's OpenAPI request schema, with every uuid field
  filled with a foreign id (body-ID swap).
"""
from __future__ import annotations

import re
import uuid
from datetime import UTC, date, datetime, time

import sqlalchemy as sa
from fastapi.routing import APIRoute
from sqlalchemy.dialects import postgresql as pg

from app.db import Base


# --------------------------------------------------------------------------- routes
def all_routes(app):
    def walk(routes, prefix=""):
        for r in routes:
            if isinstance(r, APIRoute):
                yield prefix + r.path, r
            elif hasattr(r, "original_router"):  # FastAPI >= 0.140 wraps include_router()
                yield from walk(r.original_router.routes, prefix + (r.include_context.prefix or ""))
            elif hasattr(r, "routes") and hasattr(r, "path"):  # Mount (public API sub-app)
                yield from walk(r.routes, prefix + r.path)
                app_ = getattr(r, "app", None)
                if app_ is not None and hasattr(app_, "router") and not r.routes:
                    yield from walk(app_.router.routes, prefix + r.path)

    seen = set()
    out = []
    for path, r in walk(app.routes):
        for m in sorted(r.methods - {"HEAD", "OPTIONS"}):
            if (m, path) not in seen:
                seen.add((m, path))
                out.append((m, path, r))
    return out


def dep_names(route) -> set[str]:
    acc: set[str] = set()

    def rec(d):
        for s in d.dependencies:
            acc.add(getattr(s.call, "__qualname__", type(s.call).__name__))
            rec(s)

    rec(route.dependant)
    return acc


PARAM_RE = re.compile(r"{([a-zA-Z_]+)(?::[a-z]+)?}")


def path_params(path: str) -> list[str]:
    return PARAM_RE.findall(path)


def fill(path: str, values: dict[str, str]) -> str:
    return PARAM_RE.sub(lambda m: str(values.get(m.group(1), m.group(0))), path)


# --------------------------------------------------------------------------- generic rows
_IN_RE = r"\b{col}\b\)?(?:::text)?\s+IN\s*\(([^)]*)\)"
_ANY_RE = r"\b{col}\b\)?(?:::text)?\s*=\s*ANY\s*\(\s*\(?ARRAY\[([^\]]*)\]"
TEXTY = re.compile(r"(name|title|text|label|note|body|subject|content|description|summary|message|question|answer|"
                   r"reason|comment|headline|caption)$")


def _allowed(table: sa.Table, col: str) -> list[str] | None:
    for c in table.constraints:
        if isinstance(c, sa.CheckConstraint):
            sql = str(c.sqltext)
            for pat in (_IN_RE, _ANY_RE):
                m = re.search(pat.format(col=re.escape(col)), sql, re.I)
                if m:
                    vals = re.findall(r"'([^']*)'", m.group(1))
                    if vals:
                        return vals
    return None


class RowFactory:
    """One row per workspace-scoped table for a given workspace. String columns carry `marker` so that any
    response containing it is provably the other tenant's data."""

    def __init__(self, db, ws_id: uuid.UUID, user_id: uuid.UUID, marker: str):
        self.db, self.ws, self.user, self.marker = db, ws_id, user_id, marker
        self.ids: dict[str, object] = {}       # table -> primary key of the row made for this workspace
        self.errors: dict[str, str] = {}

    def _value(self, table: sa.Table, col: sa.Column, required: bool):
        if col.name == "workspace_id":
            return self.ws
        for fk in col.foreign_keys:
            ref = fk.column.table.name
            if ref == "workspaces":
                return self.ws
            if ref == "users":
                return self.user
            if ref in self.ids and fk.column.name in ("id", "workspace_id"):
                return self.ids[ref] if fk.column.name == "id" else self.ws
            if not required:
                return None
            existing = self.db.execute(sa.select(fk.column).limit(1)).scalar()
            if existing is None:
                raise LookupError(f"needs a {ref} row")
            return existing
        allowed = _allowed(table, col.name)
        if allowed:
            return allowed[0]
        t = col.type
        if isinstance(t, sa.Enum):
            return t.enums[0]
        if isinstance(t, (pg.UUID, sa.Uuid)):
            return uuid.uuid4()
        if isinstance(t, sa.Boolean):
            return False
        if isinstance(t, (sa.Integer, sa.BigInteger, sa.SmallInteger, sa.Numeric, sa.Float)):
            return 1
        if isinstance(t, sa.DateTime):
            return datetime.now(UTC)
        if isinstance(t, sa.Date):
            return date.today()
        if isinstance(t, sa.Time):
            return time(10, 0)
        if isinstance(t, (pg.JSONB, sa.JSON)):
            return {}
        if isinstance(t, (pg.ARRAY, sa.ARRAY)):
            return []
        if isinstance(t, sa.LargeBinary):
            return b"\x00"
        if isinstance(t, (pg.INET,)):
            return "127.0.0.1"
        if isinstance(t, (sa.String, sa.Text)):
            n = getattr(t, "length", None) or 400
            if "email" in col.name:
                v = f"{self.marker.lower()}@example.com"
            elif "phone" in col.name or "e164" in col.name:
                v = "+4512345678"
            elif "currency" in col.name:
                v = "DKK"
            elif col.name in ("lang", "language", "locale") or col.name.endswith("_language"):
                v = "da"
            elif "hash" in col.name or "digest" in col.name or "token" in col.name or "slug" in col.name or col.name == "key":
                v = f"{self.marker.lower()}-{uuid.uuid4().hex}"
            else:
                v = f"{self.marker} {col.name} {uuid.uuid4().hex[:6]}"
            return v[:n]
        if not required:
            return None
        raise TypeError(f"no generator for {col.name}: {t!r}")

    def make(self, table: sa.Table) -> None:
        self._make(table, {})
        if table.name in self.errors and "CheckViolation" in self.errors[table.name]:
            for col in table.columns:  # try the other allowed values of each constrained column
                for alt in (_allowed(table, col.name) or [])[1:]:
                    del self.errors[table.name]
                    self._make(table, {col.name: alt})
                    if table.name not in self.errors:
                        return

    def _make(self, table: sa.Table, override: dict) -> None:
        row = {}
        try:
            for col in table.columns:
                required = (not col.nullable) and col.default is None and col.server_default is None
                is_pk = col.primary_key
                if is_pk and col.name == "workspace_id":
                    row[col.name] = self.ws
                    continue
                if is_pk and isinstance(col.type, (pg.UUID, sa.Uuid)) and not col.foreign_keys:
                    row[col.name] = uuid.uuid4()
                    continue
                if required or col.foreign_keys or col.name == "workspace_id" or (
                        isinstance(col.type, (sa.String, sa.Text)) and TEXTY.search(col.name) and _allowed(table, col.name) is None):
                    v = self._value(table, col, required or is_pk)
                    if v is not None or not col.nullable:
                        row[col.name] = v
            row.update(override)
            with self.db.begin_nested():
                self.db.execute(table.insert().values(**row))
            pk = [c.name for c in table.primary_key.columns]
            self.ids[table.name] = row.get("id", row.get(pk[0]) if pk else None)
        except Exception as e:  # noqa: BLE001 - record and move on: coverage is reported, not assumed
            self.errors[table.name] = f"{type(e).__name__}: {str(e).splitlines()[0][:200]}"

    def make_all(self, tables=None) -> RowFactory:
        tables = tables or [t for t in Base.metadata.sorted_tables if "workspace_id" in t.c]
        for _ in range(2):  # second pass picks up tables whose FK targets were made later in the first
            for t in tables:
                if t.name not in self.ids:
                    self.make(t)
        for name in list(self.errors):
            if name in self.ids:
                del self.errors[name]
        self.db.commit()
        return self

    def object_ids(self) -> dict[str, str]:
        """table -> id, only real per-object ids (not 1:1 tables keyed by workspace_id)."""
        return {t: str(i) for t, i in self.ids.items() if i is not None and str(i) != str(self.ws)}


def snapshot(db, ws_id) -> dict[str, str]:
    """A fingerprint of every row a workspace owns, per table."""
    out = {}
    for t in Base.metadata.sorted_tables:
        if "workspace_id" not in t.c:
            continue
        rows = db.execute(sa.select(t).where(t.c.workspace_id == ws_id)).mappings().all()
        keep = [{k: v for k, v in r.items() if k not in ("last_seen_at", "last_used_at")} for r in rows]
        out[t.name] = repr(sorted(repr(sorted(r.items(), key=lambda kv: kv[0])) for r in keep))
    return out


# --------------------------------------------------------------------------- request bodies
def _resolve(spec: dict, s: dict) -> dict:
    while "$ref" in s:
        name = s["$ref"].split("/")[-1]
        s = spec["components"]["schemas"][name]
    return s


# Values for free-text fields that the code validates itself (so the request reaches the object lookup).
HINTS = {"role": "staff", "kind": "service", "product_intent": "reception", "expected_version": 1, "mode": "group",
         "method": "credit", "action": "take", "provider": "google", "locale": "da", "language": "da", "title": "qa-sec-probe",
         "name": "qa-sec-probe", "text": "qa-sec-probe", "phone": "+4512345678", "phone_e164": "+4512345678",
         "scopes": ["calls:read"], "url": "https://qa-sec.invalid/", "website": None}
_ALT_RE = re.compile(r"^\^\(?([A-Za-z0-9_\-|.]+)\)?\$$")


def body_for(spec: dict, schema: dict | None, foreign_id: str, foreign_ws: str, depth: int = 0, name: str | None = None):
    if schema is None or depth > 6:
        return None
    s = _resolve(spec, schema)
    if name in HINTS and not (s.get("format") == "uuid"):
        return HINTS[name]
    if isinstance(s.get("pattern"), str) and (m := _ALT_RE.match(s["pattern"])):
        return m.group(1).split("|")[0]
    for key in ("anyOf", "oneOf"):
        if key in s:
            opts = [o for o in s[key] if _resolve(spec, o).get("type") != "null"]
            return body_for(spec, opts[0] if opts else s[key][0], foreign_id, foreign_ws, depth + 1)
    if "allOf" in s:
        return body_for(spec, s["allOf"][0], foreign_id, foreign_ws, depth + 1)
    if "const" in s:
        return s["const"]
    if "enum" in s:
        return s["enum"][0]
    if "default" in s and s.get("type") not in ("object",):
        return s["default"]
    t = s.get("type")
    fmt = s.get("format")
    if t == "object" or "properties" in s:
        out = {}
        for name, sub in (s.get("properties") or {}).items():
            if name not in (s.get("required") or []) and not name.endswith("_id") and not name.endswith("_ids"):
                continue
            if name == "workspace_id":
                out[name] = foreign_ws
                continue
            out[name] = body_for(spec, sub, foreign_id, foreign_ws, depth + 1, name)
        return out
    if t == "array":
        n = max(1, s.get("minItems", 1))
        return [body_for(spec, s.get("items", {}), foreign_id, foreign_ws, depth + 1) for _ in range(n)]
    if t == "string":
        if fmt == "uuid":
            return foreign_id
        if fmt == "email":
            return "qa-sec-probe@example.com"
        if fmt == "date-time":
            return "2026-12-01T10:00:00+00:00"
        if fmt == "date":
            return "2026-12-01"
        if fmt in ("uri", "url"):
            return "https://qa-sec.invalid/"  # .invalid never resolves: no request can leave the machine
        n = max(s.get("minLength", 1), 3)
        return ("qa-sec-probe-" * 5)[: max(n, min(13, s.get("maxLength", 13)))]
    if t == "integer":
        return max(s.get("minimum", 1), 1) if "maximum" not in s else s.get("minimum", 0)
    if t == "number":
        return s.get("minimum", 1)
    if t == "boolean":
        return False
    return None


def request_schema(spec: dict, method: str, path: str) -> dict | None:
    op = (spec.get("paths", {}).get(path) or {}).get(method.lower()) or {}
    content = (op.get("requestBody") or {}).get("content") or {}
    js = content.get("application/json")
    return js.get("schema") if js else None


def mask(s: str) -> str:
    """Never print a secret: keep 4 leading chars and the length."""
    return f"{s[:4]}…({len(s)} tegn)"

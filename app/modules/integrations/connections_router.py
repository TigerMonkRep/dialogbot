"""Customer-facing integrations API: the catalogue with honest status, connect/disconnect, configuration, tests
and the action trail. Secrets go in, never out: responses carry booleans, labels and timestamps only.

The OAuth callback is the one route outside `/workspaces/{id}`: the provider redirects the browser there, and the
single-use `state` row tells us which workspace and user started the attempt.
"""
from __future__ import annotations

import secrets as _secrets
from datetime import UTC, datetime
from typing import Any

import jsonschema
from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session as OrmSession

from app.config import get_settings
from app.core.audit import record_audit
from app.core.auth import WorkspaceContext, require_capability
from app.core.errors import ApiError, Conflict, ValidationFailed
from app.core.idempotency import IdempotencyGuard
from app.db import get_db
from app.models import IntegrationConnection
from app.modules.integrations import actions, connectors, credentials, oauth
from app.modules.integrations.connectors import webhook
from app.modules.integrations.connectors.base import ActionError, RunContext

router = APIRouter(prefix="/workspaces/{workspace_id}/integrations", tags=["integrations"])
oauth_router = APIRouter(prefix="/integrations/oauth", tags=["integrations"])


def _audit(db, request, ctx, action: str, key: str, after: dict | None = None) -> None:
    record_audit(db, workspace_id=ctx.workspace.id, actor_user_id=ctx.user_id, action=action, object_type="integration",
                 object_id=ctx.workspace.id, after={"connector": key, **(after or {})}, request_id=request.state.request_id)


def _spec_out(sp, st: dict | None) -> dict:
    return {
        "key": sp.key, "label": sp.label, "description": sp.description, "category": sp.category,
        "auth_kind": sp.auth_kind, "availability": sp.availability, "zapier_note": sp.zapier_note, "docs_url": sp.docs_url,
        "events": list(sp.events), "config_schema": sp.config_schema, "secret_fields": list(sp.secret_fields),
        "actions": [{"name": a.name, "label": a.label, "description": a.description, "confirm": a.confirm,
                     "channels": list(a.channels), "input_schema": a.input_schema, "output_schema": a.output_schema}
                    for a in sp.actions],
        **(st or {"status": "not_implemented", "reason": "På vej – ikke tilgængelig endnu.", "error": None,
                  "simulated": False, "account_label": "", "config": {}, "version": None, "connected_at": None,
                  "last_ok_at": None, "expires_at": None}),
    }


@router.get("")
def catalogue(ctx: WorkspaceContext = Depends(require_capability("integrations.read")), db: OrmSession = Depends(get_db)):
    st = connectors.statuses(db, ctx.workspace.id)
    items = [_spec_out(sp, st.get(sp.key)) for sp in connectors.all_specs()]
    runs = actions.recent_runs(db, ctx.workspace.id, limit=20)
    return {"items": items, "recent_actions": [actions.run_out(r) for r in runs],
            "simulated": get_settings().connectors_provider == "fake",
            "frontend_return": f"{get_settings().frontend_base_url.rstrip('/')}/app/settings/integrationer"}


class ConnectIn(BaseModel):
    config: dict[str, Any] = Field(default_factory=dict)
    secrets: dict[str, str] = Field(default_factory=dict)  # api_key / secret connectors; never echoed back


def _validate_config(sp, config: dict) -> dict:
    if not sp.config_schema:
        return {}
    try:
        jsonschema.validate(config, sp.config_schema)
    except jsonschema.ValidationError as e:
        path = ".".join(str(p) for p in e.absolute_path) or "config"
        raise ValidationFailed(f"Ugyldig opsætning ({path}): {e.message[:120]}", field_errors=[{"field": path}]) from e
    return config


def _upsert(db: OrmSession, ctx: WorkspaceContext, key: str, *, auth_kind: str, secret: dict | None, config: dict,
            account_label: str, scopes: list[str], expires_at: datetime | None, simulated: bool) -> IntegrationConnection:
    conn = credentials.connection(db, ctx.workspace.id, key, lock=True)
    if conn is None:
        conn = IntegrationConnection(workspace_id=ctx.workspace.id, connector=key, auth_kind=auth_kind)
        db.add(conn)
    else:
        conn.version += 1
    conn.auth_kind, conn.config, conn.account_label, conn.scopes = auth_kind, config, account_label[:200], scopes
    conn.expires_at, conn.simulated, conn.connected_by, conn.connected_at = expires_at, simulated, ctx.user_id, datetime.now(UTC)
    credentials.put_secret(conn, secret)
    credentials.mark_ok(conn)
    db.flush()
    return conn


@router.post("/{key}/connect", status_code=200)
def connect(key: str, body: ConnectIn, request: Request, ctx: WorkspaceContext = Depends(require_capability("integrations.manage")),
            db: OrmSession = Depends(get_db), idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")):
    sp = connectors.spec(key)
    if key == "bookings":
        raise Conflict("Dialogbots kalender styres under Bookinger (online booking og bookingtyper).",
                       code="connector_builtin")
    st = connectors.statuses(db, ctx.workspace.id)[key]
    if st["status"] == "not_implemented":
        raise ApiError(st["reason"] or "Ikke tilgængelig", code="connector_not_available", status_code=501)
    guard = IdempotencyGuard(db, f"{ctx.user_id}:{ctx.workspace.id}:integrations.connect:{key}", idempotency_key,
                             {"config": body.config, "secret_fields": sorted(body.secrets)})
    if guard.replay:
        return guard.replay[1]
    simulated = get_settings().connectors_provider == "fake"
    config = _validate_config(sp, body.config)
    if sp.auth_kind == "oauth":
        provider = oauth.provider_for("google" if key == "google_calendar" else "microsoft")
        if simulated:
            state = _secrets.token_urlsafe(16)
            db.add(oauth_state_row(ctx, key, state))
            url = f"{oauth.redirect_uri(key)}?state={state}&code=fake-code"
        else:
            url = oauth.start(db, workspace_id=ctx.workspace.id, connector=key, provider=provider, user_id=ctx.user_id)
        # Non-secret config (calendar id) is stored when the callback lands; keep it on the state via config later.
        _audit(db, request, ctx, "integrations.oauth_started", key)
        out = {"status": "authorize", "authorize_url": url}
        guard.store(200, out)
        db.commit()
        return out
    secret: dict | None = None
    shown: dict = {}
    if key in ("webhook", "zapier", "make"):
        if not webhook.url_allowed(str(config.get("url") or "")):
            raise ValidationFailed("Adressen skal være en offentlig https-adresse", field_errors=[{"field": "url"}])
        signing = webhook.new_secret()
        secret, shown = {"signing_secret": signing}, {"signing_secret": signing}  # shown exactly once
    elif sp.secret_fields:
        missing = [f for f in sp.secret_fields if not body.secrets.get(f)]
        if missing:
            raise ValidationFailed("Udfyld " + ", ".join(missing), field_errors=[{"field": f} for f in missing])
        secret = {f: body.secrets[f] for f in sp.secret_fields}
    adapter = connectors.build_adapter(db, ctx.workspace.id, key, secret, config, simulated)
    try:
        facts = adapter.test_connection()
    except ActionError as e:
        raise ApiError(f"Forbindelsen kunne ikke bekræftes: {e.message}", code="connection_test_failed", status_code=502) from e
    conn = _upsert(db, ctx, key, auth_kind=sp.auth_kind, secret=secret, config=config,
                   account_label=str(facts.get("name") or facts.get("sender") or facts.get("url") or "")[:200],
                   scopes=[], expires_at=None, simulated=simulated)
    _audit(db, request, ctx, "integrations.connected", key, {"simulated": simulated})
    out = {"status": "connected", "connector": key, "simulated": simulated, "account_label": conn.account_label,
           "version": conn.version, "facts": facts}
    guard.store(200, out)  # the stored replay never contains the signing secret
    db.commit()
    return out | shown


def oauth_state_row(ctx: WorkspaceContext, key: str, state: str):
    """A state row for the simulated OAuth flow (no verifier needed, but the row still expires and is single-use)."""
    from datetime import timedelta

    from app.core import crypto
    from app.models import OAuthState

    env = crypto.encrypt(b"fake-verifier", aad=state.encode())
    return OAuthState(state=state, workspace_id=ctx.workspace.id, connector=key, user_id=ctx.user_id,
                      key_version=env.key_version, verifier_blob=env.blob, expires_at=datetime.now(UTC) + timedelta(minutes=10))


@oauth_router.get("/{key}/callback")
def oauth_callback(key: str, state: str = Query(default=""), code: str = Query(default=""), error: str = Query(default=""),
                   db: OrmSession = Depends(get_db)):
    """Provider redirect. Always ends in a redirect to the frontend, with `connected=<key>` or `error=<code>`."""
    back = f"{get_settings().frontend_base_url.rstrip('/')}/app/settings/integrationer"
    try:
        sp = connectors.spec(key)
        if sp.auth_kind != "oauth":
            raise ApiError("Ikke en OAuth-connector", code="not_oauth")
        row, verifier = oauth.consume_state(db, state, key)
        db.flush()
        if error or not code:
            db.commit()
            return RedirectResponse(f"{back}?error=oauth_denied&connector={key}", status_code=303)
        simulated = get_settings().connectors_provider == "fake"
        if simulated:
            from app.modules.integrations.connectors.fakes import fake_oauth_tokens

            tok = fake_oauth_tokens(key)
        else:
            provider = oauth.provider_for("google" if key == "google_calendar" else "microsoft")
            tok = oauth.exchange(provider, code=code, verifier=verifier, connector=key)
        secret, expires = oauth.token_secret(tok)
        label = oauth.id_token_email(secret.get("id_token"))
        # Verify with a real call before claiming "connected".
        adapter = connectors.build_adapter(db, row.workspace_id, key, secret, {}, simulated)
        facts = adapter.test_connection()

        class _Ctx:  # minimal context for _upsert/audit
            workspace = type("W", (), {"id": row.workspace_id})()
            user_id = row.user_id

        ctx = _Ctx()
        conn = _upsert(db, ctx, key, auth_kind="oauth", secret=secret, config={},
                       account_label=str(facts.get("email") or label or facts.get("name") or "")[:200],
                       scopes=[str(x) for x in str(tok.get("scope") or "").split() if x], expires_at=expires, simulated=simulated)
        conn.config = {"calendar_id": str(facts.get("calendar_id") or "")} if facts.get("calendar_id") else {}
        record_audit(db, workspace_id=row.workspace_id, actor_user_id=row.user_id, action="integrations.connected",
                     object_type="integration", object_id=row.workspace_id, after={"connector": key, "simulated": simulated},
                     request_id=None)
        db.commit()
        return RedirectResponse(f"{back}?connected={key}", status_code=303)
    except ApiError as e:
        db.rollback()
        return RedirectResponse(f"{back}?error={e.code}&connector={key}", status_code=303)
    except ActionError as e:
        db.rollback()
        return RedirectResponse(f"{back}?error={e.code}&connector={key}", status_code=303)


class SettingsIn(BaseModel):
    config: dict[str, Any] = Field(default_factory=dict)
    expected_version: int


@router.put("/{key}")
def update_settings(key: str, body: SettingsIn, request: Request,
                    ctx: WorkspaceContext = Depends(require_capability("integrations.manage")), db: OrmSession = Depends(get_db)):
    sp = connectors.spec(key)
    conn = credentials.connection(db, ctx.workspace.id, key, lock=True)
    if conn is None:
        raise ApiError("Connectoren er ikke forbundet", code="not_connected", status_code=404)
    if conn.version != body.expected_version:
        raise Conflict("Opsætningen er ændret af en anden. Genindlæs og prøv igen.", code="version_conflict")
    config = _validate_config(sp, body.config)
    if key in ("webhook", "zapier", "make") and not webhook.url_allowed(str(config.get("url") or "")):
        raise ValidationFailed("Adressen skal være en offentlig https-adresse", field_errors=[{"field": "url"}])
    conn.config, conn.version = config, conn.version + 1
    _audit(db, request, ctx, "integrations.settings_updated", key)
    db.commit()
    return {"connector": key, "config": conn.config, "version": conn.version}


@router.post("/{key}/test")
def test_connection(key: str, request: Request, ctx: WorkspaceContext = Depends(require_capability("integrations.manage")),
                    db: OrmSession = Depends(get_db), idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")):
    guard = IdempotencyGuard(db, f"{ctx.user_id}:{ctx.workspace.id}:integrations.test:{key}", idempotency_key, {})
    if guard.replay:
        return guard.replay[1]
    conn = credentials.connection(db, ctx.workspace.id, key, lock=True)
    if key != "bookings" and conn is None:
        raise ApiError("Connectoren er ikke forbundet", code="not_connected", status_code=404)
    try:
        if conn is not None and conn.status == "error":
            credentials.mark_ok(conn)  # give the real call the chance to clear the error
        facts = connectors.adapter_for(db, ctx.workspace.id, key).test_connection()
        if conn is not None:
            credentials.mark_ok(conn)
        out = {"ok": True, "facts": facts, "simulated": bool(conn.simulated) if conn else False}
    except ActionError as e:
        if conn is not None:
            credentials.mark_error(conn, e.message)
        out = {"ok": False, "error": e.message, "simulated": bool(conn.simulated) if conn else False}
    _audit(db, request, ctx, "integrations.tested", key, {"ok": out["ok"]})
    guard.store(200, out)
    db.commit()
    return out


class RunIn(BaseModel):
    action: str = Field(min_length=1, max_length=60)
    input: dict[str, Any] = Field(default_factory=dict)


@router.post("/{key}/run")
def run_action(key: str, body: RunIn, request: Request, ctx: WorkspaceContext = Depends(require_capability("integrations.manage")),
               db: OrmSession = Depends(get_db)):
    """A person tries an action from the settings page (channel 'test'); it is logged like any other."""
    from app.modules.reports.service import tz_of

    sp = connectors.spec(key)
    if sp.action(body.action) is None:
        raise ApiError("Handlingen findes ikke på denne connector", code="unknown_action", status_code=404)
    run_ctx = RunContext(workspace_id=ctx.workspace.id, channel="test", user_id=ctx.user_id, tz=tz_of(db, ctx.workspace.id))
    text, run = actions.execute(db, ctx.workspace, body.action, body.input, run_ctx)
    _audit(db, request, ctx, "integrations.action_tested", key, {"action": body.action, "status": run.status})
    db.commit()
    return {"text": text, "run": actions.run_out(run)}


@router.delete("/{key}", status_code=204)
def disconnect(key: str, request: Request, ctx: WorkspaceContext = Depends(require_capability("integrations.manage")),
               db: OrmSession = Depends(get_db)):
    connectors.spec(key)
    conn = credentials.connection(db, ctx.workspace.id, key, lock=True)
    if conn is None:
        return None
    if conn.auth_kind == "oauth" and not conn.simulated:
        secret = credentials.get_secret(conn) or {}
        provider = oauth.provider_for("google" if key == "google_calendar" else "microsoft")
        for tok in (secret.get("refresh_token"), secret.get("access_token")):
            if tok:
                oauth.revoke(provider, tok)
    db.delete(conn)
    _audit(db, request, ctx, "integrations.disconnected", key)
    db.commit()
    return None


@router.get("/actions")
def list_actions(connector: str | None = None, limit: int = Query(default=50, ge=1, le=200),
                 ctx: WorkspaceContext = Depends(require_capability("integrations.read")), db: OrmSession = Depends(get_db)):
    return {"items": [actions.run_out(r) for r in actions.recent_runs(db, ctx.workspace.id, connector=connector, limit=limit)]}


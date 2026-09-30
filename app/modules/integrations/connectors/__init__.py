"""The connector register: which systems Dialogbot can act in, and each workspace's status per connector.

Statuses are computed, never stored as a flag the client can set:
- `not_implemented`: the connector is "på vej"/"via Zapier", or this deployment lacks what it needs (OAuth client,
  telephony) – the reason is returned so the UI can say so honestly;
- `not_connected`: available, the workspace has not connected it;
- `connected`: a credential row exists and the last real call succeeded;
- `error`: a credential row exists but the last call failed (the reason is on the row).

Order matters for the tool-builder: an OAuth calendar comes before the built-in Dialogbot calendar, so a connected
Google/Microsoft calendar takes over the four booking actions.
"""
from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session as OrmSession

from app.config import get_settings
from app.core.errors import ApiError
from app.models import ActionRun, BookingSettings, IntegrationConnection, Workspace
from app.modules.integrations import credentials
from app.modules.integrations.connectors import calendar, sms, webhook
from app.modules.integrations.connectors.base import ActionError, Adapter, ConnectorSpec, obj

REFRESH_MARGIN = timedelta(seconds=90)


def _oauth_unavailable(provider: str) -> Callable[[], str | None]:
    def check() -> str | None:
        from app.modules.integrations import oauth

        if get_settings().connectors_provider == "fake":
            return None
        if not oauth.provider_for(provider).configured():
            env = "GOOGLE_OAUTH_CLIENT_ID/SECRET" if provider == "google" else "MICROSOFT_OAUTH_CLIENT_ID/SECRET"
            return f"Kræver, at Dialogbot har registreret en OAuth-klient hos leverandøren ({env})."
        return None

    return check


def _calendar_adapter(key: str):
    def build(db: OrmSession, ws_id: uuid.UUID, secret: dict | None, config: dict, simulated: bool):
        client = _oauth_calendar_client(key, secret, config, simulated, ws_id)
        return calendar.CalendarActions(db, ws_id, client, key)

    return build


def _oauth_calendar_client(key: str, secret: dict | None, config: dict, simulated: bool, ws_id: uuid.UUID):
    if simulated:
        from app.modules.integrations.connectors.fakes import FakeCalendarClient

        return FakeCalendarClient(f"{key}:{ws_id}")
    token = (secret or {}).get("access_token", "")
    if key == "google_calendar":
        return calendar.GoogleCalendarClient(token, str(config.get("calendar_id") or "primary"))
    return calendar.MicrosoftCalendarClient(token, str(config.get("calendar_id") or ""))


class _BuiltinCalendar:
    """Dialogbot's own calendar (opening hours + iCal). Always present; 'connected' when online booking is on."""

    def __init__(self, db: OrmSession, ws_id: uuid.UUID):
        self.inner = calendar.CalendarActions(db, ws_id, None, "bookings")
        self.simulated = False

    def test_connection(self) -> dict:
        return self.inner.test_connection()

    def run(self, action, data, ctx):
        return self.inner.run(action, data, ctx)


CALENDAR_CONFIG = obj({"calendar_id": {"type": "string", "maxLength": 200,
                                       "description": "Kalender-id (tom = primær kalender)"}})

SPECS: dict[str, ConnectorSpec] = {}
for _spec in (
    ConnectorSpec(key="google_calendar", label="Google Kalender", category="calendar", auth_kind="oauth",
                  description="Assistenten finder ledige tider i jeres Google Kalender og opretter, flytter og aflyser "
                              "aftaler direkte i den. Erstatter iCal-koblingen.",
                  actions=calendar.ACTIONS, config_schema=CALENDAR_CONFIG,
                  unavailable_reason=_oauth_unavailable("google"), adapter=_calendar_adapter("google_calendar"),
                  docs_url="https://developers.google.com/calendar"),
    ConnectorSpec(key="microsoft_calendar", label="Microsoft 365-kalender (Outlook)", category="calendar", auth_kind="oauth",
                  description="Assistenten finder ledige tider i jeres Outlook-kalender og opretter, flytter og aflyser "
                              "aftaler direkte i den. Erstatter iCal-koblingen.",
                  actions=calendar.ACTIONS, config_schema=CALENDAR_CONFIG,
                  unavailable_reason=_oauth_unavailable("microsoft"), adapter=_calendar_adapter("microsoft_calendar"),
                  docs_url="https://learn.microsoft.com/graph/api/resources/calendar"),
    ConnectorSpec(key="bookings", label="Dialogbots kalender", category="calendar", auth_kind="builtin",
                  description="Ledige tider ud fra godkendte åbningstider; optaget tid fra jeres kalenders iCal-adresse. "
                              "Bruges, når ingen kalender er forbundet via Google eller Microsoft.",
                  actions=calendar.ACTIONS,
                  adapter=lambda db, ws_id, secret, config, simulated: _BuiltinCalendar(db, ws_id)),
    sms.SPEC, webhook.WEBHOOK, webhook.ZAPIER, webhook.MAKE,
):
    SPECS[_spec.key] = _spec

# "På vej" and "via Zapier/Make": promised honestly as not implemented. Etape 2–4 in docs/strategy/etapeplan-handlinger.md.
COMING: tuple[ConnectorSpec, ...] = (
    ConnectorSpec("hubspot", "HubSpot", "Slå kunden op, opret kontakt og notér henvendelsen (etape 2).", "crm", "oauth",
                  availability="coming", zapier_note="Kan nås i dag via Zapier eller Make."),
    ConnectorSpec("pipedrive", "Pipedrive", "Slå kunden op og opret aktivitet (etape 2).", "crm", "oauth",
                  availability="coming", zapier_note="Kan nås i dag via Zapier eller Make."),
    ConnectorSpec("economic", "e-conomic", "Find faktura, send fakturakopi, opret tilbudskladde (etape 3).", "accounting", "api_key",
                  availability="coming", zapier_note="Kan nås i dag via Zapier eller Make."),
    ConnectorSpec("dinero", "Dinero", "Find faktura og kunde (etape 3).", "accounting", "api_key",
                  availability="coming", zapier_note="Kan nås i dag via Zapier."),
    ConnectorSpec("billy", "Billy", "Find faktura og kunde (etape 3).", "accounting", "api_key", availability="coming",
                  zapier_note="Kan nås i dag via Zapier."),
    ConnectorSpec("microsoft_bookings", "Microsoft Bookings", "Book i jeres Bookings-side (etape 4).", "booking", "oauth",
                  availability="coming"),
    ConnectorSpec("simplybook", "SimplyBook.me", "Book i jeres SimplyBook-kalender (etape 4).", "booking", "api_key",
                  availability="coming", zapier_note="Kan nås i dag via Zapier."),
    ConnectorSpec("ordrestyring", "Ordrestyring", "Opret sag og find status (etape 4).", "field_service", "api_key",
                  availability="coming"),
    ConnectorSpec("minuba", "Minuba", "Opret sag og find status (etape 4).", "field_service", "api_key",
                  availability="coming"),
    ConnectorSpec("planday", "Planday", "Hvem er på vagt – til korrekt tilbagekald (etape 4).", "staffing", "oauth",
                  availability="coming", zapier_note="Kan nås i dag via Zapier."),
)

TOOL_ORDER = ("google_calendar", "microsoft_calendar", "bookings", "twilio_sms", "webhook", "zapier", "make")


def spec(key: str) -> ConnectorSpec:
    try:
        return SPECS[key]
    except KeyError:
        raise ApiError("Ukendt connector", code="unknown_connector", status_code=404) from None


def all_specs() -> list[ConnectorSpec]:
    return [SPECS[k] for k in TOOL_ORDER] + list(COMING)


def _builtin_calendar_status(db: OrmSession, ws_id: uuid.UUID) -> tuple[str, str | None]:
    from app.modules.bookings.service import active_types

    s = db.get(BookingSettings, ws_id)
    if s is None or not s.enabled or not active_types(db, ws_id):
        return "not_connected", "Slå online booking til og opret en bookingtype under Bookinger."
    return "connected", None


def _key_missing(sp: ConnectorSpec) -> str | None:
    s = get_settings()
    if sp.auth_kind in ("oauth", "secret", "api_key") and not s.credentials_key and s.app_env not in ("dev", "test"):
        return "Kræver, at Dialogbot har sat en krypteringsnøgle til legitimationer (CREDENTIALS_KEY) på serveren."
    return None


def statuses(db: OrmSession, ws_id: uuid.UUID) -> dict[str, dict]:
    """Status per available connector for one workspace (COMING connectors are always not_implemented)."""
    rows = credentials.connections(db, ws_id)
    simulated_env = get_settings().connectors_provider == "fake"
    out: dict[str, dict] = {}
    for key in TOOL_ORDER:
        sp = SPECS[key]
        row = rows.get(key)
        status, reason = "not_connected", None
        if (why := sp.unavailable_reason() or _key_missing(sp)) is not None:
            status, reason = "not_implemented", why
        elif key == "bookings":
            status, reason = _builtin_calendar_status(db, ws_id)
        elif row is not None:
            status = row.status
        out[key] = {"status": status, "reason": reason, "error": row.error if row else None,
                    "simulated": bool(row.simulated) if row else simulated_env,
                    "account_label": row.account_label if row else "", "config": dict(row.config) if row else {},
                    "version": row.version if row else None,
                    "connected_at": row.connected_at.isoformat() if row and row.connected_at else None,
                    "last_ok_at": row.last_ok_at.isoformat() if row and row.last_ok_at else None,
                    "expires_at": row.expires_at.isoformat() if row and row.expires_at else None}
    return out


def _fresh_secret(db: OrmSession, conn: IntegrationConnection) -> dict | None:
    """The decrypted secret, refreshing an OAuth access token that is about to expire."""
    from app.modules.integrations import oauth

    secret = credentials.get_secret(conn)
    if conn.auth_kind != "oauth" or conn.simulated or secret is None:
        return secret
    if conn.expires_at is not None and conn.expires_at - datetime.now(UTC) > REFRESH_MARGIN:
        return secret
    if not secret.get("refresh_token"):
        credentials.mark_error(conn, "Adgangen er udløbet, og der er intet fornyelsestoken – forbind igen.")
        raise ActionError("Kalenderforbindelsen er udløbet – forbind kalenderen igen", code="provider_unauthorized")
    provider = oauth.provider_for("google" if conn.connector == "google_calendar" else "microsoft")
    try:
        tok = oauth.refresh(provider, secret["refresh_token"])
    except ApiError as e:
        credentials.mark_error(conn, f"Adgangen kunne ikke fornys: {e.message}")
        raise ActionError("Kalenderforbindelsen kunne ikke fornys – forbind kalenderen igen",
                          code="provider_unauthorized") from e
    new_secret, expires = oauth.token_secret(tok, previous=secret)
    credentials.put_secret(conn, new_secret)
    conn.expires_at = expires
    db.flush()
    return new_secret


def adapter_for(db: OrmSession, ws_id: uuid.UUID, key: str) -> Adapter:
    """The adapter for a *connected* connector. Raises ActionError otherwise (the model gets an honest answer)."""
    sp = spec(key)
    st = statuses(db, ws_id).get(key)
    if st is None or st["status"] != "connected":
        raise ActionError(f"{sp.label} er ikke forbundet", code="not_connected")
    row = credentials.connection(db, ws_id, key)
    secret = _fresh_secret(db, row) if row is not None else None
    config = dict(row.config) if row is not None else {}
    simulated = bool(row.simulated) if row is not None else False
    return sp.adapter(db, ws_id, secret, config, simulated)


def calendar_client(db: OrmSession, ws_id: uuid.UUID, key: str):
    row = credentials.connection(db, ws_id, key)
    if row is None:
        raise ActionError("Kalenderen er ikke forbundet", code="not_connected")
    return _oauth_calendar_client(key, _fresh_secret(db, row), dict(row.config), bool(row.simulated), ws_id)


def build_adapter(db: OrmSession, ws_id: uuid.UUID, key: str, secret: dict | None, config: dict, simulated: bool) -> Adapter:
    """An adapter for a connection that is not stored yet (used to test before saving)."""
    return spec(key).adapter(db, ws_id, secret, config, simulated)


def after_action(db: OrmSession, ws: Workspace, run: ActionRun) -> None:
    from app.modules.integrations import events

    if run.status == "ok" and run.action not in ("ledige_tider",):
        events.emit(db, ws.id, "action.completed",
                    {"action": run.action, "label": run.label, "connector": run.connector, "channel": run.channel,
                     "conversation_id": str(run.conversation_id) if run.conversation_id else None,
                     "output": run.output, "simulated": run.simulated}, key=str(run.id))


def note_failure(db: OrmSession, ws_id: uuid.UUID, key: str, err: ActionError) -> None:
    """Authorization failures flip the connection to `error` so the owner sees it under Integrationer."""
    if err.code in ("provider_unauthorized", "sms_not_configured"):
        conn = credentials.connection(db, ws_id, key)
        if conn is not None:
            credentials.mark_error(conn, err.message)

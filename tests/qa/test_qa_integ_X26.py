"""QA X26 (integrations-qa): honest integration status – live / test-mode / adapter-only / not-implemented.

Krav X26: "Ærlig integrationsstatus: live/test/adapter/ikke bygget – UI viser præcis det; aldrig grøn stub".
DB-018: "Adapters identify environment and capabilities; provider verification gates activation; no real
launch/payment/message caused by test path."

Every provider is replaced at the adapter boundary (stub Twilio client, stubbed HTTP for the calendar client, fake
connectors). No network call leaves the process; no real value of any secret is read – env vars are set to dummies.
The status matrix these tests back is qa/integrations/status.md.
"""
from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import pytest

from app.config import Settings, get_settings
from app.modules.integrations import oauth
from app.modules.integrations.connectors import calendar as cal
from app.modules.integrations.connectors.fakes import WORLD

COMING = {"hubspot", "pipedrive", "economic", "dinero", "billy", "microsoft_bookings", "simplybook", "ordrestyring",
          "minuba", "planday"}
READY = ("google_calendar", "microsoft_calendar", "bookings", "twilio_sms", "webhook", "zapier", "make")
INTEGRATION_ENV = ("CONNECTORS_PROVIDER", "TELEPHONY_PROVIDER", "GOOGLE_OAUTH_CLIENT_ID", "GOOGLE_OAUTH_CLIENT_SECRET",
                   "MICROSOFT_OAUTH_CLIENT_ID", "MICROSOFT_OAUTH_CLIENT_SECRET", "CREDENTIALS_KEY", "TWILIO_ACCOUNT_SID",
                   "TWILIO_AUTH_TOKEN", "VAPI_API_KEY", "VAPI_SERVER_SECRET", "STRIPE_SECRET_KEY",
                   "STRIPE_WEBHOOK_SECRET", "TRACK17_API_KEY", "DUFFEL_ACCESS_TOKEN", "TRAVELPAYOUTS_TOKEN",
                   "TRAVELPAYOUTS_MARKER", "SMS_DEFAULT_SENDER")


@pytest.fixture
def bare_env(monkeypatch):
    """A deployment with NO integration env vars at all (CONNECTORS_PROVIDER=live is the default)."""
    for k in INTEGRATION_ENV:
        monkeypatch.delenv(k, raising=False)
    get_settings.cache_clear()
    WORLD.reset()
    yield monkeypatch
    WORLD.reset()
    get_settings.cache_clear()


def _set(mp, **env):
    for k, v in env.items():
        mp.setenv(k, v)
    get_settings.cache_clear()


def _owner(api, tag="x26"):
    tok = api.user(f"{tag}-owner@testmail.dk")
    ws = api.workspace(tok, "Fjord Gulvservice ApS")
    return tok, ws


def _catalogue(api, tok, ws) -> dict:
    r = api.get(tok, f"/workspaces/{ws}/integrations")
    assert r.status_code == 200, r.text
    return r.json()


def _items(cat: dict) -> dict:
    return {i["key"]: i for i in cat["items"]}


# --------------------------------------------------------------------------- env vars missing

def test_missing_env_every_connector_is_honest_and_nothing_can_be_connected(api, bare_env, db):
    from sqlalchemy import func, select

    from app.models import IntegrationConnection, OAuthState

    tok, ws = _owner(api, "x26-bare")
    cat = _catalogue(api, tok, ws)
    assert cat["simulated"] is False
    items = _items(cat)
    assert set(items) == set(READY) | COMING
    for key in ("google_calendar", "microsoft_calendar"):
        assert items[key]["status"] == "not_implemented", items[key]
        assert ("GOOGLE_OAUTH_CLIENT_ID" if key == "google_calendar" else "MICROSOFT_OAUTH_CLIENT_ID") in items[key]["reason"]
        assert items[key]["simulated"] is False
    assert items["twilio_sms"]["status"] == "not_implemented" and "TELEPHONY_PROVIDER" in items["twilio_sms"]["reason"]
    assert items["bookings"]["status"] == "not_connected"  # built-in: available, but online booking is off
    for key in ("webhook", "zapier", "make"):  # pure HTTP sinks need no provider account: really available
        assert items[key]["status"] == "not_connected" and items[key]["simulated"] is False
    for key in COMING:
        assert items[key]["status"] == "not_implemented" and items[key]["availability"] == "coming"
    # A not-implemented connector can never be connected, and the attempt leaves no state behind.
    for key in ("google_calendar", "microsoft_calendar", "twilio_sms", "hubspot"):
        r = api.post(tok, f"/workspaces/{ws}/integrations/{key}/connect", {"config": {}, "secrets": {}})
        assert r.status_code in (404, 501), (key, r.status_code, r.text)
    assert db.scalar(select(func.count()).select_from(IntegrationConnection)) == 0
    assert db.scalar(select(func.count()).select_from(OAuthState)) == 0
    # Nothing green anywhere: no connector reports connected.
    assert not [k for k, v in _items(_catalogue(api, tok, ws)).items() if v["status"] == "connected"]


def test_staging_without_credentials_key_reports_secret_connectors_unavailable(api, bare_env):
    tok, ws = _owner(api, "x26-ck")
    _set(bare_env, APP_ENV="staging", SECRET_KEY="s" * 40, ENABLE_DEV_TOOLS="false",
         GOOGLE_OAUTH_CLIENT_ID="dummy-client-id", GOOGLE_OAUTH_CLIENT_SECRET="dummy-client-secret")
    items = _items(_catalogue(api, tok, ws))
    for key in ("google_calendar", "webhook", "zapier", "make"):
        assert items[key]["status"] == "not_implemented", items[key]
        assert "CREDENTIALS_KEY" in items[key]["reason"]


# --------------------------------------------------------------------------- fake adapters

def test_fake_mode_every_connection_and_action_is_labelled_simulated(api, client, bare_env, db):
    from app.models import ActionRun, IntegrationConnection

    _set(bare_env, CONNECTORS_PROVIDER="fake")
    tok, ws = _owner(api, "x26-fake")
    cat = _catalogue(api, tok, ws)
    assert cat["simulated"] is True
    r = api.post(tok, f"/workspaces/{ws}/integrations/google_calendar/connect", {"config": {}, "secrets": {}})
    assert r.status_code == 200, r.text
    url = urlparse(r.json()["authorize_url"])
    assert parse_qs(url.query)["code"] == ["fake-code"]  # simulated consent: no provider is contacted
    back = client.get(url.path + "?" + url.query, follow_redirects=False)
    assert back.status_code == 303 and "connected=google_calendar" in back.headers["location"]
    g = _items(_catalogue(api, tok, ws))["google_calendar"]
    assert g["status"] == "connected" and g["simulated"] is True
    r = api.post(tok, f"/workspaces/{ws}/integrations/twilio_sms/connect", {"config": {}, "secrets": {}})
    assert r.status_code == 200 and r.json()["simulated"] is True, r.text
    r = api.post(tok, f"/workspaces/{ws}/integrations/twilio_sms/run",
                 {"action": "send_sms_bekraeftelse", "input": {"skabelon": "ring_tilbage", "til": "+4512345678"}})
    assert r.status_code == 200, r.text
    assert r.json()["run"]["simulated"] is True and r.json()["text"].endswith("(simuleret)")
    assert len(WORLD.sms) == 1  # recorded in-process only
    db.expire_all()
    assert all(c.simulated for c in db.query(IntegrationConnection).all())
    assert all(rn.simulated for rn in db.query(ActionRun).all())


# --------------------------------------------------------------------------- live adapters, provider stubbed

class _StubTwilio:
    """Stands in for TwilioClient: every request is refused like Twilio does for bad/expired credentials."""

    account_sid = "ACstub0000000000000000000000000000"

    def __init__(self):
        self.calls: list[tuple[str, str]] = []

    def _req(self, method, path, **kw):
        from app.modules.telephony.providers import ProviderError

        self.calls.append((method, path))
        raise ProviderError("Twilio afviste (401): Authenticate", retryable=False)


@pytest.fixture
def live_sms(bare_env, monkeypatch):
    from app.modules.telephony import providers as prov

    stub = _StubTwilio()
    monkeypatch.setattr(prov, "providers", lambda: (stub, object()))
    get_settings.cache_clear()
    return stub


def test_live_sms_connect_is_not_verified_against_twilio(api, live_sms):
    """'connected' must mean 'the last real call succeeded' (connectors/__init__.py docstring). Connecting SMS makes
    no Twilio call at all, so credentials Twilio refuses still give a green «Forbundet»."""
    tok, ws = _owner(api, "x26-sms1")
    r = api.post(tok, f"/workspaces/{ws}/integrations/twilio_sms/connect", {"config": {}, "secrets": {}})
    assert r.status_code == 200 and r.json()["simulated"] is False, r.text
    sms = _items(_catalogue(api, tok, ws))["twilio_sms"]
    assert live_sms.calls, "connect reported 'connected' without a single call to Twilio (F-IQ-01)"
    assert sms["status"] != "connected", sms


def test_live_sms_stays_connected_after_twilio_refuses_and_test_button_says_it_works(api, live_sms):
    tok, ws = _owner(api, "x26-sms2")
    assert api.post(tok, f"/workspaces/{ws}/integrations/twilio_sms/connect", {"config": {}, "secrets": {}}).status_code == 200
    r = api.post(tok, f"/workspaces/{ws}/integrations/twilio_sms/run",
                 {"action": "send_sms_bekraeftelse", "input": {"skabelon": "ring_tilbage", "til": "+4512345678"}})
    assert r.status_code == 200, r.text
    assert r.json()["run"]["status"] == "failed" and "401" in (r.json()["run"]["error"] or "")
    assert live_sms.calls == [("POST", f"/Accounts/{_StubTwilio.account_sid}/Messages.json")]
    # After Twilio refused the credentials the owner must not see a green connection …
    sms = _items(_catalogue(api, tok, ws))["twilio_sms"]
    problems = []
    if sms["status"] == "connected":
        problems.append(f"catalogue still says connected after a 401 from Twilio: {sms}")
    # … and «Test forbindelse» must not answer «Forbindelsen virker» without asking Twilio.
    t = api.post(tok, f"/workspaces/{ws}/integrations/twilio_sms/test", {}, **{"Idempotency-Key": "x26-sms2-test"})
    assert t.status_code == 200, t.text
    if t.json()["ok"] is True:
        problems.append(f"/test says ok while every SMS fails: {t.json()}")
    assert not problems, " | ".join(problems)


def test_google_connected_although_calendar_events_scope_was_not_granted(api, client, bare_env, monkeypatch):
    """Google's granular consent lets the customer untick calendar.events. The callback verifies with freeBusy only
    and stores the granted scopes without checking them, so the card turns green although no booking can ever be
    written to the calendar."""
    _set(bare_env, GOOGLE_OAUTH_CLIENT_ID="dummy-client-id", GOOGLE_OAUTH_CLIENT_SECRET="dummy-client-secret")
    granted = "openid https://www.googleapis.com/auth/userinfo.email https://www.googleapis.com/auth/calendar.freebusy"
    monkeypatch.setattr(oauth, "exchange", lambda provider, **kw: {
        "access_token": "stub-access", "refresh_token": "stub-refresh", "expires_in": 3600, "scope": granted})
    http_calls: list[tuple[str, str]] = []

    def fake_http(method, url, token, **kw):
        http_calls.append((method, url))
        if url.endswith("/freeBusy"):
            return {"calendars": {"primary": {"busy": []}}}
        raise AssertionError(f"unexpected provider call {method} {url}")

    monkeypatch.setattr(cal, "_http", fake_http)
    tok, ws = _owner(api, "x26-scope")
    r = api.post(tok, f"/workspaces/{ws}/integrations/google_calendar/connect", {"config": {}, "secrets": {}})
    assert r.status_code == 200, r.text
    url = urlparse(r.json()["authorize_url"])
    q = parse_qs(url.query)
    assert set(q["scope"][0].split()) == {"https://www.googleapis.com/auth/calendar.events",
                                          "https://www.googleapis.com/auth/calendar.freebusy", "openid", "email"}
    back = client.get(f"/api/v1/integrations/oauth/google_calendar/callback?state={q['state'][0]}&code=stub-code",
                      follow_redirects=False)
    assert back.status_code == 303
    g = _items(_catalogue(api, tok, ws))["google_calendar"]
    assert ("POST", "https://www.googleapis.com/calendar/v3/freeBusy") in http_calls
    assert not ("connected=google_calendar" in back.headers["location"] and g["status"] == "connected"), (
        "Google shows «Forbundet» without the calendar.events scope (F-IQ-02): " + back.headers["location"])


# --------------------------------------------------------------------------- capability registry (/integrations/capabilities)

def _caps(api, tok) -> dict:
    r = api.get(tok, "/integrations/capabilities")
    assert r.status_code == 200, r.text
    return {c["key"]: c for c in r.json()["items"]}


def test_capabilities_without_env_say_not_implemented(api, bare_env):
    tok, _ = _owner(api, "x26-caps")
    caps = _caps(api, tok)
    for key in ("telephony.inbound", "telephony.outbound", "payment", "cvr.lookup"):
        assert caps[key]["status"] == "not_implemented", caps[key]
    assert caps["email"]["status"] == "simulated"


def test_payment_capability_available_without_webhook_secret(api, bare_env):
    """Without STRIPE_WEBHOOK_SECRET the webhook answers 503, so a card saved in Checkout never reaches Dialogbot –
    yet the capability says 'available' (its own not-configured note names both variables)."""
    _set(bare_env, STRIPE_SECRET_KEY="sk_test_dummy_not_a_real_key")
    tok, _ = _owner(api, "x26-pay")
    cap = _caps(api, tok)["payment"]
    assert cap["status"] != "available", f"payment is 'available' without STRIPE_WEBHOOK_SECRET (F-IQ-03): {cap}"


def test_stripe_test_mode_is_visible_in_status_and_account(api, bare_env):
    """A test-mode key must be shown as test mode – not as plain 'available' / configured."""
    _set(bare_env, STRIPE_SECRET_KEY="sk_test_dummy_not_a_real_key", STRIPE_WEBHOOK_SECRET="whsec_dummy")
    tok, ws = _owner(api, "x26-paytest")
    cap = _caps(api, tok)["payment"]
    acc = api.get(tok, f"/workspaces/{ws}/billing/account").json()
    problems = []
    if cap["status"] == "available":
        problems.append(f"capability status is 'available' for an sk_test_ key (only the note says testtilstand): {cap['status']}")
    if not any(k in acc for k in ("test_mode", "mode", "livemode", "environment")):
        problems.append(f"/billing/account has no test-mode field: keys={sorted(acc)}")
    assert not problems, "F-IQ-03: " + " | ".join(problems)


def test_fake_telephony_is_reported_as_simulated(api, bare_env):
    _set(bare_env, TELEPHONY_PROVIDER="fake", VAPI_SERVER_SECRET="dummy-vapi-secret-0123456789abcdef")
    tok, _ = _owner(api, "x26-tel")
    cap = _caps(api, tok)["telephony.inbound"]
    assert cap["status"] == "simulated", f"fake telephony reported as {cap['status']!r} (F-IQ-05)"


# --------------------------------------------------------------------------- Privat apps: 17TRACK, Duffel, Travelpayouts

def test_privat_apps_coming_soon_without_keys(bare_env):
    from app.modules.privat import addons, parcels, travel

    assert addons.CATALOG["pakker"].live_status == "coming_soon"
    assert addons.CATALOG["rejser"].live_status == "coming_soon"
    assert travel.providers() == []
    with pytest.raises(parcels.TrackError):
        parcels.tracker()


def test_rejser_available_with_travelpayouts_token_but_no_marker(bare_env):
    """needs_setting=('duffel_access_token','travelpayouts_token') says the app works, but travel.providers() only uses
    Travelpayouts together with TRAVELPAYOUTS_MARKER – every search then answers «Jeg fandt ingen rejser»."""
    from app.modules.privat import addons, travel

    _set(bare_env, TRAVELPAYOUTS_TOKEN="dummy-token")
    assert travel.configured() is False
    assert addons.CATALOG["rejser"].live_status == "coming_soon", "F-IQ-06: Rejser is offered with no working provider"


@pytest.mark.parametrize("env", [{"TRACK17_API_KEY": "fake"}, {"DUFFEL_ACCESS_TOKEN": "fake"},
                                 {"TRAVELPAYOUTS_TOKEN": "fake"}])
def test_privat_test_doubles_are_refused_outside_dev_test(monkeypatch, env):
    """CONNECTORS_PROVIDER/TELEPHONY_PROVIDER/TTS_ENGINE=fake are refused in staging/prod (config._fail_closed); the
    magic value 'fake' for these keys switches in a test double in ANY environment."""
    base = {"APP_ENV": "prod", "SECRET_KEY": "p" * 40, "ENABLE_DEV_TOOLS": "false", "EMAIL_ADAPTER": "resend",
            "RESEND_API_KEY": "dummy", "DATABASE_URL": "postgresql+psycopg://x@localhost/none"}
    for k in INTEGRATION_ENV:
        monkeypatch.delenv(k, raising=False)
    for k, v in {**base, **env}.items():
        monkeypatch.setenv(k, v)
    with pytest.raises(ValueError):
        Settings()  # type: ignore[call-arg]


def test_privat_fake_doubles_report_live_status_in_prod_shaped_settings(monkeypatch):
    """What a prod process with TRACK17_API_KEY=fake would show today (evidence for F-IQ-04)."""
    from app.modules.privat import addons, parcels

    monkeypatch.setenv("TRACK17_API_KEY", "fake")
    get_settings.cache_clear()
    try:
        assert addons.CATALOG["pakker"].live_status == "available"
        assert isinstance(parcels.tracker(), parcels.FakeTracker)
    finally:
        get_settings.cache_clear()

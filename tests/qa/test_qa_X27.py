"""QA X27 (integrations-qa, bølge 2 / M2): Google Calendar OAuth (testing, simuleret ved adaptergrænsen) – forbind,
afvist samtykke, refresh, tilbagekaldt token, scopes præcis som godkendt.

Ingen netværkskald: Googles token-endpoint (oauth._token_request / httpx.post) og Calendar-API'et (calendar._http)
er stubbet. Env-variabler er dummies; ingen hemmeligheder læses. Supplerer tests/test_integrations_actions.py
(state/PKCE, refresh happy path) og tests/qa/test_qa_integ_X26.py (delvist samtykke, F-IQ-02).
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from sqlalchemy import select

from app.config import get_settings
from app.models import AuditLog, IntegrationConnection, OAuthState
from app.modules.integrations import credentials, oauth
from app.modules.integrations.connectors import calendar as cal

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
GRANTED = ("openid https://www.googleapis.com/auth/userinfo.email https://www.googleapis.com/auth/calendar.events "
           "https://www.googleapis.com/auth/calendar.freebusy")


def _idtok(email: str) -> str:
    import base64

    return "e30." + base64.urlsafe_b64encode(json.dumps({"email": email}).encode()).decode().rstrip("=") + ".sig"


@pytest.fixture
def google(monkeypatch):
    """Live-mode Google (CONNECTORS_PROVIDER=live) with the provider stubbed at the adapter boundary."""
    monkeypatch.setenv("CONNECTORS_PROVIDER", "live")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "dummy-cid.apps.googleusercontent.com")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_SECRET", "dummy-secret")
    get_settings.cache_clear()
    state = {"token_calls": [], "token_answer": None, "api_calls": [], "api_status": 200, "revoked": [],
             "revoke_fail": False}

    def token_request(provider, data):
        state["token_calls"].append(dict(data))
        ans = state["token_answer"]
        if isinstance(ans, Exception):
            raise ans
        return ans or {"access_token": f"ya29.stub-{len(state['token_calls'])}", "refresh_token": "1//stub-refresh",
                       "expires_in": 3600, "token_type": "Bearer", "scope": GRANTED, "id_token": _idtok("ejer@fjord.dk")}

    def http(method, url, token, **kw):
        state["api_calls"].append((method, url, token))
        if state["api_status"] == 401:
            raise cal.ActionError("Kalenderforbindelsen er ikke længere gyldig – forbind kalenderen igen",
                                  code="provider_unauthorized")
        if url.endswith("/freeBusy"):
            return {"calendars": {"primary": {"busy": []}}}
        return {"id": "evt1"}

    real_post = httpx.post

    def post(url, *a, **kw):
        if str(url).startswith("https://oauth2.googleapis.com/revoke"):
            if state["revoke_fail"]:
                raise httpx.ConnectError("down")
            state["revoked"].append((kw.get("params") or {}).get("token"))
            return httpx.Response(200)
        return real_post(url, *a, **kw)

    monkeypatch.setattr(oauth, "_token_request", token_request)
    monkeypatch.setattr(cal, "_http", http)
    monkeypatch.setattr(httpx, "post", post)
    yield state
    get_settings.cache_clear()


def _start(api, t):
    r = api.post(t["tok_a"], f"/workspaces/{t['ws_a']}/integrations/google_calendar/connect", {"config": {}, "secrets": {}})
    assert r.status_code == 200, r.text
    return r.json()["authorize_url"]


def _cb(client, state, **q):
    qs = "&".join(f"{k}={v}" for k, v in {"state": state, **q}.items())
    return client.get(f"/api/v1/integrations/oauth/google_calendar/callback?{qs}", follow_redirects=False)


def _item(api, t):
    return next(x for x in api.get(t["tok_a"], f"/workspaces/{t['ws_a']}/integrations").json()["items"]
                if x["key"] == "google_calendar")


def _connect(api, client, t):
    q = parse_qs(urlparse(_start(api, t)).query)
    r = _cb(client, q["state"][0], code="4/stub")
    assert r.status_code == 303 and r.headers["location"].endswith("connected=google_calendar"), r.headers["location"]


# --------------------------------------------------------------------------- connect + scopes

def test_authorize_url_asks_exactly_the_approved_scopes_offline_with_pkce(api, client, two_workspaces, google, db):
    t = two_workspaces
    url = urlparse(_start(api, t))
    q = parse_qs(url.query)
    assert f"{url.scheme}://{url.netloc}{url.path}" == "https://accounts.google.com/o/oauth2/v2/auth"
    assert set(q["scope"][0].split()) == {"openid", "email", "https://www.googleapis.com/auth/calendar.events",
                                          "https://www.googleapis.com/auth/calendar.freebusy"}
    assert q["access_type"] == ["offline"] and q["prompt"] == ["consent"] and q["response_type"] == ["code"]
    assert q["code_challenge_method"] == ["S256"] and "code_verifier" not in q
    assert q["redirect_uri"][0].endswith("/api/v1/integrations/oauth/google_calendar/callback")
    assert q["client_id"] == ["dummy-cid.apps.googleusercontent.com"] and "client_secret" not in q
    # connect works; stored scopes are what Google granted; tokens are encrypted and never shown
    r = _cb(client, q["state"][0], code="4/stub")
    assert r.headers["location"].endswith("connected=google_calendar")
    conn = db.scalar(select(IntegrationConnection).where(IntegrationConnection.connector == "google_calendar"))
    assert set(conn.scopes) == set(GRANTED.split()) and not conn.simulated and conn.account_label == "ejer@fjord.dk"
    assert b"ya29" not in bytes(conn.secret_blob)
    page = api.get(t["tok_a"], f"/workspaces/{t['ws_a']}/integrations").text
    assert "ya29" not in page and "1//stub" not in page
    assert _item(api, t)["status"] == "connected"


def test_staff_and_reader_cannot_start_oauth_and_other_tenant_cannot_use_the_state(api, client, two_workspaces, google, db):
    t = two_workspaces
    staff = api.add_member(t["tok_a"], t["ws_a"], "staff-x27@testmail.dk", "staff")
    assert api.post(staff, f"/workspaces/{t['ws_a']}/integrations/google_calendar/connect",
                    {"config": {}, "secrets": {}}).status_code == 403
    # B starts; the callback lands B's state – it can only ever connect B's workspace
    r = api.post(t["tok_b"], f"/workspaces/{t['ws_b']}/integrations/google_calendar/connect", {"config": {}, "secrets": {}})
    s = parse_qs(urlparse(r.json()["authorize_url"]).query)["state"][0]
    _cb(client, s, code="4/stub")
    rows = db.scalars(select(IntegrationConnection)).all()
    assert [str(c.workspace_id) for c in rows] == [t["ws_b"]]
    assert _item(api, t)["status"] == "not_connected"


# --------------------------------------------------------------------------- consent denied

def test_consent_denied_creates_nothing_burns_state_and_says_so(api, client, two_workspaces, google, db):
    t = two_workspaces
    s = parse_qs(urlparse(_start(api, t)).query)["state"][0]
    r = _cb(client, s, error="access_denied")
    assert r.status_code == 303
    loc = urlparse(r.headers["location"])
    assert loc.path == "/app/settings/integrationer" and parse_qs(loc.query) == {"error": ["oauth_denied"],
                                                                                "connector": ["google_calendar"]}
    assert google["token_calls"] == [] and google["api_calls"] == []
    assert db.scalar(select(IntegrationConnection)) is None
    assert db.get(OAuthState, s).used_at is not None
    # the burned state cannot be replayed with a code afterwards
    again = _cb(client, s, code="4/late")
    assert "error=oauth_state_expired" in again.headers["location"] and db.scalar(select(IntegrationConnection)) is None
    assert _item(api, t)["status"] == "not_connected"
    actions = [a.action for a in db.scalars(select(AuditLog)).all()]
    assert "integrations.oauth_started" in actions and "integrations.connected" not in actions


def test_failed_reconnect_keeps_the_working_connection(api, client, two_workspaces, google, db):
    t = two_workspaces
    _connect(api, client, t)
    google["token_answer"] = {"access_token": "ya29.partial", "refresh_token": "1//p", "expires_in": 3600,
                              "scope": "openid https://www.googleapis.com/auth/calendar.freebusy"}
    s = parse_qs(urlparse(_start(api, t)).query)["state"][0]
    r = _cb(client, s, code="4/partial")
    assert "error=oauth_scope_missing" in r.headers["location"]
    conn = db.scalar(select(IntegrationConnection))
    assert conn.status == "connected" and credentials.get_secret(conn)["access_token"] == "ya29.stub-1"


@pytest.mark.xfail(strict=True, reason="F-M2-12-X27: S2 new – Afvist samtykke og manglende kalenderadgang i Google vises som rå fejlkode: «Google Kalender blev ikke …")
def test_callback_errors_are_explained_in_words_not_codes():
    """UI'et (settings/integrationer/client.tsx) viser `errorNotice` med den rå kode: «Google Kalender blev ikke
    forbundet (oauth_scope_missing). Prøv igen …». API'ets forklaring («Giv Dialogbot lov til at oprette og se aftaler
    i kalenderen, og forbind igen») går tabt i redirecten. Kravet (X26/X27, agentdefinitionen): ærlig, forståelig
    besked ved afvist samtykke og manglende scope."""
    missing = {}
    for loc in ("da", "en", "de", "es", "fr", "it", "no", "sv"):
        msgs = json.load(open(os.path.join(ROOT, "web", "src", "i18n", "messages", loc, "settings.json"), encoding="utf-8"))
        flat = json.dumps(msgs, ensure_ascii=False)
        for code in ("oauth_denied", "oauth_scope_missing", "oauth_state_expired", "oauth_invalid_grant"):
            if f'"{code}"' not in flat:
                missing.setdefault(loc, []).append(code)
    assert not missing, f"ingen oversat tekst pr. fejlkode – brugeren ser koden: {missing}"


# --------------------------------------------------------------------------- refresh / revoked

def _expire(db, t):
    conn = db.scalar(select(IntegrationConnection).where(IntegrationConnection.workspace_id == uuid.UUID(t["ws_a"])))
    conn.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    db.commit()
    return conn


def test_expired_access_token_is_refreshed_before_use_and_kept_encrypted(api, client, two_workspaces, google, db):
    t = two_workspaces
    _connect(api, client, t)
    _expire(db, t)
    google["token_answer"] = {"access_token": "ya29.fresh", "expires_in": 3599, "token_type": "Bearer"}
    busy, readable = cal.connected_busy(db, uuid.UUID(t["ws_a"]), datetime.now(UTC), datetime.now(UTC) + timedelta(hours=2))
    db.commit()
    assert readable and busy == []
    assert google["token_calls"][-1]["grant_type"] == "refresh_token"
    assert google["token_calls"][-1]["refresh_token"] == "1//stub-refresh"
    assert google["api_calls"][-1][2] == "ya29.fresh"  # the new token was used
    db.expire_all()
    conn = db.scalar(select(IntegrationConnection))
    sec = credentials.get_secret(conn)
    assert sec["access_token"] == "ya29.fresh" and sec["refresh_token"] == "1//stub-refresh"  # Google omits it on refresh
    assert conn.expires_at > datetime.now(UTC) + timedelta(minutes=50) and conn.status == "connected"


def test_revoked_refresh_token_turns_the_card_to_error_and_reconnect_heals(api, client, two_workspaces, google, db):
    t = two_workspaces
    _connect(api, client, t)
    _expire(db, t)
    google["token_answer"] = oauth.OAuthFailed("Leverandøren afviste forbindelsen (invalid_grant).", code="oauth_invalid_grant")
    busy, readable = cal.connected_busy(db, uuid.UUID(t["ws_a"]), datetime.now(UTC), datetime.now(UTC) + timedelta(hours=2))
    db.commit()
    assert busy == [] and readable is False  # fail-open slots, bookings await confirmation (BK15)
    item = _item(api, t)
    assert item["status"] == "error" and "forbind" in (item["error"] or "").lower()
    assert "1//stub" not in json.dumps(item) and "ya29" not in json.dumps(item)
    # the test button tells the truth as well
    r = api.post(t["tok_a"], f"/workspaces/{t['ws_a']}/integrations/google_calendar/test", **{"Idempotency-Key": "x27-t"})
    assert r.json()["ok"] is False
    # reconnect heals
    google["token_answer"] = None
    _connect(api, client, t)
    assert _item(api, t)["status"] == "connected" and _item(api, t)["error"] is None


def test_access_token_revoked_at_google_before_expiry_is_reported(api, client, two_workspaces, google, db):
    t = two_workspaces
    _connect(api, client, t)
    google["api_status"] = 401
    busy, readable = cal.connected_busy(db, uuid.UUID(t["ws_a"]), datetime.now(UTC), datetime.now(UTC) + timedelta(hours=2))
    db.commit()
    assert readable is False
    assert _item(api, t)["status"] == "error"
    google["api_status"] = 200  # access restored: the next read clears the read error by itself
    busy, readable = cal.connected_busy(db, uuid.UUID(t["ws_a"]), datetime.now(UTC), datetime.now(UTC) + timedelta(hours=2))
    db.commit()
    assert readable and _item(api, t)["status"] == "connected"


# --------------------------------------------------------------------------- disconnect / revocation at Google

def test_disconnect_revokes_at_google_and_deletes_tokens_even_if_google_is_down(api, client, two_workspaces, google, db):
    t = two_workspaces
    _connect(api, client, t)
    assert api.delete(t["tok_a"], f"/workspaces/{t['ws_a']}/integrations/google_calendar").status_code == 204
    assert set(google["revoked"]) == {"1//stub-refresh", "ya29.stub-1"}
    assert db.scalar(select(IntegrationConnection)) is None
    _connect(api, client, t)
    google["revoke_fail"] = True
    assert api.delete(t["tok_a"], f"/workspaces/{t['ws_a']}/integrations/google_calendar").status_code == 204
    assert db.scalar(select(IntegrationConnection)) is None


@pytest.mark.xfail(strict=True, reason="F-M2-13-X27: S3 new – Forbinder ejeren Google Kalender igen (fx med en anden konto), overskrives den gamle nøgle uden at blive …")
def test_reconnecting_with_another_account_revokes_the_old_grant(api, client, two_workspaces, google, db):
    """/privatliv: «Du kan afbryde forbindelsen når som helst … så tilbagekalder vi adgangen og sletter nøglerne».
    Forbinder ejeren igen (fx med en anden Google-konto), overskriver _upsert den gamle nøgle uden at tilbagekalde
    den hos Google – den gamle konto har stadig givet Dialogbot adgang, men Dialogbot har smidt nøglen væk."""
    t = two_workspaces
    _connect(api, client, t)
    google["token_answer"] = {"access_token": "ya29.other", "refresh_token": "1//other-refresh", "expires_in": 3600,
                              "scope": GRANTED, "id_token": _idtok("anden@konto.dk")}
    _connect(api, client, t)
    conn = db.scalar(select(IntegrationConnection))
    assert conn.account_label == "anden@konto.dk"
    assert "1//stub-refresh" in google["revoked"], \
        f"den tidligere kontos refresh-token blev ikke tilbagekaldt (revoked={google['revoked']})"

"""OAuth 2.0 authorization code flow with PKCE and a single-use state, for Google and Microsoft.

Dialogbot owns the OAuth clients (GOOGLE_OAUTH_CLIENT_ID/SECRET, MICROSOFT_OAUTH_CLIENT_ID/SECRET); the customer
only clicks "Forbind" and consents at the provider. The provider redirects to
`{PUBLIC_BASE_URL}/api/v1/integrations/oauth/{connector}/callback`, which is not a workspace route: the `state`
row tells us which workspace and user started the attempt. Tokens are exchanged server-side and stored encrypted.

Provider endpoints as documented by Google (developers.google.com/identity/protocols/oauth2/web-server) and
Microsoft (learn.microsoft.com/entra/identity-platform/v2-oauth2-auth-code-flow), read 29/9 2026.
"""
from __future__ import annotations

import base64
import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

from sqlalchemy.orm import Session as OrmSession

from app.config import get_settings
from app.core import crypto
from app.core.errors import ApiError, NotFound
from app.models import OAuthState

STATE_TTL = timedelta(minutes=10)


class OAuthFailed(ApiError):
    status_code = 502
    code = "oauth_failed"


@dataclass(frozen=True)
class OAuthProvider:
    key: str
    authorize_url: str
    token_url: str
    scopes: tuple[str, ...]
    revoke_url: str | None = None
    extra_authorize: dict | None = None

    def client(self) -> tuple[str | None, str | None]:
        s = get_settings()
        if self.key == "google":
            return s.google_oauth_client_id, s.google_oauth_client_secret
        return s.microsoft_oauth_client_id, s.microsoft_oauth_client_secret

    def configured(self) -> bool:
        cid, secret = self.client()
        return bool(cid and secret)


def _ms_base() -> str:
    return f"https://login.microsoftonline.com/{get_settings().microsoft_oauth_tenant}/oauth2/v2.0"


GOOGLE = OAuthProvider(
    key="google",
    authorize_url="https://accounts.google.com/o/oauth2/v2/auth",
    token_url="https://oauth2.googleapis.com/token",
    revoke_url="https://oauth2.googleapis.com/revoke",
    # Narrowest scopes for the use case: calendar.events (create/move/cancel) and calendar.freebusy (busy time).
    scopes=("https://www.googleapis.com/auth/calendar.events", "https://www.googleapis.com/auth/calendar.freebusy",
            "openid", "email"),
    # offline = refresh token; consent = a refresh token also on re-authorization.
    extra_authorize={"access_type": "offline", "prompt": "consent", "include_granted_scopes": "true"},
)
MICROSOFT = OAuthProvider(
    key="microsoft",
    authorize_url="",  # built per tenant, see provider_for()
    token_url="",
    scopes=("Calendars.ReadWrite", "User.Read", "offline_access", "openid", "email"),
    extra_authorize={"response_mode": "query"},
)


def provider_for(key: str) -> OAuthProvider:
    if key == "google":
        return GOOGLE
    if key == "microsoft":
        base = _ms_base()
        return OAuthProvider(key="microsoft", authorize_url=f"{base}/authorize", token_url=f"{base}/token",
                             scopes=MICROSOFT.scopes, extra_authorize=MICROSOFT.extra_authorize)
    raise KeyError(key)


def redirect_uri(connector: str) -> str:
    return f"{get_settings().public_base_url.rstrip('/')}/api/v1/integrations/oauth/{connector}/callback"


def _challenge(verifier: str) -> str:
    return base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")


def start(db: OrmSession, *, workspace_id: uuid.UUID, connector: str, provider: OAuthProvider,
          user_id: uuid.UUID | None) -> str:
    """Create the state row and return the URL the customer's browser must open."""
    cid, _ = provider.client()
    if not cid:
        raise ApiError("OAuth-klienten er ikke konfigureret", code="oauth_not_configured", status_code=501)
    verifier = secrets.token_urlsafe(64)
    state = secrets.token_urlsafe(32)
    env = crypto.encrypt(verifier.encode(), aad=state.encode())
    db.add(OAuthState(state=state, workspace_id=workspace_id, connector=connector, user_id=user_id,
                      key_version=env.key_version, verifier_blob=env.blob, expires_at=datetime.now(UTC) + STATE_TTL))
    db.flush()
    params = {"client_id": cid, "redirect_uri": redirect_uri(connector), "response_type": "code",
              "scope": " ".join(provider.scopes), "state": state, "code_challenge": _challenge(verifier),
              "code_challenge_method": "S256", **(provider.extra_authorize or {})}
    return f"{provider.authorize_url}?{urlencode(params)}"


def consume_state(db: OrmSession, state: str, connector: str) -> tuple[OAuthState, str]:
    """Look up and burn the state. Returns the row and the PKCE verifier."""
    row = db.get(OAuthState, state, with_for_update=True) if state else None
    if row is None or row.connector != connector:
        raise NotFound("Forbindelsesforsøget kendes ikke. Start forfra fra Integrationer.", code="oauth_state_unknown")
    now = datetime.now(UTC)
    if row.used_at is not None or row.expires_at < now:
        raise ApiError("Forbindelsesforsøget er udløbet eller allerede brugt. Start forfra fra Integrationer.",
                       code="oauth_state_expired", status_code=409)
    row.used_at = now
    verifier = crypto.decrypt(crypto.Envelope(row.key_version, bytes(row.verifier_blob)), aad=state.encode()).decode()
    return row, verifier


def exchange(provider: OAuthProvider, *, code: str, verifier: str, connector: str) -> dict:
    """Authorization code → tokens. Returns the provider's token JSON (never logged)."""
    cid, secret = provider.client()
    data = {"grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri(connector),
            "client_id": cid, "client_secret": secret, "code_verifier": verifier}
    return _token_request(provider, data)


def refresh(provider: OAuthProvider, refresh_token: str) -> dict:
    cid, secret = provider.client()
    data = {"grant_type": "refresh_token", "refresh_token": refresh_token, "client_id": cid, "client_secret": secret}
    if provider.key == "microsoft":
        data["scope"] = " ".join(provider.scopes)
    return _token_request(provider, data)


def _token_request(provider: OAuthProvider, data: dict) -> dict:
    import httpx

    try:
        r = httpx.post(provider.token_url, data=data, timeout=20.0)
    except httpx.HTTPError as e:
        raise OAuthFailed("Leverandøren svarede ikke under forbindelsen. Prøv igen.") from e
    if r.status_code >= 400:
        try:
            err = r.json().get("error", "")
        except ValueError:
            err = ""
        code = "oauth_invalid_grant" if err == "invalid_grant" else "oauth_failed"
        raise OAuthFailed(f"Leverandøren afviste forbindelsen ({err or r.status_code}).", code=code)
    tok = r.json()
    if not tok.get("access_token"):
        raise OAuthFailed("Leverandøren udleverede ikke et token.")
    return tok


def revoke(provider: OAuthProvider, token: str) -> None:
    """Best effort; Microsoft has no token revocation endpoint (the customer removes the app under their account)."""
    import httpx

    if not provider.revoke_url:
        return
    try:
        httpx.post(provider.revoke_url, params={"token": token}, timeout=10.0)
    except httpx.HTTPError:
        pass


def token_secret(tok: dict, previous: dict | None = None) -> tuple[dict, datetime | None]:
    """Normalize a token response into the stored secret + expiry. Keeps the old refresh token when the provider
    does not return a new one (Google omits it on refresh)."""
    secret = {"access_token": tok["access_token"], "token_type": tok.get("token_type", "Bearer"),
              "refresh_token": tok.get("refresh_token") or (previous or {}).get("refresh_token"),
              "id_token": tok.get("id_token")}
    expires = None
    if isinstance(tok.get("expires_in"), int | float):
        expires = datetime.now(UTC) + timedelta(seconds=int(tok["expires_in"]))
    return secret, expires


def id_token_email(id_token: str | None) -> str:
    """The account e-mail from the (unverified) id_token payload – only used as a label the customer sees."""
    import json

    if not id_token or id_token.count(".") != 2:
        return ""
    try:
        payload = id_token.split(".")[1]
        data = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        return str(data.get("email") or data.get("preferred_username") or "")[:200]
    except (ValueError, UnicodeDecodeError):
        return ""
